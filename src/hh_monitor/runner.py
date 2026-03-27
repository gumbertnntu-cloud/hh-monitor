from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .auth import validate_state
from .crawler import CrawlStats, crawl_vacancy_details
from .filters import filter_vacancy, match_exclude_keywords
from .hh_api import HHApiClient, vacancy_needs_browser_dd
from .models import ChangeRow, RunParams, RunStats, SeenVacancyRow, Vacancy
from .report import generate_html_report
from .storage import (
    begin_run,
    finish_run,
    get_active_hashes,
    get_run_change_rows,
    get_run_seen_rows,
    get_vacancies_by_ids,
    get_vacancy_by_id,
    init_db,
    insert_change,
    insert_run_item,
    mark_removed,
    upsert_vacancy,
)
from .utils import hash_normalized


@dataclass(slots=True)
class RunResult:
    run_id: int
    rows: list[ChangeRow]
    seen_rows: list[SeenVacancyRow]
    stats: RunStats
    html_report_path: Path
    processed_vacancy_ids: list[str]


class SessionInvalidError(RuntimeError):
    pass


def fetch_single_vacancy_detail(
    *,
    project_root: Path,
    settings: object,
    logger: logging.Logger,
    vacancy_id: str,
    progress_callback: Callable[[str], None] | None = None,
) -> Vacancy:
    db_path = project_root / settings.paths.db_path
    state_path = project_root / settings.paths.state_path
    init_db(db_path)

    vacancy = get_vacancy_by_id(db_path, vacancy_id)
    if vacancy is None:
        raise ValueError(f"Vacancy {vacancy_id} is missing in storage. Run fast search first.")

    api_client = HHApiClient(runtime=settings.runtime, logger=logger)
    if progress_callback:
        progress_callback(f"Loading API details for vacancy {vacancy_id}")
    try:
        updated = api_client.fetch_detail(vacancy)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "api detail failed for %s, switching to browser fallback: %s",
            vacancy_id,
            exc,
        )
        vacancy.data_source_status = "fallback_needed"
        updated = vacancy

    if vacancy_needs_browser_dd(updated):
        if not validate_state(settings.search.base_url, state_path, logger):
            raise SessionInvalidError(
                "Session state is missing or expired. Run authorization first."
            )
        if progress_callback:
            progress_callback(f"Loading browser deep-dive for vacancy {vacancy_id}")
        updated_rows, crawl_stats = crawl_vacancy_details(
            vacancies=[updated],
            state_path=state_path,
            runtime=settings.runtime,
            logger=logger,
            progress_callback=progress_callback,
        )
        if crawl_stats.errors:
            raise RuntimeError(crawl_stats.errors[0])
        if not updated_rows:
            raise RuntimeError(f"Deep load returned no data for vacancy {vacancy_id}")
        updated = updated_rows[0]

    updated.normalized_hash = _compute_hash(updated)
    upsert_vacancy(db_path=db_path, vacancy=updated, seen_at=datetime.utcnow())
    return updated


def _compute_hash(vacancy: Vacancy) -> str:
    return hash_normalized(
        [
            vacancy.title,
            vacancy.company,
            vacancy.salary_raw,
            vacancy.area,
            vacancy.snippet,
            vacancy.description,
        ]
    )


def _merge_stats(crawl_stats: CrawlStats, run_stats: RunStats) -> RunStats:
    run_stats.pages_processed = crawl_stats.pages_processed
    run_stats.cards_seen = crawl_stats.cards_seen
    run_stats.cards_after_date_filter = crawl_stats.cards_after_date_filter
    run_stats.deep_opened = crawl_stats.deep_opened
    run_stats.errors.extend(crawl_stats.errors)
    return run_stats


def _run_fast_api_pipeline(
    *,
    base_url: str,
    area: int,
    query_text: str,
    max_pages: int,
    cutoff_dt: datetime,
    runtime: object,
    logger: logging.Logger,
    include_keywords: list[str],
    exclude_keywords: list[str],
    min_salary: int | None,
    progress_callback: Callable[[str], None] | None = None,
) -> tuple[list[Vacancy], CrawlStats]:
    stats = CrawlStats()
    api_client = HHApiClient(runtime=runtime, logger=logger)
    shortlisted: list[Vacancy] = []
    skipped_by_ban = 0
    skipped_by_include = 0

    for index in range(max_pages):
        if progress_callback:
            progress_callback(f"Loading API page {index + 1}/{max_pages}")
        try:
            page_items = api_client.fetch_list_page(
                base_url=base_url,
                area=area,
                query_text=query_text,
                page=index,
            )
        except Exception as exc:  # noqa: BLE001
            message = f"api-page={index}: {exc}"
            logger.error(message)
            stats.errors.append(message)
            continue

        if not page_items:
            break

        stats.pages_processed += 1
        stats.cards_seen += len(page_items)

        eligible: list[Vacancy] = []
        all_old = True
        for vacancy in page_items:
            if vacancy.published_at is None:
                eligible.append(vacancy)
                all_old = False
                continue
            if vacancy.published_at >= cutoff_dt:
                eligible.append(vacancy)
                all_old = False
        stats.cards_after_date_filter += len(eligible)

        for vacancy in eligible:
            excluded, _ = match_exclude_keywords(
                vacancy,
                exclude_keywords,
                include_description=False,
            )
            if excluded:
                skipped_by_ban += 1
                continue
            matched, _ = filter_vacancy(
                vacancy=vacancy,
                include_keywords=include_keywords,
                exclude_keywords=exclude_keywords,
                min_salary=min_salary,
                include_description=False,
                include_snippet=False,
            )
            if matched:
                shortlisted.append(vacancy)
            else:
                skipped_by_include += 1

        if all_old:
            break

    logger.info(
        "api prefilter stats: pages=%s seen=%s after_date=%s "
        "ban_skipped=%s include_skipped=%s shortlisted=%s",
        stats.pages_processed,
        stats.cards_seen,
        stats.cards_after_date_filter,
        skipped_by_ban,
        skipped_by_include,
        len(shortlisted),
    )
    if progress_callback:
        progress_callback(
            "API prefilter: "
            f"seen={stats.cards_seen}, "
            f"after_date={stats.cards_after_date_filter}, "
            f"ban_skipped={skipped_by_ban}, "
            f"include_skipped={skipped_by_include}, "
            f"detail={len(shortlisted)}"
        )

    enriched: list[Vacancy] = []
    for vacancy in shortlisted:
        if progress_callback:
            progress_callback(f"Loading API details for vacancy {vacancy.vacancy_id}")
        try:
            detailed = api_client.fetch_detail(vacancy)
        except Exception as exc:  # noqa: BLE001
            message = f"api-detail={vacancy.vacancy_id}: {exc}"
            logger.error(message)
            stats.errors.append(message)
            vacancy.data_source_status = "api_detail_failed"
            detailed = vacancy
        if detailed.data_source_status == "api_detail":
            stats.deep_opened += 1
        enriched.append(detailed)

    return enriched, stats


def _enrich_queued_vacancies(
    *,
    vacancies: list[Vacancy],
    base_url: str,
    state_path: Path,
    runtime: object,
    logger: logging.Logger,
    progress_callback: Callable[[str], None] | None = None,
) -> tuple[list[Vacancy], CrawlStats]:
    stats = CrawlStats()
    if not vacancies:
        return [], stats

    api_client = HHApiClient(runtime=runtime, logger=logger)
    enriched: list[Vacancy] = []
    browser_queue: list[Vacancy] = []

    for vacancy in vacancies:
        stats.cards_seen += 1
        stats.cards_after_date_filter += 1
        if progress_callback:
            progress_callback(f"Loading API details for queued vacancy {vacancy.vacancy_id}")
        try:
            updated = api_client.fetch_detail(vacancy)
        except Exception as exc:  # noqa: BLE001
            message = f"api-detail={vacancy.vacancy_id}: {exc}"
            logger.error(message)
            stats.errors.append(message)
            vacancy.data_source_status = "fallback_needed"
            updated = vacancy
        if updated.data_source_status == "api_detail":
            stats.deep_opened += 1
        if vacancy_needs_browser_dd(updated):
            browser_queue.append(updated)
        else:
            enriched.append(updated)

    if browser_queue:
        if not validate_state(base_url, state_path, logger):
            raise SessionInvalidError(
                "Session state is missing or expired. Run authorization first."
            )
        browser_rows, browser_stats = crawl_vacancy_details(
            vacancies=browser_queue,
            state_path=state_path,
            runtime=runtime,
            logger=logger,
            progress_callback=progress_callback,
        )
        stats.deep_opened += browser_stats.deep_opened
        stats.errors.extend(browser_stats.errors)
        by_id = {row.vacancy_id: row for row in browser_rows}
        for vacancy in browser_queue:
            enriched.append(by_id.get(vacancy.vacancy_id, vacancy))

    return enriched, stats


def run_pipeline(
    *,
    project_root: Path,
    settings: object,
    logger: logging.Logger,
    deep_target_ids: list[str] | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> RunResult:
    db_path = project_root / settings.paths.db_path
    state_path = project_root / settings.paths.state_path
    report_path = project_root / settings.paths.reports_dir / "latest.html"

    init_db(db_path)

    params = RunParams(
        mode=settings.search.mode,
        max_pages=settings.search.max_pages,
        max_age_days=settings.search.max_age_days,
        query_text=settings.search.query_text,
    )
    cutoff_dt = datetime.now() - timedelta(days=settings.search.max_age_days)
    run_id = begin_run(db_path, params, cutoff_dt)
    if progress_callback:
        progress_callback(f"__RUN_ID__:{run_id}")

    stats = RunStats()
    try:
        deep_targets = deep_target_ids or []
        if settings.search.mode == "deep" and deep_targets:
            queued_vacancies = get_vacancies_by_ids(db_path, deep_targets)
            vacancies, crawl_stats = _enrich_queued_vacancies(
                vacancies=queued_vacancies,
                base_url=settings.search.base_url,
                state_path=state_path,
                runtime=settings.runtime,
                logger=logger,
                progress_callback=progress_callback,
            )
        else:
            vacancies, crawl_stats = _run_fast_api_pipeline(
                base_url=settings.search.base_url,
                area=settings.search.area,
                query_text=settings.search.query_text,
                max_pages=settings.search.max_pages,
                cutoff_dt=cutoff_dt,
                runtime=settings.runtime,
                logger=logger,
                include_keywords=settings.filters.include_keywords,
                exclude_keywords=settings.filters.exclude_keywords,
                min_salary=settings.filters.min_salary,
                progress_callback=progress_callback,
            )
        _merge_stats(crawl_stats, stats)

        deduped: dict[str, Vacancy] = {vacancy.vacancy_id: vacancy for vacancy in vacancies}
        previous_active = get_active_hashes(db_path)
        seen_ids: set[str] = set()
        now = datetime.utcnow()

        for vacancy in deduped.values():
            if settings.search.mode == "deep" and deep_targets:
                matched, reason = True, "deep:queue"
            else:
                matched, reason = filter_vacancy(
                    vacancy=vacancy,
                    include_keywords=settings.filters.include_keywords,
                    exclude_keywords=settings.filters.exclude_keywords,
                    min_salary=settings.filters.min_salary,
                    include_description=True,
                )
            if not matched:
                continue

            vacancy.match_reason = reason
            vacancy.normalized_hash = _compute_hash(vacancy)
            seen_ids.add(vacancy.vacancy_id)

            old_hash = previous_active.get(vacancy.vacancy_id)
            status = "seen"
            if old_hash is None:
                status = "new"
                stats.new_count += 1
                insert_change(
                    db_path=db_path,
                    run_id=run_id,
                    vacancy_id=vacancy.vacancy_id,
                    change_type="new",
                    old_hash=None,
                    new_hash=vacancy.normalized_hash,
                    changed_at=now,
                )
            elif old_hash != vacancy.normalized_hash:
                status = "updated"
                stats.updated_count += 1
                insert_change(
                    db_path=db_path,
                    run_id=run_id,
                    vacancy_id=vacancy.vacancy_id,
                    change_type="updated",
                    old_hash=old_hash,
                    new_hash=vacancy.normalized_hash,
                    changed_at=now,
                )

            upsert_vacancy(db_path=db_path, vacancy=vacancy, seen_at=now)
            insert_run_item(
                db_path=db_path,
                run_id=run_id,
                vacancy_id=vacancy.vacancy_id,
                seen_at=now,
                match_reason=reason,
                parse_status=status,
            )

        stats.cards_after_keyword_filter = len(seen_ids)
        if not (settings.search.mode == "deep" and deep_targets):
            removed_ids = sorted(set(previous_active.keys()) - seen_ids)
            if removed_ids:
                mark_removed(db_path, removed_ids)
                for vacancy_id in removed_ids:
                    stats.removed_count += 1
                    insert_change(
                        db_path=db_path,
                        run_id=run_id,
                        vacancy_id=vacancy_id,
                        change_type="removed",
                        old_hash=previous_active.get(vacancy_id),
                        new_hash=None,
                        changed_at=now,
                    )

        finish_run(db_path=db_path, run_id=run_id, status="ok", stats=asdict(stats))
    except Exception:
        finish_run(db_path=db_path, run_id=run_id, status="failed", stats=asdict(stats))
        raise

    rows = get_run_change_rows(db_path, run_id)
    seen_rows = get_run_seen_rows(db_path, run_id)
    html_report_path = generate_html_report(rows=rows, output_path=report_path, run_id=run_id)
    return RunResult(
        run_id=run_id,
        rows=rows,
        seen_rows=seen_rows,
        stats=stats,
        html_report_path=html_report_path,
        processed_vacancy_ids=sorted(seen_ids),
    )

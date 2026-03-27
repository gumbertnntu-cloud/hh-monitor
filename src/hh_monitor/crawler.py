from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .browser_support import (
    PlaywrightError,
    PlaywrightTimeoutError,
    require_browser_automation,
    sync_playwright,
)
from .models import Vacancy
from .parser import parse_search_results, parse_vacancy_detail
from .utils import random_delay


class RetriableFetchError(RuntimeError):
    pass


@dataclass(slots=True)
class CrawlStats:
    pages_processed: int = 0
    cards_seen: int = 0
    cards_after_date_filter: int = 0
    deep_opened: int = 0
    errors: list[str] = field(default_factory=list)


def build_search_url(base_url: str, page: int, area: int, query_text: str) -> str:
    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page)
    query["area"] = str(area)
    query["text"] = query_text
    query.pop("searchSessionId", None)
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def _goto_with_retry(
    page: object,
    url: str,
    wait_selector: str,
    retry_max_attempts: int,
    backoff_base_sec: float,
    logger: logging.Logger,
) -> str:
    for attempt in range(1, retry_max_attempts + 1):
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            status = response.status if response else 200
            if status == 429 or status >= 500:
                raise RetriableFetchError(f"HTTP {status}")
            page.wait_for_selector(wait_selector, timeout=45000)
            return page.content()
        except (PlaywrightTimeoutError, RetriableFetchError, PlaywrightError) as exc:
            if attempt == retry_max_attempts:
                raise RuntimeError(f"failed to open {url}: {exc}") from exc
            sleep_sec = backoff_base_sec * (2 ** (attempt - 1)) + random.uniform(0, 1.0)
            logger.warning("retry attempt %s for %s after error: %s", attempt, url, exc)
            time.sleep(sleep_sec)
    raise RuntimeError(f"failed to open {url}")


def _stabilize_vacancy_detail_page(page: object, logger: logging.Logger) -> None:
    try:
        page.wait_for_selector('[data-qa="vacancy-description"]', timeout=12000)
    except Exception:
        logger.debug("vacancy-description selector not found within timeout")
    try:
        expand_candidates = [
            'button:has-text("Показать полностью")',
            'button:has-text("Читать далее")',
            '[data-qa*="vacancy-description"] button',
        ]
        for selector in expand_candidates:
            locator = page.locator(selector).first
            if locator.count() > 0:
                locator.click(timeout=1500)
                page.wait_for_timeout(350)
    except Exception:
        logger.debug("description expander click skipped")
    page.wait_for_timeout(900)


def crawl_vacancies(
    *,
    base_url: str,
    area: int,
    query_text: str,
    mode: str,
    max_pages: int,
    cutoff_dt: datetime,
    state_path: Path,
    runtime: object,
    logger: logging.Logger,
    progress_callback: Callable[[str], None] | None = None,
) -> tuple[list[Vacancy], CrawlStats]:
    require_browser_automation()
    stats = CrawlStats()
    items: list[Vacancy] = []
    now = datetime.now()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(state_path))
        page = context.new_page()

        for index in range(max_pages):
            page_url = build_search_url(
                base_url=base_url,
                page=index,
                area=area,
                query_text=query_text,
            )
            if progress_callback:
                progress_callback(f"Loading page {index + 1}/{max_pages}")
            try:
                html = _goto_with_retry(
                    page=page,
                    url=page_url,
                    wait_selector='[data-qa="vacancy-serp__results"]',
                    retry_max_attempts=runtime.retry_max_attempts,
                    backoff_base_sec=runtime.backoff_base_sec,
                    logger=logger,
                )
            except Exception as exc:  # noqa: BLE001
                message = f"page={index}: {exc}"
                stats.errors.append(message)
                logger.error(message)
                continue

            stats.pages_processed += 1
            page_cards = parse_search_results(html=html, base_url=base_url, now=now)
            if not page_cards:
                logger.info("no cards on page %s, stop", index)
                break

            stats.cards_seen += len(page_cards)
            all_old = True
            eligible: list[Vacancy] = []
            for card in page_cards:
                if card.published_at is None:
                    eligible.append(card)
                    all_old = False
                    continue
                if card.published_at >= cutoff_dt:
                    eligible.append(card)
                    all_old = False

            stats.cards_after_date_filter += len(eligible)
            if mode == "deep":
                for vacancy in eligible:
                    if vacancy.date_unknown:
                        continue
                    if progress_callback:
                        progress_callback(f"Loading details for vacancy {vacancy.vacancy_id}")
                    try:
                        _goto_with_retry(
                            page=page,
                            url=vacancy.url,
                            wait_selector='[data-qa="vacancy-title"]',
                            retry_max_attempts=runtime.retry_max_attempts,
                            backoff_base_sec=runtime.backoff_base_sec,
                            logger=logger,
                        )
                        _stabilize_vacancy_detail_page(page, logger)
                        detail_html = page.content()
                        parse_vacancy_detail(detail_html, vacancy)
                        vacancy.data_source_status = "browser_dd"
                        stats.deep_opened += 1
                    except Exception as exc:  # noqa: BLE001
                        message = f"vacancy={vacancy.vacancy_id}: {exc}"
                        stats.errors.append(message)
                        logger.error(message)
                    random_delay(runtime.delay_min_sec, runtime.delay_max_sec, runtime.jitter_sec)

            items.extend(eligible)

            if all_old:
                logger.info("all vacancies are older than cutoff at page=%s, early stop", index)
                break

            random_delay(runtime.delay_min_sec, runtime.delay_max_sec, runtime.jitter_sec)

        context.close()
        browser.close()

    return items, stats


def crawl_vacancy_details(
    *,
    vacancies: list[Vacancy],
    state_path: Path,
    runtime: object,
    logger: logging.Logger,
    progress_callback: Callable[[str], None] | None = None,
) -> tuple[list[Vacancy], CrawlStats]:
    require_browser_automation()
    stats = CrawlStats()
    if not vacancies:
        return [], stats

    stats.cards_seen = len(vacancies)
    stats.cards_after_date_filter = len(vacancies)
    updated: list[Vacancy] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(state_path))
        page = context.new_page()

        for vacancy in vacancies:
            if progress_callback:
                progress_callback(f"Loading details for queued vacancy {vacancy.vacancy_id}")
            try:
                _goto_with_retry(
                    page=page,
                    url=vacancy.url,
                    wait_selector='[data-qa="vacancy-title"]',
                    retry_max_attempts=runtime.retry_max_attempts,
                    backoff_base_sec=runtime.backoff_base_sec,
                    logger=logger,
                )
                _stabilize_vacancy_detail_page(page, logger)
                detail_html = page.content()
                parse_vacancy_detail(detail_html, vacancy)
                vacancy.data_source_status = "browser_dd"
                stats.deep_opened += 1
            except Exception as exc:  # noqa: BLE001
                message = f"queued vacancy={vacancy.vacancy_id}: {exc}"
                stats.errors.append(message)
                logger.error(message)
            updated.append(vacancy)
            random_delay(runtime.delay_min_sec, runtime.delay_max_sec, runtime.jitter_sec)

        context.close()
        browser.close()

    return updated, stats

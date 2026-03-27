from __future__ import annotations

import json
import logging
import random
import ssl
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

import certifi

from .models import Vacancy
from .parser import parse_api_description_html
from .utils import normalize_text, to_local_naive_datetime

_API_CACHE_LOCK = threading.Lock()
_API_CACHE: dict[str, tuple[str, dict[str, Any]]] = {}
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
_VACANCIES_API_QUERY_KEYS = {
    "area",
    "search_field",
    "salary",
    "experience",
    "employment",
    "schedule",
    "professional_role",
    "order_by",
    "label",
}


class HHApiError(RuntimeError):
    pass


class HHApiRetriableError(HHApiError):
    pass


@dataclass(slots=True)
class HHApiResponse:
    payload: dict[str, Any]
    from_cache: bool = False


def _first_name(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    return normalize_text(str(payload.get("name", "")).strip())


def _list_names(values: list[dict[str, Any]] | None) -> str:
    if not values:
        return ""
    names: list[str] = []
    seen: set[str] = set()
    for item in values:
        name = _first_name(item)
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return ", ".join(names)


def _metro_summary(address: dict[str, Any] | None) -> str:
    if not isinstance(address, dict):
        return ""
    stations = address.get("metro_stations")
    if not isinstance(stations, list):
        return ""
    names: list[str] = []
    seen: set[str] = set()
    for station in stations:
        if not isinstance(station, dict):
            continue
        station_name = normalize_text(str(station.get("station_name", "")).strip())
        if not station_name or station_name in seen:
            continue
        seen.add(station_name)
        names.append(station_name)
    return ", ".join(names)


def _format_salary(payload: dict[str, Any] | None) -> tuple[str, int | None, int | None]:
    if not isinstance(payload, dict):
        return "", None, None

    salary_from = payload.get("from")
    salary_to = payload.get("to")
    currency = str(payload.get("currency", "")).upper()
    gross = payload.get("gross")
    mode = _first_name(payload.get("mode"))
    frequency = _first_name(payload.get("frequency"))

    parts: list[str] = []
    if salary_from is not None and salary_to is not None:
        parts.append(f"{salary_from:,} - {salary_to:,}".replace(",", " "))
    elif salary_from is not None:
        parts.append(f"от {salary_from:,}".replace(",", " "))
    elif salary_to is not None:
        parts.append(f"до {salary_to:,}".replace(",", " "))
    if currency:
        parts.append(currency)
    if gross is True:
        parts.append("gross")
    elif gross is False:
        parts.append("net")
    if mode:
        parts.append(mode)
    if frequency:
        parts.append(frequency)
    return " ".join(parts).strip(), salary_from, salary_to


def _parse_published_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return to_local_naive_datetime(datetime.fromisoformat(raw))
    except ValueError:
        return None


def build_vacancies_url(
    base_url: str,
    page: int,
    area: int,
    query_text: str,
    per_page: int,
) -> str:
    parsed = urlparse(base_url)
    query = {
        key: value
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key in _VACANCIES_API_QUERY_KEYS and value
    }
    query["page"] = str(page)
    query["area"] = str(area)
    query["text"] = query_text
    query["per_page"] = str(per_page)
    return urlunparse(
        parsed._replace(
            scheme="https",
            netloc="api.hh.ru",
            path="/vacancies",
            query=urlencode(query, doseq=True),
        )
    )


def _detail_url(vacancy_id: str) -> str:
    return f"https://api.hh.ru/vacancies/{vacancy_id}?host=hh.ru"


def merge_vacancy_fields(target: Vacancy, source: Vacancy) -> Vacancy:
    for field_name in target.__dataclass_fields__:
        value = getattr(source, field_name)
        if value in ("", None):
            continue
        if isinstance(value, bool):
            setattr(target, field_name, value)
            continue
        setattr(target, field_name, value)
    if source.data_source_status:
        target.data_source_status = source.data_source_status
    return target


def vacancy_needs_browser_dd(vacancy: Vacancy) -> bool:
    if vacancy.data_source_status in {"api_detail_failed", "fallback_needed"}:
        return True
    return not bool(vacancy.description.strip())


def vacancy_has_pre_dd_signal(vacancy: Vacancy) -> bool:
    return bool(
        vacancy.description.strip()
        or vacancy.api_description_html.strip()
        or vacancy.published_at
        or vacancy.experience_name
        or vacancy.schedule_name
    )


def vacancy_from_api_item(item: dict[str, Any]) -> Vacancy:
    salary_raw, salary_from, salary_to = _format_salary(
        item.get("salary_range") or item.get("salary")
    )
    snippet = "\n".join(
        part
        for part in [
            normalize_text(str((item.get("snippet") or {}).get("responsibility", ""))),
            normalize_text(str((item.get("snippet") or {}).get("requirement", ""))),
        ]
        if part
    )
    address = item.get("address")
    area = _first_name(item.get("area")) or normalize_text(
        str((address or {}).get("city", ""))
    )
    return Vacancy(
        vacancy_id=str(item.get("id", "")).strip(),
        url=normalize_text(str(item.get("alternate_url") or "")),
        title=normalize_text(str(item.get("name") or "")),
        company=_first_name(item.get("employer")),
        salary_raw=salary_raw,
        salary_from=salary_from,
        salary_to=salary_to,
        area=area,
        snippet=snippet,
        published_at=_parse_published_at(item.get("published_at")),
        date_unknown=item.get("published_at") is None,
        address_raw=normalize_text(str((address or {}).get("raw", ""))),
        metro_summary=_metro_summary(address),
        experience_name=_first_name(item.get("experience")),
        employment_name=_first_name(item.get("employment")),
        schedule_name=_first_name(item.get("schedule")),
        work_format_names=_list_names(item.get("work_format")),
        working_hours_names=_list_names(item.get("working_hours")),
        work_schedule_by_days_names=_list_names(item.get("work_schedule_by_days")),
        professional_roles=_list_names(item.get("professional_roles")),
        employer_trusted=bool((item.get("employer") or {}).get("trusted")),
        employer_accredited_it=bool((item.get("employer") or {}).get("accredited_it_employer")),
        data_source_status="api_list",
    )


def enrich_vacancy_from_api_detail(
    vacancy: Vacancy,
    payload: dict[str, Any],
    description_text: str,
) -> Vacancy:
    salary_raw, salary_from, salary_to = _format_salary(
        payload.get("salary_range") or payload.get("salary")
    )
    address = payload.get("address")
    detail = Vacancy(
        vacancy_id=vacancy.vacancy_id,
        url=normalize_text(str(payload.get("alternate_url") or vacancy.url)),
        title=normalize_text(str(payload.get("name") or vacancy.title)),
        company=_first_name(payload.get("employer")) or vacancy.company,
        salary_raw=salary_raw,
        salary_from=salary_from,
        salary_to=salary_to,
        area=_first_name(payload.get("area"))
        or normalize_text(str((address or {}).get("city", ""))),
        description=description_text,
        published_at=_parse_published_at(payload.get("published_at")),
        date_unknown=payload.get("published_at") is None,
        address_raw=normalize_text(str((address or {}).get("raw", ""))),
        metro_summary=_metro_summary(address),
        experience_name=_first_name(payload.get("experience")),
        employment_name=_first_name(payload.get("employment")),
        schedule_name=_first_name(payload.get("schedule")),
        work_format_names=_list_names(payload.get("work_format")),
        working_hours_names=_list_names(payload.get("working_hours")),
        work_schedule_by_days_names=_list_names(payload.get("work_schedule_by_days")),
        professional_roles=_list_names(payload.get("professional_roles")),
        employer_trusted=bool((payload.get("employer") or {}).get("trusted")),
        employer_accredited_it=bool((payload.get("employer") or {}).get("accredited_it_employer")),
        api_description_html=unescape(str(payload.get("description") or "")),
        data_source_status="api_detail",
    )
    return merge_vacancy_fields(vacancy, detail)


class HHApiClient:
    def __init__(
        self,
        *,
        runtime: object,
        logger: logging.Logger,
        user_agent: str = "hh-monitor/1.0",
    ) -> None:
        self.runtime = runtime
        self.logger = logger
        self.user_agent = user_agent
        self._last_request_at = 0.0
        self._detail_suspended = False

    @property
    def detail_suspended(self) -> bool:
        return self._detail_suspended

    def fetch_list_page(
        self,
        *,
        base_url: str,
        area: int,
        query_text: str,
        page: int,
        per_page: int = 50,
    ) -> list[Vacancy]:
        url = build_vacancies_url(
            base_url=base_url,
            page=page,
            area=area,
            query_text=query_text,
            per_page=per_page,
        )
        payload = self._request_json(url).payload
        items = payload.get("items")
        if not isinstance(items, list):
            return []
        return [vacancy_from_api_item(item) for item in items if isinstance(item, dict)]

    def fetch_detail(self, vacancy: Vacancy) -> Vacancy:
        if self._detail_suspended:
            vacancy.data_source_status = "fallback_needed"
            return vacancy
        try:
            payload = self._request_json(_detail_url(vacancy.vacancy_id)).payload
        except HHApiRetriableError:
            self._detail_suspended = True
            vacancy.data_source_status = "fallback_needed"
            return vacancy
        description_html = unescape(str(payload.get("description") or ""))
        return enrich_vacancy_from_api_detail(
            vacancy,
            payload,
            description_text=parse_api_description_html(description_html),
        )

    def _request_json(self, url: str) -> HHApiResponse:
        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        with _API_CACHE_LOCK:
            cached = _API_CACHE.get(url)
        if cached:
            headers["If-None-Match"] = cached[0]

        for attempt in range(1, self.runtime.retry_max_attempts + 1):
            self._throttle()
            request = Request(url, headers=headers)
            try:
                with urlopen(request, timeout=30, context=_SSL_CONTEXT) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    etag = response.headers.get("ETag")
                    if etag:
                        with _API_CACHE_LOCK:
                            _API_CACHE[url] = (etag, payload)
                    return HHApiResponse(payload=payload)
            except HTTPError as exc:
                if exc.code == 304 and cached:
                    return HHApiResponse(payload=cached[1], from_cache=True)
                if exc.code in {403, 429, 500, 502, 503, 504}:
                    if attempt == self.runtime.retry_max_attempts:
                        raise HHApiRetriableError(f"api {exc.code} for {url}") from exc
                    self._sleep_backoff(attempt=attempt, retry_after=exc.headers.get("Retry-After"))
                    continue
                raise HHApiError(f"api {exc.code} for {url}") from exc
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt == self.runtime.retry_max_attempts:
                    raise HHApiRetriableError(f"api failed for {url}: {exc}") from exc
                self._sleep_backoff(attempt=attempt, retry_after=None)
        raise HHApiError(f"api failed for {url}")

    def _throttle(self) -> None:
        min_interval = 0.15
        delta = time.monotonic() - self._last_request_at
        if delta < min_interval:
            time.sleep(min_interval - delta)
        self._last_request_at = time.monotonic()

    def _sleep_backoff(self, *, attempt: int, retry_after: str | None) -> None:
        if retry_after:
            try:
                time.sleep(float(retry_after))
                return
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    delay = max(0.0, (retry_at - datetime.now(retry_at.tzinfo)).total_seconds())
                    time.sleep(delay)
                    return
                except Exception:
                    pass
        base = self.runtime.backoff_base_sec * (2 ** (attempt - 1))
        time.sleep(base + random.uniform(0, 0.75))

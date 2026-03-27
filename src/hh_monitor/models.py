from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Status = Literal["new", "updated", "removed"]
Mode = Literal["fast", "deep"]


@dataclass(slots=True)
class Vacancy:
    vacancy_id: str
    url: str
    title: str
    company: str
    salary_raw: str = ""
    salary_from: int | None = None
    salary_to: int | None = None
    area: str = ""
    snippet: str = ""
    description: str = ""
    activity_text: str = ""
    published_at: datetime | None = None
    date_unknown: bool = False
    match_reason: str = ""
    normalized_hash: str = ""
    address_raw: str = ""
    metro_summary: str = ""
    experience_name: str = ""
    employment_name: str = ""
    schedule_name: str = ""
    work_format_names: str = ""
    working_hours_names: str = ""
    work_schedule_by_days_names: str = ""
    professional_roles: str = ""
    employer_trusted: bool = False
    employer_accredited_it: bool = False
    api_description_html: str = ""
    data_source_status: str = "unknown"


@dataclass(slots=True)
class RunParams:
    mode: Mode
    max_pages: int
    max_age_days: int
    query_text: str


@dataclass(slots=True)
class ChangeRow:
    date_seen: str
    vacancy_id: str
    title: str
    company: str
    salary: str
    area: str
    url: str
    match_reason: str
    status: Status


@dataclass(slots=True)
class SeenVacancyRow:
    date_seen: str
    vacancy_id: str
    title: str
    company: str
    salary: str
    area: str
    url: str
    match_reason: str
    parse_status: str
    published_at: str = ""
    location_detail: str = ""
    pre_dd_meta: str = ""
    data_source_status: str = ""


@dataclass(slots=True)
class RunStats:
    pages_processed: int = 0
    cards_seen: int = 0
    cards_after_date_filter: int = 0
    cards_after_keyword_filter: int = 0
    deep_opened: int = 0
    new_count: int = 0
    updated_count: int = 0
    removed_count: int = 0
    errors: list[str] = field(default_factory=list)

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RuntimeSettings(BaseModel):
    delay_min_sec: float = 1.0
    delay_max_sec: float = 3.0
    jitter_sec: float = 0.4
    retry_max_attempts: int = 4
    backoff_base_sec: float = 2.0

    @model_validator(mode="after")
    def validate_delay(self) -> RuntimeSettings:
        if self.delay_max_sec < self.delay_min_sec:
            raise ValueError("delay_max_sec must be >= delay_min_sec")
        return self


class SearchSettings(BaseModel):
    base_url: str = "https://hh.ru/search/vacancy?text=&salary=&ored_clusters=true&area=1"
    area: int = 1
    query_text: str = ""
    mode: Literal["fast", "deep"] = "fast"
    max_pages: int = Field(default=10, ge=1, le=100)
    max_age_days: int = Field(default=30, ge=1, le=365)


class FilterSettings(BaseModel):
    include_keywords: list[str] = Field(
        default_factory=lambda: [
            "CEO",
            "COO",
            "Исполнительный директор",
            "Директор по трансформации",
            "Chief of Staff",
        ]
    )
    exclude_keywords: list[str] = Field(
        default_factory=lambda: [
            "стажер",
            "intern",
            "ассистент",
            "junior",
            "без опыта",
        ]
    )
    min_salary: int | None = None


class PathSettings(BaseModel):
    db_path: str = "data/hh_monitor.db"
    state_path: str = "state/state.json"
    settings_path: str = "config/settings.json"
    logs_dir: str = "logs"
    reports_dir: str = "reports"
    exports_dir: str = "exports"


class AppSettings(BaseModel):
    search: SearchSettings = Field(default_factory=SearchSettings)
    filters: FilterSettings = Field(default_factory=FilterSettings)
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    paths: PathSettings = Field(default_factory=PathSettings)

    def ensure_runtime_dirs(self, project_root: Path) -> None:
        for folder in [
            project_root / self.paths.logs_dir,
            project_root / "state",
            project_root / "data",
            project_root / self.paths.reports_dir,
            project_root / self.paths.exports_dir,
            project_root / "config",
        ]:
            folder.mkdir(parents=True, exist_ok=True)


def load_settings(settings_path: Path) -> AppSettings:
    if not settings_path.exists():
        defaults = AppSettings()
        save_settings(defaults, settings_path)
        return defaults
    with settings_path.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    return AppSettings.model_validate(payload)


def save_settings(settings: AppSettings, settings_path: Path) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = settings_path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as fp:
        json.dump(settings.model_dump(), fp, ensure_ascii=False, indent=2)
    temp_path.replace(settings_path)
    settings_path.chmod(0o600)

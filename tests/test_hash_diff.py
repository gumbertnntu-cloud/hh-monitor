from __future__ import annotations

from datetime import datetime

from hh_monitor.models import Vacancy
from hh_monitor.utils import hash_normalized


def test_hash_changes_when_description_changes() -> None:
    base = Vacancy(
        vacancy_id="1",
        url="https://hh.ru/vacancy/1",
        title="COO",
        company="ACME",
        salary_raw="от 500 000 ₽",
        area="Москва",
        snippet="Стратегия",
        description="Описание 1",
        published_at=datetime(2026, 2, 15),
    )
    h1 = hash_normalized(
        [base.title, base.company, base.salary_raw, base.area, base.snippet, base.description]
    )
    base.description = "Описание 2"
    h2 = hash_normalized(
        [base.title, base.company, base.salary_raw, base.area, base.snippet, base.description]
    )
    assert h1 != h2

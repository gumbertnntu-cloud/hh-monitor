from __future__ import annotations

from datetime import UTC, datetime

from hh_monitor.utils import parse_hh_relative_date, to_local_naive_datetime


def test_parse_hh_relative_date() -> None:
    now = datetime(2026, 2, 15, 12, 0, 0)
    assert parse_hh_relative_date("сегодня", now).date() == now.date()
    assert parse_hh_relative_date("вчера", now).date().isoformat() == "2026-02-14"
    assert parse_hh_relative_date("10 дней назад", now).date().isoformat() == "2026-02-05"
    assert parse_hh_relative_date("2 недели назад", now).date().isoformat() == "2026-02-01"
    assert parse_hh_relative_date("1 месяц назад", now).date().isoformat() == "2026-01-16"


def test_parse_hh_relative_date_unknown() -> None:
    now = datetime(2026, 2, 15, 12, 0, 0)
    assert parse_hh_relative_date("", now) is None
    assert parse_hh_relative_date("только что опубликовано", now) is None


def test_to_local_naive_datetime_normalizes_aware_values() -> None:
    raw = datetime(2026, 3, 27, 12, 44, 19, tzinfo=UTC)
    normalized = to_local_naive_datetime(raw)

    assert normalized.tzinfo is None

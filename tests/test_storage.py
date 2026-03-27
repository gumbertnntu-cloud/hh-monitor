from __future__ import annotations

from datetime import datetime

from hh_monitor.models import Vacancy
from hh_monitor.storage import get_vacancies_by_ids, init_db, upsert_vacancy


def test_get_vacancies_by_ids_preserves_requested_order(tmp_path) -> None:
    db_path = tmp_path / "hh_monitor.db"
    init_db(db_path)

    now = datetime(2026, 2, 15, 12, 0, 0)
    v1 = Vacancy(
        vacancy_id="v1",
        url="https://hh.ru/vacancy/v1",
        title="Chief of Staff",
        company="ACME",
        snippet="strategy",
        normalized_hash="h1",
        published_at=now,
    )
    v2 = Vacancy(
        vacancy_id="v2",
        url="https://hh.ru/vacancy/v2",
        title="COO",
        company="Beta",
        snippet="operations",
        normalized_hash="h2",
        published_at=now,
    )

    upsert_vacancy(db_path=db_path, vacancy=v1, seen_at=now)
    upsert_vacancy(db_path=db_path, vacancy=v2, seen_at=now)

    rows = get_vacancies_by_ids(db_path, ["v2", "v1", "missing"])
    assert [row.vacancy_id for row in rows] == ["v2", "v1"]
    assert rows[0].title == "COO"
    assert rows[1].title == "Chief of Staff"


def test_init_db_migrates_existing_vacancies_table(tmp_path) -> None:
    db_path = tmp_path / "hh_monitor.db"
    db_path.write_text("")
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE vacancies (
          vacancy_id TEXT PRIMARY KEY,
          url TEXT NOT NULL,
          title TEXT NOT NULL,
          company TEXT NOT NULL,
          salary_raw TEXT,
          salary_from INTEGER,
          salary_to INTEGER,
          area TEXT,
          snippet TEXT,
          description TEXT,
          published_at TEXT,
          activity_text TEXT,
          date_unknown INTEGER NOT NULL DEFAULT 0,
          normalized_hash TEXT NOT NULL,
          first_seen_at TEXT NOT NULL,
          last_seen_at TEXT NOT NULL,
          is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.commit()
    conn.close()

    init_db(db_path)

    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(vacancies)").fetchall()}
    conn.close()
    assert "address_raw" in columns
    assert "data_source_status" in columns

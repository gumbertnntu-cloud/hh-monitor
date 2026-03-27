from __future__ import annotations

from hh_monitor.hh_api import (
    enrich_vacancy_from_api_detail,
    vacancy_from_api_item,
    vacancy_has_pre_dd_signal,
    vacancy_needs_browser_dd,
)
from hh_monitor.parser import parse_api_description_html


def test_vacancy_from_api_item_extracts_pre_dd_fields() -> None:
    vacancy = vacancy_from_api_item(
        {
            "id": "101",
            "name": "Chief of Staff",
            "alternate_url": "https://hh.ru/vacancy/101",
            "area": {"name": "Москва"},
            "salary": {"from": 500000, "to": 700000, "currency": "RUR", "gross": True},
            "address": {
                "raw": "Москва, Пресненская набережная, 10",
                "metro_stations": [
                    {"station_name": "Деловой центр"},
                    {"station_name": "Деловой центр"},
                ],
            },
            "published_at": "2026-03-27T12:44:19+0300",
            "snippet": {"responsibility": "Вести штаб", "requirement": "Опыт в strategy"},
            "experience": {"name": "Более 6 лет"},
            "employment": {"name": "Полная занятость"},
            "schedule": {"name": "Полный день"},
            "work_format": [{"name": "Гибрид"}],
            "working_hours": [{"name": "8 часов"}],
            "work_schedule_by_days": [{"name": "5/2"}],
            "professional_roles": [{"name": "Chief of Staff"}],
            "employer": {
                "name": "ACME",
                "trusted": True,
                "accredited_it_employer": False,
            },
        }
    )

    assert vacancy.vacancy_id == "101"
    assert vacancy.company == "ACME"
    assert vacancy.salary_from == 500000
    assert vacancy.address_raw == "Москва, Пресненская набережная, 10"
    assert vacancy.metro_summary == "Деловой центр"
    assert vacancy.professional_roles == "Chief of Staff"
    assert vacancy.data_source_status == "api_list"


def test_enrich_vacancy_from_api_detail_preserves_existing_values_when_detail_empty() -> None:
    vacancy = vacancy_from_api_item(
        {
            "id": "101",
            "name": "Chief of Staff",
            "alternate_url": "https://hh.ru/vacancy/101",
            "area": {"name": "Москва"},
            "salary": {"from": 500000, "to": None, "currency": "RUR", "gross": True},
            "snippet": {"responsibility": "Штаб CEO", "requirement": ""},
            "employer": {"name": "ACME"},
        }
    )

    description_html = "<strong>Обязанности:</strong><ul><li><p>Стратегия</p></li></ul>"
    enriched = enrich_vacancy_from_api_detail(
        vacancy,
        {
            "alternate_url": "https://hh.ru/vacancy/101",
            "description": description_html,
            "experience": {"name": "Более 6 лет"},
            "employment": {"name": "Полная занятость"},
            "schedule": {"name": "Полный день"},
            "professional_roles": [{"name": "Chief of Staff"}],
            "employer": {"name": "ACME", "trusted": True, "accredited_it_employer": True},
        },
        description_text=parse_api_description_html(description_html),
    )

    assert enriched.snippet == "Штаб CEO"
    assert "Стратегия" in enriched.description
    assert enriched.experience_name == "Более 6 лет"
    assert enriched.employer_trusted is True
    assert enriched.employer_accredited_it is True
    assert enriched.data_source_status == "api_detail"


def test_vacancy_needs_browser_dd_only_when_api_detail_is_incomplete() -> None:
    vacancy = vacancy_from_api_item(
        {
            "id": "101",
            "name": "Chief of Staff",
            "alternate_url": "https://hh.ru/vacancy/101",
            "area": {"name": "Москва"},
            "employer": {"name": "ACME"},
        }
    )
    assert vacancy_needs_browser_dd(vacancy) is True
    assert vacancy_has_pre_dd_signal(vacancy) is False

    vacancy.description = "Полный текст"
    vacancy.data_source_status = "api_detail"
    assert vacancy_needs_browser_dd(vacancy) is False
    assert vacancy_has_pre_dd_signal(vacancy) is True

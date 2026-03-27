from __future__ import annotations

from datetime import datetime
from pathlib import Path

from hh_monitor.parser import parse_search_results


def test_parse_search_results_extracts_cards() -> None:
    html = (Path(__file__).parent / "fixtures" / "hh_search_page.html").read_text(encoding="utf-8")
    now = datetime(2026, 2, 15, 12, 0, 0)

    results = parse_search_results(html=html, base_url="https://hh.ru/search/vacancy", now=now)

    assert len(results) == 3
    first = results[0]
    assert first.vacancy_id == "1001"
    assert first.title == "Chief Operating Officer"
    assert first.company == "ACME Corp"
    assert first.salary_from == 500000
    assert first.area == "Москва"
    assert first.date_unknown is False

    second = results[1]
    assert second.vacancy_id == "1002"
    assert second.published_at is not None
    assert (now - second.published_at).days >= 39

    third = results[2]
    assert third.vacancy_id == "1003"
    assert third.published_at is None
    assert third.date_unknown is True


def test_parse_search_results_merges_all_available_snippet_blocks() -> None:
    html = """
    <div data-qa="vacancy-serp__results">
      <div data-qa="vacancy-serp__vacancy">
        <a data-qa="serp-item__title" href="https://hh.ru/vacancy/9999">
          <span data-qa="serp-item__title-text">COO</span>
        </a>
        <div data-qa="vacancy-serp__vacancy-employer-text">Example</div>
        <div data-qa="short_description">Краткий блок</div>
        <div data-qa="vacancy-serp__vacancy_snippet_responsibility">Задачи A</div>
        <div data-qa="vacancy-serp__vacancy_snippet_requirement">Требования B</div>
        <div data-qa="vacancy-serp__vacancy-work-format">Гибрид</div>
        <div data-qa="skills-element">Стратегия</div>
      </div>
    </div>
    """
    now = datetime(2026, 2, 15, 12, 0, 0)
    results = parse_search_results(html=html, base_url="https://hh.ru/search/vacancy", now=now)

    assert len(results) == 1
    assert results[0].snippet == "\n".join(
        ["Краткий блок", "Задачи A", "Требования B", "Гибрид", "Стратегия"]
    )

from __future__ import annotations

from hh_monitor.filters import filter_vacancy, match_exclude_keywords
from hh_monitor.models import Vacancy


def test_filter_vacancy_include_exclude_and_salary() -> None:
    vacancy = Vacancy(
        vacancy_id="1",
        url="https://hh.ru/vacancy/1",
        title="Chief Operating Officer",
        company="ACME",
        snippet="Трансформация",
        description="Операционная стратегия",
        salary_from=600000,
        salary_to=800000,
    )
    matched, reason = filter_vacancy(
        vacancy,
        include_keywords=["COO", "Chief"],
        exclude_keywords=["junior"],
        min_salary=500000,
        include_description=True,
    )
    assert matched is True
    assert "salary:>=500000" in reason


def test_filter_vacancy_respects_exclude() -> None:
    vacancy = Vacancy(
        vacancy_id="2",
        url="https://hh.ru/vacancy/2",
        title="Junior assistant",
        company="ACME",
        snippet="без опыта",
    )
    matched, reason = filter_vacancy(
        vacancy,
        include_keywords=["assistant"],
        exclude_keywords=["junior", "без опыта"],
        min_salary=None,
        include_description=False,
    )
    assert matched is False
    assert "exclude" in reason


def test_filter_vacancy_matches_russian_inflections() -> None:
    vacancy = Vacancy(
        vacancy_id="3",
        url="https://hh.ru/vacancy/3",
        title="Ищем исполнительного директора для трансформации компании",
        company="ACME",
        snippet="Опыт директора в B2B обязателен",
    )
    matched, reason = filter_vacancy(
        vacancy,
        include_keywords=["исполнительный директор", "директор по трансформации"],
        exclude_keywords=[],
        min_salary=None,
        include_description=False,
    )
    assert matched is True
    assert "include:title" in reason


def test_filter_vacancy_matches_english_inflections() -> None:
    vacancy = Vacancy(
        vacancy_id="4",
        url="https://hh.ru/vacancy/4",
        title="Directors of Operations for international growth",
        company="Globex",
        snippet="Operations leadership role",
    )
    matched, _ = filter_vacancy(
        vacancy,
        include_keywords=["Director of Operations"],
        exclude_keywords=[],
        min_salary=None,
        include_description=False,
    )
    assert matched is True


def test_filter_vacancy_exclude_matches_inflected_phrase() -> None:
    vacancy = Vacancy(
        vacancy_id="5",
        url="https://hh.ru/vacancy/5",
        title="Коммерческий директор",
        company="Example",
        snippet="Подойдет кандидату с опытом руководителя отдела продаж",
    )
    matched, reason = filter_vacancy(
        vacancy,
        include_keywords=["директор"],
        exclude_keywords=["руководитель отдела продаж"],
        min_salary=None,
        include_description=False,
    )
    assert matched is False
    assert 'exclude:snippet("руководитель отдела продаж")' in reason


def test_filter_vacancy_can_match_professional_roles_and_description() -> None:
    vacancy = Vacancy(
        vacancy_id="6",
        url="https://hh.ru/vacancy/6",
        title="Операционный лидер",
        company="Example",
        professional_roles="Chief of Staff",
        description="Нужен сильный Chief of Staff для CEO",
    )
    matched, reason = filter_vacancy(
        vacancy,
        include_keywords=["chief of staff"],
        exclude_keywords=[],
        min_salary=None,
        include_description=True,
    )
    assert matched is True
    assert "include:" in reason


def test_filter_vacancy_does_not_match_ceo_only_in_snippet_context() -> None:
    vacancy = Vacancy(
        vacancy_id="7",
        url="https://hh.ru/vacancy/7",
        title="Fullstack-разработчик",
        company="Рефни",
        snippet="Финальный звонок с CEO и командой.",
        description="Разработка продукта для HR-tech.",
        professional_roles="Программист, разработчик",
    )
    matched, reason = filter_vacancy(
        vacancy,
        include_keywords=["CEO"],
        exclude_keywords=[],
        min_salary=None,
        include_description=True,
    )
    assert matched is False
    assert reason == "include:not_matched"


def test_filter_vacancy_can_disable_snippet_matching_for_pre_detail_shortlist() -> None:
    vacancy = Vacancy(
        vacancy_id="7b",
        url="https://hh.ru/vacancy/7b",
        title="Менеджер продукта",
        company="Example",
        snippet="Работа рядом с Chief of Staff",
        professional_roles="Менеджер продукта",
    )
    matched, reason = filter_vacancy(
        vacancy,
        include_keywords=["Chief of Staff"],
        exclude_keywords=[],
        min_salary=None,
        include_description=False,
        include_snippet=False,
    )
    assert matched is False
    assert reason == "include:not_matched"


def test_match_exclude_keywords_works_on_list_fields_before_detail() -> None:
    vacancy = Vacancy(
        vacancy_id="8",
        url="https://hh.ru/vacancy/8",
        title="Операционный директор",
        company="Example",
        snippet="Опыт в FMCG обязателен",
    )
    excluded, reason = match_exclude_keywords(
        vacancy,
        ["FMCG", "ассистент"],
        include_description=False,
    )
    assert excluded is True
    assert reason == 'exclude:snippet("FMCG")'

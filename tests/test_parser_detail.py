from __future__ import annotations

from pathlib import Path

from hh_monitor.models import Vacancy
from hh_monitor.parser import parse_vacancy_detail


def test_parse_vacancy_detail_overrides_fields() -> None:
    html = (Path(__file__).parent / "fixtures" / "hh_vacancy_page.html").read_text(encoding="utf-8")
    vacancy = Vacancy(
        vacancy_id="1003",
        url="https://hh.ru/vacancy/1003",
        title="Old title",
        company="Old company",
    )

    parse_vacancy_detail(html, vacancy)
    assert vacancy.title == "Chief of Staff"
    assert vacancy.company == "Contoso"
    assert vacancy.salary_to == 700000
    assert "операционное управление" in vacancy.description


def test_parse_vacancy_detail_preserves_bullets_and_bold_markers() -> None:
    html = """
    <html>
      <body>
        <div data-qa="vacancy-description">
          <h2>Успешный кандидат имеет</h2>
          <ul>
            <li>
              Опыт <strong>Генерального</strong>, <strong>Операционного</strong> или
              <b>Исполнительного директора</b>, COO, VP Operations;
            </li>
            <li>
              Опыт <strong>управления производством</strong> и сервисом.
            </li>
          </ul>
        </div>
      </body>
    </html>
    """
    vacancy = Vacancy(
        vacancy_id="1005",
        url="https://hh.ru/vacancy/1005",
        title="Role",
        company="Company",
    )

    parse_vacancy_detail(html, vacancy)

    assert "Успешный кандидат имеет:" in vacancy.description
    assert (
        "— Опыт **Генерального**, **Операционного** или "
        "**Исполнительного директора**, COO, VP Operations;"
    ) in vacancy.description
    assert "— Опыт **управления производством** и сервисом." in vacancy.description


def test_parse_vacancy_detail_repairs_inline_spacing_artifacts() -> None:
    html = """
    <html>
      <body>
        <div data-qa="vacancy-description">
          <p>Ищем<span>COO</span>, который возьмёт управление.</p>
          <p>KPI/OKR и performance-экономика.</p>
        </div>
      </body>
    </html>
    """
    vacancy = Vacancy(
        vacancy_id="1006",
        url="https://hh.ru/vacancy/1006",
        title="Role",
        company="Company",
    )

    parse_vacancy_detail(html, vacancy)
    assert "Ищем COO, который" in vacancy.description
    assert "KPI/OKR" in vacancy.description
    assert "ИщемCOO" not in vacancy.description
    assert "KPI / OKR" not in vacancy.description


def test_parse_vacancy_detail_repairs_adjacent_bold_spacing() -> None:
    html = """
    <html>
      <body>
        <div data-qa="vacancy-description">
          <p>Мы видим, что<strong>текущая модель</strong> требует обновления.</p>
          <p>Поэтому мы ищем<strong>операционного директора</strong>, который усилит команду.</p>
          <p>Нужен руководитель, который работает<strong>руками и головой</strong>.</p>
        </div>
      </body>
    </html>
    """
    vacancy = Vacancy(
        vacancy_id="1007",
        url="https://hh.ru/vacancy/1007",
        title="Role",
        company="Company",
    )

    parse_vacancy_detail(html, vacancy)
    assert "что **текущая модель** требует" in vacancy.description
    assert "ищем **операционного директора**, который" in vacancy.description
    assert "работает **руками и головой**" in vacancy.description

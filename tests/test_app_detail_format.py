from __future__ import annotations

from hh_monitor.app import MainWindow


def test_format_deep_full_text_html_adds_blank_before_heading() -> None:
    text = "Первая строка\nВаши задачи:\nТело"

    rendered = MainWindow._format_deep_full_text_html(None, text)

    expected = (
        "Первая строка<br><br>"
        "<span style='color:#E6C15A; font-weight:700;'>Ваши задачи:</span>"
    )
    assert expected in rendered


def test_format_deep_full_text_html_renders_bold_and_joins_split_commas() -> None:
    text = "Опыт\n**Генерального**\n,\n**Операционного**"

    rendered = MainWindow._format_deep_full_text_html(None, text)

    expected = (
        "Опыт<br>"
        "<span style='font-weight:700; color:#F0F0F3;'>Генерального</span>, "
        "<span style='font-weight:700; color:#F0F0F3;'>Операционного</span>"
    )
    assert expected in rendered


def test_compose_query_text_does_not_inject_blockers_into_hh_query() -> None:
    query = MainWindow._compose_query_text(
        None,
        positions=["генеральный директор", "CEO"],
        blockers=["секретарь", "assistant"],
    )

    assert query == '("генеральный директор") OR CEO'


def test_render_salary_value_html_highlights_numeric_salary() -> None:
    rendered = MainWindow._render_salary_value_html(None, "от 300 000 ₽")
    assert "color:#FF5A5A" in rendered
    assert "font-size:18px" in rendered
    assert "300 000" in rendered


def test_render_salary_value_html_keeps_plain_for_non_numeric_salary() -> None:
    rendered = MainWindow._render_salary_value_html(None, "не указана")
    assert "color:#FF5A5A" not in rendered
    assert rendered == "не указана"


def test_format_deep_full_text_html_repairs_missing_spaces_around_bold() -> None:
    text = "Мы видим, что**текущая модель**требует обновления."
    rendered = MainWindow._format_deep_full_text_html(None, text)
    expected = (
        "что <span style='font-weight:700; color:#F0F0F3;'>"
        "текущая модель</span> требует"
    )
    assert expected in rendered

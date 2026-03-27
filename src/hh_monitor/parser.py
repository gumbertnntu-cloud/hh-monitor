from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

from .models import Vacancy
from .utils import normalize_text, parse_hh_relative_date, parse_salary_range

VACANCY_ID_RE = re.compile(r"/vacancy/(\d+)")
DESCRIPTION_BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li"}
DESCRIPTION_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
BOLD_SPAN_RE = re.compile(r"(?<!\*)\*\*([^*\n]+?)\*\*(?!\*)")


def _first_text(node: Tag | None, selector: str) -> str:
    if node is None:
        return ""
    found = node.select_one(selector)
    if not found:
        return ""
    return normalize_text(found.get_text(" ", strip=True))


def _collect_texts(node: Tag | None, selector: str) -> list[str]:
    if node is None:
        return []
    results: list[str] = []
    seen: set[str] = set()
    for found in node.select(selector):
        text = normalize_text(found.get_text(" ", strip=True))
        if not text or text in seen:
            continue
        seen.add(text)
        results.append(text)
    return results


def _extract_vacancy_id(url: str) -> str | None:
    match = VACANCY_ID_RE.search(url)
    if not match:
        return None
    return match.group(1)


def _normalize_preserving_newlines(value: str) -> str:
    lines = [re.sub(r"\s+", " ", chunk).strip() for chunk in value.replace("\xa0", " ").split("\n")]
    return "\n".join(lines)


def _repair_spacing_artifacts(value: str) -> str:
    text = value.replace("\xa0", " ")
    # HH rich text can lose spaces around markdown-like bold markers when
    # inline spans are flattened (e.g. "...что**модель**...").
    text = _repair_bold_marker_spacing(text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([а-яёa-z])([A-ZА-ЯЁ]{2,})", r"\1 \2", text)
    text = re.sub(r"([A-ZА-ЯЁ]{2,})([а-яёa-z])", r"\1 \2", text)
    text = re.sub(r"\b([A-ZА-ЯЁ]{2,})\s*/\s*([A-ZА-ЯЁ]{2,})\b", r"\1/\2", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _repair_bold_marker_spacing(text: str) -> str:
    text = text.replace("****", "** **")
    pieces: list[str] = []
    last = 0
    for match in BOLD_SPAN_RE.finditer(text):
        start, end = match.span()
        pieces.append(text[last:start])
        prev_char = text[start - 1] if start > 0 else ""
        next_char = text[end] if end < len(text) else ""
        if prev_char and (prev_char.isalnum() or prev_char == "_"):
            pieces.append(" ")
        pieces.append(match.group(0))
        if next_char and (next_char.isalnum() or next_char == "_"):
            pieces.append(" ")
        last = end
    pieces.append(text[last:])
    return "".join(pieces)


def _flatten_rich_inline(node: Tag | NavigableString) -> str:
    if isinstance(node, NavigableString):
        return str(node).replace("\xa0", " ")
    if not isinstance(node, Tag):
        return ""

    name = (node.name or "").lower()
    if name in {"script", "style", "noscript"}:
        return ""
    if name == "br":
        return "\n"

    raw = "".join(_flatten_rich_inline(child) for child in node.children)
    normalized = _normalize_preserving_newlines(raw)
    if name in {"b", "strong"}:
        text = normalized.strip()
        return f"**{text}**" if text else ""
    return normalized


def _extract_structured_description(node: Tag) -> str:
    lines: list[str] = []
    for block in node.find_all(list(DESCRIPTION_BLOCK_TAGS)):
        parent = block.parent
        nested_in_block = False
        while isinstance(parent, Tag) and parent is not node:
            if (parent.name or "").lower() in DESCRIPTION_BLOCK_TAGS:
                nested_in_block = True
                break
            parent = parent.parent
        if nested_in_block:
            continue

        text = _flatten_rich_inline(block).strip()
        if not text:
            continue

        segments = [seg.strip() for seg in text.split("\n") if seg.strip()]
        if not segments:
            continue

        tag_name = (block.name or "").lower()
        if tag_name == "li":
            joined = " ".join(segments)
            joined = _repair_spacing_artifacts(joined)
            segments = [joined] if joined else []
            if not segments:
                continue

        for idx, segment in enumerate(segments):
            line = _repair_spacing_artifacts(segment)
            if tag_name == "li" and idx == 0 and not line.startswith(("—", "-", "•")):
                line = f"— {line}"
            if tag_name in DESCRIPTION_HEADING_TAGS and idx == 0 and not line.endswith(":"):
                line = f"{line}:"
            lines.append(line)

    if lines:
        return "\n".join(lines)

    fallback_lines = [
        _repair_spacing_artifacts(normalize_text(chunk))
        for chunk in node.get_text("\n", strip=True).splitlines()
        if normalize_text(chunk)
    ]
    return "\n".join(fallback_lines)


def parse_search_results(html: str, base_url: str, now: datetime) -> list[Vacancy]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select('[data-qa="vacancy-serp__vacancy"]')
    results: list[Vacancy] = []
    for card in cards:
        title_link = card.select_one('[data-qa="serp-item__title"]') or card.select_one(
            "a[href*='/vacancy/']"
        )
        if title_link is None:
            continue

        href = title_link.get("href", "")
        if not href:
            continue
        url = urljoin(base_url, href)
        vacancy_id = _extract_vacancy_id(url)
        if not vacancy_id:
            continue

        title = _first_text(card, '[data-qa="serp-item__title-text"]')
        if not title:
            title = normalize_text(title_link.get_text(" ", strip=True))

        company = (
            _first_text(card, '[data-qa="vacancy-serp__vacancy-employer-text"]')
            or _first_text(card, '[data-qa="vacancy-serp__vacancy-employer"]')
            or _first_text(card, '[data-qa="vacancy-serp__vacancy-employer-company-name"]')
        )

        salary = ""
        salary_node = card.select_one('[data-qa^="vacancy-serp__vacancy-compensation"]')
        if salary_node:
            salary = normalize_text(salary_node.get_text(" ", strip=True))

        area = _first_text(card, '[data-qa="vacancy-serp__vacancy-address"]')
        snippet_parts: list[str] = []
        seen_snippet_parts: set[str] = set()
        for text in _collect_texts(
            card,
            (
                '[data-qa="short_description"],'
                '[data-qa="vacancy-serp__vacancy_snippet_responsibility"],'
                '[data-qa="vacancy-serp__vacancy_snippet_requirement"],'
                '[data-qa^="vacancy-serp__vacancy_snippet"],'
                '[data-qa="vacancy-serp__vacancy-work-format"],'
                '[data-qa="vacancy-serp__vacancy-work-schedule"],'
                '[data-qa="vacancy-serp__vacancy-experience"],'
                '[data-qa="skills-element"]'
            ),
        ):
            if text in seen_snippet_parts:
                continue
            seen_snippet_parts.add(text)
            snippet_parts.append(text)
        snippet = "\n".join(snippet_parts)
        activity_text = _first_text(card, '[data-qa="vacancy-serp-item-activity"]')
        published_at = parse_hh_relative_date(activity_text, now)
        salary_from, salary_to = parse_salary_range(salary)

        results.append(
            Vacancy(
                vacancy_id=vacancy_id,
                url=url,
                title=title,
                company=company,
                salary_raw=salary,
                salary_from=salary_from,
                salary_to=salary_to,
                area=area,
                snippet=snippet,
                activity_text=activity_text,
                published_at=published_at,
                date_unknown=published_at is None,
            )
        )
    return results


def parse_vacancy_detail(html: str, vacancy: Vacancy) -> Vacancy:
    soup = BeautifulSoup(html, "lxml")
    title = _first_text(soup, '[data-qa="vacancy-title"]')
    company = _first_text(soup, '[data-qa="vacancy-company-name"]')
    salary = _first_text(soup, '[data-qa="vacancy-salary"]')
    description = ""
    description_node = soup.select_one('[data-qa="vacancy-description"]')
    if description_node:
        description = _extract_structured_description(description_node)
    area = (
        _first_text(soup, '[data-qa="vacancy-view-location"]')
        or _first_text(soup, '[data-qa="vacancy-address"]')
        or vacancy.area
    )

    if title:
        vacancy.title = title
    if company:
        vacancy.company = company
    if salary:
        vacancy.salary_raw = salary
        vacancy.salary_from, vacancy.salary_to = parse_salary_range(salary)
    if description:
        vacancy.description = description
    vacancy.area = area
    return vacancy


def parse_api_description_html(description_html: str) -> str:
    html = description_html.strip()
    if not html:
        return ""
    soup = BeautifulSoup(f"<div>{html}</div>", "lxml")
    container = soup.select_one("div")
    if container is None:
        return ""
    return _extract_structured_description(container)

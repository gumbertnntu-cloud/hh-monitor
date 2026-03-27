from __future__ import annotations

import re
from functools import lru_cache

from .models import Vacancy
from .utils import normalize_text

try:
    import snowballstemmer
except Exception:  # noqa: BLE001
    snowballstemmer = None

RU_WORD_RE = re.compile(r"[а-яё]+", re.IGNORECASE)
EN_WORD_RE = re.compile(r"[a-z]+", re.IGNORECASE)
TOKEN_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)

if snowballstemmer is not None:
    _RU_STEMMER = snowballstemmer.stemmer("russian")
    _EN_STEMMER = snowballstemmer.stemmer("english")
else:
    _RU_STEMMER = None
    _EN_STEMMER = None


def _fallback_ru_stem(token: str) -> str:
    endings = [
        "иями",
        "ями",
        "ами",
        "иями",
        "его",
        "ого",
        "ему",
        "ому",
        "ыми",
        "ими",
        "иях",
        "ах",
        "ях",
        "ов",
        "ев",
        "ей",
        "ой",
        "ий",
        "ый",
        "ая",
        "яя",
        "ую",
        "юю",
        "ам",
        "ям",
        "ом",
        "ем",
        "ою",
        "ею",
        "а",
        "я",
        "ы",
        "и",
        "е",
        "у",
        "ю",
        "о",
    ]
    for ending in endings:
        if token.endswith(ending) and len(token) - len(ending) >= 3:
            return token[: -len(ending)]
    return token


def _fallback_en_lemma(token: str) -> str:
    irregular = {
        "men": "man",
        "women": "woman",
        "people": "person",
        "children": "child",
        "teeth": "tooth",
        "feet": "foot",
    }
    if token in irregular:
        return irregular[token]
    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    if token.endswith("es") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and len(token) > 3:
        return token[:-1]
    return token


@lru_cache(maxsize=8192)
def _normalize_token(token: str) -> str:
    token_norm = normalize_text(token).lower()
    if not token_norm:
        return ""

    if _RU_STEMMER is not None and RU_WORD_RE.search(token_norm):
        return _RU_STEMMER.stemWord(token_norm)
    if _EN_STEMMER is not None and EN_WORD_RE.search(token_norm):
        return _EN_STEMMER.stemWord(token_norm)
    if RU_WORD_RE.search(token_norm):
        return _fallback_ru_stem(token_norm)
    if EN_WORD_RE.search(token_norm):
        return _fallback_en_lemma(token_norm)
    return token_norm


def _lemma_tokens(value: str) -> list[str]:
    text = normalize_text(value).lower()
    if not text:
        return []
    return [_normalize_token(token) for token in TOKEN_RE.findall(text) if token]


def _contains_token_sequence(value_tokens: list[str], keyword_tokens: list[str]) -> bool:
    if not value_tokens or not keyword_tokens:
        return False
    if len(keyword_tokens) == 1:
        return keyword_tokens[0] in value_tokens
    window = len(keyword_tokens)
    for idx in range(0, len(value_tokens) - window + 1):
        if value_tokens[idx : idx + window] == keyword_tokens:
            return True
    return False


def _contains_keyword(value: str, keyword: str) -> bool:
    value_tokens = _lemma_tokens(value)
    keyword_tokens = _lemma_tokens(keyword)
    if value_tokens and keyword_tokens:
        return _contains_token_sequence(value_tokens, keyword_tokens)
    return normalize_text(keyword).lower() in normalize_text(value).lower()


def _include_fields_for_keyword(
    vacancy: Vacancy,
    keyword: str,
    include_description: bool,
    include_snippet: bool = True,
) -> dict[str, str]:
    fields: dict[str, str] = {
        "title": vacancy.title,
        "roles": vacancy.professional_roles,
    }

    keyword_text = normalize_text(keyword)
    keyword_tokens = _lemma_tokens(keyword_text)
    is_short_acronym = (
        len(keyword_tokens) == 1
        and keyword_text.isascii()
        and keyword_text.upper() == keyword_text
        and len(keyword_text) <= 5
    )
    if is_short_acronym:
        return fields

    if include_snippet:
        fields["snippet"] = vacancy.snippet
    if include_description:
        fields["description"] = vacancy.description
    return fields


def _exclude_fields_for_vacancy(vacancy: Vacancy, include_description: bool) -> dict[str, str]:
    fields: dict[str, str] = {
        "title": vacancy.title,
        "company": vacancy.company,
        "snippet": vacancy.snippet,
    }
    if include_description:
        fields["description"] = vacancy.description
    return fields


def match_exclude_keywords(
    vacancy: Vacancy,
    exclude_keywords: list[str],
    *,
    include_description: bool,
) -> tuple[bool, str]:
    exclude_hits: list[str] = []
    exclude_fields = _exclude_fields_for_vacancy(vacancy, include_description)
    for keyword in exclude_keywords:
        for field_name, value in exclude_fields.items():
            if value and _contains_keyword(value, keyword):
                exclude_hits.append(f'exclude:{field_name}("{keyword}")')
                break
    if exclude_hits:
        return True, ", ".join(exclude_hits)
    return False, ""


def filter_vacancy(
    vacancy: Vacancy,
    include_keywords: list[str],
    exclude_keywords: list[str],
    min_salary: int | None,
    include_description: bool,
    include_snippet: bool = True,
) -> tuple[bool, str]:
    include_hits: list[str] = []

    if include_keywords:
        for keyword in include_keywords:
            include_fields = _include_fields_for_keyword(
                vacancy,
                keyword,
                include_description,
                include_snippet=include_snippet,
            )
            for field_name, value in include_fields.items():
                if value and _contains_keyword(value, keyword):
                    include_hits.append(f'include:{field_name}("{keyword}")')
                    break
        if not include_hits:
            return False, "include:not_matched"

    excluded, exclude_reason = match_exclude_keywords(
        vacancy,
        exclude_keywords,
        include_description=include_description,
    )
    if excluded:
        return False, exclude_reason

    if min_salary is not None:
        salary_candidates = [
            value for value in [vacancy.salary_from, vacancy.salary_to] if value is not None
        ]
        if not salary_candidates:
            return False, "salary:unknown"
        if max(salary_candidates) < min_salary:
            return False, f"salary:<{min_salary}"
        include_hits.append(f"salary:>={min_salary}")

    if not include_hits:
        include_hits.append("include:empty_rules")
    return True, ", ".join(include_hits)

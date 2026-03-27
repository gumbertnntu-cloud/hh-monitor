from __future__ import annotations

import hashlib
import random
import re
import time
from collections.abc import Iterable
from datetime import datetime, timedelta

RU_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}


def normalize_text(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def to_local_naive_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone().replace(tzinfo=None)


def hash_normalized(fields: Iterable[str]) -> str:
    payload = "|".join(normalize_text(item).lower() for item in fields)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_salary_range(salary_raw: str) -> tuple[int | None, int | None]:
    text = normalize_text(salary_raw).lower().replace("₽", "")
    if not text:
        return None, None

    numbers = [int(chunk.replace(" ", "")) for chunk in re.findall(r"\d[\d ]*", text)]
    if not numbers:
        return None, None

    if "от" in text and len(numbers) >= 1:
        return numbers[0], None
    if "до" in text and len(numbers) >= 1:
        return None, numbers[0]
    if len(numbers) >= 2:
        return numbers[0], numbers[1]
    return numbers[0], numbers[0]


def parse_hh_relative_date(activity_text: str, now: datetime) -> datetime | None:
    text = normalize_text(activity_text).lower()
    if not text:
        return None

    if "сегодня" in text:
        return now
    if "вчера" in text:
        return now - timedelta(days=1)

    match = re.search(
        r"(\d+)\s+(минут|минуты|минуту|час|часа|часов|день|дня|дней|неделю|недели|недель|месяц|месяца|месяцев)",
        text,
    )
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        if unit.startswith("минут"):
            return now - timedelta(minutes=value)
        if unit.startswith("час"):
            return now - timedelta(hours=value)
        if unit.startswith("д"):
            return now - timedelta(days=value)
        if unit.startswith("недел") or unit.startswith("неде"):
            return now - timedelta(days=value * 7)
        if unit.startswith("месяц"):
            return now - timedelta(days=value * 30)

    if "более месяца" in text:
        return now - timedelta(days=31)

    date_match = re.search(
        r"(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)(?:\s+(\d{4}))?",
        text,
    )
    if date_match:
        day = int(date_match.group(1))
        month_name = date_match.group(2)
        year = int(date_match.group(3) or now.year)
        month = RU_MONTHS[month_name]
        parsed = datetime(year, month, day)
        if parsed > now:
            parsed = parsed.replace(year=year - 1)
        return parsed

    return None


def random_delay(min_sec: float, max_sec: float, jitter_sec: float) -> None:
    value = random.uniform(min_sec, max_sec) + random.uniform(0, jitter_sec)
    time.sleep(value)

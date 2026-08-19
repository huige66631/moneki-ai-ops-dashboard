from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[\s\u3000]+", "", value)
    return re.sub(r"[，。！？、,.!?：:；;（）()「」『』\"'‘’“”]", "", value)


def _resolve_year(month: int, bounds: tuple[date, date]) -> int | None:
    if bounds[0].year == bounds[1].year:
        return bounds[0].year
    candidates: set[int] = set()
    for candidate in range(bounds[0].year, bounds[1].year + 1):
        start = date(candidate, month, 1)
        end = date(candidate + (month == 12), 1 if month == 12 else month + 1, 1) - timedelta(days=1)
        if start <= bounds[1] and end >= bounds[0]:
            candidates.add(candidate)
    return candidates.pop() if len(candidates) == 1 else None


def parse_date_range(text: str, bounds: tuple[date, date]) -> tuple[date, date] | None:
    full_date_pattern = re.compile(
        r"(20\d{2})\s*(?:年\s*|[-/]\s*)(\d{1,2})\s*"
        r"(?:月\s*|[-/]\s*)(\d{1,2})\s*[日号]?"
    )
    full_dates: list[date] = []
    for match in full_date_pattern.finditer(text):
        try:
            full_dates.append(date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
        except ValueError:
            return None
    if full_dates:
        if len(full_dates) >= 2:
            return full_dates[0], full_dates[1]
        return full_dates[0], full_dates[0]

    month_match = re.search(r"(20\d{2})\s*[年/-]\s*(\d{1,2})\s*月", text)
    if month_match:
        year = int(month_match.group(1))
        month = int(month_match.group(2))
    else:
        month_match = re.search(r"(\d{1,2})\s*月", text)
        if month_match:
            month = int(month_match.group(1))
            if not 1 <= month <= 12:
                return None
            year = _resolve_year(month, bounds)
            if year is None:
                return None
        else:
            month_match = re.search(r"(?:(20\d{2})\s*年\s*)?(十[一二]?|[一二三四五六七八九])月", text)
            if not month_match:
                return None
            year = int(month_match.group(1)) if month_match.group(1) else None
            month = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}[month_match.group(2)]
            if year is None:
                year = _resolve_year(month, bounds)
                if year is None:
                    return None

    if not 1 <= month <= 12:
        return None
    start = date(year, month, 1)
    end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return start, end - timedelta(days=1)

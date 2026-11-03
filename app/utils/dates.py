"""Utilidades de fecha y hora locales."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


def today() -> date:
    return date.today()


def start_of_day(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    return datetime.combine(value, time.min)


def end_of_day(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.replace(hour=23, minute=59, second=59, microsecond=999999)
    return datetime.combine(value, time.max).replace(microsecond=0)


def start_of_month(value: date) -> date:
    return value.replace(day=1)


def add_days(value: date, days: int) -> date:
    return value + timedelta(days=days)


def week_range(any_day: date) -> tuple[date, date]:
    monday = any_day - timedelta(days=any_day.weekday())
    return monday, monday + timedelta(days=6)


def month_range(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return first, nxt - timedelta(days=1)


def fmt_datetime(value: datetime | None) -> str:
    return value.strftime("%d/%m/%Y %H:%M") if value else ""


def fmt_date(value: date | datetime | None) -> str:
    if not value:
        return ""
    return value.strftime("%d/%m/%Y")


def fmt_time(value: datetime | None) -> str:
    return value.strftime("%H:%M") if value else ""

"""Formato de numeros y cantidades."""
from __future__ import annotations


def fmt_int(value: int | None) -> str:
    return f"{int(value or 0):,}".replace(",", ".")


def fmt_signed(value: int | None) -> str:
    value = int(value or 0)
    if value > 0:
        return f"+{fmt_int(value)}"
    return fmt_int(value)

"""Tiny, explicit value normalisation.

Only formatting is harmonised here (decimal comma, German yes/no, connector spelling).
Nothing is looked up, inferred or filled in.
"""
from __future__ import annotations

import re


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def number(value: str | None) -> str | None:
    """'1,83' / '1.83' / '0.10' -> '1.83' / '1.83' / '0.1'. Non-numbers are kept as-is."""
    value = blank_to_none(value)
    if value is None:
        return None
    candidate = value.replace(",", ".")
    try:
        as_float = float(candidate)
    except ValueError:
        return value
    text = f"{as_float:.6f}".rstrip("0").rstrip(".")
    return text


def price(value: str | None) -> str | None:
    """Keep two decimals for money: '9,8' -> '9.80'."""
    value = blank_to_none(value)
    if value is None:
        return None
    try:
        return f"{float(value.replace(',', '.')):.2f}"
    except ValueError:
        return value


_STERILITY = {
    "ja": "sterile", "yes": "sterile", "sterile": "sterile", "steril": "sterile",
    "nein": "non_sterile", "no": "non_sterile", "non_sterile": "non_sterile", "unsteril": "non_sterile",
}


def sterility(value: str | None) -> str | None:
    value = blank_to_none(value)
    if value is None:
        return None
    return _STERILITY.get(value.lower(), value)


def connector(value: str | None) -> str | None:
    """'Luer-Lock' / 'luer_lock' / 'Luer Lock' -> 'luer_lock'."""
    value = blank_to_none(value)
    if value is None:
        return None
    return re.sub(r"[\s\-]+", "_", value.strip().lower())


def sku(value: str | None) -> str | None:
    value = blank_to_none(value)
    return value.upper() if value else None


def gtin_check_digit_ok(gtin: str) -> tuple[bool, int | None]:
    """GS1 check digit for GTIN-8/12/13/14. Returns (is_valid, expected_digit)."""
    if not gtin.isdigit() or len(gtin) not in (8, 12, 13, 14):
        return False, None
    digits = [int(c) for c in gtin]
    body, check = digits[:-1], digits[-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    expected = (10 - total % 10) % 10
    return expected == check, expected

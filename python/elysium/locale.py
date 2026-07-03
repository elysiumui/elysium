"""Locale-aware formatting — Tier-2 Qt parity (QLocale).

Formats numbers, currency, dates, and times for a locale. Uses ``Babel`` (full
CLDR) when it's installed; otherwise falls back to a small built-in table for
common locales — no hard dependency, thread-safe (never touches the global
``setlocale``).

    from elysium import locale as L
    L.format_number(1234567.5, locale="de")   # "1.234.567,5"
    L.format_currency(9.9, "USD", locale="en") # "$9.90"
    L.format_date(date.today(), locale="fr")
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional

from elysium.i18n import get_locale

try:  # optional, richer CLDR data
    import babel.numbers as _bn
    import babel.dates as _bd
    _HAVE_BABEL = True
except Exception:
    _HAVE_BABEL = False


# Minimal fallback data: (decimal_sep, group_sep, currency_prefix?, symbol map).
_SEPS = {
    "en": (".", ","),
    "de": (",", "."),
    "fr": (",", " "),   # narrow no-break space
    "es": (",", "."),
    "ar": (".", ","),
    "he": (".", ","),
    "ja": (".", ","),
    "zh": (".", ","),
}
_CURRENCY = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}


def _lang(locale: Optional[str]) -> str:
    return (locale or get_locale()).replace("-", "_").split("_")[0].lower()


def _seps(locale: Optional[str]) -> tuple[str, str]:
    return _SEPS.get(_lang(locale), (".", ","))


def format_decimal(value: float, locale: Optional[str] = None, *,
                   decimals: Optional[int] = None) -> str:
    loc = locale or get_locale()
    if _HAVE_BABEL:
        if decimals is not None:
            fmt = "#,##0." + ("0" * decimals) if decimals > 0 else "#,##0"
            return _bn.format_decimal(value, format=fmt, locale=loc)
        return _bn.format_decimal(value, locale=loc)
    return _fallback_number(value, locale, decimals)


def format_number(value: float, locale: Optional[str] = None) -> str:
    """Group-separated number in the locale's convention."""
    return format_decimal(value, locale)


def _fallback_number(value: float, locale: Optional[str], decimals: Optional[int]) -> str:
    dec, grp = _seps(locale)
    neg = value < 0
    value = abs(value)
    if decimals is not None:
        s = f"{value:.{decimals}f}"
    else:
        s = f"{value:.6f}".rstrip("0").rstrip(".") if value != int(value) else f"{int(value)}"
    int_part, _, frac_part = s.partition(".")
    # Group the integer part in threes.
    groups = []
    while len(int_part) > 3:
        groups.insert(0, int_part[-3:])
        int_part = int_part[:-3]
    groups.insert(0, int_part)
    out = grp.join(groups)
    if frac_part:
        out += dec + frac_part
    return ("-" if neg else "") + out


def format_currency(value: float, currency: str = "USD",
                    locale: Optional[str] = None) -> str:
    loc = locale or get_locale()
    if _HAVE_BABEL:
        return _bn.format_currency(value, currency, locale=loc)
    symbol = _CURRENCY.get(currency, currency + " ")
    amount = _fallback_number(value, locale, 2)
    return f"{symbol}{amount}"


def format_percent(value: float, locale: Optional[str] = None) -> str:
    loc = locale or get_locale()
    if _HAVE_BABEL:
        return _bn.format_percent(value, locale=loc)
    return _fallback_number(value * 100.0, locale, 0) + "%"


def format_date(value: _dt.date, locale: Optional[str] = None, *,
                fmt: str = "medium") -> str:
    loc = locale or get_locale()
    if _HAVE_BABEL:
        return _bd.format_date(value, format=fmt, locale=loc)
    return value.isoformat()


def format_datetime(value: _dt.datetime, locale: Optional[str] = None, *,
                    fmt: str = "medium") -> str:
    loc = locale or get_locale()
    if _HAVE_BABEL:
        return _bd.format_datetime(value, format=fmt, locale=loc)
    return value.isoformat(sep=" ", timespec="seconds")


def format_time(value: _dt.time, locale: Optional[str] = None, *,
                fmt: str = "medium") -> str:
    loc = locale or get_locale()
    if _HAVE_BABEL:
        return _bd.format_time(value, format=fmt, locale=loc)
    return value.isoformat(timespec="seconds")


def have_babel() -> bool:
    return _HAVE_BABEL


__all__ = [
    "format_number", "format_decimal", "format_currency", "format_percent",
    "format_date", "format_datetime", "format_time", "have_babel",
]

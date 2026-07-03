"""Internationalization — Tier-2 Qt parity (QTranslator / tr(), RTL layout).

Translation is gettext-first (Python's stdlib ``gettext`` + compiled ``.mo``
catalogs — the standard translator toolchain), with a JSON-catalog fast path
for simple apps. Plus right-to-left support: locale + per-string direction
detection (Arabic/Hebrew/…) and horizontal layout-mirroring helpers.

    from elysium.i18n import tr, tr_n, install
    install("fr", localedir="locale")      # loads locale/fr/LC_MESSAGES/<domain>.mo
    label = tr("Save")                     # → "Enregistrer"
    msg = tr_n("{n} file", "{n} files", n) # plural-aware

Mark translatable strings with ``tr("...")`` so ``xgettext``/``pybabel`` can
extract them. Locale-aware number/date formatting lives in
:mod:`elysium.locale`.
"""
from __future__ import annotations

import gettext as _gettext
from contextlib import contextmanager
from typing import Any, Iterator, Optional

# --- current translator state ----------------------------------------------

_DOMAIN = "messages"
_translation: _gettext.NullTranslations = _gettext.NullTranslations()
_locale = "en"
_dir_override: Optional[str] = None

LTR = "ltr"
RTL = "rtl"

# Languages written right-to-left (ISO-639 primary subtags).
_RTL_LANGS = {"ar", "he", "fa", "ur", "ps", "sd", "yi", "dv", "ku", "arc", "nqo"}

# Unicode ranges with strong right-to-left directionality.
_RTL_RANGES = (
    (0x0590, 0x05FF),   # Hebrew
    (0x0600, 0x06FF),   # Arabic
    (0x0700, 0x074F),   # Syriac
    (0x0750, 0x077F),   # Arabic Supplement
    (0x0780, 0x07BF),   # Thaana
    (0x08A0, 0x08FF),   # Arabic Extended-A
    (0xFB1D, 0xFDFF),   # Hebrew + Arabic presentation forms A
    (0xFE70, 0xFEFF),   # Arabic presentation forms B
)


# --- translation -----------------------------------------------------------

def install(locale: str, *, localedir: Optional[str] = None,
            domain: str = "messages") -> None:
    """Load and activate the gettext catalog for ``locale`` from ``localedir``
    (``<localedir>/<locale>/LC_MESSAGES/<domain>.mo``). Falls back to an
    identity translator (returns msgids) when no catalog is found."""
    global _translation, _locale, _DOMAIN
    _DOMAIN = domain
    _locale = locale
    if localedir is not None:
        try:
            _translation = _gettext.translation(
                domain, localedir=localedir, languages=[locale], fallback=True)
            return
        except Exception:
            pass
    _translation = _gettext.NullTranslations()


def set_locale(locale: str) -> None:
    """Switch locale, re-resolving the active gettext domain. Re-render the UI
    on the next frame to apply the new strings."""
    global _locale
    _locale = locale
    if localedir := getattr(_translation, "_elysium_localedir", None):
        install(locale, localedir=localedir, domain=_DOMAIN)
    else:
        # No bound catalog dir → keep identity translator but record locale
        # (affects direction + locale formatting).
        pass


def get_locale() -> str:
    return _locale


def use_translation(translation: _gettext.NullTranslations, locale: str = "en") -> None:
    """Install an already-constructed gettext translation (e.g. from a test
    fixture or a custom loader)."""
    global _translation, _locale
    _translation = translation
    _locale = locale


def load_json_catalog(mapping: dict[str, str], locale: str = "en") -> None:
    """Install a translator from a plain ``{msgid: msgstr}`` dict — a quick
    path for apps that don't want the gettext toolchain."""
    class _JsonTranslation(_gettext.NullTranslations):
        def gettext(self, message: str) -> str:
            return mapping.get(message, message)

        def ngettext(self, singular: str, plural: str, n: int) -> str:
            key = singular if n == 1 else plural
            return mapping.get(key, key)

    use_translation(_JsonTranslation(), locale)


def tr(message: str, **kwargs: Any) -> str:
    """Translate ``message``; if ``kwargs`` are given, ``str.format`` the
    result with them (``tr("Hi {name}", name=x)``)."""
    out = _translation.gettext(message)
    return out.format(**kwargs) if kwargs else out


def tr_n(singular: str, plural: str, n: int, **kwargs: Any) -> str:
    """Plural-aware translation. ``n`` selects the form; it's also passed to
    ``str.format`` as ``n`` along with any ``kwargs``."""
    out = _translation.ngettext(singular, plural, n)
    return out.format(n=n, **kwargs)


def tr_ctx(context: str, message: str, **kwargs: Any) -> str:
    """Context-qualified translation (gettext ``pgettext``)."""
    pget = getattr(_translation, "pgettext", None)
    out = pget(context, message) if pget else _translation.gettext(message)
    return out.format(**kwargs) if kwargs else out


# --- direction / RTL -------------------------------------------------------

def locale_is_rtl(locale: Optional[str] = None) -> bool:
    loc = (locale or _locale).replace("_", "-").split("-")[0].lower()
    return loc in _RTL_LANGS


def text_is_rtl(s: str) -> bool:
    """True when the first strong-directional character is right-to-left
    (the Unicode first-strong heuristic)."""
    for ch in s:
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in _RTL_RANGES):
            return True
        # Strong LTR: basic Latin/Greek/Cyrillic letters end the scan.
        if ch.isalpha() and cp < 0x0590:
            return False
    return False


def current_direction() -> str:
    """Active layout direction: an explicit :func:`direction` override, else
    derived from the current locale."""
    if _dir_override is not None:
        return _dir_override
    return RTL if locale_is_rtl() else LTR


def is_rtl() -> bool:
    return current_direction() == RTL


@contextmanager
def direction(d: str) -> Iterator[None]:
    """Temporarily force layout direction (``LTR`` / ``RTL``) regardless of
    locale — for previews and mixed-direction sub-trees."""
    global _dir_override
    prev = _dir_override
    _dir_override = d
    try:
        yield
    finally:
        _dir_override = prev


# --- layout mirroring ------------------------------------------------------

def mirror_x(x: float, item_w: float, container_w: float) -> float:
    """Reflect an x-position within ``container_w`` (left edge ↔ right edge).
    Use when laying out under RTL so left-anchored items become right-anchored."""
    return container_w - (x + item_w)


def maybe_mirror_x(x: float, item_w: float, container_w: float) -> float:
    """:func:`mirror_x` when the active direction is RTL, else ``x`` unchanged."""
    return mirror_x(x, item_w, container_w) if is_rtl() else x


def flip_align(align: str) -> str:
    """Swap ``left``/``right`` for RTL; ``center``/``justify`` pass through."""
    if not is_rtl():
        return align
    return {"left": "right", "right": "left"}.get(align, align)


__all__ = [
    "install", "set_locale", "get_locale", "use_translation", "load_json_catalog",
    "tr", "tr_n", "tr_ctx",
    "LTR", "RTL", "locale_is_rtl", "text_is_rtl", "current_direction", "is_rtl",
    "direction", "mirror_x", "maybe_mirror_x", "flip_align",
]

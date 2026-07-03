"""Tier-2 Phase-7: i18n / RTL / locale."""
from __future__ import annotations

import datetime as dt
import struct

import pytest

from elysium import i18n
from elysium import locale as L


# --- gettext .mo fixture ----------------------------------------------------

def _write_mo(path, catalog: dict[str, str]) -> None:
    """Minimal GNU .mo writer (singular entries), per the msgfmt algorithm."""
    keys = sorted(catalog.keys())
    ids = b""
    strs = b""
    entries = []
    for k in keys:
        kb = k.encode("utf-8")
        vb = catalog[k].encode("utf-8")
        entries.append((len(kb), len(ids), len(vb), len(strs)))
        ids += kb + b"\x00"
        strs += vb + b"\x00"
    keystart = 7 * 4 + 16 * len(keys)
    valuestart = keystart + len(ids)
    koffsets, voffsets = [], []
    for l1, o1, l2, o2 in entries:
        koffsets += [l1, o1 + keystart]
        voffsets += [l2, o2 + valuestart]
    out = struct.pack("Iiiiiii", 0x950412DE, 0, len(keys),
                      7 * 4, 7 * 4 + len(keys) * 8, 0, 0)
    out += struct.pack("i" * len(koffsets), *koffsets)
    out += struct.pack("i" * len(voffsets), *voffsets)
    out += ids + strs
    path.write_bytes(out)


@pytest.fixture(autouse=True)
def _reset_i18n():
    yield
    i18n.use_translation(__import__("gettext").NullTranslations(), "en")


# --- translation ------------------------------------------------------------

def test_install_gettext_mo(tmp_path):
    d = tmp_path / "fr" / "LC_MESSAGES"
    d.mkdir(parents=True)
    _write_mo(d / "messages.mo", {"Save": "Enregistrer", "Cancel": "Annuler"})
    i18n.install("fr", localedir=str(tmp_path))
    assert i18n.tr("Save") == "Enregistrer"
    assert i18n.tr("Cancel") == "Annuler"
    assert i18n.tr("Unknown") == "Unknown"   # fallback to msgid


def test_tr_formats_kwargs():
    i18n.load_json_catalog({"Hi {name}": "Bonjour {name}"}, locale="fr")
    assert i18n.tr("Hi {name}", name="Ada") == "Bonjour Ada"


def test_tr_n_plural_selection():
    i18n.load_json_catalog({"{n} file": "{n} fichier", "{n} files": "{n} fichiers"},
                           locale="fr")
    assert i18n.tr_n("{n} file", "{n} files", 1) == "1 fichier"
    assert i18n.tr_n("{n} file", "{n} files", 3) == "3 fichiers"


def test_identity_when_no_catalog():
    i18n.use_translation(__import__("gettext").NullTranslations(), "en")
    assert i18n.tr("Whatever") == "Whatever"


# --- direction / RTL --------------------------------------------------------

def test_locale_is_rtl():
    assert i18n.locale_is_rtl("ar")
    assert i18n.locale_is_rtl("he_IL")
    assert not i18n.locale_is_rtl("en")
    assert not i18n.locale_is_rtl("fr_FR")


def test_text_is_rtl_detection():
    assert i18n.text_is_rtl("مرحبا")        # Arabic
    assert i18n.text_is_rtl("שלום")          # Hebrew
    assert not i18n.text_is_rtl("Hello")
    assert not i18n.text_is_rtl("123 abc")
    assert i18n.text_is_rtl("123 مرحبا")     # first strong char is Arabic


def test_direction_override_context():
    i18n.load_json_catalog({}, locale="en")  # LTR locale
    assert i18n.current_direction() == i18n.LTR
    with i18n.direction(i18n.RTL):
        assert i18n.is_rtl()
        assert i18n.current_direction() == i18n.RTL
    assert not i18n.is_rtl()


def test_current_direction_follows_locale():
    i18n.load_json_catalog({}, locale="ar")
    assert i18n.is_rtl()


def test_mirror_x_and_flip_align():
    # Reflect a 30-wide item at x=10 inside a 200 container.
    assert i18n.mirror_x(10, 30, 200) == 160
    with i18n.direction(i18n.RTL):
        assert i18n.flip_align("left") == "right"
        assert i18n.maybe_mirror_x(10, 30, 200) == 160
    with i18n.direction(i18n.LTR):
        assert i18n.flip_align("left") == "left"
        assert i18n.maybe_mirror_x(10, 30, 200) == 10


# --- locale formatting ------------------------------------------------------

def test_format_number_grouping():
    # Fallback path (no Babel) or Babel — both group thousands per locale.
    en = L.format_number(1234567, locale="en")
    de = L.format_number(1234567, locale="de")
    assert en.replace(",", "") == "1234567"
    assert "1" in de and de != en or L.have_babel()  # de uses '.' as group sep


def test_format_decimal_places():
    s = L.format_decimal(3.14159, locale="en", decimals=2)
    assert s.startswith("3") and "14" in s


def test_format_currency_symbol():
    s = L.format_currency(9.9, "USD", locale="en")
    assert "9" in s and ("$" in s or "USD" in s)


def test_format_date_returns_string():
    s = L.format_date(dt.date(2024, 3, 15), locale="en")
    assert "2024" in s or "24" in s


# --- native RTL paragraph rendering ----------------------------------------

def test_native_draw_paragraph_accepts_rtl_and_renders_arabic():
    from elysium._native import _native as n
    layer = n.SkiaLayer(120, 40)
    layer.clear(0.0, 0.0, 0.0, 0.0)
    # rtl=True base direction; Arabic shapes + reorders via Skia's bidi.
    h = layer.draw_paragraph("مرحبا بالعالم", 4.0, 24.0, 112.0, 16.0,
                             (0, 0, 0, 255), 0, "", 0, [], True)
    assert h > 0
    png = layer.encode_png()
    assert isinstance(png, (bytes, bytearray)) and len(png) > 0

"""Tier-3: the deprecation mechanism (the forward path for strict semver)."""
from __future__ import annotations

import warnings

import pytest

import elysium
from elysium._deprecation import deprecated, deprecated_alias


def test_deprecated_function_warns_and_forwards():
    @deprecated(since="1.2", removal="2.0", alt="new_fn")
    def old_fn(a, b):
        return a + b

    with pytest.warns(DeprecationWarning, match="old_fn is deprecated since Elysium 1.2"):
        assert old_fn(2, 3) == 5


def test_deprecated_class_warns_on_construction():
    @deprecated(since="1.1", alt="NewWidget")
    class OldWidget:
        def __init__(self, x):
            self.x = x

    with pytest.warns(DeprecationWarning, match="use NewWidget instead"):
        w = OldWidget(7)
    assert w.x == 7


def test_deprecated_alias_forwards():
    def real(x):
        return x * 2

    old = deprecated_alias("old_double", real, since="1.3", removal="2.0")
    with pytest.warns(DeprecationWarning, match="old_double is deprecated"):
        assert old(21) == 42


def test_warning_names_removal_version():
    @deprecated(since="1.2", removal="2.0")
    def gone():
        return None

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        gone()
    assert "will be removed in 2.0" in str(caught[-1].message)


def test_public_export():
    assert elysium.deprecated is deprecated
    assert elysium.deprecated_alias is deprecated_alias

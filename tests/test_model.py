"""Parsing, and the three places the controller's vocabulary differs from Home Assistant's."""

from __future__ import annotations

import pytest
from luxor import (
    COLOUR_NONE,
    DMX_SENTINEL,
    Colour,
    Group,
    Theme,
    ThemeGroup,
    is_static_colour,
    normalise_hue,
)


def test_group_uses_the_short_field_names():
    group = Group.from_json({"Name": "Group 01", "Grp": 1, "Inten": 50, "Colr": 3})
    assert (group.number, group.name, group.intensity, group.colr) == (1, "Group 01", 50, 3)
    assert group.is_on


def test_theme_group_uses_the_long_field_names():
    """The same three concepts, different keys. Reading one shape and writing the other is how a
    colour write silently goes nowhere."""
    entry = ThemeGroup.from_json({"GroupNumber": 1, "Intensity": 100, "Color": 3})
    assert (entry.number, entry.intensity, entry.colour) == (1, 100, 3)
    assert entry.to_json() == {"GroupNumber": 1, "Intensity": 100, "Color": 3}


def test_the_two_shapes_do_not_parse_each_other():
    with pytest.raises(KeyError):
        Group.from_json({"GroupNumber": 1, "Intensity": 100, "Color": 3})
    with pytest.raises(KeyError):
        ThemeGroup.from_json({"Name": "Group 01", "Grp": 1, "Inten": 50, "Colr": 3})


def test_is_on_is_intensity_not_colour():
    assert not Group.from_json({"Name": "a", "Grp": 1, "Inten": 0, "Colr": 3}).is_on
    assert Group.from_json({"Name": "a", "Grp": 1, "Inten": 1, "Colr": 0}).is_on


@pytest.mark.parametrize(("raw", "expected"), [(0, 0), (1, 1), (359, 359), (360, 0)])
def test_hue_360_folds_to_zero(raw, expected):
    """The device range is 0-359, the palette reports up to 360, Home Assistant wants [0, 360).
    Without this an entity written at hue 0 reads back at 360 and flaps forever."""
    assert normalise_hue(raw) == expected


def test_colour_hs_needs_no_scaling():
    colour = Colour.from_json({"C": 5, "Hue": 0, "Sat": 100})
    assert colour.hs == (0.0, 100.0)


def test_colour_zero_is_not_a_colour():
    """`Colr 0` means the group is configured as non-colour fixtures. Reporting it as black would
    be a plausible-looking lie."""
    group = Group.from_json({"Name": "a", "Grp": 1, "Inten": 100, "Colr": COLOUR_NONE})
    assert not group.has_static_colour
    assert not is_static_colour(COLOUR_NONE)


@pytest.mark.parametrize("colr", [251, 255, 260])
def test_colour_wheels_are_not_static_colours(colr):
    group = Group.from_json({"Name": "a", "Grp": 1, "Inten": 100, "Colr": colr})
    assert group.is_colour_wheel
    assert not group.has_static_colour


def test_dmx_is_not_a_static_colour():
    group = Group.from_json({"Name": "a", "Grp": 1, "Inten": 100, "Colr": DMX_SENTINEL})
    assert group.is_dmx
    assert not group.has_static_colour


@pytest.mark.parametrize("colr", [1, 125, 250])
def test_palette_indices_are_static_colours(colr):
    assert Group.from_json({"Name": "a", "Grp": 1, "Inten": 0, "Colr": colr}).has_static_colour


def test_theme_on_off_is_a_bool():
    assert Theme.from_json({"Name": "Theme A", "ThemeIndex": 0, "OnOff": 1}).on
    assert not Theme.from_json({"Name": "Theme A", "ThemeIndex": 0, "OnOff": 0}).on


# --- the captures parse ---------------------------------------------------------------------------


def test_every_captured_group_parses(load_fixture):
    groups = [Group.from_json(raw) for raw in load_fixture("group_list_get")["GroupList"]]
    assert len(groups) == 65
    assert all(g.has_static_colour for g in groups)
    assert not any(g.is_on for g in groups)


def test_every_captured_colour_parses_and_is_in_range(load_fixture):
    colours = [Colour.from_json(raw) for raw in load_fixture("color_list_get")["ColorList"]]
    assert len(colours) == 78
    assert all(0 <= c.hue < 360 for c in colours)
    assert all(0 <= c.saturation <= 100 for c in colours)


def test_the_illuminate_all_capture_is_all_non_colour(load_fixture):
    """The measured damage, as a fixture. Every group reads as non-colour fixtures at 75%."""
    groups = [
        Group.from_json(raw)
        for raw in load_fixture("group_list_get_after_illuminate_all")["GroupList"]
    ]
    assert len(groups) == 65
    assert all(not g.has_static_colour for g in groups)
    assert all(g.intensity == 75 for g in groups)

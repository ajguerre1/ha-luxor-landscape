"""The colour write path, and the one property that separates it from what it replaces."""

from __future__ import annotations

import pytest
from luxor import Colour, Group, GroupNameError
from luxor.colour import ColourWriteError, resolve_hs, set_group_colour
from luxor.slots import SlotTable

NOW = "2026-09-09T17:00:00-04:00"


@pytest.fixture
def table() -> SlotTable:
    return SlotTable()


async def _set(client, table, group=23, hue=200, sat=90, theme=0):
    return await set_group_colour(
        client, table, group_number=group, hue=hue, saturation=sat, theme_index=theme, now=NOW
    )


# --- the acceptance property ----------------------------------------------------------------------


async def test_the_colour_survives_a_theme_activation(client, session, table):
    """This is the criterion the design exists for.

    A colour written at group level looks correct until the next theme runs. Because this write
    also updates the theme, the activation re-applies the colour that is already there.
    """
    await _set(client, table)
    assert session.groups[23]["Colr"] == table.slot_for(23)

    await client.illuminate_theme(0, True)

    assert session.groups[23]["Colr"] == table.slot_for(23)
    colour = next(c for c in await client.colour_list() if c.index == table.slot_for(23))
    assert colour.hs == (200.0, 90.0)


async def test_a_group_level_write_alone_would_not_survive(client, session, table):
    """The disarmed control.

    Points the group at a freshly defined slot without touching the theme -- which is what both
    existing open-source Luxor projects do -- and shows the nightly activation taking it away. The
    test above is only meaningful next to this one.
    """
    await client.set_palette_colour(101, 200, 90)
    await client.point_group_at_colour(23, session.groups[23]["Name"], 101)
    assert session.groups[23]["Colr"] == 101

    await client.illuminate_theme(0, True)

    assert session.groups[23]["Colr"] == 1, "the theme did not reclaim the group"


async def test_only_the_named_group_moves(client, session, table):
    before = {n: g["Colr"] for n, g in session.groups.items() if n != 23}
    await _set(client, table)
    after = {n: g["Colr"] for n, g in session.groups.items() if n != 23}
    assert after == before


# --- ordering -------------------------------------------------------------------------------------


async def test_the_slot_is_defined_before_anything_points_at_it(client, session, table):
    """Point first and the group visibly lights in whatever the slot used to mean."""
    await _set(client, table)
    order = [s.method for s in session.sent]
    assert order.index("ColorListSet") < order.index("ThemeSet")
    assert order.index("ColorListSet") < order.index("GroupListEdit")


async def test_the_theme_is_written_as_a_whole(client, session, table):
    """`Groups` is the membership, not a patch. A partial list strips the theme."""
    await _set(client, table)
    sent = next(s for s in session.sent if s.method == "ThemeSet")
    assert len(sent.body["Groups"]) == 65
    assert sent.body["ThemeIndex"] == 0


async def test_intensities_in_the_theme_are_preserved(client, session, table):
    before = {e["GroupNumber"]: e["Intensity"] for e in session.theme_groups[0]}
    await _set(client, table)
    after = {e["GroupNumber"]: e["Intensity"] for e in session.theme_groups[0]}
    assert after == before


async def test_a_repeat_write_does_not_repoint_the_group_again(client, session, table):
    """Second time round the group already points at its slot, so the dangerous call is skipped."""
    first = await _set(client, table)
    assert first.group_repointed
    session.sent.clear()
    second = await _set(client, table, hue=10, sat=20)
    assert not second.group_repointed
    assert "GroupListEdit" not in [s.method for s in session.sent]
    assert second.slot == first.slot


# --- refusals -------------------------------------------------------------------------------------


async def test_a_group_outside_the_theme_is_refused(client, session, table):
    """Theme 2 has two members. Writing colour for any other group there would never be applied."""
    with pytest.raises(ColourWriteError) as err:
        await _set(client, table, group=23, theme=2)
    assert "not a member of theme 2" in str(err.value)
    assert "ThemeSet" not in [s.method for s in session.sent]


async def test_a_group_that_does_not_exist_is_refused(client, session, table):
    with pytest.raises(ColourWriteError):
        await _set(client, table, group=999)
    assert not any(s.method in {"ColorListSet", "ThemeSet", "GroupListEdit"} for s in session.sent)


async def test_a_colliding_name_is_refused_before_the_rename(client, session, table):
    """Two groups sharing a name means `GroupListEdit` would be rejected with 202.

    Caught here rather than at the controller, because a 202 arriving mid-sequence looks like a
    transport failure and the theme has already been written by then.
    """
    session.groups[24]["Name"] = session.groups[23]["Name"]
    with pytest.raises(GroupNameError) as err:
        await _set(client, table)
    assert "also" in str(err.value)
    assert "GroupListEdit" not in [s.method for s in session.sent]


async def test_the_name_comes_from_the_read_inside_this_operation(client, session, table):
    """Not from a cache, and not from anything a user could have renamed.

    Asserted by changing the name on the controller between operations and checking the write
    carries the new one.
    """
    await _set(client, table)
    session.groups[23]["Name"] = "Renamed On Panel"
    session.groups[23]["Colr"] = 1  # force the repoint branch again
    session.sent.clear()

    await _set(client, table, hue=30, sat=40)

    edit = next(s for s in session.sent if s.method == "GroupListEdit")
    assert edit.body["Name"] == "Renamed On Panel"
    assert session.groups[23]["Name"] == "Renamed On Panel", (
        "the group was renamed by its own write"
    )


async def test_a_write_that_does_not_land_raises(client, session, table):
    """Verification is against the controller, not against what we intended."""
    original = session._do_GroupListEdit

    def silently_ignore(body):
        original(body)
        session.groups[23]["Colr"] = 1  # something else won
        return {"Status": 0}

    session._do_GroupListEdit = silently_ignore
    with pytest.raises(ColourWriteError) as err:
        await _set(client, table)
    assert "reads colour 1" in str(err.value)


async def test_a_rename_by_the_write_is_caught(client, session, table):
    original = session._do_GroupListEdit

    def rename_it(body):
        result = original(body)
        session.groups[23]["Name"] = "Mangled"
        return result

    session._do_GroupListEdit = rename_it
    with pytest.raises(ColourWriteError) as err:
        await _set(client, table)
    assert "renamed" in str(err.value)


# --- reporting ------------------------------------------------------------------------------------


def test_resolve_hs_reads_the_palette():
    colours = {1: (43.0, 38.0), 3: (50.0, 5.0)}
    assert resolve_hs(Group(number=1, name="a", intensity=0, colr=1), colours) == (43.0, 38.0)


@pytest.mark.parametrize("colr", [0, 251, 260, 65535])
def test_resolve_hs_returns_none_for_anything_that_is_not_a_static_colour(colr):
    """0 is non-colour fixtures, 251-260 are animated wheels, 65535 is DMX. None is one colour."""
    assert resolve_hs(Group(number=1, name="a", intensity=0, colr=colr), {1: (43.0, 38.0)}) is None


def test_resolve_hs_returns_none_for_a_slot_the_palette_does_not_define():
    """A theme can reference a slot the colour list omits. Reporting a guess would be worse."""
    assert resolve_hs(Group(number=1, name="a", intensity=0, colr=200), {1: (43.0, 38.0)}) is None


async def test_the_reported_colour_follows_the_controller(client, session, table):
    """When a theme repaints a group, the entity's colour changes to match.

    That is what makes the design's no-op visible: if it is working, the nightly theme changes
    nothing, and the way to know is that the reported colour is read rather than remembered.
    """
    await _set(client, table, hue=200, sat=90)
    colours = {c.index: c.hs for c in await client.colour_list()}
    groups = {g.number: g for g in await client.group_list()}
    assert resolve_hs(groups[23], colours) == (200.0, 90.0)

    # Somebody repaints the theme on the faceplate and runs it.
    session.theme_groups[0] = [
        {**e, "Color": 5} if e["GroupNumber"] == 23 else e for e in session.theme_groups[0]
    ]
    await client.illuminate_theme(0, True)

    groups = {g.number: g for g in await client.group_list()}
    assert resolve_hs(groups[23], colours) == (0.0, 100.0)


def test_a_colour_parses_to_the_same_hs_it_was_written_with():
    assert Colour(index=101, hue=200, saturation=90).hs == (200.0, 90.0)

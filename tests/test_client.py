"""Wire-level behaviour of the client, against the captured protocol."""

from __future__ import annotations

import asyncio

import aiohttp
import pytest
from luxor import (
    MAX_GROUP_NAME_BYTES,
    ColourRangeError,
    EmptyBodyError,
    GroupNameError,
    IntensityRangeError,
    LuxorClient,
    LuxorConnectionError,
    LuxorStatusError,
    ThemeGroup,
)

# --- reads ---------------------------------------------------------------------------------------


async def test_controller_name(client):
    assert (await client.controller_name()).startswith("lxtwo-")


async def test_group_list_matches_the_capture(client):
    groups = await client.group_list()
    assert len(groups) == 65
    assert sorted(g.number for g in groups) == list(range(1, 66))
    # 58 groups on palette colour 1 and 7 on colour 3, which is what theme 0 paints.
    by_colr: dict[int, int] = {}
    for group in groups:
        by_colr[group.colr] = by_colr.get(group.colr, 0) + 1
    assert by_colr == {1: 58, 3: 7}


async def test_theme_list_and_restriction(client):
    themes = await client.theme_list()
    assert [t.index for t in themes] == [0, 1, 2]
    assert all(not t.on for t in themes)
    assert await client.themes_restricted() is False


async def test_theme_groups_carry_the_colour(client):
    """The measurement the whole design rests on.

    Theme 0's per-group colour map is identical to the group list's, because the group list is
    reporting what theme 0 painted.
    """
    groups = {g.number: g.colr for g in await client.group_list()}
    theme = {tg.number: tg.colour for tg in await client.theme_groups(0)}
    assert theme == groups


async def test_alarm_themes_paint_red(client):
    """Theme 1 covers everything, theme 2 covers two groups, both on one palette slot."""
    house = await client.theme_groups(1)
    entry = await client.theme_groups(2)
    assert len(house) == 65
    assert {tg.colour for tg in house} == {5}
    assert sorted(tg.number for tg in entry) == [21, 61]
    assert {tg.colour for tg in entry} == {5}
    red = next(c for c in await client.colour_list() if c.index == 5)
    assert red.hs == (0.0, 100.0)


async def test_colour_list_size_and_gaps(client):
    colours = await client.colour_list()
    assert len(colours) == 78
    defined = {c.index for c in colours}
    # 1-13 plus a block at 185-250 with 236 missing. The block is a fossil: nothing references it.
    assert set(range(1, 14)) <= defined
    assert 236 not in defined
    assert 250 in defined


async def test_a_missing_method_raises_with_its_status(client, session):
    """`Status: 1` is how the candidate integration's colour endpoint was found not to exist."""
    session.unknown.add("ColorListGet")
    with pytest.raises(LuxorStatusError) as err:
        await client.colour_list()
    assert err.value.status == 1
    assert "Unknown method" in str(err.value)


# --- writes --------------------------------------------------------------------------------------


async def test_illuminate_group_builds_the_documented_body(client, session):
    await client.illuminate_group(7, 42)
    assert session.sent[-1].method == "IlluminateGroup"
    assert session.sent[-1].body == {"GroupNumber": 7, "Intensity": 42}


@pytest.mark.parametrize("intensity", [-1, 101, 255])
async def test_intensity_out_of_range_never_reaches_the_wire(client, session, intensity):
    with pytest.raises(IntensityRangeError):
        await client.illuminate_group(7, intensity)
    assert session.sent == []


async def test_extinguish_all_turns_everything_off_and_leaves_colour_alone(client, session):
    """Driven from the ON state, because from OFF it changes nothing and proves nothing.

    This is the same mistake the hardware test made first: run against already-off lights,
    `ExtinguishAll` "preserved" colour trivially and licensed nothing.
    """
    await client.illuminate_theme(0, True)
    assert all(g["Inten"] > 0 for g in session.groups.values())
    before = {n: g["Colr"] for n, g in session.groups.items()}

    await client.extinguish_all()

    assert all(g["Inten"] == 0 for g in session.groups.values())
    assert {n: g["Colr"] for n, g in session.groups.items()} == before


async def test_activating_a_theme_repaints_every_member_group(client, session):
    """Why colour must be written into the theme rather than onto the group."""
    for group in session.groups.values():
        group["Colr"] = 0
    await client.illuminate_theme(0, True)
    by_colr: dict[int, int] = {}
    for group in session.groups.values():
        by_colr[group["Colr"]] = by_colr.get(group["Colr"], 0) + 1
    assert by_colr == {1: 58, 3: 7}


async def test_palette_write_then_theme_write_survives_a_theme_activation(client, session):
    """The end-to-end shape of the design, at protocol level.

    Define the slot, point the theme at it, then activate the theme. The group ends up on the new
    colour *because* the theme says so, which is the property a group-level write cannot have.
    """
    slot = 101
    await client.set_palette_colour(slot, 200, 90)

    groups = await client.theme_groups(0)
    updated = [
        ThemeGroup(
            number=g.number, intensity=g.intensity, colour=slot if g.number == 23 else g.colour
        )
        for g in groups
    ]
    await client.set_theme_groups(0, updated)
    await client.illuminate_theme(0, True)

    assert session.groups[23]["Colr"] == slot
    colour = next(c for c in await client.colour_list() if c.index == slot)
    assert colour.hs == (200.0, 90.0)
    # And every other group is untouched.
    assert session.groups[24]["Colr"] == 1


async def test_theme_set_refuses_an_empty_membership(client, session):
    with pytest.raises(EmptyBodyError):
        await client.set_theme_groups(0, [])
    assert session.sent == []


@pytest.mark.parametrize(("hue", "sat"), [(-1, 50), (361, 50), (10, -1), (10, 101)])
async def test_colour_out_of_range_never_reaches_the_wire(client, session, hue, sat):
    with pytest.raises(ColourRangeError):
        await client.set_palette_colour(50, hue, sat)
    assert session.sent == []


@pytest.mark.parametrize("index", [0, 251, 65535])
async def test_a_non_palette_slot_is_refused(client, session, index):
    """0 is 'non-colour fixtures', 251+ are colour wheels, 65535 is DMX. None is writable."""
    with pytest.raises(ColourRangeError):
        await client.set_palette_colour(index, 10, 10)
    assert session.sent == []


# --- the one dangerous call ----------------------------------------------------------------------


async def test_group_list_edit_sends_the_name_it_was_given(client, session):
    name = session.groups[7]["Name"]
    await client.point_group_at_colour(7, name, 101)
    assert session.sent[-1].body == {"Name": name, "GroupNumber": 7, "Color": 101}
    assert session.groups[7]["Name"] == name, "the group was renamed"


async def test_an_empty_name_is_refused(client, session):
    with pytest.raises(GroupNameError):
        await client.point_group_at_colour(7, "", 101)
    assert session.sent == []


async def test_a_name_over_the_byte_cap_is_refused(client, session):
    """The cap is in BYTES, so a multi-byte character can be truncated mid-sequence."""
    at_cap = session.groups[7]["Name"]
    assert len(at_cap.encode()) == MAX_GROUP_NAME_BYTES
    await client.point_group_at_colour(7, at_cap, 101)  # exactly at the cap is fine

    over = at_cap + "x"
    with pytest.raises(GroupNameError):
        await client.point_group_at_colour(7, over, 101)

    # Nine characters of three-byte each is 27 bytes while len() says 9.
    multibyte = "中" * 9
    assert len(multibyte) < MAX_GROUP_NAME_BYTES < len(multibyte.encode())
    with pytest.raises(GroupNameError):
        await client.point_group_at_colour(7, multibyte, 101)


async def test_a_colliding_name_is_rejected_by_the_controller(client, session):
    """Names are a unique key. The client cannot see the collision; the controller answers 202."""
    other = session.groups[8]["Name"]
    with pytest.raises(LuxorStatusError) as err:
        await client.point_group_at_colour(7, other, 101)
    assert err.value.status == 202


async def test_group_list_edit_renames_when_given_the_wrong_name(client, session):
    """The hazard, demonstrated rather than asserted away.

    There is no `OldName` field. Passing a name the group does not have is not a lookup failure --
    it is a rename. Any caller must read the name inside the same operation.
    """
    await client.point_group_at_colour(7, "Something Else", 101)
    assert session.groups[7]["Name"] == "Something Else"


# --- transport -----------------------------------------------------------------------------------


async def test_only_one_request_is_in_flight(session):
    """The controller refuses a second concurrent request, so the client must serialise."""
    concurrent = 0
    peak = 0
    original = session.post

    def counting_post(url, **kwargs):
        nonlocal concurrent, peak
        concurrent += 1
        peak = max(peak, concurrent)
        try:
            return original(url, **kwargs)
        finally:
            concurrent -= 1

    session.post = counting_post
    client = LuxorClient("192.0.2.10", session, min_gap=0.0)
    await asyncio.gather(*(client.group_list() for _ in range(20)))
    assert peak == 1
    assert len(session.sent) == 20


async def test_requests_are_paced(session):
    client = LuxorClient("192.0.2.10", session, min_gap=0.05)
    started = asyncio.get_running_loop().time()
    for _ in range(4):
        await client.group_list()
    # Three gaps between four requests.
    assert asyncio.get_running_loop().time() - started >= 0.15 - 0.01


async def test_a_timeout_becomes_a_connection_error(session):
    session.raise_on["GroupListGet"] = TimeoutError()
    client = LuxorClient("192.0.2.10", session, min_gap=0.0)
    with pytest.raises(LuxorConnectionError):
        await client.group_list()


async def test_a_client_error_becomes_a_connection_error(session):
    session.raise_on["GroupListGet"] = aiohttp.ClientError("refused")
    client = LuxorClient("192.0.2.10", session, min_gap=0.0)
    with pytest.raises(LuxorConnectionError):
        await client.group_list()


async def test_a_failure_is_never_degraded_into_a_stale_success(client, session):
    """The reference Homebridge plugin returns cached data on error, which makes a failed write
    indistinguishable from a successful one. This client raises."""
    session.fail_with["GroupListGet"] = 102
    with pytest.raises(LuxorStatusError) as err:
        await client.group_list()
    assert err.value.status == 102


@pytest.mark.parametrize("host", ["192.0.2.10", "http://192.0.2.10", "http://192.0.2.10/"])
async def test_the_host_is_normalised(session, host):
    client = LuxorClient(host, session, min_gap=0.0)
    assert client.host == "192.0.2.10"
    await client.group_list()
    assert session.sent[-1].method == "GroupListGet"

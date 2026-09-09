"""Setting a group's colour so that it survives the controller's own schedule.

The order of the four writes is not a preference. Each step exists because leaving it out produces a
specific, observed failure:

===================================  ==========================================================
Step                                 What its absence causes
===================================  ==========================================================
1. read the group list, fresh        `GroupListEdit` renames the group, because the name it
                                     carries came from somewhere stale
2. `ColorListSet` the slot           the group visibly lights in whatever the slot used to mean
3. `ThemeSet` the theme's entry      the colour is correct all evening and reverts at sunset
4. `GroupListEdit` the group         nothing changes until the theme next runs
===================================  ==========================================================

Step 3 is the durable one and step 4 is the visible one; neither alone is sufficient. Reactivating
the theme would also apply the colour, and is rejected: on this controller theme 0 stores
``Intensity: 100`` for all 65 groups, so it would overwrite every individual brightness.

Once both the theme and the group point at the same slot, the nightly re-apply writes the value
that is already there. The controller's reclaim becomes a no-op instead of a fight, and there is no
repair loop for a poll to notice.
"""

from __future__ import annotations

from dataclasses import dataclass

from .client import LuxorClient
from .errors import GroupNameError, LuxorError
from .model import Group, ThemeGroup
from .slots import SlotTable


class ColourWriteError(LuxorError):
    """A colour write could not be completed safely, or did not land."""


@dataclass(frozen=True, slots=True)
class ColourWrite:
    """What a completed write actually did, for logging and for tests."""

    group: int
    slot: int
    hue: int
    saturation: int
    theme_index: int
    theme_updated: bool
    group_repointed: bool


async def set_group_colour(
    client: LuxorClient,
    table: SlotTable,
    *,
    group_number: int,
    hue: int,
    saturation: int,
    theme_index: int,
    now: str,
) -> ColourWrite:
    """Give one group a colour that survives the next theme activation."""
    groups = await client.group_list()
    by_number = {group.number: group for group in groups}
    group = by_number.get(group_number)
    if group is None:
        raise ColourWriteError(f"group {group_number} is not on the controller")

    themes = {theme_index: await client.theme_groups(theme_index)}
    if not any(entry.number == group_number for entry in themes[theme_index]):
        raise ColourWriteError(
            f"group {group_number} is not a member of theme {theme_index}, so a colour written "
            "there would never be applied. Choose a theme that contains this group."
        )

    colours = await client.colour_list()
    claim = table.claim(group, colours=colours, themes=themes, now=now)
    slot = claim.slot

    # 1. Define what the slot means, before anything points at it.
    await client.set_palette_colour(slot, hue, saturation)

    # 2. The durable write. Read-modify-write of the whole theme: `Groups` is the membership, not a
    #    patch, so a partial list would strip the theme rather than leave it alone.
    entries = themes[theme_index]
    updated = [
        ThemeGroup(number=e.number, intensity=e.intensity, colour=slot)
        if e.number == group_number
        else e
        for e in entries
    ]
    theme_updated = updated != entries
    if theme_updated:
        await client.set_theme_groups(theme_index, updated)

    # 3. The visible write, and the only dangerous call in the integration.
    group_repointed = False
    if group.colr != slot:
        _guard_name(group, groups)
        await client.point_group_at_colour(group_number, group.name, slot)
        group_repointed = True

    # 4. Verify against the controller, not against what we intended.
    if group_repointed:
        await _verify(client, group, slot)

    return ColourWrite(
        group=group_number,
        slot=slot,
        hue=hue,
        saturation=saturation,
        theme_index=theme_index,
        theme_updated=theme_updated,
        group_repointed=group_repointed,
    )


def _guard_name(group: Group, groups: list[Group]) -> None:
    """Refuse a `GroupListEdit` whose name would collide.

    Names are a unique key on the controller and a collision returns 202. Checking here rather
    than letting the controller answer keeps a failed colour change from looking like a transport
    problem, and it needs the whole group list, which the client does not have.
    """
    clashes = [
        other for other in groups if other.name == group.name and other.number != group.number
    ]
    if clashes:
        raise GroupNameError(
            f"group {group.number} is named {group.name!r}, which group {clashes[0].number} also "
            "uses. GroupListEdit would be rejected with 202. Rename one of them on the controller."
        )


async def _verify(client: LuxorClient, group: Group, slot: int) -> None:
    """Re-read and assert both the name and the colour.

    The name is checked as well as the colour because `GroupListEdit` carries it, so a wrong name
    is a rename rather than an error. A write that renamed a group and set the right colour would
    otherwise pass.
    """
    after = {g.number: g for g in await client.group_list()}
    now = after.get(group.number)
    if now is None:
        raise ColourWriteError(f"group {group.number} vanished during the write")
    if now.name != group.name:
        raise ColourWriteError(
            f"group {group.number} was renamed from {group.name!r} to {now.name!r} by the write"
        )
    if now.colr != slot:
        raise ColourWriteError(
            f"group {group.number} reads colour {now.colr} after being pointed at slot {slot}"
        )


def resolve_hs(group: Group, colours: dict[int, tuple[float, float]]) -> tuple[float, float] | None:
    """The group's colour as Home Assistant's `hs_color`, or None if it has none.

    Reports what the controller has, not what was last asked for. When a theme repaints a group the
    entity's colour changes to match, which is what makes the no-op visible: if the design is
    working, the nightly theme changes nothing.
    """
    if not group.has_static_colour:
        return None
    return colours.get(group.colr)

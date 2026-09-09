"""Slot ownership, and the guard that must be able to refuse."""

from __future__ import annotations

import pytest
from luxor import Colour, Group, ThemeGroup
from luxor.slots import (
    SlotAllocationError,
    SlotClaim,
    SlotTable,
    available_slots,
    revalidate,
    theme_reserved_slots,
)

NOW = "2026-09-09T17:00:00-04:00"


def _group(number: int, name: str = "Group 01", colr: int = 1) -> Group:
    return Group(number=number, name=name, intensity=0, colr=colr)


@pytest.fixture
def colours(load_fixture) -> list[Colour]:
    return [Colour.from_json(raw) for raw in load_fixture("color_list_get")["ColorList"]]


@pytest.fixture
def themes(load_fixture) -> dict[int, list[ThemeGroup]]:
    return {
        i: [ThemeGroup.from_json(raw) for raw in load_fixture(f"theme_get_{i}")["Groups"]]
        for i in (0, 1, 2)
    }


# --- what is reserved, and what is merely defined -------------------------------------------------


def test_only_three_slots_are_referenced_by_any_theme(themes):
    assert theme_reserved_slots(themes) == {1, 3, 5}


def test_available_slots_prefer_never_defined_ones(colours, themes):
    free = available_slots(colours, themes)
    defined = {c.index for c in colours}
    # 14-184 and 236 have never been defined; those come first.
    assert free[0] == 14
    assert all(slot not in defined for slot in free[:172])


def test_the_fossil_block_is_offered_last_not_never(colours, themes):
    """185-250 are defined and referenced by nothing.

    Reusing one is safe but indistinguishable from stepping on another tool's allocation, so they
    are available and ranked behind everything else rather than excluded.
    """
    free = available_slots(colours, themes)
    assert 250 in free
    assert free.index(250) > free.index(184)


def test_theme_referenced_slots_are_never_offered(colours, themes):
    free = available_slots(colours, themes)
    for reserved in (1, 3, 5):
        assert reserved not in free


def test_a_slot_a_theme_uses_but_the_colour_list_omits_is_still_reserved(colours):
    """The case a naive 'not in the colour list means free' rule gets wrong."""
    themes = {0: [ThemeGroup(number=1, intensity=100, colour=200)]}
    assert 200 not in available_slots([c for c in colours if c.index != 200], themes)


# --- claiming -------------------------------------------------------------------------------------


def test_a_claim_records_what_was_true_at_the_time(colours, themes):
    table = SlotTable()
    claim = table.claim(_group(23, "Group 23", colr=1), colours=colours, themes=themes, now=NOW)
    assert claim.group == 23
    assert claim.name_at_claim == "Group 23"
    assert claim.colr_at_claim == 1
    assert claim.claimed_at == NOW
    assert table.slot_for(23) == claim.slot


def test_claiming_twice_returns_the_same_slot(colours, themes):
    """Idempotent. Re-claiming would be deriving, one call later."""
    table = SlotTable()
    first = table.claim(_group(23), colours=colours, themes=themes, now=NOW)
    second = table.claim(_group(23), colours=colours, themes=themes, now="later")
    assert first == second
    assert len(table) == 1


def test_claims_do_not_collide(colours, themes):
    table = SlotTable()
    for number in range(1, 66):
        table.claim(_group(number, f"Group {number:02d}"), colours=colours, themes=themes, now=NOW)
    assert len(table) == 65
    assert len(table.slots) == 65, "two groups were given the same slot"
    assert not (table.slots & theme_reserved_slots(themes))


def test_exhaustion_raises_rather_than_reusing(colours):
    """With almost everything reserved there is no slot, and that must be an error."""
    themes = {0: [ThemeGroup(number=1, intensity=100, colour=slot) for slot in range(1, 251)]}
    table = SlotTable()
    with pytest.raises(SlotAllocationError):
        table.claim(_group(1), colours=colours, themes=themes, now=NOW)


def test_round_trips_through_json(colours, themes):
    table = SlotTable()
    table.claim(_group(23, "Group 23"), colours=colours, themes=themes, now=NOW)
    table.claim(_group(24, "Group 24"), colours=colours, themes=themes, now=NOW)
    restored = SlotTable.from_json(table.to_json())
    assert restored.to_json() == table.to_json()
    assert restored.slot_for(23) == table.slot_for(23)


def test_an_absent_table_loads_as_empty():
    assert len(SlotTable.from_json(None)) == 0


# --- revalidation: the guard must be able to refuse -----------------------------------------------


def test_a_healthy_table_revalidates_clean(colours, themes):
    table = SlotTable()
    groups = [_group(n, f"Group {n:02d}") for n in range(1, 66)]
    for group in groups:
        table.claim(group, colours=colours, themes=themes, now=NOW)
    assert revalidate(table, groups, themes) == []


def test_a_renamed_group_is_refused(colours, themes):
    """The renumbering case and the rename case are the same symptom.

    Either way the slot was claimed for a different group than the one holding this number now,
    which is exactly what the fossil block on the reference controller records.
    """
    table = SlotTable()
    table.claim(_group(23, "Group 23"), colours=colours, themes=themes, now=NOW)
    problems = revalidate(table, [_group(23, "Something Else")], themes)
    assert len(problems) == 1
    assert problems[0].group == 23
    assert "Something Else" in problems[0].reason


def test_a_vanished_group_is_refused(colours, themes):
    table = SlotTable()
    table.claim(_group(23, "Group 23"), colours=colours, themes=themes, now=NOW)
    problems = revalidate(table, [], themes)
    assert [p.group for p in problems] == [23]
    assert "no longer exists" in problems[0].reason


def test_a_slot_a_theme_has_since_claimed_is_refused(colours, themes):
    table = SlotTable()
    group = _group(23, "Group 23")
    claim = table.claim(group, colours=colours, themes=themes, now=NOW)
    # Somebody edited the theme on the faceplate and pointed a group at our slot.
    themes[0] = [*themes[0], ThemeGroup(number=1, intensity=100, colour=claim.slot)]
    problems = revalidate(table, [group], themes)
    assert any("referenced by a theme" in p.reason for p in problems)


def test_two_groups_claiming_one_slot_is_refused(colours, themes):
    """Only reachable through a corrupted or hand-edited table, which is why it is checked."""
    table = SlotTable(
        [
            SlotClaim(
                group=23, slot=101, name_at_claim="Group 23", colr_at_claim=1, claimed_at=NOW
            ),
            SlotClaim(
                group=24, slot=101, name_at_claim="Group 24", colr_at_claim=1, claimed_at=NOW
            ),
        ]
    )
    groups = [_group(23, "Group 23"), _group(24, "Group 24")]
    problems = revalidate(table, groups, themes)
    assert any("claimed by both" in p.reason for p in problems)


def test_revalidation_reports_every_problem_not_the_first(colours, themes):
    """The caller raises one repair issue, not 65, so it needs them all at once."""
    table = SlotTable(
        [
            SlotClaim(
                group=n,
                slot=100 + n,
                name_at_claim=f"Group {n:02d}",
                colr_at_claim=1,
                claimed_at=NOW,
            )
            for n in (23, 24, 25)
        ]
    )
    problems = revalidate(table, [_group(23, "Renamed"), _group(24, "Renamed too")], themes)
    assert {p.group for p in problems} == {23, 24, 25}

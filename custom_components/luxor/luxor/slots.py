"""Palette-slot ownership: which group owns which of the controller's 250 colour slots.

Giving a group its own colour means giving it a palette slot nothing else uses. The obvious scheme
is a function of the group number -- the Homebridge plugin uses `f(N) = 251 - N` -- and on this
hardware it is provably wrong.

The reference controller's defined slots are 1-13 plus 185-250 with **236 missing**. That set is
exactly `f(N)` over groups `{1..66} \\ {15}`, while the controller today has groups 1-65. So the
group numbering changed after that block was written, and every slot in it now belongs to a
different group than the one that claimed it. Nothing detected that, because under a positional
scheme ownership is *derived* rather than recorded, and a derived fact cannot disagree with itself.

So ownership is recorded. A claim carries what was true when it was made, and startup compares that
against what is true now. When they disagree the answer is to stop and report, never to re-derive:
silently re-assigning is precisely how the fossil block came to exist.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .const import PALETTE_MAX, PALETTE_MIN
from .errors import LuxorError
from .model import Colour, Group, ThemeGroup


class SlotAllocationError(LuxorError):
    """No slot could be claimed, or a claim would collide."""


@dataclass(frozen=True, slots=True)
class SlotClaim:
    """One group's ownership of one palette slot, and the evidence it rested on.

    `name_at_claim` and `colr_at_claim` are not decoration. They are what makes a stale claim
    detectable: a group that has been renamed or renumbered on the faceplate no longer matches the
    record, and that is the signal to stop writing rather than to overwrite a stranger's colour.
    """

    group: int
    slot: int
    name_at_claim: str
    colr_at_claim: int
    claimed_at: str

    def to_json(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "slot": self.slot,
            "name_at_claim": self.name_at_claim,
            "colr_at_claim": self.colr_at_claim,
            "claimed_at": self.claimed_at,
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> SlotClaim:
        return cls(
            group=int(raw["group"]),
            slot=int(raw["slot"]),
            name_at_claim=str(raw["name_at_claim"]),
            colr_at_claim=int(raw["colr_at_claim"]),
            claimed_at=str(raw["claimed_at"]),
        )


@dataclass(frozen=True, slots=True)
class SlotProblem:
    """A reason colour writing must stop for a group, in words a repair issue can use."""

    group: int
    reason: str


def theme_reserved_slots(themes: Mapping[int, Sequence[ThemeGroup]]) -> set[int]:
    """Every palette slot any theme points at.

    These are never available. Redefining one changes what a theme looks like, and on this system
    two of the three themes are alarm modes -- repainting those from red is a security regression
    wearing a lighting change's clothes.
    """
    return {entry.colour for groups in themes.values() for entry in groups}


def available_slots(
    colours: Iterable[Colour],
    themes: Mapping[int, Sequence[ThemeGroup]],
    claimed: Iterable[int] = (),
) -> list[int]:
    """Slots that are free to claim, best candidates first.

    "Defined" is not "in use" and "undefined" is not "free", so both directions are checked:

    * A slot can be **defined and referenced by nothing** -- the entire 185-250 block is. Reusing
      one is safe but indistinguishable from stepping on another tool's allocation, so those come
      last rather than never.
    * A slot can be **referenced by a theme without appearing in the colour list at all**. Those
      are excluded even though nothing in `ColorListGet` mentions them, which is the case a naive
      "not in the colour list means free" rule gets wrong.
    """
    defined = {colour.index for colour in colours}
    reserved = theme_reserved_slots(themes) | set(claimed)
    never_defined = [
        slot
        for slot in range(PALETTE_MIN, PALETTE_MAX + 1)
        if slot not in defined and slot not in reserved
    ]
    fossils = [
        slot
        for slot in range(PALETTE_MIN, PALETTE_MAX + 1)
        if slot in defined and slot not in reserved
    ]
    return never_defined + fossils


class SlotTable:
    """The recorded ownership, and the only thing that may hand out a slot."""

    def __init__(self, claims: Iterable[SlotClaim] = ()) -> None:
        self._claims: dict[int, SlotClaim] = {claim.group: claim for claim in claims}

    # --- persistence ---------------------------------------------------------------------------

    @classmethod
    def from_json(cls, raw: Iterable[Mapping[str, Any]] | None) -> SlotTable:
        return cls(SlotClaim.from_json(entry) for entry in (raw or ()))

    def to_json(self) -> list[dict[str, Any]]:
        return [claim.to_json() for claim in sorted(self._claims.values(), key=lambda c: c.group)]

    # --- reads ---------------------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._claims)

    def __contains__(self, group: int) -> bool:
        return group in self._claims

    def slot_for(self, group: int) -> int | None:
        claim = self._claims.get(group)
        return claim.slot if claim else None

    def claim_for(self, group: int) -> SlotClaim | None:
        return self._claims.get(group)

    @property
    def slots(self) -> set[int]:
        return {claim.slot for claim in self._claims.values()}

    # --- writes --------------------------------------------------------------------------------

    def claim(
        self,
        group: Group,
        *,
        colours: Iterable[Colour],
        themes: Mapping[int, Sequence[ThemeGroup]],
        now: str,
    ) -> SlotClaim:
        """Claim a slot for `group`, recording what was true at the time.

        Idempotent: a group that already holds a claim keeps it. Re-claiming would be the same
        mistake as deriving, one call later.
        """
        existing = self._claims.get(group.number)
        if existing is not None:
            return existing

        candidates = available_slots(colours, themes, claimed=self.slots)
        if not candidates:
            raise SlotAllocationError(
                f"no palette slot is free for group {group.number}. "
                f"{len(self._claims)} slots are already claimed and the rest are referenced by a "
                "theme."
            )
        claim = SlotClaim(
            group=group.number,
            slot=candidates[0],
            name_at_claim=group.name,
            colr_at_claim=group.colr,
            claimed_at=now,
        )
        self._claims[group.number] = claim
        return claim

    def release(self, group: int) -> None:
        self._claims.pop(group, None)


def revalidate(
    table: SlotTable,
    groups: Iterable[Group],
    themes: Mapping[int, Sequence[ThemeGroup]],
) -> list[SlotProblem]:
    """Check every recorded claim against the controller as it is now.

    Returns the problems rather than raising, because the caller needs all of them at once to
    raise one repair issue rather than 65.

    A clean result is the *only* licence to write colour. This is deliberately capable of
    refusing: a guard that has never rejected anything cannot be told from one that cannot.
    """
    problems: list[SlotProblem] = []
    by_number = {group.number: group for group in groups}
    reserved = theme_reserved_slots(themes)
    seen: dict[int, int] = {}

    for claim in sorted(table.to_json(), key=lambda c: c["group"]):
        group_number = claim["group"]
        slot = claim["slot"]
        group = by_number.get(group_number)

        if group is None:
            problems.append(
                SlotProblem(
                    group_number, f"group {group_number} no longer exists on the controller"
                )
            )
            continue
        if group.name != claim["name_at_claim"]:
            # The renumbering case, and the rename case, are the same symptom. Either way the slot
            # was claimed for a different group than the one holding this number now.
            problems.append(
                SlotProblem(
                    group_number,
                    f"group {group_number} is now named {group.name!r} but slot {slot} was "
                    f"claimed for {claim['name_at_claim']!r}. The numbering or naming has "
                    "changed, so this slot may belong to a different group.",
                )
            )
        if slot in reserved:
            problems.append(
                SlotProblem(
                    group_number,
                    f"slot {slot} is now referenced by a theme. Writing it would change what that "
                    "theme looks like.",
                )
            )
        if slot in seen:
            problems.append(
                SlotProblem(
                    group_number,
                    f"slot {slot} is claimed by both group {seen[slot]} and group {group_number}",
                )
            )
        seen[slot] = group_number

    return problems

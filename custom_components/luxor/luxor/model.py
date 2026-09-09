"""Typed views over the controller's JSON.

Two things here are easy to get wrong and both have bitten a shipped integration:

* `Group.colr` is **not** a setting the group owns. It is the colour the last theme painted onto
  that group. Proved on 2026-09-09: theme 0's per-group colour map is byte-identical to the group
  list's, and activating theme 0 restored all 65 groups exactly after they had been wiped.
* The group list and the theme record use **different field names for the same things**:
  `{Name, Grp, Inten, Colr}` versus `{GroupNumber, Intensity, Color}`. Reading one shape and
  writing the other is how a colour write silently goes nowhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .const import (
    COLOUR_NONE,
    COLOUR_WHEEL_MAX,
    COLOUR_WHEEL_MIN,
    DMX_SENTINEL,
    HUE_MAX,
    is_static_colour,
)


def normalise_hue(hue: int) -> int:
    """Fold the controller's inclusive 360 onto Home Assistant's half-open [0, 360).

    The device's documented range is 0-359, the palette reports up to 360, and the reference
    Homebridge plugin writes 360 as its default. Without this, an entity written at hue 0 reads
    back at 360 and flaps forever.
    """
    return 0 if hue >= HUE_MAX else hue


@dataclass(frozen=True, slots=True)
class Colour:
    """One palette slot: an index, a hue and a saturation."""

    index: int
    hue: int
    saturation: int

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> Colour:
        return cls(
            index=int(raw["C"]),
            hue=normalise_hue(int(raw["Hue"])),
            saturation=int(raw["Sat"]),
        )

    @property
    def hs(self) -> tuple[float, float]:
        """As Home Assistant's `hs_color`. No scaling: both use 0-360 and 0-100 already."""
        return (float(self.hue), float(self.saturation))


@dataclass(frozen=True, slots=True)
class Group:
    """A light group as the controller currently has it.

    `colr` is live state, not configuration -- see the module docstring.
    """

    number: int
    name: str
    intensity: int
    colr: int

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> Group:
        return cls(
            number=int(raw["Grp"]),
            name=str(raw["Name"]),
            intensity=int(raw["Inten"]),
            colr=int(raw.get("Colr", COLOUR_NONE)),
        )

    @property
    def is_on(self) -> bool:
        return self.intensity > 0

    @property
    def has_static_colour(self) -> bool:
        """Whether `colr` resolves to a single hue and saturation.

        False for 0 (configured as non-colour fixtures), for 251-260 (animated colour wheels) and
        for 65535 (under DMX control). All three exist on this hardware family and none of them
        can be reported as an `hs_color`.
        """
        return is_static_colour(self.colr)

    @property
    def is_colour_wheel(self) -> bool:
        return COLOUR_WHEEL_MIN <= self.colr <= COLOUR_WHEEL_MAX

    @property
    def is_dmx(self) -> bool:
        return self.colr == DMX_SENTINEL


@dataclass(frozen=True, slots=True)
class Theme:
    """A theme as it appears in the theme list. Membership is not included here."""

    index: int
    name: str
    on: bool

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> Theme:
        return cls(
            index=int(raw["ThemeIndex"]),
            name=str(raw["Name"]),
            on=int(raw["OnOff"]) == 1,
        )


@dataclass(frozen=True, slots=True)
class ThemeGroup:
    """One group's entry inside a theme: the intensity and colour the theme paints.

    This is where colour actually lives. Note the long field names, which differ from the group
    list's short ones.
    """

    number: int
    intensity: int
    colour: int

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> ThemeGroup:
        return cls(
            number=int(raw["GroupNumber"]),
            intensity=int(raw["Intensity"]),
            colour=int(raw["Color"]),
        )

    def to_json(self) -> dict[str, int]:
        return {
            "GroupNumber": self.number,
            "Intensity": self.intensity,
            "Color": self.colour,
        }

"""Home Assistant side constants.

The protocol constants live in `luxor/const.py` and are deliberately not re-exported here: this
module is about how the integration presents itself to Home Assistant, not about the wire.
"""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "luxor"

#: Version 1 adopted the previous integration's entry untouched, which is what made the swap
#: invisible. Version 2 corrects the identity schemes it inherited -- see `migrate.py`. Adoption
#: had to ship and be proven on its own first, so that a missing entity would have one candidate
#: cause rather than two.
CONFIG_VERSION: Final = 2

CONF_HOST: Final = "host"
CONF_GROUP_INTERVAL: Final = "group_interval"
CONF_THEME_INTERVAL: Final = "theme_interval"

#: Today's values, carried over so the swap changes nothing observable about polling.
DEFAULT_GROUP_INTERVAL: Final = 60
DEFAULT_THEME_INTERVAL: Final = 600

#: Batches the refresh that follows a command, so a 65-light service call produces one read rather
#: than 65.
REQUEST_REFRESH_DELAY: Final = 0.3

#: Which theme colour writes target. Every group belongs to at least two themes on a typical
#: system, so this cannot be inferred -- see the options flow.
CONF_COLOUR_THEME: Final = "colour_theme"
DEFAULT_COLOUR_THEME: Final = 0

MANUFACTURER: Final = "FXLuminaire"

#: The namespace the previous integration used for per-group devices. Off-spec twice over: it is
#: not the integration domain, and its value is an `int` where Home Assistant's type is `str`.
#: Adopting it is what preserved 65 devices through the swap; `migrate.py` converts it, and this
#: constant survives only so the migration can recognise what it is converting FROM.
LEGACY_DEVICE_NAMESPACE: Final = "luxor_light"


#: What identity looks like from version 2 onward. Controller-scoped, so a second Luxor on the
#: same Home Assistant cannot collide with the first -- which `LUXOR_LIGHT_{n}` would have done,
#: silently, since group numbers start at 1 on every controller.
def light_unique_id(controller: str, group: int) -> str:
    return f"{controller}_group_{group}"


def scene_unique_id(controller: str, theme_index: int) -> str:
    return f"{controller}_theme_{theme_index}"


def light_device_identifier(controller: str, group: int) -> tuple[str, str]:
    return (DOMAIN, f"{controller}:group:{group}")


PLATFORMS: Final = ["light", "scene", "button"]

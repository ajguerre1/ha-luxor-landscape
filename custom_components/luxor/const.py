"""Home Assistant side constants.

The protocol constants live in `luxor/const.py` and are deliberately not re-exported here: this
module is about how the integration presents itself to Home Assistant, not about the wire.
"""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "luxor"

#: Kept at 1 so `async_migrate_entry` never fires against the config entry the integration this
#: replaces created. The entry is adopted, not recreated -- that is the whole drop-in mechanism.
CONFIG_VERSION: Final = 1

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

#: Where the slot table is persisted. It lives in the entry rather than in a separate store so it
#: cannot drift away from the entry it describes.
CONF_SLOT_TABLE: Final = "slot_table"

MANUFACTURER: Final = "FXLuminaire"

#: Reproduced exactly, and both parts are off-spec. The namespace is not the integration domain and
#: the value is an int where Home Assistant's type is str. Adopting them is what preserves 65
#: devices; they are corrected later in one guarded migration.
DEVICE_LIGHT_NAMESPACE: Final = "luxor_light"

PLATFORMS: Final = ["light", "scene", "button"]

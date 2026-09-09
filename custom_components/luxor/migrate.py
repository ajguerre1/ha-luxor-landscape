"""Version 1 to 2: correct the identity schemes inherited from the previous integration.

Version 1 reproduced three schemes exactly, flaws included, because that is what made the swap
invisible: Home Assistant keys entities on `(domain, platform, unique_id)` and devices on their
identifiers, so reproducing them meant nothing moved. Three of them are wrong in ways worth fixing
now that adoption is proven.

* device `("luxor_light", 23)` becomes `("luxor", "<controller>:group:23")`. The old namespace is
  not the integration domain, and its value is an `int` where Home Assistant's type is `str`.
* light `LUXOR_LIGHT_23` becomes `<controller>_group_23`. The old one is not controller-scoped, so
  a second Luxor collides silently: group numbers start at 1 on every controller.
* scene `Evening Wash0` becomes `<controller>_theme_0`. The old one derives from the theme's
  **name**, so renaming a theme on the faceplate orphans the entity.

**This updates registry records in place; it does not recreate them.**
`async_update_device` and `async_update_entity` preserve the device_id and the entity_id, which is
what keeps areas, the `light.landscape_lights` group membership, and every dashboard reference
intact. Emitting a new scheme *without* this migration is what would orphan them.

**It runs entirely from the local registries.** No network. A migration that has to reach the
controller fails when the controller is briefly unreachable at boot, which this one has been.

**It is one-way.** After this runs, rolling back to the previous integration would orphan all 68
entities, because their unique_ids no longer match what that integration emits. Version 1 kept that
rollback cheap on purpose; version 2 spends it.
"""

from __future__ import annotations

import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    LEGACY_DEVICE_NAMESPACE,
    light_device_identifier,
    light_unique_id,
    scene_unique_id,
)

_LOGGER = logging.getLogger(__name__)

LEGACY_LIGHT_UNIQUE_ID = re.compile(r"^LUXOR_LIGHT_(\d+)$")
#: `"{name}{index}"`, which is only decodable when the trailing digit run is a SINGLE character.
#:
#: Any longer run can be split more than one way -- `"Zone 12"` is theme `"Zone 1"` at index 2 just
#: as readily as theme `"Zone "` at index 12 -- and nothing in the string says which. An earlier
#: version of this rule asked whether the name ended in a digit, which passes `"Zone 12"` and
#: rewrites it on a guess; CI caught that. Theme indices reach 25, so two-digit indices are real
#: and are simply not recoverable from the unique_id alone.
LEGACY_SCENE_UNIQUE_ID = re.compile(r"^(?P<name>.*[^\d])(?P<index>\d)$")


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Bring a version-1 entry up to version 2."""
    if entry.version >= 2:
        return True

    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    entry_devices = dr.async_entries_for_config_entry(devices, entry.entry_id)

    controller = next(
        (i[1] for d in entry_devices for i in d.identifiers if i[0] == DOMAIN),
        None,
    )
    if controller is None:
        # Nothing was ever created under this entry, so there is nothing to convert. Bumping the
        # version rather than failing: a fresh entry is already in the version-2 world.
        _LOGGER.debug("No controller device for %s; nothing to migrate", entry.entry_id)
        hass.config_entries.async_update_entry(entry, version=2)
        return True

    moved_devices = _migrate_devices(devices, entry_devices, controller)
    moved_lights, moved_scenes, skipped = _migrate_entities(entities, entry, controller)

    _LOGGER.info(
        "Migrated luxor entry to version 2: %d device identifier(s), %d light unique_id(s), "
        "%d scene unique_id(s)%s",
        moved_devices,
        moved_lights,
        moved_scenes,
        f"; {len(skipped)} scene(s) left alone: {skipped}" if skipped else "",
    )
    hass.config_entries.async_update_entry(entry, version=2)
    return True


def _migrate_devices(
    registry: dr.DeviceRegistry,
    entry_devices: list[dr.DeviceEntry],
    controller: str,
) -> int:
    moved = 0
    for device in entry_devices:
        legacy = {i for i in device.identifiers if i[0] == LEGACY_DEVICE_NAMESPACE}
        if not legacy:
            continue
        replacements = {light_device_identifier(controller, int(i[1])) for i in legacy}
        # Keep any identifier that is not ours to touch. A device carrying an identifier from
        # another integration is not this migration's business.
        new = (device.identifiers - legacy) | replacements
        registry.async_update_device(device.id, new_identifiers=new)
        moved += 1
    return moved


def _migrate_entities(
    registry: er.EntityRegistry,
    entry: ConfigEntry,
    controller: str,
) -> tuple[int, int, list[str]]:
    lights = scenes = 0
    skipped: list[str] = []

    for record in er.async_entries_for_config_entry(registry, entry.entry_id):
        if record.domain == "light":
            match = LEGACY_LIGHT_UNIQUE_ID.match(record.unique_id)
            if match:
                registry.async_update_entity(
                    record.entity_id,
                    new_unique_id=light_unique_id(controller, int(match.group(1))),
                )
                lights += 1
            continue

        if record.domain != "scene" or record.unique_id.startswith(f"{controller}_theme_"):
            continue

        match = LEGACY_SCENE_UNIQUE_ID.match(record.unique_id)
        if not match:
            # Ambiguous, or not the shape we expect. Left exactly as it is: a scene with an old
            # unique_id keeps working, whereas a wrong guess renames the entity.
            skipped.append(record.entity_id)
            continue

        registry.async_update_entity(
            record.entity_id,
            new_unique_id=scene_unique_id(controller, int(match.group("index"))),
        )
        scenes += 1

    return lights, scenes, skipped

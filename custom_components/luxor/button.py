"""All off.

There is deliberately no all-on. `IlluminateAll` is the method that sets every group to `Colr 0`,
destroying the colour configuration across the whole system -- measured in isolation on 2026-09-09
-- and the manual states the physical control is off-only. The protocol client denies it outright,
so this platform could not offer one even if a future edit here wanted to.

`ExtinguishAll` was cleared by measurement rather than by reading: run from the ON state, with a
theme-off from the same on state as a control, it left every group's colour untouched.
"""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LuxorConfigEntry
from .const import DOMAIN, MANUFACTURER
from .luxor import LuxorError

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LuxorAllOffButton(entry.runtime_data)])


class LuxorAllOffButton(ButtonEntity):
    """Turn every group off in one request."""

    _attr_has_entity_name = True
    _attr_translation_key = "all_off"
    _attr_should_poll = False

    def __init__(self, data) -> None:
        self._data = data
        self._attr_unique_id = f"{data.controller}_all_off"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._data.controller)},
            manufacturer=MANUFACTURER,
            name=self._data.controller,
        )

    async def async_press(self) -> None:
        try:
            await self._data.client.extinguish_all()
        except LuxorError as err:
            raise HomeAssistantError(f"could not turn the landscape lights off: {err}") from err
        await self._data.groups.async_request_refresh()
        await self._data.themes.async_request_refresh()

"""One scene entity per Luxor theme."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.scene import Scene
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LuxorConfigEntry
from .const import DOMAIN, MANUFACTURER
from .luxor import LuxorError

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

#: The controller ignores an activation for a theme it already considers on, so a re-trigger does
#: nothing -- which matters because the alarm themes are re-triggered rather than toggled. Turning
#: it off first makes the activation land. The pause is what the reference Homebridge plugin uses.
REACTIVATE_PAUSE = 0.1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    data = entry.runtime_data
    known: dict[int, LuxorScene] = {}

    @callback
    def _sync() -> None:
        new = [
            known.setdefault(index, LuxorScene(data, index, theme.name))
            for index, theme in data.themes.data.items()
            if index not in known
        ]
        if new:
            async_add_entities(new)

    _sync()
    entry.async_on_unload(data.themes.async_add_listener(_sync))


class LuxorScene(Scene):
    """A Luxor theme."""

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self, data, theme_index: int, name: str) -> None:
        self._data = data
        self._theme_index = theme_index
        self._attr_name = name
        # Reproduced exactly, including its flaws: it is ambiguous (theme "X" at index 12 and theme
        # "X1" at index 2 both give "X12") and it orphans the entity if a theme is renamed on the
        # faceplate. Adopting it is what preserves the three existing scene entities; it is
        # corrected later in one guarded migration.
        self._attr_unique_id = f"{name}{theme_index}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._data.controller)},
            manufacturer=MANUFACTURER,
            name=self._data.controller,
        )

    @property
    def available(self) -> bool:
        return self._data.themes.last_update_success

    async def async_activate(self, **kwargs: Any) -> None:
        try:
            theme = self._data.themes.data.get(self._theme_index)
            if theme is not None and theme.on:
                await self._data.client.illuminate_theme(self._theme_index, False)
                await asyncio.sleep(REACTIVATE_PAUSE)
            await self._data.client.illuminate_theme(self._theme_index, True)
        except LuxorError as err:
            raise HomeAssistantError(f"could not activate {self._attr_name}: {err}") from err
        # A theme activation repaints every member group's colour, so the groups need re-reading
        # too, not just the themes.
        await self._data.themes.async_request_refresh()
        await self._data.groups.async_request_refresh()

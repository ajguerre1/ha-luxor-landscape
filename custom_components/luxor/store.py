"""Where the palette-slot table lives.

**Not in the config entry's options**, and that was found by a test rather than by reasoning.

The obvious home for the slot table is `entry.options`, which is durable and travels with the
entry. But writing options calls `async_update_entry`, which fires the entry's update listener,
which reloads the integration. So every single colour change would tear down 68 entities and
rebuild them -- and in the test that showed up as a reload happening outside the patched session,
reaching for a real socket.

`Store` is the right home anyway: the slot table is state this integration owns, not configuration
a user set. Options stay for the things a user chooses.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .luxor import SlotTable

STORAGE_VERSION = 1


def _key(entry_id: str) -> str:
    return f"{DOMAIN}.{entry_id}.slots"


class SlotStore:
    """Loads and saves one entry's slot table."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[list[dict]] = Store(hass, STORAGE_VERSION, _key(entry_id))

    async def async_load(self) -> SlotTable:
        return SlotTable.from_json(await self._store.async_load())

    async def async_save(self, table: SlotTable) -> None:
        await self._store.async_save(table.to_json())

    async def async_remove(self) -> None:
        await self._store.async_remove()

"""Everything one config entry owns at runtime."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN
from .coordinator import LuxorGroupCoordinator, LuxorThemeCoordinator
from .luxor import LuxorClient, SlotTable, revalidate
from .store import SlotStore

_LOGGER = logging.getLogger(__name__)

SLOT_ISSUE = "slot_table_stale"


@dataclass
class LuxorData:
    client: LuxorClient
    controller: str
    groups: LuxorGroupCoordinator
    themes: LuxorThemeCoordinator
    slots: SlotTable
    store: SlotStore
    #: Set by revalidation. While this is False every colour write is refused, because a stale slot
    #: claim means the slot may now belong to a different group.
    colour_writable: bool = field(default=True)

    def revalidate_slots(self, hass: HomeAssistant) -> None:
        """Check the recorded slot claims against the controller as it is now.

        Called at every startup, and capable of refusing. A guard that has never rejected anything
        cannot be told from one that cannot.
        """
        problems = revalidate(self.slots, self.groups.data.values(), self.themes.membership)
        self.colour_writable = not problems

        if not problems:
            ir.async_delete_issue(hass, DOMAIN, SLOT_ISSUE)
            return

        # One issue rather than 65, which is why revalidate returns every problem instead of
        # raising on the first.
        _LOGGER.warning(
            "Luxor colour writing is disabled: %d palette-slot claim(s) no longer match the "
            "controller. %s",
            len(problems),
            "; ".join(f"group {p.group}: {p.reason}" for p in problems[:5]),
        )
        ir.async_create_issue(
            hass,
            DOMAIN,
            SLOT_ISSUE,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=SLOT_ISSUE,
            translation_placeholders={
                "count": str(len(problems)),
                "detail": "; ".join(f"group {p.group}: {p.reason}" for p in problems[:5]),
            },
        )

    async def async_persist_slots(self) -> None:
        """Save the slot table.

        Through a Store, never through `entry.options`: an options write fires the update listener
        and reloads the integration, so a colour change would rebuild all 68 entities.
        """
        await self.store.async_save(self.slots)

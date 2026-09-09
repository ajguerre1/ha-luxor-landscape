"""Shared device wiring.

Every identifier here reproduces exactly what the integration this replaces emits, because Home
Assistant keys entities on `(domain, platform, unique_id)` and devices on their identifiers. Change
one and 68 entities are orphaned and recreated with a `_2` suffix.

Two of these are off-spec and are reproduced anyway. The light device namespace is `luxor_light`,
which is not the integration domain, and its second element is a bare `int` where Home Assistant's
type is `str`. Adopting them is what makes the swap invisible; they are corrected later in one
guarded migration, not silently at adoption time.
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER


def controller_device_info(controller: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, controller)},
        manufacturer=MANUFACTURER,
        name=controller,
    )


class LuxorEntity(CoordinatorEntity):
    """Base for anything that hangs off a coordinator and belongs to the controller."""

    _attr_has_entity_name = False

    def __init__(self, coordinator, controller: str) -> None:
        super().__init__(coordinator)
        self._controller = controller

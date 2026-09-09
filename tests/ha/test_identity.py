"""Identity, which is the whole drop-in mechanism.

Home Assistant keys entities on `(domain, platform, unique_id)` and devices on their identifiers.
Reproduce those and a swap is invisible; change one character and 68 entities are orphaned and
recreated with a `_2` suffix.

That is not merely untidy here. A `group` helper on the live system holds all 65 light entity ids
as **strings**, and nothing reconciles them: a member whose id moves drops out silently and the
group carries on with fewer lights. So these are the cheapest tests in the repository and the ones
most worth having.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.luxor.const import DOMAIN, light_device_identifier, light_unique_id

CONTROLLER = "lxtwo-000000000"


async def test_a_legacy_entry_is_adopted_and_then_migrated(hass: HomeAssistant, setup_entry):
    """A version-1 entry loads and comes out at version 2.

    Through v0.1.x this test asserted the entry stayed at version 1, because adoption was the whole
    mechanism and firing a migration would have been the bug. Version 2 deliberately changes that:
    the entry is still *adopted* -- never deleted, never recreated -- and then its inherited
    identity schemes are converted in place. `tests/ha/test_migrate.py` is what proves the
    conversion moves nothing.

    The entry data is untouched either way, which is what the swap actually rests on.
    """
    entry = await setup_entry()
    assert entry.state is entry.state.LOADED
    assert entry.version == 2
    assert entry.data["host"] == "192.0.2.10"


async def test_entity_counts(hass: HomeAssistant, setup_entry):
    entry = await setup_entry()
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    lights = [e for e in entities if e.domain == "light"]
    scenes = [e for e in entities if e.domain == "scene"]
    buttons = [e for e in entities if e.domain == "button"]
    assert len(lights) == 65
    assert len(scenes) == 3
    assert len(buttons) == 1


async def test_every_light_unique_id_is_reproduced_exactly(hass: HomeAssistant, setup_entry):
    """`<controller>_group_{n}` for groups 1-65, and nothing else.

    Controller-scoped since v0.2.0. The previous `LUXOR_LIGHT_{n}` is what `test_migrate.py`
    converts from, and is not expected to survive here.
    """
    entry = await setup_entry()
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    ids = {e.unique_id for e in entities if e.domain == "light"}
    assert ids == {f"{CONTROLLER}_group_{n}" for n in range(1, 66)}


async def test_every_scene_unique_id_is_reproduced_exactly(hass: HomeAssistant, setup_entry):
    """`{name}{index}`, flaws and all. Adopting it is what preserves the three scene entities."""
    entry = await setup_entry()
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    ids = {e.unique_id for e in entities if e.domain == "scene"}
    assert ids == {f"{CONTROLLER}_theme_{i}" for i in (0, 1, 2)}


async def test_no_entity_id_carries_a_suffix(hass: HomeAssistant, setup_entry):
    """A `_2` anywhere means identity was not preserved. It is a stop, not a rename."""
    entry = await setup_entry()
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    suffixed = [e.entity_id for e in entities if e.entity_id.endswith(("_2", "_3"))]
    assert suffixed == []


async def test_device_identifiers_are_reproduced_including_their_flaws(
    hass: HomeAssistant, setup_entry
):
    """`("luxor", "<controller>:group:N")` per group, and `("luxor", <controller>)` for the hub.

    Version 1 reproduced the previous integration's `("luxor_light", <int>)` verbatim -- off-spec
    twice over -- because that is what kept the existing 65 devices through the swap. Version 2
    converts them in place, which `tests/ha/test_migrate.py` proves does not move a device_id.
    """
    entry = await setup_entry()
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)

    hub = [d for d in devices if (DOMAIN, CONTROLLER) in d.identifiers]
    assert len(hub) == 1

    light_ids = {i for d in devices for i in d.identifiers if i != (DOMAIN, CONTROLLER)}
    assert light_ids == {light_device_identifier(CONTROLLER, n) for n in range(1, 66)}
    assert all(isinstance(i[1], str) for i in light_ids), "identifier values must be str"


async def test_device_count(hass: HomeAssistant, setup_entry):
    """One controller plus one per group."""
    entry = await setup_entry()
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 66


async def test_every_light_hangs_off_the_controller(hass: HomeAssistant, setup_entry):
    entry = await setup_entry()
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    hub = next(d for d in devices if (DOMAIN, CONTROLLER) in d.identifiers)
    children = [d for d in devices if (DOMAIN, CONTROLLER) not in d.identifiers]
    assert len(children) == 65
    assert all(d.via_device_id == hub.id for d in children)


@pytest.mark.parametrize("group", [1, 23, 65])
async def test_a_light_keeps_the_controller_s_own_name(hass: HomeAssistant, setup_entry, group):
    """Entity names come from the controller, so a rename there follows through."""
    await setup_entry()
    registry = er.async_get(hass)
    entity = registry.async_get_entity_id("light", DOMAIN, light_unique_id(CONTROLLER, group))
    assert entity is not None
    state = hass.states.get(entity)
    assert state.attributes["friendly_name"] == (
        "Group Seventeen Xyz" if group == 7 else f"Group {group:02d}"
    )


async def test_no_deprecated_device_registry_key_is_emitted(hass: HomeAssistant, setup_entry):
    """`via_device_id`, never `via_device`.

    This test exists because CI did not catch the real thing. The integration shipped with
    `DeviceInfo(via_device=...)`, which Home Assistant 2026.9 removed from `DeviceInfo` entirely
    and which emits a deprecation dated **2027.8.0** -- the very defect this integration replaced
    the old one partly to fix. It only surfaced on the live system, after the cutover.

    Asserted against the `DeviceInfo` the entity actually returns rather than against a log line,
    because a warning that fires once per integration per boot is easy to miss and easy to filter.
    """
    entry = await setup_entry()
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    hub = next(d for d in devices if (DOMAIN, CONTROLLER) in d.identifiers)

    lights = [
        e
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.domain == "light"
    ]
    assert lights, "no light entities to inspect"

    component = hass.data["entity_components"]["light"]
    entity = component.get_entity(lights[0].entity_id)
    info = entity.device_info

    assert "via_device" not in info, (
        "DeviceInfo carries the deprecated `via_device` key; it is removed in Home Assistant "
        "2027.8.0 and is absent from DeviceInfo in 2026.9"
    )
    assert info.get("via_device_id") == hub.id

"""Version 1 to 2, and the one thing that must not happen: an entity moving.

The migration converts registry records **in place**. The whole reason to do it that way is that
`async_update_device` and `async_update_entity` preserve the device_id and the entity_id, and on
this system a moved entity_id drops silently out of a `group` helper that holds all 65 light ids as
plain strings. So every test here asserts the *old* identity survives the change of scheme, not
just that the new scheme appears.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxor.const import DOMAIN, LEGACY_DEVICE_NAMESPACE

from .conftest import LEGACY_ENTRY_DATA

CONTROLLER = "lxtwo-000000000"


def _seed_v1(hass: HomeAssistant) -> MockConfigEntry:
    """A version-1 entry with exactly the registry records the previous integration created."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=LEGACY_ENTRY_DATA, options={}, version=1, title="Luxor Controller"
    )
    entry.add_to_hass(hass)

    devices = dr.async_get(hass)
    entities = er.async_get(hass)

    hub = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, CONTROLLER)},
        name=CONTROLLER,
    )
    for group in (1, 23, 65):
        devices.async_get_or_create(
            config_entry_id=entry.entry_id,
            # An int, exactly as the previous integration wrote it.
            identifiers={(LEGACY_DEVICE_NAMESPACE, group)},
            name=f"Group {group:02d}",
            via_device_id=hub.id,
        )
        entities.async_get_or_create(
            "light",
            DOMAIN,
            f"LUXOR_LIGHT_{group}",
            config_entry=entry,
            suggested_object_id=f"group_{group:02d}",
        )
    for name, index in (("Theme A", 0), ("Theme B", 1), ("Theme C", 2)):
        entities.async_get_or_create(
            "scene",
            DOMAIN,
            f"{name}{index}",
            config_entry=entry,
            suggested_object_id=name.lower().replace(" ", "_"),
        )
    return entry


async def _migrate(hass: HomeAssistant, entry: MockConfigEntry, session) -> None:
    with patch("custom_components.luxor.async_get_clientsession", return_value=session):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


# --- the property that matters ------------------------------------------------------------------


async def test_nothing_moves(hass: HomeAssistant, session):
    """Device ids, entity ids and areas all survive the change of scheme."""
    entry = _seed_v1(hass)
    devices, entities = dr.async_get(hass), er.async_get(hass)

    before_devices = {d.id for d in dr.async_entries_for_config_entry(devices, entry.entry_id)}
    before_entities = {
        e.entity_id for e in er.async_entries_for_config_entry(entities, entry.entry_id)
    }

    await _migrate(hass, entry, session)

    after_devices = {d.id for d in dr.async_entries_for_config_entry(devices, entry.entry_id)}
    after_entities = {
        e.entity_id for e in er.async_entries_for_config_entry(entities, entry.entry_id)
    }
    assert before_devices <= after_devices, "a device_id changed"
    assert before_entities <= after_entities, "an entity_id changed"
    assert not [e for e in after_entities if e.endswith(("_2", "_3"))], "identity was not preserved"


async def test_the_entry_reaches_version_2(hass: HomeAssistant, session):
    entry = _seed_v1(hass)
    await _migrate(hass, entry, session)
    assert entry.version == 2


# --- the three schemes --------------------------------------------------------------------------


async def test_device_identifiers_are_converted(hass: HomeAssistant, session):
    entry = _seed_v1(hass)
    await _migrate(hass, entry, session)

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    identifiers = {i for d in devices for i in d.identifiers}

    assert not [i for i in identifiers if i[0] == LEGACY_DEVICE_NAMESPACE], "legacy namespace left"
    for group in (1, 23, 65):
        assert (DOMAIN, f"{CONTROLLER}:group:{group}") in identifiers
    assert (DOMAIN, CONTROLLER) in identifiers, "the hub identifier must be left alone"
    assert all(isinstance(i[1], str) for i in identifiers), "identifier values must be str"


async def test_light_unique_ids_are_converted(hass: HomeAssistant, session):
    entry = _seed_v1(hass)
    await _migrate(hass, entry, session)
    ids = {
        e.unique_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.domain == "light"
    }
    assert not [i for i in ids if i.startswith("LUXOR_LIGHT_")]
    assert {f"{CONTROLLER}_group_{g}" for g in (1, 23, 65)} <= ids


async def test_scene_unique_ids_are_converted(hass: HomeAssistant, session):
    entry = _seed_v1(hass)
    await _migrate(hass, entry, session)
    ids = {
        e.unique_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.domain == "scene"
    }
    assert ids == {f"{CONTROLLER}_theme_{i}" for i in (0, 1, 2)}


# --- refusals and idempotence -------------------------------------------------------------------


async def test_an_ambiguous_scene_name_is_left_alone(hass: HomeAssistant, session):
    """`"X1"` at index 2 and `"X"` at index 12 both produce `"X12"`.

    There is no way to tell them apart from the string, so the migration refuses rather than
    guesses. A scene keeping an old unique_id still works; a wrong guess renames the entity.
    """
    entry = _seed_v1(hass)
    entities = er.async_get(hass)
    entities.async_get_or_create(
        "scene", DOMAIN, "Zone 12", config_entry=entry, suggested_object_id="zone_12"
    )

    await _migrate(hass, entry, session)

    ids = {
        e.unique_id
        for e in er.async_entries_for_config_entry(entities, entry.entry_id)
        if e.domain == "scene"
    }
    assert "Zone 12" in ids, "an ambiguous unique_id was rewritten on a guess"


async def test_it_does_not_run_twice(hass: HomeAssistant, session):
    """Version-gated. A second setup must convert nothing, because there is nothing left to convert
    and a second pass over already-converted records is how a migration corrupts them."""
    entry = _seed_v1(hass)
    await _migrate(hass, entry, session)
    first = {
        e.entity_id: e.unique_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    await _migrate(hass, entry, session)

    second = {
        e.entity_id: e.unique_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }
    assert second == first


async def test_a_fresh_install_needs_no_migration(hass: HomeAssistant, session, setup_entry):
    """A version-2 entry created today already carries the new schemes."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=LEGACY_ENTRY_DATA, options={}, version=2, title="Luxor Controller"
    )
    entry.add_to_hass(hass)
    await _migrate(hass, entry, session)

    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    lights = [e for e in entities if e.domain == "light"]
    assert len(lights) == 65
    assert all(e.unique_id.startswith(f"{CONTROLLER}_group_") for e in lights)


@pytest.mark.parametrize("version", [1, 2])
async def test_setup_succeeds_from_either_version(hass: HomeAssistant, session, version):
    entry = MockConfigEntry(
        domain=DOMAIN, data=LEGACY_ENTRY_DATA, options={}, version=version, title="Luxor"
    )
    entry.add_to_hass(hass)
    await _migrate(hass, entry, session)
    assert entry.state is entry.state.LOADED
    assert entry.version == 2

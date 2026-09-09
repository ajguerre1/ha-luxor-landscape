"""Setup, resilience, and behaviour parity with the integration being replaced."""

from __future__ import annotations

from unittest.mock import patch

import aiohttp
import pytest
from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_HS_COLOR, ColorMode
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from custom_components.luxor.const import DOMAIN
from custom_components.luxor.data import SLOT_ISSUE
from custom_components.luxor.luxor import SlotClaim, SlotTable
from custom_components.luxor.store import SlotStore

#: On a fresh registry Home Assistant generates the entity id from the device name plus the entity
#: name. On the live system the existing entries keep their own ids because the unique_id matches,
#: which is what the identity tests assert; a test starting from empty gets the generated form.
SCENE_A = "scene.lxtwo_000000000_theme_a"


def _entity(hass: HomeAssistant, group: int) -> str:
    return er.async_get(hass).async_get_entity_id("light", DOMAIN, f"LUXOR_LIGHT_{group}")


# --- setup ----------------------------------------------------------------------------------------


async def test_an_unreachable_controller_retries_rather_than_failing(
    hass: HomeAssistant, session, legacy_entry
):
    """`ConfigEntryNotReady`, not `return False`.

    This controller went unreachable four times in one recent day. An entry that fails outright at
    boot stays failed until somebody notices, which for landscape lighting means until dark.
    """
    session.raise_on["ControllerName"] = aiohttp.ClientError("refused")
    with patch("custom_components.luxor.async_get_clientsession", return_value=session):
        await hass.config_entries.async_setup(legacy_entry.entry_id)
        await hass.async_block_till_done()
    assert legacy_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_is_clean(hass: HomeAssistant, setup_entry):
    entry = await setup_entry()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


# --- brightness parity ----------------------------------------------------------------------------


async def test_lights_start_off_matching_the_capture(hass: HomeAssistant, setup_entry):
    await setup_entry()
    assert hass.states.get(_entity(hass, 23)).state == "off"


async def test_turn_on_and_off(hass: HomeAssistant, setup_entry, session):
    await setup_entry()
    entity = _entity(hass, 23)

    await hass.services.async_call(
        "light", SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity, ATTR_BRIGHTNESS: 128}, blocking=True
    )
    await hass.async_block_till_done()
    assert session.groups[23]["Inten"] == 50
    assert hass.states.get(entity).state == "on"

    await hass.services.async_call(
        "light", SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity}, blocking=True
    )
    await hass.async_block_till_done()
    assert session.groups[23]["Inten"] == 0


async def test_the_dimmest_request_does_not_turn_the_light_off(
    hass: HomeAssistant, setup_entry, session
):
    """`brightness=1` rounds to intensity 0 in the integration being replaced, so the dimmest
    possible request switches the light off. Clamped to 1 here."""
    await setup_entry()
    await hass.services.async_call(
        "light",
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: _entity(hass, 23), ATTR_BRIGHTNESS: 1},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert session.groups[23]["Inten"] == 1
    assert hass.states.get(_entity(hass, 23)).state == "on"


async def test_colour_mode_comes_from_the_controller_type(hass: HomeAssistant, setup_entry):
    """A ZDTWO gets HS. Decided once at setup, not derived per poll from a mutable `Colr` --
    Home Assistant rejects a mode set containing both BRIGHTNESS and HS, so 65 entities flipping
    mode at runtime is not a thing that can be allowed to happen."""
    await setup_entry()
    state = hass.states.get(_entity(hass, 23))
    assert state.attributes["supported_color_modes"] == [ColorMode.HS]


# --- colour ---------------------------------------------------------------------------------------


async def test_setting_a_colour_writes_the_theme_and_survives_activation(
    hass: HomeAssistant, setup_entry, session
):
    """The acceptance criterion, through the Home Assistant surface."""
    await setup_entry()
    entity = _entity(hass, 23)

    await hass.services.async_call(
        "light", SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity, ATTR_HS_COLOR: (200, 90)}, blocking=True
    )
    await hass.async_block_till_done()

    slot = session.groups[23]["Colr"]
    assert session.colours[slot] == {"C": slot, "Hue": 200, "Sat": 90}
    assert any(e["GroupNumber"] == 23 and e["Color"] == slot for e in session.theme_groups[0])

    # The nightly reclaim is now a no-op.
    await hass.services.async_call("scene", "turn_on", {ATTR_ENTITY_ID: SCENE_A}, blocking=True)
    await hass.async_block_till_done()
    assert session.groups[23]["Colr"] == slot


async def test_the_slot_table_is_persisted(hass: HomeAssistant, setup_entry, session):
    entry = await setup_entry()
    await hass.services.async_call(
        "light",
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: _entity(hass, 23), ATTR_HS_COLOR: (200, 90)},
        blocking=True,
    )
    await hass.async_block_till_done()
    table = await SlotStore(hass, entry.entry_id).async_load()
    assert table.slot_for(23) == session.groups[23]["Colr"]
    assert table.claim_for(23).name_at_claim == session.groups[23]["Name"]


async def test_setting_a_colour_does_not_reload_the_entry(
    hass: HomeAssistant, setup_entry, session
):
    """Regression guard.

    The slot table was first persisted into `entry.options`. That fires the update listener, which
    reloads the integration, so every colour change tore down and rebuilt all 68 entities. CI found
    it as a reload reaching for a real socket outside the patched session.
    """
    entry = await setup_entry()
    entity = _entity(hass, 23)
    before = hass.states.get(entity).last_changed

    with patch.object(hass.config_entries, "async_reload") as reload:
        await hass.services.async_call(
            "light",
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: entity, ATTR_HS_COLOR: (200, 90)},
            blocking=True,
        )
        await hass.async_block_till_done()
    reload.assert_not_called()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(entity) is not None
    assert before is not None


async def test_a_stale_slot_table_disables_colour_and_raises_a_repair(
    hass: HomeAssistant, session, legacy_entry
):
    """The guard, proved by refusing.

    A claim recorded against a name the controller no longer has means the slot may belong to a
    different group now. Writing anyway is how the fossil block on the reference controller was
    made.
    """
    await SlotStore(hass, legacy_entry.entry_id).async_save(
        SlotTable(
            [
                SlotClaim(
                    group=23,
                    slot=101,
                    name_at_claim="A Name It Has Not",
                    colr_at_claim=1,
                    claimed_at="2026-09-09T00:00:00+00:00",
                )
            ]
        )
    )
    with patch("custom_components.luxor.async_get_clientsession", return_value=session):
        assert await hass.config_entries.async_setup(legacy_entry.entry_id)
        await hass.async_block_till_done()

    assert ir.async_get(hass).async_get_issue(DOMAIN, SLOT_ISSUE) is not None

    with pytest.raises(HomeAssistantError, match="disabled"):
        await hass.services.async_call(
            "light",
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: _entity(hass, 23), ATTR_HS_COLOR: (200, 90)},
            blocking=True,
        )
    assert "ColorListSet" not in [s.method for s in session.sent]


async def test_a_healthy_table_raises_no_repair(hass: HomeAssistant, setup_entry):
    """The armed control for the test above. A guard that always fires is not a guard."""
    await setup_entry()
    assert ir.async_get(hass).async_get_issue(DOMAIN, SLOT_ISSUE) is None


# --- all off ------------------------------------------------------------------------------------


async def test_all_off_uses_extinguish_all(hass: HomeAssistant, setup_entry, session):
    await setup_entry()
    await hass.services.async_call("scene", "turn_on", {ATTR_ENTITY_ID: SCENE_A}, blocking=True)
    await hass.async_block_till_done()
    assert any(g["Inten"] > 0 for g in session.groups.values())
    before = {n: g["Colr"] for n, g in session.groups.items()}

    entity = er.async_get(hass).async_get_entity_id("button", DOMAIN, "lxtwo-000000000_all_off")
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: entity}, blocking=True)
    await hass.async_block_till_done()

    assert all(g["Inten"] == 0 for g in session.groups.values())
    assert {n: g["Colr"] for n, g in session.groups.items()} == before, "all-off disturbed colour"
    assert "IlluminateAll" not in [s.method for s in session.sent]


async def test_there_is_no_all_on_entity(hass: HomeAssistant, setup_entry):
    """Withdrawn permanently. `IlluminateAll` destroys the colour configuration of every group."""
    await setup_entry()
    buttons = [
        e
        for e in er.async_get(hass).entities.values()
        if e.platform == DOMAIN and e.domain == "button"
    ]
    assert len(buttons) == 1
    assert "all_off" in buttons[0].unique_id

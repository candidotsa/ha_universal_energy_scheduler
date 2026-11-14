"""Home Assistant tests: entity IDs and the options flow.

Run with pytest-homeassistant-custom-component installed; skipped otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.helpers import device_registry as dr  # noqa: E402
from homeassistant.helpers import entity_registry as er  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.ha_universal_energy_scheduler.const import DOMAIN  # noqa: E402

ENTITY_IDS = {
    "sensor.energy_scheduler_current_period",
    "sensor.energy_scheduler_next_change",
    "sensor.energy_scheduler_current_price",
    "binary_sensor.energy_scheduler_off_peak",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    hass.config.currency = "EUR"
    await hass.config.async_set_time_zone("Europe/Lisbon")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Goldenergy · Bi-horário — ciclo semanal",
        data={
            "country": "PT",
            "operator": "Goldenergy",
            "plan": "bi_horario_semanal",
            "price_mode": "manual",
            "prices": {"off_peak": 0.12, "standard": 0.19},
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_entity_ids_do_not_depend_on_supplier(hass: HomeAssistant) -> None:
    await _setup(hass)
    ids = {state.entity_id for state in hass.states.async_all() if "energy_scheduler" in state.entity_id}
    assert ids == ENTITY_IDS


async def test_options_change_supplier_and_prices(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    registry = er.async_get(hass)
    before = {e.entity_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)}

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"operator": "EDP Comercial", "plan": "bi_horario_semanal"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"price_mode": "manual"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"price_off_peak": 0.0427, "price_standard": 0.108}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()

    # New prices are live without a manual reload.
    price = hass.states.get("sensor.energy_scheduler_current_price")
    assert price.attributes["price_off_peak"] == 0.0427
    assert price.attributes["price_standard"] == 0.108

    # Title and device follow the new supplier…
    assert entry.title == "EDP Comercial · Bi-horário — ciclo semanal"
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device.manufacturer == "EDP Comercial"
    assert device.name == entry.title

    # …while entity IDs stay the same.
    after = {e.entity_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
    assert after == before == ENTITY_IDS

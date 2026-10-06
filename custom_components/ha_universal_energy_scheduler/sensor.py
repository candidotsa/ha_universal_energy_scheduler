"""Sensors: current tariff period and time of the next change."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EnergySchedulerConfigEntry
from .coordinator import EnergySchedulerCoordinator
from .entity import EnergySchedulerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnergySchedulerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [CurrentPeriodSensor(coordinator)]
    if len(coordinator.plan.periods) > 1:
        entities.append(NextChangeSensor(coordinator))
    if coordinator.prices:
        entities.append(CurrentPriceSensor(coordinator))
    async_add_entities(entities)


class CurrentPeriodSensor(EnergySchedulerEntity, SensorEntity):
    """Active period: off_peak / mid_peak / peak / standard."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator: EnergySchedulerCoordinator) -> None:
        super().__init__(coordinator, "current_period")
        self._attr_options = list(coordinator.plan.periods)

    @property
    def native_value(self) -> str:
        return self.coordinator.data.period

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "next_period": data.next_period,
            "next_change": data.next_change.isoformat() if data.next_change else None,
            "season": data.season,
            "day_type": data.day_type,
            "plan": self.coordinator.plan.name,
            "country": self.coordinator.country.code,
        }


class NextChangeSensor(EnergySchedulerEntity, SensorEntity):
    """When the period changes next (timestamp)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: EnergySchedulerCoordinator) -> None:
        super().__init__(coordinator, "next_change")

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.data.next_change

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"next_period": self.coordinator.data.next_period}


class CurrentPriceSensor(EnergySchedulerEntity, SensorEntity):
    """Price per kWh of the active period (usable in the Energy dashboard)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 4

    def __init__(self, coordinator: EnergySchedulerCoordinator) -> None:
        super().__init__(coordinator, "current_price")
        self._attr_native_unit_of_measurement = f"{coordinator.hass.config.currency}/kWh"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.prices.get(self.coordinator.data.period)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        prices = self.coordinator.prices
        attributes: dict[str, Any] = {
            "period": data.period,
            "next_price": prices.get(data.next_period) if data.next_period else None,
            "next_change": data.next_change.isoformat() if data.next_change else None,
            **{f"price_{period}": price for period, price in prices.items()},
            "price_source": self.coordinator.price_mode,
        }
        if (price_set := self.coordinator.price_set) is not None:
            attributes["prices_valid_from"] = price_set.valid_from
            attributes["prices_note"] = price_set.note
        return attributes

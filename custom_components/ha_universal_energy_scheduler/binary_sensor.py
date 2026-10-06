"""Binary sensor that is on during the cheapest (off-peak) period."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    if "off_peak" in coordinator.plan.periods:
        async_add_entities([OffPeakBinarySensor(coordinator)])


class OffPeakBinarySensor(EnergySchedulerEntity, BinarySensorEntity):
    """On while the off-peak (vazio / valle / heures creuses) period is active."""

    def __init__(self, coordinator: EnergySchedulerCoordinator) -> None:
        super().__init__(coordinator, "off_peak")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.period == "off_peak"

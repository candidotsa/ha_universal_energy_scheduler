"""Base entity for Universal Energy Scheduler."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EnergySchedulerCoordinator


class EnergySchedulerEntity(CoordinatorEntity[EnergySchedulerCoordinator]):
    """All entities of one tariff share a device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EnergySchedulerCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=coordinator.operator,
            model=coordinator.plan.name,
            entry_type=DeviceEntryType.SERVICE,
        )

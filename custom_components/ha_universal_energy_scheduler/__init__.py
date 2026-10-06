"""Universal Energy Scheduler — time-of-use tariff periods for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError

from .const import CONF_COUNTRY, CONF_PLAN, PLATFORMS
from .coordinator import EnergySchedulerCoordinator
from .schedule import ScheduleError, load_country

type EnergySchedulerConfigEntry = ConfigEntry[EnergySchedulerCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EnergySchedulerConfigEntry) -> bool:
    """Set up a tariff from a config entry."""
    config = {**entry.data, **entry.options}

    try:
        country = await hass.async_add_executor_job(load_country, config[CONF_COUNTRY])
    except (OSError, ScheduleError) as err:
        raise ConfigEntryError(
            f"Could not load tariff data for {config[CONF_COUNTRY]}: {err}"
        ) from err

    plan = country.plans.get(config[CONF_PLAN])
    if plan is None:
        raise ConfigEntryError(
            f"Tariff plan '{config[CONF_PLAN]}' no longer exists for {country.name}; "
            "open the integration options and pick another plan"
        )

    coordinator = EnergySchedulerCoordinator(hass, entry, country, plan, config)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_start()
    entry.async_on_unload(coordinator.async_stop)
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EnergySchedulerConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: EnergySchedulerConfigEntry) -> None:
    """Reload when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)

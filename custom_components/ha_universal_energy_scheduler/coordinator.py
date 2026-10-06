"""Keeps the current tariff period up to date, event-driven (no polling)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_time, async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_HOLIDAY_ENTITY,
    CONF_OPERATOR,
    CONF_PRICE_MODE,
    CONF_PRICES,
    DOMAIN,
    PRICE_MODE_DEFAULT,
    PRICE_MODE_MANUAL,
    PRICE_MODE_NONE,
)
from .schedule import CountryData, Plan, PriceSet, ScheduleState

_LOGGER = logging.getLogger(__name__)


class EnergySchedulerCoordinator(DataUpdateCoordinator[ScheduleState]):
    """Computes the active period and wakes up exactly at the next change."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        country: CountryData,
        plan: Plan,
        config: dict[str, Any],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=None,
        )
        self.country = country
        self.plan = plan
        self.operator: str | None = config.get(CONF_OPERATOR)
        self.holiday_entity: str | None = config.get(CONF_HOLIDAY_ENTITY) or None
        # Price per kWh for each period (may be empty).
        self.price_mode: str = config.get(CONF_PRICE_MODE) or (
            PRICE_MODE_MANUAL if config.get(CONF_PRICES) else PRICE_MODE_NONE
        )
        self.price_set: PriceSet | None = None
        self.prices: dict[str, float] = {}
        if self.price_mode == PRICE_MODE_DEFAULT:
            # Resolved at every start, so updated tariff files bring new prices.
            self.price_set = country.default_prices(self.operator, plan.key)
            if self.price_set is None:
                _LOGGER.warning(
                    "No built-in prices for %s / %s any more; "
                    "choose manual prices in the integration options",
                    self.operator,
                    plan.name,
                )
            else:
                self.prices = dict(self.price_set.values)
        elif self.price_mode == PRICE_MODE_MANUAL:
            self.prices = {
                period: float(price)
                for period, price in (config.get(CONF_PRICES) or {}).items()
                if period in plan.periods and price is not None
            }
        self._unsub_timer: CALLBACK_TYPE | None = None
        self._unsub_holiday: CALLBACK_TYPE | None = None

    async def _async_update_data(self) -> ScheduleState:
        return self._evaluate()

    @callback
    def async_start(self) -> None:
        """Re-evaluate whenever the holiday/workday entity changes."""
        if self.holiday_entity:
            self._unsub_holiday = async_track_state_change_event(
                self.hass, [self.holiday_entity], self._handle_holiday_change
            )

    @callback
    def async_stop(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        if self._unsub_holiday:
            self._unsub_holiday()
            self._unsub_holiday = None

    @callback
    def _evaluate(self, scheduled_for: datetime | None = None) -> ScheduleState:
        now = dt_util.now()
        # Timers can fire a few ms early; never evaluate before the boundary.
        if scheduled_for is not None and scheduled_for > now:
            now = scheduled_for
        today = now.date()

        def is_holiday(day: date) -> bool:
            # The workday sensor only describes today; future days are
            # re-evaluated at midnight anyway.
            if not self.holiday_entity or day != today:
                return False
            state = self.hass.states.get(self.holiday_entity)
            return state is not None and state.state == STATE_OFF

        result = self.plan.evaluate(now, is_holiday)
        self._schedule_next(now, result)
        return result

    @callback
    def _schedule_next(self, now: datetime, result: ScheduleState) -> None:
        if self._unsub_timer:
            self._unsub_timer()
        midnight = dt_util.start_of_local_day(now.date() + timedelta(days=1))
        wake = min(result.next_change or midnight, midnight)

        @callback
        def _fire(_fired: datetime) -> None:
            self._handle_timer(wake)

        self._unsub_timer = async_track_point_in_time(self.hass, _fire, wake)

    @callback
    def _handle_timer(self, scheduled_for: datetime) -> None:
        self._unsub_timer = None
        self.async_set_updated_data(self._evaluate(scheduled_for))

    @callback
    def _handle_holiday_change(self, _event: Event[EventStateChangedData]) -> None:
        self.async_set_updated_data(self._evaluate())

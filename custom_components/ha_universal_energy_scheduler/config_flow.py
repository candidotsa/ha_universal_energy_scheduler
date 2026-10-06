"""Config and options flow for Universal Energy Scheduler.

Steps: country -> supplier + tariff plan -> price source -> (manual prices).
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.translation import async_get_translations

from .const import (
    CONF_COUNTRY,
    CONF_HOLIDAY_ENTITY,
    CONF_OPERATOR,
    CONF_PLAN,
    CONF_PRICE_MODE,
    CONF_PRICES,
    DOMAIN,
    PRICE_MODE_DEFAULT,
    PRICE_MODE_MANUAL,
    PRICE_MODE_NONE,
)
from .schedule import (
    CountryData,
    Plan,
    PriceSet,
    ScheduleError,
    available_countries,
    load_country,
)

_LOGGER = logging.getLogger(__name__)
PRICE_PREFIX = "price_"


# ------------------------------------------------------------------ schemas


def _plan_schema(country: CountryData, defaults: dict[str, Any]) -> vol.Schema:
    operators = [SelectOptionDict(value=o, label=o) for o in country.operators]
    plans = [SelectOptionDict(value=key, label=p.name) for key, p in country.plans.items()]
    return vol.Schema(
        {
            vol.Required(
                CONF_OPERATOR, default=defaults.get(CONF_OPERATOR, vol.UNDEFINED)
            ): SelectSelector(
                SelectSelectorConfig(
                    options=operators, custom_value=True, mode=SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Required(
                CONF_PLAN, default=defaults.get(CONF_PLAN, vol.UNDEFINED)
            ): SelectSelector(
                SelectSelectorConfig(options=plans, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional(
                CONF_HOLIDAY_ENTITY,
                description={"suggested_value": defaults.get(CONF_HOLIDAY_ENTITY)},
            ): EntitySelector(EntitySelectorConfig(domain="binary_sensor")),
        }
    )


def _price_mode_schema(has_defaults: bool, current: str | None) -> vol.Schema:
    options = [PRICE_MODE_MANUAL, PRICE_MODE_NONE]
    if has_defaults:
        options.insert(0, PRICE_MODE_DEFAULT)
    if current not in options:
        current = options[0]
    return vol.Schema(
        {
            vol.Required(CONF_PRICE_MODE, default=current): SelectSelector(
                SelectSelectorConfig(
                    options=options,
                    translation_key=CONF_PRICE_MODE,
                    mode=SelectSelectorMode.LIST,
                )
            )
        }
    )


def _prices_schema(hass: HomeAssistant, plan: Plan, suggested: dict[str, float]) -> vol.Schema:
    unit = f"{hass.config.currency}/kWh"
    return vol.Schema(
        {
            vol.Optional(
                f"{PRICE_PREFIX}{period}",
                description={"suggested_value": suggested.get(period)},
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=10, step="any", mode=NumberSelectorMode.BOX,
                    unit_of_measurement=unit,
                )
            )
            for period in plan.periods
        }
    )


def _prices_from_input(plan: Plan, user_input: dict[str, Any]) -> dict[str, float]:
    return {
        period: float(value)
        for period in plan.periods
        if (value := user_input.get(f"{PRICE_PREFIX}{period}")) is not None
    }


def _title(country: CountryData, data: dict[str, Any]) -> str:
    return f"{data[CONF_OPERATOR]} · {country.plans[data[CONF_PLAN]].name}"


async def _describe_prices(hass: HomeAssistant, plan: Plan, prices: PriceSet | None) -> str:
    """Human-readable summary of the built-in prices, for the form description."""
    if prices is None:
        return "—"
    try:
        names = await async_get_translations(hass, hass.config.language, "entity", {DOMAIN})
    except Exception:  # noqa: BLE001 - only cosmetic
        _LOGGER.debug("Could not load translations for price summary", exc_info=True)
        names = {}

    def label(period: str) -> str:
        key = f"component.{DOMAIN}.entity.sensor.current_period.state.{period}"
        return names.get(key, period)

    parts = [
        f"{label(period)}: {prices.values[period]:.4f}"
        for period in plan.periods
        if period in prices.values
    ]
    text = " · ".join(parts) + f" {hass.config.currency}/kWh"
    if prices.note:
        text += f" — {prices.note}"
    if prices.valid_from:
        text += f" ({prices.valid_from})"
    return text


# --------------------------------------------------------------- shared steps


class _PriceSteps:
    """Price source + manual prices, shared by the config and options flows."""

    hass: HomeAssistant
    _country: CountryData | None
    _flow_data: dict[str, Any]

    def _plan(self) -> Plan:
        assert self._country is not None
        return self._country.plans[self._flow_data[CONF_PLAN]]

    def _defaults(self) -> PriceSet | None:
        assert self._country is not None
        return self._country.default_prices(self._flow_data.get(CONF_OPERATOR), self._flow_data[CONF_PLAN])

    def _current_mode(self) -> str | None:
        return None

    def _suggested_manual_prices(self) -> dict[str, float]:
        defaults = self._defaults()
        return dict(defaults.values) if defaults else {}

    async def _show_price_mode(self):
        defaults = self._defaults()
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="price_mode",
            data_schema=_price_mode_schema(defaults is not None, self._current_mode()),
            description_placeholders={
                "plan": self._plan().name,
                "defaults": await _describe_prices(self.hass, self._plan(), defaults),
            },
        )

    def _show_prices(self):
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="prices",
            data_schema=_prices_schema(self.hass, self._plan(), self._suggested_manual_prices()),
            description_placeholders={"plan": self._plan().name},
        )


# ---------------------------------------------------------------- config flow


class EnergySchedulerConfigFlow(_PriceSteps, ConfigFlow, domain=DOMAIN):
    """Country -> supplier and plan -> price source -> prices."""

    VERSION = 1

    def __init__(self) -> None:
        self._country: CountryData | None = None
        self._flow_data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> EnergySchedulerOptionsFlow:
        return EnergySchedulerOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        countries = await self.hass.async_add_executor_job(available_countries)
        if not countries:
            return self.async_abort(reason="no_tariff_data")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._country = await self.hass.async_add_executor_job(
                    load_country, user_input[CONF_COUNTRY]
                )
            except (OSError, ScheduleError):
                errors["base"] = "cannot_load"
            else:
                self._flow_data = {CONF_COUNTRY: self._country.code}
                return await self.async_step_plan()

        default = self.hass.config.country if self.hass.config.country in countries else None
        schema = vol.Schema(
            {
                vol.Required(CONF_COUNTRY, default=default or vol.UNDEFINED): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=code, label=name)
                            for code, name in countries.items()
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_plan(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._country is not None
        if user_input is not None:
            self._flow_data.update(user_input)
            return await self.async_step_price_mode()

        return self.async_show_form(
            step_id="plan",
            data_schema=_plan_schema(self._country, {}),
            description_placeholders={"country": self._country.name},
        )

    async def async_step_price_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            return await self._show_price_mode()
        self._flow_data[CONF_PRICE_MODE] = user_input[CONF_PRICE_MODE]
        if user_input[CONF_PRICE_MODE] == PRICE_MODE_MANUAL:
            return await self.async_step_prices()
        return self._create({CONF_PRICES: {}})

    async def async_step_prices(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is None:
            return self._show_prices()
        return self._create({CONF_PRICES: _prices_from_input(self._plan(), user_input)})

    def _create(self, extra: dict[str, Any]) -> ConfigFlowResult:
        assert self._country is not None
        data = {**self._flow_data, **extra}
        return self.async_create_entry(title=_title(self._country, data), data=data)


# --------------------------------------------------------------- options flow


class EnergySchedulerOptionsFlow(_PriceSteps, OptionsFlow):
    """Change supplier, plan, holiday sensor and prices."""

    def __init__(self) -> None:
        self._country: CountryData | None = None
        self._flow_data: dict[str, Any] = {}

    @property
    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    def _same_contract(self) -> bool:
        current = self._current
        return (
            current.get(CONF_PLAN) == self._flow_data.get(CONF_PLAN)
            and current.get(CONF_OPERATOR) == self._flow_data.get(CONF_OPERATOR)
        )

    def _current_mode(self) -> str | None:
        current = self._current
        mode = current.get(CONF_PRICE_MODE)
        if mode is None and current.get(CONF_PRICES):
            mode = PRICE_MODE_MANUAL
        return mode

    def _suggested_manual_prices(self) -> dict[str, float]:
        current = self._current
        if self._same_contract() and current.get(CONF_PRICES):
            return dict(current[CONF_PRICES])
        return super()._suggested_manual_prices()

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current = self._current
        try:
            self._country = await self.hass.async_add_executor_job(
                load_country, current[CONF_COUNTRY]
            )
        except (OSError, ScheduleError):
            return self.async_abort(reason="cannot_load")

        if user_input is not None:
            # Explicit None so clearing the field overrides entry.data.
            user_input.setdefault(CONF_HOLIDAY_ENTITY, None)
            self._flow_data = dict(user_input)
            return await self.async_step_price_mode()

        if current.get(CONF_PLAN) not in self._country.plans:
            current.pop(CONF_PLAN, None)
        return self.async_show_form(
            step_id="init",
            data_schema=_plan_schema(self._country, current),
            description_placeholders={"country": self._country.name},
        )

    async def async_step_price_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            return await self._show_price_mode()
        self._flow_data[CONF_PRICE_MODE] = user_input[CONF_PRICE_MODE]
        if user_input[CONF_PRICE_MODE] == PRICE_MODE_MANUAL:
            return await self.async_step_prices()
        return self._save({CONF_PRICES: {}})

    async def async_step_prices(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is None:
            return self._show_prices()
        return self._save({CONF_PRICES: _prices_from_input(self._plan(), user_input)})

    def _save(self, extra: dict[str, Any]) -> ConfigFlowResult:
        assert self._country is not None
        data = {**self._flow_data, **extra}
        self.hass.config_entries.async_update_entry(
            self.config_entry, title=_title(self._country, data)
        )
        return self.async_create_entry(data=data)

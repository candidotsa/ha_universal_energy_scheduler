"""Constants for Universal Energy Scheduler."""

from homeassistant.const import Platform

DOMAIN = "ha_universal_energy_scheduler"
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

CONF_COUNTRY = "country"
CONF_OPERATOR = "operator"
CONF_PLAN = "plan"
CONF_HOLIDAY_ENTITY = "holiday_entity"
CONF_PRICES = "prices"
CONF_PRICE_MODE = "price_mode"

PRICE_MODE_DEFAULT = "default"  # built-in prices from the tariff file (follow updates)
PRICE_MODE_MANUAL = "manual"  # prices typed by the user
PRICE_MODE_NONE = "none"  # no price sensor

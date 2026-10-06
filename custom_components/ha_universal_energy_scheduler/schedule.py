"""Tariff schedule engine.

Pure Python on purpose (no Home Assistant imports) so it can be unit-tested
and reused. Times in the tariff files are local wall-clock times of the
country they describe; the datetimes passed in must be timezone-aware and
already in that local timezone.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import re
from typing import Any

PERIODS: tuple[str, ...] = ("off_peak", "mid_peak", "peak", "standard", "flat")
SEASONS: tuple[str, ...] = ("all", "winter", "summer")
DAY_TYPES: tuple[str, ...] = ("all", "workday", "saturday", "sunday", "holiday")

# Where a day type looks for its rules, in order.
_DAY_FALLBACKS: dict[str, tuple[str, ...]] = {
    "workday": ("workday", "all"),
    "saturday": ("saturday", "all"),
    "sunday": ("sunday", "all"),
    "holiday": ("holiday", "sunday", "all"),
}

MINUTES_PER_DAY = 24 * 60
TARIFFS_DIR = Path(__file__).parent / "tariffs"
_TIME_RE = re.compile(r"^(\d{2}):(\d{2})$")

HolidayCheck = Callable[[date], bool]


class ScheduleError(ValueError):
    """Raised when a tariff file is invalid."""


def parse_time(value: str) -> int:
    """Convert 'HH:MM' (00:00..24:00) to minutes since midnight."""
    match = _TIME_RE.match(value) if isinstance(value, str) else None
    if not match:
        raise ScheduleError(f"Invalid time {value!r}, expected 'HH:MM'")
    hours, minutes = int(match.group(1)), int(match.group(2))
    total = hours * 60 + minutes
    if minutes > 59 or total > MINUTES_PER_DAY:
        raise ScheduleError(f"Invalid time {value!r}")
    return total


@dataclass(frozen=True)
class Interval:
    """A half-open interval [start, end) in minutes since midnight."""

    start: int
    end: int
    period: str

    def contains(self, minute: int) -> bool:
        return self.start <= minute < self.end


@dataclass(frozen=True)
class ScheduleState:
    """Result of evaluating a plan at a given moment."""

    period: str
    season: str
    day_type: str
    next_change: datetime | None
    next_period: str | None


class Plan:
    """One tariff plan (e.g. 'bi-horário, ciclo semanal')."""

    def __init__(self, key: str, raw: dict[str, Any]) -> None:
        self.key = key
        try:
            self.name: str = raw["name"]
            self.periods: tuple[str, ...] = tuple(raw["periods"])
            self.default: str = raw["default"]
            rules = raw["rules"]
        except (KeyError, TypeError) as err:
            raise ScheduleError(f"Plan {key!r}: missing field {err}") from err

        unknown = set(self.periods) - set(PERIODS)
        if unknown:
            raise ScheduleError(f"Plan {key!r}: unknown periods {sorted(unknown)}")
        if self.default not in self.periods:
            raise ScheduleError(f"Plan {key!r}: default {self.default!r} not in periods")
        if not isinstance(rules, dict) or not rules:
            raise ScheduleError(f"Plan {key!r}: 'rules' must be a non-empty object")

        seasons = set(rules)
        if seasons - set(SEASONS):
            raise ScheduleError(f"Plan {key!r}: unknown seasons {sorted(seasons - set(SEASONS))}")
        if seasons not in ({"all"}, {"winter", "summer"}):
            raise ScheduleError(
                f"Plan {key!r}: seasons must be either 'all' or both 'winter' and 'summer'"
            )

        self._rules: dict[str, dict[str, tuple[Interval, ...]]] = {}
        for season, days in rules.items():
            if set(days) - set(DAY_TYPES):
                raise ScheduleError(
                    f"Plan {key!r}/{season}: unknown day types {sorted(set(days) - set(DAY_TYPES))}"
                )
            self._rules[season] = {
                day: self._parse_day(f"{key}/{season}/{day}", periods)
                for day, periods in days.items()
            }

    def _parse_day(self, where: str, raw: dict[str, list[list[str]]]) -> tuple[Interval, ...]:
        intervals: list[Interval] = []
        for period, ranges in raw.items():
            if period not in self.periods:
                raise ScheduleError(f"{where}: period {period!r} not declared in 'periods'")
            for pair in ranges:
                if not isinstance(pair, list) or len(pair) != 2:
                    raise ScheduleError(f"{where}: intervals must be ['HH:MM', 'HH:MM']")
                start, end = parse_time(pair[0]), parse_time(pair[1])
                if start >= end:
                    raise ScheduleError(
                        f"{where}: {pair} is empty or crosses midnight "
                        "(split it into two intervals ending/starting at 24:00/00:00)"
                    )
                intervals.append(Interval(start, end, period))
        intervals.sort(key=lambda i: i.start)
        for prev, cur in zip(intervals, intervals[1:]):
            if cur.start < prev.end:
                raise ScheduleError(f"{where}: overlapping intervals")
        return tuple(intervals)

    # ------------------------------------------------------------------ lookup

    @property
    def seasonal(self) -> bool:
        return "all" not in self._rules

    def season_at(self, moment: datetime) -> str:
        """Winter/summer follow legal (DST) time, as ERSE defines it."""
        if not self.seasonal:
            return "all"
        return "summer" if moment.dst() else "winter"

    @staticmethod
    def day_type(day: date, is_holiday: HolidayCheck | None = None) -> str:
        weekday = day.weekday()
        if weekday == 5:
            return "saturday"
        if weekday == 6:
            return "sunday"
        if is_holiday is not None and is_holiday(day):
            return "holiday"
        return "workday"

    def intervals_for(self, season: str, day_type: str) -> tuple[Interval, ...]:
        days = self._rules[season]
        for candidate in _DAY_FALLBACKS[day_type]:
            if candidate in days:
                return days[candidate]
        return ()

    def period_at(self, moment: datetime, is_holiday: HolidayCheck | None = None) -> str:
        _require_aware(moment)
        season = self.season_at(moment)
        intervals = self.intervals_for(season, self.day_type(moment.date(), is_holiday))
        minute = moment.hour * 60 + moment.minute
        for interval in intervals:
            if interval.contains(minute):
                return interval.period
        return self.default

    def _boundary_minutes(self) -> list[int]:
        minutes = {0}
        for days in self._rules.values():
            for intervals in days.values():
                for interval in intervals:
                    minutes.add(interval.start)
                    if interval.end < MINUTES_PER_DAY:
                        minutes.add(interval.end)
        return sorted(minutes)

    def evaluate(
        self,
        moment: datetime,
        is_holiday: HolidayCheck | None = None,
        horizon_days: int = 8,
    ) -> ScheduleState:
        """Current period plus when (and to what) it changes next."""
        _require_aware(moment)
        current = self.period_at(moment, is_holiday)
        boundaries = self._boundary_minutes()
        next_change: datetime | None = None
        next_period: str | None = None
        for offset in range(horizon_days + 1):
            day = moment.date() + timedelta(days=offset)
            for minute in boundaries:
                candidate = datetime.combine(
                    day, time(minute // 60, minute % 60), tzinfo=moment.tzinfo
                )
                if candidate <= moment:
                    continue
                period = self.period_at(candidate, is_holiday)
                if period != current:
                    next_change, next_period = candidate, period
                    break
            if next_change is not None:
                break
        return ScheduleState(
            period=current,
            season=self.season_at(moment),
            day_type=self.day_type(moment.date(), is_holiday),
            next_change=next_change,
            next_period=next_period,
        )


@dataclass(frozen=True)
class PriceSet:
    """Built-in price per kWh for each period of one plan of one supplier."""

    values: dict[str, float]
    valid_from: str | None = None
    note: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class CountryData:
    """Contents of one tariffs/<cc>.json file."""

    code: str
    name: str
    operators: tuple[str, ...]
    plans: dict[str, Plan]
    # Optional built-in prices: operator -> plan key -> PriceSet
    prices: dict[str, dict[str, PriceSet]]

    def default_prices(self, operator: str | None, plan_key: str) -> PriceSet | None:
        return self.prices.get(operator or "", {}).get(plan_key)


def _require_aware(moment: datetime) -> None:
    if moment.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")


def parse_country(code: str, raw: dict[str, Any]) -> CountryData:
    try:
        plans = {key: Plan(key, value) for key, value in raw["plans"].items()}
        prices = _parse_prices(code, raw.get("prices", {}), plans)
        return CountryData(
            code=code.upper(),
            name=raw["name"],
            operators=tuple(raw.get("operators", [])),
            plans=plans,
            prices=prices,
        )
    except (KeyError, AttributeError, TypeError) as err:
        raise ScheduleError(f"Country {code!r}: invalid file ({err})") from err


def _parse_prices(
    code: str, raw: dict[str, Any], plans: dict[str, Plan]
) -> dict[str, dict[str, PriceSet]]:
    result: dict[str, dict[str, PriceSet]] = {}
    for operator, by_plan in raw.items():
        for plan_key, entry in by_plan.items():
            where = f"Country {code!r}: prices for {operator!r}/{plan_key!r}"
            plan = plans.get(plan_key)
            if plan is None:
                raise ScheduleError(f"{where}: unknown plan")
            if not isinstance(entry, dict) or not isinstance(entry.get("values"), dict):
                raise ScheduleError(f"{where}: expected an object with 'values'")
            values: dict[str, float] = {}
            for period, price in entry["values"].items():
                if period not in plan.periods:
                    raise ScheduleError(f"{where}: period {period!r} not in plan")
                if isinstance(price, bool) or not isinstance(price, (int, float)) or price < 0:
                    raise ScheduleError(f"{where}: invalid price {price!r}")
                values[period] = float(price)
            if not values:
                raise ScheduleError(f"{where}: 'values' is empty")
            valid_from = entry.get("valid_from")
            if valid_from is not None:
                try:
                    date.fromisoformat(valid_from)
                except (TypeError, ValueError) as err:
                    raise ScheduleError(f"{where}: invalid valid_from {valid_from!r}") from err
            result.setdefault(operator, {})[plan_key] = PriceSet(
                values=values,
                valid_from=valid_from,
                note=entry.get("note"),
                source=entry.get("source"),
            )
    return result


def load_country(code: str, directory: Path = TARIFFS_DIR) -> CountryData:
    """Load and validate one country file. Blocking I/O: run in an executor."""
    path = directory / f"{code.lower()}.json"
    with path.open(encoding="utf-8") as handle:
        return parse_country(code, json.load(handle))


def available_countries(directory: Path = TARIFFS_DIR) -> dict[str, str]:
    """Map of country code -> display name. Blocking I/O: run in an executor."""
    countries: dict[str, str] = {}
    for path in sorted(directory.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            countries[path.stem.upper()] = json.load(handle).get("name", path.stem.upper())
    return countries

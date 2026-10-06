"""Tests for the tariff schedule engine and the bundled tariff files."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from schedule import (
    PERIODS,
    ScheduleError,
    Plan,
    available_countries,
    load_country,
    parse_country,
)

LISBON = ZoneInfo("Europe/Lisbon")
MADRID = ZoneInfo("Europe/Madrid")


def at(tz, y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=tz)


@pytest.fixture(scope="module")
def pt():
    return load_country("PT")


@pytest.fixture(scope="module")
def es():
    return load_country("ES")


# ---------------------------------------------------------------- data files


@pytest.mark.parametrize("code", sorted(available_countries()))
def test_every_tariff_file_is_valid(code):
    country = load_country(code)
    assert country.plans, f"{code} has no plans"
    for plan in country.plans.values():
        assert set(plan.periods) <= set(PERIODS)
        if len(plan.periods) == 1:
            continue  # flat-rate plans never change, by design
        # Every plan must actually produce more than one period somewhere,
        # otherwise the sensor would be useless.
        seen = set()
        for day in range(1, 8):  # a full week in January and in July
            for month in (1, 7):
                for hour in range(24):
                    seen.add(plan.period_at(at(LISBON, 2026, month, day + 4, hour)))
        assert len(seen) > 1, f"{code}/{plan.key} never changes period"


# ---------------------------------------------------------- PT bi-horário


def test_pt_bi_semanal_workday_winter(pt):
    plan = pt.plans["bi_horario_semanal"]
    wed = (2026, 1, 14)
    assert plan.period_at(at(LISBON, *wed, 6, 59)) == "off_peak"
    assert plan.period_at(at(LISBON, *wed, 7, 0)) == "standard"
    state = plan.evaluate(at(LISBON, *wed, 6, 30))
    assert state.next_change == at(LISBON, *wed, 7, 0)
    assert state.next_period == "standard"
    assert state.season == "winter"


def test_pt_bi_semanal_saturday_differs_by_season(pt):
    plan = pt.plans["bi_horario_semanal"]
    # 13:30 on a Saturday: off-peak in winter, standard in summer.
    assert plan.period_at(at(LISBON, 2026, 1, 17, 13, 30)) == "off_peak"
    assert plan.period_at(at(LISBON, 2026, 7, 18, 13, 30)) == "standard"


def test_pt_bi_semanal_sunday_runs_into_monday(pt):
    plan = pt.plans["bi_horario_semanal"]
    state = plan.evaluate(at(LISBON, 2026, 1, 18, 12))  # Sunday noon
    assert state.period == "off_peak"
    assert state.next_change == at(LISBON, 2026, 1, 19, 7)  # Monday 07:00
    assert state.next_period == "standard"


def test_pt_bi_diario_crosses_midnight(pt):
    plan = pt.plans["bi_horario_diario"]
    state = plan.evaluate(at(LISBON, 2026, 3, 10, 23))
    assert state.period == "off_peak"
    assert state.next_change == at(LISBON, 2026, 3, 11, 8)


def test_pt_bi_diario_2027_shifted_half_hour(pt):
    plan = pt.plans["bi_horario_diario_2027"]
    assert plan.period_at(at(LISBON, 2026, 3, 10, 22, 15)) == "standard"
    assert plan.period_at(at(LISBON, 2026, 3, 10, 22, 30)) == "off_peak"
    assert plan.period_at(at(LISBON, 2026, 3, 10, 8, 15)) == "off_peak"


def test_saturday_is_never_treated_as_holiday(pt):
    """Regression: the old code turned every Saturday into a Sunday."""
    plan = pt.plans["bi_horario_semanal"]
    always_holiday = lambda _d: True  # noqa: E731
    assert plan.day_type(date(2026, 1, 17), always_holiday) == "saturday"
    assert plan.period_at(at(LISBON, 2026, 1, 17, 10), always_holiday) == "standard"


# --------------------------------------------------------- PT tri-horário


def test_pt_tri_diario_seasons(pt):
    plan = pt.plans["tri_horario_diario"]
    assert plan.period_at(at(LISBON, 2026, 1, 14, 9, 30)) == "peak"
    assert plan.period_at(at(LISBON, 2026, 7, 15, 9, 30)) == "mid_peak"
    assert plan.period_at(at(LISBON, 2026, 7, 15, 11)) == "peak"
    assert plan.period_at(at(LISBON, 2026, 7, 15, 23)) == "off_peak"


def test_pt_tri_semanal(pt):
    plan = pt.plans["tri_horario_semanal"]
    assert plan.period_at(at(LISBON, 2026, 1, 14, 10)) == "peak"
    assert plan.period_at(at(LISBON, 2026, 7, 15, 9, 15)) == "peak"
    assert plan.period_at(at(LISBON, 2026, 7, 15, 12, 15)) == "mid_peak"
    assert plan.period_at(at(LISBON, 2026, 1, 17, 10)) == "mid_peak"  # Saturday
    assert plan.period_at(at(LISBON, 2026, 1, 17, 15)) == "off_peak"


def test_dst_switch_changes_season(pt):
    plan = pt.plans["bi_horario_semanal"]
    # DST starts in Portugal on Sunday 2026-03-29.
    assert plan.season_at(at(LISBON, 2026, 3, 28, 12)) == "winter"
    assert plan.season_at(at(LISBON, 2026, 3, 30, 12)) == "summer"


# ------------------------------------------------------------------ Spain


def test_es_2_0td_workday(es):
    plan = es.plans["2_0td"]
    assert plan.period_at(at(MADRID, 2026, 1, 14, 7)) == "off_peak"
    assert plan.period_at(at(MADRID, 2026, 1, 14, 9)) == "mid_peak"
    assert plan.period_at(at(MADRID, 2026, 1, 14, 11)) == "peak"
    assert plan.period_at(at(MADRID, 2026, 1, 17, 11)) == "off_peak"  # Saturday


def test_es_holiday_is_off_peak(es):
    plan = es.plans["2_0td"]
    holiday = lambda d: d == date(2026, 10, 12)  # noqa: E731  Fiesta Nacional (Monday)
    assert plan.period_at(at(MADRID, 2026, 10, 12, 11), holiday) == "off_peak"
    assert plan.period_at(at(MADRID, 2026, 10, 13, 11), holiday) == "peak"


# ------------------------------------------------------------- validation


def _plan(rules, periods=("off_peak", "standard"), default="standard"):
    return Plan("t", {"name": "t", "periods": list(periods), "default": default, "rules": rules})


def test_rejects_overlap():
    with pytest.raises(ScheduleError, match="overlapping"):
        _plan({"all": {"all": {"off_peak": [["00:00", "08:00"], ["07:00", "09:00"]]}}})


def test_rejects_crossing_midnight():
    with pytest.raises(ScheduleError, match="crosses midnight"):
        _plan({"all": {"all": {"off_peak": [["22:00", "08:00"]]}}})


def test_rejects_unknown_period():
    with pytest.raises(ScheduleError):
        _plan({"all": {"all": {"super_cheap": [["00:00", "08:00"]]}}})


def test_rejects_half_seasons():
    with pytest.raises(ScheduleError, match="seasons"):
        _plan({"winter": {"all": {"off_peak": [["00:00", "08:00"]]}}})


def test_requires_aware_datetime(pt):
    with pytest.raises(ValueError):
        pt.plans["bi_horario_diario"].period_at(datetime(2026, 1, 1, 12))


# ------------------------------------------------------- flat rate / prices


def test_pt_simples_is_flat(pt):
    plan = pt.plans["simples"]
    state = plan.evaluate(at(LISBON, 2026, 1, 14, 10))
    assert state.period == "flat"
    assert state.next_change is None


def _country(prices):
    return parse_country(
        "XX",
        {
            "name": "Test",
            "operators": ["A"],
            "plans": {
                "bi": {
                    "name": "Bi",
                    "periods": ["off_peak", "standard"],
                    "default": "standard",
                    "rules": {"all": {"all": {"off_peak": [["00:00", "08:00"]]}}},
                }
            },
            "prices": prices,
        },
    )


def test_default_prices_per_operator():
    country = _country(
        {"A": {"bi": {"valid_from": "2026-01-01", "note": "n", "values": {"off_peak": 0.1, "standard": 0.2}}}}
    )
    prices = country.default_prices("A", "bi")
    assert prices.values == {"off_peak": 0.1, "standard": 0.2}
    assert prices.valid_from == "2026-01-01"
    assert country.default_prices("B", "bi") is None
    assert country.default_prices(None, "bi") is None


def test_prices_must_match_plan_periods():
    with pytest.raises(ScheduleError, match="not in plan"):
        _country({"A": {"bi": {"values": {"peak": 0.3}}}})
    with pytest.raises(ScheduleError, match="unknown plan"):
        _country({"A": {"tri": {"values": {"peak": 0.3}}}})
    with pytest.raises(ScheduleError, match="invalid price"):
        _country({"A": {"bi": {"values": {"off_peak": -1}}}})
    with pytest.raises(ScheduleError, match="valid_from"):
        _country({"A": {"bi": {"valid_from": "2026-13-01", "values": {"off_peak": 0.1}}}})
    with pytest.raises(ScheduleError, match="values"):
        _country({"A": {"bi": {"off_peak": 0.1}}})


def test_pt_regulated_prices_2026(pt):
    """ERSE Diretiva 10/2025, BTN <=20.7 kVA and >2.3 kVA, without VAT."""
    su = lambda plan: pt.default_prices("SU Eletricidade", plan).values  # noqa: E731
    assert su("simples") == {"flat": 0.1654}
    assert su("bi_horario_semanal") == {"off_peak": 0.1087, "standard": 0.1988}
    assert su("tri_horario_diario") == {"off_peak": 0.1087, "mid_peak": 0.1690, "peak": 0.2495}
    assert pt.default_prices("EDP Comercial", "simples") is None


# --------------------------------------------------- Italy / Germany / UK

ROME = ZoneInfo("Europe/Rome")
BERLIN = ZoneInfo("Europe/Berlin")
LONDON = ZoneInfo("Europe/London")


def test_it_trioraria_fasce():
    plan = load_country("IT").plans["trioraria"]
    assert plan.period_at(at(ROME, 2026, 1, 14, 10)) == "peak"       # F1
    assert plan.period_at(at(ROME, 2026, 1, 14, 7, 30)) == "mid_peak"  # F2
    assert plan.period_at(at(ROME, 2026, 1, 14, 23, 30)) == "off_peak"  # F3
    assert plan.period_at(at(ROME, 2026, 1, 17, 10)) == "mid_peak"   # Saturday F2
    assert plan.period_at(at(ROME, 2026, 1, 18, 10)) == "off_peak"   # Sunday F3


def test_it_bioraria_holiday_is_f23():
    plan = load_country("IT").plans["bioraria"]
    holiday = lambda d: d == date(2026, 12, 8)  # noqa: E731  Immacolata (Tuesday)
    assert plan.period_at(at(ROME, 2026, 12, 8, 10), holiday) == "off_peak"
    assert plan.period_at(at(ROME, 2026, 12, 9, 10), holiday) == "peak"
    assert plan.period_at(at(ROME, 2026, 12, 9, 19), holiday) == "off_peak"


def test_de_ht_nt():
    plan = load_country("DE").plans["ht_nt_22_06"]
    state = plan.evaluate(at(BERLIN, 2026, 1, 14, 21))
    assert state.period == "standard"
    assert state.next_change == at(BERLIN, 2026, 1, 14, 22)
    assert state.next_period == "off_peak"


def test_gb_intelligent_octopus_go_window():
    plan = load_country("GB").plans["intelligent_octopus_go"]
    assert plan.period_at(at(LONDON, 2026, 7, 1, 23, 29)) == "standard"
    assert plan.period_at(at(LONDON, 2026, 7, 1, 23, 30)) == "off_peak"
    state = plan.evaluate(at(LONDON, 2026, 7, 1, 23, 45))
    assert state.next_change == at(LONDON, 2026, 7, 2, 5, 30)

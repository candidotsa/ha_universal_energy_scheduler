# Contributing

The most useful contribution is **tariff data**. Each country is one file in
`custom_components/ha_universal_energy_scheduler/tariffs/<country-code>.json`.

## Data format

```json
{
  "name": "Portugal (Continente)",
  "source": "Where the schedule comes from (regulator document)",
  "operators": ["EDP Comercial", "Goldenergy"],
  "plans": {
    "bi_horario_semanal": {
      "name": "Bi-horário — ciclo semanal",
      "periods": ["off_peak", "standard"],
      "default": "standard",
      "rules": {
        "winter": {
          "workday":  { "off_peak": [["00:00", "07:00"]] },
          "saturday": { "off_peak": [["00:00", "09:30"], ["13:00", "18:30"], ["22:00", "24:00"]] },
          "sunday":   { "off_peak": [["00:00", "24:00"]] }
        },
        "summer": { "...": "..." }
      }
    }
  }
}
```

Rules:

- **periods**: any of `off_peak`, `mid_peak`, `peak`, `standard`, `flat` (single-price plans use `"periods": ["flat"]` and empty rules). `default` is used for any time not covered by an interval.
- **seasons**: either `all`, or both `winter` and `summer` (summer = while DST is in effect).
- **day types**: `all`, `workday` (Mon–Fri), `saturday`, `sunday`, `holiday`. Missing ones fall back:
  `holiday → sunday → all`, `workday/saturday/sunday → all`.
- **intervals**: `["HH:MM", "HH:MM"]`, start inclusive, end exclusive, `24:00` allowed.
  They may not overlap and may not cross midnight — split `22:00–08:00` into `["00:00","08:00"]` and `["22:00","24:00"]`.
- Plan keys are stored in users' config entries: **never rename or remove a published plan key**; add a new one instead.
- **prices** (optional): built-in prices per kWh, offered in the setup as "built-in prices" for that supplier and plan:
  ```json
  "prices": {
    "SU Eletricidade": {
      "bi_horario_semanal": {
        "valid_from": "2026-01-01",
        "note": "Tarifa regulada ERSE 2026 (BTN 3,45–20,7 kVA), sem IVA",
        "source": "https://www.erse.pt/...",
        "values": { "off_peak": 0.1087, "standard": 0.1988 }
      }
    }
  }
  ```
  Only add prices from an official, public price sheet (regulator or supplier), say in `note` whether VAT is included,
  and update `valid_from` whenever the values change. Users who picked built-in prices get the new values when they update.
- Always include an official source in the pull request.

## Tests

```bash
pip install pytest
pytest -q tests
```

The tests load every tariff file, so an invalid file fails CI.
Please add a few assertions for new plans in `tests/test_schedule.py` (a known time → expected period).

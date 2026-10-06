# Changelog

## 1.0.0-beta.1 — first public beta

- Fixed: "Unknown error" when choosing to enter your own prices (invalid number selector step).

> Tariff schedules and prices still need to be confirmed by users in each country.

- Domain is now `ha_universal_energy_scheduler` (the old `ha-universal-energy-scheduler` with hyphens was not a valid Home Assistant domain). Remove the old integration before installing this one.
- New tariff data format with validation and unit tests (see CONTRIBUTING.md).
- Portugal: bi-horário and tri-horário, daily and weekly cycles (ERSE), plus the new 2027 daily bi-horário schedule.
- Spain: 2.0TD. France: Heures Creuses 22h–6h and 23h–7h.
- Germany: Eintarif and HT/NT. Italy: monoraria, bioraria and trioraria (ARERA F1/F2/F3). United Kingdom: standard, Economy 7, Octopus Go and Intelligent Octopus Go.
- Event-driven updates: the sensor changes exactly at each boundary instead of polling every 30 s.
- New entities: next change (timestamp) and an off-peak binary sensor.
- Period states are now language-neutral: `off_peak`, `mid_peak`, `peak`, `standard` (shown translated in the UI).
- Holidays: optional workday sensor; Saturdays are no longer treated as Sundays.
- Plan, supplier and holiday sensor can be changed from the integration options.
- Single-price plans (Simples/normal in Portugal, precio único in Spain, Base in France).
- Prices per kWh for each period: choose built-in prices (kept up to date with the integration), your own prices, or none; current-price sensor for the Energy dashboard.
- Built-in prices for SU Eletricidade (ERSE regulated tariff 2026, without VAT).
- English, Portuguese, Spanish, French, German and Italian translations; bundled icon.
- Beta warning shown in the setup dialog.

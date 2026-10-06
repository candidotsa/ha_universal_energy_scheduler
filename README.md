# Universal Energy Scheduler

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
![status](https://img.shields.io/badge/status-beta-orange)
[![Validate](https://github.com/candidotsa/ha_universal_energy_scheduler/actions/workflows/validate.yml/badge.svg)](https://github.com/candidotsa/ha_universal_energy_scheduler/actions/workflows/validate.yml)

> [!WARNING]
> **Beta.** Tariff schedules and prices are transcribed from public sources and **still need to be confirmed**.
> Always check them against your contract or bill, and please [report anything wrong](https://github.com/candidotsa/ha_universal_energy_scheduler/issues/new/choose).
>
> 🇵🇹 **Versão beta.** Os horários e preços dos tarifários **ainda precisam de confirmação**. Confirme sempre com o seu contrato ou fatura e reporte erros nas *Issues*.

A Home Assistant integration that knows which **time-of-use electricity period** you are in right now
(off-peak, mid-peak, peak) and **when it changes next**, so automations can shift loads to the cheapest hours.

No cloud, no polling: the schedule is computed locally and entities update at the exact minute the period changes.

> 🇵🇹 **Em português:** integração que indica o período tarifário atual (vazio, cheias, ponta, fora de vazio)
> e a hora da próxima mudança, para bi-horário e tri-horário em ciclo diário ou semanal, segundo os horários da ERSE.
> Ver [secção em português](#-em-português).

## Supported tariffs

| Country | Plans | Notes |
|---|---|---|
| 🇵🇹 Portugal (mainland) | Simples (normal); bi-horário and tri-horário, daily and weekly cycle; bi-horário daily with the new 2027 schedule | ERSE schedules, same for every supplier |
| 🇪🇸 Spain (Peninsula, Balearic and Canary Islands) | Single price; 2.0TD (punta / llano / valle) | Weekends and national holidays are valle |
| 🇫🇷 France | Base; Heures Creuses 22h–6h and 23h–7h | Off-peak hours depend on your delivery point |
| 🇩🇪 Germany | Eintarif; HT/NT with Niedertarif 22–6 and 21–6 | HT/NT hours are set by your grid operator |
| 🇮🇹 Italy | Monoraria; bioraria (F1 / F23); trioraria (F1 / F2 / F3) | ARERA time bands; Sundays and holidays are F3 |
| 🇬🇧 United Kingdom | Standard variable; Economy 7; Octopus Go; Intelligent Octopus Go | Economy 7 hours vary by meter; smart-charge slots are not modelled |

All schedules are **beta** and need confirmation — see the warning above.

**Built-in prices** currently available: 🇵🇹 SU Eletricidade (ERSE regulated tariff 2026, contracted power 3.45–20.7 kVA, **without VAT**) for Simples, bi-horário and tri-horário. Prices only cover the energy term (€/kWh) — standing/power charges and taxes are not included.

Missing your tariff? It's a JSON file — see [CONTRIBUTING.md](CONTRIBUTING.md) or open an issue with an official source.

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/candidotsa/ha_universal_energy_scheduler`, category **Integration**.
2. Download **Universal Energy Scheduler** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → Universal Energy Scheduler**.

### Manual

Copy `custom_components/ha_universal_energy_scheduler` into your `config/custom_components/` folder and restart.

Requires Home Assistant 2025.2 or newer (the icon shows from 2026.3).

## Configuration

1. Choose the country.
2. Choose the supplier (type your own if it's not listed) and the tariff plan — **Simples/normal** for a single price, or a time-of-use plan.
3. **Prices:** choose where the price per kWh comes from:
   - **Built-in prices** — shipped with the integration for that supplier and plan (when available), and updated automatically when you update the integration.
   - **My own prices** — type the price of each period; the fields are pre-filled with the built-in prices when they exist, so you only change what is different.
   - **No prices** — no price sensor.
4. Optionally choose a **workday sensor** (for tariffs where public holidays count as Sunday, such as Spain 2.0TD). Use a sensor that is *off* on non-working days, like the built-in [Workday](https://www.home-assistant.io/integrations/workday/) integration. Only Monday–Friday holidays are taken into account.

Plan, supplier, prices and workday sensor can be changed later via **Configure** — handy when your meter switches to new schedules.

Seasons (winter/summer) follow legal time (DST) of your Home Assistant time zone, as defined by ERSE.

## Entities

| Entity | Description |
|---|---|
| `sensor.<name>_current_period` | `off_peak`, `mid_peak`, `peak` or `standard` (shown translated). Attributes: `next_period`, `next_change`, `season`, `day_type`, `plan`. |
| `sensor.<name>_next_change` | Timestamp of the next period change, with `next_period`. |
| `binary_sensor.<name>_off_peak` | `on` during the off-peak period (time-of-use plans only). |
| `sensor.<name>_current_price` | Price per kWh of the active period (only when prices are set). Attributes: `next_price`, `next_change`, all period prices, `price_source` (`default`/`manual`) and, for built-in prices, `prices_valid_from` and `prices_note`. |

The **current price** sensor can be used directly in the **Energy dashboard** (*Settings → Dashboards → Energy → Grid consumption → Use an entity with current price*).

How periods map to local names:

| State | 🇵🇹 | 🇪🇸 | 🇫🇷 | 🇩🇪 | 🇮🇹 | 🇬🇧 |
|---|---|---|---|---|---|---|
| `off_peak` | Vazio | Valle | Heures creuses | Niedertarif (NT) | F3 / F23 | Off-peak |
| `mid_peak` | Cheias | Llano | — | — | F2 | — |
| `peak` | Ponta | Punta | — | — | F1 | — |
| `standard` | Fora de vazio | — | Heures pleines | Hochtarif (HT) | — | Peak / day rate |
| `flat` | Simples | Precio único | Base | Eintarif | Monoraria | Single rate |

Check the real entity IDs in **Settings → Entities** — they depend on the device name.

## Automation examples

Start the dishwasher when off-peak begins:

```yaml
automation:
  - alias: Dishwasher at off-peak
    triggers:
      - trigger: state
        entity_id: binary_sensor.edp_comercial_bi_horario_ciclo_semanal_off_peak
        to: "on"
    actions:
      - action: switch.turn_on
        target:
          entity_id: switch.dishwasher
```

Stop a load when peak starts:

```yaml
automation:
  - alias: Pause heater during peak
    triggers:
      - trigger: state
        entity_id: sensor.edp_comercial_tri_horario_ciclo_diario_current_period
        to: peak
    actions:
      - action: switch.turn_off
        target:
          entity_id: switch.water_heater
```

## Disclaimer

Schedules are transcribed from public regulator documents and may contain errors or become outdated.
Always check them against your contract/bill. Not affiliated with any regulator or supplier.

## 🇵🇹 Em português

**⚠️ Versão beta:** os horários e preços ainda precisam de confirmação.

**Instalação:** HACS → Repositórios personalizados → adicionar este repositório como *Integration* → transferir → reiniciar →
*Definições → Dispositivos e serviços → Adicionar integração → Universal Energy Scheduler*.

**Configuração:** país → comercializador e tarifário (Simples/normal, bi-horário ou tri-horário) → preços:

- **Usar preços de origem** — vêm com a integração e são atualizados quando a integração é atualizada. Para já existem os da **SU Eletricidade** (tarifa regulada ERSE 2026, 3,45–20,7 kVA, **sem IVA**).
- **Definir os meus preços** — os campos vêm preenchidos com os preços de origem (se existirem); altere só o que for diferente no seu contrato.
- **Sem preços** — não cria o sensor de preço.

Os preços são só o termo de energia (€/kWh): não incluem a potência contratada, taxas nem IVA. O sensor de preço atual pode ser usado no painel de Energia.

**Notas para Portugal:**

- Os períodos horários são definidos pela ERSE e são iguais em todos os comercializadores; o comercializador escolhido serve só para dar nome ao dispositivo.
- Verão/inverno seguem a hora legal (mudança da hora), como no ciclo semanal da ERSE.
- **Novos horários ERSE:** a ERSE aprovou novos períodos horários que serão aplicados aos clientes BTN bi e tri-horários entre 1 de julho e 31 de dezembro de 2027. Quando o seu contador mudar, escolha o novo tarifário em *Configurar*. Por agora só está incluído o bi-horário diário novo; os restantes serão adicionados quando os mapas completos estiverem confirmados (contribuições bem-vindas).
- Açores e Madeira têm horários próprios e ainda não estão incluídos.

## License

MIT

# Battery System Engineering Tool - v1.1

A personal engineering decision-support tool for battery energy storage system (BESS) feasibility, sizing and electrical architecture. It is transparent and auditable: every result traces back to inputs, equations and assumptions.

> **Not a certified design tool.** It does not replace detailed design, supplier confirmation, applicable standards, classification requirements or formal engineering approval.

## Quick start

Python 3.11+.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Run the tests:

```bash
pip install -r requirements-dev.txt
pytest
```

### Deploy on Streamlit Community Cloud

1. Push this folder to a GitHub repository (keep `app.py` at the repository root).
2. On <https://share.streamlit.io> choose **New app**, select the repository and set the main file to `app.py`.

## First thing to do: replace the module data

`data/components/vda355_4p3s.json` ships with **placeholder capacity (50 Ah) and unknown manufacturer/chemistry**. Voltages come from the original README (4 modules = 33.6 / 44.4 / 52.2 V). The app shows a PLACEHOLDER warning until you overwrite the file with datasheet values and set `"data_status": "VERIFIED"`.

Module record fields:

| Field | Required | Notes |
|---|---|---|
| manufacturer, model, chemistry | yes | |
| series_cells, parallel_cells | yes | |
| nominal_voltage_v, voltage_min_v, voltage_max_v | yes | module level; must satisfy min < nominal < max |
| capacity_ah | yes | |
| max_discharge_current_a | no | if absent, the current check is MISSING |
| energy_wh_stated | no | compared with V x Ah; sizing always uses V x Ah |
| internal_resistance_mohm, ocv_soc, r0_soc_temperature, r1_c1_soc_temperature, thermal_capacity_j_per_k, thermal_resistance_k_per_w | no | stored for v3/v4, not used in v1 |
| source, notes | no | |
| data_status | no | `VERIFIED`, `UNVERIFIED` (default) or `PLACEHOLDER`. Anything but VERIFIED raises a WARNING |

Drop additional `.json` records into `data/components/` and pick them in the sidebar (files starting with `_` are ignored).

## What it does

- Constant-power AC or DC loads
- Generic conversion chain: `[transformer] -> inverter -> [DC/DC] -> battery` (AC) or `[DC/DC] -> battery` / direct (DC)
- **Series-count search**: tests every nearby integer series count against the full module voltage envelope, shows why each passes or fails, and picks the feasible one with the fewest modules
- Parallel-string sizing from design energy, minimum SOC and explicit EOL factors
- Power, apparent-power, voltage-interface and worst-case current checks (current is highest at minimum bus voltage for a constant-power load)
- Optional part-load efficiency curves, inverter standby and battery parasitic load
- Status per check (PASS / WARNING / MISSING / FAIL) and an overall status
- Calculation audit trail, exportable as JSON

Equations and conventions are in [`engineering_basis.md`](engineering_basis.md).

## Philosophy: nothing is silently invented

- Efficiency must be supplied. If it is not, the tool stops with MISSING.
- Standby power and battery parasitic load left empty are treated as 0 W **with a WARNING**.
- A thermal factor of 1.0, unconfirmed assumptions, placeholder module data and double-counted SOC all raise warnings.
- The sidebar opens with a clearly labelled illustrative worked example; use **Clear assumption inputs** to start without pre-filled efficiency, standby or parasitic values.

## Important result notes

- With modules of 8.4-13.05 V (ratio 1.55), the original 40-60 V inverter window (ratio 1.50) **cannot** be satisfied by any integer series count. The tool now reports this explicitly. The worked example uses a 30-72 V window, for which 4 or 5 modules in series are feasible.
- The voltage check uses datasheet cut-off voltages (a conservative envelope). OCV/SOC, voltage sag and temperature are not modelled; see the limitations list in the app.

## Repository structure

```text
app.py                  Streamlit interface
audit.py                statuses, checks, audit log, MissingDataError
battery_model.py        battery module record and pack arithmetic
power_components.py     load, inverter, DC/DC converter, transformer
sizing_engine.py        chain, series search, sizing, checks
engineering_basis.md    equations and conventions
data/components/        module records (JSON)
tests/test_sizing.py    pytest suite
.github/workflows/      CI (runs pytest on push)
```

## Changes from v1.0

- Series-count search implemented (the README previously promised it); default example no longer opens in an unfixable FAIL state
- DC loads are checked (direct connection window, DC/DC converter); transformer and DC/DC are wired into the chain
- Power, VA, inverter-rating, interface-voltage, phase and worst-case-current checks added
- No silent defaults for efficiency; standby/parasitic/thermal/assumption warnings
- Status is a computed aggregate and is shown in the UI; audit trail is produced and exportable
- Data quality is computed from the record; stated-vs-derived energy mismatch is flagged
- Input validation (phases, efficiency, windows, factors); path resolved relative to the app file
- Tests rewritten to cover all of the above

## Roadmap

v2 dynamic load profiles; v3 equivalent-circuit model (OCV, R0, RC); v4 electrothermal model; v5 degradation/SOH; v6 expanded COTS database and recommendations.

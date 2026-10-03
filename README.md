# Battery System Engineering Tool — v1

## What is this?

This is a personal engineering decision-support tool for battery energy storage system (BESS) feasibility, sizing and electrical architecture.

It is designed for real engineering projects where the battery may need to supply either DC or AC loads through power-conversion equipment such as:

- DC/DC converters
- Inverters
- Transformers
- Rectifiers

The tool is intentionally designed to be transparent and auditable.

## Core principle

The software separates:

1. **Manufacturer data** — values directly stated by a supplier/datasheet.
2. **Derived values** — values calculated from manufacturer data.
3. **Engineering assumptions** — values introduced because required information is unavailable.
4. **Estimated values** — model values that are not manufacturer-certified.
5. **Missing values** — values that remain unknown.

The software must never silently invent missing battery data.

## v1 scope

v1 supports:

- Battery modules with configurable series/parallel topology
- Constant electrical loads
- AC and DC loads
- Inverter/DC-DC/transformer stages as architecture components
- Battery-bus voltage feasibility checks
- Series and parallel module sizing
- BOL/EOL capacity factors
- Engineering margins
- Component/COTS data entry
- Explicit assumptions and validation status
- Basic Streamlit user interface
- Automated calculation tests

Duty-cycle calculations are intentionally outside v1. A separate load calculation can provide the constant design load used here.

## Engineering workflow

```text
Project requirement
        |
        v
Load definition
        |
        v
Power-conversion architecture
        |
        v
Battery-bus requirement
        |
        v
Battery module selection
        |
        v
Series / parallel sizing
        |
        v
BOL / EOL checks
        |
        v
Voltage / power / current checks
        |
        v
Engineering result + audit trail
```

## Example

For an AC load:

```text
AC load
  |
  v
Inverter
  |
  v
DC battery bus
  |
  v
Battery modules
```

The software accounts for inverter efficiency when calculating the required battery-side power.

If the selected battery module is 11.1 V nominal and the target bus is approximately 48 V, the tool evaluates feasible integer series counts rather than simply dividing 48 / 11.1.

For example:

```text
4 modules in series
Nominal bus = 44.4 V
Minimum bus = 33.6 V
Maximum bus = 52.2 V
```

The actual battery voltage range must be compatible with the selected power-conversion equipment.

## COTS components

COTS products can be entered as component records containing:

- Manufacturer
- Model
- Datasheet/reference
- Input voltage range
- Output voltage
- Rated power
- Peak power
- Efficiency
- Temperature limits
- Mass
- Dimensions
- Cost, where known
- Verification date

Commercial product data is kept separate from the engineering calculation engine.

## Auditability

Every important result should eventually be traceable to:

```text
Input
  -> Equation
  -> Result
  -> Source / assumption
  -> Validation
```

The tool is a decision-support/calculation package. It is **not** a certified design tool and does not replace detailed design, supplier confirmation, applicable standards, classification requirements, or formal engineering approval.

## Running locally

Install Python 3.11+.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the local Streamlit address shown in the terminal.

## Repository structure

```text
battery_system_engineering_tool_v1/
|
├── app.py
├── battery_model.py
├── power_components.py
├── sizing_engine.py
├── audit.py
├── engineering_basis.md
├── requirements.txt
|
├── data/
│   └── components/
│       └── vda355_4p3s.json
|
└── tests/
    └── test_sizing.py
```

## Roadmap

### v1
Static sizing and electrical architecture.

### v2
Dynamic load profiles and power-flow modelling.

### v3
Equivalent-circuit battery model:
- OCV vs SOC
- R0
- RC dynamics
- current/voltage response

### v4
Electrothermal model.

### v5
Degradation and SOH modelling.

### v6
Expanded COTS database and recommendation engine.

The architecture is deliberately being built so that later physics does not change the basic input/output and audit structure.

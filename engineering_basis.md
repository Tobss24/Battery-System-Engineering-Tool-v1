# Engineering Basis — v1

## 1. Purpose

This document defines the engineering assumptions and calculation conventions for the Battery System Engineering Tool.

## 2. Sign convention

Loads are positive power demand.

Battery-side power is positive when the battery is delivering power to the system.

## 3. AC load

For a constant AC real-power load:

P_AC = specified real power.

For power factor PF:

S_AC = P_AC / PF

For a balanced three-phase load:

I_AC = P_AC / (sqrt(3) * V_LL * PF)

The first release uses real power for energy sizing and retains apparent power/current for engineering checks.

## 4. Inverter

For DC-to-AC conversion:

P_DC = P_AC / efficiency

If inverter standby power is provided:

P_DC,total = P_AC / efficiency + standby_power

Efficiency must be supplied by the user or a component record. It must not be assumed silently.

## 5. DC load

For a DC load:

P_DC = specified load power.

If a converter is inserted upstream, its efficiency is applied to determine the upstream power requirement.

## 6. Transformer

An ideal transformer does not create or consume energy.

For a practical transformer:

P_primary = P_secondary / efficiency

Voltage ratio:

V_secondary / V_primary = N_secondary / N_primary

A transformer is required when the selected AC source voltage does not match the required load voltage and no suitable inverter output is selected.

## 7. Battery module topology

For Ns identical modules in series:

V_nom_pack = Ns * V_nom_module

V_min_pack = Ns * V_min_module

V_max_pack = Ns * V_max_module

Capacity remains approximately equal to the capacity of one series string.

For Np parallel strings:

Capacity_pack = Np * Capacity_string

Energy_pack = V_nom_pack * Capacity_pack

Total module count:

N_modules = Ns * Np

## 8. Energy sizing

For constant load power:

E_load = P_load * autonomy_hours

The battery-side energy requirement includes conversion losses.

For a conversion chain with efficiencies eta_1, eta_2, ...:

P_battery = P_load / (eta_1 * eta_2 * ...)

Where standby losses are known, they are added explicitly.

## 9. EOL

EOL usable capacity is represented using explicit factors.

Example:

E_EOL = E_BOL * f_SOC * f_thermal * f_cyclic * f_calendar

The factors are inputs. They are not treated as universal battery constants.

## 10. Margin

Design margin is applied explicitly to the required energy:

E_design = E_required * (1 + margin)

The UI must show the margin separately.

## 11. Battery-bus feasibility

The software does not assume that a nominal battery bus voltage is sufficient.

For a candidate series count, the full operating voltage range is calculated and compared with the allowable input range of the connected power-conversion component.

A candidate is not considered fully feasible merely because its nominal voltage is close to the target.

## 12. Missing data

Missing manufacturer data remains missing.

If an engineering estimate is used, it must be labelled as an assumption/estimate and should carry a confidence level.

## 13. COTS recommendations

COTS recommendations are decision-support only.

A recommended product must be traceable to a product record and its source/reference. Availability, price, certification and technical suitability must be verified before procurement or final design.

## 14. Engineering status

- PASS = calculation/check satisfies the defined criterion.
- WARNING = calculation can proceed, but an assumption or incomplete input exists.
- FAIL = defined requirement is not satisfied.
- MISSING = required information is unavailable.

## 15. Design boundary

The software is a calculation and decision-support tool. It does not constitute certification or formal design approval.

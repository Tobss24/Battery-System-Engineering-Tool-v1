# Engineering Basis - v1.1

## 1. Purpose

Assumptions and calculation conventions for the Battery System Engineering Tool. The code implements exactly what is written here; anything not written here is not modelled.

## 2. Sign convention

Loads are positive power demand. Battery-side power is positive when the battery delivers power to the system.

## 3. AC load

Constant real power P_AC. For power factor PF: S_AC = P_AC / PF.
Balanced three-phase current: I_AC = P_AC / (sqrt(3) * V_LL * PF).
Real power drives energy sizing. Apparent power is used for transformer loading and an inverter rating warning.

## 4. DC load

P_DC = specified load power. PF and phases are ignored (normalised to 1). A DC load may carry an allowable supply voltage window, required to verify a direct connection.

## 5. Conversion chain

Stages are ordered from the load towards the battery. Supported arrangements:

- AC load: [transformer] -> inverter -> [DC/DC converter] -> battery
- DC load: [DC/DC converter] -> battery, or direct connection

Power is propagated stage by stage:

- Inverter: P_in = P_out / eta + P_standby
- DC/DC converter: P_in = P_out / eta
- Transformer: P_primary = P_secondary / eta

Efficiency is never assumed. If no efficiency (flat value or curve) is supplied the calculation stops with MISSING. If a part-load curve is supplied, efficiency is interpolated at the operating fraction of rated power; otherwise a flat value is used and a WARNING is raised when the stage runs below 20 % of rating.

Inverter standby and battery parasitic load, if not supplied, are treated as 0 W with a WARNING (supply 0 explicitly once confirmed).

### Interface checks

- Inverter AC output vs load voltage must match within +/-5 %, otherwise FAIL (a transformer is required).
- Transformer secondary vs load, and inverter output vs transformer primary, must match within +/-5 %.
- DC/DC output must lie inside the load window (or match load voltage within +/-5 % if no window is given) and inside the inverter DC window when feeding an inverter.
- Inverter phases must equal load phases when the inverter phases are specified.

### Rating checks

Output real power vs rated power for inverters and converters; secondary apparent power vs rated VA for transformers. PASS up to 80 %, WARNING 80-100 %, FAIL above 100 %.

## 6. Energy sizing

P_battery = P_chain + P_parasitic
E_required = P_battery * autonomy_hours
E_design = E_required * (1 + margin)   (margin energy is reported separately)

## 7. Usable energy and EOL factors

usable_fraction = (1 - SOC_min) * f_soc * f_thermal * f_cyclic * f_calendar

The factors are user inputs, not battery constants. Meaning of each:

- SOC_min: lower SOC floor of the operating window.
- f_soc: extra SOC-related loss beyond SOC_min (e.g. SOC estimation error). A WARNING is raised if both are applied, to prevent double counting.
- f_thermal: capacity at operating temperature. A value of 1.0 raises a WARNING.
- f_cyclic, f_calendar: lifetime (end-of-life) fade, not single-discharge effects.

## 8. Battery topology and sizing

V_nom = Ns * V_nom_module; V_min = Ns * V_min_module; V_max = Ns * V_max_module
E_module = V_nom_module * Ah_module (V x Ah is always used; a stated energy that differs by more than 2 % raises a WARNING)
Np = ceil(E_design / (Ns * E_module * usable_fraction)), N_modules = Ns * Np

## 9. Series-count search and bus feasibility

The bus-side component is the one adjacent to the battery (DC/DC converter, else inverter, else the DC load). Its DC input window [Wmin, Wmax] must contain the whole pack envelope:

Ns * V_min_module >= Wmin and Ns * V_max_module <= Wmax

so Ceil(Wmin / V_min_module) <= Ns <= Floor(Wmax / V_max_module). This is only possible when Wmax / Wmin >= V_max_module / V_min_module. In automatic mode the tool evaluates every nearby integer Ns, reports PASS/FAIL with the reason for each, and selects the feasible Ns with the fewest total modules. If none is feasible it explains why and the result is FAIL.

The envelope uses the datasheet cut-off voltages. Because the operating SOC window lies inside that envelope and the BMS disconnects at the cut-off, this is a conservative acceptance check. It does not model OCV, SOC-dependent voltage, R0 sag or temperature.

## 10. Current checks

For a constant-power load, current is highest at the lowest bus voltage:

I_worst = P_battery / V_min_pack; per string I_string = I_worst / Np; C-rate = I_string / Ah_module

I_string is compared to the module's maximum discharge current. If that is not in the module record the check is MISSING. An inverter maximum DC current, if supplied, is checked at the same worst case.

## 11. Missing data

Missing manufacturer data remains missing. Any estimate must be labelled as an assumption. The module record carries data_status: VERIFIED, UNVERIFIED (default) or PLACEHOLDER; anything other than VERIFIED raises a WARNING.

## 12. COTS recommendations

Decision support only. A recommended product must be traceable to a product record and source. Availability, price, certification and suitability must be verified before procurement.

## 13. Engineering status

- PASS: the check satisfies its criterion.
- WARNING: calculation can proceed, but an assumption or incomplete input exists.
- MISSING: information required to evaluate a check is unavailable.
- FAIL: a defined requirement is not satisfied.

Overall status = most severe check status (PASS < WARNING < MISSING < FAIL). A hard-required value (e.g. efficiency) that is absent stops the calculation instead of producing a result.

The "I have reviewed all assumption inputs" tick clears the Assumption review WARNING; it does not verify the values.

## 14. Audit trail

Every result carries records of input -> equation -> result -> source/assumption status, shown in the app and exportable as JSON.

## 15. Not modelled in v1

Duty cycles, OCV/SOC curves, R0/RC dynamics, voltage sag, temperature, self-discharge (only via the parasitic input), part-load efficiency (unless a curve is given), degradation.

## 16. Design boundary

Calculation and decision-support tool. It does not constitute certification or formal design approval.

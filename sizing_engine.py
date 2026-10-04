"""Static battery sizing and electrical architecture checks (v1).

Flow: build conversion chain -> propagate power load->battery -> energy sizing ->
series-count search against the bus-side voltage window -> parallel strings ->
power / current / voltage / data checks -> aggregated status + audit trail.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from typing import Any, Dict, List, Optional, Tuple

from audit import (
    FAIL,
    MISSING,
    PASS,
    WARNING,
    AuditLog,
    Check,
    MissingDataError,
    worst_status,
)
from battery_model import BatteryModule
from power_components import DCConverter, Inverter, Load, Transformer

VOLTAGE_MATCH_TOL = 0.05  # +/-5 % for nominal voltage matching between stages
RATING_WARN_FRACTION = 0.80  # WARNING above 80 % of a component rating
LOW_LOAD_EFF_FRACTION = 0.20  # WARNING if flat efficiency is used below 20 % load
ENERGY_MISMATCH_WARN_PCT = 2.0
_EPS = 1e-9

LIMITATIONS = [
    "Constant load power only; duty cycles are outside v1.",
    "Voltage checks use the datasheet cut-off envelope. OCV/SOC, R0 sag and BMS "
    "cut-offs are not modelled, so real bus voltage under load can differ.",
    "No temperature model: low-temperature capacity loss exists only through the "
    "explicit thermal factor.",
    "Self-discharge and BMS quiescent draw exist only through the explicit "
    "battery parasitic-load input.",
    "Efficiency is flat unless a part-load curve is supplied.",
    "Calculation and decision support only; not certification or design approval.",
]


@dataclass
class EOLFactors:
    # soc: additional SOC-related usable-energy loss beyond the minimum-SOC floor
    #      (e.g. SOC estimation error, charge cap). Do not repeat the min-SOC floor here.
    # thermal: capacity available at the operating temperature.
    # cyclic: lifetime cycling fade at end of life (not a single-discharge effect).
    # calendar: lifetime calendar fade at end of life.
    soc: float = 1.0
    thermal: float = 1.0
    cyclic: float = 1.0
    calendar: float = 1.0

    def __post_init__(self) -> None:
        for name in ("soc", "thermal", "cyclic", "calendar"):
            value = getattr(self, name)
            if not 0 < value <= 1:
                raise ValueError(f"EOL {name} factor must be > 0 and <= 1.")

    @property
    def combined(self) -> float:
        return self.soc * self.thermal * self.cyclic * self.calendar


@dataclass
class SizingResult:
    load_power_w: float
    chain_power_w: float  # power the conversion chain draws from the battery bus
    parasitic_power_w: float
    battery_power_w: float  # chain + parasitic
    autonomy_hours: float
    required_energy_wh: float
    margin: float
    margin_energy_wh: float
    design_energy_wh: float
    usable_fraction: float
    series_modules: int
    parallel_strings: int
    total_modules: int
    nominal_bus_v: float
    minimum_bus_v: float
    maximum_bus_v: float
    bol_energy_wh: float
    eol_usable_energy_wh: float
    worst_case_current_a: float  # battery_power / minimum bus voltage
    per_string_current_a: float
    c_rate_per_string: float
    bus_feasible: Optional[bool]
    series_selection: str
    series_feasibility: Optional[Dict[str, Any]]
    stages: List[Dict[str, Any]]
    candidates: List[Dict[str, Any]]
    checks: List[Check]
    audit: List[Dict[str, Any]]
    limitations: List[str]
    status: str


# --------------------------------------------------------------------------- series search
def series_feasibility(battery: BatteryModule, window: Tuple[float, float]) -> Dict[str, Any]:
    """Which integer series counts can keep the FULL module envelope inside the window?

    Needs Ns*Vmin_module >= window_min and Ns*Vmax_module <= window_max, i.e.
    ceil(window_min/Vmin) <= Ns <= floor(window_max/Vmax). This is only possible when the
    window ratio (max/min) is at least the module ratio (Vmax/Vmin).
    """
    lo, hi = window
    ns_min = max(1, ceil(lo / battery.voltage_min_v - _EPS))
    ns_max = floor(hi / battery.voltage_max_v + _EPS)
    return {
        "window_v": (lo, hi),
        "ns_min": ns_min,
        "ns_max": ns_max,
        "feasible_possible": ns_min <= ns_max,
        "module_voltage_ratio": battery.voltage_max_v / battery.voltage_min_v,
        "window_ratio": hi / lo,
    }


def evaluate_series_candidates(
    battery: BatteryModule,
    window: Optional[Tuple[float, float]],
    design_energy_wh: Optional[float] = None,
    usable_fraction: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Evaluate integer series counts around the window; report PASS/FAIL and why."""
    if window is None:
        return []
    lo, hi = window
    first = max(1, int(lo // battery.voltage_max_v))
    last = min(first + 500, max(first + 2, int(hi // battery.voltage_max_v) + 2))
    rows: List[Dict[str, Any]] = []
    for ns in range(first, last + 1):
        vmin = ns * battery.voltage_min_v
        vmax = ns * battery.voltage_max_v
        reasons = []
        if vmin < lo - _EPS:
            reasons.append(f"minimum {vmin:.1f} V is below window minimum {lo:.1f} V")
        if vmax > hi + _EPS:
            reasons.append(f"maximum {vmax:.1f} V is above window maximum {hi:.1f} V")
        row: Dict[str, Any] = {
            "series_modules": ns,
            "nominal_v": ns * battery.nominal_voltage_v,
            "min_v": vmin,
            "max_v": vmax,
            "feasible": not reasons,
            "reason": "OK" if not reasons else "; ".join(reasons),
        }
        if design_energy_wh is not None and usable_fraction:
            strings = max(
                1, ceil(design_energy_wh / (ns * battery.derived_energy_wh * usable_fraction) - _EPS)
            )
            row["parallel_strings"] = strings
            row["total_modules"] = ns * strings
        rows.append(row)
    return rows


def _select_series(candidates: List[Dict[str, Any]], window: Tuple[float, float]) -> Tuple[int, str]:
    lo, hi = window
    feasible = [c for c in candidates if c["feasible"]]
    if feasible:
        best = min(feasible, key=lambda c: (c.get("total_modules", 0), c["series_modules"]))
        return best["series_modules"], (
            "Auto: feasible series count with the fewest total modules "
            f"({len(feasible)} feasible candidate(s))."
        )

    def violation(c: Dict[str, Any]) -> float:
        return max(lo - c["min_v"], 0.0) + max(c["max_v"] - hi, 0.0)

    best = min(candidates, key=lambda c: (violation(c), c["series_modules"]))
    return best["series_modules"], (
        "Auto: NO feasible series count exists; showing the least-violating candidate "
        "so the rest of the sizing can be inspected. This design FAILS the bus check."
    )


# --------------------------------------------------------------------------- chain helpers
def _build_stages(
    load: Load,
    inverter: Optional[Inverter],
    transformer: Optional[Transformer],
    dc_converter: Optional[DCConverter],
) -> List[Any]:
    """Stages ordered from the load towards the battery."""
    stages: List[Any] = []
    if load.is_ac:
        if inverter is None:
            raise ValueError("An inverter is required for an AC load.")
        if transformer is not None:
            stages.append(transformer)
        stages.append(inverter)
    else:
        if inverter is not None:
            raise ValueError("An inverter cannot supply a DC load.")
        if transformer is not None:
            raise ValueError("A transformer cannot be used on a DC load path.")
    if dc_converter is not None:
        stages.append(dc_converter)
    return stages


def _label(stage: Any) -> str:
    return f"{type(stage).__name__} '{stage.name}'"


def _match(name: str, actual: float, required: float, hint: str) -> Check:
    ok = abs(actual - required) <= VOLTAGE_MATCH_TOL * required + _EPS
    msg = f"{actual:g} V vs required {required:g} V"
    if not ok:
        msg += f" - outside +/-{VOLTAGE_MATCH_TOL:.0%}. {hint}"
    return Check(name, PASS if ok else FAIL, msg, actual, required)


def _within(name: str, value: float, window: Tuple[float, float]) -> Check:
    lo, hi = window
    ok = lo - _EPS <= value <= hi + _EPS
    msg = f"{value:g} V vs window {lo:g}-{hi:g} V" + ("" if ok else " - outside the window.")
    return Check(name, PASS if ok else FAIL, msg, value, window)


def _interface_checks(load: Load, stages: List[Any]) -> List[Check]:
    checks: List[Check] = []
    chain = [load] + list(stages)
    for a, b in zip(chain, chain[1:]):
        if isinstance(a, Load) and a.is_ac:
            if isinstance(b, Transformer):
                checks.append(_match(
                    "Transformer secondary vs load voltage", b.secondary_v, a.voltage_v,
                    "Choose a transformer with the correct secondary voltage."))
            elif isinstance(b, Inverter):
                checks.append(_match(
                    "Inverter AC output vs load voltage", b.ac_output_v, a.voltage_v,
                    "A transformer is required, or choose an inverter with the correct output."))
                if b.ac_phases is not None:
                    ok = b.ac_phases == a.phases
                    checks.append(Check(
                        "Inverter phases vs load phases", PASS if ok else FAIL,
                        f"inverter {b.ac_phases}-phase vs load {a.phases}-phase", b.ac_phases, a.phases))
        elif isinstance(a, Load):
            if isinstance(b, DCConverter):
                if a.dc_window is not None:
                    checks.append(_within("DC/DC output vs load voltage window", b.output_v, a.dc_window))
                else:
                    checks.append(_match(
                        "DC/DC output vs load voltage", b.output_v, a.voltage_v,
                        "Choose a converter with the correct output voltage."))
        elif isinstance(a, Transformer) and isinstance(b, Inverter):
            checks.append(_match(
                "Inverter AC output vs transformer primary", b.ac_output_v, a.primary_v,
                "Transformer primary must match the inverter output."))
        elif isinstance(a, Inverter) and isinstance(b, DCConverter):
            checks.append(_within("DC/DC output vs inverter DC window", b.output_v, a.dc_window))
    return checks


def _rating_check(name: str, used: float, rated: float, unit: str) -> Check:
    fraction = used / rated
    if fraction > 1 + _EPS:
        status, note = FAIL, "exceeds rating"
    elif fraction > RATING_WARN_FRACTION:
        status, note = WARNING, f"above {RATING_WARN_FRACTION:.0%} of rating"
    else:
        status, note = PASS, "within rating"
    return Check(name, status, f"{used:,.1f} {unit} of {rated:,.1f} {unit} ({fraction:.0%}) - {note}",
                 used, rated)


def _propagate(load: Load, stages: List[Any], log: AuditLog):
    """Walk from the load to the battery, applying each stage's efficiency."""
    checks: List[Check] = []
    rows: List[Dict[str, Any]] = []
    missing: List[str] = []
    power = load.real_power_w

    for stage in stages:
        out_w = power
        label = _label(stage)
        standby = 0.0
        try:
            eff, basis = stage.efficiency_at(out_w)
        except MissingDataError as exc:
            missing.extend(exc.items)
            continue

        if isinstance(stage, Inverter):
            if stage.standby_power_w is None:
                checks.append(Check(
                    f"{label} standby power", WARNING,
                    "Standby power not supplied - treated as 0 W. Enter 0 explicitly once "
                    "confirmed from the datasheet."))
            standby = stage.standby_power_w or 0.0
            in_w = out_w / eff + standby
            equation = "P_dc = P_ac / eta + P_standby"
            checks.append(_rating_check(f"{label} loading", out_w, stage.rated_power_w, "W"))
            if load.apparent_power_va > stage.rated_power_w + _EPS:
                checks.append(Check(
                    f"{label} apparent power", WARNING,
                    f"Load apparent power {load.apparent_power_va:,.0f} VA exceeds the "
                    f"{stage.rated_power_w:,.0f} rating. Confirm whether the rating is in W or VA."))
            rated_text = f"{stage.rated_power_w:,.0f} W"
        elif isinstance(stage, DCConverter):
            in_w = out_w / eff
            equation = "P_in = P_out / eta"
            checks.append(_rating_check(f"{label} loading", out_w, stage.rated_power_w, "W"))
            rated_text = f"{stage.rated_power_w:,.0f} W"
        else:  # Transformer
            in_w = out_w / eff
            equation = "P_primary = P_secondary / eta"
            checks.append(_rating_check(
                f"{label} loading", load.apparent_power_va, stage.rated_power_va, "VA"))
            rated_text = f"{stage.rated_power_va:,.0f} VA"

        if (
            isinstance(stage, (Inverter, DCConverter))
            and not stage.efficiency_curve
            and out_w / stage.rated_power_w < LOW_LOAD_EFF_FRACTION
        ):
            checks.append(Check(
                f"{label} part-load efficiency", WARNING,
                f"Operating at {out_w / stage.rated_power_w:.0%} of rating with a flat "
                "efficiency; real part-load efficiency is usually lower. Supply a curve."))

        rows.append({
            "stage": label,
            "output_w": out_w,
            "efficiency": eff,
            "efficiency_basis": basis,
            "standby_w": standby,
            "input_w": in_w,
            "rated": rated_text,
        })
        log.add(
            f"{label} power", equation,
            {"P_out_w": out_w, "eta": eff, "standby_w": standby}, in_w,
            source=getattr(stage, "source", None) or "user-supplied component data",
            status="CALCULATED", notes=basis,
        )
        power = in_w

    if missing:
        raise MissingDataError(missing)
    return rows, checks, power


def _bus_component(load: Load, stages: List[Any]) -> Tuple[Any, Optional[Tuple[float, float]]]:
    comp = stages[-1] if stages else load
    window = comp.dc_window
    return comp, window


# --------------------------------------------------------------------------- main entry point
def size_battery(
    load: Load,
    battery: BatteryModule,
    autonomy_hours: float,
    margin: float,
    eol_factors: EOLFactors,
    series_modules: Optional[int] = None,
    inverter: Optional[Inverter] = None,
    min_soc_fraction: float = 0.0,
    *,
    transformer: Optional[Transformer] = None,
    dc_converter: Optional[DCConverter] = None,
    parasitic_power_w: Optional[float] = None,
    assumptions_confirmed: bool = False,
) -> SizingResult:
    """Size the battery. series_modules=None selects the best feasible series count.

    Raises ValueError for invalid input and MissingDataError (a ValueError) when a
    value that must not be assumed (e.g. a component efficiency) was not supplied.
    """
    if autonomy_hours <= 0:
        raise ValueError("Autonomy must be > 0 hours.")
    if margin < 0:
        raise ValueError("Margin cannot be negative.")
    if not 0 <= min_soc_fraction < 1:
        raise ValueError("Minimum SOC fraction must be >= 0 and < 1.")
    if series_modules is not None and (
        isinstance(series_modules, bool) or not isinstance(series_modules, int) or series_modules < 1
    ):
        raise ValueError("Series modules must be an integer >= 1 (or None for automatic).")
    if parasitic_power_w is not None and parasitic_power_w < 0:
        raise ValueError("Parasitic power cannot be negative.")

    log = AuditLog()
    checks: List[Check] = []

    # 1. Architecture and power chain (load -> battery)
    stages = _build_stages(load, inverter, transformer, dc_converter)
    checks += _interface_checks(load, stages)
    rows, chain_checks, chain_power = _propagate(load, stages, log)
    checks += chain_checks

    if parasitic_power_w is None:
        parasitic = 0.0
        checks.append(Check(
            "Battery parasitic load", WARNING,
            "Not supplied - treated as 0 W. Self-discharge and BMS quiescent draw matter "
            "at long autonomy (every 10 W is ~6.7 kWh over 28 days)."))
    else:
        parasitic = parasitic_power_w
    log.add("Battery parasitic load", "P_parasitic = user input", {"P_w": parasitic}, parasitic,
            status="USER INPUT" if parasitic_power_w is not None else "ASSUMPTION",
            notes="BMS quiescent + self-discharge equivalent")

    battery_power = chain_power + parasitic
    log.add("Battery-side power", "P_batt = P_chain + P_parasitic",
            {"P_chain_w": chain_power, "P_parasitic_w": parasitic}, battery_power)

    # 2. Energy
    required_energy = battery_power * autonomy_hours
    design_energy = required_energy * (1 + margin)
    margin_energy = design_energy - required_energy
    log.add("Required energy", "E = P_batt * hours",
            {"P_batt_w": battery_power, "hours": autonomy_hours}, required_energy)
    log.add("Design energy", "E_design = E * (1 + margin)",
            {"E_wh": required_energy, "margin": margin}, design_energy, status="USER INPUT")

    usable_fraction = (1 - min_soc_fraction) * eol_factors.combined
    log.add("Usable fraction", "(1 - SOC_min) * f_soc * f_thermal * f_cyclic * f_calendar",
            {"min_soc": min_soc_fraction, "f_soc": eol_factors.soc, "f_thermal": eol_factors.thermal,
             "f_cyclic": eol_factors.cyclic, "f_calendar": eol_factors.calendar},
            usable_fraction, status="ASSUMPTION",
            notes="EOL factors are user inputs, not battery constants")

    # 3. Series count against the bus-side voltage window
    bus_comp, window = _bus_component(load, stages)
    bus_name = "load" if isinstance(bus_comp, Load) else _label(bus_comp)
    candidates = evaluate_series_candidates(battery, window, design_energy, usable_fraction)
    feasibility = series_feasibility(battery, window) if window else None

    if series_modules is None:
        if window is None:
            raise MissingDataError([
                "Allowable DC voltage window of the load (needed to select the series count "
                "for a direct DC connection)"
            ])
        ns, selection = _select_series(candidates, window)
    else:
        ns, selection = series_modules, "Manual series count."

    # 4. Parallel strings and pack
    string_energy = ns * battery.derived_energy_wh
    parallel = max(1, ceil(design_energy / (string_energy * usable_fraction) - _EPS))
    pack = battery.pack_from_modules(ns, parallel)
    eol_usable = pack["energy_wh_bol"] * usable_fraction
    log.add("Pack topology", "N_modules = Ns * Np; Np = ceil(E_design / (Ns*E_module*usable))",
            {"Ns": ns, "E_module_wh": battery.derived_energy_wh, "usable_fraction": usable_fraction},
            {"Np": parallel, "modules": pack["module_count"], "V_min": pack["minimum_voltage_v"],
             "V_nom": pack["nominal_voltage_v"], "V_max": pack["maximum_voltage_v"]},
            source=battery.source, notes=selection)

    # 5. Bus feasibility
    bus_feasible: Optional[bool]
    if window is None:
        bus_feasible = None
        checks.append(Check(
            "Battery bus vs load voltage window", MISSING,
            "The DC load's allowable voltage window was not supplied, so a direct connection "
            "cannot be verified."))
    else:
        lo, hi = window
        bus_feasible = (pack["minimum_voltage_v"] >= lo - _EPS
                        and pack["maximum_voltage_v"] <= hi + _EPS)
        msg = (f"Pack {pack['minimum_voltage_v']:.1f}-{pack['maximum_voltage_v']:.1f} V "
               f"(nominal {pack['nominal_voltage_v']:.1f} V) vs window {lo:g}-{hi:g} V")
        if bus_feasible:
            checks.append(Check(f"Battery bus vs {bus_name} DC window", PASS, msg))
        else:
            if not feasibility["feasible_possible"]:
                msg += (f". No integer series count can fit: the module voltage ratio is "
                        f"{feasibility['module_voltage_ratio']:.2f} (Vmax/Vmin) but the window ratio is "
                        f"only {feasibility['window_ratio']:.2f}. Use a wider window, a different "
                        "converter, or restrict the module voltage range via the BMS.")
            else:
                msg += (f". Feasible series counts for this window: "
                        f"{feasibility['ns_min']} to {feasibility['ns_max']}.")
            checks.append(Check(f"Battery bus vs {bus_name} DC window", FAIL, msg))

    # 6. Energy / current checks
    ok = eol_usable + _EPS >= design_energy
    checks.append(Check(
        "Usable EOL energy vs design energy", PASS if ok else FAIL,
        f"{eol_usable:,.0f} Wh usable vs {design_energy:,.0f} Wh required "
        f"(margin {margin:.0%} = {margin_energy:,.0f} Wh)", eol_usable, design_energy))

    worst_current = battery_power / pack["minimum_voltage_v"]
    per_string = worst_current / parallel
    c_rate = per_string / battery.capacity_ah
    log.add("Worst-case battery current", "I = P_batt / V_bus,min (constant-power load)",
            {"P_batt_w": battery_power, "V_min_v": pack["minimum_voltage_v"]}, worst_current,
            notes="Constant-power loads draw most current at the lowest bus voltage")
    if battery.max_discharge_current_a is None:
        checks.append(Check(
            "Module discharge current limit", MISSING,
            f"No max discharge current in the module record. Worst-case per-string current is "
            f"{per_string:.2f} A ({c_rate:.3f} C)."))
    else:
        checks.append(_rating_check(
            "Module discharge current", per_string, battery.max_discharge_current_a, "A"))

    if isinstance(bus_comp, Inverter) and bus_comp.max_dc_current_a is not None:
        checks.append(_rating_check(
            f"{_label(bus_comp)} DC input current",
            rows[-1]["input_w"] / pack["minimum_voltage_v"], bus_comp.max_dc_current_a, "A"))

    # 7. Data and assumption checks
    if battery.data_status != "VERIFIED":
        checks.append(Check(
            "Battery module data", WARNING,
            f"Module record is marked {battery.data_status}. Verify against the datasheet and "
            "set data_status to VERIFIED."))
    mismatch = battery.energy_mismatch_pct
    if mismatch is not None and abs(mismatch) > ENERGY_MISMATCH_WARN_PCT:
        checks.append(Check(
            "Stated vs derived module energy", WARNING,
            f"Stated {battery.energy_wh_stated:,.1f} Wh differs from V x Ah = "
            f"{battery.derived_energy_wh:,.1f} Wh by {mismatch:+.1f}%. Sizing uses V x Ah."))
    if eol_factors.thermal >= 1.0:
        checks.append(Check(
            "Thermal derating", WARNING,
            "Thermal factor is 1.0 - no low-temperature capacity loss applied. Confirm against "
            "the operating temperature."))
    if min_soc_fraction > 0 and eol_factors.soc < 1.0:
        checks.append(Check(
            "SOC double-counting", WARNING,
            "Both a minimum SOC and an SOC factor below 1.0 are applied. Confirm they "
            "represent different effects."))
    if not assumptions_confirmed:
        checks.append(Check(
            "Assumption review", WARNING,
            "Margin, minimum SOC, EOL factors, efficiency and standby values are user inputs "
            "that have not been confirmed."))

    status = worst_status(c.status for c in checks)
    return SizingResult(
        load_power_w=load.real_power_w,
        chain_power_w=chain_power,
        parasitic_power_w=parasitic,
        battery_power_w=battery_power,
        autonomy_hours=autonomy_hours,
        required_energy_wh=required_energy,
        margin=margin,
        margin_energy_wh=margin_energy,
        design_energy_wh=design_energy,
        usable_fraction=usable_fraction,
        series_modules=ns,
        parallel_strings=parallel,
        total_modules=pack["module_count"],
        nominal_bus_v=pack["nominal_voltage_v"],
        minimum_bus_v=pack["minimum_voltage_v"],
        maximum_bus_v=pack["maximum_voltage_v"],
        bol_energy_wh=pack["energy_wh_bol"],
        eol_usable_energy_wh=eol_usable,
        worst_case_current_a=worst_current,
        per_string_current_a=per_string,
        c_rate_per_string=c_rate,
        bus_feasible=bus_feasible,
        series_selection=selection,
        series_feasibility=feasibility,
        stages=rows,
        candidates=candidates,
        checks=checks,
        audit=log.records,
        limitations=list(LIMITATIONS),
        status=status,
    )

"""Battery System Engineering Tool - Streamlit interface (v1.1)."""
import json
from dataclasses import asdict
from pathlib import Path

import streamlit as st

from audit import FAIL, MISSING, PASS, WARNING, MissingDataError
from battery_model import BatteryModule
from power_components import DCConverter, Inverter, Load, Transformer
from sizing_engine import EOLFactors, size_battery

st.set_page_config(page_title="Battery System Engineering Tool", layout="wide")

DATA_DIR = Path(__file__).resolve().parent / "data" / "components"
ICON = {PASS: "✅", WARNING: "⚠️", MISSING: "❓", FAIL: "❌"}

# Illustrative worked example. Efficiency, standby and parasitic values are examples,
# not recommendations: replace them with datasheet values for a real project.
EXAMPLE = {
    "load_type": "AC", "load_power": 600.0, "load_voltage": 480.0, "pf": 0.90, "phases": 3,
    "load_vmin": None, "load_vmax": None,
    "autonomy_days": 28.0, "margin_pct": 10.0, "min_soc_pct": 10.0,
    "ns_mode": "Auto (best feasible)", "ns_manual": 4,
    "soc_factor": 1.0, "thermal_factor": 0.95, "cyclic_factor": 0.80, "calendar_factor": 1.0,
    "inv_name": "Example inverter (illustrative)", "inv_min": 30.0, "inv_max": 72.0,
    "inv_ac": 480.0, "inv_power": 1000.0, "inv_eff": 0.93, "inv_standby": None,
    "inv_phases": 3, "inv_imax": None, "inv_curve": "",
    "use_tr": False, "tr_primary": 400.0, "tr_secondary": 480.0, "tr_va": 1500.0, "tr_eff": None,
    "use_dc": False, "dc_in_min": 30.0, "dc_in_max": 72.0, "dc_out": 48.0,
    "dc_power": 1000.0, "dc_eff": None,
    "parasitic_w": None, "confirmed": False,
}
ASSUMPTION_KEYS = ["inv_eff", "inv_standby", "parasitic_w", "tr_eff", "dc_eff"]


def load_example():
    for key, value in EXAMPLE.items():
        st.session_state[key] = value


def clear_assumptions():
    for key in ASSUMPTION_KEYS:
        st.session_state[key] = None
    st.session_state["confirmed"] = False


def parse_curve(text):
    """Parse lines of 'load_fraction, efficiency' into a list of tuples (or None)."""
    points = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            fraction, eff = (float(x) for x in line.replace(";", ",").split(","))
        except ValueError:
            raise ValueError(f"Cannot parse efficiency curve line: '{line}' (use 'fraction, efficiency').")
        points.append((fraction, eff))
    return points or None


if "_initialised" not in st.session_state:
    load_example()
    st.session_state["_initialised"] = True

st.title("Battery System Engineering Tool")
st.caption(
    "v1.1 - transparent battery sizing and electrical architecture decision support. "
    "Calculation aid only; not certification or design approval."
)

# ------------------------------------------------------------------ sidebar
sb = st.sidebar
sb.button("Reset to worked example", on_click=load_example)
sb.button("Clear assumption inputs", on_click=clear_assumptions,
          help="Empties efficiency, standby and parasitic inputs so nothing is pre-assumed.")

sb.header("Battery module")
module_files = sorted(p for p in DATA_DIR.glob("*.json") if not p.name.startswith("_"))
if not module_files:
    st.error(f"No module records found in {DATA_DIR}.")
    st.stop()
module_file = sb.selectbox("Module record", module_files, format_func=lambda p: p.name)
try:
    module_data = json.loads(module_file.read_text(encoding="utf-8"))
    battery = BatteryModule.from_dict(module_data)
except Exception as exc:  # noqa: BLE001 - show any record problem to the user
    st.error(f"Could not load {module_file.name}: {exc}")
    st.stop()

sb.header("Load")
load_type = sb.selectbox("Load type", ["AC", "DC"], key="load_type")
load_power = sb.number_input("Load real power [W]", min_value=1.0, step=10.0, key="load_power")
load_voltage = sb.number_input("Load voltage [V] (AC: line-to-line)", min_value=1.0, step=1.0, key="load_voltage")
if load_type == "AC":
    pf = sb.number_input("Power factor", min_value=0.1, max_value=1.0, step=0.01, key="pf")
    phases = sb.selectbox("Phases", [1, 3], key="phases")
    load_vmin = load_vmax = None
else:
    pf, phases = 1.0, 1
    sb.caption("Allowable supply window of the DC load (needed to verify a direct connection).")
    load_vmin = sb.number_input("Load minimum voltage [V]", min_value=0.1, step=1.0, key="load_vmin")
    load_vmax = sb.number_input("Load maximum voltage [V]", min_value=0.1, step=1.0, key="load_vmax")

sb.header("Autonomy and margin")
autonomy_days = sb.number_input("Autonomy [days]", min_value=0.01, step=1.0, key="autonomy_days")
margin_pct = sb.number_input("Design margin [%]", min_value=0.0, step=1.0, key="margin_pct")
min_soc_pct = sb.number_input("Minimum SOC [%]", min_value=0.0, max_value=99.0, step=1.0, key="min_soc_pct")
parasitic_w = sb.number_input(
    "Battery parasitic load [W]", min_value=0.0, step=0.5, key="parasitic_w",
    help="BMS quiescent draw + self-discharge equivalent. Leave empty to see a WARNING.")

sb.header("Series topology")
ns_mode = sb.radio("Series count", ["Auto (best feasible)", "Manual"], key="ns_mode")
ns_manual = sb.number_input("Modules in series (manual)", min_value=1, step=1, key="ns_manual",
                            disabled=ns_mode != "Manual")

sb.header("End-of-life factors")
soc_factor = sb.number_input(
    "SOC factor", min_value=0.01, max_value=1.0, step=0.01, key="soc_factor",
    help="Extra SOC-related loss beyond the minimum-SOC floor (e.g. SOC estimation error). "
         "Do not repeat the minimum SOC here.")
thermal_factor = sb.number_input(
    "Thermal factor", min_value=0.01, max_value=1.0, step=0.01, key="thermal_factor",
    help="Capacity available at the operating temperature. 1.0 = no cold derating.")
cyclic_factor = sb.number_input(
    "Cyclic (lifetime) factor", min_value=0.01, max_value=1.0, step=0.01, key="cyclic_factor",
    help="End-of-life fade from lifetime cycling. Not a single-discharge effect.")
calendar_factor = sb.number_input(
    "Calendar (lifetime) factor", min_value=0.01, max_value=1.0, step=0.01, key="calendar_factor")

sb.header("Architecture")
inv_name = inv_min = inv_max = inv_ac = inv_power = inv_eff = inv_standby = None
inv_phases = inv_imax = None
inv_curve_text = ""
use_tr = use_dc = False
if load_type == "AC":
    sb.subheader("Inverter (required for AC)")
    inv_name = sb.text_input("Name", key="inv_name")
    inv_min = sb.number_input("DC input minimum [V]", min_value=0.1, step=1.0, key="inv_min")
    inv_max = sb.number_input("DC input maximum [V]", min_value=0.1, step=1.0, key="inv_max")
    inv_ac = sb.number_input("AC output [V]", min_value=0.1, step=1.0, key="inv_ac")
    inv_phases = sb.selectbox("AC output phases", [None, 1, 3], key="inv_phases",
                              format_func=lambda v: "not specified" if v is None else f"{v}-phase")
    inv_power = sb.number_input("Rated power [W]", min_value=1.0, step=10.0, key="inv_power")
    inv_eff = sb.number_input("Efficiency (0-1)", min_value=0.01, max_value=1.0, step=0.01, key="inv_eff",
                              help="Required. Not assumed. Leave empty to see MISSING.")
    inv_standby = sb.number_input("Standby power [W]", min_value=0.0, step=0.5, key="inv_standby",
                                  help="Enter 0 only if the datasheet says so. Empty = WARNING.")
    inv_imax = sb.number_input("Max DC input current [A] (optional)", min_value=0.1, step=1.0, key="inv_imax")
    inv_curve_text = sb.text_area(
        "Part-load efficiency curve (optional)", key="inv_curve",
        help="One 'load_fraction, efficiency' pair per line, e.g. 0.1, 0.85. Replaces the flat efficiency.")
    use_tr = sb.checkbox("Add transformer between inverter and load", key="use_tr")
    if use_tr:
        sb.subheader("Transformer")
        tr_primary = sb.number_input("Primary [V]", min_value=0.1, step=1.0, key="tr_primary")
        tr_secondary = sb.number_input("Secondary [V]", min_value=0.1, step=1.0, key="tr_secondary")
        tr_va = sb.number_input("Rated [VA]", min_value=1.0, step=10.0, key="tr_va")
        tr_eff = sb.number_input("Efficiency (0-1)", min_value=0.01, max_value=1.0, step=0.01, key="tr_eff")
use_dc = sb.checkbox("Add DC/DC converter on the battery side", key="use_dc")
if use_dc:
    sb.subheader("DC/DC converter")
    dc_in_min = sb.number_input("Input minimum [V]", min_value=0.1, step=1.0, key="dc_in_min")
    dc_in_max = sb.number_input("Input maximum [V]", min_value=0.1, step=1.0, key="dc_in_max")
    dc_out = sb.number_input("Output [V]", min_value=0.1, step=1.0, key="dc_out")
    dc_power = sb.number_input("Rated power [W]", min_value=1.0, step=10.0, key="dc_power")
    dc_eff = sb.number_input("Efficiency (0-1)", min_value=0.01, max_value=1.0, step=0.01, key="dc_eff")

sb.header("Review")
confirmed = sb.checkbox("I have reviewed all assumption inputs", key="confirmed",
                        help="Until ticked, the result carries a WARNING.")

# ------------------------------------------------------------------ banners
if battery.data_status != "VERIFIED":
    st.warning(
        f"Module record **{module_file.name}** is marked **{battery.data_status}**. "
        "Replace the values with datasheet data and set `data_status` to `VERIFIED`. "
        + (battery.notes or "")
    )
if battery.ignored_keys:
    st.info(f"Ignored unknown keys in {module_file.name}: {', '.join(battery.ignored_keys)}")

# ------------------------------------------------------------------ required-input check
required = {
    "Load power": load_power, "Load voltage": load_voltage, "Autonomy": autonomy_days,
    "Design margin": margin_pct, "Minimum SOC": min_soc_pct,
    "SOC factor": soc_factor, "Thermal factor": thermal_factor,
    "Cyclic factor": cyclic_factor, "Calendar factor": calendar_factor,
}
if load_type == "AC":
    required.update({"Power factor": pf, "Inverter DC minimum": inv_min, "Inverter DC maximum": inv_max,
                     "Inverter AC output": inv_ac, "Inverter rated power": inv_power})
    if use_tr:
        required.update({"Transformer primary": tr_primary, "Transformer secondary": tr_secondary,
                         "Transformer rating": tr_va})
if use_dc:
    required.update({"DC/DC input minimum": dc_in_min, "DC/DC input maximum": dc_in_max,
                     "DC/DC output": dc_out, "DC/DC rated power": dc_power})
blank = [label for label, value in required.items() if value is None]
if blank:
    st.warning("Enter a value for: " + ", ".join(blank))
    st.stop()

# ------------------------------------------------------------------ build and run
try:
    load = Load(load_type, load_power, load_voltage, pf, phases,
                voltage_min_v=load_vmin, voltage_max_v=load_vmax)
    factors = EOLFactors(soc_factor, thermal_factor, cyclic_factor, calendar_factor)
    inverter = transformer = converter = None
    if load_type == "AC":
        inverter = Inverter(
            inv_name or "Inverter", inv_min, inv_max, inv_ac, inv_power, inv_eff, inv_standby,
            ac_phases=inv_phases, max_dc_current_a=inv_imax, efficiency_curve=parse_curve(inv_curve_text))
        if use_tr:
            transformer = Transformer("Transformer", tr_primary, tr_secondary, tr_va, tr_eff)
    if use_dc:
        converter = DCConverter("DC/DC converter", dc_in_min, dc_in_max, dc_out, dc_power, dc_eff)

    result = size_battery(
        load=load,
        battery=battery,
        autonomy_hours=autonomy_days * 24.0,
        margin=margin_pct / 100.0,
        eol_factors=factors,
        series_modules=None if ns_mode.startswith("Auto") else int(ns_manual),
        inverter=inverter,
        min_soc_fraction=min_soc_pct / 100.0,
        transformer=transformer,
        dc_converter=converter,
        parasitic_power_w=parasitic_w,
        assumptions_confirmed=confirmed,
    )
except MissingDataError as exc:
    st.error("**MISSING required input - no result produced.** These values are never assumed:")
    for item in exc.items:
        st.write(f"- {item}")
    st.stop()
except ValueError as exc:
    st.error(f"Invalid input: {exc}")
    st.stop()

# ------------------------------------------------------------------ results
banner = {
    PASS: st.success, WARNING: st.warning, MISSING: st.warning, FAIL: st.error,
}[result.status]
counts = {s: sum(c.status == s for c in result.checks) for s in (PASS, WARNING, MISSING, FAIL)}
banner(
    f"**Overall status: {result.status}** - {counts[PASS]} pass, {counts[WARNING]} warning, "
    f"{counts[MISSING]} missing, {counts[FAIL]} fail. See the Checks tab."
)

cols = st.columns(5)
cols[0].metric("Battery-side power", f"{result.battery_power_w:,.1f} W")
cols[1].metric("Design energy", f"{result.design_energy_wh / 1000:,.1f} kWh")
cols[2].metric("Series x parallel", f"{result.series_modules} x {result.parallel_strings}")
cols[3].metric("Total modules", f"{result.total_modules:,}")
cols[4].metric("Nominal bus", f"{result.nominal_bus_v:,.1f} V")

tab_result, tab_series, tab_chain, tab_checks, tab_audit = st.tabs(
    ["Result", "Series search", "Power chain", "Checks", "Audit and data"])

with tab_result:
    left, right = st.columns(2)
    with left:
        st.subheader("Energy")
        st.write(f"Load power: **{result.load_power_w:,.1f} W**")
        st.write(f"Power drawn from battery bus by conversion chain: **{result.chain_power_w:,.1f} W**")
        st.write(f"Battery parasitic load: **{result.parasitic_power_w:,.1f} W**")
        st.write(f"Battery-side power: **{result.battery_power_w:,.1f} W**")
        st.write(f"Required energy ({result.autonomy_hours:,.0f} h): **{result.required_energy_wh:,.0f} Wh**")
        st.write(f"Design margin ({result.margin:.0%}): **+{result.margin_energy_wh:,.0f} Wh**")
        st.write(f"Design energy: **{result.design_energy_wh:,.0f} Wh**")
        st.write(f"Usable fraction (min SOC x EOL factors): **{result.usable_fraction:.3f}**")
    with right:
        st.subheader("Battery bus and sizing")
        st.write(f"Series x parallel: **{result.series_modules} x {result.parallel_strings}** "
                 f"= **{result.total_modules:,}** modules")
        st.write(f"Operating envelope: **{result.minimum_bus_v:.1f} V** to **{result.maximum_bus_v:.1f} V** "
                 f"(nominal {result.nominal_bus_v:.1f} V)")
        st.write(f"BOL nominal energy: **{result.bol_energy_wh:,.0f} Wh**")
        st.write(f"EOL usable energy: **{result.eol_usable_energy_wh:,.0f} Wh**")
        st.write(f"Worst-case current (at minimum bus voltage): **{result.worst_case_current_a:,.2f} A**")
        st.write(f"Per string: **{result.per_string_current_a:,.3f} A** "
                 f"({result.c_rate_per_string:.4f} C)")
        st.caption(result.series_selection)
    st.subheader("Limitations of this calculation")
    for item in result.limitations:
        st.write(f"- {item}")

with tab_series:
    st.write("Each integer series count is tested against the full module voltage envelope.")
    if result.series_feasibility:
        info = result.series_feasibility
        if info["feasible_possible"]:
            st.success(f"Feasible series counts: {info['ns_min']} to {info['ns_max']}.")
        else:
            st.error(
                f"No integer series count can fit this window. Module Vmax/Vmin = "
                f"{info['module_voltage_ratio']:.2f}, window max/min = {info['window_ratio']:.2f}. "
                "The window must be at least as wide as the module's voltage ratio.")
    if result.candidates:
        st.dataframe([
            {"Series": c["series_modules"], "Nominal [V]": round(c["nominal_v"], 1),
             "Min [V]": round(c["min_v"], 1), "Max [V]": round(c["max_v"], 1),
             "Feasible": "PASS" if c["feasible"] else "FAIL",
             "Parallel strings": c.get("parallel_strings"), "Total modules": c.get("total_modules"),
             "Reason": c["reason"]} for c in result.candidates])
    else:
        st.info("No voltage window available, so no candidates can be evaluated.")

with tab_chain:
    st.write("Power is propagated from the load towards the battery.")
    if result.stages:
        st.dataframe([
            {"Stage": s["stage"], "Output [W]": round(s["output_w"], 2),
             "Efficiency": round(s["efficiency"], 4), "Basis": s["efficiency_basis"],
             "Standby [W]": s["standby_w"], "Input [W]": round(s["input_w"], 2),
             "Rating": s["rated"]} for s in result.stages])
    else:
        st.info("Direct connection: no conversion stages.")

with tab_checks:
    st.dataframe([
        {"": ICON[c.status], "Check": c.name, "Status": c.status, "Detail": c.message}
        for c in sorted(result.checks, key=lambda c: [FAIL, MISSING, WARNING, PASS].index(c.status))
    ])

with tab_audit:
    st.subheader("Battery data quality")
    for key, status in battery.data_quality().items():
        icon = "✓" if status == "KNOWN" else ("↳" if status == "DERIVED" else "⚠")
        st.write(f"{icon} {key}: {status}")
    st.caption("OCV/SOC, R0/RC and thermal data are stored for later versions and are not used in v1.")
    st.subheader("Calculation audit trail")
    st.dataframe([
        {"Calculation": r["calculation"], "Equation": r["equation"], "Status": r["status"],
         "Result": json.dumps(r["result"], default=str), "Notes": r["notes"]}
        for r in result.audit])
    report = {"module": asdict(battery), "result": asdict(result)}
    st.download_button("Download full report (JSON)", data=json.dumps(report, indent=2, default=str),
                       file_name="battery_sizing_report.json", mime="application/json")
    with st.expander("Raw module record"):
        st.json(module_data)

import json
from pathlib import Path
import streamlit as st
from battery_model import BatteryModule
from power_components import Load, Inverter
from sizing_engine import EOLFactors, size_battery

st.set_page_config(page_title="Battery System Engineering Tool", layout="wide")
st.title("Battery System Engineering Tool")
st.caption("v1 — transparent battery sizing and electrical architecture decision support")

data_path = Path("data/components/vda355_4p3s.json")
data = json.loads(data_path.read_text())

battery = BatteryModule(**data)

st.sidebar.header("Project Inputs")

load_type = st.sidebar.selectbox("Load type", ["AC", "DC"])
load_power = st.sidebar.number_input("Client load power [W]", min_value=1.0, value=600.0)
load_voltage = st.sidebar.number_input("Client load voltage [V]", min_value=1.0, value=480.0)
pf = st.sidebar.number_input("Power factor", min_value=0.1, max_value=1.0, value=0.90)
phases = st.sidebar.selectbox("Phases", [1, 3], index=1 if load_type == "AC" else 0)

autonomy_days = st.sidebar.number_input("Autonomy [days]", min_value=0.1, value=28.0)
margin_pct = st.sidebar.number_input("Design margin [%]", min_value=0.0, value=10.0)
min_soc_pct = st.sidebar.number_input("Minimum SOC [%]", min_value=0.0, max_value=99.0, value=10.0)

st.sidebar.header("Battery Topology")
series_modules = st.sidebar.number_input("Modules in series", min_value=1, value=4, step=1)

st.sidebar.header("EOL Factors")
soc_factor = st.sidebar.number_input("SOC factor", min_value=0.01, max_value=1.0, value=1.0)
thermal_factor = st.sidebar.number_input("Thermal factor", min_value=0.01, max_value=1.0, value=1.0)
cyclic_factor = st.sidebar.number_input("Cyclic factor", min_value=0.01, max_value=1.0, value=0.8)
calendar_factor = st.sidebar.number_input("Calendar factor", min_value=0.01, max_value=1.0, value=1.0)

inverter = None
if load_type == "AC":
    st.sidebar.header("Inverter")
    inv_name = st.sidebar.text_input("Inverter", "User-selected inverter")
    inv_min = st.sidebar.number_input("Inverter DC minimum [V]", min_value=0.1, value=40.0)
    inv_max = st.sidebar.number_input("Inverter DC maximum [V]", min_value=0.1, value=60.0)
    inv_ac = st.sidebar.number_input("Inverter AC output [V]", min_value=0.1, value=480.0)
    inv_power = st.sidebar.number_input("Inverter rated power [W]", min_value=1.0, value=1000.0)
    inv_eff = st.sidebar.number_input("Inverter efficiency", min_value=0.01, max_value=1.0, value=0.93)
    inv_standby = st.sidebar.number_input("Inverter standby power [W]", min_value=0.0, value=0.0)
    inverter = Inverter(inv_name, inv_min, inv_max, inv_ac, inv_power, inv_eff, inv_standby)

load = Load(load_type, load_power, load_voltage, pf, phases)
factors = EOLFactors(soc_factor, thermal_factor, cyclic_factor, calendar_factor)

result = size_battery(
    load=load,
    battery=battery,
    autonomy_hours=autonomy_days * 24,
    margin=margin_pct / 100,
    eol_factors=factors,
    series_modules=int(series_modules),
    inverter=inverter,
    min_soc_fraction=min_soc_pct / 100,
)

st.subheader("Engineering Result")
cols = st.columns(4)
cols[0].metric("Battery-side power", f"{result.battery_power_w:,.1f} W")
cols[1].metric("Design energy", f"{result.design_energy_wh:,.0f} Wh")
cols[2].metric("Nominal bus", f"{result.nominal_bus_v:,.1f} V")
cols[3].metric("Total modules", f"{result.total_modules}")

st.subheader("Battery Bus")
st.write(
    f"**Operating range:** {result.minimum_bus_v:.1f} V to "
    f"{result.maximum_bus_v:.1f} V"
)

if result.inverter_feasible is True:
    st.success("PASS — battery voltage range is within the specified inverter DC input range.")
elif result.inverter_feasible is False:
    st.error("FAIL — battery voltage range is not compatible with the specified inverter DC input range.")

st.subheader("Sizing")
st.write(f"Series modules: **{result.series_modules}**")
st.write(f"Parallel strings: **{result.parallel_strings}**")
st.write(f"Total modules: **{result.total_modules}**")
st.write(f"BOL nominal energy: **{result.bol_energy_wh:,.0f} Wh**")
st.write(f"EOL usable energy after explicit factors: **{result.eol_usable_energy_wh:,.0f} Wh**")

st.subheader("Battery Data Quality")
for key, status in battery.data_quality().items():
    if status == "KNOWN":
        st.write(f"✓ {key}: {status}")
    elif status == "DERIVED":
        st.write(f"↳ {key}: {status}")
    else:
        st.write(f"⚠ {key}: {status}")

st.subheader("Current Engineering Basis")
st.info(
    "v1 uses constant load power. Duty cycle is intentionally outside this calculation. "
    "AC loads require an inverter. The complete battery voltage range is checked against "
    "the inverter DC input range. Missing battery physics data is not silently estimated."
)

with st.expander("Raw VDA355 component data"):
    st.json(data)

from dataclasses import dataclass
from math import ceil
from battery_model import BatteryModule
from power_components import Load, Inverter

@dataclass
class EOLFactors:
    soc: float = 1.0
    thermal: float = 1.0
    cyclic: float = 1.0
    calendar: float = 1.0

    @property
    def combined(self) -> float:
        return self.soc * self.thermal * self.cyclic * self.calendar

@dataclass
class SizingResult:
    load_power_w: float
    battery_power_w: float
    autonomy_hours: float
    required_energy_wh: float
    design_energy_wh: float
    series_modules: int
    parallel_strings: int
    total_modules: int
    nominal_bus_v: float
    minimum_bus_v: float
    maximum_bus_v: float
    bol_energy_wh: float
    eol_usable_energy_wh: float
    margin: float
    inverter_feasible: bool | None
    status: str

def size_battery(
    load: Load,
    battery: BatteryModule,
    autonomy_hours: float,
    margin: float,
    eol_factors: EOLFactors,
    series_modules: int,
    inverter: Inverter | None = None,
    min_soc_fraction: float = 0.0,
) -> SizingResult:

    if autonomy_hours <= 0:
        raise ValueError("Autonomy must be > 0 hours.")
    if margin < 0:
        raise ValueError("Margin cannot be negative.")
    if not 0 <= min_soc_fraction < 1:
        raise ValueError("Minimum SOC fraction must be >= 0 and < 1.")

    if load.load_type.upper() == "AC":
        if inverter is None:
            raise ValueError("An inverter is required for an AC load.")
        battery_power = inverter.battery_power_required(load.real_power_w)
    else:
        battery_power = load.real_power_w

    required_energy = battery_power * autonomy_hours
    design_energy = required_energy * (1 + margin)

    # Approximate usable EOL energy from nominal pack energy.
    # Minimum SOC is an additional explicit usable-energy constraint.
    usable_fraction = (1 - min_soc_fraction) * eol_factors.combined

    # Parallel strings required from BOL nominal energy.
    module_string_energy = series_modules * battery.derived_energy_wh
    parallel_strings = max(1, ceil(design_energy / (module_string_energy * usable_fraction)))

    pack = battery.pack_from_modules(series_modules, parallel_strings)
    eol_usable = pack["energy_wh_bol"] * usable_fraction

    inverter_feasible = None
    if inverter is not None:
        inverter_feasible = inverter.accepts_bus(
            pack["minimum_voltage_v"], pack["maximum_voltage_v"]
        )

    status = "PASS"
    if inverter_feasible is False:
        status = "FAIL"

    return SizingResult(
        load_power_w=load.real_power_w,
        battery_power_w=battery_power,
        autonomy_hours=autonomy_hours,
        required_energy_wh=required_energy,
        design_energy_wh=design_energy,
        series_modules=series_modules,
        parallel_strings=parallel_strings,
        total_modules=pack["module_count"],
        nominal_bus_v=pack["nominal_voltage_v"],
        minimum_bus_v=pack["minimum_voltage_v"],
        maximum_bus_v=pack["maximum_voltage_v"],
        bol_energy_wh=pack["energy_wh_bol"],
        eol_usable_energy_wh=eol_usable,
        margin=margin,
        inverter_feasible=inverter_feasible,
        status=status,
    )

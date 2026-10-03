from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class BatteryModule:
    manufacturer: str
    model: str
    chemistry: str
    series_cells: int
    parallel_cells: int
    nominal_voltage_v: float
    capacity_ah: float
    voltage_min_v: float
    voltage_max_v: float
    mass_kg: Optional[float] = None
    energy_wh_stated: Optional[float] = None
    internal_resistance_mohm: Optional[float] = None
    source: Optional[str] = None
    notes: str = ""

    @property
    def cell_count(self) -> int:
        return self.series_cells * self.parallel_cells

    @property
    def derived_energy_wh(self) -> float:
        return self.nominal_voltage_v * self.capacity_ah

    def pack_from_modules(self, series_modules: int, parallel_strings: int) -> Dict[str, float]:
        if series_modules < 1 or parallel_strings < 1:
            raise ValueError("Series modules and parallel strings must be >= 1.")
        nominal_v = series_modules * self.nominal_voltage_v
        min_v = series_modules * self.voltage_min_v
        max_v = series_modules * self.voltage_max_v
        capacity_ah = parallel_strings * self.capacity_ah
        energy_wh = nominal_v * capacity_ah
        module_count = series_modules * parallel_strings
        return {
            "series_modules": series_modules,
            "parallel_strings": parallel_strings,
            "module_count": module_count,
            "nominal_voltage_v": nominal_v,
            "minimum_voltage_v": min_v,
            "maximum_voltage_v": max_v,
            "capacity_ah": capacity_ah,
            "energy_wh_bol": energy_wh,
        }

    def data_quality(self) -> Dict[str, str]:
        checks = {
            "nominal_voltage": "KNOWN",
            "capacity": "KNOWN",
            "voltage_min": "KNOWN",
            "voltage_max": "KNOWN",
            "energy": "KNOWN" if self.energy_wh_stated is not None else "DERIVED",
            "internal_resistance": "KNOWN" if self.internal_resistance_mohm is not None else "MISSING",
            "ocv_soc": "MISSING",
            "r0_soc_temperature": "MISSING",
            "r1_c1_soc_temperature": "MISSING",
            "thermal_capacity": "MISSING",
            "thermal_resistance": "MISSING",
        }
        return checks

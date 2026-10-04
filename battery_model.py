"""Battery module record and series/parallel pack arithmetic."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Optional

VALID_DATA_STATUS = {"VERIFIED", "UNVERIFIED", "PLACEHOLDER"}


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
    max_discharge_current_a: Optional[float] = None
    # Stored for later versions (v3/v4). Not used by the v1 calculation.
    ocv_soc: Optional[list] = None
    r0_soc_temperature: Optional[Any] = None
    r1_c1_soc_temperature: Optional[Any] = None
    thermal_capacity_j_per_k: Optional[float] = None
    thermal_resistance_k_per_w: Optional[float] = None
    source: Optional[str] = None
    # VERIFIED    -> checked against a manufacturer datasheet by the user
    # UNVERIFIED  -> default; raises a WARNING in every result
    # PLACEHOLDER -> illustrative numbers; raises a WARNING in every result
    data_status: str = "UNVERIFIED"
    notes: str = ""
    ignored_keys: List[str] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.series_cells < 1 or self.parallel_cells < 1:
            raise ValueError("Series and parallel cell counts must be >= 1.")
        for name in ("nominal_voltage_v", "capacity_ah", "voltage_min_v", "voltage_max_v"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0.")
        if not self.voltage_min_v < self.nominal_voltage_v < self.voltage_max_v:
            raise ValueError("Module voltages must satisfy min < nominal < max.")
        for name in (
            "mass_kg",
            "energy_wh_stated",
            "internal_resistance_mohm",
            "max_discharge_current_a",
        ):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be > 0 when supplied.")
        if self.data_status not in VALID_DATA_STATUS:
            raise ValueError(f"data_status must be one of {sorted(VALID_DATA_STATUS)}.")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BatteryModule":
        """Build a module from a JSON record; unknown keys are kept visible, not fatal."""
        known = {f.name for f in fields(cls) if f.init}
        module = cls(**{k: v for k, v in data.items() if k in known})
        module.ignored_keys = sorted(set(data) - known)
        return module

    @property
    def cell_count(self) -> int:
        return self.series_cells * self.parallel_cells

    @property
    def derived_energy_wh(self) -> float:
        """Nominal module energy = nominal voltage x capacity (used for sizing)."""
        return self.nominal_voltage_v * self.capacity_ah

    @property
    def energy_mismatch_pct(self) -> Optional[float]:
        """Percent difference between stated and derived energy (None if not stated)."""
        if self.energy_wh_stated is None:
            return None
        return 100.0 * (self.energy_wh_stated - self.derived_energy_wh) / self.derived_energy_wh

    def pack_from_modules(self, series_modules: int, parallel_strings: int) -> Dict[str, float]:
        if series_modules < 1 or parallel_strings < 1:
            raise ValueError("Series modules and parallel strings must be >= 1.")
        nominal_v = series_modules * self.nominal_voltage_v
        min_v = series_modules * self.voltage_min_v
        max_v = series_modules * self.voltage_max_v
        capacity_ah = parallel_strings * self.capacity_ah
        return {
            "series_modules": series_modules,
            "parallel_strings": parallel_strings,
            "module_count": series_modules * parallel_strings,
            "nominal_voltage_v": nominal_v,
            "minimum_voltage_v": min_v,
            "maximum_voltage_v": max_v,
            "capacity_ah": capacity_ah,
            "energy_wh_bol": nominal_v * capacity_ah,
        }

    def data_quality(self) -> Dict[str, str]:
        """Status of each data item, computed from what the record actually contains."""

        def known(value: Any) -> str:
            return "MISSING" if value is None else "KNOWN"

        return {
            "nominal_voltage": "KNOWN",
            "capacity": "KNOWN",
            "voltage_min": "KNOWN",
            "voltage_max": "KNOWN",
            "energy": "DERIVED" if self.energy_wh_stated is None else "KNOWN",
            "max_discharge_current": known(self.max_discharge_current_a),
            "internal_resistance": known(self.internal_resistance_mohm),
            "ocv_soc": known(self.ocv_soc),
            "r0_soc_temperature": known(self.r0_soc_temperature),
            "r1_c1_soc_temperature": known(self.r1_c1_soc_temperature),
            "thermal_capacity": known(self.thermal_capacity_j_per_k),
            "thermal_resistance": known(self.thermal_resistance_k_per_w),
        }

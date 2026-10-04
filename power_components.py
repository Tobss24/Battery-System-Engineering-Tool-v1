"""Load and power-conversion components (inverter, DC/DC converter, transformer)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from audit import MissingDataError

_EPS = 1e-9


def _validate_efficiency(value: Optional[float], label: str) -> None:
    if value is not None and not 0 < value <= 1:
        raise ValueError(f"{label}: efficiency must be > 0 and <= 1.")


def _validate_curve(curve: Optional[Sequence[Tuple[float, float]]], label: str) -> None:
    if curve is None:
        return
    if len(curve) < 2:
        raise ValueError(f"{label}: an efficiency curve needs at least two points.")
    for fraction, eff in curve:
        if fraction < 0:
            raise ValueError(f"{label}: curve load fraction must be >= 0.")
        if not 0 < eff <= 1:
            raise ValueError(f"{label}: curve efficiency must be > 0 and <= 1.")


def _interp(x: float, points: Sequence[Tuple[float, float]]) -> float:
    pts = sorted(points)
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]  # unreachable; keeps type-checkers happy


def _efficiency_at(
    label: str,
    flat: Optional[float],
    curve: Optional[Sequence[Tuple[float, float]]],
    rated_w: float,
    output_w: float,
) -> Tuple[float, str]:
    """Return (efficiency, basis). Never invents a value: raises if none was supplied."""
    if curve:
        fraction = output_w / rated_w
        return _interp(fraction, curve), f"efficiency curve at {fraction:.0%} load"
    if flat is None:
        raise MissingDataError([f"{label}: efficiency"])
    return flat, "flat (single-point) efficiency"


@dataclass
class Load:
    load_type: str  # "AC" or "DC"
    real_power_w: float
    voltage_v: float
    power_factor: float = 1.0
    phases: int = 1
    frequency_hz: Optional[float] = None
    name: str = "Client Load"
    # Allowable supply window for a DC load (required to verify a direct DC connection).
    voltage_min_v: Optional[float] = None
    voltage_max_v: Optional[float] = None

    def __post_init__(self) -> None:
        self.load_type = str(self.load_type).upper()
        if self.load_type not in {"AC", "DC"}:
            raise ValueError("load_type must be AC or DC.")
        if self.real_power_w <= 0:
            raise ValueError("Load power must be > 0 W.")
        if self.voltage_v <= 0:
            raise ValueError("Load voltage must be > 0 V.")
        if self.load_type == "AC":
            if not 0 < self.power_factor <= 1:
                raise ValueError("Power factor must be > 0 and <= 1.")
            if self.phases not in (1, 3):
                raise ValueError("Phases must be 1 or 3.")
        else:
            # Power factor and phases have no meaning for a DC load.
            self.power_factor = 1.0
            self.phases = 1
        if (self.voltage_min_v is None) != (self.voltage_max_v is None):
            raise ValueError("Supply both the minimum and maximum load voltage, or neither.")
        if self.voltage_min_v is not None:
            if self.voltage_min_v <= 0 or self.voltage_min_v >= self.voltage_max_v:
                raise ValueError("Load voltage window must satisfy 0 < min < max.")

    @property
    def is_ac(self) -> bool:
        return self.load_type == "AC"

    @property
    def dc_window(self) -> Optional[Tuple[float, float]]:
        if self.voltage_min_v is None:
            return None
        return (self.voltage_min_v, self.voltage_max_v)

    @property
    def apparent_power_va(self) -> float:
        return self.real_power_w / self.power_factor if self.is_ac else self.real_power_w

    @property
    def current_a(self) -> float:
        if self.is_ac and self.phases == 3:
            return self.real_power_w / ((3 ** 0.5) * self.voltage_v * self.power_factor)
        return self.real_power_w / (self.voltage_v * self.power_factor)


@dataclass
class Inverter:
    name: str
    dc_min_v: float
    dc_max_v: float
    ac_output_v: float
    rated_power_w: float
    efficiency: Optional[float]  # None = not supplied -> MissingDataError at calculation
    standby_power_w: Optional[float] = None  # None = not supplied -> WARNING, treated as 0 W
    source: Optional[str] = None
    ac_phases: Optional[int] = None
    max_dc_current_a: Optional[float] = None
    efficiency_curve: Optional[List[Tuple[float, float]]] = None  # (load fraction, efficiency)

    def __post_init__(self) -> None:
        if self.dc_min_v <= 0 or self.dc_min_v >= self.dc_max_v:
            raise ValueError("Inverter DC window must satisfy 0 < min < max.")
        if self.ac_output_v <= 0 or self.rated_power_w <= 0:
            raise ValueError("Inverter AC output voltage and rated power must be > 0.")
        if self.standby_power_w is not None and self.standby_power_w < 0:
            raise ValueError("Inverter standby power cannot be negative.")
        if self.ac_phases not in (None, 1, 3):
            raise ValueError("Inverter AC phases must be 1, 3 or unspecified.")
        if self.max_dc_current_a is not None and self.max_dc_current_a <= 0:
            raise ValueError("Inverter maximum DC current must be > 0 when supplied.")
        _validate_efficiency(self.efficiency, self.name)
        _validate_curve(self.efficiency_curve, self.name)

    @property
    def dc_window(self) -> Tuple[float, float]:
        return (self.dc_min_v, self.dc_max_v)

    def efficiency_at(self, ac_output_w: float) -> Tuple[float, str]:
        return _efficiency_at(
            f"Inverter '{self.name}'", self.efficiency, self.efficiency_curve,
            self.rated_power_w, ac_output_w,
        )

    def battery_power_required(self, ac_load_w: float) -> float:
        eff, _ = self.efficiency_at(ac_load_w)
        return ac_load_w / eff + (self.standby_power_w or 0.0)

    def accepts_bus(self, minimum_v: float, maximum_v: float) -> bool:
        return minimum_v >= self.dc_min_v - _EPS and maximum_v <= self.dc_max_v + _EPS


@dataclass
class DCConverter:
    name: str
    input_min_v: float
    input_max_v: float
    output_v: float
    rated_power_w: float
    efficiency: Optional[float]
    source: Optional[str] = None
    efficiency_curve: Optional[List[Tuple[float, float]]] = None

    def __post_init__(self) -> None:
        if self.input_min_v <= 0 or self.input_min_v >= self.input_max_v:
            raise ValueError("Converter input window must satisfy 0 < min < max.")
        if self.output_v <= 0 or self.rated_power_w <= 0:
            raise ValueError("Converter output voltage and rated power must be > 0.")
        _validate_efficiency(self.efficiency, self.name)
        _validate_curve(self.efficiency_curve, self.name)

    @property
    def dc_window(self) -> Tuple[float, float]:
        return (self.input_min_v, self.input_max_v)

    def efficiency_at(self, output_w: float) -> Tuple[float, str]:
        return _efficiency_at(
            f"DC/DC converter '{self.name}'", self.efficiency, self.efficiency_curve,
            self.rated_power_w, output_w,
        )

    def input_power_required(self, output_power_w: float) -> float:
        eff, _ = self.efficiency_at(output_power_w)
        return output_power_w / eff

    def accepts_input(self, minimum_v: float, maximum_v: float) -> bool:
        return minimum_v >= self.input_min_v - _EPS and maximum_v <= self.input_max_v + _EPS


@dataclass
class Transformer:
    name: str
    primary_v: float
    secondary_v: float
    rated_power_va: float
    efficiency: Optional[float]
    source: Optional[str] = None

    def __post_init__(self) -> None:
        if min(self.primary_v, self.secondary_v, self.rated_power_va) <= 0:
            raise ValueError("Transformer voltages and rating must be > 0.")
        _validate_efficiency(self.efficiency, self.name)

    @property
    def voltage_ratio(self) -> float:
        """V_secondary / V_primary = N_secondary / N_primary."""
        return self.secondary_v / self.primary_v

    def efficiency_at(self, secondary_real_power_w: float) -> Tuple[float, str]:
        if self.efficiency is None:
            raise MissingDataError([f"Transformer '{self.name}': efficiency"])
        return self.efficiency, "flat (single-point) efficiency"

    def primary_power_required(self, secondary_real_power_w: float) -> float:
        eff, _ = self.efficiency_at(secondary_real_power_w)
        return secondary_real_power_w / eff

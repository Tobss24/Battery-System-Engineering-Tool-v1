from dataclasses import dataclass
from typing import Optional

@dataclass
class Load:
    load_type: str  # "AC" or "DC"
    real_power_w: float
    voltage_v: float
    power_factor: float = 1.0
    phases: int = 1
    frequency_hz: Optional[float] = None
    name: str = "Client Load"

    def __post_init__(self):
        if self.real_power_w <= 0:
            raise ValueError("Load power must be > 0 W.")
        if self.voltage_v <= 0:
            raise ValueError("Load voltage must be > 0 V.")
        if not 0 < self.power_factor <= 1:
            raise ValueError("Power factor must be > 0 and <= 1.")
        if self.load_type.upper() not in {"AC", "DC"}:
            raise ValueError("load_type must be AC or DC.")

    @property
    def apparent_power_va(self) -> float:
        if self.load_type.upper() == "DC":
            return self.real_power_w
        return self.real_power_w / self.power_factor

    @property
    def current_a(self) -> float:
        if self.load_type.upper() == "AC" and self.phases == 3:
            return self.real_power_w / ((3 ** 0.5) * self.voltage_v * self.power_factor)
        return self.real_power_w / (self.voltage_v * (self.power_factor if self.load_type.upper() == "AC" else 1.0))

@dataclass
class Inverter:
    name: str
    dc_min_v: float
    dc_max_v: float
    ac_output_v: float
    rated_power_w: float
    efficiency: float
    standby_power_w: float = 0.0
    source: Optional[str] = None

    def battery_power_required(self, ac_load_w: float) -> float:
        if not 0 < self.efficiency <= 1:
            raise ValueError("Efficiency must be > 0 and <= 1.")
        return ac_load_w / self.efficiency + self.standby_power_w

    def accepts_bus(self, minimum_v: float, maximum_v: float) -> bool:
        return minimum_v >= self.dc_min_v and maximum_v <= self.dc_max_v

@dataclass
class DCConverter:
    name: str
    input_min_v: float
    input_max_v: float
    output_v: float
    rated_power_w: float
    efficiency: float
    source: Optional[str] = None

    def input_power_required(self, output_power_w: float) -> float:
        return output_power_w / self.efficiency

    def accepts_input(self, minimum_v: float, maximum_v: float) -> bool:
        return minimum_v >= self.input_min_v and maximum_v <= self.input_max_v

@dataclass
class Transformer:
    name: str
    primary_v: float
    secondary_v: float
    rated_power_va: float
    efficiency: float
    source: Optional[str] = None

    def primary_power_required(self, secondary_real_power_w: float) -> float:
        return secondary_real_power_w / self.efficiency

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional

from ..engine.cave_model import CaveSystem


@dataclass
class DiveGasConfig:
    tank_volume_liters: float = 12.0
    tank_pressure_bar: float = 200.0
    num_tanks: int = 2
    sac_rate_lmin: float = 20.0
    reserve_fraction: float = 1.0 / 3.0

    @property
    def total_gas_liters(self) -> float:
        return self.tank_volume_liters * self.tank_pressure_bar * self.num_tanks

    def usable_gas_liters(self) -> float:
        return self.total_gas_liters * (1.0 - self.reserve_fraction)

    def turn_pressure_bar(self) -> float:
        return self.tank_pressure_bar * self.reserve_fraction

    def max_bottom_time_at_depth(self, depth_m: float) -> float:
        ata = 1.0 + depth_m / 10.0
        consumption_lmin = self.sac_rate_lmin * ata
        usable = self.usable_gas_liters()
        return usable / consumption_lmin / 2.0

    def penetration_distance_m(self, depth_m: float, swim_speed_mmin: float = 15.0) -> float:
        time = self.max_bottom_time_at_depth(depth_m)
        return time * swim_speed_mmin


@dataclass
class SARBriefing:
    cave_name: str
    missing_since: str = ""
    diver_name: str = "Unknown"
    diver_certification: str = "Unknown"
    last_known_position: str = "Entrance"
    gas_config: DiveGasConfig = field(default_factory=DiveGasConfig)
    water_temp_c: float = 20.0
    visibility_m: float = 5.0

    def generate_gas_summary(self) -> str:
        lines = [
            "═══ GAS MANAGEMENT (SAR Team) ═══",
            f"  Tanks:          {self.gas_config.num_tanks} × {self.gas_config.tank_volume_liters}L "
            f"@ {self.gas_config.tank_pressure_bar} bar",
            f"  Total gas:      {self.gas_config.total_gas_liters:,.0f} L",
            f"  Usable (⅔):     {self.gas_config.usable_gas_liters():,.0f} L",
            f"  Turn pressure:  {self.gas_config.turn_pressure_bar():.0f} bar",
            "",
            "  Penetration limits by depth:",
        ]
        for depth in (10, 20, 30, 40, 60):
            penet = self.gas_config.penetration_distance_m(depth)
            btime = self.gas_config.max_bottom_time_at_depth(depth)
            lines.append(
                f"    {depth:>3}m depth → {penet:>5.0f}m / {btime:>4.1f} min max penetration"
            )
        return "\n".join(lines)

    def generate_search_priorities(self, cave: Optional[CaveSystem] = None) -> str:
        lines = [
            "═══ SEARCH PRIORITIES ═══",
            f"  Cave:            {self.cave_name}",
            f"  Missing since:   {self.missing_since or 'Unknown'}",
            f"  Last known pos:  {self.last_known_position}",
            f"  Water temp:      {self.water_temp_c}°C",
            f"  Visibility:      {self.visibility_m}m",
            "",
            "  Search sequence (statistical by cave diving incidents):",
            "  1. Entrance area and line traps (first 50m)",
            "  2. First restriction or depth change",
            "  3. Junction points — wrong turn taken",
            "  4. Air bell areas — potential refuge",
            "  5. Maximum penetration limit for victim's gas",
            "  6. Dead-end passages and low spots",
            "",
            "  Silt disturbance protocol:",
            "  • Enter slowly, maintain neutral buoyancy",
            "  • Follow existing guideline; do not remove",
            "  • Station one diver at each junction",
            "  • Use continuous guideline from surface",
        ]

        if cave:
            segs = cave.get_shot_segments()
            if segs:
                _, bbox_max = cave.get_bounding_box()
                lines.append("")
                lines.append(f"  Cave data ({cave.name}):")
                lines.append(f"    Surveyed length: {cave.total_length_m():.0f} m")
                lines.append(f"    Station count:   {cave.station_count()}")
                lines.append(f"    Surveys:         {len(cave.surveys)}")

        return "\n".join(lines)

    def full_briefing(self, cave: Optional[CaveSystem] = None) -> str:
        divider = "─" * 50
        return "\n".join([
            "╔══════════════════════════════════════════════════╗",
            "║     CAVE DIVE SEARCH & RESCUE BRIEFING           ║",
            "╚══════════════════════════════════════════════════╝",
            "",
            self.generate_search_priorities(cave),
            "",
            divider,
            "",
            self.generate_gas_summary(),
            "",
            divider,
            "",
            "═══ EMERGENCY CONTACTS ═══",
            "  • Cave Diving Section (NSS-CDS): nss-cds.org",
            "  • NACD: nacd.com",
            "  • DAN Emergency: +1-919-684-9111",
            "  • IANTD: iantd.com",
            "  • Local Emergency: 911 / 112",
            "",
            "IMPORTANT: This briefing is AI-assisted.",
            "   Always verify with local authorities and",
            "   experienced cave rescue specialists.",
            divider,
        ])


def quick_gas_check(
    depth_m: float,
    tank_vol_l: float = 12.0,
    tank_pressure_bar: float = 200.0,
    num_tanks: int = 2,
    sac_lmin: float = 20.0,
) -> str:
    cfg = DiveGasConfig(
        tank_volume_liters=tank_vol_l,
        tank_pressure_bar=tank_pressure_bar,
        num_tanks=num_tanks,
        sac_rate_lmin=sac_lmin,
    )
    max_penet = cfg.penetration_distance_m(depth_m)
    turn_time = cfg.max_bottom_time_at_depth(depth_m)
    turn_pressure = cfg.turn_pressure_bar()

    return (
        f"Depth: {depth_m}m | "
        f"Turn @ {turn_pressure:.0f} bar | "
        f"Max penetration: {max_penet:.0f}m | "
        f"Bottom time: {turn_time:.1f} min"
    )

from __future__ import annotations
import math
import random
from dataclasses import dataclass

import numpy as np

from .cave_model import CaveSystem, CaveMetadata, Survey, Shot, Station, LRUD


@dataclass
class CaveProfile:
    total_length_m: float = 300.0
    max_depth_m: float = 30.0
    num_branches: int = 3
    branch_probability: float = 0.15
    passage_width_m: float = 3.0
    passage_height_m: float = 2.0
    width_variance: float = 0.4
    sinuosity: float = 0.25
    general_bearing: float = 45.0
    depth_gradient: float = -1.5


def build_from_metadata(metadata: CaveMetadata, seed: int = 42) -> CaveSystem:
    rng = random.Random(seed)

    profile = CaveProfile(
        total_length_m=max(50.0, metadata.total_surveyed_m or 300.0),
        max_depth_m=max(5.0, metadata.max_depth_m or 30.0),
        num_branches=_estimate_branches(metadata),
        passage_width_m=_estimate_width(metadata),
        passage_height_m=_estimate_height(metadata),
        general_bearing=rng.uniform(30, 150),
        sinuosity=_estimate_sinuosity(metadata),
    )

    cave = CaveSystem(metadata.name, metadata)
    _generate_surveys(cave, profile, rng)
    cave.compute_coordinates()

    if not metadata.description:
        metadata.description = (
            f"[ESTIMATED 3D RECONSTRUCTION — not a real survey]\n"
            f"Generated from available metadata. "
            f"For planning reference only."
        )
    else:
        metadata.description = (
            f"[ESTIMATED 3D RECONSTRUCTION]\n{metadata.description}"
        )

    return cave


def _generate_surveys(cave: CaveSystem, profile: CaveProfile, rng: random.Random) -> None:
    main_length = profile.total_length_m * 0.55
    main_survey = _generate_passage(
        name="Main Passage (estimated)",
        start_name="E1",
        total_length=main_length,
        bearing=profile.general_bearing,
        depth_start=0.0,
        max_depth=profile.max_depth_m,
        width=profile.passage_width_m,
        height=profile.passage_height_m,
        width_var=profile.width_variance,
        sinuosity=profile.sinuosity,
        rng=rng,
    )
    cave.add_survey(main_survey)

    branch_starts = list(main_survey.stations.keys())
    used_starts: set[str] = set()
    remaining = profile.total_length_m - main_length
    branch_count = 0

    for station_name in branch_starts[3:]:
        if branch_count >= profile.num_branches:
            break
        if remaining <= 30:
            break
        if station_name in used_starts:
            continue
        if rng.random() > 0.35:
            continue

        branch_bearing = (profile.general_bearing + rng.uniform(60, 120)) % 360
        branch_len = min(remaining * rng.uniform(0.2, 0.45), 200.0)
        width_scale = rng.uniform(0.5, 1.0)

        branch = _generate_passage(
            name=f"Branch {chr(65 + branch_count)} (estimated)",
            start_name=station_name,
            total_length=branch_len,
            bearing=branch_bearing,
            depth_start=0.0,
            max_depth=profile.max_depth_m * rng.uniform(0.4, 0.9),
            width=profile.passage_width_m * width_scale,
            height=profile.passage_height_m * rng.uniform(0.5, 0.9),
            width_var=profile.width_variance,
            sinuosity=profile.sinuosity * rng.uniform(0.8, 1.5),
            rng=rng,
            prefix=f"B{chr(65 + branch_count)}",
        )
        cave.add_survey(branch)
        used_starts.add(station_name)
        remaining -= branch_len
        branch_count += 1


def _generate_passage(
    name: str,
    start_name: str,
    total_length: float,
    bearing: float,
    depth_start: float,
    max_depth: float,
    width: float,
    height: float,
    width_var: float,
    sinuosity: float,
    rng: random.Random,
    prefix: str = "A",
) -> Survey:
    survey = Survey(name=name)
    shot_length = 8.0
    num_shots = max(3, min(80, int(total_length / shot_length)))

    current_bearing = bearing
    depth_profile = _depth_profile(num_shots, max_depth)

    stations_seen: dict[str, Station] = {}
    prev_name = start_name
    stations_seen[prev_name] = Station(prev_name)

    for i in range(num_shots):
        current_bearing += rng.gauss(0, sinuosity * 30)
        current_bearing %= 360

        this_len = shot_length + rng.gauss(0, 1.5)
        this_len = max(2.0, min(18.0, this_len))

        if i < num_shots * 0.6:
            target_depth_change = depth_profile[i]
            incl = math.degrees(math.atan2(-target_depth_change, this_len))
            incl = max(-35.0, min(35.0, incl + rng.gauss(0, 2)))
        else:
            incl = rng.gauss(2, 3)

        w = max(0.3, width + rng.gauss(0, width_var))
        h = max(0.2, height + rng.gauss(0, width_var * 0.5))
        lrud = LRUD(
            left=w * rng.uniform(0.3, 0.7),
            right=w * rng.uniform(0.3, 0.7),
            up=h * rng.uniform(0.3, 0.7),
            down=h * rng.uniform(0.3, 0.7),
        )

        next_name = f"{prefix}{i + 1}"
        shot = Shot(
            from_station=prev_name,
            to_station=next_name,
            length=this_len,
            bearing=current_bearing,
            inclination=incl,
            lrud_to=lrud,
        )
        survey.shots.append(shot)
        stations_seen[next_name] = Station(next_name, lrud=lrud)
        prev_name = next_name

    survey.stations = stations_seen
    return survey


def _depth_profile(n: int, max_depth: float) -> list[float]:
    profile = []
    for i in range(n):
        t = i / n
        if t < 0.5:
            depth_change = -max_depth * math.sin(math.pi * t) * 0.15
        else:
            depth_change = max_depth * math.sin(math.pi * t) * 0.05
        profile.append(depth_change)
    return profile


def _estimate_branches(meta: CaveMetadata) -> int:
    total = meta.total_surveyed_m or 300
    if total < 200:
        return 1
    if total < 1000:
        return 2
    if total < 5000:
        return 4
    return 6


def _estimate_width(meta: CaveMetadata) -> float:
    base = 2.5
    if "strong" in (meta.flow or "").lower():
        base += 1.5
    if meta.water_type == "saltwater":
        base += 0.5
    return base


def _estimate_height(meta: CaveMetadata) -> float:
    return _estimate_width(meta) * 0.7


def _estimate_sinuosity(meta: CaveMetadata) -> float:
    if "strong" in (meta.flow or "").lower():
        return 0.1
    if meta.water_type == "saltwater":
        return 0.3
    return 0.2

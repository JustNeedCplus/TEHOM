from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

from .cave_model import CaveSystem


@dataclass
class IncidentParams:
    entry_station: str
    entry_time: datetime
    total_gas_litres: float
    sac_rate_lmin: float = 20.0
    swim_speed_mmin: float = 15.0

    @property
    def turn_gas_litres(self) -> float:
        return self.total_gas_litres / 3.0

    @property
    def usable_penetration_gas_litres(self) -> float:
        return self.total_gas_litres * (2.0 / 3.0)


@dataclass
class StationEstimate:
    station_name: str
    distance_m: float
    time_to_reach_min: float
    gas_to_reach_l: float
    avg_depth_m: float
    probability: float
    reachable: bool
    beyond_turn: bool
    at_surface: bool = False


@dataclass
class DeadReckoningResult:
    entry_station: str
    elapsed_min: float
    gas_used_l: float
    gas_remaining_l: float
    turn_distance_m: float
    max_range_m: float
    estimates: list[StationEstimate] = field(default_factory=list)
    exhaustion_time_min: float = 0.0

    @property
    def high_probability_stations(self) -> list[StationEstimate]:
        return [e for e in self.estimates if e.probability > 0.5 and e.reachable]

    @property
    def search_zone_stations(self) -> list[StationEstimate]:
        return [e for e in self.estimates if e.probability > 0.1 and e.reachable]


def _build_graph(cave: CaveSystem) -> dict[str, list[tuple[str, float, float]]]:
    stations = cave.get_all_stations()
    graph: dict[str, list[tuple[str, float, float]]] = {n: [] for n in stations}

    for survey in cave.surveys:
        for shot in survey.shots:
            if shot.is_splay():
                continue
            a = stations.get(shot.from_station)
            b = stations.get(shot.to_station)
            if a is None or b is None:
                continue
            depth_a = max(0.0, float(a.z))
            depth_b = max(0.0, float(b.z))
            avg_depth = (depth_a + depth_b) / 2.0
            length = max(0.001, float(shot.length))
            graph[shot.from_station].append((shot.to_station, length, avg_depth))
            graph[shot.to_station].append((shot.from_station, length, avg_depth))

    return graph


def _dijkstra(
    graph: dict[str, list[tuple[str, float, float]]],
    start: str,
    params: IncidentParams,
) -> dict[str, tuple[float, float, float]]:
    dist: dict[str, tuple[float, float, float]] = {}
    heap = [(0.0, 0.0, 0.0, start)]

    while heap:
        d, gas, depth_sum, node = heapq.heappop(heap)
        if node in dist:
            continue
        dist[node] = (d, gas, depth_sum)

        for neighbor, length, avg_depth in graph.get(node, []):
            if neighbor in dist:
                continue
            ata = 1.0 + avg_depth / 10.0
            segment_time_min = length / params.swim_speed_mmin
            gas_segment = params.sac_rate_lmin * ata * segment_time_min
            heapq.heappush(heap, (
                d + length,
                gas + gas_segment,
                depth_sum + avg_depth * length,
                neighbor,
            ))

    return dist


def compute(
    cave: CaveSystem,
    params: IncidentParams,
    now: Optional[datetime] = None,
) -> DeadReckoningResult:
    if now is None:
        now = datetime.now()

    elapsed_min = max(0.0, (now - params.entry_time).total_seconds() / 60.0)

    graph = _build_graph(cave)
    stations = cave.get_all_stations()

    if params.entry_station not in graph and graph:
        fallback = next(iter(graph))
        params = IncidentParams(
            entry_station=fallback,
            entry_time=params.entry_time,
            total_gas_litres=params.total_gas_litres,
            sac_rate_lmin=params.sac_rate_lmin,
            swim_speed_mmin=params.swim_speed_mmin,
        )

    if not graph:
        return DeadReckoningResult(
            entry_station=params.entry_station,
            elapsed_min=elapsed_min,
            gas_used_l=0.0,
            gas_remaining_l=params.total_gas_litres,
            turn_distance_m=0.0,
            max_range_m=0.0,
        )

    dijkstra_result = _dijkstra(graph, params.entry_station, params)

    atas = []
    for st_name, (d, g, depth_sum) in dijkstra_result.items():
        if d > 0:
            atas.append(1.0 + (depth_sum / d) / 10.0)
    avg_ata = float(np.mean(atas)) if atas else 1.5

    elapsed_gas = params.sac_rate_lmin * avg_ata * elapsed_min
    gas_remaining = max(0.0, params.total_gas_litres - elapsed_gas)

    turn_gas = params.turn_gas_litres
    max_gas = params.usable_penetration_gas_litres
    turn_distance_m = 0.0
    max_range_m = 0.0
    for st_name, (d, g, _) in dijkstra_result.items():
        if g <= turn_gas and d > turn_distance_m:
            turn_distance_m = d
        if g <= max_gas and d > max_range_m:
            max_range_m = d

    exhaustion_time_min = (
        params.total_gas_litres / (params.sac_rate_lmin * avg_ata)
        if avg_ata > 0 else 0.0
    )

    expected_dist = elapsed_min * params.swim_speed_mmin

    sigma = max(expected_dist * 0.35, 30.0)

    estimates: list[StationEstimate] = []
    for st_name, (d, gas, depth_sum) in dijkstra_result.items():
        if st_name == params.entry_station:
            continue

        avg_depth = depth_sum / max(d, 0.001)
        time_to_reach = d / params.swim_speed_mmin
        reachable = gas <= turn_gas
        beyond_turn = (not reachable) and gas <= max_gas

        if gas > max_gas:
            prob = 0.0
        elif elapsed_min < 1.0:
            prob = math.exp(-0.5 * (d / max(sigma * 0.5, 20.0)) ** 2) if reachable else 0.0
        else:
            if reachable or beyond_turn:
                prob = math.exp(-0.5 * ((d - expected_dist) / sigma) ** 2)
                if beyond_turn:
                    prob *= 0.25
                elif gas > turn_gas * 0.85:
                    prob *= 0.6
            else:
                prob = 0.0

        st_obj = stations.get(st_name)
        at_surface = st_obj is not None and float(st_obj.z) < 2.0

        estimates.append(StationEstimate(
            station_name=st_name,
            distance_m=d,
            time_to_reach_min=time_to_reach,
            gas_to_reach_l=gas,
            avg_depth_m=avg_depth,
            probability=prob,
            reachable=reachable,
            beyond_turn=beyond_turn,
            at_surface=at_surface,
        ))

    prob_sum = sum(e.probability for e in estimates)
    if prob_sum > 0:
        for e in estimates:
            e.probability /= prob_sum

    estimates.sort(key=lambda e: e.probability, reverse=True)

    return DeadReckoningResult(
        entry_station=params.entry_station,
        elapsed_min=elapsed_min,
        gas_used_l=elapsed_gas,
        gas_remaining_l=gas_remaining,
        turn_distance_m=turn_distance_m,
        max_range_m=max_range_m,
        estimates=estimates,
        exhaustion_time_min=exhaustion_time_min,
    )

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class LRUD:
    left: float = 0.0
    right: float = 0.0
    up: float = 0.0
    down: float = 0.0

    @property
    def width(self) -> float:
        return self.left + self.right

    @property
    def height(self) -> float:
        return self.up + self.down

    @property
    def radius_approx(self) -> float:
        return max(self.width, self.height) / 2.0


@dataclass
class Station:
    name: str
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    lrud: Optional[LRUD] = None
    depth: float = 0.0
    flags: str = ""
    comment: str = ""

    @property
    def position(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z])


@dataclass
class Shot:
    from_station: str
    to_station: str
    length: float
    bearing: float
    inclination: float
    lrud_from: Optional[LRUD] = None
    lrud_to: Optional[LRUD] = None
    flags: str = ""
    comment: str = ""

    def is_splay(self) -> bool:
        return self.to_station.startswith("-") or "splay" in self.flags.lower()


@dataclass
class Survey:
    name: str
    date: str = ""
    surveyors: list[str] = field(default_factory=list)
    declination: float = 0.0
    stations: dict[str, Station] = field(default_factory=dict)
    shots: list[Shot] = field(default_factory=list)
    comment: str = ""


@dataclass
class CaveMetadata:
    name: str
    country: str = ""
    region: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    max_depth_m: float = 0.0
    total_surveyed_m: float = 0.0
    water_type: str = "saltwater"
    visibility_m: float = 0.0
    flow: str = "none"
    access: str = ""
    hazards: list[str] = field(default_factory=list)
    description: str = ""
    sources: list[str] = field(default_factory=list)


class CaveSystem:

    def __init__(self, name: str, metadata: Optional[CaveMetadata] = None):
        self.name = name
        self.metadata = metadata or CaveMetadata(name=name)
        self.surveys: list[Survey] = []
        self._all_stations: dict[str, Station] = {}
        self._computed = False

    def add_survey(self, survey: Survey) -> None:
        self.surveys.append(survey)
        self._computed = False

    def compute_coordinates(self) -> None:
        from .loop_closure import compute_with_loop_closure
        compute_with_loop_closure(self)
        return

    def loop_closure_quality(self) -> dict:
        from .loop_closure import loop_closure_error
        return loop_closure_error(self)

    def _compute_coordinates_unused(self) -> None:
        self._all_stations = {}

        for survey in self.surveys:
            if not survey.shots:
                continue

            adj: dict[str, list[tuple[str, Shot, bool]]] = {}
            for shot in survey.shots:
                if shot.is_splay():
                    continue
                adj.setdefault(shot.from_station, []).append(
                    (shot.to_station, shot, False)
                )
                adj.setdefault(shot.to_station, []).append(
                    (shot.from_station, shot, True)
                )

            first_name = survey.shots[0].from_station
            if first_name not in self._all_stations:
                seed = survey.stations.get(first_name, Station(first_name))
                seed.x, seed.y, seed.z = 0.0, 0.0, 0.0
                self._all_stations[first_name] = seed

            visited = {first_name}
            stack = [first_name]

            while stack:
                current_name = stack.pop()
                current = self._all_stations[current_name]

                for neighbor_name, shot, reversed_shot in adj.get(current_name, []):
                    if neighbor_name in visited:
                        continue

                    dx, dy, dz = self._shot_vector(shot, reversed_shot, survey.declination)
                    neighbor = survey.stations.get(neighbor_name, Station(neighbor_name))
                    neighbor.x = current.x + dx
                    neighbor.y = current.y + dy
                    neighbor.z = current.z + dz

                    if shot.lrud_to and not reversed_shot:
                        neighbor.lrud = shot.lrud_to
                    elif shot.lrud_from and reversed_shot:
                        neighbor.lrud = shot.lrud_from

                    self._all_stations[neighbor_name] = neighbor
                    visited.add(neighbor_name)
                    stack.append(neighbor_name)

        self._computed = True

    @staticmethod
    def _shot_vector(shot: Shot, reversed_shot: bool, declination: float) -> tuple[float, float, float]:
        bearing_rad = math.radians(shot.bearing + declination)
        incl_rad = math.radians(shot.inclination)

        horizontal = shot.length * math.cos(incl_rad)
        dx = horizontal * math.sin(bearing_rad)
        dy = horizontal * math.cos(bearing_rad)
        dz = shot.length * math.sin(incl_rad)

        if reversed_shot:
            return -dx, -dy, -dz
        return dx, dy, dz

    def get_all_stations(self) -> dict[str, Station]:
        if not self._computed:
            self.compute_coordinates()
        return self._all_stations

    def get_shot_segments(self) -> list[tuple[np.ndarray, np.ndarray, Shot]]:
        if not self._computed:
            self.compute_coordinates()

        segments = []
        for survey in self.surveys:
            for shot in survey.shots:
                if shot.is_splay():
                    continue
                a = self._all_stations.get(shot.from_station)
                b = self._all_stations.get(shot.to_station)
                if a is not None and b is not None:
                    segments.append((a.position, b.position, shot))
        return segments

    def get_bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        stations = self.get_all_stations()
        if not stations:
            return np.zeros(3), np.zeros(3)
        positions = np.array([s.position for s in stations.values()])
        return positions.min(axis=0), positions.max(axis=0)

    def total_length_m(self) -> float:
        total = 0.0
        for survey in self.surveys:
            for shot in survey.shots:
                if not shot.is_splay():
                    total += shot.length
        return total

    def station_count(self) -> int:
        return len(self.get_all_stations())

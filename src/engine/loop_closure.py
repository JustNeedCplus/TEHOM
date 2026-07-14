from __future__ import annotations
import math
import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cave_model import CaveSystem, Survey, Shot, Station


def shot_vector(shot: "Shot", reversed_shot: bool,
                declination: float = 0.0) -> tuple[float, float, float]:
    tape     = shot.length
    bearing  = math.radians((shot.bearing + declination) % 360)
    clino    = math.radians(shot.inclination)

    horizontal = tape * math.cos(clino)
    dx =  horizontal * math.sin(bearing)
    dy =  horizontal * math.cos(bearing)
    dz = -tape       * math.sin(clino)

    if reversed_shot:
        return -dx, -dy, -dz
    return dx, dy, dz


def compute_with_loop_closure(cave: "CaveSystem") -> None:
    cave._all_stations = {}

    for survey in cave.surveys:
        if not survey.shots:
            continue

        main_shots = [s for s in survey.shots if not s.is_splay()]
        if not main_shots:
            continue

        station_names = set()
        for shot in main_shots:
            station_names.add(shot.from_station)
            station_names.add(shot.to_station)

        n_stations = len(station_names)
        n_shots    = len(main_shots)

        has_loops = n_shots >= n_stations

        if has_loops:
            positions = _least_squares_adjustment(
                main_shots, station_names, survey.declination
            )
        else:
            positions = _dfs_traversal(
                main_shots, station_names, survey.declination
            )

        for name, (x, y, z) in positions.items():
            st = survey.stations.get(name)
            if st is None:
                from .cave_model import Station
                st = Station(name)
            st.x, st.y, st.z = float(x), float(y), float(z)
            cave._all_stations[name] = st

        for shot in main_shots:
            to_st = cave._all_stations.get(shot.to_station)
            if to_st and shot.lrud_to:
                to_st.lrud = shot.lrud_to
            from_st = cave._all_stations.get(shot.from_station)
            if from_st and shot.lrud_from and from_st.lrud is None:
                from_st.lrud = shot.lrud_from

        for shot in survey.shots:
            if not shot.is_splay():
                continue
            from_st = cave._all_stations.get(shot.from_station)
            if from_st is None:
                continue
            dx, dy, dz = shot_vector(shot, False, survey.declination)
            splay_name = shot.to_station
            from .cave_model import Station
            splay = Station(splay_name)
            splay.x = from_st.x + dx
            splay.y = from_st.y + dy
            splay.z = from_st.z + dz
            cave._all_stations[splay_name] = splay

    cave._computed = True


def _least_squares_adjustment(
    shots: list,
    station_names: set,
    declination: float
) -> dict[str, tuple[float, float, float]]:
    name_to_idx = {name: i for i, name in enumerate(sorted(station_names))}
    n  = len(name_to_idx)
    m  = len(shots)

    b_vec   = np.zeros(m * 3)
    weights = np.zeros(m)
    A_mat   = np.zeros((m * 3, n * 3))

    for i, shot in enumerate(shots):
        dx, dy, dz = shot_vector(shot, False, declination)
        b_vec[i*3]   = dx
        b_vec[i*3+1] = dy
        b_vec[i*3+2] = dz

        length = max(shot.length, 0.01)
        weights[i] = 1.0 / length

        from_idx = name_to_idx[shot.from_station]
        to_idx   = name_to_idx[shot.to_station]

        for k in range(3):
            row = i * 3 + k
            A_mat[row, to_idx   * 3 + k] = +1.0
            A_mat[row, from_idx * 3 + k] = -1.0

    sqrt_w = np.sqrt(np.repeat(weights, 3))
    A_weighted = A_mat * sqrt_w[:, np.newaxis]
    b_weighted = b_vec * sqrt_w

    anchor_idx = 0
    constraint_weight = 1e6

    constraint_A = np.zeros((3, n * 3))
    constraint_b = np.zeros(3)
    for k in range(3):
        constraint_A[k, anchor_idx * 3 + k] = 1.0

    A_final = np.vstack([A_weighted, constraint_A * constraint_weight])
    b_final = np.concatenate([b_weighted, constraint_b * constraint_weight])

    result, residuals, rank, sv = np.linalg.lstsq(A_final, b_final, rcond=None)

    positions = {}
    for name, idx in name_to_idx.items():
        x = result[idx * 3]
        y = result[idx * 3 + 1]
        z = result[idx * 3 + 2]
        positions[name] = (float(x), float(y), float(z))

    return positions


def _dfs_traversal(
    shots: list,
    station_names: set,
    declination: float
) -> dict[str, tuple[float, float, float]]:
    adj: dict[str, list] = {}
    for shot in shots:
        adj.setdefault(shot.from_station, []).append((shot.to_station, shot, False))
        adj.setdefault(shot.to_station,   []).append((shot.from_station, shot, True))

    first = shots[0].from_station
    positions = {first: (0.0, 0.0, 0.0)}
    visited = {first}
    stack = [first]

    while stack:
        current = stack.pop()
        cx, cy, cz = positions[current]
        for neighbour, shot, reversed_shot in adj.get(current, []):
            if neighbour in visited:
                continue
            dx, dy, dz = shot_vector(shot, reversed_shot, declination)
            positions[neighbour] = (cx + dx, cy + dy, cz + dz)
            visited.add(neighbour)
            stack.append(neighbour)

    return positions


def loop_closure_error(cave: "CaveSystem") -> dict[str, float]:
    errors = {}
    for survey in cave.surveys:
        main_shots = [s for s in survey.shots if not s.is_splay()]
        total_sq_error = 0.0
        n_loops = 0

        for shot in main_shots:
            from_st = cave._all_stations.get(shot.from_station)
            to_st   = cave._all_stations.get(shot.to_station)
            if from_st is None or to_st is None:
                continue

            dx_meas, dy_meas, dz_meas = shot_vector(shot, False, survey.declination)
            dx_actual = to_st.x - from_st.x
            dy_actual = to_st.y - from_st.y
            dz_actual = to_st.z - from_st.z

            err = math.sqrt(
                (dx_actual - dx_meas)**2 +
                (dy_actual - dy_meas)**2 +
                (dz_actual - dz_meas)**2
            )
            total_sq_error += err ** 2
            n_loops += 1

        rms = math.sqrt(total_sq_error / n_loops) if n_loops > 0 else 0.0
        errors[survey.name] = rms

    return errors

from __future__ import annotations
import math
import random
from typing import Optional


AIR        = 0
STONE      = 1
GRAVEL     = 2
WATER      = 3
SAND       = 4
DARK_STONE = 5

CHUNK_SIZE = 48


def build_chunk(cave, station_name: str, seed: int = 0) -> dict:
    rng = random.Random(seed + hash(station_name) % 99999)

    stations = cave.get_all_stations()
    station  = stations.get(station_name)
    if station is None:
        return _empty_chunk(station_name)

    connected_shots = []
    for survey in cave.surveys:
        for shot in survey.shots:
            if shot.is_splay():
                continue
            if shot.from_station == station_name:
                connected_shots.append((shot, False))
            elif shot.to_station == station_name:
                connected_shots.append((shot, True))

    lrud = _get_lrud(station, connected_shots)

    scale = 2.0
    half_w = max(2.5, (lrud.left  + lrud.right) / 2.0) * scale
    half_h = max(2.0, (lrud.up    + lrud.down)  / 2.0) * scale
    floor_offset = max(1.5, lrud.down) * scale

    passages = []
    for shot, reversed_shot in connected_shots:
        bearing = (shot.bearing + 180) % 360 if reversed_shot else shot.bearing
        slrud = shot.lrud_to if not reversed_shot else shot.lrud_from
        if slrud is None:
            slrud = lrud
        sw = max(2.5, (slrud.left + slrud.right) / 2.0) * scale
        sh = max(2.0, (slrud.up   + slrud.down)  / 2.0) * scale
        passages.append({
            "bearing": bearing,
            "length":  CHUNK_SIZE // 2 - 2,
            "half_w":  sw,
            "half_h":  sh,
            "floor_offset": max(1.5, slrud.down) * scale,
        })

    if not passages:
        passages.append({
            "bearing": 0.0,
            "length":  CHUNK_SIZE // 2 - 2,
            "half_w":  half_w,
            "half_h":  half_h,
            "floor_offset": floor_offset,
        })

    voxels = _carve_chunk(passages, half_w, half_h, floor_offset, rng)

    cam_y_offset = -floor_offset + half_h * 0.4

    all_stations = cave.get_all_stations()
    z_values = [abs(s.z) for s in all_stations.values() if hasattr(s, "z")]
    z_max = max(z_values) if z_values else 1.0
    cave_max_depth = getattr(cave, "metadata", None)
    real_max = getattr(cave_max_depth, "max_depth_m", 0.0) if cave_max_depth else 0.0
    if real_max > 0 and z_max > 0:
        depth_m = abs(float(station.z)) / z_max * real_max
    elif hasattr(station, "depth") and float(station.depth) > 0:
        depth_m = float(station.depth)
    else:
        depth_m = abs(float(station.z)) if hasattr(station, "z") else 0.0

    return {
        "station":         station_name,
        "depth_m":         depth_m,
        "lrud":            {
            "l": lrud.left, "r": lrud.right,
            "u": lrud.up,   "d": lrud.down
        },
        "passage_bearing": passages[0]["bearing"],
        "voxels":          voxels,
        "chunk_size":      CHUNK_SIZE,
        "passages":        passages,
        "cam_y_offset":    cam_y_offset,
    }


def _get_lrud(station, shots):
    try:
        if station.lrud and any(v > 0 for v in [
            station.lrud.left, station.lrud.right,
            station.lrud.up,   station.lrud.down
        ]):
            return station.lrud
    except Exception:
        pass
    for shot, rev in shots:
        try:
            lrud = shot.lrud_to if not rev else shot.lrud_from
            if lrud and any(v > 0 for v in [lrud.left, lrud.right, lrud.up, lrud.down]):
                return lrud
        except Exception:
            continue
    class DefaultLRUD:
        left = right = 1.25
        up = 1.5
        down = 0.75
    return DefaultLRUD()


def _carve_chunk(passages, centre_hw, centre_hh, floor_off, rng):
    N = CHUNK_SIZE
    half = N // 2

    grid = [STONE if rng.random() < 0.75 else DARK_STONE for _ in range(N * N * N)]

    def idx(x, y, z):
        if 0 <= x < N and 0 <= y < N and 0 <= z < N:
            return z * N * N + y * N + x
        return None

    def set_block(x, y, z, b):
        i = idx(x, y, z)
        if i is not None:
            grid[i] = b

    def get_block(x, y, z):
        i = idx(x, y, z)
        return grid[i] if i is not None else STONE

    def carve_ellipse(ox, oy, oz, hw, hh):
        for dy in range(-math.ceil(hh) - 1, math.ceil(hh) + 2):
            for dx in range(-math.ceil(hw) - 1, math.ceil(hw) + 2):
                n = rng.uniform(-0.25, 0.25)
                dist = (dx / max(hw + n, 0.1)) ** 2 + (dy / max(hh + n * 0.5, 0.1)) ** 2
                if dist <= 1.0:
                    set_block(ox + dx, oy + dy, oz, WATER)

    cy_centre = half - int(floor_off) + int(centre_hh * 0.4)
    for dz in range(-3, 4):
        fade = 1.0 - abs(dz) / 4.0
        carve_ellipse(half, cy_centre, half + dz,
                      centre_hw * (0.8 + fade * 0.2),
                      centre_hh * (0.8 + fade * 0.2))

    for p in passages:
        bearing_rad = math.radians(p["bearing"])
        dx_step = math.sin(bearing_rad)
        dz_step = math.cos(bearing_rad)
        hw = p["half_w"]
        hh = p["half_h"]
        fo = p["floor_offset"]
        cy = half - int(fo) + int(hh * 0.4)
        length = p["length"]

        for step in range(1, length + 1):
            t = step / length
            vy = rng.gauss(0, 0.15) * t
            px = int(round(half + dx_step * step))
            pz = int(round(half + dz_step * step))
            py = int(round(cy + vy))
            taper = 1.0 if step < length * 0.8 else 1.0 - (t - 0.8) / 0.2 * 0.15
            carve_ellipse(px, py, pz,
                          hw * taper + rng.gauss(0, 0.1),
                          hh * taper + rng.gauss(0, 0.08))

    for z in range(N):
        for x in range(N):
            for y in range(1, N):
                if get_block(x, y, z) == WATER and get_block(x, y-1, z) in (STONE, DARK_STONE):
                    grid[idx(x, y-1, z)] = SAND if rng.random() < 0.3 else GRAVEL

    return grid


def build_passage_data(cave, station_name: str) -> dict:
    stations = cave.get_all_stations()
    station  = stations.get(station_name)
    if station is None:
        return {
            "station": station_name, "depth_m": 0.0,
            "lrud": {"l": 1.5, "r": 1.5, "u": 1.2, "d": 0.8},
            "passage_bearing": 0.0, "passages": [],
        }

    connected_shots = []
    for survey in cave.surveys:
        for shot in survey.shots:
            if shot.is_splay():
                continue
            if shot.from_station == station_name:
                connected_shots.append((shot, False))
            elif shot.to_station == station_name:
                connected_shots.append((shot, True))

    lrud = _get_lrud(station, connected_shots)

    scale = 2.0
    passages = []
    for shot, reversed_shot in connected_shots:
        bearing = (shot.bearing + 180) % 360 if reversed_shot else shot.bearing
        slrud = shot.lrud_to if not reversed_shot else shot.lrud_from
        if slrud is None:
            slrud = lrud
        sw = max(2.5, (slrud.left + slrud.right) / 2.0) * scale
        sh = max(2.0, (slrud.up   + slrud.down)  / 2.0) * scale
        passages.append({
            "bearing":      bearing,
            "half_w":       sw,
            "half_h":       sh,
            "floor_offset": max(1.5, slrud.down) * scale,
        })

    all_z    = [abs(s.z) for s in cave.get_all_stations().values()]
    z_max    = max(all_z) if all_z else 1.0
    cave_meta = getattr(cave, "metadata", None)
    real_max  = getattr(cave_meta, "max_depth_m", 0.0) if cave_meta else 0.0
    if real_max > 0 and z_max > 0:
        depth_m = abs(float(station.z)) / z_max * real_max
    elif hasattr(station, "depth") and float(station.depth) > 0:
        depth_m = float(station.depth)
    else:
        depth_m = abs(float(station.z))

    return {
        "station":         station_name,
        "depth_m":         depth_m,
        "lrud":            {"l": lrud.left, "r": lrud.right, "u": lrud.up, "d": lrud.down},
        "passage_bearing": passages[0]["bearing"] if passages else 0.0,
        "passages":        passages,
    }


def _empty_chunk(station_name):
    N = CHUNK_SIZE
    half = N // 2
    grid = [STONE if (x != half or abs(y - half) > 4 or abs(z - half) > 3)
            else WATER
            for z in range(N) for y in range(N) for x in range(N)]
    return {
        "station": station_name, "depth_m": 0.0,
        "lrud": {"l": 2.0, "r": 2.0, "u": 2.0, "d": 1.0},
        "passage_bearing": 0.0, "voxels": grid,
        "chunk_size": N, "passages": [], "cam_y_offset": 0.0,
    }

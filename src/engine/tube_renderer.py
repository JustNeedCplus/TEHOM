from __future__ import annotations
import numpy as np
import math
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .cave_model import CaveSystem, Station

RING_SEGMENTS = 8

DEFAULT_LRUD = (1.0, 1.0, 0.8, 0.8)

MIN_DIM = 0.05


def _lrud_values(station: "Station") -> tuple[float, float, float, float]:
    lrud = getattr(station, "lrud", None)
    if lrud is None:
        return DEFAULT_LRUD
    l = max(float(lrud.left  or DEFAULT_LRUD[0]), MIN_DIM)
    r = max(float(lrud.right or DEFAULT_LRUD[1]), MIN_DIM)
    u = max(float(lrud.up    or DEFAULT_LRUD[2]), MIN_DIM)
    d = max(float(lrud.down  or DEFAULT_LRUD[3]), MIN_DIM)
    return l, r, u, d


def _make_ring(
    centre: np.ndarray,
    forward: np.ndarray,
    l: float, r: float, u: float, d: float
) -> np.ndarray:
    fwd = forward / (np.linalg.norm(forward) + 1e-9)

    world_up = np.array([0.0, 0.0, 1.0])
    if abs(np.dot(fwd, world_up)) > 0.9:
        world_up = np.array([0.0, 1.0, 0.0])

    right_vec = np.cross(fwd, world_up)
    right_vec /= np.linalg.norm(right_vec) + 1e-9
    up_vec = np.cross(right_vec, fwd)
    up_vec /= np.linalg.norm(up_vec) + 1e-9

    angles = np.linspace(0, 2 * math.pi, RING_SEGMENTS, endpoint=False)
    verts = np.zeros((RING_SEGMENTS, 3))

    for i, angle in enumerate(angles):
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        rx = r if cos_a >= 0 else l
        ry = u if sin_a >= 0 else d

        px = rx * cos_a
        py = ry * sin_a

        verts[i] = centre + right_vec * px + up_vec * py

    return verts


def _tube_segment_mesh(
    ring_a: np.ndarray,
    ring_b: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    n = RING_SEGMENTS
    verts = np.vstack([ring_a, ring_b])

    faces = []
    for i in range(n):
        next_i = (i + 1) % n
        a0, a1 = i, next_i
        b0, b1 = i + n, next_i + n
        faces.append([a0, a1, b0])
        faces.append([a1, b1, b0])

    return verts, np.array(faces, dtype=np.uint32)


def build_tube_meshes(cave: "CaveSystem") -> list[dict]:
    stations = cave.get_all_stations()
    if not stations:
        return []

    z_vals = [s.z for s in stations.values()]
    z_min  = min(z_vals)
    z_max  = max(z_vals)
    z_range = max(abs(z_max - z_min), 0.001)

    meta = getattr(cave, "metadata", None)
    real_max_depth = getattr(meta, "max_depth_m", 0.0) if meta else 0.0

    results = []

    for survey in cave.surveys:
        main_shots = [s for s in survey.shots if not s.is_splay()]
        if not main_shots:
            continue

        chains = _build_chains(main_shots)

        for chain in chains:
            if len(chain) < 2:
                continue

            all_verts = []
            all_faces = []
            vert_offset = 0
            prev_ring = None

            for idx, name in enumerate(chain):
                st = stations.get(name)
                if st is None:
                    prev_ring = None
                    continue

                centre = np.array([st.x, st.y, st.z], dtype=np.float64)

                if idx < len(chain) - 1:
                    next_name = chain[idx + 1]
                    next_st = stations.get(next_name)
                    if next_st:
                        forward = np.array([
                            next_st.x - st.x,
                            next_st.y - st.y,
                            next_st.z - st.z,
                        ])
                    else:
                        forward = np.array([1.0, 0.0, 0.0])
                else:
                    prev_name = chain[idx - 1]
                    prev_st = stations.get(prev_name)
                    if prev_st:
                        forward = np.array([
                            st.x - prev_st.x,
                            st.y - prev_st.y,
                            st.z - prev_st.z,
                        ])
                    else:
                        forward = np.array([1.0, 0.0, 0.0])

                if np.linalg.norm(forward) < 0.001:
                    forward = np.array([1.0, 0.0, 0.0])

                l, r, u, d = _lrud_values(st)
                ring = _make_ring(centre, forward, l, r, u, d)

                if prev_ring is not None:
                    verts, faces = _tube_segment_mesh(prev_ring, ring)
                    all_verts.append(verts)
                    all_faces.append(faces + vert_offset)
                    vert_offset += len(verts)

                prev_ring = ring

            if not all_verts:
                continue

            combined_verts = np.vstack(all_verts).astype(np.float32)
            combined_faces = np.vstack(all_faces).astype(np.uint32)

            mid_name = chain[len(chain) // 2]
            mid_st   = stations.get(mid_name)
            mid_z    = mid_st.z if mid_st else 0.0

            t = float(np.clip((z_max - mid_z) / z_range, 0, 1))
            color = _depth_color(t)

            results.append({
                "vertices":    combined_verts,
                "faces":       combined_faces,
                "color":       color,
                "survey":      survey.name,
                "depth_range": (z_min, z_max),
            })

    return results


def _depth_color(t: float) -> tuple:
    r = 0.0
    g = max(0.0, 0.7 - 0.6 * t)
    b = 1.0 - 0.15 * t
    a = 0.72
    return (r, g, b, a)


def _build_chains(shots: list) -> list[list[str]]:
    adj: dict[str, list[str]] = {}
    for shot in shots:
        adj.setdefault(shot.from_station, []).append(shot.to_station)
        adj.setdefault(shot.to_station,   []).append(shot.from_station)

    degree = {name: len(neighbours) for name, neighbours in adj.items()}

    endpoints = [n for n, d in degree.items() if d == 1]
    if not endpoints:
        endpoints = [shots[0].from_station]

    visited_edges: set[frozenset] = set()
    chains = []

    def trace_chain(start: str, came_from: Optional[str]) -> list[str]:
        chain = [start]
        current = start
        prev = came_from
        while True:
            neighbours = [n for n in adj.get(current, []) if n != prev]
            if not neighbours:
                break
            if len(neighbours) > 1 and current != start:
                break
            next_node = neighbours[0]
            edge = frozenset([current, next_node])
            if edge in visited_edges:
                break
            visited_edges.add(edge)
            chain.append(next_node)
            prev = current
            current = next_node
        return chain

    for ep in endpoints:
        for neighbour in adj.get(ep, []):
            edge = frozenset([ep, neighbour])
            if edge not in visited_edges:
                chain = trace_chain(ep, None)
                if len(chain) >= 2:
                    chains.append(chain)

    for shot in shots:
        edge = frozenset([shot.from_station, shot.to_station])
        if edge not in visited_edges:
            chain = trace_chain(shot.from_station, None)
            if len(chain) >= 2:
                chains.append(chain)

    return chains

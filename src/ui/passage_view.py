from __future__ import annotations

import math
from typing import Optional

import numpy as np

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt

try:
    import pyqtgraph as pg
    import pyqtgraph.opengl as gl
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False


_RING_N = 20


def _make_ring(centre, forward, l: float, r: float, u: float, d: float, n: int = _RING_N):
    fwd = np.array(forward, dtype=np.float64)
    norm = np.linalg.norm(fwd)
    fwd = fwd / norm if norm > 1e-9 else np.array([1.0, 0.0, 0.0])

    world_up = np.array([0.0, 0.0, 1.0])
    if abs(np.dot(fwd, world_up)) > 0.9:
        world_up = np.array([0.0, 1.0, 0.0])

    right_vec = np.cross(fwd, world_up)
    right_vec /= np.linalg.norm(right_vec) + 1e-9
    up_vec = np.cross(right_vec, fwd)
    up_vec /= np.linalg.norm(up_vec) + 1e-9

    angles = np.linspace(0, 2 * math.pi, n, endpoint=False)
    verts = np.zeros((n, 3))
    for i, angle in enumerate(angles):
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        rx = r if cos_a >= 0 else l
        ry = u if sin_a >= 0 else d
        verts[i] = np.array(centre) + right_vec * (rx * cos_a) + up_vec * (ry * sin_a)
    return verts


def _tube_mesh(ring_a: np.ndarray, ring_b: np.ndarray):
    n = len(ring_a)
    verts = np.vstack([ring_a, ring_b])
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, i + n])
        faces.append([j, j + n, i + n])
    return verts.astype(np.float32), np.array(faces, dtype=np.uint32)


def _bearing_cardinal(b: float) -> str:
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[round(b / 45) % 8]



class PassageViewWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._items: list = []
        self._view: Optional[gl.GLViewWidget] = None

        if PYQTGRAPH_AVAILABLE:
            self._view = gl.GLViewWidget()
            self._view.setBackgroundColor(pg.mkColor("#050C14"))
            self._layout.addWidget(self._view)
        else:
            self._layout.addWidget(QLabel("pyqtgraph not available"))

        self._hud = QLabel(self)
        self._hud.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._hud.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._hud.setStyleSheet("""
            color:
            background: rgba(5, 12, 20, 0.88);
            border: 1px solid
            border-radius: 3px;
            padding: 8px 13px;
            font-family: Menlo, Consolas, monospace;
            font-size: 11px;
            line-height: 1.7;
        """)
        self._hud.setTextFormat(Qt.TextFormat.RichText)
        self._hud.hide()

        self._placeholder = QLabel(self)
        self._placeholder.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setTextFormat(Qt.TextFormat.RichText)
        self._placeholder.setStyleSheet("background: transparent;")
        self._placeholder.setText(
            "<span style='color:#2A3A4A; font-size:32px;'>⬡</span><br><br>"
            "<span style='color:#6B7A8A; font-size:12px;'>Click a station dot on the cave map</span><br>"
            "<span style='color:#3A4A5A; font-size:10px;'>to explore the passage cross-section</span>"
        )
        self._placeholder.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._placeholder:
            self._placeholder.setGeometry(0, 0, self.width(), self.height())
        if self._hud and self._hud.isVisible():
            self._hud.move(10, 10)


    def clear(self):
        self._clear_items()
        if self._hud:
            self._hud.hide()
        if self._placeholder:
            self._placeholder.show()

    def load_station(self, data: dict):
        if not PYQTGRAPH_AVAILABLE or self._view is None:
            return
        self._clear_items()

        station_name = data.get("station", "?")
        depth_m      = float(data.get("depth_m", 0.0))
        lrud         = data.get("lrud", {})
        passages     = data.get("passages", [])
        primary_b    = float(data.get("passage_bearing", 0.0))

        l = max(float(lrud.get("l", 1.5)), 0.15)
        r = max(float(lrud.get("r", 1.5)), 0.15)
        u = max(float(lrud.get("u", 1.2)), 0.15)
        d = max(float(lrud.get("d", 0.8)), 0.15)

        self._render_passage_arms(passages, l, r, u, d, primary_b)
        self._render_station_ring(l, r, u, d, primary_b)
        self._render_lrud_spokes(l, r, u, d, primary_b)
        self._render_caveline(primary_b)
        self._render_floor(l, r, d, primary_b)

        self._set_camera(primary_b, l, r, u, d)
        self._update_hud(station_name, depth_m, l, r, u, d, primary_b)

        self._placeholder.hide()
        self._hud.move(10, 10)
        self._hud.show()


    def _render_passage_arms(self, passages, l, r, u, d, primary_b):
        voxel_scale = 0.5

        arms = []
        for p in passages:
            b = float(p.get("bearing", primary_b))
            hw = float(p.get("half_w", (l + r))) * voxel_scale
            hh = float(p.get("half_h", (u + d))) * voxel_scale
            arms.append((b, hw, hh))

        if not arms:
            arms = [(primary_b, (l + r) / 2, (u + d) / 2)]

        for i, (bearing, hw, hh) in enumerate(arms):
            brd = math.radians(bearing)
            fwd = np.array([math.sin(brd), math.cos(brd), 0.0])

            arm_len = 12.0
            n_rings  = 5
            lrud_far = {
                "l": max(hw * 0.45, 0.15), "r": max(hw * 0.55, 0.15),
                "u": max(hh * 0.6,  0.15), "d": max(hh * 0.4,  0.15),
            }

            rings = []
            for step in range(n_rings + 1):
                t = step / n_rings
                centre = fwd * (t * arm_len)
                tl = l + (lrud_far["l"] - l) * t
                tr = r + (lrud_far["r"] - r) * t
                tu = u + (lrud_far["u"] - u) * t
                td = d + (lrud_far["d"] - d) * t
                rings.append(_make_ring(centre, fwd,
                                        max(tl, 0.1), max(tr, 0.1),
                                        max(tu, 0.1), max(td, 0.1)))

            color = (0.14, 0.20, 0.28, 0.88) if i == 0 else (0.10, 0.14, 0.20, 0.72)
            for j in range(len(rings) - 1):
                verts, faces = _tube_mesh(rings[j], rings[j + 1])
                mesh = gl.GLMeshItem(
                    vertexes=verts, faces=faces, color=color,
                    smooth=True, drawEdges=False, drawFaces=True,
                    glOptions="translucent",
                )
                self._view.addItem(mesh)
                self._items.append(mesh)

        back_brd = math.radians((primary_b + 180) % 360)
        back_fwd = np.array([math.sin(back_brd), math.cos(back_brd), 0.0])
        back_rings = [
            _make_ring(back_fwd * t * 3.0, back_fwd, l, r, u, d)
            for t in [0, 0.33, 0.66, 1.0]
        ]
        for j in range(len(back_rings) - 1):
            verts, faces = _tube_mesh(back_rings[j], back_rings[j + 1])
            mesh = gl.GLMeshItem(
                vertexes=verts, faces=faces, color=(0.11, 0.16, 0.22, 0.70),
                smooth=True, drawEdges=False, drawFaces=True,
                glOptions="translucent",
            )
            self._view.addItem(mesh)
            self._items.append(mesh)

    def _render_station_ring(self, l, r, u, d, primary_b):
        brd  = math.radians(primary_b)
        fwd  = np.array([math.sin(brd), math.cos(brd), 0.0])
        n    = 48

        ring = _make_ring(np.zeros(3), fwd, l, r, u, d, n)
        closed = np.vstack([ring, ring[0]]).astype(np.float32)

        glow_ring = _make_ring(np.zeros(3), fwd, l * 1.05, r * 1.05, u * 1.05, d * 1.05, n)
        glow_closed = np.vstack([glow_ring, glow_ring[0]]).astype(np.float32)
        glow = gl.GLLinePlotItem(
            pos=glow_closed, color=(0.0, 0.55, 1.0, 0.28),
            width=9.0, antialias=True, mode="line_strip",
        )
        self._view.addItem(glow)
        self._items.append(glow)

        mid = gl.GLLinePlotItem(
            pos=closed, color=(0.0, 0.75, 1.0, 0.55),
            width=5.0, antialias=True, mode="line_strip",
        )
        self._view.addItem(mid)
        self._items.append(mid)

        outer = gl.GLLinePlotItem(
            pos=closed, color=(0.0, 0.88, 1.0, 1.0),
            width=2.0, antialias=True, mode="line_strip",
        )
        self._view.addItem(outer)
        self._items.append(outer)

    def _render_lrud_spokes(self, l, r, u, d, primary_b):
        brd     = math.radians(primary_b)
        fwd     = np.array([math.sin(brd), math.cos(brd), 0.0])
        world_up = np.array([0.0, 0.0, 1.0])
        right_vec = np.cross(fwd, world_up)
        n = np.linalg.norm(right_vec)
        right_vec = right_vec / n if n > 1e-9 else np.array([1.0, 0.0, 0.0])
        up_vec = np.cross(right_vec, fwd)
        n2 = np.linalg.norm(up_vec)
        up_vec = up_vec / n2 if n2 > 1e-9 else np.array([0.0, 0.0, 1.0])

        origin = np.zeros(3)
        spokes = [
            (origin, origin + right_vec * r,  (0.25, 1.0, 0.35, 1.0), "R"),
            (origin, origin - right_vec * l,  (1.0, 0.35, 0.35, 1.0), "L"),
            (origin, origin + up_vec * u,     (0.85, 0.85, 0.85, 1.0), "U"),
            (origin, origin - up_vec * d,     (1.0, 0.78, 0.15, 1.0), "D"),
        ]

        for start, end, color, label in spokes:
            pts = np.array([start, end], dtype=np.float32)
            line = gl.GLLinePlotItem(
                pos=pts, color=(*color[:3], 0.75), width=1.5,
                antialias=True, mode="line_strip",
            )
            self._view.addItem(line)
            self._items.append(line)

            dot = gl.GLScatterPlotItem(
                pos=end.reshape(1, 3).astype(np.float32),
                color=color, size=7, pxMode=True,
            )
            self._view.addItem(dot)
            self._items.append(dot)

    def _render_caveline(self, primary_b):
        brd = math.radians(primary_b)
        dx, dy = math.sin(brd), math.cos(brd)
        back  = np.array([-dx * 3.0, -dy * 3.0, 0.0])
        ahead = np.array([ dx * 12.0,  dy * 12.0, 0.0])
        pts   = np.array([back, np.zeros(3), ahead], dtype=np.float32)

        for width, alpha in [(9.0, 0.18), (4.0, 0.45), (1.8, 0.95)]:
            line = gl.GLLinePlotItem(
                pos=pts, color=(0.0, 0.82, 1.0, alpha),
                width=width, antialias=True, mode="line_strip",
            )
            self._view.addItem(line)
            self._items.append(line)

        station_dot = gl.GLScatterPlotItem(
            pos=np.zeros((1, 3), dtype=np.float32),
            color=(1.0, 1.0, 1.0, 1.0), size=9, pxMode=True,
        )
        self._view.addItem(station_dot)
        self._items.append(station_dot)

    def _render_floor(self, l, r, d, primary_b):
        brd      = math.radians(primary_b)
        fwd      = np.array([math.sin(brd), math.cos(brd), 0.0])
        world_up = np.array([0.0, 0.0, 1.0])
        right_vec = np.cross(fwd, world_up)
        n = np.linalg.norm(right_vec)
        right_vec = right_vec / n if n > 1e-9 else np.array([1.0, 0.0, 0.0])

        floor_z = -d
        fw, bk  = 12.0, 3.0

        verts = np.array([
            (-right_vec * l + np.array([0, 0, floor_z])).tolist(),
            ( right_vec * r + np.array([0, 0, floor_z])).tolist(),
            (fwd * fw + right_vec * r + np.array([0, 0, floor_z])).tolist(),
            (fwd * fw - right_vec * l + np.array([0, 0, floor_z])).tolist(),
        ], dtype=np.float32)
        faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.uint32)

        floor = gl.GLMeshItem(
            vertexes=verts, faces=faces,
            color=(0.04, 0.13, 0.32, 0.45),
            smooth=False, drawEdges=False, drawFaces=True,
            glOptions="translucent",
        )
        self._view.addItem(floor)
        self._items.append(floor)


    def _set_camera(self, primary_b, l, r, u, d):
        if not self._view:
            return

        brd  = math.radians(primary_b)
        dx   = math.sin(brd)
        dy   = math.cos(brd)

        cx = dx * 4.0
        cy = dy * 4.0
        self._view.opts["center"] = pg.Vector(cx, cy, 0.0)

        passage_span = max(l + r, u + d)
        dist = max(10.0, passage_span * 2.8 + 4.0)

        cam_azimuth = (primary_b + 210) % 360

        self._view.setCameraPosition(
            distance=dist,
            elevation=22,
            azimuth=cam_azimuth,
        )
        self._view.update()


    def _update_hud(self, station_name, depth_m, l, r, u, d, bearing):
        width_m  = l + r
        height_m = u + d
        card     = _bearing_cardinal(bearing)

        area_m2 = math.pi * (width_m / 2) * (height_m / 2)

        if width_m >= 1.0 and height_m >= 0.8:
            fit_text = "<span style='color:#19FF33;'>PASSABLE</span>"
        elif width_m >= 0.6 and height_m >= 0.5:
            fit_text = "<span style='color:#EBEB1A;'>TIGHT</span>"
        else:
            fit_text = "<span style='color:#E03030;'>RESTRICTION</span>"

        self._hud.setText(
            f"<b style='color:#E8ECF0; font-size:12px;'>{station_name}</b><br>"
            f"<span style='color:#3A5468;'>Depth   </span>"
            f"<span style='color:#4DA8F0;'>{depth_m:.1f} m ({depth_m * 3.281:.0f} ft)</span><br>"
            f"<span style='color:#3A5468;'>Width   </span>"
            f"<span style='color:#4DA8F0;'>{width_m:.2f} m</span>"
            f"<span style='color:#2A3A4A; font-size:9px;'>  L {l:.2f} + R {r:.2f}</span><br>"
            f"<span style='color:#3A5468;'>Height  </span>"
            f"<span style='color:#4DA8F0;'>{height_m:.2f} m</span>"
            f"<span style='color:#2A3A4A; font-size:9px;'>  U {u:.2f} + D {d:.2f}</span><br>"
            f"<span style='color:#3A5468;'>Area    </span>"
            f"<span style='color:#4DA8F0;'>{area_m2:.1f} m²</span><br>"
            f"<span style='color:#3A5468;'>Bearing </span>"
            f"<span style='color:#4DA8F0;'>{bearing:.0f}° {card}</span><br>"
            f"<span style='color:#3A5468;'>Profile </span>{fit_text}"
        )
        self._hud.adjustSize()


    def _clear_items(self):
        for item in self._items:
            try:
                self._view.removeItem(item)
            except Exception:
                pass
        self._items.clear()

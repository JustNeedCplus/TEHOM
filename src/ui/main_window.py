
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QToolBar, QStatusBar, QLabel, QLineEdit, QPushButton,
    QTextEdit, QComboBox, QFileDialog, QMessageBox, QGroupBox,
    QScrollArea, QFrame, QSlider, QCheckBox, QTabWidget,
    QProgressBar, QDialog, QFormLayout, QDialogButtonBox,
    QSpinBox, QDoubleSpinBox, QDateTimeEdit,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QAction, QIcon, QFont, QColor, QPalette

import numpy as np

from ..engine.cave_model import CaveSystem, CaveMetadata
from ..engine.compass_parser import parse_compass_dat, parse_compass_dat_string, generate_sample_dat
from ..engine.survex_parser import parse_survex
from ..engine.cave_renderer import get_cave_stats_text
from ..engine.procedural_cave import build_from_metadata
from ..ai.cave_assistant import CaveAssistant
from ..database.cave_database import CaveDatabase
from ..database.incident_database import IncidentDatabase
from ..ai.incident_scanner import IncidentScanner
from .incident_dialog import IncidentDatabaseDialog
from .sar_dialog import SARDialog
from .settings import AppSettings
from .passage_view import PassageViewWidget
from ..engine.voxel_builder import build_passage_data

try:
    import pyqtgraph as pg
    import pyqtgraph.opengl as gl
    pg.setConfigOptions(antialias=True)
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False

_COLOURS = [
    (0.00, 0.47, 0.84, 1.0),
    (0.94, 0.94, 0.94, 1.0),
    (0.20, 0.72, 0.90, 1.0),
    (0.96, 0.67, 0.22, 1.0),
    (0.58, 0.82, 0.98, 1.0),
    (0.75, 0.75, 0.75, 1.0),
    (0.40, 0.86, 0.78, 1.0),
]



class AICaveSearchWorker(QThread):
    result_ready = pyqtSignal(dict)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(self, assistant: CaveAssistant, cave_name: str):
        super().__init__()
        self.assistant = assistant
        self.cave_name = cave_name

    def run(self):
        try:
            data = self.assistant.lookup_cave(self.cave_name)
            self.result_ready.emit(data)
        except Exception as e:
            self.error_signal.emit(str(e))
        finally:
            self.finished_signal.emit()


class CaveBuildWorker(QThread):
    cave_ready = pyqtSignal(object)
    error_signal = pyqtSignal(str)

    def __init__(self, db_data: dict, db):
        super().__init__()
        self.db_data = db_data
        self.db = db

    def run(self):
        try:
            from ..engine.procedural_cave import build_from_metadata
            meta = self.db.to_metadata(self.db_data)
            cave = build_from_metadata(meta)
            self.cave_ready.emit(cave)
        except Exception as e:
            self.error_signal.emit(str(e))


class AIChatWorker(QThread):
    stream_chunk = pyqtSignal(str)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(self, assistant: CaveAssistant, message: str, history: list):
        super().__init__()
        self.assistant = assistant
        self.message = message
        self.history = history

    def run(self):
        try:
            for chunk in self.assistant.chat_stream(self.message, self.history):
                self.stream_chunk.emit(chunk)
        except Exception as e:
            self.error_signal.emit(str(e))
        finally:
            self.finished_signal.emit()



class CaveViewerWidget(QWidget):


    station_clicked = pyqtSignal(str)
    station_right_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._current_cave: Optional[CaveSystem] = None
        self._gl_items: list = []
        self._view = None
        self._station_positions = []
        self._tube_mode: bool = True
        self._incidents = {}
        self._incident_markers = []
        self._dead_reckoning_items = []
        self._press_pos = None

        if PYQTGRAPH_AVAILABLE:
            self._view = gl.GLViewWidget()
            self._view.setBackgroundColor(pg.mkColor("#141618"))
            self._view.setCameraPosition(distance=150, elevation=25, azimuth=45)
            grid = gl.GLGridItem()
            grid.scale(10, 10, 1)
            grid.setColor(pg.mkColor("#252A2E"))
            self._view.addItem(grid)
            self._layout.addWidget(self._view)
            self._view.mousePressEvent = self._on_mouse_press
            self._view.mouseReleaseEvent = self._on_mouse_release
            self._drag_started = False

            self._splash = QLabel(self)
            self._splash.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._splash.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._splash.setStyleSheet("color:#0078D4; font-size:14px; background:transparent;")
            self._splash.setText(
                "<b>TEHOM</b><br><br>"
                "Type a cave name above and click <b>Reconstruct Cave</b><br>"
                "<span style='color:#6B7A8A;'>or  File → Open Survey File (.dat / .svx)</span>"
            )
        else:
            self._splash = QLabel(
                "pyqtgraph not found.\n\nRun:\n  pip install pyqtgraph PyOpenGL\nThen restart."
            )
            self._splash.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._splash.setStyleSheet("color:#E05A33; font-size:13px; background:#141618;")
            self._layout.addWidget(self._splash)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._splash and self._splash.isVisible() and self._view:
            self._splash.setGeometry(0, 0, self.width(), self.height())


    def load_cave(self, cave: CaveSystem):
        if not PYQTGRAPH_AVAILABLE or self._view is None:
            return
        self._current_cave = cave

        for item in self._gl_items:
            try:
                self._view.removeItem(item)
            except Exception:
                pass
        self._gl_items.clear()

        stations = cave.get_all_stations()

        if self._tube_mode:
            self._render_tubes(cave)
        else:
            self._render_lines(cave, stations)
        self._render_cavelines(cave, stations)

        if stations:
            pos = np.array([s.position for s in stations.values()], dtype=np.float32)
            z_vals = pos[:, 2]
            z_min, z_max = z_vals.min(), z_vals.max()
            z_range = max(z_max - z_min, 0.001)
            t = np.clip((z_max - z_vals) / z_range, 0, 1)
            r = 0.0  * np.ones(len(t))
            g = 0.8  - 0.6 * t
            b = 1.0  - 0.2 * t
            a = 0.9  * np.ones(len(t))
            colors = np.stack([r, g, b, a], axis=1).astype(np.float32)
            dots = gl.GLScatterPlotItem(pos=pos, color=colors, size=5, pxMode=True)
            self._view.addItem(dots)
            self._gl_items.append(dots)
            self._station_positions = [(name, s.position) for name, s in stations.items()]

        self._render_station_labels(cave, stations)

        bbox_min, bbox_max = cave.get_bounding_box()
        if not np.all(bbox_min == bbox_max):
            centre = (bbox_min + bbox_max) / 2.0
            span   = float(np.max(bbox_max - bbox_min))
            self._view.opts["center"]   = pg.Vector(*centre.tolist())
            self._view.opts["distance"] = max(50.0, span * 1.8)
            self._view.setCameraPosition(elevation=25, azimuth=45)
            self._view.update()

        self._splash.hide()


    def _on_mouse_press(self, event):
        self._press_pos = event.pos()
        gl.GLViewWidget.mousePressEvent(self._view, event)

    def _on_mouse_release(self, event):
        from PyQt6.QtCore import Qt as _Qt
        gl.GLViewWidget.mouseReleaseEvent(self._view, event)
        if event.button() == _Qt.MouseButton.RightButton:
            if self._station_positions:
                self._pick_and_emit_right(event.pos().x(), event.pos().y())
            return
        if event.button() != _Qt.MouseButton.LeftButton:
            return
        if self._press_pos is None:
            return
        delta = event.pos() - self._press_pos
        if False:
            return
        if not self._station_positions:
            return
        self._pick_station(event.pos().x(), event.pos().y())

    def _pick_station(self, mouse_x, mouse_y):
        if not self._view or not self._station_positions:
            return
        import numpy as np
        w = self._view.width()
        h = self._view.height()
        try:
            mv = np.array(self._view.viewMatrix().copyDataTo(), dtype=np.float32).reshape(4,4).T
            opts = self._view.opts
            fov = opts.get("fov", 60.0)
            near = opts.get("near", 0.1)
            far = opts.get("far", 1000.0)
            aspect = w / h if h > 0 else 1.0
            f = 1.0 / np.tan(np.radians(fov) / 2.0)
            proj = np.zeros((4,4), dtype=np.float32)
            proj[0,0] = f / aspect
            proj[1,1] = f
            proj[2,2] = (far + near) / (near - far)
            proj[2,3] = (2 * far * near) / (near - far)
            proj[3,2] = -1.0
            mvp = proj @ mv
        except Exception as e:
            return
        best_name = None
        best_dist = float("inf")
        for name, pos3d in self._station_positions:
            p = np.array([float(pos3d[0]), float(pos3d[1]), float(pos3d[2]), 1.0], dtype=np.float32)
            clip = mvp @ p
            if abs(clip[3]) < 0.0001:
                continue
            nx = clip[0] / clip[3]
            ny = clip[1] / clip[3]
            sx = (nx + 1.0) * 0.5 * w
            sy = (1.0 - ny) * 0.5 * h
            dist = ((sx - mouse_x)**2 + (sy - mouse_y)**2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_name = name
        if best_name and best_dist < 450:
            self.station_clicked.emit(best_name)

    def _pick_and_emit_right(self, mouse_x, mouse_y):
        if not self._view or not self._station_positions:
            return
        import numpy as np
        cam_center = self._view.opts.get("center", pg.Vector(0,0,0))
        cam_dist   = self._view.opts.get("distance", 100.0)
        cam_el     = float(self._view.opts.get("elevation", 30.0))
        cam_az     = float(self._view.opts.get("azimuth", 45.0))
        el_r = np.radians(cam_el)
        az_r = np.radians(cam_az)
        cx = float(cam_center.x()) + cam_dist * np.cos(el_r) * np.sin(az_r)
        cy = float(cam_center.y()) + cam_dist * np.sin(el_r)
        cz = float(cam_center.z()) + cam_dist * np.cos(el_r) * np.cos(az_r)
        cam_pos = np.array([cx, cy, cz])
        to_centre = np.array([float(cam_center.x()), float(cam_center.y()),
                               float(cam_center.z())]) - cam_pos
        tc_norm = np.linalg.norm(to_centre)
        if tc_norm < 0.001:
            return
        forward = to_centre / tc_norm
        best_name = None
        best_dist = float("inf")
        for name, pos3d in self._station_positions:
            sp = np.array([float(pos3d[0]), float(pos3d[1]), float(pos3d[2])])
            to_st = sp - cam_pos
            dist_3d = np.linalg.norm(to_st)
            if dist_3d < 0.001:
                continue
            to_st_n = to_st / dist_3d
            dot = np.dot(to_st_n, forward)
            if dot < 0.1:
                continue
            screen_dist = np.linalg.norm(to_st_n - forward * dot) * dist_3d
            if screen_dist < best_dist:
                best_dist = screen_dist
                best_name = name
        if best_name and best_dist < 450:
            self.station_right_clicked.emit(best_name)

    def _render_tubes(self, cave):
        try:
            from ..engine.tube_renderer import build_tube_meshes
            meshes = build_tube_meshes(cave)
            print(f"TUBE: built {len(meshes)} meshes")
            for mesh_data in meshes:
                verts = mesh_data["vertices"]
                faces = mesh_data["faces"]
                color = mesh_data["color"]
                if len(verts) < 3 or len(faces) < 1:
                    continue
                mesh_item = gl.GLMeshItem(
                    vertexes=verts, faces=faces, color=color,
                    smooth=False, drawEdges=False, drawFaces=True,
                    glOptions="translucent",
                )
                self._view.addItem(mesh_item)
                self._gl_items.append(mesh_item)
        except Exception as e:
            print(f"Tube render error: {e}")
            stations = cave.get_all_stations()
            self._render_lines(cave, stations)

    def _render_lines(self, cave, stations):
        all_z = [s.position[2] for s in stations.values()] if stations else [0, 1]
        gz_min = min(all_z); gz_max = max(all_z)
        gz_range = max(gz_max - gz_min, 0.001)
        for i, survey in enumerate(cave.surveys):
            pts = self._survey_polyline(survey, stations)
            if len(pts) < 2:
                continue
            pts_arr = np.array(pts, dtype=np.float32)
            t = float(np.clip((gz_max - pts_arr[:, 2].mean()) / gz_range, 0, 1))
            colour = (0.0, max(0.0, 0.75 - 0.5*t), 1.0 - 0.25*t, 0.85)
            item = gl.GLLinePlotItem(pos=pts_arr, color=colour, width=2.5,
                                     antialias=True, mode="line_strip")
            self._view.addItem(item)
            self._gl_items.append(item)

    def _render_cavelines(self, cave, stations):
        if not stations:
            return
        all_z = [s.position[2] for s in stations.values()]
        gz_min = min(all_z)
        gz_max = max(all_z)
        gz_range = max(gz_max - gz_min, 0.001)

        _CAVELINE_COLORS = [
            (0.0, 0.9, 1.0, 1.0),
            (1.0, 0.9, 0.2, 1.0),
            (0.4, 1.0, 0.4, 1.0),
            (1.0, 0.5, 0.2, 1.0),
            (0.8, 0.5, 1.0, 1.0),
            (0.9, 0.9, 0.9, 1.0),
            (0.2, 0.8, 0.8, 1.0),
        ]

        for i, survey in enumerate(cave.surveys):
            pts = self._survey_polyline(survey, stations)
            if len(pts) < 2:
                continue
            pts_arr = np.array(pts, dtype=np.float32)
            color = _CAVELINE_COLORS[i % len(_CAVELINE_COLORS)]
            line = gl.GLLinePlotItem(
                pos=pts_arr, color=color, width=3.0,
                antialias=True, mode="line_strip"
            )
            self._view.addItem(line)
            self._gl_items.append(line)


    def clear_dead_reckoning(self):
        for item in self._dead_reckoning_items:
            try:
                self._view.removeItem(item)
            except Exception:
                pass
        self._dead_reckoning_items.clear()

    def update_dead_reckoning(self, result):
        if not PYQTGRAPH_AVAILABLE or self._view is None:
            return

        self.clear_dead_reckoning()

        station_map = {name: pos for name, pos in self._station_positions}

        for est in result.estimates:
            pos3d = station_map.get(est.station_name)
            if pos3d is None:
                continue

            p = est.probability
            if p <= 0.001:
                continue

            pos = np.array([[float(pos3d[0]), float(pos3d[1]), float(pos3d[2])]])

            if p > 0.50:
                core_col = (0.1, 1.0, 0.2, 1.0)
                halo_col = (0.1, 1.0, 0.2, 0.35)
                dot_size = 18
                halo_size = 38
            elif p > 0.20:
                core_col = (1.0, 0.92, 0.1, 1.0)
                halo_col = (1.0, 0.92, 0.1, 0.28)
                dot_size = 14
                halo_size = 30
            elif p > 0.06:
                core_col = (1.0, 0.55, 0.05, 1.0)
                halo_col = (1.0, 0.55, 0.05, 0.22)
                dot_size = 11
                halo_size = 24
            else:
                core_col = (0.7, 0.1, 0.1, 0.75)
                halo_col = (0.7, 0.1, 0.1, 0.15)
                dot_size = 8
                halo_size = 18

            if est.beyond_turn:
                lum = 0.35 + p * 0.25
                core_col = (lum, lum, lum, 0.7)
                halo_col = (lum, lum, lum, 0.15)

            halo = gl.GLScatterPlotItem(pos=pos, color=halo_col, size=halo_size, pxMode=True)
            halo._dr_station = est.station_name
            self._view.addItem(halo)
            self._dead_reckoning_items.append(halo)

            dot = gl.GLScatterPlotItem(pos=pos, color=core_col, size=dot_size, pxMode=True)
            dot._dr_station = est.station_name
            self._view.addItem(dot)
            self._dead_reckoning_items.append(dot)

    def _render_station_labels(self, cave, stations):
        if not stations:
            return

        from PyQt6.QtGui import QFont, QColor

        adj: dict[str, int] = {}
        for survey in cave.surveys:
            for shot in survey.shots:
                if shot.is_splay():
                    continue
                adj[shot.from_station] = adj.get(shot.from_station, 0) + 1
                adj[shot.to_station]   = adj.get(shot.to_station,   0) + 1

        key_stations = {
            name for name, deg in adj.items()
            if deg == 1 or deg > 2
        }

        for survey in cave.surveys:
            if survey.shots:
                key_stations.add(survey.shots[0].from_station)

        label_font  = QFont("Menlo", 9)
        label_color = QColor(160, 200, 220, 200)

        for name in key_stations:
            st = stations.get(name)
            if st is None:
                continue
            pos = st.position.astype(np.float32)
            label_pos = pos + np.array([0.4, 0.4, 0.5], dtype=np.float32)
            try:
                text_item = gl.GLTextItem(
                    pos=label_pos,
                    text=name,
                    color=label_color,
                    font=label_font,
                )
                self._view.addItem(text_item)
                self._gl_items.append(text_item)
            except Exception:
                pass

    def toggle_tube_mode(self):
        self._tube_mode = not self._tube_mode
        return self._tube_mode

    def reset_view(self):
        if not self._view:
            return
        if self._current_cave:
            bbox_min, bbox_max = self._current_cave.get_bounding_box()
            centre = (bbox_min + bbox_max) / 2.0
            span   = float(np.max(bbox_max - bbox_min)) if not np.all(bbox_min == bbox_max) else 100
            self._view.opts["center"]   = pg.Vector(*centre.tolist())
            self._view.opts["distance"] = max(50.0, span * 1.8)
            self._view.setCameraPosition(elevation=25, azimuth=45)
            self._view.update()

    def set_background(self, color: str):
        if self._view:
            self._view.setBackgroundColor(pg.mkColor(color))

    @staticmethod
    def _survey_polyline(survey, all_stations: dict) -> list:
        pts, seen = [], set()
        for shot in survey.shots:
            if shot.is_splay():
                continue
            for name in (shot.from_station, shot.to_station):
                if name not in seen:
                    st = all_stations.get(name)
                    if st is not None:
                        pts.append(st.position.tolist())
                        seen.add(name)
        return pts



class CaveInfoPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.title_label = QLabel("No cave loaded")
        self.title_label.setFont(QFont("Menlo", 11, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #E8ECF0;")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setStyleSheet(
            "background: #1A1D20; color: #9BAAB8; font-family: Menlo; font-size: 11px; border: none;"
        )
        layout.addWidget(self.info_text)

        self.hazards_box = QGroupBox("Hazards")
        self.hazards_box.setStyleSheet("color: #F0A444; border: 1px solid #2E2E2E;")
        hazards_layout = QVBoxLayout(self.hazards_box)
        self.hazards_label = QLabel("None listed")
        self.hazards_label.setWordWrap(True)
        self.hazards_label.setStyleSheet("color: #B07830;")
        hazards_layout.addWidget(self.hazards_label)
        layout.addWidget(self.hazards_box)

        layout.addStretch()

    def update_cave(self, cave: CaveSystem):
        self.title_label.setText(cave.name)
        self.info_text.setText(get_cave_stats_text(cave))
        if cave.metadata.hazards:
            self.hazards_label.setText("\n".join(f"• {h}" for h in cave.metadata.hazards))
        else:
            self.hazards_label.setText("None listed")

    def update_from_db(self, data: dict):
        name = data.get("name", "Unknown")
        self.title_label.setText(name)

        lines = [
            f"Country: {data.get('country', 'Unknown')}",
            f"Region:  {data.get('region', 'Unknown')}",
        ]
        lat, lon = data.get("latitude", 0), data.get("longitude", 0)
        if lat or lon:
            lines.append(f"GPS:     {lat:.4f}, {lon:.4f}")

        total = data.get("total_m") or data.get("total_surveyed_m", 0)
        if total:
            lines.append(f"Surveyed: {total:,.0f} m  ({total/1000:.1f} km)")

        depth = data.get("max_depth_m", 0)
        if depth:
            lines.append(f"Max depth: {depth:.0f} m ({depth*3.28084:.0f} ft)")

        vis = data.get("visibility_m", 0)
        if vis:
            lines.append(f"Visibility: {vis:.0f} m")

        lines.append(f"Water: {data.get('water_type', 'Unknown').capitalize()}")
        lines.append(f"Flow:  {data.get('flow', 'Unknown').capitalize()}")
        lines.append(f"Access: {data.get('access', 'Unknown')}")

        if data.get("description"):
            lines.append(f"\n{data['description']}")

        passages = data.get("passages") or data.get("known_passages", [])
        if passages:
            lines.append(f"\nKnown passages:")
            for p in passages:
                lines.append(f"  • {p}")

        self.info_text.setText("\n".join(lines))

        hazards = data.get("hazards", [])
        if hazards:
            self.hazards_label.setText("\n".join(f"• {h}" for h in hazards))
        else:
            self.hazards_label.setText("None listed")


class AIChatPanel(QWidget):

    send_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        header = QLabel("AI Cave Assistant")
        header.setFont(QFont("Menlo", 10, QFont.Weight.Bold))
        header.setStyleSheet("color: #9BAAB8; padding: 4px; letter-spacing: 1px;")
        layout.addWidget(header)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet(
            "background: #141618; color: #9BAAB8; font-family: Menlo; font-size: 11px; border: none;"
        )
        self.chat_display.setPlaceholderText("AI responses will appear here...")
        layout.addWidget(self.chat_display)

        input_row = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask about any cave, SAR scenario, dive planning...")
        self.input_field.setStyleSheet(
            "background: #1A1D20; color: #E8ECF0; border: 1px solid #2E3540; padding: 4px;"
        )
        self.input_field.returnPressed.connect(self._send)
        input_row.addWidget(self.input_field)

        self.send_btn = QPushButton("Send")
        self.send_btn.setStyleSheet(
            "background: #0078D4; color: #fff; font-weight: bold; padding: 4px 10px; border: none;"
        )
        self.send_btn.clicked.connect(self._send)
        input_row.addWidget(self.send_btn)
        layout.addLayout(input_row)

        quick_layout = QHBoxLayout()
        for label, prompt in [
            ("SAR Mode", "Generate a SAR briefing for the currently loaded cave"),
            ("Dive Plan", "What are the key safety considerations for diving this cave?"),
            ("History", "What is the discovery and survey history of this cave?"),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(
                "background: #1E2226; color: #6B7A8A; font-size: 10px; padding: 3px 6px;"
                "border: 1px solid #2E3540;"
            )
            btn.clicked.connect(lambda checked, p=prompt: self._send_quick(p))
            quick_layout.addWidget(btn)
        layout.addLayout(quick_layout)

    def _send(self):
        text = self.input_field.text().strip()
        if text:
            self.send_requested.emit(text)
            self.input_field.clear()

    def _send_quick(self, prompt: str):
        self.send_requested.emit(prompt)

    def append_user(self, text: str):
        self.chat_display.append(f'<span style="color:#E8ECF0;">You: {text}</span>')

    def begin_assistant_response(self):
        self.chat_display.append('<span style="color:#0078D4;">AI: </span>')

    def append_chunk(self, chunk: str):
        cursor = self.chat_display.textCursor()
        from PyQt6.QtGui import QTextCursor
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(chunk)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()

    def end_response(self):
        self.chat_display.append("")

    def set_busy(self, busy: bool):
        self.send_btn.setEnabled(not busy)
        self.input_field.setEnabled(not busy)



class DeadReckoningPanel(QWidget):

    run_now = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        header = QLabel("Dead Reckoning — Search Zone")
        header.setFont(QFont("Menlo", 10, QFont.Weight.Bold))
        header.setStyleSheet("color: #F0A444; padding: 4px; letter-spacing: 1px;")
        layout.addWidget(header)

        note = QLabel(
            "Enable SAR Incident Mode → right-click a station → mark incident.\n\n"
            "Red dot   = last known position (where you clicked).\n"
            "Heat map  = where the diver PROBABLY IS NOW,\n"
            "  based on elapsed time x swim speed from the red dot.\n"
            "  Heat appears ahead of the red dot — this is correct."
        )
        note.setStyleSheet("color: #6B7A8A; font-size: 10px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.status_box = QGroupBox("Incident Status")
        status_layout = QVBoxLayout(self.status_box)
        self.elapsed_label = QLabel("No active incident")
        self.elapsed_label.setStyleSheet("color: #E03030; font-size: 11px; font-weight: bold;")
        status_layout.addWidget(self.elapsed_label)
        self.gas_label = QLabel("")
        self.gas_label.setStyleSheet("color: #F0A444; font-size: 11px;")
        self.gas_label.setWordWrap(True)
        status_layout.addWidget(self.gas_label)
        self.range_label = QLabel("")
        self.range_label.setStyleSheet("color: #9BAAB8; font-size: 10px;")
        self.range_label.setWordWrap(True)
        status_layout.addWidget(self.range_label)
        layout.addWidget(self.status_box)

        prob_box = QGroupBox("Probable Locations (ranked)")
        prob_layout = QVBoxLayout(prob_box)
        self.prob_display = QTextEdit()
        self.prob_display.setReadOnly(True)
        self.prob_display.setFixedHeight(280)
        self.prob_display.setStyleSheet(
            "background: #141618; color: #9BAAB8; font-family: Menlo; "
            "font-size: 10px; border: none;"
        )
        prob_layout.addWidget(self.prob_display)
        layout.addWidget(prob_box)

        legend = QLabel(
            "<span style='color:#19FF33;'>■</span> High (&gt;50%)  "
            "<span style='color:#EBEB1A;'>■</span> Medium (&gt;20%)  "
            "<span style='color:#FF8C0D;'>■</span> Low (&gt;6%)  "
            "<span style='color:#B21919;'>■</span> Edge"
        )
        legend.setStyleSheet("font-size: 10px; color: #6B7A8A;")
        legend.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(legend)

        update_btn = QPushButton("Update Now")
        update_btn.setStyleSheet(
            "background: #1E2A1E; color: #19FF33; border: 1px solid #2E4A2E; "
            "font-size: 11px; padding: 4px 10px;"
        )
        update_btn.clicked.connect(self.run_now.emit)
        layout.addWidget(update_btn)

        layout.addStretch()

    def show_no_incident(self):
        self.elapsed_label.setText("No active incident")
        self.gas_label.setText("")
        self.range_label.setText("")
        self.prob_display.clear()

    def update_result(self, result, incident_info: dict):
        diver   = incident_info.get("name", "Unknown Diver")
        station = result.entry_station

        h = int(result.elapsed_min) // 60
        m = int(result.elapsed_min) % 60
        elapsed_str = f"{h}h {m:02d}m" if h else f"{m}m"

        self.elapsed_label.setText(f"ACTIVE — {diver} | {elapsed_str} elapsed")

        total_gas = result.gas_used_l + result.gas_remaining_l
        gas_pct   = max(0, result.gas_remaining_l / max(total_gas, 1) * 100)
        time_left = max(0, result.exhaustion_time_min - result.elapsed_min)

        if result.gas_remaining_l <= 0:
            self.gas_label.setStyleSheet("color:#E03030;font-size:11px;font-weight:bold;")
            self.gas_label.setText("GAS EXHAUSTED — recovery operation")
        elif result.elapsed_min > result.exhaustion_time_min * 0.75:
            self.gas_label.setStyleSheet("color:#E03030;font-size:11px;font-weight:bold;")
            self.gas_label.setText(
                f"Gas critical — ~{result.gas_remaining_l:.0f} L ({gas_pct:.0f}%)\n"
                f"   Est. exhaustion in {time_left:.0f} min"
            )
        else:
            self.gas_label.setStyleSheet("color:#F0A444;font-size:11px;")
            self.gas_label.setText(
                f"Gas ~{result.gas_remaining_l:.0f} L remaining ({gas_pct:.0f}%)\n"
                f"Exhaustion in ~{time_left:.0f} min"
            )

        expected_dist = result.elapsed_min * 15.0
        top = next((e for e in result.estimates if e.probability > 0.001), None)
        spatial_lines = [
            f"Last seen:  {station}",
            f"Time elapsed: {elapsed_str}",
            f"Expected swim: ~{expected_dist:.0f} m from entry",
            f"Turn point: {result.turn_distance_m:.0f} m from entry",
            f"Max range:  {result.max_range_m:.0f} m from entry",
        ]
        if top:
            spatial_lines.append(f"Top target: {top.station_name}  ({top.distance_m:.0f} m from entry)")
        self.range_label.setText("\n".join(spatial_lines))

        lines = [
            "<span style='color:#6B7A8A;font-size:9px;'>"
            "Heat = where diver probably IS NOW (not where last seen).<br>"
            f"Red dot = last seen at <b style='color:#E8ECF0;'>{station}</b>. "
            f"After {elapsed_str} the search zone is ~{expected_dist:.0f} m ahead."
            "</span><br>"
        ]

        shown = [e for e in result.estimates if e.probability > 0.001][:15]
        for est in shown:
            pct = est.probability * 100
            if pct > 50:
                col, tier = "#19FF33", "HIGH"
            elif pct > 20:
                col, tier = "#EBEB1A", "MED "
            elif pct > 6:
                col, tier = "#FF8C0D", "LOW "
            else:
                col, tier = "#B21919", "EDGE"

            flag = ""
            if est.beyond_turn:
                flag = " <span style='color:#888;'>[past turn]</span>"
            elif est.at_surface:
                flag = " <span style='color:#88F;'>[air bell?]</span>"

            lines.append(
                f'<span style="color:{col};">{tier}</span>  '
                f'<b>{est.station_name}</b>  '
                f'{pct:4.1f}%  '
                f'<span style="color:#4A6A7A;">{est.distance_m:.0f} m from entry  '
                f'{est.avg_depth_m:.1f} m dep</span>'
                f'{flag}'
            )

        self.prob_display.setHtml(
            "<style>body{font-family:Menlo;font-size:10px;color:#9BAAB8;line-height:1.5;}"
            "b{color:#E8ECF0;}</style>"
            + "<br>".join(lines)
        )



class ApiKeyDialog(QDialog):
    def __init__(self, current_key: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Anthropic API Key")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)

        self.key_input = QLineEdit(current_key)
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("sk-ant-...")
        layout.addRow("API Key:", self.key_input)

        note = QLabel(
            "Get your key at console.anthropic.com\n"
            "The key is stored only in memory for this session."
        )
        note.setStyleSheet("color: #6B7A8A; font-size: 10px;")
        layout.addRow(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    @property
    def api_key(self) -> str:
        return self.key_input.text().strip()




class CaveDatabaseDialog(QDialog):
    cave_selected = pyqtSignal(str)

    def __init__(self, caves, parent=None):
        super().__init__(parent)
        self._caves = caves
        self.setWindowTitle("Cave Database")
        self.setMinimumSize(660, 480)
        self.setStyleSheet("""
            QDialog { background: #1A1D20; color: #9BAAB8; }
            QLineEdit { background: #141618; color: #E8ECF0; border: 1px solid #2E3540; border-radius: 2px; padding: 5px 10px; font-size: 12px; }
            QLineEdit:focus { border-color: #0078D4; }
            QTableWidget { background: #141618; color: #9BAAB8; border: 1px solid #252A2E; gridline-color: #252A2E; font-size: 12px; outline: none; }
            QTableWidget::item { padding: 6px 10px; border-bottom: 1px solid #1E2226; }
            QTableWidget::item:selected { background: #1E2A3A; color: #E8ECF0; }
            QTableWidget::item:hover { background: #1E2226; }
            QHeaderView::section { background: #1E2226; color: #6B7A8A; font-size: 9px; letter-spacing: 1px; padding: 6px 10px; border: none; border-bottom: 1px solid #2E3540; }
            QPushButton { background: #1E2226; color: #9BAAB8; border: 1px solid #2E3540; border-radius: 2px; padding: 5px 14px; font-size: 12px; }
            QPushButton:hover { background: #252A2E; color: #E8ECF0; }
            QPushButton
            QPushButton
            QScrollBar:vertical { background: #141618; width: 6px; border: none; }
            QScrollBar::handle:vertical { background: #2E3540; border-radius: 3px; }
        """)
        self._build_ui()

    def _build_ui(self):
        from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)
        header_row = QHBoxLayout()
        title = QLabel("Cave Database")
        title.setFont(QFont(".AppleSystemUIFont", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #E8ECF0;")
        header_row.addWidget(title)
        self._count_label = QLabel(f"{len(self._caves)} caves")
        self._count_label.setStyleSheet("color: #6B7A8A; font-size: 11px;")
        header_row.addWidget(self._count_label, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header_row)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search caves, countries, regions...")
        self._search.setFixedHeight(32)
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Cave", "Country", "Region", "Surveyed", "Max Depth"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._table)
        self._populate(self._caves)
        btn_row = QHBoxLayout()
        self._selected_label = QLabel("No cave selected")
        self._selected_label.setStyleSheet("color: #6B7A8A; font-size: 11px;")
        btn_row.addWidget(self._selected_label)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        load_btn = QPushButton("Reconstruct Cave")
        load_btn.setObjectName("btn_load")
        load_btn.clicked.connect(self._on_load)
        btn_row.addWidget(load_btn)
        layout.addLayout(btn_row)
        self._table.selectionModel().selectionChanged.connect(self._on_selection)

    def _populate(self, caves):
        from PyQt6.QtWidgets import QTableWidgetItem
        self._table.setRowCount(len(caves))
        for row, c in enumerate(caves):
            name = c.get("name", "-")
            country = c.get("country", "-")
            region = c.get("region", "-")
            total = c.get("total_m", 0)
            depth = c.get("max_depth_m", 0)
            for col, text in enumerate([name, country, region, f"{total:,.0f} m" if total else "-", f"{depth:.0f} m" if depth else "-"]):
                item = QTableWidgetItem(text)
                item.setData(256, name)
                if col == 0: item.setForeground(QColor("#E8ECF0"))
                elif col in (3, 4): item.setForeground(QColor("#0078D4"))
                self._table.setItem(row, col, item)
            self._table.setRowHeight(row, 34)

    def _filter(self, text):
        text = text.lower()
        self._populate([c for c in self._caves if text in c.get("name","").lower() or text in c.get("country","").lower() or text in c.get("region","").lower()])

    def _on_selection(self):
        rows = self._table.selectedItems()
        if rows:
            self._selected_label.setText(f"Selected: {rows[0].data(256)}")
            self._selected_label.setStyleSheet("color: #9BAAB8; font-size: 11px;")

    def _on_double_click(self, item):
        name = item.data(256)
        if name:
            self.cave_selected.emit(name)
            self.accept()

    def _on_load(self):
        rows = self._table.selectedItems()
        if rows:
            self.cave_selected.emit(rows[0].data(256))
            self.accept()


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TEHOM — Underwater Cave Mapping & SAR System")
        self.setMinimumSize(1200, 750)

        self._cave: Optional[CaveSystem] = None
        self._settings = AppSettings()
        self._ai_key = self._settings.get_api_key() or os.getenv("ANTHROPIC_API_KEY", "")
        self._assistant = CaveAssistant(self._ai_key)
        self._db = CaveDatabase()
        self._incident_db = IncidentDatabase()
        self._incident_scanner = IncidentScanner(self._ai_key)
        self._chat_history: list[dict] = []
        self._worker: Optional[QThread] = None
        self._sar_incident_mode = False
        self._incidents = {}
        self._incident_markers = []


        self._apply_dark_theme()
        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self._statusbar_setup()

        self._dr_timer = QTimer(self)
        self._dr_timer.setInterval(60_000)
        self._dr_timer.timeout.connect(self._update_dead_reckoning)


    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color:
                color:
                font-family: "Helvetica Neue", "Helvetica Neue", sans-serif;
            }
            QMenuBar {
                background:
                color:
                border-bottom: 1px solid
                font-size: 12px;
            }
            QMenuBar::item { padding: 4px 10px; }
            QMenuBar::item:selected { background: #1E2226; color: #E8ECF0; }
            QMenu {
                background:
                border: 1px solid
                color:
                font-size: 12px;
            }
            QMenu::item { padding: 5px 20px; }
            QMenu::item:selected { background: #1E2A3A; color: #E8ECF0; }
            QMenu::separator { height: 1px; background: #252A2E; margin: 2px 0; }
            QToolBar {
                background:
                border-bottom: 1px solid
                spacing: 2px;
                padding: 2px 4px;
            }
            QToolBar QToolButton {
                color:
                background: transparent;
                padding: 3px 10px;
                border: none;
                font-size: 12px;
            }
            QToolBar QToolButton:hover {
                color:
                background:
            }
            QSplitter::handle { background: #252A2E; width: 1px; }
            QGroupBox {
                border: 1px solid
                border-radius: 2px;
                margin-top: 10px;
                padding-top: 8px;
                color:
            }
            QGroupBox::title {
                color:
                font-size: 10px;
                letter-spacing: 1px;
                text-transform: uppercase;
                subcontrol-origin: margin;
                padding: 0 4px;
            }
            QTabWidget::pane {
                border: none;
                border-top: 1px solid
            }
            QTabBar::tab {
                background:
                color:
                padding: 5px 16px;
                border: none;
                border-bottom: 2px solid transparent;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                color:
                border-bottom: 2px solid
                background:
            }
            QTabBar::tab:hover:!selected { color: #9BAAB8; background: #1A1D20; }
            QScrollBar:vertical {
                background:
                width: 6px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background:
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover { background: #0078D4; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QPushButton {
                background:
                color:
                border: 1px solid
                padding: 4px 10px;
                font-size: 12px;
                border-radius: 2px;
            }
            QPushButton:hover {
                background:
                color:
                border-color:
            }
            QPushButton:pressed { background: #141618; }
            QLineEdit {
                background:
                color:
                border: 1px solid
                border-radius: 2px;
                padding: 4px 6px;
                font-size: 12px;
            }
            QLineEdit:focus { border-color: #0078D4; }
            QTextEdit {
                background:
                color:
                border: none;
                font-size: 12px;
            }
            QProgressBar {
                background:
                border: none;
                height: 3px;
            }
            QProgressBar::chunk { background: #0078D4; }
            QStatusBar {
                background:
                border-top: 1px solid
                color:
                font-size: 11px;
            }
        """)


    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        search_bar = self._build_search_bar()
        main_layout.addLayout(search_bar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(4)
        main_layout.addWidget(self.progress_bar)

        outer_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(outer_splitter)

        left_splitter = QSplitter(Qt.Orientation.Vertical)
        self.viewer = CaveViewerWidget()
        self.viewer.station_clicked.connect(self._on_station_clicked)
        self.viewer.station_right_clicked.connect(self._on_station_right_clicked)
        left_splitter.addWidget(self.viewer)
        self.voxel_view = PassageViewWidget()
        self.voxel_view.setMinimumHeight(200)
        left_splitter.addWidget(self.voxel_view)
        left_splitter.setSizes([700, 0])
        left_splitter.setCollapsible(0, False)
        left_splitter.setCollapsible(1, True)
        self._left_splitter = left_splitter
        outer_splitter.addWidget(left_splitter)

        right_panel = QTabWidget()
        right_panel.setFixedWidth(320)
        self.info_panel = CaveInfoPanel()
        right_panel.addTab(self.info_panel, "Cave Info")
        self.chat_panel = AIChatPanel()
        self.chat_panel.send_requested.connect(self._handle_chat)
        right_panel.addTab(self.chat_panel, "AI Assistant")
        self.dr_panel = DeadReckoningPanel()
        self.dr_panel.run_now.connect(self._update_dead_reckoning)
        right_panel.addTab(self.dr_panel, "Dead Reckoning")
        self._right_panel = right_panel
        outer_splitter.addWidget(right_panel)
        outer_splitter.setSizes([880, 320])

    def _build_search_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()

        icon_label = QLabel("")
        icon_label.setFont(QFont("Arial", 16))
        row.addWidget(icon_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Enter cave name (e.g. 'Ginnie Springs', 'Tham Luang', 'Dos Ojos')"
        )
        self.search_input.setMinimumHeight(34)
        self.search_input.setStyleSheet(
            "background: #1A1D20; color: #E8ECF0; border: 1px solid #2E3540; "
            "border-radius: 2px; padding: 4px 10px; font-size: 13px;"
        )
        self.search_input.returnPressed.connect(self._search_cave)
        row.addWidget(self.search_input)

        self.search_btn = QPushButton("Reconstruct Cave")
        self.search_btn.setMinimumHeight(34)
        self.search_btn.setStyleSheet(
            "background: #0078D4; color: #fff; font-weight: 600; border: none; "
            "font-size: 12px; padding: 4px 18px; border-radius: 2px;"
        )
        self.search_btn.clicked.connect(self._search_cave)
        row.addWidget(self.search_btn)

        self._sar_btn = QPushButton("SAR Mode")
        self._sar_btn.setMinimumHeight(34)
        self._sar_btn.setStyleSheet(
            "background: #1E1610; color: #F0A444; font-weight: 600; border: 1px solid #3A2A10; "
            "font-size: 12px; padding: 4px 12px; border-radius: 2px;"
        )
        self._sar_btn.clicked.connect(self._sar_mode)
        row.addWidget(self._sar_btn)

        self._cave_search_widgets = [icon_label, self.search_input, self.search_btn, self._sar_btn]

        return row


    def _build_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        open_action = QAction("Open Survey File (.dat, .svx)...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_survey_file)
        file_menu.addAction(open_action)

        demo_action = QAction("Load Demo Cave", self)
        demo_action.triggered.connect(self._load_demo)
        file_menu.addAction(demo_action)

        file_menu.addSeparator()
        export_action = QAction("Export Stats as Text...", self)
        export_action.triggered.connect(self._export_stats)
        file_menu.addAction(export_action)

        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = menubar.addMenu("View")
        reset_view = QAction("Reset Camera", self)
        reset_view.setShortcut("R")
        reset_view.triggered.connect(lambda: self.viewer.reset_view())
        view_menu.addAction(reset_view)

        tools_menu = menubar.addMenu("Tools")
        db_action = QAction("Browse Cave Database...", self)
        db_action.triggered.connect(self._browse_database)
        tools_menu.addAction(db_action)

        sar_action = QAction("SAR Planning Tool...", self)
        sar_action.setShortcut("Ctrl+Shift+S")
        sar_action.triggered.connect(self._sar_mode)
        tools_menu.addAction(sar_action)

        gas_action = QAction("Quick Gas Calculator...", self)
        gas_action.triggered.connect(self._quick_gas)
        tools_menu.addAction(gas_action)

        settings_menu = menubar.addMenu("Settings")
        api_action = QAction("Set Anthropic API Key...", self)
        api_action.triggered.connect(self._set_api_key)
        settings_menu.addAction(api_action)

        depth_color_action = QAction("Toggle Depth Coloring", self)
        depth_color_action.setCheckable(True)
        depth_color_action.setChecked(self._settings.get_depth_coloring())
        depth_color_action.triggered.connect(self._toggle_depth_coloring)
        settings_menu.addAction(depth_color_action)
        self._depth_color_action = depth_color_action

        help_menu = menubar.addMenu("Help")
        about_action = QAction("About TEHOM", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        help_menu.addSeparator()
        update_action = QAction("Check for Updates...", self)
        update_action.triggered.connect(self._check_for_updates)
        help_menu.addAction(update_action)

        open_log_action = QAction("Open App Log", self)
        open_log_action.triggered.connect(self._open_log)
        help_menu.addAction(open_log_action)


    def _build_toolbar(self):
        tb = QToolBar("Tools")
        tb.setObjectName("toolbar_tools")
        tb.setIconSize(QSize(24, 24))
        self.addToolBar(tb)

        for label, slot, tooltip in [
            ("Open File", self._open_survey_file, "Open a Compass .dat or Survex .svx file"),
            ("Demo Cave", self._load_demo, "Load a built-in demo cave"),
            ("Reset View", lambda: self.viewer.reset_view(), "Reset camera to fit cave"),
            ("Browse DB", self._browse_database, "Browse the cave database"),
            ("SAR Mode", self._sar_mode, "Open Search & Rescue Planning tool"),
            ("Print Briefing", self._print_briefing, "Generate SAR pre-dive briefing PDF"),
        ]:
            action = QAction(label, self)
            action.setToolTip(tooltip)
            action.triggered.connect(slot)
            tb.addAction(action)

        tb.addSeparator()

        self._sar_mode_action = QAction("SAR Incident: OFF", self)
        self._sar_mode_action.setToolTip("Toggle SAR Incident Mode — right-click stations to mark incident points")
        self._sar_mode_action.toggled.connect(self._on_sar_mode_toggled)
        self._sar_mode_action.setCheckable(True)
        tb.addAction(self._sar_mode_action)

        clear_action = QAction("Clear Incidents", self)
        clear_action.setToolTip("Remove all incident markers")
        clear_action.triggered.connect(self._clear_incidents)
        tb.addAction(clear_action)

        tb.addSeparator()

        self._tube_action = QAction("3D Passages: ON", self)
        self._tube_action.setToolTip("Toggle between 3D tube passages and line view")
        self._tube_action.triggered.connect(self._toggle_tube_mode)
        tb.addAction(self._tube_action)

        tb.addSeparator()

        incidents_action = QAction("Incident DB", self)
        incidents_action.setToolTip("Upload and browse past incident reports")
        incidents_action.triggered.connect(self._open_incident_db)
        tb.addAction(incidents_action)

        dr_action = QAction("DR Update", self)
        dr_action.setToolTip("Run dead reckoning update now")
        dr_action.triggered.connect(self._update_dead_reckoning)
        tb.addAction(dr_action)



    def _on_station_right_clicked(self, station_name):
        if self._sar_incident_mode:
            self._status(f"Station selected: {station_name} — opening incident dialog...")
            self._show_incident_dialog(station_name)

    def _toggle_tube_mode(self):
        is_on = self.viewer.toggle_tube_mode()
        self._tube_action.setText("3D Passages: ON" if is_on else "3D Passages: OFF")
        if self._cave:
            self.viewer.load_cave(self._cave)

    def _open_incident_db(self):
        cave_name = self._cave.name if self._cave else ""
        dlg = IncidentDatabaseDialog(
            self._incident_db, self._incident_scanner,
            cave_name=cave_name, parent=self
        )
        dlg.show_on_map.connect(self._show_historical_incident_on_map)
        dlg.exec()

    def _show_historical_incident_on_map(self, report):
        import pyqtgraph.opengl as gl
        if not report.last_known_station:
            self._status("No station data for this incident — cannot show on map")
            return

        pos3d = None
        for name, p in self.viewer._station_positions:
            if name.upper() == report.last_known_station.upper():
                pos3d = p
                break

        if pos3d is None:
            for name, p in self.viewer._station_positions:
                if report.last_known_station.upper() in name.upper():
                    pos3d = p
                    break

        if pos3d is None:
            self._status(
                f"Station '{report.last_known_station}' not found on current map — "
                "load the relevant cave first"
            )
            return

        pos = np.array([[float(pos3d[0]), float(pos3d[1]), float(pos3d[2])]])

        marker = gl.GLScatterPlotItem(
            pos=pos, color=(1.0, 0.85, 0.0, 1.0), size=16, pxMode=True
        )
        marker._incident_station = f"HIST_{report.id}"
        self.viewer._view.addItem(marker)
        self._incident_markers.append(marker)

        halo = gl.GLScatterPlotItem(
            pos=pos, color=(1.0, 0.85, 0.0, 0.3), size=30, pxMode=True
        )
        halo._incident_station = f"HIST_{report.id}"
        self.viewer._view.addItem(halo)
        self._incident_markers.append(halo)

        self._status(
            f"Historical incident — {report.cave_name} | "
            f"{report.outcome.upper()} | {report.incident_date or 'Unknown date'} | "
            f"Station {report.last_known_station}"
        )
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self.status_label.setStyleSheet("color: #C47A1A;"))

    def _on_sar_mode_toggled(self, checked):
        self._sar_incident_mode = checked
        if checked:
            self._sar_mode_action.setText("SAR Incident: ON")
            self._dr_timer.start()
            self._status("SAR Incident Mode ON — right-click a station dot to mark incident")
        else:
            self._sar_mode_action.setText("SAR Incident: OFF")
            self._dr_timer.stop()
            self.viewer.clear_dead_reckoning()
            self.dr_panel.show_no_incident()
            self._status("SAR Incident Mode OFF")

    def _toggle_sar_incident_mode(self):
        self._sar_mode_action.setChecked(not self._sar_incident_mode)

    def _clear_incidents(self):
        for marker in self._incident_markers:
            try:
                self.viewer._view.removeItem(marker)
            except Exception:
                pass
        self._incident_markers.clear()
        self._incidents.clear()
        self.viewer.clear_dead_reckoning()
        self.dr_panel.show_no_incident()
        self._status("Incident markers cleared")

    def _update_dead_reckoning(self):
        if not self._cave or not self._incidents:
            self.viewer.clear_dead_reckoning()
            self.dr_panel.show_no_incident()
            return

        from ..engine.dead_reckoning import compute, IncidentParams
        from datetime import datetime

        latest_station = list(self._incidents.keys())[-1]
        inc = self._incidents[latest_station]

        try:
            entry_time = datetime.strptime(inc["entry_time"], "%Y-%m-%d  %H:%M")
        except Exception:
            entry_time = datetime.now()

        gas_bar = inc.get("gas_bar", 200)
        tank_vol = inc.get("tank_vol", 11.1)
        total_gas_l = float(gas_bar) * float(tank_vol)

        params = IncidentParams(
            entry_station=latest_station,
            entry_time=entry_time,
            total_gas_litres=total_gas_l,
            sac_rate_lmin=20.0,
            swim_speed_mmin=15.0,
        )

        try:
            result = compute(self._cave, params)
            self.viewer.update_dead_reckoning(result)
            self.dr_panel.update_result(result, inc)

            for i in range(self._right_panel.count()):
                if self._right_panel.tabText(i) == "Dead Reckoning":
                    self._right_panel.setCurrentIndex(i)
                    break

            top = result.estimates[0] if result.estimates else None
            if top and top.probability > 0:
                h = int(result.elapsed_min) // 60
                m = int(result.elapsed_min) % 60
                elapsed_str = f"{h}h {m:02d}m" if h else f"{m}m"
                self._status(
                    f"DR updated — {inc.get('name', '?')} | {elapsed_str} elapsed | "
                    f"Highest prob: {top.station_name} ({top.probability*100:.1f}%) "
                    f"at {top.distance_m:.0f}m"
                )
        except Exception as e:
            self._status(f"Dead reckoning error: {e}", error=True)

    def _pick_incident_station(self, mouse_x, mouse_y):
        if not self._view or not self._station_positions:
            return
        import numpy as np
        cam_center = self._view.opts.get("center", pg.Vector(0,0,0))
        cam_dist   = self._view.opts.get("distance", 100.0)
        cam_el     = float(self._view.opts.get("elevation", 30.0))
        cam_az     = float(self._view.opts.get("azimuth", 45.0))
        el_r = np.radians(cam_el)
        az_r = np.radians(cam_az)
        cx = float(cam_center.x()) + cam_dist * np.cos(el_r) * np.sin(az_r)
        cy = float(cam_center.y()) + cam_dist * np.sin(el_r)
        cz = float(cam_center.z()) + cam_dist * np.cos(el_r) * np.cos(az_r)
        cam_pos = np.array([cx, cy, cz])
        to_centre = np.array([float(cam_center.x()), float(cam_center.y()),
                               float(cam_center.z())]) - cam_pos
        tc_norm = np.linalg.norm(to_centre)
        if tc_norm < 0.001:
            return
        forward = to_centre / tc_norm
        best_name = None
        best_dist = float("inf")
        for name, pos3d in self._station_positions:
            sp = np.array([float(pos3d[0]), float(pos3d[1]), float(pos3d[2])])
            to_st = sp - cam_pos
            dist_3d = np.linalg.norm(to_st)
            if dist_3d < 0.001:
                continue
            to_st_n = to_st / dist_3d
            dot = np.dot(to_st_n, forward)
            if dot < 0.1:
                continue
            screen_dist = np.linalg.norm(to_st_n - forward * dot) * dist_3d
            if screen_dist < best_dist:
                best_dist = screen_dist
                best_name = name
        if best_name and best_dist < 450:
            self._show_incident_dialog(best_name)

    def _show_incident_dialog(self, station_name):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox
        from PyQt6.QtCore import QDateTime

        depth_str = "—"
        if self._cave:
            stations = self._cave.get_all_stations()
            st = stations.get(station_name)
            if st:
                z_vals = [abs(s.z) for s in stations.values()]
                z_max  = max(z_vals) if z_vals else 1.0
                meta   = getattr(self._cave, "metadata", None)
                real_max = meta.max_depth_m if meta else z_max
                depth_str = f"{abs(st.z) / z_max * real_max:.1f} m"

        dlg = QDialog(self)
        dlg.setWindowTitle(f"SAR Incident — Station {station_name}")
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet("""
            QDialog { background: #141618; color: #E8ECF0; }
            QLabel  { color: #9BAAB8; font-size: 12px; }
            QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QDateTimeEdit {
                background:
                border-radius: 2px; padding: 4px 8px; font-size: 12px;
            }
            QPushButton {
                background:
                border-radius: 2px; padding: 6px 18px; font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background: #005FA3; }
            QPushButton[flat="true"] {
                background:
            }
        """)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        from PyQt6.QtWidgets import QLabel as _QLabel
        header = _QLabel(f"Mark Incident at Station {station_name}  |  Depth {depth_str}")
        header.setStyleSheet("color: #E03030; font-size: 14px; font-weight: bold;")
        layout.addWidget(header)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("border: 1px solid #2E3540;")
        layout.addWidget(line)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        diver_name = QLineEdit()
        diver_name.setPlaceholderText("Full name of missing diver")
        diver_name.setText(self._incidents.get(station_name, {}).get("name", ""))

        entry_time = QDateTimeEdit()
        entry_time.setDisplayFormat("yyyy-MM-dd  HH:mm")
        entry_time.setDateTime(QDateTime.currentDateTime())
        saved_time = self._incidents.get(station_name, {}).get("entry_time")
        if saved_time:
            entry_time.setDateTime(QDateTime.fromString(saved_time, "yyyy-MM-dd  HH:mm"))

        gas_bar = QSpinBox()
        gas_bar.setRange(0, 300)
        gas_bar.setSuffix(" bar")
        gas_bar.setValue(self._incidents.get(station_name, {}).get("gas_bar", 200))

        tank_vol = QDoubleSpinBox()
        tank_vol.setRange(0, 60)
        tank_vol.setSuffix(" L")
        tank_vol.setDecimals(1)
        tank_vol.setValue(self._incidents.get(station_name, {}).get("tank_vol", 11.1))

        penetration = QSpinBox()
        penetration.setRange(0, 5000)
        penetration.setSuffix(" m")
        penetration.setValue(self._incidents.get(station_name, {}).get("penetration_m", 0))

        notes = QTextEdit()
        notes.setFixedHeight(70)
        notes.setPlaceholderText("Additional notes — equipment, buddy, planned route...")
        notes.setText(self._incidents.get(station_name, {}).get("notes", ""))

        form.addRow("Diver Name:", diver_name)
        form.addRow("Entry Time:", entry_time)
        form.addRow("Gas at Entry:", gas_bar)
        form.addRow("Tank Volume:", tank_vol)
        form.addRow("Max Penetration:", penetration)
        form.addRow("Notes:", notes)
        layout.addLayout(form)

        gas_info = _QLabel("")
        gas_info.setStyleSheet("color: #4DA8F0; font-size: 11px;")
        layout.addWidget(gas_info)

        def update_gas_estimate():
            bar = gas_bar.value()
            vol = tank_vol.value()
            total_l = bar * vol
            turn_l  = total_l * (2/3)
            reserve = total_l * (1/3)
            elapsed = entry_time.dateTime().secsTo(QDateTime.currentDateTime()) / 60.0
            sac     = 20.0
            used    = sac * max(0, elapsed)
            remain  = max(0, total_l - used)
            gas_info.setText(
                f"Total gas: {total_l:.0f} L  |  Turn pressure: {turn_l:.0f} L  |  "
                f"Reserve: {reserve:.0f} L  |  Est. remaining now: {remain:.0f} L"
            )

        gas_bar.valueChanged.connect(update_gas_estimate)
        tank_vol.valueChanged.connect(update_gas_estimate)
        entry_time.dateTimeChanged.connect(update_gas_estimate)
        update_gas_estimate()

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Mark Incident")
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        dlg.raise_()
        dlg.activateWindow()
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._incidents[station_name] = {
                "name":         diver_name.text() or "Unknown Diver",
                "entry_time":   entry_time.dateTime().toString("yyyy-MM-dd  HH:mm"),
                "gas_bar":      gas_bar.value(),
                "tank_vol":     tank_vol.value(),
                "penetration_m":penetration.value(),
                "notes":        notes.toPlainText(),
                "station":      station_name,
                "depth_str":    depth_str,
            }
            self._add_incident_marker(station_name)
            diver = self._incidents[station_name]["name"]
            self._status(
                f"INCIDENT MARKED — {diver} | Last known: Station {station_name} "
                f"| Depth {depth_str} | Entry {self._incidents[station_name]['entry_time']}"
            )
            QTimer.singleShot(0, lambda: self.status_label.setStyleSheet("color: #E03030;"))
            QTimer.singleShot(100, self._update_dead_reckoning)

    def _add_incident_marker(self, station_name):
        import pyqtgraph.opengl as gl

        pos3d = None
        for name, p in self.viewer._station_positions:
            if name == station_name:
                pos3d = p
                break
        if pos3d is None:
            return

        pos = np.array([[float(pos3d[0]), float(pos3d[1]), float(pos3d[2])]])

        for m in list(self._incident_markers):
            if getattr(m, "_incident_station", None) == station_name:
                try:
                    self.viewer._view.removeItem(m)
                except Exception:
                    pass
                self._incident_markers.remove(m)

        marker = gl.GLScatterPlotItem(
            pos=pos, color=(1.0, 0.1, 0.1, 1.0), size=20, pxMode=True
        )
        marker._incident_station = station_name
        self.viewer._view.addItem(marker)
        self._incident_markers.append(marker)

        halo = gl.GLScatterPlotItem(
            pos=pos, color=(1.0, 0.45, 0.0, 0.5), size=36, pxMode=True
        )
        halo._incident_station = station_name
        self.viewer._view.addItem(halo)
        self._incident_markers.append(halo)

    def _print_briefing(self):
        if not self._cave:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Cave Loaded", "Please load or reconstruct a cave first.")
            return
        try:
            from ..engine.sar_briefing_pdf import generate_briefing_pdf
            import subprocess, os
            self._status("Generating SAR briefing PDF...")
            path = generate_briefing_pdf(self._cave, output_dir=os.path.expanduser("~/Desktop"))
            self._status(f"Briefing saved: {os.path.basename(path)}")
            subprocess.Popen(["open", path])
        except Exception as e:
            self._status(f"PDF error: {e}", error=True)

    def _statusbar_setup(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.status_label = QLabel("Ready — Load a cave or search by name above")
        self.status_label.setStyleSheet("color: #A0B0C0; font-size: 12px;")
        self.status.addPermanentWidget(self.status_label, 1)

        self.ai_status = QLabel(
            "AI: Connected" if self._assistant.is_available else "AI: Offline (set API key)"
        )
        self.ai_status.setStyleSheet(
            "color: #0078D4; font-size: 11px;" if self._assistant.is_available else "color: #B05020; font-size: 11px;"
        )
        self.status.addPermanentWidget(self.ai_status)


    def _search_cave(self):
        name = self.search_input.text().strip()
        if not name:
            return

        self._set_busy(True, f"Searching for '{name}'...")

        results = self._db.search(name)
        if results:
            data = results[0]
            self.info_panel.update_from_db(data)
            self._status(f"Found '{data['name']}' in local database. Building 3D model...")
            self._build_cave_from_db(data)
            return

        self._status(f"Querying AI for '{name}'...")
        worker = AICaveSearchWorker(self._assistant, name)
        worker.result_ready.connect(self._on_cave_lookup_result)
        worker.finished_signal.connect(lambda: self._set_busy(False))
        worker.error_signal.connect(lambda e: self._status(f"Error: {e}", error=True))
        self._worker = worker
        worker.start()

    def _on_cave_lookup_result(self, data: dict):
        if data.get("found"):
            self.info_panel.update_from_db(data)
            self._db.upsert_from_ai(data)
            self._build_cave_from_db(data)
        else:
            self._set_busy(False)
            self._status(
                f"Cave not found: '{data.get('name')}'. Try a different name.", error=True
            )
            QMessageBox.information(
                self,
                "Cave Not Found",
                f"Could not find '{data.get('name')}' in the database.\n\n"
                f"{data.get('description', '')}\n\n"
                "Try: Ginnie Springs, Tham Luang, Dos Ojos, Eagle's Nest, Orda Cave",
            )

    def _build_cave_from_db(self, data: dict):
        self._status(f"Building 3D model for {data.get('name', 'cave')}...")
        worker = CaveBuildWorker(data, self._db)
        worker.cave_ready.connect(self._on_cave_built)
        worker.error_signal.connect(lambda e: (
            self._status(f"Build error: {e}", error=True),
            self._set_busy(False),
        ))
        self._worker = worker
        worker.start()

    def _on_cave_built(self, cave):
        self._cave = cave
        self._status(f"Rendering {cave.name}…")
        self.viewer.load_cave(cave)
        self.voxel_view.clear()
        self.info_panel.update_cave(cave)
        self._set_busy(False)
        self._status(
            f"Loaded: {cave.name}  |  "
            f"{cave.station_count()} stations  |  "
            f"{cave.total_length_m():.0f} m surveyed  ·  Click a station dot to explore"
        )

    def _open_survey_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Survey File",
            str(Path.home()),
            "Survey Files (*.dat *.DAT *.svx *.SVX);;Compass DAT (*.dat);;Survex (*.svx);;All Files (*)",
        )
        if not path:
            return
        self._settings.add_recent_file(path)
        self._set_busy(True, f"Loading {Path(path).name}...")
        try:
            ext = Path(path).suffix.lower()
            if ext == ".svx":
                cave = parse_survex(path)
            else:
                cave = parse_compass_dat(path)
            self._cave = cave
            self.viewer.load_cave(cave)
            self.info_panel.update_cave(cave)
            self._status(
                f"Loaded: {cave.name}  |  "
                f"{cave.station_count()} stations  |  "
                f"{cave.total_length_m():.0f} m surveyed  ·  Click a station dot to explore"
            )
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load survey file:\n{e}")
            self._status(f"Load error: {e}", error=True)
        finally:
            self._set_busy(False)

    def _load_demo(self):
        self._set_busy(True, "Loading demo cave...")
        try:
            sample_dat = generate_sample_dat("Blue Springs Underwater Cave")
            cave = parse_compass_dat_string(sample_dat, "Blue Springs Underwater Cave")
            meta = CaveMetadata(
                name="Blue Springs Underwater Cave",
                country="USA",
                region="Florida (Demo)",
                max_depth_m=28,
                total_surveyed_m=cave.total_length_m(),
                water_type="freshwater",
                visibility_m=25,
                flow="mild",
                hazards=["DEMO ONLY — not a real survey"],
                description="Demonstration cave generated from sample data. Not a real survey.",
            )
            cave.metadata = meta
            self._cave = cave
            self.viewer.load_cave(cave)
            self.info_panel.update_cave(cave)
            self._status(
                f"Demo loaded: {cave.station_count()} stations, "
                f"{cave.total_length_m():.0f} m surveyed  ·  Click a station dot to explore"
            )
        except Exception as e:
            QMessageBox.critical(self, "Demo Error", str(e))
        finally:
            self._set_busy(False)


    def _on_station_clicked(self, station_name):
        if not self._cave:
            return
        self._status(f"Loading voxel view for station {station_name}...")
        sizes = self._left_splitter.sizes()
        if sizes[1] < 200:
            total = sum(sizes)
            self._left_splitter.setSizes([int(total * 0.55), int(total * 0.45)])
        cave_ref = self._cave
        class PassageWorker(QThread):
            chunk_ready = pyqtSignal(dict)
            def __init__(self, cave, name):
                super().__init__()
                self._cave = cave
                self._name = name
            def run(self):
                from ..engine.voxel_builder import build_passage_data
                data = build_passage_data(self._cave, self._name)
                self.chunk_ready.emit(data)
        worker = PassageWorker(cave_ref, station_name)
        worker.chunk_ready.connect(self._on_chunk_ready)
        worker.chunk_ready.connect(lambda _: worker.deleteLater())
        self._passage_worker = worker
        worker.start()

    def _on_chunk_ready(self, chunk_data):
        self.voxel_view.load_station(chunk_data)
        lrud = chunk_data.get("lrud", {})
        w = lrud.get("l", 0) + lrud.get("r", 0)
        h = lrud.get("u", 0) + lrud.get("d", 0)
        name = chunk_data.get("station", "?")
        depth = chunk_data.get("depth_m", 0.0)
        msg = "Station " + str(name) + "  |  Depth " + str(round(depth,1)) + " m  |  Passage " + str(round(w,1)) + " m wide x " + str(round(h,1)) + " m high"
        print("STATUS:", msg)
        QTimer.singleShot(0, lambda: self.status_label.setText(msg))
        QTimer.singleShot(0, lambda: self.status_label.setStyleSheet("color: #0078D4;"))

    def _sar_mode(self):
        dlg = SARDialog(self._cave, self._assistant, self)
        dlg.exec()

    def _quick_gas(self):
        from .sar_dialog import SARDialog
        dlg = SARDialog(self._cave, self._assistant, self)
        dlg.exec()

    def _toggle_depth_coloring(self, checked: bool):
        self._settings.set_depth_coloring(checked)
        if self._cave:
            self.viewer.load_cave(self._cave)

    def _export_stats(self):
        if not self._cave:
            QMessageBox.information(self, "Export", "No cave loaded.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Stats", f"{self._cave.name}_stats.txt", "Text Files (*.txt)"
        )
        if path:
            text = get_cave_stats_text(self._cave)
            Path(path).write_text(text, encoding="utf-8")
            self._status(f"Exported to {path}")

    def _handle_chat(self, message: str):
        if self._cave:
            context = (
                f"[Current cave: {self._cave.name}, "
                f"{self._cave.metadata.country}, "
                f"max depth {self._cave.metadata.max_depth_m}m] "
            )
            message = context + message

        self.chat_panel.append_user(message)
        self.chat_panel.begin_assistant_response()
        self.chat_panel.set_busy(True)

        worker = AIChatWorker(self._assistant, message, self._chat_history)
        worker.stream_chunk.connect(self.chat_panel.append_chunk)
        worker.finished_signal.connect(self._on_chat_done)
        worker.error_signal.connect(lambda e: self.chat_panel.append_chunk(f"\nError: {e}"))
        self._worker = worker
        worker.start()

    def _on_chat_done(self):
        self.chat_panel.end_response()
        self.chat_panel.set_busy(False)
        self._set_busy(False)

    def _set_api_key(self):
        dlg = ApiKeyDialog(self._ai_key, self)
        dlg.raise_()
        dlg.activateWindow()
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._ai_key = dlg.api_key
            self._settings.set_api_key(self._ai_key)
            self._assistant = CaveAssistant(self._ai_key)
            self._incident_scanner = IncidentScanner(self._ai_key)
            self.ai_status.setText(
                "AI: Connected" if self._assistant.is_available else "AI: Offline"
            )
            self.ai_status.setStyleSheet(
                "color: #0078D4;" if self._assistant.is_available else "color: #B05020;"
            )


    def _browse_database(self):
        caves = self._db.all_caves()
        dlg = CaveDatabaseDialog(caves, self)
        dlg.cave_selected.connect(self._load_cave_from_db)
        dlg.exec()

    def _load_cave_from_db(self, cave_name: str):
        self.search_input.setText(cave_name)
        self._search_cave()


    def _show_about(self):
        import subprocess
        from pathlib import Path
        proj = Path(__file__).parent.parent.parent
        try:
            commit = subprocess.check_output(
                ["git", "log", "-1", "--format=%h %s", "--abbrev=7"],
                cwd=proj, stderr=subprocess.DEVNULL, text=True
            ).strip()
            commit_date = subprocess.check_output(
                ["git", "log", "-1", "--format=%ci"],
                cwd=proj, stderr=subprocess.DEVNULL, text=True
            ).strip()[:10]
            git_info = f"<br>Build: {commit}<br>Date: {commit_date}"
        except Exception:
            git_info = ""
        QMessageBox.about(
            self,
            "About TEHOM",
            "<b>TEHOM</b><br>"
            "Version 0.1.0 — Prototype<br><br>"
            "3D underwater cave mapping and visualization system<br>"
            "for cave divers and search & rescue operations.<br><br>"
            "Survey formats: Compass .dat, Survex .svx<br>"
            "AI: Claude (Anthropic) for global cave lookup<br><br>"
            f"{git_info}<br>"
            "WARNING: This software is for planning/simulation ONLY.<br>"
            "Always dive with proper training and certification.",
        )

    def _check_for_updates(self):
        import subprocess
        from pathlib import Path
        proj = Path(__file__).parent.parent.parent

        try:
            subprocess.check_output(
                ["git", "status"], cwd=proj, stderr=subprocess.DEVNULL
            )
        except Exception:
            QMessageBox.information(
                self, "Updates",
                "Version control not configured.\n\n"
                "To enable updates, push your code to GitHub and run:\n"
                "  git remote add origin <your-github-url>"
            )
            return

        try:
            remotes = subprocess.check_output(
                ["git", "remote"], cwd=proj, stderr=subprocess.DEVNULL, text=True
            ).strip()
        except Exception:
            remotes = ""

        if not remotes:
            QMessageBox.information(
                self, "No Remote Configured",
                "TEHOM tracks changes locally with git, but no remote is set.\n\n"
                "Current commit:\n"
                + subprocess.check_output(
                    ["git", "log", "-3", "--oneline"],
                    cwd=proj, text=True
                ).strip() +
                "\n\nTo push updates from another machine:\n"
                "  git remote add origin <github-url>\n"
                "  git push -u origin master\n\n"
                "Then to update here: Help → Check for Updates"
            )
            return

        reply = QMessageBox.question(
            self, "Check for Updates",
            "Pull latest changes from remote?\nTEHOM will need to restart after updating.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            result = subprocess.check_output(
                ["git", "pull", "--ff-only"],
                cwd=proj, stderr=subprocess.STDOUT, text=True
            )
            if "Already up to date" in result:
                QMessageBox.information(self, "Up to Date", "TEHOM is already up to date.")
            else:
                QMessageBox.information(
                    self, "Updated",
                    f"Update applied:\n\n{result}\n\nPlease quit and restart TEHOM."
                )
        except subprocess.CalledProcessError as e:
            QMessageBox.warning(
                self, "Update Failed",
                f"Could not pull updates:\n\n{e.output}"
            )

    def _open_log(self):
        import subprocess, os
        log = os.path.expanduser("~/Library/Logs/TEHOM.log")
        if not os.path.exists(log):
            QMessageBox.information(
                self, "Log", "No log file yet.\nLogs appear after first launch from the .app."
            )
            return
        subprocess.Popen(["open", log])

    def _status(self, text: str, error: bool = False):
        self.status_label.setText(text)
        color = "#C05030" if error else "#A0B0C0"
        self.status_label.setStyleSheet(f"color: {color}; font-size: 12px;")

    def _set_busy(self, busy: bool, message: str = ""):
        self.progress_bar.setVisible(busy)
        self.search_btn.setEnabled(not busy)
        if message:
            self._status(message)

    def showEvent(self, event):
        super().showEvent(event)
        self._settings.restore_geometry(self)

    def closeEvent(self, event):
        self._settings.save_geometry(self)
        self._db.close()
        event.accept()

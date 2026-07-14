from __future__ import annotations
import numpy as np
from typing import Optional

try:
    import pyvista as pv
    PYVISTA_AVAILABLE = True
except ImportError:
    PYVISTA_AVAILABLE = False

from .cave_model import CaveSystem, Station


SURVEY_COLORS = [
    "#4D9EFF",
    "#FF5252",
    "#8AE234",
    "#FFD040",
    "#C77DFF",
    "#FF8C40",
    "#40D9C0",
]

STATION_COLOR  = "#E8E8E8"
WATER_COLOR    = "#1A3A52"
PASSAGE_WALL_COLOR = "#5A5A5A"


class CaveRenderer:

    def __init__(self, cave: CaveSystem):
        self.cave = cave
        self._actors: list = []

    def build_plotter(
        self,
        background_color: str = "#3D3D3D",
        show_stations: bool = True,
        show_grid: bool = True,
        passage_radius_scale: float = 1.0,
        water_surface: bool = True,
    ) -> "pv.Plotter":
        if not PYVISTA_AVAILABLE:
            raise ImportError("pyvista is required for 3D rendering. Run: pip install pyvista pyvistaqt")

        plotter = pv.Plotter(window_size=[1200, 800])

        plotter.set_background("#3D3D3D", top="#2B2B2B")

        self._add_passages(plotter, passage_radius_scale)
        if show_stations:
            self._add_stations(plotter)
        if water_surface:
            self._add_water_surface(plotter)
        if show_grid:
            self._add_blender_grid(plotter)

        self._add_scale_bar(plotter)
        self._add_axis_widget(plotter)
        plotter.reset_camera()
        plotter.camera.elevation = 20
        plotter.camera.azimuth = -45

        return plotter

    def _add_passages(self, plotter: "pv.Plotter", radius_scale: float) -> None:
        segments = self.cave.get_shot_segments()
        if not segments:
            return

        survey_shots: dict[str, list] = {}
        for survey in self.cave.surveys:
            shot_names = {id(s) for s in survey.shots}
            for pt_a, pt_b, shot in segments:
                if id(shot) in shot_names:
                    survey_shots.setdefault(survey.name, []).append((pt_a, pt_b, shot))

        for i, (survey_name, shot_list) in enumerate(survey_shots.items()):
            color = SURVEY_COLORS[i % len(SURVEY_COLORS)]
            self._render_survey_tubes(plotter, shot_list, color, radius_scale, survey_name)

    def _render_survey_tubes(
        self,
        plotter: "pv.Plotter",
        shot_list: list,
        color: str,
        radius_scale: float,
        survey_name: str,
    ) -> None:
        if not shot_list:
            return

        for pt_a, pt_b, shot in shot_list:
            pts = np.vstack([pt_a, pt_b])
            line = pv.Spline(pts, 2)

            radius = 0.5
            if shot.lrud_to:
                radius = max(0.2, shot.lrud_to.radius_approx * radius_scale)

            tube = line.tube(radius=radius, n_sides=12)
            plotter.add_mesh(
                tube,
                color=color,
                opacity=0.85,
                smooth_shading=True,
                name=f"passage_{survey_name}_{id(shot)}",
            )

    def _add_stations(self, plotter: "pv.Plotter") -> None:
        stations = self.cave.get_all_stations()
        if not stations:
            return

        positions = np.array([s.position for s in stations.values()])
        cloud = pv.PolyData(positions)
        glyphs = cloud.glyph(
            geom=pv.Sphere(radius=0.15),
            orient=False,
            scale=False,
        )
        plotter.add_mesh(
            glyphs,
            color=STATION_COLOR,
            opacity=1.0,
            name="stations",
        )

        if len(stations) <= 100:
            for name, station in stations.items():
                plotter.add_point_labels(
                    [station.position + np.array([0, 0, 0.4])],
                    [name],
                    font_size=8,
                    text_color="white",
                    always_visible=False,
                    shape_opacity=0.3,
                )

    def _add_water_surface(self, plotter: "pv.Plotter") -> None:
        bbox_min, bbox_max = self.cave.get_bounding_box()
        if np.all(bbox_min == bbox_max):
            return

        surface_z = bbox_max[2] + 5.0
        margin = 10.0
        plane = pv.Plane(
            center=[(bbox_min[0] + bbox_max[0]) / 2,
                    (bbox_min[1] + bbox_max[1]) / 2,
                    surface_z],
            direction=[0, 0, 1],
            i_size=(bbox_max[0] - bbox_min[0]) + margin * 2,
            j_size=(bbox_max[1] - bbox_min[1]) + margin * 2,
        )
        plotter.add_mesh(
            plane,
            color=WATER_COLOR,
            opacity=0.25,
            name="water_surface",
        )

    def _add_scale_bar(self, plotter: "pv.Plotter") -> None:
        bbox_min, bbox_max = self.cave.get_bounding_box()
        if np.all(bbox_min == bbox_max):
            return

        length = self.cave.total_length_m()
        scale = max(5.0, round(length / 20, -1))

        start = bbox_min + np.array([0, 0, -2])
        end = start + np.array([scale, 0, 0])

        line = pv.Line(start, end)
        plotter.add_mesh(line, color="#E8E8E8", line_width=2, name="scale_bar")
        plotter.add_point_labels(
            [(start + end) / 2 + np.array([0, 0, -1])],
            [f"{int(scale)} m"],
            font_size=10,
            text_color="#E8E8E8",
            always_visible=True,
        )

    def _add_blender_grid(self, plotter: "pv.Plotter") -> None:
        bbox_min, bbox_max = self.cave.get_bounding_box()
        if np.all(bbox_min == bbox_max):
            return

        grid_z = float(bbox_min[2]) - 2.0

        pad = 20.0
        x_min = float(bbox_min[0]) - pad
        x_max = float(bbox_max[0]) + pad
        y_min = float(bbox_min[1]) - pad
        y_max = float(bbox_max[1]) + pad

        step = 10.0

        x = x_min
        while x <= x_max + 0.01:
            line = pv.Line([x, y_min, grid_z], [x, y_max, grid_z])
            plotter.add_mesh(line, color="#505050", line_width=1,
                             opacity=0.6, name=f"grid_x_{x:.0f}")
            x += step

        y = y_min
        while y <= y_max + 0.01:
            line = pv.Line([x_min, y, grid_z], [x_max, y, grid_z])
            plotter.add_mesh(line, color="#505050", line_width=1,
                             opacity=0.6, name=f"grid_y_{y:.0f}")
            y += step

        plotter.add_mesh(
            pv.Line([x_min, 0, grid_z], [x_max, 0, grid_z]),
            color="#FF5252", line_width=2, opacity=0.9, name="axis_x",
        )
        plotter.add_mesh(
            pv.Line([0, y_min, grid_z], [0, y_max, grid_z]),
            color="#8AE234", line_width=2, opacity=0.9, name="axis_y",
        )

    def _add_axis_widget(self, plotter: "pv.Plotter") -> None:
        plotter.add_axes(
            xlabel="X",
            ylabel="Y",
            zlabel="Z",
            line_width=3,
            x_color="#FF5252",
            y_color="#8AE234",
            z_color="#4D9EFF",
            color_box=False,
        )


def get_cave_stats_text(cave: CaveSystem) -> str:
    meta = cave.metadata
    lines = [
        f"Cave: {cave.name}",
        f"Location: {meta.country}{', ' + meta.region if meta.region else ''}",
        f"Surveys: {len(cave.surveys)}",
        f"Stations: {cave.station_count()}",
        f"Surveyed length: {cave.total_length_m():.1f} m",
    ]
    if meta.max_depth_m:
        lines.append(f"Max depth: {meta.max_depth_m:.0f} m")
    if meta.visibility_m:
        lines.append(f"Visibility: {meta.visibility_m:.0f} m")
    if meta.water_type:
        lines.append(f"Water type: {meta.water_type.capitalize()}")
    if meta.hazards:
        lines.append(f"Hazards: {', '.join(meta.hazards)}")
    return "\n".join(lines)

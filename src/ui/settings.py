from __future__ import annotations
from PyQt6.QtCore import QSettings


APP_NAME = "TEHOM"
ORG_NAME = "TEHOM"


class AppSettings:
    def __init__(self):
        self._s = QSettings(ORG_NAME, APP_NAME)

    def get_api_key(self) -> str:
        return self._s.value("ai/api_key", "", type=str)

    def set_api_key(self, key: str) -> None:
        self._s.setValue("ai/api_key", key)

    def get_background_color(self) -> str:
        return self._s.value("viewer/background", "#141618", type=str)

    def set_background_color(self, color: str) -> None:
        self._s.setValue("viewer/background", color)

    def get_show_stations(self) -> bool:
        return self._s.value("viewer/show_stations", True, type=bool)

    def set_show_stations(self, val: bool) -> None:
        self._s.setValue("viewer/show_stations", val)

    def get_depth_coloring(self) -> bool:
        return self._s.value("viewer/depth_coloring", True, type=bool)

    def set_depth_coloring(self, val: bool) -> None:
        self._s.setValue("viewer/depth_coloring", val)

    def get_passage_radius_scale(self) -> float:
        return float(self._s.value("viewer/radius_scale", 1.0))

    def set_passage_radius_scale(self, val: float) -> None:
        self._s.setValue("viewer/radius_scale", val)

    def save_geometry(self, window) -> None:
        self._s.setValue("window/geometry", window.saveGeometry())
        self._s.setValue("window/state", window.saveState())

    def restore_geometry(self, window) -> None:
        geom = self._s.value("window/geometry")
        state = self._s.value("window/state")
        if geom:
            window.restoreGeometry(geom)
        if state:
            window.restoreState(state)

    def get_recent_files(self) -> list[str]:
        return self._s.value("files/recent", [], type=list)

    def add_recent_file(self, path: str) -> None:
        recent = self.get_recent_files()
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        self._s.setValue("files/recent", recent[:10])

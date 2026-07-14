from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QDoubleSpinBox, QSpinBox, QTextEdit,
    QPushButton, QDialogButtonBox, QTabWidget, QWidget, QComboBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from ..ai.sar_planner import SARBriefing, DiveGasConfig
from ..engine.cave_model import CaveSystem
from ..ai.cave_assistant import CaveAssistant


class SARBriefingWorker(QThread):
    chunk_ready = pyqtSignal(str)
    done = pyqtSignal()

    def __init__(self, assistant: CaveAssistant, cave_name: str,
                 missing_since: str, diver_profile: str):
        super().__init__()
        self.assistant = assistant
        self.cave_name = cave_name
        self.missing_since = missing_since
        self.diver_profile = diver_profile

    def run(self):
        for chunk in self.assistant.chat_stream(
            f"EMERGENCY SAR BRIEFING for cave: {self.cave_name}\n"
            f"Missing since: {self.missing_since}\n"
            f"Diver: {self.diver_profile}\n\n"
            f"Provide a detailed SAR briefing including cave layout, search priorities, "
            f"gas management, hazards for rescuers, and emergency contacts."
        ):
            self.chunk_ready.emit(chunk)
        self.done.emit()


class SARDialog(QDialog):

    def __init__(
        self,
        cave: Optional[CaveSystem],
        assistant: CaveAssistant,
        parent=None,
    ):
        super().__init__(parent)
        self.cave = cave
        self.assistant = assistant
        self._worker: Optional[QThread] = None

        self.setWindowTitle("Search & Rescue Planning")
        self.setMinimumSize(700, 600)
        self.setStyleSheet("""
            QDialog {
                background:
                color:
                font-family: "Segoe UI", "Helvetica Neue", sans-serif;
            }
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
            QLabel { color: #9BAAB8; }
            QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
                background:
                color:
                border: 1px solid
                border-radius: 2px;
                padding: 4px 6px;
                font-size: 12px;
            }
            QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {
                border-color:
            }
            QTextEdit {
                background:
                color:
                border: 1px solid
                border-radius: 2px;
                font-family: "JetBrains Mono", "Menlo", monospace;
                font-size: 11px;
            }
            QPushButton {
                background:
                color:
                border: 1px solid
                border-radius: 2px;
                padding: 4px 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background:
                color:
                border-color:
            }
            QPushButton:pressed { background: #141618; }
            QTabWidget::pane { border: none; border-top: 1px solid #252A2E; }
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
            QTabBar::tab:hover:!selected { color: #9BAAB8; }
            QScrollBar:vertical { background: #141618; width: 6px; border: none; }
            QScrollBar::handle:vertical { background: #2E3540; border-radius: 3px; }
            QScrollBar::handle:vertical:hover { background: #0078D4; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel("SEARCH & RESCUE PLANNING SYSTEM")
        header.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        header.setStyleSheet("color: #F0A444; padding: 6px; letter-spacing: 1px;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        warning = QLabel(
            "This tool provides planning assistance only. "
            "Always involve trained cave rescue specialists and local emergency services."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "color: #C8903A; background: #1E1610; border: 1px solid #3A2A10; "
            "border-radius: 2px; padding: 6px 10px; font-size: 11.5px;"
        )
        layout.addWidget(warning)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        tabs.addTab(self._build_incident_tab(), "Incident Details")

        tabs.addTab(self._build_gas_tab(), "Gas Calculator")

        tabs.addTab(self._build_ai_briefing_tab(), "AI Briefing")

        btn_row = QHBoxLayout()
        generate_btn = QPushButton("Generate Offline Briefing")
        generate_btn.setStyleSheet(
            "background: #1E1610; color: #F0A444; font-weight: 600; "
            "border: 1px solid #3A2A10; border-radius: 2px; padding: 6px 14px;"
        )
        generate_btn.clicked.connect(self._generate_offline_briefing)
        btn_row.addWidget(generate_btn)

        ai_btn = QPushButton("Generate AI Briefing")
        ai_btn.setStyleSheet(
            "background: #0078D4; color: #fff; font-weight: 600; "
            "border: none; border-radius: 2px; padding: 6px 14px;"
        )
        ai_btn.clicked.connect(self._generate_ai_briefing)
        btn_row.addWidget(ai_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _build_incident_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setSpacing(8)

        cave_name = self.cave.name if self.cave else ""
        self.cave_input = QLineEdit(cave_name)
        layout.addRow("Cave name:", self.cave_input)

        self.missing_input = QLineEdit()
        self.missing_input.setPlaceholderText("e.g. 14:30 local time")
        layout.addRow("Missing since:", self.missing_input)

        self.diver_input = QLineEdit()
        self.diver_input.setPlaceholderText("e.g. John Doe — Cave Diver, tech certified")
        layout.addRow("Diver name/profile:", self.diver_input)

        self.last_pos_input = QLineEdit("Entrance")
        layout.addRow("Last known position:", self.last_pos_input)

        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0, 40)
        self.temp_spin.setValue(20.0)
        self.temp_spin.setSuffix(" °C")
        layout.addRow("Water temperature:", self.temp_spin)

        self.vis_spin = QDoubleSpinBox()
        self.vis_spin.setRange(0, 100)
        self.vis_spin.setValue(5.0)
        self.vis_spin.setSuffix(" m")
        layout.addRow("Visibility:", self.vis_spin)

        return widget

    def _build_gas_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        form_group = QGroupBox("SAR Diver Gas Configuration")
        form = QFormLayout(form_group)

        self.tank_vol = QDoubleSpinBox()
        self.tank_vol.setRange(1, 50)
        self.tank_vol.setValue(12.0)
        self.tank_vol.setSuffix(" L")
        form.addRow("Tank volume:", self.tank_vol)

        self.tank_pressure = QDoubleSpinBox()
        self.tank_pressure.setRange(50, 300)
        self.tank_pressure.setValue(200.0)
        self.tank_pressure.setSuffix(" bar")
        form.addRow("Fill pressure:", self.tank_pressure)

        self.num_tanks = QSpinBox()
        self.num_tanks.setRange(1, 8)
        self.num_tanks.setValue(2)
        form.addRow("Number of tanks:", self.num_tanks)

        self.sac_rate = QDoubleSpinBox()
        self.sac_rate.setRange(5, 60)
        self.sac_rate.setValue(20.0)
        self.sac_rate.setSuffix(" L/min")
        form.addRow("SAC rate:", self.sac_rate)

        self.depth_input = QDoubleSpinBox()
        self.depth_input.setRange(0, 200)
        self.depth_input.setValue(20.0)
        self.depth_input.setSuffix(" m")
        form.addRow("Working depth:", self.depth_input)

        layout.addWidget(form_group)

        calc_btn = QPushButton("Calculate")
        calc_btn.setStyleSheet(
            "background: #0078D4; color: #fff; font-weight: 600; "
            "border: none; border-radius: 2px; padding: 5px 14px;"
        )
        calc_btn.clicked.connect(self._calculate_gas)
        layout.addWidget(calc_btn)

        self.gas_result = QTextEdit()
        self.gas_result.setReadOnly(True)
        layout.addWidget(self.gas_result)

        return widget

    def _build_ai_briefing_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.ai_briefing_text = QTextEdit()
        self.ai_briefing_text.setReadOnly(True)
        self.ai_briefing_text.setPlaceholderText(
            "Click 'Generate AI Briefing' to get an AI-powered SAR briefing.\n\n"
            "Requires Anthropic API key (Settings → Set API Key)."
        )
        layout.addWidget(self.ai_briefing_text)

        return widget

    def _calculate_gas(self):
        cfg = DiveGasConfig(
            tank_volume_liters=self.tank_vol.value(),
            tank_pressure_bar=self.tank_pressure.value(),
            num_tanks=self.num_tanks.value(),
            sac_rate_lmin=self.sac_rate.value(),
        )
        depth = self.depth_input.value()

        lines = [
            f"DIVE GAS ANALYSIS  (depth: {depth}m)",
            "─" * 40,
            f"Total gas:          {cfg.total_gas_liters:>8,.0f} L",
            f"Rule-of-thirds:     {cfg.usable_gas_liters():>8,.0f} L usable",
            f"Turn pressure:      {cfg.turn_pressure_bar():>8.0f} bar",
            "",
            f"SAC at {depth}m:         {cfg.sac_rate_lmin * (1 + depth/10):>8.1f} L/min",
            f"Max bottom time:    {cfg.max_bottom_time_at_depth(depth):>8.1f} min",
            f"Max penetration:    {cfg.penetration_distance_m(depth):>8.0f} m",
            "",
            "Penetration table:",
        ]
        for d in (5, 10, 15, 20, 25, 30, 40, 50, 60):
            p = cfg.penetration_distance_m(d)
            t = cfg.max_bottom_time_at_depth(d)
            lines.append(f"  {d:>3}m → {p:>6.0f}m / {t:>5.1f} min")

        self.gas_result.setText("\n".join(lines))

    def _generate_offline_briefing(self):
        briefing = SARBriefing(
            cave_name=self.cave_input.text() or "Unknown Cave",
            missing_since=self.missing_input.text(),
            diver_name=self.diver_input.text(),
            last_known_position=self.last_pos_input.text(),
            gas_config=DiveGasConfig(
                tank_volume_liters=self.tank_vol.value(),
                tank_pressure_bar=self.tank_pressure.value(),
                num_tanks=self.num_tanks.value(),
                sac_rate_lmin=self.sac_rate.value(),
            ),
            water_temp_c=self.temp_spin.value(),
            visibility_m=self.vis_spin.value(),
        )
        text = briefing.full_briefing(self.cave)

        self.ai_briefing_text.setText(text)
        parent_tabs = self.findChild(QTabWidget)
        if parent_tabs:
            parent_tabs.setCurrentIndex(2)

    def _generate_ai_briefing(self):
        self.ai_briefing_text.setPlainText("Generating AI briefing...\n")

        worker = SARBriefingWorker(
            self.assistant,
            self.cave_input.text() or "Unknown Cave",
            self.missing_input.text(),
            self.diver_input.text(),
        )
        worker.chunk_ready.connect(lambda c: self._append_briefing(c))
        worker.done.connect(lambda: None)
        self._worker = worker
        worker.start()

        parent_tabs = self.findChild(QTabWidget)
        if parent_tabs:
            parent_tabs.setCurrentIndex(2)

    def _append_briefing(self, chunk: str):
        from PyQt6.QtGui import QTextCursor
        cursor = self.ai_briefing_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(chunk)
        self.ai_briefing_text.setTextCursor(cursor)
        self.ai_briefing_text.ensureCursorVisible()

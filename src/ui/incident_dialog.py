from __future__ import annotations
import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QTextEdit, QTableWidget, QTableWidgetItem,
    QTabWidget, QWidget, QProgressBar, QMessageBox, QHeaderView,
    QSplitter, QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QFont

if TYPE_CHECKING:
    from ..database.incident_database import IncidentReport

DARK_STYLE = """
    QDialog, QWidget {
        background:
        color:
        font-family: "Helvetica Neue", sans-serif;
    }
    QTabWidget::pane {
        border: 1px solid
        background:
    }
    QTabBar::tab {
        background:
        color:
        padding: 8px 18px;
        border: 1px solid
        font-size: 12px;
    }
    QTabBar::tab:selected {
        background:
        color: white;
        border-color:
    }
    QTableWidget {
        background:
        color:
        gridline-color:
        border: 1px solid
        font-size: 11px;
    }
    QTableWidget::item:selected {
        background:
    }
    QHeaderView::section {
        background:
        color:
        padding: 6px;
        border: 1px solid
        font-size: 11px;
        font-weight: bold;
    }
    QPushButton {
        background:
        color: white;
        border: none;
        border-radius: 2px;
        padding: 7px 18px;
        font-size: 12px;
        font-weight: bold;
    }
    QPushButton:hover { background: #005FA3; }
    QPushButton
        background:
    }
    QPushButton
    QPushButton
        background:
        color:
    }
    QPushButton
    QTextEdit {
        background:
        color:
        border: 1px solid
        font-size: 11px;
        padding: 6px;
    }
    QProgressBar {
        background:
        border: 1px solid
        border-radius: 2px;
        text-align: center;
        color: white;
        font-size: 11px;
    }
    QProgressBar::chunk {
        background:
    }
    QLabel
        font-size: 16px;
        font-weight: bold;
        color:
    }
    QLabel
        font-size: 11px;
        color:
    }
"""


class ScanWorker(QThread):
    finished  = pyqtSignal(object)
    error     = pyqtSignal(str)
    progress  = pyqtSignal(str)

    def __init__(self, scanner, filepath: str):
        super().__init__()
        self._scanner  = scanner
        self._filepath = filepath

    def run(self):
        try:
            self.progress.emit("Extracting text from document...")
            report = self._scanner.scan_file(self._filepath)
            self.finished.emit(report)
        except Exception as e:
            self.error.emit(str(e))


class IncidentDatabaseDialog(QDialog):

    show_on_map = pyqtSignal(object)

    def __init__(self, incident_db, scanner, cave_name: str = "", parent=None):
        super().__init__(parent)
        self._db        = incident_db
        self._scanner   = scanner
        self._cave_name = cave_name
        self._worker    = None

        self.setWindowTitle("TEHOM — Incident Database")
        self.setMinimumSize(900, 600)
        self.setStyleSheet(DARK_STYLE)

        self._build_ui()
        self._load_table()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel("Incident Report Database")
        header.setObjectName("header")
        sub = QLabel(
            "Upload past incident reports (PDF, DOCX, TXT). "
            "AI extracts structured data for SAR briefing context."
        )
        sub.setObjectName("subheader")
        layout.addWidget(header)
        layout.addWidget(sub)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("border: 1px solid #252A2E;")
        layout.addWidget(line)

        tabs = QTabWidget()
        tabs.addTab(self._build_upload_tab(), "Upload Report")
        tabs.addTab(self._build_browse_tab(), "Browse Database")
        layout.addWidget(tabs)

        btn_row = QHBoxLayout()
        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondary")
        close_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _build_upload_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        drop_label = QLabel(
            "Select an incident report file to upload.\n"
            "Supported formats: PDF, DOCX, TXT\n\n"
            "AI will extract: cave name, date, outcome, cause, depth,\n"
            "hazards, last known position, and lessons learned."
        )
        drop_label.setStyleSheet(
            "background: #1E2530; border: 2px dashed #2E3540; "
            "padding: 24px; color: #6B7A8A; font-size: 12px; border-radius: 4px;"
        )
        drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(drop_label)

        select_btn = QPushButton("Select Incident Report File")
        select_btn.clicked.connect(self._select_file)
        layout.addWidget(select_btn)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress_label = QLabel("")
        self._progress_label.setStyleSheet("color: #0078D4; font-size: 11px;")
        layout.addWidget(self._progress)
        layout.addWidget(self._progress_label)

        preview_label = QLabel("Extracted Data Preview:")
        preview_label.setStyleSheet("color: #9BAAB8; font-size: 11px;")
        layout.addWidget(preview_label)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText("Extracted incident data will appear here after scanning...")
        self._preview.setMinimumHeight(180)
        layout.addWidget(self._preview)

        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("Save to Database")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_report)
        btn_row.addStretch()
        btn_row.addWidget(self._save_btn)
        layout.addLayout(btn_row)

        self._pending_report = None
        return w

    def _build_browse_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        filter_row = QHBoxLayout()
        self._filter_label = QLabel(f"Showing all incidents  |  Total: {self._db.count()}")
        self._filter_label.setStyleSheet("color: #6B7A8A; font-size: 11px;")
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("secondary")
        refresh_btn.setFixedWidth(80)
        refresh_btn.clicked.connect(self._load_table)
        filter_row.addWidget(self._filter_label)
        filter_row.addStretch()
        filter_row.addWidget(refresh_btn)
        layout.addLayout(filter_row)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "Cave", "Date", "Outcome", "Cause", "Depth (m)", "Penetration (m)", "Confidence"
        ])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.itemSelectionChanged.connect(self._on_row_selected)
        splitter.addWidget(self._table)

        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 8, 0, 0)

        detail_header = QLabel("Incident Detail")
        detail_header.setStyleSheet("color: #9BAAB8; font-size: 11px; font-weight: bold;")
        detail_layout.addWidget(detail_header)

        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMaximumHeight(160)
        detail_layout.addWidget(self._detail)

        action_row = QHBoxLayout()
        self._map_btn = QPushButton("Show on Map")
        self._map_btn.setEnabled(False)
        self._map_btn.clicked.connect(self._show_on_map)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setObjectName("danger")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._delete_selected)

        action_row.addWidget(self._map_btn)
        action_row.addStretch()
        action_row.addWidget(self._delete_btn)
        detail_layout.addLayout(action_row)

        splitter.addWidget(detail_widget)
        splitter.setSizes([300, 200])
        layout.addWidget(splitter)

        return w

    def _select_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Incident Report",
            str(Path.home()),
            "Documents (*.pdf *.docx *.txt);;All Files (*)"
        )
        if not path:
            return
        self._scan_file(path)

    def _scan_file(self, filepath: str):
        self._progress.setVisible(True)
        self._progress_label.setText(f"Scanning: {Path(filepath).name}")
        self._preview.setPlainText("")
        self._save_btn.setEnabled(False)
        self._pending_report = None

        self._worker = ScanWorker(self._scanner, filepath)
        self._worker.finished.connect(self._on_scan_complete)
        self._worker.error.connect(self._on_scan_error)
        self._worker.progress.connect(lambda msg: self._progress_label.setText(msg))
        self._worker.start()

    def _on_scan_complete(self, report):
        self._progress.setVisible(False)
        self._progress_label.setText(f"Scan complete — {report.source_file}")
        self._pending_report = report

        lines = [
            f"Cave:              {report.cave_name}",
            f"Date:              {report.incident_date or 'Unknown'}",
            f"Diver:             {report.diver_name}",
            f"Certification:     {report.diver_cert or 'Unknown'}",
            f"Outcome:           {report.outcome.upper()}",
            f"Cause:             {report.cause}",
            f"Depth:             {report.depth_of_incident} m",
            f"Penetration:       {report.penetration_m} m",
            f"Last known pos:    {report.last_known_station or 'Unknown'}",
            f"Gas situation:     {report.gas_at_incident or 'Unknown'}",
            f"Hazards:           {', '.join(report.hazards_involved) or 'None recorded'}",
            f"Confidence:        {report.confidence}",
            f"",
            f"SUMMARY:",
            report.summary,
            f"",
            f"LESSONS:",
            report.lessons,
        ]
        self._preview.setPlainText("\n".join(lines))
        self._save_btn.setEnabled(True)

    def _on_scan_error(self, error: str):
        self._progress.setVisible(False)
        self._progress_label.setText(f"Error: {error}")
        QMessageBox.warning(self, "Scan Error", f"Could not scan file:\n{error}")

    def _save_report(self):
        if not self._pending_report:
            return
        incident_id = self._db.save(self._pending_report)
        self._pending_report.id = incident_id
        self._progress_label.setText(
            f"Saved to database (ID {incident_id}) — {self._pending_report.cave_name}"
        )
        self._save_btn.setEnabled(False)
        self._load_table()

    def _load_table(self):
        reports = (
            self._db.get_by_cave(self._cave_name)
            if self._cave_name else self._db.get_all()
        )
        self._reports = reports
        self._table.setRowCount(len(reports))
        self._filter_label.setText(
            f"Showing {len(reports)} incident{'s' if len(reports) != 1 else ''}  "
            f"|  Total in database: {self._db.count()}"
        )

        outcome_colors = {
            "fatality":  "#C0392B",
            "rescue":    "#1E7A4A",
            "near-miss": "#C47A1A",
            "injury":    "#E07820",
        }

        for i, r in enumerate(reports):
            items = [
                r.cave_name,
                r.incident_date or "—",
                r.outcome.upper() if r.outcome else "—",
                r.cause or "—",
                f"{r.depth_of_incident:.0f}" if r.depth_of_incident else "—",
                f"{r.penetration_m:.0f}" if r.penetration_m else "—",
                r.confidence,
            ]
            for j, text in enumerate(items):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                if j == 2:
                    color = outcome_colors.get(r.outcome, "#6B7A8A")
                    item.setForeground(QColor(color))
                    font = QFont()
                    font.setBold(True)
                    item.setFont(font)
                self._table.setItem(i, j, item)

        self._table.resizeRowsToContents()

    def _on_row_selected(self):
        rows = self._table.selectedItems()
        if not rows:
            self._detail.setPlainText("")
            self._map_btn.setEnabled(False)
            self._delete_btn.setEnabled(False)
            return

        row = self._table.currentRow()
        if row < 0 or row >= len(self._reports):
            return

        r = self._reports[row]
        detail = "\n".join([
            f"Cave: {r.cave_name}  |  Date: {r.incident_date or 'Unknown'}  |  "
            f"Source: {r.source_file}",
            f"",
            f"SUMMARY: {r.summary}",
            f"",
            f"LESSONS: {r.lessons}",
            f"",
            f"Hazards: {', '.join(r.hazards_involved) or 'None recorded'}",
        ])
        self._detail.setPlainText(detail)
        self._map_btn.setEnabled(bool(r.last_known_station))
        self._delete_btn.setEnabled(True)

    def _show_on_map(self):
        row = self._table.currentRow()
        if 0 <= row < len(self._reports):
            self.show_on_map.emit(self._reports[row])

    def _delete_selected(self):
        row = self._table.currentRow()
        if row < 0 or row >= len(self._reports):
            return
        r = self._reports[row]
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete incident record for {r.cave_name} ({r.incident_date})?\n"
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._db.delete(r.id)
            self._load_table()

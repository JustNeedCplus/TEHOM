from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

DB_PATH = Path(__file__).parent.parent.parent / "data" / "incidents.db"


@dataclass
class IncidentReport:
    id:               Optional[int] = None
    cave_name:        str = ""
    incident_date:    str = ""
    diver_name:       str = "Unknown"
    diver_cert:       str = ""
    outcome:          str = ""
    cause:            str = ""
    last_known_station: str = ""
    depth_of_incident: float = 0.0
    gas_at_incident:  str = ""
    penetration_m:    float = 0.0
    hazards_involved: list = field(default_factory=list)
    summary:          str = ""
    lessons:          str = ""
    source_file:      str = ""
    raw_text:         str = ""
    confidence:       str = "medium"


class IncidentDatabase:

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self):
        conn = self._connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS incidents (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                cave_name           TEXT NOT NULL,
                incident_date       TEXT,
                diver_name          TEXT,
                diver_cert          TEXT,
                outcome             TEXT,
                cause               TEXT,
                last_known_station  TEXT,
                depth_of_incident   REAL,
                gas_at_incident     TEXT,
                penetration_m       REAL,
                hazards_involved    TEXT,
                summary             TEXT,
                lessons             TEXT,
                source_file         TEXT,
                raw_text            TEXT,
                confidence          TEXT,
                created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_incidents_cave ON incidents(cave_name);
        """)
        conn.commit()

    def save(self, report: IncidentReport) -> int:
        conn = self._connect()
        cur = conn.execute("""
            INSERT INTO incidents (
                cave_name, incident_date, diver_name, diver_cert,
                outcome, cause, last_known_station, depth_of_incident,
                gas_at_incident, penetration_m, hazards_involved,
                summary, lessons, source_file, raw_text, confidence
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            report.cave_name, report.incident_date, report.diver_name,
            report.diver_cert, report.outcome, report.cause,
            report.last_known_station, report.depth_of_incident,
            report.gas_at_incident, report.penetration_m,
            json.dumps(report.hazards_involved),
            report.summary, report.lessons, report.source_file,
            report.raw_text, report.confidence,
        ))
        conn.commit()
        return cur.lastrowid

    def get_by_cave(self, cave_name: str) -> list[IncidentReport]:
        conn = self._connect()
        rows = conn.execute("""
            SELECT * FROM incidents
            WHERE LOWER(cave_name) LIKE LOWER(?)
            ORDER BY incident_date DESC
        """, (f"%{cave_name}%",)).fetchall()
        return [self._row_to_report(r) for r in rows]

    def get_all(self) -> list[IncidentReport]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM incidents ORDER BY incident_date DESC"
        ).fetchall()
        return [self._row_to_report(r) for r in rows]

    def delete(self, incident_id: int):
        conn = self._connect()
        conn.execute("DELETE FROM incidents WHERE id = ?", (incident_id,))
        conn.commit()

    def count(self) -> int:
        conn = self._connect()
        return conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]

    def _row_to_report(self, row) -> IncidentReport:
        d = dict(row)
        d["hazards_involved"] = json.loads(d.get("hazards_involved") or "[]")
        return IncidentReport(**{
            k: v for k, v in d.items()
            if k in IncidentReport.__dataclass_fields__
        })

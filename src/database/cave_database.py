from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Optional

from ..engine.cave_model import CaveMetadata

DB_PATH = Path(__file__).parent.parent.parent / "data" / "cave_sites.db"


class CaveDatabase:

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

    def _init_db(self) -> None:
        conn = self._connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS caves (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                aliases     TEXT,
                country     TEXT,
                region      TEXT,
                latitude    REAL,
                longitude   REAL,
                total_m     REAL,
                max_depth_m REAL,
                water_type  TEXT,
                visibility_m REAL,
                flow        TEXT,
                hazards     TEXT,
                description TEXT,
                passages    TEXT,
                access      TEXT,
                sources     TEXT,
                confidence  TEXT,
                survey_file TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_caves_name ON caves(name);

            CREATE TABLE IF NOT EXISTS survey_files (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                cave_id   INTEGER REFERENCES caves(id),
                filename  TEXT NOT NULL,
                format    TEXT,
                filepath  TEXT,
                added_at  TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
        self._seed_known_caves()

    def _seed_known_caves(self) -> None:
        sites = [
            {
                "name": "Ginnie Springs",
                "aliases": ["Devil's Eye", "Devil's Ear"],
                "country": "USA",
                "region": "Florida",
                "latitude": 29.8358,
                "longitude": -82.7021,
                "total_m": 6300,
                "max_depth_m": 32,
                "water_type": "freshwater",
                "visibility_m": 30,
                "flow": "strong",
                "hazards": ["strong outflow", "silt", "restrictions"],
                "description": (
                    "World-famous cave diving site on the Santa Fe River, Florida. "
                    "Features the Devil's Eye and Devil's Ear systems with exceptional "
                    "clarity. One of the most visited underwater caves globally."
                ),
                "passages": ["Devil's Eye", "Devil's Ear", "Devil's System", "Hill 400"],
                "access": "Open to certified cave divers, fee required",
                "confidence": "high",
            },
            {
                "name": "Eagle's Nest Sink",
                "aliases": ["Eagle's Nest", "Pit of Death"],
                "country": "USA",
                "region": "Florida",
                "latitude": 28.5897,
                "longitude": -82.5983,
                "total_m": 1200,
                "max_depth_m": 91,
                "water_type": "freshwater",
                "visibility_m": 30,
                "flow": "none",
                "hazards": ["extreme depth", "narcosis", "deco obligation", "multiple fatalities"],
                "description": (
                    "Deepest known underwater cave in the USA at 91m/300ft. "
                    "Requires technical cave certification and trimix. Many fatalities recorded."
                ),
                "passages": ["Main Room", "The Garage", "The Crypt"],
                "access": "Restricted — permit required",
                "confidence": "high",
            },
            {
                "name": "Cenote Dos Ojos",
                "aliases": ["Dos Ojos", "Two Eyes"],
                "country": "Mexico",
                "region": "Quintana Roo",
                "latitude": 20.3997,
                "longitude": -87.4342,
                "total_m": 82000,
                "max_depth_m": 35,
                "water_type": "freshwater",
                "visibility_m": 60,
                "flow": "none",
                "hazards": ["halocline", "silt", "depth", "navigation complexity"],
                "description": (
                    "Part of the massive Sac Actun cave system. "
                    "Named for its two open sinkholes. World-class visibility up to 60m."
                ),
                "passages": ["Barbie Line", "Bat Cave", "T-Bone", "Ponderosa"],
                "access": "Open to certified cave divers, fee required",
                "confidence": "high",
            },
            {
                "name": "Sistema Sac Actun",
                "aliases": ["Sac Actun", "White Cave"],
                "country": "Mexico",
                "region": "Quintana Roo",
                "latitude": 20.3950,
                "longitude": -87.4000,
                "total_m": 376000,
                "max_depth_m": 119,
                "water_type": "freshwater",
                "visibility_m": 60,
                "flow": "tidal influence near coast",
                "hazards": ["halocline", "extreme length", "navigation", "depth"],
                "description": (
                    "Longest known underwater cave in the world at ~376km surveyed. "
                    "Connected to Sistema Dos Ojos in 2018. "
                    "Runs beneath the Yucatan Peninsula near Tulum."
                ),
                "passages": [
                    "Main Line", "Barbie Line", "Xibalba", "Nohoch Nah Chich",
                    "Dos Ojos section", "Dreamgate"
                ],
                "access": "Certified cave divers; various entry points",
                "confidence": "high",
            },
            {
                "name": "Tham Luang Nang Non",
                "aliases": ["Tham Luang", "Wild Boars Cave"],
                "country": "Thailand",
                "region": "Chiang Rai Province",
                "latitude": 20.3800,
                "longitude": 99.8740,
                "total_m": 10316,
                "max_depth_m": 20,
                "water_type": "freshwater",
                "visibility_m": 1,
                "flow": "extreme seasonal",
                "hazards": [
                    "monsoon flooding", "near-zero visibility", "restrictions",
                    "extreme distance", "communication loss"
                ],
                "description": (
                    "Site of the historic 2018 rescue of 13 trapped individuals. "
                    "Primarily a dry cave that floods severely during monsoon season. "
                    "The rescue required world-class cave diving expertise."
                ),
                "passages": ["Monk's Series", "Sam Yaek", "Chamber 9 (Pattaya Beach)"],
                "access": "National park — restricted access",
                "confidence": "high",
            },
            {
                "name": "Blue Spring State Park",
                "aliases": ["Blue Spring", "Orange City Blue Spring"],
                "country": "USA",
                "region": "Florida",
                "latitude": 28.9486,
                "longitude": -81.3386,
                "total_m": 280,
                "max_depth_m": 36,
                "water_type": "freshwater",
                "visibility_m": 20,
                "flow": "strong outflow",
                "hazards": ["strong flow", "depth", "manatee season restrictions"],
                "description": (
                    "Florida state park with a large freshwater spring. "
                    "Famous for manatee aggregations in winter. "
                    "Short but deep cave with strong outflow."
                ),
                "passages": ["Main boil", "Primary conduit"],
                "access": "State park — seasonal restrictions for manatees",
                "confidence": "high",
            },
            {
                "name": "Wakulla Springs",
                "aliases": ["Edward Ball Wakulla Springs"],
                "country": "USA",
                "region": "Florida",
                "latitude": 30.2349,
                "longitude": -84.3082,
                "total_m": 32000,
                "max_depth_m": 91,
                "water_type": "freshwater",
                "visibility_m": 30,
                "flow": "variable",
                "hazards": ["depth", "silt", "length", "restricted access"],
                "description": (
                    "One of the largest freshwater springs in the world. "
                    "Home to the WKPP (Wakulla Karst Plain Project) which "
                    "has mapped extensive passages using rebreathers and scooters."
                ),
                "passages": ["Turner Sink", "Sullivan connection", "Main Gallery"],
                "access": "Restricted — advanced cave/technical divers with permits",
                "confidence": "high",
            },
            {
                "name": "Abismo Anhumas",
                "aliases": ["Anhumas Abyss", "Anhumas Pit"],
                "country": "Brazil",
                "region": "Mato Grosso do Sul (Bonito)",
                "latitude": -20.5042,
                "longitude": -56.5108,
                "total_m": 500,
                "max_depth_m": 82,
                "water_type": "freshwater",
                "visibility_m": 50,
                "flow": "none",
                "hazards": ["extreme depth", "rappel approach", "narcosis", "limited access"],
                "description": (
                    "Spectacular vertical pit cave requiring a 72m rappel to reach the water. "
                    "Crystal-clear blue water with stalactites descending below the surface. "
                    "Access strictly limited to preserve the environment."
                ),
                "passages": ["Main pool", "Submerged chambers"],
                "access": "Strictly limited — guided tours only, advance booking required",
                "confidence": "high",
            },
            {
                "name": "Orda Cave",
                "aliases": ["Orda", "Ordynskaya Cave"],
                "country": "Russia",
                "region": "Perm Krai",
                "latitude": 57.1936,
                "longitude": 56.9119,
                "total_m": 4800,
                "max_depth_m": 22,
                "water_type": "freshwater",
                "visibility_m": 46,
                "flow": "very slow",
                "hazards": ["extreme cold (4°C)", "remote location", "crystal formations"],
                "description": (
                    "Longest known underwater gypsum cave in the world. "
                    "Located in the Urals. Famous for its transparent water "
                    "and otherworldly gypsum crystal formations. Water is 4°C year-round."
                ),
                "passages": ["White section", "Orda section", "Main Gallery"],
                "access": "Certified cave divers; dry suit and cold water training required",
                "confidence": "high",
            },
            {
                "name": "Pozo Azul",
                "aliases": ["Blue Well"],
                "country": "Spain",
                "region": "Burgos, Castile and Leon",
                "latitude": 42.5528,
                "longitude": -3.5894,
                "total_m": 8050,
                "max_depth_m": 90,
                "water_type": "freshwater",
                "visibility_m": 10,
                "flow": "variable — very strong in wet season",
                "hazards": [
                    "extreme length", "extreme depth", "floods", "cold", "remote location"
                ],
                "description": (
                    "One of the deepest and longest underwater caves in Europe. "
                    "Has been progressively extended using rebreathers and DPVs. "
                    "Multiple sump sections with surface intervals in between."
                ),
                "passages": ["Sump 1", "Sump 2", "Sump 3", "Dry galleries between sumps"],
                "access": "Highly technical — world-class expedition divers only",
                "confidence": "high",
            },
        ]

        conn = self._connect()
        for site in sites:
            existing = conn.execute(
                "SELECT id FROM caves WHERE name = ?", (site["name"],)
            ).fetchone()
            if existing:
                continue

            conn.execute("""
                INSERT INTO caves
                    (name, aliases, country, region, latitude, longitude,
                     total_m, max_depth_m, water_type, visibility_m, flow,
                     hazards, description, passages, access, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                site["name"],
                json.dumps(site.get("aliases", [])),
                site.get("country", ""),
                site.get("region", ""),
                site.get("latitude", 0.0),
                site.get("longitude", 0.0),
                site.get("total_m", 0.0),
                site.get("max_depth_m", 0.0),
                site.get("water_type", "freshwater"),
                site.get("visibility_m", 0.0),
                site.get("flow", "unknown"),
                json.dumps(site.get("hazards", [])),
                site.get("description", ""),
                json.dumps(site.get("passages", [])),
                site.get("access", ""),
                site.get("confidence", "medium"),
            ))
        conn.commit()

    def search(self, query: str) -> list[dict]:
        conn = self._connect()
        q = f"%{query.lower()}%"
        rows = conn.execute("""
            SELECT * FROM caves
            WHERE lower(name) LIKE ?
               OR lower(aliases) LIKE ?
               OR lower(country) LIKE ?
               OR lower(region) LIKE ?
            ORDER BY name
            LIMIT 20
        """, (q, q, q, q)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_by_name(self, name: str) -> Optional[dict]:
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM caves WHERE lower(name) = ?", (name.lower(),)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def upsert_from_ai(self, data: dict) -> None:
        conn = self._connect()
        existing = conn.execute(
            "SELECT id FROM caves WHERE lower(name) = ?",
            (data.get("name", "").lower(),)
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE caves SET
                    country = ?, region = ?, latitude = ?, longitude = ?,
                    total_m = ?, max_depth_m = ?, water_type = ?,
                    visibility_m = ?, flow = ?, hazards = ?,
                    description = ?, passages = ?, access = ?,
                    confidence = ?, updated_at = datetime('now')
                WHERE lower(name) = ?
            """, (
                data.get("country", ""),
                data.get("region", ""),
                data.get("latitude", 0.0),
                data.get("longitude", 0.0),
                data.get("total_surveyed_m", data.get("total_m", 0.0)),
                data.get("max_depth_m", 0.0),
                data.get("water_type", "freshwater"),
                data.get("visibility_m", 0.0),
                data.get("flow", "unknown"),
                json.dumps(data.get("hazards", [])),
                data.get("description", ""),
                json.dumps(data.get("known_passages", data.get("passages", []))),
                data.get("access", ""),
                data.get("confidence", "medium"),
                data.get("name", "").lower(),
            ))
        else:
            conn.execute("""
                INSERT INTO caves
                    (name, aliases, country, region, latitude, longitude,
                     total_m, max_depth_m, water_type, visibility_m, flow,
                     hazards, description, passages, access, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("name", "Unknown"),
                json.dumps(data.get("aliases", [])),
                data.get("country", ""),
                data.get("region", ""),
                data.get("latitude", 0.0),
                data.get("longitude", 0.0),
                data.get("total_surveyed_m", data.get("total_m", 0.0)),
                data.get("max_depth_m", 0.0),
                data.get("water_type", "freshwater"),
                data.get("visibility_m", 0.0),
                data.get("flow", "unknown"),
                json.dumps(data.get("hazards", [])),
                data.get("description", ""),
                json.dumps(data.get("known_passages", data.get("passages", []))),
                data.get("access", ""),
                data.get("confidence", "medium"),
            ))
        conn.commit()

    def all_caves(self) -> list[dict]:
        conn = self._connect()
        rows = conn.execute("SELECT * FROM caves ORDER BY country, name").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def to_metadata(self, data: dict) -> CaveMetadata:
        return CaveMetadata(
            name=data.get("name", "Unknown"),
            country=data.get("country", ""),
            region=data.get("region", ""),
            latitude=data.get("latitude", 0.0),
            longitude=data.get("longitude", 0.0),
            max_depth_m=data.get("max_depth_m", 0.0),
            total_surveyed_m=data.get("total_m", 0.0),
            water_type=data.get("water_type", "freshwater"),
            visibility_m=data.get("visibility_m", 0.0),
            flow=data.get("flow", "none"),
            access=data.get("access", ""),
            hazards=json.loads(data.get("hazards", "[]"))
                if isinstance(data.get("hazards"), str) else data.get("hazards", []),
            description=data.get("description", ""),
        )

    @staticmethod
    def _row_to_dict(row) -> dict:
        if row is None:
            return {}
        d = dict(row)
        for key in ("aliases", "hazards", "passages", "sources"):
            if isinstance(d.get(key), str):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    d[key] = []
        return d

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

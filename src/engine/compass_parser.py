from __future__ import annotations
import re
from pathlib import Path
from typing import Optional

from .cave_model import CaveSystem, CaveMetadata, Survey, Shot, Station, LRUD


_FORMAT_FIELDS = {
    "D": "length",
    "A": "bearing",
    "V": "inclination",
    "L": "lrud_l",
    "R": "lrud_r",
    "U": "lrud_u",
    "d": "lrud_d",
}

FORM_FEED = "\x0c"


def parse_compass_dat(filepath: str | Path) -> CaveSystem:
    filepath = Path(filepath)
    text = filepath.read_text(encoding="utf-8", errors="replace")
    return _parse_text(text, filepath.stem)


def parse_compass_dat_string(text: str, cave_name: str = "Unnamed Cave") -> CaveSystem:
    return _parse_text(text, cave_name)


def _parse_text(text: str, default_name: str) -> CaveSystem:
    blocks = re.split(r"\x0c", text)
    cave_name = default_name
    metadata = CaveMetadata(name=cave_name)
    cave = CaveSystem(cave_name, metadata)

    for block in blocks:
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 4:
            continue

        survey = _parse_survey_block(lines, cave_name)
        if survey:
            cave.add_survey(survey)

    cave.compute_coordinates()
    return cave


def _parse_survey_block(lines: list[str], cave_name: str) -> Optional[Survey]:
    try:
        header = lines[0].strip()
        if not header:
            return None

        survey_name = header
        date_str = ""
        surveyors = []
        declination = 0.0

        idx = 1
        if idx < len(lines):
            parts = lines[idx].split()
            if parts:
                survey_name = parts[0]
                if len(parts) > 1:
                    date_str = parts[1]
        idx += 1

        if idx < len(lines):
            surveyors = [s.strip() for s in lines[idx].split(",") if s.strip()]
        idx += 1

        if idx < len(lines):
            fmt_line = lines[idx].strip()
            decl_match = re.search(r"DECLINATION:\s*([-\d.]+)", fmt_line, re.IGNORECASE)
            if decl_match:
                declination = float(decl_match.group(1))
            elif fmt_line:
                parts = fmt_line.split()
                if parts:
                    try:
                        declination = float(parts[0])
                    except ValueError:
                        pass
        idx += 1

        survey = Survey(
            name=survey_name,
            date=date_str,
            surveyors=surveyors,
            declination=declination,
        )

        if idx < len(lines) and re.match(r"[A-Z\s]+FROM", lines[idx], re.IGNORECASE):
            idx += 1

        stations_seen: dict[str, Station] = {}

        for line in lines[idx:]:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            comment = ""
            if ";" in line:
                line, comment = line.split(";", 1)
                comment = comment.strip()
            if "/" in line:
                line, comment = line.split("/", 1)
                comment = comment.strip()

            parts = line.split()
            if len(parts) < 8:
                continue

            try:
                from_st = parts[0]
                to_st = parts[1]
                length = float(parts[2])
                bearing = float(parts[3])
                inclination = float(parts[4])
                lrud_l = float(parts[5]) if parts[5] not in ("-", "--") else 0.0
                lrud_r = float(parts[6]) if parts[6] not in ("-", "--") else 0.0
                lrud_u = float(parts[7]) if parts[7] not in ("-", "--") else 0.0
                lrud_d = float(parts[8]) if len(parts) > 8 and parts[8] not in ("-", "--") else 0.0

                lrud = LRUD(lrud_l, lrud_r, lrud_u, lrud_d)
                flags = parts[9] if len(parts) > 9 else ""

                shot = Shot(
                    from_station=from_st,
                    to_station=to_st,
                    length=max(0.0, length),
                    bearing=bearing % 360,
                    inclination=max(-90.0, min(90.0, inclination)),
                    lrud_to=lrud,
                    flags=flags,
                    comment=comment,
                )
                survey.shots.append(shot)

                for name in (from_st, to_st):
                    if name not in stations_seen:
                        stations_seen[name] = Station(name, lrud=lrud if name == to_st else None)

            except (ValueError, IndexError):
                continue

        survey.stations = stations_seen
        return survey if survey.shots else None

    except Exception:
        return None


def generate_sample_dat(cave_name: str = "Sample Underwater Cave") -> str:
    return f"""{cave_name}
MAIN  01/15/2024  Main passage survey
J. Smith, A. Doe, B. Jones
DECLINATION: 3.5 CORRECTED SURVEY

FROM  TO  LENGTH  BEARING  INC  LEFT  RIGHT  UP  DOWN  FLAGS  COMMENT
A1  A2  10.5  045.0  -5.0  1.2  1.5  0.8  1.0
A2  A3  8.3   048.0  -3.0  1.0  1.8  0.9  1.1
A3  A4  12.1  052.0  -8.0  1.5  1.2  1.0  0.8
A4  A5  9.7   055.0  -4.0  2.0  2.2  1.2  1.0
A5  A6  15.2  060.0  -2.0  1.8  1.5  1.1  0.9
A6  A7  11.4  058.0  -6.0  1.3  1.6  0.8  1.2
A7  A8  8.9   050.0  -5.0  1.0  1.0  0.7  0.9
A8  A9  13.6  045.0  -3.0  1.4  1.7  1.0  1.1
A9  A10 10.2  040.0  -7.0  1.6  1.4  0.9  1.0
\x0c
{cave_name}
BRANCH  01/15/2024  Side passage survey
J. Smith, A. Doe
DECLINATION: 3.5 CORRECTED SURVEY

FROM  TO  LENGTH  BEARING  INC  LEFT  RIGHT  UP  DOWN  FLAGS  COMMENT
A4  B1  7.8   135.0  -2.0  0.8  0.9  0.6  0.7
B1  B2  9.1   140.0  -4.0  0.7  1.0  0.6  0.8
B2  B3  11.3  145.0  -6.0  0.9  0.8  0.7  0.6
B3  B4  8.5   150.0  -3.0  1.1  0.9  0.8  0.7
B4  B5  6.9   148.0  -5.0  0.8  1.0  0.6  0.8
\x0c
"""

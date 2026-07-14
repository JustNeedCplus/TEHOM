from __future__ import annotations
import re
import math
from pathlib import Path
from typing import Optional

from .cave_model import CaveSystem, CaveMetadata, Survey, Shot, Station, LRUD


def parse_survex(filepath: str | Path) -> CaveSystem:
    filepath = Path(filepath)
    text = filepath.read_text(encoding="utf-8", errors="replace")
    return _parse_svx_text(text, filepath.stem)


def parse_survex_string(text: str, cave_name: str = "Unnamed Cave") -> CaveSystem:
    return _parse_svx_text(text, cave_name)


def _parse_svx_text(text: str, default_name: str) -> CaveSystem:
    metadata = CaveMetadata(name=default_name)
    cave = CaveSystem(default_name, metadata)

    lines = text.splitlines()
    _parse_block(lines, cave, default_name)
    cave.compute_coordinates()
    return cave


def _parse_block(lines: list[str], cave: CaveSystem, cave_name: str) -> None:
    survey_stack: list[Survey] = []
    current_survey: Optional[Survey] = None

    data_order: list[str] = ["from", "to", "tape", "compass", "clino"]
    declination = 0.0

    i = 0
    while i < len(lines):
        raw = lines[i].strip()
        i += 1

        if ";" in raw:
            raw = raw[:raw.index(";")].strip()
        if not raw:
            continue

        low = raw.lower()

        if low.startswith("*begin"):
            name = raw[6:].strip() or f"survey_{len(cave.surveys)}"
            survey = Survey(name=name, declination=declination)
            if current_survey is not None:
                survey_stack.append(current_survey)
            current_survey = survey

        elif low.startswith("*end"):
            if current_survey and current_survey.shots:
                cave.add_survey(current_survey)
            if survey_stack:
                current_survey = survey_stack.pop()
            else:
                current_survey = None

        elif low.startswith("*calibrate") or low.startswith("*declination"):
            m = re.search(r"[-+]?\d+\.?\d*", raw[raw.lower().index("decl") if "decl" in low else 10:])
            if m:
                declination = float(m.group())
            if current_survey:
                current_survey.declination = declination

        elif low.startswith("*data"):
            fields = raw.split()[1:]
            if fields and fields[0].lower() not in ("normal", "diving", "cartesian"):
                pass
            else:
                if len(fields) > 1:
                    data_order = [f.lower() for f in fields[1:]]

        elif low.startswith("*"):
            continue

        else:
            if current_survey is None:
                current_survey = Survey(name=cave_name, declination=declination)

            parts = raw.split()
            shot = _parse_data_row(parts, data_order)
            if shot:
                current_survey.shots.append(shot)
                for name in (shot.from_station, shot.to_station):
                    if name not in current_survey.stations:
                        current_survey.stations[name] = Station(name)

    if current_survey and current_survey.shots:
        cave.add_survey(current_survey)


def _parse_data_row(parts: list[str], order: list[str]) -> Optional[Shot]:
    if len(parts) < 3:
        return None
    try:
        vals: dict[str, str] = {}
        for idx, field in enumerate(order):
            if idx < len(parts):
                vals[field] = parts[idx]

        from_st = vals.get("from", parts[0])
        to_st = vals.get("to", parts[1])

        length = float(vals.get("tape", vals.get("length", "0")))
        bearing = float(vals.get("compass", vals.get("bearing", "0")))
        clino = float(vals.get("clino", vals.get("gradient", "0")))

        lrud = None
        if all(k in vals for k in ("left", "right", "up", "down")):
            lrud = LRUD(
                float(vals["left"]),
                float(vals["right"]),
                float(vals["up"]),
                float(vals["down"]),
            )

        return Shot(
            from_station=from_st,
            to_station=to_st,
            length=max(0.0, length),
            bearing=bearing % 360,
            inclination=max(-90.0, min(90.0, clino)),
            lrud_to=lrud,
        )
    except (ValueError, IndexError, KeyError):
        return None

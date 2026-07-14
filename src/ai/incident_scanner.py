from __future__ import annotations
import json
import re
import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..database.incident_database import IncidentReport

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

try:
    import docx as python_docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False


EXTRACTION_PROMPT = """You are analysing a cave diving incident report for a SAR database.

Extract all available information and return ONLY a JSON object with these fields:
{
  "cave_name": "name of the cave system",
  "incident_date": "YYYY-MM-DD or partial date or empty string",
  "diver_name": "diver's name or Unknown",
  "diver_cert": "certification level e.g. cave diver, open water, tech",
  "outcome": "fatality OR rescue OR near-miss OR injury",
  "cause": "primary cause in 5-10 words e.g. gas failure, silt-out, entanglement",
  "last_known_station": "station name or landmark where diver was last seen/known position",
  "depth_of_incident": 0.0,
  "gas_at_incident": "description of gas situation e.g. out of gas, turned at 1/3",
  "penetration_m": 0.0,
  "hazards_involved": ["list", "of", "hazards"],
  "summary": "2-3 sentence factual summary of what happened",
  "lessons": "key lessons or contributing factors in 2-3 sentences",
  "confidence": "high if data is clear, medium if inferred, low if very sparse"
}

Return ONLY valid JSON. No preamble, no markdown fences.

INCIDENT REPORT TEXT:
"""


def extract_text_from_file(filepath: str) -> str:
    path = Path(filepath)
    ext  = path.suffix.lower()

    if ext == ".pdf":
        if not PYPDF_AVAILABLE:
            raise RuntimeError("pypdf not installed. Run: pip install pypdf")
        reader = PdfReader(filepath)
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    elif ext == ".docx":
        if not DOCX_AVAILABLE:
            raise RuntimeError("python-docx not installed. Run: pip install python-docx")
        doc = python_docx.Document(filepath)
        return "\n".join(p.text for p in doc.paragraphs)

    elif ext in (".txt", ".md", ".rtf"):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    else:
        raise ValueError(f"Unsupported file type: {ext}")


def _offline_extract(text: str, filename: str) -> dict:
    text_lower = text.lower()

    cave_name = "Unknown"
    cave_patterns = [
        r"(?:cave|sink|spring|system|cenote)[:\s]+([A-Z][^\n,\.]{3,40})",
        r"([A-Z][a-z]+ (?:Cave|Spring|Sink|System|Cenote))",
        r"incident at ([A-Z][^\n,\.]{3,30})",
    ]
    for pat in cave_patterns:
        m = re.search(pat, text)
        if m:
            cave_name = m.group(1).strip()
            break

    date_str = ""
    date_m = re.search(r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\w+ \d{1,2},? \d{4})", text)
    if date_m:
        date_str = date_m.group(1)

    outcome = "unknown"
    if any(w in text_lower for w in ["fatal", "death", "died", "deceased", "drowned"]):
        outcome = "fatality"
    elif any(w in text_lower for w in ["rescued", "recovery", "recovered alive"]):
        outcome = "rescue"
    elif any(w in text_lower for w in ["near miss", "near-miss", "close call"]):
        outcome = "near-miss"

    depth = 0.0
    depth_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:m|metres|meters)\b", text_lower)
    if depth_m:
        depth = float(depth_m.group(1))

    hazards = []
    hazard_keywords = [
        "silt", "silt-out", "silted", "entanglement", "entangled",
        "out of gas", "gas failure", "lost guideline", "guideline",
        "narcosis", "oxygen toxicity", "decompression", "restriction",
        "flow", "current", "visibility", "darkness", "equipment failure",
    ]
    for kw in hazard_keywords:
        if kw in text_lower:
            hazards.append(kw)

    summary = text[:300].replace("\n", " ").strip()

    return {
        "cave_name":           cave_name,
        "incident_date":       date_str,
        "diver_name":          "Unknown",
        "diver_cert":          "",
        "outcome":             outcome,
        "cause":               ", ".join(hazards[:3]) if hazards else "unknown",
        "last_known_station":  "",
        "depth_of_incident":   depth,
        "gas_at_incident":     "",
        "penetration_m":       0.0,
        "hazards_involved":    hazards,
        "summary":             summary,
        "lessons":             "Extracted offline — connect AI for full analysis.",
        "confidence":          "low",
    }


class IncidentScanner:

    def __init__(self, api_key: str = ""):
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self._client = None
        self._setup_client()

    def _setup_client(self):
        try:
            import anthropic
            if self._api_key:
                self._client = anthropic.Anthropic(api_key=self._api_key)
        except ImportError:
            pass

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def scan_file(self, filepath: str) -> "IncidentReport":
        from ..database.incident_database import IncidentReport

        filename = Path(filepath).name
        raw_text = extract_text_from_file(filepath)

        if not raw_text.strip():
            raise ValueError("Could not extract text from file — it may be scanned/image-only.")

        text_for_ai = raw_text[:8000]

        if self.is_available:
            extracted = self._ai_extract(text_for_ai)
        else:
            extracted = _offline_extract(text_for_ai, filename)

        return IncidentReport(
            cave_name          = extracted.get("cave_name", "Unknown"),
            incident_date      = extracted.get("incident_date", ""),
            diver_name         = extracted.get("diver_name", "Unknown"),
            diver_cert         = extracted.get("diver_cert", ""),
            outcome            = extracted.get("outcome", "unknown"),
            cause              = extracted.get("cause", ""),
            last_known_station = extracted.get("last_known_station", ""),
            depth_of_incident  = float(extracted.get("depth_of_incident") or 0),
            gas_at_incident    = extracted.get("gas_at_incident", ""),
            penetration_m      = float(extracted.get("penetration_m") or 0),
            hazards_involved   = extracted.get("hazards_involved", []),
            summary            = extracted.get("summary", ""),
            lessons            = extracted.get("lessons", ""),
            source_file        = filename,
            raw_text           = raw_text,
            confidence         = extracted.get("confidence", "medium"),
        )

    def _ai_extract(self, text: str) -> dict:
        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": EXTRACTION_PROMPT + text
                }]
            )
            raw = response.content[0].text.strip()
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.split("```")[0]
            return json.loads(raw.strip())
        except Exception as e:
            return _offline_extract(text, "")

    def generate_sar_context(self, cave_name: str,
                              incidents: list) -> str:
        if not incidents:
            return "No previous incidents recorded for this cave in the database."

        if not self.is_available:
            return self._offline_sar_context(cave_name, incidents)

        incident_summaries = []
        for inc in incidents:
            incident_summaries.append(
                f"- {inc.incident_date or 'Unknown date'}: {inc.outcome.upper()} "
                f"— {inc.cause}. Depth: {inc.depth_of_incident}m. "
                f"Penetration: {inc.penetration_m}m. {inc.summary}"
            )

        prompt = f"""Based on these past incidents at {cave_name}, provide a concise SAR context summary (max 200 words) covering:
1. Most dangerous sections (by incident frequency/location)
2. Most common causes of incidents
3. Key warnings for rescue divers based on historical patterns

PAST INCIDENTS:
{chr(10).join(incident_summaries)}

Be direct and prioritise life-safety information."""

        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()
        except Exception:
            return self._offline_sar_context(cave_name, incidents)

    def _offline_sar_context(self, cave_name: str, incidents: list) -> str:
        fatalities = [i for i in incidents if i.outcome == "fatality"]
        rescues    = [i for i in incidents if i.outcome == "rescue"]
        all_hazards = []
        for inc in incidents:
            all_hazards.extend(inc.hazards_involved)

        hazard_counts = {}
        for h in all_hazards:
            hazard_counts[h] = hazard_counts.get(h, 0) + 1
        top_hazards = sorted(hazard_counts.items(), key=lambda x: x[1], reverse=True)[:3]

        lines = [
            f"HISTORICAL INCIDENT SUMMARY — {cave_name.upper()}",
            f"Total recorded incidents: {len(incidents)}",
            f"Fatalities: {len(fatalities)}  |  Rescues: {len(rescues)}",
        ]
        if top_hazards:
            lines.append(f"Most common hazards: {', '.join(h for h, _ in top_hazards)}")
        if fatalities:
            depths = [i.depth_of_incident for i in fatalities if i.depth_of_incident > 0]
            if depths:
                lines.append(f"Average fatality depth: {sum(depths)/len(depths):.0f}m")

        return "\n".join(lines)

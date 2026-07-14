from __future__ import annotations
import json
import os
from typing import Optional, Generator

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


SYSTEM_PROMPT = """You are an expert cave diving assistant integrated into TEHOM,
a 3D underwater cave mapping application used by cave divers and search-and-rescue teams.

Your knowledge includes:
- Underwater cave systems worldwide (Florida, Mexico, Brazil, Thailand, Europe, etc.)
- Cave diving safety protocols (rule of thirds, S-drills, team diving)
- Survey techniques: Compass, Survex, Therion formats
- SAR (Search & Rescue) procedures for missing divers
- Hydrological and geological context of cave systems
- Famous cave diving incidents and their lessons
- Mapping conventions and survey notation

When a user asks about a specific cave:
1. Provide its location (country, region, GPS if known)
2. Key measurements: total surveyed length, max depth, width/height ranges
3. Notable passages and features
4. Known hazards and environmental conditions
5. Visibility and flow conditions typical
6. Access status (open to public, restricted, permit required)
7. Historical significance and discovery timeline
8. Any known accidents and lessons learned

For SAR operations:
- Prioritize actionable information
- Describe known branching points and likely paths
- Note air supply and depth considerations
- Reference any guideline systems or markers known to exist

Always be factual. If you are uncertain about specific measurements, say so.
Distinguish between well-documented caves and those with limited survey data.
"""

CAVE_LOOKUP_PROMPT = """The user is searching for the cave: "{cave_name}"

Please respond with a JSON object in this exact format:
{{
  "found": true/false,
  "name": "Official cave name",
  "aliases": ["other names"],
  "country": "Country",
  "region": "State/Province/Region",
  "latitude": 00.0000,
  "longitude": 00.0000,
  "total_surveyed_m": 00000,
  "max_depth_m": 00,
  "water_type": "freshwater/saltwater/brackish",
  "visibility_m": 00,
  "flow": "none/mild/moderate/strong",
  "hazards": ["list", "of", "hazards"],
  "description": "2-3 sentence description",
  "known_passages": ["main tunnel", "..."],
  "access": "Open to certified divers / Permit required / etc.",
  "sources": ["NSS-CDS", "..."],
  "confidence": "high/medium/low"
}}

If the cave is not found or unknown, set found to false and fill what you can.
"""


class CaveAssistant:

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self._client: Optional["anthropic.Anthropic"] = None

        if ANTHROPIC_AVAILABLE and self.api_key:
            self._client = anthropic.Anthropic(api_key=self.api_key)

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def lookup_cave(self, cave_name: str) -> dict:
        if not self.is_available:
            return self._offline_lookup(cave_name)

        try:
            prompt = CAVE_LOOKUP_PROMPT.format(cave_name=cave_name)
            message = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()

            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            return json.loads(raw)

        except Exception as e:
            return {
                "found": False,
                "name": cave_name,
                "error": str(e),
                "description": f"Could not retrieve data for '{cave_name}'.",
            }

    def chat(self, user_message: str, history: list[dict] | None = None) -> str:
        if not self.is_available:
            return (
                "AI assistant is offline. Set ANTHROPIC_API_KEY in your environment "
                "or enter it in Settings → API Key."
            )

        messages = list(history or [])
        messages.append({"role": "user", "content": user_message})

        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=messages,
            )
            return response.content[0].text

        except Exception as e:
            return f"Error communicating with AI: {e}"

    def chat_stream(
        self, user_message: str, history: list[dict] | None = None
    ) -> Generator[str, None, None]:
        if not self.is_available:
            yield "AI assistant is offline. Set ANTHROPIC_API_KEY in Settings."
            return

        messages = list(history or [])
        messages.append({"role": "user", "content": user_message})

        try:
            with self._client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    yield text

        except Exception as e:
            yield f"\n[Error: {e}]"

    def sar_briefing(self, cave_name: str, missing_since: str = "", diver_profile: str = "") -> str:
        if not self.is_available:
            return self._offline_sar_briefing(cave_name, missing_since, diver_profile)

        prompt = f"""EMERGENCY SAR BRIEFING REQUEST

Cave: {cave_name}
Missing since: {missing_since or 'Unknown'}
Diver profile: {diver_profile or 'Unknown — assume recreational cave diver'}

Generate a structured SAR briefing covering:
1. Cave layout summary (primary route, known branches, dead ends)
2. Most likely locations to check first (by dive time from entrance)
3. Critical depth and gas management thresholds for rescuers
4. Known hazards rescuers will encounter
5. Historical incidents at this site (if any)
6. Recommended team configuration and equipment
7. Emergency contact resources (local dive rescue teams, agencies)

Format clearly with section headers. Prioritize speed of comprehension.
"""
        try:
            return self.chat(prompt)
        except Exception:
            return self._offline_sar_briefing(cave_name, missing_since, diver_profile)

    def _offline_sar_briefing(self, cave_name: str, missing_since: str = "", diver_profile: str = "") -> str:
        data = self._offline_lookup(cave_name)

        if not data.get("found"):
            return (
                f"OFFLINE SAR BRIEFING — {cave_name.upper()}\n"
                f"{'=' * 50}\n\n"
                f"WARNING: No offline data available for this cave system.\n"
                f"AI assistant is offline. Connect to internet and set API key for full briefing.\n\n"
                f"IMMEDIATE ACTIONS:\n"
                f"  1. Contact local cave diving community for site-specific knowledge\n"
                f"  2. Contact NSS-CDS or NACD for regional SAR contacts\n"
                f"  3. NSS-CDS Emergency: contact through nss-cds.org\n"
                f"  4. Do not send rescue divers without site-specific briefing\n"
            )

        name        = data.get("name", cave_name)
        max_depth   = data.get("max_depth_m", 0)
        total_m     = data.get("total_surveyed_m", 0)
        visibility  = data.get("visibility_m", 0)
        flow        = data.get("flow", "unknown")
        hazards     = data.get("hazards", [])
        passages    = data.get("known_passages", [])
        description = data.get("description", "")
        water_type  = data.get("water_type", "freshwater")
        access      = data.get("access", "Unknown")
        region      = data.get("region", "")
        country     = data.get("country", "")

        sac = 20.0
        depth_factor = 1 + max_depth / 10.0
        sac_depth = sac * depth_factor
        penetration_m = (total_m / 2) if total_m else 100
        transit_min = penetration_m / 15.0
        min_gas_l = sac_depth * transit_min * 3
        turn_time = transit_min

        lines = [
            f"OFFLINE SAR BRIEFING — {name.upper()}",
            f"{'=' * 60}",
            f"[OFFLINE MODE — Generated from local database. AI unavailable.]",
            f"Missing since: {missing_since or 'Unknown'}",
            f"Diver profile: {diver_profile or 'Unknown — assume certified cave diver'}",
            f"",
            f"CAVE OVERVIEW",
            f"-" * 40,
            f"  Location:        {region}, {country}",
            f"  Max depth:       {max_depth} m ({max_depth * 3.28:.0f} ft)",
            f"  Surveyed length: {total_m} m ({total_m * 3.28:.0f} ft)",
            f"  Visibility:      {visibility} m",
            f"  Water type:      {water_type.capitalize()}",
            f"  Flow:            {flow.capitalize()}",
            f"  Access:          {access}",
            f"",
            f"  {description}",
            f"",
            f"KNOWN PASSAGES (search priority order)",
            f"-" * 40,
        ]
        for i, p in enumerate(passages, 1):
            lines.append(f"  {i}. {p}")

        lines += [
            f"",
            f"HAZARDS FOR RESCUE DIVERS",
            f"-" * 40,
        ]
        for h in hazards:
            lines.append(f"  ! {h}")

        lines += [
            f"",
            f"GAS PLANNING (estimated — verify with dive team)",
            f"-" * 40,
            f"  Max depth:            {max_depth} m",
            f"  SAC at depth:         {sac_depth:.0f} L/min (20 L/min surface SAC)",
            f"  Est. transit to mid:  {transit_min:.0f} min at 15 m/min",
            f"  Min gas per diver:    {min_gas_l:.0f} L (Rule of Thirds)",
            f"  Turn time from entry: {turn_time:.0f} min",
            f"",
            f"SEARCH PRIORITIES",
            f"-" * 40,
            f"  1. Primary route to planned max penetration of missing diver",
            f"  2. All named passage branches within gas range",
            f"  3. Any air bells or elevated sections above primary route",
            f"  4. Restriction points where diver may be entrapped",
            f"",
            f"EMERGENCY CONTACTS",
            f"-" * 40,
            f"  NSS-CDS (Cave Diving Section):  nss-cds.org",
            f"  NACD:                           nacdive.com",
            f"  Local Sheriff (Florida):         911",
            f"  Florida Fish & Wildlife:         *FWC (*392)",
            f"",
            f"NOTE: This is an offline briefing from cached data.",
            f"Verify all information with the most current survey before rescue diver entry.",
        ]

        return "\n".join(lines)

    def generate_reconstruction_hints(self, cave_name: str) -> str:
        prompt = f"""For the cave: {cave_name}

Generate estimated survey data I can use to create a 3D reconstruction.
Provide:
1. Approximate passage count and typical dimensions (height × width in meters)
2. Estimated total length and depth profile
3. General layout: linear, branching, looping, etc.
4. Notable features (haloclines, air bells, restrictions, large rooms)
5. Suggested color coding for different passage zones

Be clear these are approximations for visualization purposes only.
"""
        try:
            return self.chat(prompt)
        except Exception:
            data = self._offline_lookup(cave_name)
            if data.get("found"):
                passages = data.get("known_passages", [])
                depth = data.get("max_depth_m", 30)
                length = data.get("total_surveyed_m", 500)
                return (
                    f"[OFFLINE MODE] Using cached data for {data['name']}.\n"
                    f"Max depth: {depth}m. Total surveyed: {length}m.\n"
                    f"Known passages: {', '.join(passages)}.\n"
                    f"Passage dimensions estimated — connect AI for detailed reconstruction."
                )
            return "[OFFLINE] No reconstruction data available for this cave. Connect to AI for full reconstruction."

    @staticmethod
    def _offline_lookup(cave_name: str) -> dict:
        known = {
            "ginnie springs": {
                "found": True,
                "name": "Ginnie Springs",
                "country": "USA",
                "region": "Florida",
                "latitude": 29.8358,
                "longitude": -82.7021,
                "total_surveyed_m": 6300,
                "max_depth_m": 32,
                "water_type": "freshwater",
                "visibility_m": 30,
                "flow": "strong outflow",
                "hazards": ["Strong outflow", "silt", "restrictions in Devil's Ear", "flow reversal after rain"],
                "description": "World-famous cave diving destination on the Santa Fe River. Features Devil's Eye and Devil's Ear with crystal-clear water and strong outflow. One of the most dived underwater caves in the world.",
                "known_passages": ["Devil's Eye", "Devil's Ear", "Devil's System", "Hill 400", "Eye Sink"],
                "access": "Open to certified cave divers, fee required",
                "confidence": "high",
            },
            "devils system": {
                "found": True,
                "name": "Devil's System (Devil's Eye/Ear)",
                "country": "USA",
                "region": "Florida — Gilchrist County",
                "latitude": 29.8358,
                "longitude": -82.7021,
                "total_surveyed_m": 6300,
                "max_depth_m": 32,
                "water_type": "freshwater",
                "visibility_m": 30,
                "flow": "strong outflow",
                "hazards": ["Strong outflow", "restrictions", "silt", "multiple entry points can confuse navigation"],
                "description": "Part of the Ginnie Springs complex. Devil's Eye is the primary entry — a large open basin. Devil's Ear is a restriction entrance with very strong flow. Both connect into the same system.",
                "known_passages": ["Devil's Eye", "Devil's Ear", "Hill 400", "The Gallery"],
                "access": "Certified cave divers only, Ginnie Springs resort fee",
                "confidence": "high",
            },
            "eagles nest": {
                "found": True,
                "name": "Eagle's Nest Sink",
                "country": "USA",
                "region": "Florida — Hernando County",
                "latitude": 28.5897,
                "longitude": -82.5983,
                "total_surveyed_m": 1200,
                "max_depth_m": 91,
                "water_type": "freshwater",
                "visibility_m": 30,
                "flow": "none",
                "hazards": ["Extreme depth 91m", "narcosis", "decompression obligation", "silty bottom", "multiple fatalities", "trimix required below 40m"],
                "description": "The deepest known underwater cave in the USA. Known as The Pit of Death. Has claimed numerous lives. Large rooms connected by tunnels. Requires technical cave diving certification and trimix.",
                "known_passages": ["Main Room", "The Garage", "The Crypt", "Upstream Tunnel"],
                "access": "Permit required — advanced technical cave divers only",
                "confidence": "high",
            },
            "peacock springs": {
                "found": True,
                "name": "Peacock Springs State Park",
                "country": "USA",
                "region": "Florida — Suwannee County",
                "latitude": 30.1236,
                "longitude": -83.1547,
                "total_surveyed_m": 8000,
                "max_depth_m": 27,
                "water_type": "freshwater",
                "visibility_m": 25,
                "flow": "moderate outflow",
                "hazards": ["Silt", "multiple interconnected systems can disorient", "flow", "restrictions in Olsen Sink connection"],
                "description": "One of the longest underwater cave systems in the USA. Multiple springs connect including Peacock 1, Peacock 2, Peacock 3, Olsen Sink, and Orange Grove Sink. State park with well-maintained site.",
                "known_passages": ["Peacock 1", "Peacock 2", "Peacock 3", "Olsen Sink Connection", "Orange Grove Sink", "Challenge Sink"],
                "access": "State park — cave diving permit required, certified cave divers only",
                "confidence": "high",
            },
            "troy spring": {
                "found": True,
                "name": "Troy Spring State Park",
                "country": "USA",
                "region": "Florida — Lafayette County",
                "latitude": 29.9906,
                "longitude": -82.9978,
                "total_surveyed_m": 450,
                "max_depth_m": 17,
                "water_type": "freshwater",
                "visibility_m": 20,
                "flow": "moderate",
                "hazards": ["Silt disturbance", "shallow depth limits bottom time", "boat traffic on surface"],
                "description": "State park spring with a submerged Civil War steamship. The cave system is relatively short but popular. Clear water with good visibility. Suitable for cavern and entry-level cave divers.",
                "known_passages": ["Main Basin", "Primary Tunnel", "Steamship Madison wreck area"],
                "access": "State park — daily fee, cavern and cave divers welcome",
                "confidence": "high",
            },
            "madison blue": {
                "found": True,
                "name": "Madison Blue Spring State Park",
                "country": "USA",
                "region": "Florida — Madison County",
                "latitude": 30.4783,
                "longitude": -83.2408,
                "total_surveyed_m": 3200,
                "max_depth_m": 34,
                "water_type": "freshwater",
                "visibility_m": 30,
                "flow": "strong outflow",
                "hazards": ["Strong flow", "silt", "depth", "restrictions in downstream tunnels"],
                "description": "State park spring with one of the strongest flows in Florida. Crystal-clear water. Connects to a significant underwater cave system. Popular training site and exploration destination.",
                "known_passages": ["Main Basin", "Upstream Tunnel", "Downstream Tunnel", "The Gallery"],
                "access": "State park — cave diving permit required",
                "confidence": "high",
            },
            "blue grotto": {
                "found": True,
                "name": "Blue Grotto",
                "country": "USA",
                "region": "Florida — Gilchrist County",
                "latitude": 29.7489,
                "longitude": -82.7389,
                "total_surveyed_m": 120,
                "max_depth_m": 33,
                "water_type": "freshwater",
                "visibility_m": 30,
                "flow": "none",
                "hazards": ["Depth", "popular training site — diver traffic", "silt on floor", "halocline below 24m"],
                "description": "A large circular sinkhole with a cavern zone and a short cave system below. Very popular training site for cavern and cave certification courses. Has a distinct halocline.",
                "known_passages": ["Main Basin", "Cavern Zone", "Cave Restriction"],
                "access": "Private facility — daily fee, all certification levels welcome",
                "confidence": "high",
            },
            "morrison springs": {
                "found": True,
                "name": "Morrison Springs County Park",
                "country": "USA",
                "region": "Florida — Walton County",
                "latitude": 30.6717,
                "longitude": -85.9003,
                "total_surveyed_m": 600,
                "max_depth_m": 18,
                "water_type": "freshwater",
                "visibility_m": 15,
                "flow": "moderate",
                "hazards": ["Silt", "visibility drops in wet season", "boat traffic", "snorkellers in cavern zone"],
                "description": "County park spring in the Florida panhandle. Less visited than north-central Florida springs. Good cavern zone with short cave system. Popular with families and divers.",
                "known_passages": ["Main Spring", "Cavern Zone", "Upper Tunnel"],
                "access": "County park — day use fee",
                "confidence": "high",
            },
            "wakulla springs": {
                "found": True,
                "name": "Wakulla Springs State Park",
                "country": "USA",
                "region": "Florida — Wakulla County",
                "latitude": 30.2347,
                "longitude": -84.3086,
                "total_surveyed_m": 9600,
                "max_depth_m": 91,
                "water_type": "freshwater",
                "visibility_m": 30,
                "flow": "variable — can reverse",
                "hazards": ["Extreme depth in main spring", "very long penetrations", "flow reversal", "complex passage network", "mastodon fossils on floor"],
                "description": "One of the largest and deepest freshwater springs in the world. Part of a massive cave network connected to other Wakulla County springs. Site of significant scientific exploration. Mastodon bones found on floor.",
                "known_passages": ["Main Spring Bowl", "Leon Sinks Connection", "Upstream Tunnel", "Turner Sink Connection"],
                "access": "State park — cave diving by research permit only, not open to recreational cave divers",
                "confidence": "high",
            },
            "ichetucknee springs": {
                "found": True,
                "name": "Ichetucknee Springs State Park",
                "country": "USA",
                "region": "Florida — Columbia County",
                "latitude": 29.9806,
                "longitude": -82.7631,
                "total_surveyed_m": 800,
                "max_depth_m": 12,
                "water_type": "freshwater",
                "visibility_m": 20,
                "flow": "strong outflow",
                "hazards": ["Strong flow", "snorkellers and tubers on surface", "shallow depth", "restricted diving permits"],
                "description": "State park with multiple spring vents feeding the Ichetucknee River. Cave diving limited to specific vents. Primarily known as a tubing and snorkelling destination. Limited but interesting cave diving.",
                "known_passages": ["Blue Hole", "Mission Spring", "Singing Spring"],
                "access": "State park — cave diving permits strictly limited",
                "confidence": "high",
            },
            "tham luang": {
                "found": True,
                "name": "Tham Luang Nang Non",
                "country": "Thailand",
                "region": "Chiang Rai Province",
                "latitude": 20.3800,
                "longitude": 99.8740,
                "total_surveyed_m": 10316,
                "max_depth_m": 20,
                "water_type": "freshwater",
                "visibility_m": 1,
                "flow": "seasonal — extreme during monsoon",
                "hazards": ["Seasonal flooding", "very low visibility", "tight restrictions", "long distances from entrance", "communication difficulties"],
                "description": "Site of the 2018 rescue of 12 Thai boys and their coach. Located in Mae Sai district. Primarily a dry cave with seasonal flooding. The rescue was the most complex cave rescue ever attempted.",
                "known_passages": ["Monk's Series", "Sam Yaek Junction", "Chamber 9 — Pattaya Beach"],
                "access": "Restricted — national park, limited access",
                "confidence": "high",
            },
            "dos ojos": {
                "found": True,
                "name": "Cenote Dos Ojos",
                "country": "Mexico",
                "region": "Quintana Roo",
                "latitude": 20.3997,
                "longitude": -87.4342,
                "total_surveyed_m": 82000,
                "max_depth_m": 35,
                "water_type": "freshwater",
                "visibility_m": 60,
                "flow": "none",
                "hazards": ["Halocline disorientation", "silt", "depth", "vast system — navigation critical"],
                "description": "One of the most spectacular cenote dive sites in the Yucatan Peninsula. Part of the vast Sac Actun system. Named for two open sinkholes resembling eyes from the air. World-class visibility.",
                "known_passages": ["Barbie Line", "Bat Cave", "T-Bone Section", "Sac Actun Connection"],
                "access": "Open to certified cave divers, fee required",
                "confidence": "high",
            },
            "the pit": {
                "found": True,
                "name": "The Pit (Cenote Dos Ojos)",
                "country": "Mexico",
                "region": "Quintana Roo",
                "latitude": 20.3997,
                "longitude": -87.4342,
                "total_surveyed_m": 82000,
                "max_depth_m": 119,
                "water_type": "freshwater with halocline",
                "visibility_m": 60,
                "flow": "none",
                "hazards": ["Extreme depth", "halocline at 30m", "hydrogen sulphide layer", "decompression obligation", "narcosis"],
                "description": "A massive open cenote dropping to 119m with a spectacular hydrogen sulphide cloud layer. Part of the Dos Ojos system. One of the most photographed underwater cave environments in the world.",
                "known_passages": ["Main Pit", "Halocline Zone", "H2S Cloud", "Deep Section"],
                "access": "Technical cave divers only — trimix required",
                "confidence": "high",
            },
            "diepolder": {
                "found": True,
                "name": "Diepolder Cave System",
                "country": "USA",
                "region": "Florida — Hernando County",
                "latitude": 28.6167,
                "longitude": -82.4833,
                "total_surveyed_m": 500,
                "max_depth_m": 88,
                "water_type": "freshwater",
                "visibility_m": 30,
                "flow": "none",
                "hazards": ["Extreme depth", "decompression obligation", "multiple fatalities", "silty floor", "trimix required"],
                "description": "Two connected sinkholes — Diepolder 2 and Diepolder 3 — reaching extreme depths. Among the deepest cave dives accessible in Florida. Technical diving destination with significant historical fatalities.",
                "known_passages": ["Diepolder 2 Main Shaft", "Diepolder 3 Main Shaft", "Connecting Passage"],
                "access": "Permit required — technical cave divers only",
                "confidence": "high",
            },
        }

        def normalize(s: str) -> str:
            return s.lower().replace("'", "").replace("-", " ").replace("  ", " ").strip()

        query = normalize(cave_name)
        for key, data in known.items():
            if normalize(key) in query or query in normalize(key):
                return data
            for alias in data.get("aliases", []):
                if normalize(alias) in query or query in normalize(alias):
                    return data

        return {
            "found": False,
            "name": cave_name,
            "description": (
                f"'{cave_name}' is not in the offline database. "
                "Connect to the AI assistant for full global cave lookup."
            ),
            "confidence": "none",
        }

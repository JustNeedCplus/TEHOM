# TEHOM

**3D underwater cave mapping and search-and-rescue (SAR) platform**

TEHOM turns cave survey data into an interactive 3D model for planning and incident response. Load Compass (`.dat`) or Survex (`.svx`) surveys, explore passages, mark SAR incidents, estimate missing-diver probability with dead reckoning, and generate briefing PDFs. Optional AI assists with cave lookup and incident analysis.

Built for cave diving SAR planning and field-ready visualisation — not just cartography.

## Features

- 3D tube-mesh cave reconstruction from survey shots (tape, compass, clinometer, LRUD)
- Compass DAT and Survex SVX parsers with loop closure
- Station exploration with passage / voxel views
- SAR incident markers and printable briefing PDFs
- Gas-aware dead-reckoning probability estimates for missing-diver scenarios
- Optional Anthropic-powered cave assistant (offline-capable without a key)

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Optional AI
cp .env.example .env               # then set ANTHROPIC_API_KEY

python main.py
```

**Try it:** File → Open Survey File, or load the demo cave. Sample surveys are in `data/sample_caves/`.

## Stack

Python · PyQt6 · pyqtgraph / OpenGL · NumPy · Anthropic (optional)

## Layout

```
├── main.py              # App entry
├── requirements.txt
├── src/
│   ├── ai/              # Cave assistant, SAR planner, incident scanner
│   ├── database/        # Cave + incident stores
│   ├── engine/          # Parsers, cave model, renderers, SAR PDF
│   └── ui/              # Desktop UI
├── data/
│   └── sample_caves/    # Demo .dat / .svx
└── assets/              # Icons
```

## Notes

- Survey data is for simulation and planning only.
- This public release is the cave diving / SAR edition.
- Do not commit `.env`, API keys, or real incident databases.

## License

MIT (or your preferred license)

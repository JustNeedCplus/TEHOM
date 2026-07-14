# TEHOM — Software Bill of Materials (SBOM)

Classification: UNCLASSIFIED
Generated: 2026-07-14
Version: 0.1.0-public

## Runtime Dependencies

| Package | Min Version | License | Purpose | Network Access |
|---------|------------|---------|---------|----------------|
| PyQt6 | 6.6.0 | GPL v3 / Commercial | GUI framework | No |
| pyqtgraph | 0.13.0 | MIT | 3D OpenGL rendering | No |
| PyOpenGL | 3.1.0 | BSD | OpenGL bindings | No |
| numpy | 1.26.0 | BSD | Numerical computation | No |
| anthropic | 0.26.0 | MIT | AI cave assistant | Yes (optional) |
| requests | 2.31.0 | Apache 2.0 | HTTP client for AI API | Yes (optional) |
| python-dotenv | 1.0.0 | BSD | Environment variable loading | No |

## Optional Dependencies

| Package | Purpose | Required For |
|---------|---------|-------------|
| Pillow | Icon generation | App icon build only |

## Network Behaviour

- May contact Anthropic API (`api.anthropic.com`) for AI cave lookup when an API key is configured
- No telemetry, no analytics, no phone-home

## Build Environment

- Python: 3.10+
- Platform: macOS (Darwin), Linux (tested), Windows (untested)
- No native compiled extensions beyond PyQt6/numpy wheels

#!/bin/bash
# TEHOM — macOS App Bundle Builder
# Creates TEHOM.app and installs it to /Applications
# Run:  bash build_app.sh
# Re-run any time you want to refresh the icon or launcher.
# Source code edits in ~/TEHOM take effect immediately — no rebuild needed.

set -e

TEHOM_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="TEHOM"
APP_BUNDLE="$TEHOM_DIR/$APP_NAME.app"
APPLICATIONS="/Applications/$APP_NAME.app"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  TEHOM — Build macOS App"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Source: $TEHOM_DIR"

# ── 1. Generate icon if not already present ───────────────────────────────────
if [ ! -f "$TEHOM_DIR/assets/TEHOM.icns" ]; then
    echo "→ Generating app icon..."
    cd "$TEHOM_DIR"
    source .venv/bin/activate
    python generate_icon.py
    deactivate
fi

# ── 2. Create .app bundle structure ──────────────────────────────────────────
echo "→ Building $APP_NAME.app..."
rm -rf "$APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# ── 3. Info.plist ─────────────────────────────────────────────────────────────
cat > "$APP_BUNDLE/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>TEHOM</string>
    <key>CFBundleDisplayName</key>
    <string>TEHOM</string>
    <key>CFBundleIdentifier</key>
    <string>com.tehom.cavemapper</string>
    <key>CFBundleVersion</key>
    <string>0.1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>0.1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>THOM</string>
    <key>CFBundleExecutable</key>
    <string>TEHOM</string>
    <key>CFBundleIconFile</key>
    <string>TEHOM</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSSupportsAutomaticGraphicsSwitching</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHumanReadableCopyright</key>
    <string>TEHOM — Underwater Cave Mapping and SAR System</string>
    <key>CFBundleDocumentTypes</key>
    <array>
        <dict>
            <key>CFBundleTypeName</key>
            <string>Compass Survey File</string>
            <key>CFBundleTypeExtensions</key>
            <array><string>dat</string></array>
            <key>CFBundleTypeRole</key>
            <string>Viewer</string>
        </dict>
        <dict>
            <key>CFBundleTypeName</key>
            <string>Survex Survey File</string>
            <key>CFBundleTypeExtensions</key>
            <array><string>svx</string></array>
            <key>CFBundleTypeRole</key>
            <string>Viewer</string>
        </dict>
    </array>
    <key>NSRequiresAquaSystemAppearance</key>
    <false/>
</dict>
</plist>
PLIST

# ── 4. Launcher script ────────────────────────────────────────────────────────
LAUNCHER="$APP_BUNDLE/Contents/MacOS/$APP_NAME"
cat > "$LAUNCHER" << LAUNCHER
#!/bin/bash
# TEHOM launcher — activates the project venv and runs main.py
# Edits to source in TEHOM_DIR take effect immediately without rebuilding.

TEHOM_DIR="$TEHOM_DIR"
LOG="\$HOME/Library/Logs/TEHOM.log"

cd "\$TEHOM_DIR" || exit 1
source .venv/bin/activate

# macOS OpenGL backend
export QSG_RHI_BACKEND=opengl

exec python main.py 2>"\$LOG"
LAUNCHER
chmod +x "$LAUNCHER"

# ── 5. Copy icon ──────────────────────────────────────────────────────────────
cp "$TEHOM_DIR/assets/TEHOM.icns" "$APP_BUNDLE/Contents/Resources/TEHOM.icns"

# ── 6. Install to /Applications ───────────────────────────────────────────────
echo "→ Installing to /Applications..."
rm -rf "$APPLICATIONS"
cp -r "$APP_BUNDLE" "$APPLICATIONS"

# Touch so macOS registers the new app immediately
touch "$APPLICATIONS"

# ── 7. Register with Launch Services (makes icon appear in dock on next open) ─
/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister \
    -f "$APPLICATIONS" 2>/dev/null || true

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  TEHOM.app installed successfully."
echo ""
echo "  Launch: open /Applications/TEHOM.app"
echo "       or: Spotlight → TEHOM"
echo "       or: Finder → Applications → TEHOM"
echo ""
echo "  To update the software:"
echo "    1. Edit source files in: $TEHOM_DIR"
echo "    2. No rebuild needed — changes are live immediately."
echo "    3. If you add new dependencies:"
echo "         cd $TEHOM_DIR && source .venv/bin/activate"
echo "         pip install <package>"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

#!/usr/bin/env python3

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def check_dependencies() -> list[str]:
    missing = []
    for pkg, import_name in [
        ("PyQt6", "PyQt6"),
        ("numpy", "numpy"),
        ("anthropic", "anthropic"),
    ]:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)
    return missing


def main():
    missing = check_dependencies()
    if missing:
        print(f"\n❌ Missing required packages: {', '.join(missing)}")
        print(f"\n  pip install {' '.join(missing)}")
        sys.exit(1)

    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtCore import QTimer

    import os
    os.environ["QSG_RHI_BACKEND"] = "opengl"
    from PyQt6.QtCore import Qt as _Qt
    from PyQt6.QtWidgets import QApplication as _QApp
    _QApp.setAttribute(_Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("TEHOM")
    app.setOrganizationName("TEHOM")
    app.setApplicationVersion("0.1.0")

    from src.ui.main_window import MainWindow
    window = MainWindow()
    window.show()
    window.raise_()
    window.activateWindow()

    from src.ui.settings import AppSettings
    _settings = AppSettings()
    api_key = os.getenv("ANTHROPIC_API_KEY", "") or _settings.get_api_key() or ""
    if not api_key:
        def show_welcome():
            QMessageBox.information(
                window,
                "Welcome to TEHOM",
                "Welcome!\n\n"
                "To enable full AI cave lookup:\n"
                "  Settings → Set Anthropic API Key\n\n"
                "To get started right now:\n"
                "• Click 'Load Demo Cave' to see a 3D cave\n"
                "• Search: 'Ginnie Springs', 'Tham Luang', 'Dos Ojos'\n\n"
                "⚠️  Survey data is for simulation/planning only.",
            )
        QTimer.singleShot(500, show_welcome)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

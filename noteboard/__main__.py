"""Entry point for the noteboard popup.

QT_WAYLAND_SHELL_INTEGRATION has to be set before Qt opens the Wayland
connection, so it happens here rather than in a wrapper script.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell")

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

QML_DIR = Path(__file__).parent / "qml"


def main() -> int:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("noteboard")
    app.setDesktopFileName("io.github.ekats.noteboard")

    engine = QQmlApplicationEngine()
    engine.load(QML_DIR / "Popup.qml")
    if not engine.rootObjects():
        return 1

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

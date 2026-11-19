"""Entry point for the noteboard popup daemon.

QT_WAYLAND_SHELL_INTEGRATION has to be set before Qt opens the Wayland
connection, so it happens here rather than in a wrapper script. Note that it
applies to every window in the process, which is why the notes board will be
a separate process -- see the README.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell")

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

from noteboard.service import PopupService  # noqa: E402

QML_DIR = Path(__file__).parent / "qml"

# Offset from the pointer, so the popup sits next to the cursor rather than
# directly under it.
POINTER_GAP = 12


def main() -> int:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("noteboard")
    app.setDesktopFileName("io.github.ekats.noteboard")

    engine = QQmlApplicationEngine()
    engine.load(QML_DIR / "Popup.qml")
    roots = engine.rootObjects()
    if not roots:
        return 1
    window = roots[0]

    def place(x: int, y: int, screen_name: str) -> None:
        """Show the popup near (x, y) on the named output.

        x and y arrive output-relative from the KWin script. Clamping keeps
        the popup fully on that output when the pointer is near an edge.
        """
        screen = next((s for s in app.screens() if s.name() == screen_name), None)
        if screen is not None:
            # A layer surface is bound to an output when it is created, so a
            # live surface cannot be moved between outputs -- it has to be
            # destroyed and recreated. QWindow.screen() is no help in
            # deciding when: it does not track the output the layer surface
            # actually went to, and reports the primary screen regardless.
            # Since the popup is hidden between shows, just recreate every
            # time. setVisible(False) would not do it either, as Qt collapses
            # a hide/show pair in one event loop pass.
            window.destroy()
            window.setScreen(screen)
            window.setProperty("targetScreen", screen)
            bounds = screen.geometry()
            x = min(x + POINTER_GAP, bounds.width() - window.width())
            y = min(y + POINTER_GAP, bounds.height() - window.height())
        window.setProperty("originX", max(0, x))
        window.setProperty("originY", max(0, y))
        window.setVisible(True)
        window.requestActivate()

    service = PopupService()
    service.showRequested.connect(place)
    if not service.register():
        print("noteboard: could not take the D-Bus name, is it already running?",
              file=sys.stderr)
        return 1

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

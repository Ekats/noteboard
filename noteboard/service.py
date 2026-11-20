"""D-Bus service the KWin script calls into.

The script passes output-relative pointer coordinates, the output name and
the active window class;
see noteboard/kwin/noteboard.js for why that split exists.
"""

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtDBus import QDBusConnection

SERVICE_NAME = "io.github.ekats.noteboard"
OBJECT_PATH = "/Popup"


class PopupService(QObject):
    # x, y are relative to the named output; the last field is the resource
    # class of the window that was active when the shortcut fired.
    showRequested = Signal(int, int, str, str)

    @Slot(int, int, str, str)
    def showAt(self, x: int, y: int, screen_name: str, window_class: str) -> None:
        self.showRequested.emit(x, y, screen_name, window_class)

    def register(self) -> bool:
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return False
        if not bus.registerService(SERVICE_NAME):
            # Already taken, so another daemon owns the popup.
            return False
        return bus.registerObject(
            OBJECT_PATH, self, QDBusConnection.RegisterOption.ExportAllSlots
        )

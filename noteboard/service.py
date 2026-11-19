"""D-Bus service the KWin script calls into.

The script passes output-relative pointer coordinates plus the output name;
see noteboard/kwin/noteboard.js for why that split exists.
"""

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtDBus import QDBusConnection

SERVICE_NAME = "io.github.ekats.noteboard"
OBJECT_PATH = "/Popup"


class PopupService(QObject):
    # x, y are relative to the named output.
    showRequested = Signal(int, int, str)

    @Slot(int, int, str)
    def showAt(self, x: int, y: int, screen_name: str) -> None:
        self.showRequested.emit(x, y, screen_name)

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

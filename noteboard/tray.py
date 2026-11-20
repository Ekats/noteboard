"""Tray icon that opens the popup at the pointer.

The daemon cannot read the pointer, so a click asks KWin to run the same
shortcut action the keyboard does, via kglobalaccel. The item itself is a
hand-rolled StatusNotifierItem (see sni.py), so no Qt window exists for it.
"""

from PySide6.QtCore import QObject
from PySide6.QtDBus import QDBusConnection, QDBusMessage

from noteboard.sni import StatusNotifierItem

# KWin shortcut action names registered in kwin/noteboard.js.
ACTION_CAPTURE = "NoteboardShowPopup"
ACTION_NOTES = "NoteboardShowNotes"


class Tray(QObject):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        self._item = StatusNotifierItem("NoteBoard", self)
        self._item.activated.connect(lambda: self._open(0, ACTION_CAPTURE))
        self._item.contextRequested.connect(lambda: self._open(1, ACTION_NOTES))
        self._item.start()

    def _open(self, page: int, action: str) -> None:
        # A click while the popup is open toggles it closed on the same tab
        # and switches tab otherwise, so the other click never feels dead.
        if self._window.isVisible():
            if self._window.property("page") == page:
                self._window.setVisible(False)
            else:
                self._window.setProperty("page", page)
            return
        message = QDBusMessage.createMethodCall(
            "org.kde.kglobalaccel", "/component/kwin",
            "org.kde.kglobalaccel.Component", "invokeShortcut")
        message.setArguments([action])
        QDBusConnection.sessionBus().asyncCall(message)

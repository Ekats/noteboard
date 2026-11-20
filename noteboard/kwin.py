"""Loads the KWin script that owns the global shortcut.

Without this the script only exists in KWin until the next restart or login,
so the daemon installs it itself and again whenever KWin reappears.
"""

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtDBus import (QDBusConnection, QDBusInterface, QDBusMessage,
                            QDBusServiceWatcher)

KWIN_SERVICE = "org.kde.KWin"
SCRIPT_NAME = "noteboard"
SCRIPT_PATH = Path(__file__).parent / "kwin" / "noteboard.js"

RETRY_FIRST_MS = 500
RETRY_GIVE_UP_MS = 10_000


class KWinScript(QObject):
    loaded = Signal()  # the script is running, its shortcuts registering

    def __init__(self, parent=None):
        super().__init__(parent)
        bus = QDBusConnection.sessionBus()
        # Parented to self so the watcher lives as long as this object.
        self._watcher = QDBusServiceWatcher(
            KWIN_SERVICE, bus,
            QDBusServiceWatcher.WatchModeFlag.WatchForRegistration, self)
        self._watcher.serviceRegistered.connect(lambda _name: self.ensure())
        # One timer, so a second registration restarts the pending retry
        # instead of stacking another.
        self._retry = QTimer(self, singleShot=True)
        self._retry.timeout.connect(self._attempt)
        self._delay_ms = RETRY_FIRST_MS
        self._waited_ms = 0

    def ensure(self) -> None:
        self._retry.stop()
        self._delay_ms = RETRY_FIRST_MS
        self._waited_ms = 0
        self._attempt()

    def _attempt(self) -> None:
        bus = QDBusConnection.sessionBus()
        if not bus.interface().isServiceRegistered(KWIN_SERVICE).value():
            print("noteboard: KWin is not on the bus, the shortcut script "
                  "was not loaded", file=sys.stderr)
            return
        error = self._load(bus)
        if error is None:
            self.loaded.emit()
            return
        # KWin takes its bus name before /Scripting is exported, so right
        # after a restart the first calls can fail.
        if self._waited_ms >= RETRY_GIVE_UP_MS:
            print(f"noteboard: could not load the KWin script: {error}",
                  file=sys.stderr)
            return
        delay = min(self._delay_ms, RETRY_GIVE_UP_MS - self._waited_ms)
        self._waited_ms += delay
        self._retry.start(delay)
        self._delay_ms *= 2

    def _load(self, bus: QDBusConnection) -> str | None:
        """Returns None on success, else a description of the D-Bus error."""
        scripting = QDBusInterface(KWIN_SERVICE, "/Scripting",
                                   "org.kde.kwin.Scripting", bus)

        def call(method: str, *args) -> tuple[QDBusMessage, str | None]:
            reply = scripting.call(method, *args)
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                return reply, f"{method}: {reply.errorName()}: {reply.errorMessage()}"
            return reply, None

        reply, error = call("isScriptLoaded", SCRIPT_NAME)
        if error:
            return error
        # A copy left from an older path or version would keep its old
        # shortcut handler, and loadScript refuses a name that is taken.
        if reply.arguments()[0]:
            _, error = call("unloadScript", SCRIPT_NAME)
            if error:
                return error
        reply, error = call("loadScript", str(SCRIPT_PATH), SCRIPT_NAME)
        if error:
            return error
        if reply.arguments()[0] < 0:
            return "loadScript: KWin rejected the script"
        # loadScript only registers the script; start runs everything that
        # is loaded but not yet running.
        _, error = call("start")
        return error

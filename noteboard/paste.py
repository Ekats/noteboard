"""Pasting into the previously focused app.

A Wayland client cannot synthesise key events for another client, so the
keystroke goes through the xdg-desktop-portal RemoteDesktop interface. It
needs a one-off user permission, which is remembered through a restore token.
The whole thing is opt-in ("Paste automatically" in Settings): switched off,
no portal session is created and a click only copies.

The portal calls use Gio rather than QtDBus: its options are a{sv} dicts
that must carry D-Bus uint values, and PySide6 cannot marshal one (Python
ints go out as int32). Qt's event dispatcher on Linux is the GLib one, so
GDBus callbacks fire on the Qt main thread with no extra loop or thread.
"""

import sys

from PySide6.QtCore import Property, QObject, QSettings, QTimer, Signal, Slot

from noteboard.clipboard import WaylandClipboard

try:
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
except (ImportError, ValueError):
    Gio = GLib = None

APP_ID = "io.github.ekats.noteboard"
PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
REGISTRY = "org.freedesktop.host.portal.Registry"
REMOTE_DESKTOP = "org.freedesktop.portal.RemoteDesktop"
REQUEST = "org.freedesktop.portal.Request"
SESSION = "org.freedesktop.portal.Session"

DEVICE_KEYBOARD = 1
PERSIST_UNTIL_REVOKED = 2
TOKEN_KEY = "portal/restoreToken"
# The app id the token was granted to. A token from before NoteBoard
# identified itself belongs to the empty id, and KDE asks again by name.
TOKEN_APP_KEY = "portal/restoreTokenApp"
AUTO_PASTE_KEY = "autoPaste"

KEY_CONTROL_L = 0xffe3
KEY_SHIFT_L = 0xffe1
KEY_V = 0x76

# Terminals take Ctrl+Shift+V, since plain Ctrl+V is a control character to
# them. Lower-cased resourceClass values, as KWin reports them.
TERMINAL_CLASSES = {
    "konsole", "org.kde.konsole", "yakuake", "org.kde.yakuake", "kitty",
    "alacritty", "foot", "org.wezfurlong.wezterm", "wezterm",
    "com.mitchellh.ghostty", "gnome-terminal-server", "org.gnome.ptyxis",
    "xterm", "tilix", "terminator",
}

# Pause between our selection landing and the keystroke, for KWin to hand
# keyboard focus back once the popup's exclusive grab is released.
SETTLE_MS = 100
# Send anyway if the watcher never echoes our copy back.
ECHO_TIMEOUT_MS = 1000


def has_grant(settings: QSettings) -> bool:
    """Whether a permission was granted to NoteBoard under its own name."""
    return bool(settings.value(TOKEN_KEY, "")) \
        and settings.value(TOKEN_APP_KEY, "") == APP_ID


def migrate_auto_paste(settings: QSettings) -> bool:
    """Reads "Paste automatically", deciding it once when the key is absent:
    on for someone who already granted the permission, off for a fresh
    install so that nothing asks before the user has chosen."""
    if not settings.contains(AUTO_PASTE_KEY):
        settings.setValue(AUTO_PASTE_KEY, bool(settings.value(TOKEN_KEY, "")))
    return str(settings.value(AUTO_PASTE_KEY)).lower() == "true"


def combo_for(window_class: str) -> list[int]:
    if window_class.lower() in TERMINAL_CLASSES:
        return [KEY_CONTROL_L, KEY_SHIFT_L, KEY_V]
    return [KEY_CONTROL_L, KEY_V]


class PortalKeyboard(QObject):
    # "off" (no session), "waiting" (permission pending), "allowed",
    # "denied", "unavailable" (no portal to ask).
    stateChanged = Signal()

    def __init__(self, parent=None, settings: QSettings | None = None):
        super().__init__(parent)
        self._settings = settings if settings is not None else QSettings()
        self._conn = None
        self._state = "off"
        self._gen = 0  # bumped by stop(), so late replies are ignored
        self._session: str | None = None
        self._serial = 0
        self._starting = False
        self._closed = False  # the session ended after having worked
        self._failed = False

    @property
    def ready(self) -> bool:
        return self._session is not None and not self._starting

    @property
    def state(self) -> str:
        return self._state

    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.stateChanged.emit()

    def stop(self) -> None:
        """Ends the session, if any, and forgets any request in flight."""
        self._gen += 1
        if self._conn is not None and self._session is not None:
            self._conn.call(
                PORTAL, self._session, SESSION, "Close", None, None,
                Gio.DBusCallFlags.NONE, -1, None, None)
        self._session = None
        self._starting = False
        self._closed = False
        self._failed = False
        self._set_state("off")

    def start(self) -> None:
        """Creates the session. Done at startup (or when the setting is
        switched on) so that the permission dialog never appears in the
        middle of a paste."""
        if Gio is None:
            self._fail("python-gobject is not installed", "unavailable")
            return
        if self._starting or self.ready:
            return
        self._failed = False
        self._starting = True
        self._set_state("waiting")
        try:
            self._connect()
        except GLib.Error as e:
            self._fail(e.message, "unavailable")
            return
        self._request("CreateSession", None, {
            "session_handle_token": GLib.Variant("s", self._token("session")),
        }, self._on_created)

    def _connect(self) -> None:
        if self._conn is not None:
            return
        # Not the shared Gio.bus_get_sync() connection: the portal ties the
        # app id to the connection, and Register must be the first thing
        # said on it.
        conn = Gio.DBusConnection.new_for_address_sync(
            Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None),
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
            | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
        try:
            conn.call_sync(PORTAL, PORTAL_PATH, REGISTRY, "Register",
                           GLib.Variant("(sa{sv})", (APP_ID, {})), None,
                           Gio.DBusCallFlags.NONE, -1, None)
        except GLib.Error as e:
            # Still works, but KDE then asks for an "unidentifiable application".
            print(f"noteboard: could not register with the portal ({e.message})",
                  file=sys.stderr)
        self._conn = conn

    def send_combo(self, keysyms: list[int]) -> bool:
        """Presses the keys in order and releases them in reverse."""
        if self._closed:
            # Retry once per Closed signal, not in a loop. This paste still
            # falls back to copy-only; a permission dialog may open now.
            self._closed = False
            self.start()
        if not self.ready:
            return False
        events = [(k, 1) for k in keysyms] + [(k, 0) for k in reversed(keysyms)]
        for keysym, state in events:
            self._conn.call(
                PORTAL, PORTAL_PATH, REMOTE_DESKTOP, "NotifyKeyboardKeysym",
                GLib.Variant("(oa{sv}iu)", (self._session, {}, keysym, state)),
                None, Gio.DBusCallFlags.NONE, -1, None, self._on_notified)
        return True

    def _token(self, kind: str) -> str:
        self._serial += 1
        return f"noteboard_{kind}{self._serial}"

    def _fail(self, why: str, state: str = "denied") -> None:
        self._starting = False
        self._set_state(state)
        if not self._failed:  # one line per failure, not per retry
            print(f"noteboard: paste is off, copy only ({why})", file=sys.stderr)
        self._failed = True

    def _request(self, method, session, options, on_ok) -> None:
        """Calls a portal method that answers through Request::Response.

        The Response is subscribed to before the call, on the path the
        portal is documented to use, so it cannot be missed.
        """
        token = self._token("req")
        sender = self._conn.get_unique_name()[1:].replace(".", "_")
        path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
        options = {"handle_token": GLib.Variant("s", token), **options}
        sub = None
        gen = self._gen

        def on_response(_c, _s, _p, _i, _n, params):
            self._conn.signal_unsubscribe(sub)
            if gen != self._gen:
                return
            code, results = params.unpack()
            if code != 0:
                self._fail("permission denied" if code == 1 else f"{method} failed")
                return
            on_ok(results)

        sub = self._conn.signal_subscribe(
            PORTAL, REQUEST, "Response", path, None,
            Gio.DBusSignalFlags.NONE, on_response)

        def on_reply(conn, res):
            try:
                conn.call_finish(res)
            except GLib.Error as e:
                conn.signal_unsubscribe(sub)
                if gen == self._gen:
                    self._fail(f"{method}: {e.message}", "unavailable")

        if session is None:
            args = GLib.Variant("(a{sv})", (options,))
        elif method == "Start":
            args = GLib.Variant("(osa{sv})", (session, "", options))
        else:
            args = GLib.Variant("(oa{sv})", (session, options))
        self._conn.call(PORTAL, PORTAL_PATH, REMOTE_DESKTOP, method, args,
                        None, Gio.DBusCallFlags.NONE, -1, None, on_reply)

    def _on_created(self, results) -> None:
        session = results["session_handle"]
        options = {
            "types": GLib.Variant("u", DEVICE_KEYBOARD),
            "persist_mode": GLib.Variant("u", PERSIST_UNTIL_REVOKED),
        }
        token = self._settings.value(TOKEN_KEY, "")
        if token:
            options["restore_token"] = GLib.Variant("s", token)
        self._conn.signal_subscribe(
            PORTAL, SESSION, "Closed", session, None,
            Gio.DBusSignalFlags.NONE, self._on_closed)
        self._request("SelectDevices", session, options,
                      lambda _r: self._request("Start", session, {},
                                               lambda r: self._on_started(session, r)))

    def _on_started(self, session, results) -> None:
        # The token changes on every start, so the newest one is kept.
        if results.get("restore_token"):
            self._settings.setValue(TOKEN_KEY, results["restore_token"])
            self._settings.setValue(TOKEN_APP_KEY, APP_ID)
        if not results.get("devices", 0) & DEVICE_KEYBOARD:
            self._fail("keyboard access was not granted")
            return
        self._session = session
        self._starting = False
        self._set_state("allowed")

    def _on_closed(self, *_args) -> None:
        if self._session is None:  # we closed it ourselves in stop()
            return
        self._session = None
        self._closed = True
        self._set_state("denied")

    @staticmethod
    def _on_notified(conn, res) -> None:
        try:
            conn.call_finish(res)
        except GLib.Error as e:
            print(f"noteboard: key event failed: {e.message}", file=sys.stderr)


class Paster(QObject):
    """Copies an entry and, when "Paste automatically" is on, types the paste
    shortcut into the app the popup was opened from.

    The portal session exists only while the setting is on. Switching it on
    asks right away (KDE's dialog is the consent). Whenever the permission is
    refused or lost the setting switches itself off, so what the switch shows
    is what happens."""

    autoPasteChanged = Signal()
    statusChanged = Signal()

    def __init__(self, clipboard: WaylandClipboard, keyboard: PortalKeyboard,
                 parent=None, settings: QSettings | None = None):
        super().__init__(parent)
        self._clipboard = clipboard
        self._keyboard = keyboard
        self._settings = settings if settings is not None else QSettings()
        self._auto = migrate_auto_paste(self._settings)
        self._note = ""  # why the setting was switched off, for the status line
        self._window_class = ""
        self._pending: str | None = None
        self._timeout = QTimer(self, singleShot=True, interval=ECHO_TIMEOUT_MS)
        self._timeout.timeout.connect(self._send)
        clipboard.changed.connect(self._on_clipboard)
        keyboard.stateChanged.connect(self._on_state)

    def begin(self) -> None:
        """At startup: resumes silently under an existing grant. Without one
        the setting is switched off rather than asking, so no dialog appears
        at login; switching it on again asks."""
        if not self._auto:
            return
        if has_grant(self._settings):
            self._keyboard.start()
        else:
            self._switch_off("")

    def _get_auto(self) -> bool:
        return self._auto

    def _get_status(self) -> str:
        """off, waiting, allowed, declined or unavailable. The last two are
        only seen with the setting off, as the reason it was switched off."""
        return self._keyboard.state if self._auto else (self._note or "off")

    autoPaste = Property(bool, _get_auto, notify=autoPasteChanged)
    status = Property(str, _get_status, notify=statusChanged)

    def _on_state(self) -> None:
        if self._auto and self._keyboard.state in ("denied", "unavailable"):
            self._switch_off("unavailable" if self._keyboard.state == "unavailable"
                             else "declined")
        else:
            self.statusChanged.emit()

    def _switch_off(self, note: str) -> None:
        self._auto = False
        self._note = note
        self._settings.setValue(AUTO_PASTE_KEY, False)
        self._pending = None
        self._timeout.stop()
        self._keyboard.stop()
        self.autoPasteChanged.emit()
        self.statusChanged.emit()

    @Slot(bool)
    def setAutoPaste(self, on: bool) -> None:
        if on == self._auto:
            return
        if not on:
            self._switch_off("")
            return
        self._auto = True
        self._note = ""
        self._settings.setValue(AUTO_PASTE_KEY, True)
        self._keyboard.start()
        self.autoPasteChanged.emit()
        self.statusChanged.emit()

    def set_target(self, window_class: str) -> None:
        self._window_class = window_class

    @Slot(str)
    def paste(self, text: str) -> None:
        self._clipboard.copy(text)
        if not self._auto:
            return
        self._pending = text
        self._timeout.start()

    def _on_clipboard(self, text: str) -> None:
        # Our own copy coming back means the selection is ours and the store
        # has already bumped the entry (the model's slot is connected first).
        if self._pending is not None and text == self._pending:
            self._timeout.stop()
            QTimer.singleShot(SETTLE_MS, self._send)

    def _send(self) -> None:
        if self._pending is None:
            return
        self._pending = None
        self._keyboard.send_combo(combo_for(self._window_class))

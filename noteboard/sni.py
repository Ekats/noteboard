"""StatusNotifierItem exported by hand, for the tray icon.

QSystemTrayIcon cannot be used: with no context menu set, Qt swallows the
SNI ContextMenu call (no `activated` signal) and creates a window for it,
which would become a layer surface here. Doing the protocol directly gives
a distinct right click and creates no window.

Uses Gio rather than QtDBus for the same reason as paste.py: Qt's GLib event
dispatcher runs GDBus callbacks on the main thread with no extra loop.
"""

import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

try:
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
except (ImportError, ValueError):
    Gio = GLib = None

WATCHER = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
ITEM_PATH = "/StatusNotifierItem"
ITEM_IFACE = "org.kde.StatusNotifierItem"

ICON_NAME = "noteboard"
ICON_DIR = str(Path(__file__).parent)  # holds noteboard.png

INTROSPECTION = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="u" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <property name="OverlayIconName" type="s" access="read"/>
    <property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
    <property name="AttentionIconName" type="s" access="read"/>
    <property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
    <property name="AttentionMovieName" type="s" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
    <signal name="NewIcon"/>
    <signal name="NewStatus"><arg type="s"/></signal>
  </interface>
</node>
"""


def _pixmaps() -> list:
    """The icon as one ARGB32, network byte order, SNI pixmap."""
    image = QImage(str(Path(ICON_DIR) / "noteboard.png"))
    if image.isNull():
        return []
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    rgba = bytes(image.constBits())
    argb = bytearray(len(rgba))
    argb[0::4], argb[1::4], argb[2::4], argb[3::4] = (
        rgba[3::4], rgba[0::4], rgba[1::4], rgba[2::4])
    return [(image.width(), image.height(), bytes(argb))]


class StatusNotifierItem(QObject):
    activated = Signal()      # left click
    contextRequested = Signal()  # right click

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title
        self._conn = None
        self._name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self._props = {}

    def start(self) -> None:
        if Gio is None:
            print("noteboard: no tray icon (python-gobject is not installed)",
                  file=sys.stderr)
            return
        try:
            self._conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error as e:
            print(f"noteboard: no tray icon ({e.message})", file=sys.stderr)
            return
        self._props = {
            "Category": GLib.Variant("s", "ApplicationStatus"),
            "Id": GLib.Variant("s", "noteboard"),
            "Title": GLib.Variant("s", self._title),
            "Status": GLib.Variant("s", "Active"),
            "WindowId": GLib.Variant("u", 0),
            "IconName": GLib.Variant("s", ICON_NAME),
            "IconThemePath": GLib.Variant("s", ICON_DIR),
            "IconPixmap": GLib.Variant("a(iiay)", _pixmaps()),
            "OverlayIconName": GLib.Variant("s", ""),
            "OverlayIconPixmap": GLib.Variant("a(iiay)", []),
            "AttentionIconName": GLib.Variant("s", ""),
            "AttentionIconPixmap": GLib.Variant("a(iiay)", []),
            "AttentionMovieName": GLib.Variant("s", ""),
            "ToolTip": GLib.Variant("(sa(iiay)ss)",
                                    (ICON_NAME, [], self._title, "")),
            "ItemIsMenu": GLib.Variant("b", False),
        }
        node = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION)
        self._conn.register_object(
            ITEM_PATH, node.interfaces[0], self._on_call, self._on_get, None)
        # Held by the bus for the life of the process.
        Gio.bus_own_name_on_connection(
            self._conn, self._name, Gio.BusNameOwnerFlags.NONE, None, None)
        # Registers now if the watcher is there, and again whenever it comes
        # back (a Plasma restart forgets every item).
        Gio.bus_watch_name_on_connection(
            self._conn, WATCHER, Gio.BusNameWatcherFlags.NONE,
            lambda *_: self._register(), None)

    def _register(self) -> None:
        self._conn.call(
            WATCHER, WATCHER_PATH, WATCHER, "RegisterStatusNotifierItem",
            GLib.Variant("(s)", (self._name,)), None,
            Gio.DBusCallFlags.NONE, -1, None, self._on_registered)

    @staticmethod
    def _on_registered(conn, res) -> None:
        try:
            conn.call_finish(res)
        except GLib.Error as e:
            print(f"noteboard: tray registration failed: {e.message}",
                  file=sys.stderr)

    def _on_get(self, _conn, _sender, _path, _iface, name):
        return self._props.get(name)

    def _on_call(self, _conn, _sender, _path, _iface, method, _params, invocation):
        if method == "Activate":
            self.activated.emit()
        elif method == "ContextMenu":
            self.contextRequested.emit()
        # SecondaryActivate (middle click) and Scroll are ignored.
        invocation.return_value(None)

"""One-time claim of Meta+V from Plasma's clipboard popup.

kglobalaccel keeps an action's saved key over a new default and refuses a key
another action holds, so changing the default in noteboard.js does nothing on
a machine where Meta+V already belongs to Klipper's "Show Clipboard Items at
Mouse Position". The first start therefore moves the key over, once. A flag in
the settings file stops it from ever running again, so a later rebind in
System Settings > Shortcuts wins.

Gio rather than QtDBus, as in paste.py: the key lists are a(ai) values and
the method signatures are exact. The calls are synchronous with a timeout,
since this runs once at startup.
"""

import sys

from PySide6.QtCore import QObject, QSettings

try:
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
except (ImportError, ValueError):
    Gio = GLib = None

SERVICE = "org.kde.kglobalaccel"
PATH = "/kglobalaccel"
IFACE = "org.kde.KGlobalAccel"

FLAG_KEY = "shortcuts/claimedMetaV"
TIMEOUT_MS = 2000

# Qt::MetaModifier | Qt::Key_V, a QKeyCombination as an int.
META_V = 0x10000000 | 0x56

# actionId order: component, action, component friendly, action friendly.
OURS = ["kwin", "NoteboardShowPopup", "KWin", "NoteBoard: show popup at pointer"]
KLIPPER = ("plasmashell", "show-on-mouse-pos")


class ShortcutClaim(QObject):
    def claim(self) -> None:
        settings = QSettings()
        if settings.value(FLAG_KEY, False, type=bool):
            return
        if Gio is None:
            print("noteboard: Meta+V not claimed (python-gobject is not "
                  "installed)", file=sys.stderr)
            return
        try:
            self._claim()
        except GLib.Error as e:
            print(f"noteboard: Meta+V not claimed, will retry next start "
                  f"({e.message})", file=sys.stderr)
            return
        settings.setValue(FLAG_KEY, True)
        settings.sync()

    def _set_keys(self, action_id: list[str], keys: list[int]) -> None:
        self._conn.call_sync(
            SERVICE, PATH, IFACE, "setForeignShortcutKeys",
            GLib.Variant("(asa(ai))", (action_id, [(keys,)] if keys else [])),
            None, Gio.DBusCallFlags.NONE, TIMEOUT_MS, None)

    def _claim(self) -> None:
        self._conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        # Rows: action, action friendly, component, component friendly,
        # context, context friendly, keys, default keys.
        rows = self._conn.call_sync(
            SERVICE, PATH, IFACE, "getGlobalShortcutsByKey",
            GLib.Variant("(i)", (META_V,)), GLib.VariantType("(a(ssssssaiai))"),
            Gio.DBusCallFlags.NONE, TIMEOUT_MS, None).unpack()[0]
        owners = [r for r in rows if META_V in r[6]]
        if owners:
            action, action_friendly, comp, comp_friendly = owners[0][:4]
            if (comp, action) == (OURS[0], OURS[1]):
                return
            if len(owners) > 1 or (comp, action) != KLIPPER:
                print(f"noteboard: Meta+V belongs to {comp}/{action}, "
                      "leaving it alone", file=sys.stderr)
                return
            self._set_keys([comp, action, comp_friendly, action_friendly], [])
        self._set_keys(OURS, [META_V])
        print("noteboard: took Meta+V from Plasma's clipboard popup",
              file=sys.stderr)

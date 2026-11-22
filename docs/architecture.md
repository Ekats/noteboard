# Architecture

NoteBoard is split into a resident popup daemon, a notes board that launches
on demand, and the SQLite store they share. Only the daemon exists so far;
the board is not started (see the Status table in the README).

- **Popup daemon** (`python3 -m noteboard`): the layer-shell popup, clipboard
  monitoring, the tray icon, the KWin script loader and Memos sync. It owns
  the D-Bus name `io.github.ekats.noteboard`.
- **Board**: an ordinary toplevel window, launched on demand.
- **Store**: one SQLite database (`noteboard.db`, WAL mode) that both read
  and write. See [development.md](development.md) for where it lives.

## Why layer-shell

The popup is a `wlr-layer-shell` surface rather than an ordinary window.
That matters because xdg-shell gives a client no way to place its own
window or take a keyboard grab, so a popup built on it cannot appear where
you want it or take the keyboard. Layer-shell can do both: the popup anchors
to the top-left corner and uses its margins as absolute coordinates, and it
requests exclusive keyboard interactivity.

The popup does not depend on focus to go away. It closes on **Esc**, on its
close button, and on a tray click on the tab that is showing. If
**Close 1 s after the mouse leaves** is switched on in Settings (off by
default), it also closes one second after the pointer leaves the panel;
coming back within that second cancels the close. Because the keyboard grab
is exclusive, Esc is the only way out from the keyboard.

## Pasting

A Wayland client cannot press keys in another client, so **Paste
automatically** (Settings, opt-in) sends Ctrl+V through the
xdg-desktop-portal RemoteDesktop interface (`noteboard/paste.py`). The portal
session is created only while the setting is on. Switching it on makes the
request at once; a decline, failure or later revocation switches the setting
off again, and so does a startup with no permission recorded for NoteBoard's
own app id (no dialog at login). Off, a click just copies.

The portal identifies a caller per D-Bus connection, and KDE's permission
dialog can only show the app's name (it cannot carry a custom reason). So the
portal calls use their own connection, and the first call on it is
`org.freedesktop.host.portal.Registry.Register("io.github.ekats.noteboard")`.
Without that KDE shows "an unidentifiable application". The restore token is
stored with the app id it was granted to; one from before registration is not
trusted, which is the one-time re-approval.

Configuration is declarative, via the QML module that ships with
`layer-shell-qt` (`org.kde.layershell`) — no C++ shim is needed.

### Why the board is a separate process

`QT_WAYLAND_SHELL_INTEGRATION=layer-shell` is process-global and has no
per-window opt-out. Verified on Plasma 6.8.2 with the same QML file run
twice:

| | Surface created |
|---|---|
| env var set | `get_layer_surface(… 2, "window")` |
| env var unset | `get_xdg_surface(…)` |

A window with no attached `LayerShell` properties still becomes a layer
surface, just with default namespace `window` on `LayerTop`. So the popup
and the notes board cannot share a process: the board needs to be an
ordinary toplevel that the user can move, tile and find in the task
switcher.

The split is wanted regardless — the popup is a resident daemon doing
clipboard monitoring, the board launches on demand. They share the SQLite
store.

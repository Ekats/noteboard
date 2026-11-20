# NoteBoard

More than just another clipboard manager — a popup clipboard history and
Keep-style sticky notes in one place.

Early development. Primary target is KDE Plasma 6 on Wayland.

## Why layer-shell

The popup is a `wlr-layer-shell` surface rather than an ordinary window.
That matters because xdg-shell gives a client no way to place its own
window or take a keyboard grab, so a popup built on it cannot appear where
you want it or reliably dismiss itself when focus moves away. Layer-shell
can do both.

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

## Status

| Piece | State |
|---|---|
| Layer-shell popup surface | Working |
| Cursor-relative placement | Working |
| Global shortcut (Meta+Shift+V) | Working, script loaded by the daemon |
| Clipboard history store and list | Working |
| Clipboard capture and copy-back | Working (needs `wl-clipboard`) |
| Paste into the previous app | Working, via the RemoteDesktop portal (one-off permission prompt on first run) |
| Sticky notes board | Not started |
| Memos sync | Not started |
| Google Keep import | Not started |

## Requirements

- Qt 6 with `qt6-qtwayland` and `qt6-qtdeclarative`
- `layer-shell-qt` (provides the `org.kde.layershell` QML module)
- `python3-pyside6`
- `python3-gobject` (Gio talks to the RemoteDesktop portal for pasting;
  PySide6's QtDBus cannot send the uint options it needs)
- `wl-clipboard` 2.2+ (`wl-paste --watch` captures the clipboard; needs a
  compositor with a data-control protocol, which KWin has)
- A compositor advertising `zwlr_layer_shell_v1` (KWin and wlroots do;
  GNOME/Mutter does not)

On Fedora:

```
sudo dnf install python3-pyside6 python3-gobject layer-shell-qt qt6-qtwayland qt6-qtdeclarative
```

## Running

```
python3 -m noteboard
```

### Running at login

```
pip install --user -e .
cp packaging/io.github.ekats.noteboard.desktop ~/.config/autostart/
```

The daemon loads its own KWin script (the `Meta+Shift+V` shortcut) on
start and again whenever KWin restarts, so nothing else needs setting up.

## Notes on sync

The local store mirrors the [Memos](https://github.com/usememos/memos) v1
data model — Markdown content, inline `#tags`, `pinned`, `state` — because
Memos has a documented, versioned API. Fields Memos has no room for
(note colour, title, reminders) are kept local-only and never sync.

Google Keep has no official API for personal accounts
(`keep.googleapis.com` is Workspace enterprise-only), so Keep is a one-way
importer rather than a sync peer.

# NoteBoard

More than just another clipboard manager — a popup clipboard history and
Keep-style sticky notes in one place.

Early development. Primary target is KDE Plasma 6 on Wayland.

## Status

| Piece | State |
|---|---|
| Layer-shell popup surface | Working |
| Cursor-relative placement | Working |
| Global shortcut (Meta+V) | Working, script loaded by the daemon |
| Tray icon (left: Capture, right: Notes) | Working, StatusNotifierItem without a menu |
| Quit button (Settings) | Working, exits 0 so the systemd unit stays stopped |
| Run at login | systemd user service (`packaging/noteboard.service`) |
| Clipboard history store and list | Working |
| Clipboard capture and copy-back | Working (needs `wl-clipboard`) |
| Paste into the previous app | Working, via the RemoteDesktop portal (one-off permission prompt on first run) |
| Capture tab | Working: clipboard list plus a draft pad (written to the store on every edit); send button or Ctrl+Enter turns the draft into a note |
| Notes tab | Working: Markdown cards with inline edit, pin, and delete with confirmation |
| Settings | Working: font family and size, bold/italic/outline, sticky colour, window and inner opacity (optionally linked), clipboard history limit, close-on-mouse-leave |
| Sticky notes board (separate window) | Not started |
| Memos sync | Working, two-way, opt-in (Settings → Memos sync) |
| Google Keep import | Not started |

## Requirements

- Qt 6 with `qt6-qtwayland` and `qt6-qtdeclarative`
- `layer-shell-qt` (provides the `org.kde.layershell` QML module)
- `python3-pyside6`
- `python3-gobject` (Gio talks to the RemoteDesktop portal for pasting;
  PySide6's QtDBus cannot send the uint options it needs)
- `libsecret` (the Memos access token is kept in the Secret Service, read
  through `python3-gobject`)
- `wl-clipboard` 2.2+ (`wl-paste --watch` captures the clipboard; needs a
  compositor with a data-control protocol, which KWin has)
- A compositor advertising `zwlr_layer_shell_v1` (KWin and wlroots do;
  GNOME/Mutter does not)

On Fedora:

```
sudo dnf install python3-pyside6 python3-gobject libsecret layer-shell-qt qt6-qtwayland qt6-qtdeclarative wl-clipboard
```

## Install

```
pip install --user -e .
mkdir -p ~/.local/share/applications
cp packaging/io.github.ekats.noteboard.desktop ~/.local/share/applications/
```

The `.desktop` file is only the app's identity (not an autostart entry).
The unit expects the entry point at `~/.local/bin/noteboard`, which is where
`pip install --user` puts it.

## Enable the service

```
systemctl --user link "$PWD/packaging/noteboard.service"
systemctl --user enable --now noteboard
```

## First run

The first paste into another app shows a one-off RemoteDesktop portal
permission prompt. On its first start NoteBoard also takes `Meta+V` from
Plasma's clipboard popup; [docs/running.md](docs/running.md) explains how to
give it back.

## Docs

- [docs/architecture.md](docs/architecture.md) — why layer-shell, why the board is a separate process
- [docs/running.md](docs/running.md) — systemd service, tray icon, shortcuts
- [docs/sync.md](docs/sync.md) — Memos sync and its conflict rules
- [docs/development.md](docs/development.md) — running from the tree, tests, data and config paths

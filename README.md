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
| Paste into the previous app | Working, via the RemoteDesktop portal (opt-in "Paste automatically" setting, one-off permission prompt) |
| Capture tab | Working: clipboard list plus a draft pad (written to the store on every edit); send button or Ctrl+Enter turns the draft into a note |
| Notes tab | Working: Markdown cards with inline edit, pin, and delete with confirmation |
| Settings | Working: font family and size, bold/italic/outline, sticky colour, window and inner opacity (optionally linked), clipboard history limit, close-on-mouse-leave |
| Sticky notes board (separate window) | Not started |
| Memos sync | Working, two-way, opt-in (Settings → Memos sync) |
| Google Keep import | Not started |

## Requirements

- Qt 6 with `qt6-qtwayland` and `qt6-qtdeclarative`
- `layer-shell-qt` 6.6+ (provides the `org.kde.layershell` QML module)
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

Download the package for your distro from the
[Releases](https://github.com/Ekats/noteboard/releases) page. Dependencies are
installed by the package manager; the service is not enabled automatically.

```
sudo dnf install ./noteboard-*.rpm              # Fedora
sudo apt install ./noteboard_*.deb              # Ubuntu 26.04 or newer
sudo pacman -U noteboard-*.pkg.tar.zst          # Arch
systemctl --user enable --now noteboard
```

Needs `layer-shell-qt` 6.6+ and Qt 6.9+ (Popup.qml uses `LayerShell.Window.screen`
and `RectangularShadow`). That rules out Debian 13 and Ubuntu 25.10 (and older):
the `.deb` refuses to install there. Fedora and Arch are current enough.

### From source (pip)

Install the dependencies above with your package manager first, in
particular the **distro's** PySide6: the PySide6 wheel from PyPI bundles its
own Qt, which cannot see the system's `org.kde.layershell` module, so
NoteBoard deliberately does not depend on it.

```
pip install --user .
mkdir -p ~/.local/share/applications ~/.config/systemd/user
sed "s|@HOME@|$HOME|" packaging/io.github.ekats.noteboard.desktop \
  > ~/.local/share/applications/io.github.ekats.noteboard.desktop
cp packaging/noteboard.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now noteboard
```

The `.desktop` file is only the app's identity (not an autostart entry); its
`Exec` must be the absolute path, which the `sed` fills in. The unit expects
the entry point at `~/.local/bin/noteboard`, which is where `pip install --user`
puts it. (Packages rewrite both paths to `/usr/bin/noteboard`.)

## First run

Pasting into the previous app is opt-in: Settings → **Paste automatically**.
Off (the default on a fresh install), a click only copies and you press Ctrl+V.
Turning it on makes KDE show a one-off permission dialog (keyboard access,
labelled “remote control”); if you decline, the switch turns itself off. If you
granted it with an earlier version, the switch is turned off once at the next
start, because NoteBoard now identifies itself by name; see
[docs/running.md](docs/running.md). On its first start NoteBoard also takes `Meta+V` from
Plasma's clipboard popup; [docs/running.md](docs/running.md) explains how to
give it back.

## License

GPL-3.0-or-later; see [LICENSE](LICENSE).

## Docs

- [docs/architecture.md](docs/architecture.md) — why layer-shell, why the board is a separate process
- [docs/running.md](docs/running.md) — systemd service, tray icon, shortcuts
- [docs/sync.md](docs/sync.md) — Memos sync and its conflict rules
- [docs/development.md](docs/development.md) — running from the tree, tests, data and config paths

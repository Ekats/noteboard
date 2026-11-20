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
| Global shortcut (Meta+V) | Working, script loaded by the daemon |
| Tray icon (left: Capture, right: Notes) | Working, StatusNotifierItem without a menu |
| Quit button (Settings) | Working, exits 0 so the systemd unit stays stopped |
| Run at login | systemd user service (`packaging/noteboard.service`) |
| Clipboard history store and list | Working |
| Clipboard capture and copy-back | Working (needs `wl-clipboard`) |
| Paste into the previous app | Working, via the RemoteDesktop portal (one-off permission prompt on first run) |
| Latest sticky editable in the popup | Working (written to the store on every edit) |
| Sticky notes board | Not started |
| Memos sync | Working, two-way, opt-in (Settings → Memos sync) |
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

### Running all the time (systemd user service)

NoteBoard runs as a systemd user service started with the graphical
session. A crash restarts it after 2 s; **Quit NoteBoard** (bottom of
Settings) exits cleanly and it stays quit until the next login or
`systemctl --user start noteboard`.

Install:

```
pip install --user -e .
mkdir -p ~/.local/share/applications
cp packaging/io.github.ekats.noteboard.desktop ~/.local/share/applications/
```

The `.desktop` file is only the app's identity (not an autostart entry).
The unit expects the entry point at `~/.local/bin/noteboard`, which is where
`pip install --user` puts it.

Enable and start (either link the unit so edits to the repo copy apply, or
copy it):

```
systemctl --user link "$PWD/packaging/noteboard.service"
# or: cp packaging/noteboard.service ~/.config/systemd/user/ && systemctl --user daemon-reload
systemctl --user enable --now noteboard
```

Status and logs:

```
systemctl --user status noteboard
journalctl --user -u noteboard -f
```

Stop / disable:

```
systemctl --user stop noteboard
systemctl --user disable noteboard
```

**Migrating from XDG autostart:** if you previously installed the autostart
entry, remove it so the two do not both start the daemon:

```
rm ~/.config/autostart/io.github.ekats.noteboard.desktop
```

### Tray icon

The tray icon (a StatusNotifierItem, no window) opens the popup at the
pointer: **left click** → Capture tab, **right click** → Notes tab. Clicking
while the popup is open closes it if that tab is showing, otherwise switches
to that tab. Middle click does nothing. The right-click action is the KWin
shortcut `NoteboardShowNotes` (System Settings → Shortcuts → NoteBoard),
which you can also bind a key to.

The daemon loads its own KWin script (the `Meta+V` shortcut) on
start and again whenever KWin restarts, so nothing else needs setting up.

On its first start NoteBoard takes `Meta+V` from Plasma's own clipboard popup
("Show Clipboard Items at Mouse Position"). It does this once, and only if
that popup is what holds the key; a key held by anything else is left alone.
After that, rebind it freely in System Settings → Keyboard → Shortcuts. To
give `Meta+V` back to Plasma:

```sh
busctl --user call org.kde.kglobalaccel /kglobalaccel org.kde.KGlobalAccel \
  setForeignShortcutKeys 'asa(ai)' 4 kwin NoteboardShowPopup KWin 'NoteBoard: show popup at pointer' 0 \
&& busctl --user call org.kde.kglobalaccel /kglobalaccel org.kde.KGlobalAccel \
  setForeignShortcutKeys 'asa(ai)' 4 plasmashell show-on-mouse-pos plasmashell 'Show Clipboard Items at Mouse Position' 1 1 268435542
```

## Notes on sync

The local store mirrors the [Memos](https://github.com/usememos/memos) v1
data model — Markdown content, inline `#tags`, `pinned`, `state` — because
Memos has a documented, versioned API. Fields Memos has no room for
(note colour, title, reminders) are kept local-only and never sync.

### Syncing with a Memos server

Targets Memos 0.30. Off until you open Settings → Memos sync, switch it on,
enter the server URL and paste an access token (create one in Memos under
Settings → My account → Access tokens). The token is kept in the Secret
Service (KWallet / GNOME Keyring) via libsecret — needs `python3-gobject`
and `libsecret` — and never written to `noteboard.conf`. Until all three are
set, no thread is started and nothing touches the network.

Syncing runs on a worker thread at startup, 3 s after a local memo change,
when the popup opens if the last run is over a minute old, every 10 minutes
and on **Sync now**; overlapping triggers coalesce into one run. The note list
reloads when a run changed something, after you finish editing a card if one
is open.

Rules, ported from the MoeMemos apps:

- Memos are matched by id (local notes are created with a 32-char hex id,
  which the server accepts). "Changed on the server" means its `updateTime`
  differs from the one recorded at the last sync (the server only has
  second resolution).
- Edited only here → pushed (only content, pinned, state and visibility, so
  attachments on the server are left alone). Edited only on the server →
  pulled. Edited on both → both are kept: your version becomes a new note,
  the server's replaces the original.
- Deleting here deletes on the server; deleting on the server deletes here —
  unless you edited it here meanwhile, in which case it is re-created. An
  edit made elsewhere beats a delete made here.
- Edits made while a push is in flight are never overwritten; they go out
  on the next run.
- Colour, title, reminders and the capture-pad draft stay local.
- Only your own memos are synced, archived ones included.

Google Keep has no official API for personal accounts
(`keep.googleapis.com` is Workspace enterprise-only), so Keep is a one-way
importer rather than a sync peer.

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

## Status

| Piece | State |
|---|---|
| Layer-shell popup surface | Working |
| Cursor-relative placement | In progress |
| Clipboard history | Not started |
| Sticky notes board | Not started |
| Memos sync | Not started |
| Google Keep import | Not started |

## Requirements

- Qt 6 with `qt6-qtwayland` and `qt6-qtdeclarative`
- `layer-shell-qt` (provides the `org.kde.layershell` QML module)
- `python3-pyside6`
- A compositor advertising `zwlr_layer_shell_v1` (KWin and wlroots do;
  GNOME/Mutter does not)

On Fedora:

```
sudo dnf install python3-pyside6 layer-shell-qt qt6-qtwayland qt6-qtdeclarative
```

## Running

```
python3 -m noteboard
```

## Notes on sync

The local store mirrors the [Memos](https://github.com/usememos/memos) v1
data model — Markdown content, inline `#tags`, `pinned`, `state` — because
Memos has a documented, versioned API. Fields Memos has no room for
(note colour, title, reminders) are kept local-only and never sync.

Google Keep has no official API for personal accounts
(`keep.googleapis.com` is Workspace enterprise-only), so Keep is a one-way
importer rather than a sync peer.

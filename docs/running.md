# Running

## Running all the time (systemd user service)

NoteBoard runs as a systemd user service started with the graphical
session. A crash restarts it after 2 s; **Quit NoteBoard** (bottom of
Settings) exits cleanly and it stays quit until the next login or
`systemctl --user start noteboard`.

Install (see the README for the full steps):

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

## Tray icon

The tray icon (a StatusNotifierItem, no window) opens the popup at the
pointer: **left click** → Capture tab, **right click** → Notes tab. Clicking
while the popup is open closes it if that tab is showing, otherwise switches
to that tab. Middle click does nothing. The right-click action is the KWin
shortcut `NoteboardShowNotes` (System Settings → Shortcuts → NoteBoard),
which you can also bind a key to.

The daemon loads its own KWin script (the `Meta+V` shortcut) on
start and again whenever KWin restarts, so nothing else needs setting up.

## Meta+V

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

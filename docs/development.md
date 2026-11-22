# Development

## Running from the tree

```
python3 -m noteboard
```

This cannot run alongside the systemd service: both register the D-Bus name
`io.github.ekats.noteboard`, and the second one prints "could not take the
D-Bus name, is it already running?" and exits 1. Stop the service first:

```
systemctl --user stop noteboard
```

See [running.md](running.md) for the service.

## Tests

The tests are stdlib `unittest` under `tests/`. From the repo root:

```
python3 -m unittest discover tests
```

## Data and config paths

| What | Path |
|---|---|
| Clipboard history, notes and draft (SQLite) | `~/.local/share/noteboard/noteboard.db` |
| Settings (QtCore `Settings`/`QSettings`) | `~/.config/noteboard/noteboard.conf` |

The settings file also holds the one-off flags for the Meta+V takeover, the
`autoPaste` setting and the RemoteDesktop portal restore token (with
`portal/restoreTokenApp`, the app id it was granted to). The Memos access token is not in it;
it lives in the Secret Service.

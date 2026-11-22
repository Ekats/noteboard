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

## Packages

Three native packages are built from the same tree: an RPM
(`packaging/rpm/noteboard.spec`), a DEB (`debian/`) and an Arch package
(`packaging/arch/PKGBUILD`). `pyproject.toml` has no runtime dependencies on
purpose (the PySide6 wheel bundles a Qt that cannot see `layer-shell-qt`), so
each packaging lists the distro's real dependencies by hand. The repo's
`noteboard.service` and `.desktop` point at the `pip --user` location; each
packaging rewrites that to `/usr/bin`.

The build and smoke steps run in throw-away containers, the same scripts
locally and in CI (podman, or docker if podman is missing):

```
packaging/container.sh test  rpm  dist   # unit tests in Fedora
packaging/container.sh build rpm  dist   # fedora:latest      -> dist/*.rpm
packaging/container.sh build deb  dist   # ubuntu:26.04       -> dist/*.deb
packaging/container.sh build arch dist   # archlinux:latest   -> dist/*.pkg.tar.zst
packaging/container.sh smoke rpm  dist   # install it in a clean container and check it
```

`smoke` installs the package with dnf/apt/pacman (dependencies resolved from
the repos, no weak/recommended ones), checks every installed file and the
`/usr/bin` paths, and loads the installed `Popup.qml` on Qt's `offscreen`
platform (`packaging/smoke/qml_load.py`). The `org.kde.layershell` import
resolves there; the layer surface itself is not created (offscreen is not a
Wayland window), so placement still needs a manual check on a real session.
`IMAGE=debian:trixie packaging/container.sh smoke deb dist` shows how older
releases refuse the install.

The version lives in `pyproject.toml`; `packaging/check-versions.sh` fails
the build if the spec, `debian/changelog` or the PKGBUILD disagree.

## Releases

Bump the version in `pyproject.toml`, the spec (`Version:`, `%changelog`),
`debian/changelog` and the PKGBUILD (`pkgver`), commit, then push a tag:

```
git tag v0.1.0 && git push origin v0.1.0
```

The `CI` workflow then runs the tests, builds and smoke-tests the three
packages, and creates the GitHub Release with them attached (notes are
generated from the commits since the previous release). The tag must equal
`v` plus the `pyproject.toml` version or the run fails.

## Data and config paths

| What | Path |
|---|---|
| Clipboard history, notes and draft (SQLite) | `~/.local/share/noteboard/noteboard.db` |
| Settings (QtCore `Settings`/`QSettings`) | `~/.config/noteboard/noteboard.conf` |

The settings file also holds the one-off flags for the Meta+V takeover, the
`autoPaste` setting and the RemoteDesktop portal restore token (with
`portal/restoreTokenApp`, the app id it was granted to). The Memos access token is not in it;
it lives in the Secret Service.

#!/bin/sh
# Usage: smoke.sh <rpm|deb|arch> <package-file>
# Runs inside a clean container of the target distro. Installs the package
# with the distro's package manager (dependencies resolved from the repos,
# no recommended packages) and checks the result.
set -eu
kind=$1
pkg=$2
here=$(dirname "$0")

case $kind in
rpm)
    dnf install -y --setopt=install_weak_deps=False "$pkg"
    ;;
deb)
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y --no-install-recommends "$pkg"
    ;;
arch)
    pacman -Syu --noconfirm --disable-sandbox >/dev/null
    pacman -U --noconfirm --disable-sandbox "$pkg"
    ;;
*) echo "unknown kind $kind" >&2; exit 2 ;;
esac

fail=0
check() { # check <description> <command...>
    desc=$1; shift
    if "$@" >/dev/null 2>&1; then echo "ok   $desc"; else echo "FAIL $desc"; fail=1; fi
}

# Run from / with -I so the import cannot pick up a source tree.
cd /
check "import noteboard" python3 -I -c "import noteboard"
check "import the daemon modules (PySide6, gi Secret)" python3 -I -c \
    "import noteboard.__main__, noteboard.secrets, noteboard.paste"

pkgdir=$(python3 -I -c "import noteboard, pathlib; print(pathlib.Path(noteboard.__file__).parent)")
for f in qml/Popup.qml qml/HomePage.qml qml/NotesPage.qml qml/SettingsPage.qml \
         qml/OutlineLabel.qml qml/ShadeButton.qml qml/sticky.js \
         kwin/noteboard.js noteboard.png; do
    check "package data $f" test -s "$pkgdir/$f"
done

for f in /usr/bin/noteboard \
         /usr/share/applications/io.github.ekats.noteboard.desktop \
         /usr/share/icons/hicolor/96x96/apps/noteboard.png \
         /usr/lib/systemd/user/noteboard.service; do
    check "installed $f" test -s "$f"
done
check "entry point is executable" test -x /usr/bin/noteboard
check "desktop Exec is /usr/bin/noteboard" grep -qx 'Exec=/usr/bin/noteboard' \
    /usr/share/applications/io.github.ekats.noteboard.desktop
check "unit ExecStart is /usr/bin/noteboard" grep -qx 'ExecStart=/usr/bin/noteboard' \
    /usr/lib/systemd/user/noteboard.service
check "no pip --user path left in packaged files" sh -c \
    '! grep -E "^Exec(Start)?=.*(\.local/bin|@HOME@|%h)" /usr/share/applications/io.github.ekats.noteboard.desktop /usr/lib/systemd/user/noteboard.service'
check "unit is not enabled automatically" sh -c \
    '! ls /etc/systemd/user/*.wants/noteboard.service /usr/lib/systemd/user/*.wants/noteboard.service'
check "package does not require the PySide6 wheel" python3 -I -c \
    "import importlib.metadata as m; r = m.requires('noteboard') or []; assert not r, r"
check "wl-paste available" command -v wl-paste

echo "--- offscreen QML load"
if python3 -I "$here/qml_load.py"; then echo "ok   Popup.qml loads"; else echo "FAIL Popup.qml loads"; fail=1; fi

[ "$fail" = 0 ] && echo "SMOKE PASSED ($kind)" || echo "SMOKE FAILED ($kind)"
exit $fail

#!/bin/sh
# Runs inside a Fedora container with the repo at /src: system PySide6 (the
# same stack the Fedora package uses), then the stdlib unittest suite.
set -eu
dnf install -y --setopt=install_weak_deps=False python3 python3-pyside6 \
    python3-gobject libsecret layer-shell-qt qt6-qtwayland qt6-qtdeclarative wl-clipboard
# Work on a copy: /src is read-only and the tests write __pycache__.
work=$(mktemp -d)
cp -r /src/. "$work/"
cd "$work"
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -v tests

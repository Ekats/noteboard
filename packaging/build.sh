#!/bin/sh
# Usage: build.sh <rpm|deb|arch>      (runs INSIDE the target distro container)
# Expects the repo at /src (read-only is fine) and writes packages to /out.
# Use packaging/container.sh to run it in a throw-away container.
set -eu
kind=$1
src=${SRC:-/src}
out=${OUT:-/out}
work=$(mktemp -d)
mkdir -p "$out"

"$src/packaging/check-versions.sh" "$src"
tarball=$("$src/packaging/make-source.sh" "$src" "$work/dist")
version=$(basename "$tarball" .tar.gz)   # noteboard-<version>

case $kind in
rpm)
    dnf install -y rpm-build python3-devel python3-pip python3-setuptools \
        python3-wheel pyproject-rpm-macros desktop-file-utils systemd-rpm-macros
    mkdir -p "$work/rpmbuild/SOURCES"
    cp "$tarball" "$work/rpmbuild/SOURCES/"
    rpmbuild -bb --define "_topdir $work/rpmbuild" "$src/packaging/rpm/noteboard.spec"
    cp "$work"/rpmbuild/RPMS/noarch/noteboard-*.rpm "$out/"
    ;;
deb)
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y --no-install-recommends build-essential debhelper dh-python \
        pybuild-plugin-pyproject python3-all python3-setuptools fakeroot
    tar -C "$work" -xzf "$tarball"
    (cd "$work/$version" && dpkg-buildpackage -us -uc -b)
    cp "$work"/noteboard_*_all.deb "$out/"
    ;;
arch)
    pacman -Syu --noconfirm --disable-sandbox >/dev/null
    pacman -S --noconfirm --needed --disable-sandbox base-devel python-build \
        python-installer python-setuptools python-wheel
    # makepkg refuses to run as root.
    id builder >/dev/null 2>&1 || useradd -m builder
    build=/home/builder/pkg
    rm -rf "$build"; mkdir -p "$build"
    cp "$tarball" "$src/packaging/arch/PKGBUILD" "$build/"
    chown -R builder "$build"
    # --nodeps: the runtime depends (Qt, PySide6...) are not needed to build a
    # pure-Python wheel; the smoke test installs them from the repos instead.
    su builder -c "cd $build && makepkg -f --noconfirm --nodeps"
    cp "$build"/noteboard-*.pkg.tar.zst "$out/"
    ;;
*) echo "unknown kind $kind" >&2; exit 2 ;;
esac
ls -l "$out"

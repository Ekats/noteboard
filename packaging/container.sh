#!/bin/sh
# Usage: container.sh <build|smoke|test> <rpm|deb|arch> [out-dir]
# Runs one step in a throw-away container (podman, or docker when podman is
# missing), identically on a laptop and in CI.
#   build  builds the package from the working tree into <out-dir>
#   smoke  installs the package from <out-dir> in a CLEAN container and checks it
#   test   runs the unit tests in a Fedora container (kind is ignored: use "rpm")
# Set IMAGE to override the base image (e.g. IMAGE=debian:trixie for deb).
set -eu
step=$1
kind=$2
repo=$(cd "$(dirname "$0")/.." && pwd)
out=$(mkdir -p "${3:-$repo/dist}" && cd "${3:-$repo/dist}" && pwd)
engine=$(command -v podman || command -v docker)

case $kind in
rpm)  default_image=docker.io/library/fedora:latest ;;
# Ubuntu 26.04 is the oldest Debian-family release whose layer-shell-qt (6.6)
# has the QML API Popup.qml uses; see debian/control.
deb)  default_image=docker.io/library/ubuntu:26.04 ;;
arch) default_image=docker.io/library/archlinux:latest ;;
*) echo "unknown kind $kind" >&2; exit 2 ;;
esac
image=${IMAGE:-$default_image}
case $image in */*) ;; *) image=docker.io/library/$image ;; esac

run() { "$engine" run --rm -v "$repo:/src:ro,z" -v "$out:/out:z" "$@"; }

case $step in
build)
    run "$image" sh /src/packaging/build.sh "$kind"
    ;;
smoke)
    # Exactly one package of the kind; the container sees only /out and /src.
    case $kind in rpm) ext=rpm ;; deb) ext=deb ;; arch) ext=pkg.tar.zst ;; esac
    pkg=$(ls "$out"/noteboard*.$ext | head -n1)
    run "$image" sh /src/packaging/smoke/smoke.sh "$kind" "/out/$(basename "$pkg")"
    ;;
test)
    run -e QT_QPA_PLATFORM=offscreen "$image" sh /src/packaging/unit-tests.sh
    ;;
*) echo "unknown step $step" >&2; exit 2 ;;
esac

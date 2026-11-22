#!/bin/sh
# Usage: make-source.sh <repo-dir> <out-dir>
# Writes <out-dir>/noteboard-<version>.tar.gz from the working tree (not git
# archive, so local uncommitted changes are packaged too and CI needs no git
# metadata). The tarball has a noteboard-<version>/ top directory.
set -eu
repo=$1
out=$2
version=$(sed -n 's/^version = "\(.*\)"/\1/p' "$repo/pyproject.toml")
[ -n "$version" ] || { echo "no version in pyproject.toml" >&2; exit 1; }
mkdir -p "$out"
tar -C "$repo" \
    --exclude=.git --exclude=.mco --exclude=.mcp.json --exclude=.vscode \
    --exclude=__pycache__ --exclude='*.egg-info' --exclude=build --exclude=dist \
    --transform "s,^\./,noteboard-$version/," \
    -czf "$out/noteboard-$version.tar.gz" .
echo "$out/noteboard-$version.tar.gz"

#!/bin/sh
# Usage: check-versions.sh <repo-dir>   (and, in CI on a tag, EXPECT_TAG=v0.1.0)
# pyproject.toml is the version source; the three packagings repeat it by
# convention, so fail early when one is left behind.
set -eu
repo=${1:-.}
v=$(sed -n 's/^version = "\(.*\)"/\1/p' "$repo/pyproject.toml")
rpm=$(sed -n 's/^Version:[[:space:]]*//p' "$repo/packaging/rpm/noteboard.spec")
deb=$(sed -n '1s/^noteboard (\([^-]*\)-.*/\1/p' "$repo/debian/changelog")
arch=$(sed -n 's/^pkgver=//p' "$repo/packaging/arch/PKGBUILD")
fail=0
for pair in "rpm=$rpm" "deb=$deb" "arch=$arch"; do
    [ "${pair#*=}" = "$v" ] || { echo "version mismatch: ${pair%%=*} has ${pair#*=}, pyproject has $v" >&2; fail=1; }
done
if [ -n "${EXPECT_TAG:-}" ] && [ "$EXPECT_TAG" != "v$v" ]; then
    echo "tag $EXPECT_TAG does not match pyproject version $v" >&2
    fail=1
fi
[ "$fail" = 0 ] && echo "versions agree: $v"
exit $fail

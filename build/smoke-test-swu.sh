#!/bin/sh
# Checks the update packages of a build before they are published. Printers
# install releases on their own (automatic updates), so a package that can't
# be unpacked, or carries the wrong version, must never reach GitHub.
#
#   sh build/smoke-test-swu.sh <dist directory> <expected version>
#
# For every update-*.swu, standard and compressed:
#   - it opens with the password of its printer family
#   - its setup archive passes its md5 and unpacks with the same code the
#     printer uses (files/3-rinkhals/opt/rinkhals/ui/swu_setup.py)
#   - update.sh, the version files and the files update.sh insists on exist
#   - the version inside is the one being released
# and every standard package has a compressed twin that is smaller.

set -e

DIST=${1:?Usage: smoke-test-swu.sh <dist directory> <expected version>}
VERSION=${2:?Usage: smoke-test-swu.sh <dist directory> <expected version>}
HERE=$(cd "$(dirname "$0")" && pwd)
UNPACK=$HERE/../files/3-rinkhals/opt/rinkhals/ui/swu_setup.py
PYTHON=${PYTHON:-python3}

password_for() {
    case "$1" in
        update-k2p-k3*) echo 'U2FsdGVkX19deTfqpXHZnB5GeyQ/dtlbHjkUnwgCi+w=' ;;
        update-ks1*) echo 'U2FsdGVkX1+lG6cHmshPLI/LaQr9cZCjA8HZt6Y8qmbB7riY' ;;
        update-k3m*) echo '4DKXtEGStWHpPgZm8Xna9qluzAI8VJzpOsEIgd8brTLiXs8fLSu3vRx8o7fMf4h6' ;;
        *) return 1 ;;
    esac
}

fail() {
    echo "FAILED: $*" >&2
    exit 1
}

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

count=0
for swu in "$DIST"/update-*.swu; do
    [ -f "$swu" ] || fail "no update-*.swu in $DIST"
    name=$(basename "$swu")
    password=$(password_for "$name") || fail "$name: unknown printer family"

    rm -rf "$WORK/x"
    mkdir -p "$WORK/x"
    unzip -q -P "$password" "$swu" -d "$WORK/x" || fail "$name: does not open with its password"
    dir=$WORK/x/update_swu
    [ -d "$dir" ] || fail "$name: no update_swu folder inside"

    case "$name" in
        *-compressed.swu) archive=setup.tar.xz ;;
        *) archive=setup.tar.gz ;;
    esac
    [ -f "$dir/$archive" ] || fail "$name: expected $archive inside"
    [ -f "$dir/$archive.md5" ] || fail "$name: no $archive.md5"

    "$PYTHON" "$UNPACK" "$dir" > /dev/null || fail "$name: the printer's unpacker rejects it"

    for path in update.sh .version rinkhals/.version rinkhals/start.sh rinkhals/tools.sh \
        rinkhals/usr/bin/python rinkhals/opt/rinkhals/ui/swu_setup.py rinkhals/home/rinkhals; do
        [ -e "$dir/$path" ] || [ -L "$dir/$path" ] || fail "$name: $path is missing"
    done
    for file in .version rinkhals/.version; do
        found=$(cat "$dir/$file")
        [ "$found" = "$VERSION" ] || fail "$name: $file says '$found', expected '$VERSION'"
    done

    echo "ok  $name ($(du -h "$swu" | cut -f1))"
    count=$((count + 1))
done

# Each standard package has a compressed twin, and it really is smaller
for swu in "$DIST"/update-*.swu; do
    case "$swu" in *-compressed.swu) continue ;; esac
    twin=${swu%.swu}-compressed.swu
    [ -f "$twin" ] || fail "$(basename "$swu") has no compressed package"
    [ "$(wc -c < "$twin")" -lt "$(wc -c < "$swu")" ] || fail "$(basename "$twin") is not smaller than the standard package"
done

echo "$count packages checked, version $VERSION"

#!/bin/sh

# Finalizes the bundle directory after all build outputs have been merged into it.
# Usage: prepare-bundle.sh <bundle_dir> <version>
#   bundle_dir: path to the bundle directory (default: /bundle)
#   version:    version string (default: dev)
#
# Expects:
#   $bundle_dir/rinkhals/  — merged output from buildroot, python, and apps stages
#   $bundle_dir/           — root-level files (e.g. start.sh.patch)

set -e

BUNDLE_DIR=${1:-/bundle}
VERSION=${2:-dev}

# Remove everything but shell patches
find "$BUNDLE_DIR/rinkhals/opt/rinkhals/patches" -type f ! -name "*.sh" -exec rm {} +

# Rename busybox (to avoid conflict with stock) and update all symlinks
mv "$BUNDLE_DIR/rinkhals/bin/busybox" "$BUNDLE_DIR/rinkhals/bin/busybox.rinkhals"
find "$BUNDLE_DIR/" -type l -exec sh -c '
    for link; do
        target=$(readlink "$link")
        if [ "$(basename "$target")" = "busybox" ]; then
            dir=$(dirname "$target")
            newtarget="$dir/busybox.rinkhals"
            newtarget="${newtarget#./}"
            ln -snf "$newtarget" "$link"
        fi
    done
    ' sh {} +

# Validate and set Boomslang version
# Accepted: a release name as a tag (2611-3-alpha, see build/release-name.sh),
# a dated tag from before the names (yyyymmdd_nn, yyyymmdd_nn_tag), a Git
# commit ID, or 'dev'. The version becomes a folder name on the printer, so
# nothing with spaces or slashes may get through.
RELEASE_NAME='^[0-9]{2}(1[0-2]|[1-9])-[0-9]{1,3}-(alpha|beta|release-preview|release)$'
DATED='^[0-9]{8}_[0-9]{2}(_[a-z0-9_-]+)?$'
if [ -z "$VERSION" ] || {
    [ "$VERSION" != "dev" ] &&
    ! echo "$VERSION" | grep -Eq "$RELEASE_NAME" &&
    ! echo "$VERSION" | grep -Eq "$DATED" &&
    ! echo "$VERSION" | grep -Eq '^[0-9a-f]{40}$'
} || {
    echo "$VERSION" | grep -Eq "$DATED" &&
    ! date -d "$(echo "$VERSION" | cut -d'_' -f1)" +"%Y%m%d" >/dev/null 2>&1
}; then
    echo "Invalid version (must be a release name like '2611-3-alpha', 'yyyymmdd_nn', 'yyyymmdd_nn_tag', a Git commit ID, or 'dev'): $VERSION"
    exit 1
else
    echo "$VERSION" > "$BUNDLE_DIR/.version"
    echo "$VERSION" > "$BUNDLE_DIR/rinkhals/.version"
fi

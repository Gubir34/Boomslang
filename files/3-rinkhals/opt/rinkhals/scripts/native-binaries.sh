#!/bin/sh

# Crash-safe patching of the stock Anycubic binaries (gkapi, K3SysUi).
#
# The patched binary has to run from its stock location, so start.sh swaps it
# in, starts it, then swaps the stock binary back. The previous sequence
# deleted <target>.original at the start of every boot. If power was lost while
# the patched copy was in place, the next boot deleted the only intact stock
# copy and kept a half-written patched file instead (issue #198: gkapi and
# gkapi.patch truncated to 8 MiB).
#
# The rules here:
# - The stock binary is never deleted. Its identity is checked against the
#   "Before MD5" of the firmware's patch script before anything is moved.
# - A .original left behind by an interrupted boot is restored when it is the
#   stock binary for this firmware, and kept otherwise.
# - The patched copy is built in <target>.new, verified against the patch
#   script's "After MD5" and flushed to storage before it replaces the stock
#   binary. At every step, either <target> or <target>.original is the
#   complete stock binary.
# - Anything unexpected leaves the files untouched and skips the patch.
#
# native_restore only swaps back what native_patch swapped out in this boot
# (a marker in $NATIVE_STATE_DIR, a RAM disk that is empty after every
# boot). A leftover <target>.original that nobody verified is never moved
# into place.
#
# Usage, from the directory holding the binaries:
#   native_patch <target> <patch script>    # before starting <target>
#   native_restore <target>                 # once <target> is running

native_log() {
    if command -v log > /dev/null 2>&1; then
        log "$@"
    else
        echo "$@"
    fi
}

NATIVE_STATE_DIR=${NATIVE_STATE_DIR:-/tmp/rinkhals}

native_marker() {
    echo "$NATIVE_STATE_DIR/native-$(basename "$1").swapped"
}

native_md5() {
    [ -f "$1" ] || return 1
    md5sum "$1" 2> /dev/null | awk '{print $1}'
}

native_patch_md5() {
    # $1: patch script, $2: Before or After
    sed -n "s/^# $2 MD5: \([0-9a-f]\{32\}\)$/\1/p" "$1" | head -n 1
}

# Make sure <target> is the stock binary, using .original if it has to.
# Returns 1 when the stock binary cannot be found, without changing anything.
native_recover() {
    TARGET=$1
    STOCK_MD5=$2

    rm -f "$TARGET.new" 2> /dev/null

    if [ "$(native_md5 "$TARGET")" = "$STOCK_MD5" ]; then
        return 0
    fi

    if [ "$(native_md5 "$TARGET.original")" = "$STOCK_MD5" ]; then
        native_log "  - $TARGET is not the stock binary, restoring it from $TARGET.original (interrupted startup)"
        if [ -f "$TARGET" ]; then
            rm -f "$TARGET.patch" 2> /dev/null
            mv -f "$TARGET" "$TARGET.patch"
        fi
        mv -f "$TARGET.original" "$TARGET"
        sync
        return 0
    fi

    native_log "  - /!\\ $TARGET does not match the stock binary for this firmware and no stock copy was found, leaving it untouched"
    return 1
}

native_patch() {
    TARGET=$1
    TARGET_PATCH=$2
    rm -f "$(native_marker "$TARGET")" 2> /dev/null

    STOCK_MD5=$(native_patch_md5 "$TARGET_PATCH" Before)
    PATCHED_MD5=$(native_patch_md5 "$TARGET_PATCH" After)
    if [ -z "$STOCK_MD5" ] || [ -z "$PATCHED_MD5" ]; then
        native_log "  - /!\\ $TARGET_PATCH has no MD5 header, skipping $TARGET"
        return 1
    fi

    native_recover "$TARGET" "$STOCK_MD5" || return 1

    # Build and verify the patched copy next to the stock binary
    if ! cp "$TARGET" "$TARGET.new"; then
        rm -f "$TARGET.new" 2> /dev/null
        native_log "  - /!\\ Could not copy $TARGET, skipping the patch"
        return 1
    fi
    "$TARGET_PATCH" "$TARGET.new" > /dev/null 2>&1
    if [ "$(native_md5 "$TARGET.new")" != "$PATCHED_MD5" ]; then
        rm -f "$TARGET.new"
        native_log "  - /!\\ Patching $TARGET did not give the expected result, starting it unpatched"
        return 1
    fi
    chmod +x "$TARGET.new"
    sync

    # Swap it in. A stale .original was either restored above or does not
    # match this firmware, so it can go.
    rm -f "$TARGET.original" 2> /dev/null
    mv -f "$TARGET" "$TARGET.original"
    mv -f "$TARGET.new" "$TARGET"
    sync
    mkdir -p "$NATIVE_STATE_DIR" && : > "$(native_marker "$TARGET")"
    return 0
}

native_restore() {
    TARGET=$1

    # Only undo our own swap from this boot
    [ -f "$(native_marker "$TARGET")" ] || return 0
    [ -f "$TARGET.original" ] || return 0

    rm -f "$TARGET.patch" 2> /dev/null
    if [ -f "$TARGET" ]; then
        mv -f "$TARGET" "$TARGET.patch"
    fi
    mv -f "$TARGET.original" "$TARGET"
    rm -f "$(native_marker "$TARGET")" 2> /dev/null
    sync
}

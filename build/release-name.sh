#!/bin/sh
# Boomslang release names: {YY}{M} {N} {Channel}
#
#   2611 3 Alpha  = year 2026, November (month 1 to 12, not zero padded),
#                   3rd release of that month (0 to 999, one count shared by
#                   every channel), Alpha channel
#
# Channels, least to most stable: Alpha, Beta, Release Preview, Release.
# Only Release is published as a full release; the others are pre-releases.
#
# Git tags (and the version folders on the printer) can't hold spaces, so the
# tag is the same name written 2611-3-alpha, 2611-4-release-preview, ...
# The touch UI (release_assets.py) and the web portal (firmware.go,
# firmwareStatus.ts) read the same format.
#
# Usage:
#   release-name.sh next <channel> [YYM]   tag for the next release, reading
#                                          existing tags from stdin (one per
#                                          line, git ls-remote output is fine)
#   release-name.sh title <tag>            "2611 3 Alpha"
#   release-name.sh prerelease <tag>       exit 0 when the tag is a pre-release
#   release-name.sh check <tag>            exit 0 when the tag is a release name

set -e

channel_name() {
    case "$1" in
        alpha) echo Alpha ;;
        beta) echo Beta ;;
        release-preview) echo "Release Preview" ;;
        release) echo Release ;;
        *) return 1 ;;
    esac
}

is_name() {
    echo "$1" | grep -Eq '^[0-9]{2}(1[0-2]|[1-9])-[0-9]{1,3}-(alpha|beta|release-preview|release)$'
}

case "$1" in
    next)
        channel=$2
        channel_name "$channel" > /dev/null || { echo "Unknown channel '$channel' (alpha, beta, release-preview, release)" >&2; exit 1; }
        prefix=${3:-$(date -u +%y)$(date -u +%m | sed 's/^0//')}
        # Highest number used this month by any channel, + 1. Reading the
        # tags rather than counting releases: a deleted release can leave its
        # tag behind, and counting would then reuse a number.
        next=$(sed -e 's|.*/||' -e 's|.*[[:space:]]||' -e 's|\^{}$||' |
            grep -E "^${prefix}-[0-9]{1,3}-(alpha|beta|release-preview|release)$" |
            cut -d- -f2 |
            awk '{ n = $1 + 0; if (n > max) max = n } END { print max + 1 }')
        if [ "$next" -gt 999 ]; then
            echo "Release number $next for $prefix is over 999" >&2
            exit 1
        fi
        echo "${prefix}-${next}-${channel}"
        ;;
    title)
        if is_name "$2"; then
            month=${2%%-*}
            rest=${2#*-}
            number=${rest%%-*}
            channel=${rest#*-}
            echo "$month $number $(channel_name "$channel")"
        else
            echo "$2"   # an older dated tag (20261108_04)
        fi
        ;;
    prerelease)
        case "$2" in
            *-release) exit 1 ;;
            *-alpha|*-beta|*-release-preview|*_test*|*beta*) exit 0 ;;
            *) exit 1 ;;
        esac
        ;;
    check)
        is_name "$2"
        ;;
    *)
        sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'
        exit 1
        ;;
esac

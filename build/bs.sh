#!/bin/sh
# Quick deploy of small changes to the Boomslang running on the printer,
# without building a new package.
#
#   sh build/bs.sh connect       once: opens a 2 hour SSH connection
#                                       (asks for the root password, default rockchip)
#   sh build/bs.sh ui            touch screen UI (python and shell files)
#   sh build/bs.sh core          everything above plus images, fonts, scripts, tools,
#                                       patches and start/stop scripts
#   sh build/bs.sh apps [name..] apps from this repo or ../Boomslang.Apps
#                                       (restarts each one if it is enabled)
#   sh build/bs.sh install <update-*.swu>
#                                       full update from this PC, like Updates > Install on
#                                       the printer (asks to confirm, then reboots it)
#   sh build/bs.sh status        versions, memory and Boomslang processes
#   sh build/bs.sh close         close the connection now
#
# Nothing permanent is installed on the printer: the connection is a
# temporary control socket on this PC that ends after 2 hours or on "close".
# Files go into the active Boomslang install, so a normal update or
# reinstall replaces them. BS_DRY=1 lists what would be sent without
# touching the printer. BS_HOST overrides the printer address.
#
# Not covered: the Go web portal binary and the Python/Buildroot parts need
# a real build (docker buildx build).

set -e
HOST=${BS_HOST:-192.168.1.102}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
APPS_REPO=${BS_APPS_REPO:-$REPO/../Boomslang.Apps}
FILES=$REPO/files
SOCK=$HOME/.ssh/ctl-boomslang-$HOST
CUR=/useremain/rinkhals/.current

remote() {
    ssh -o ControlPath="$SOCK" -o BatchMode=yes root@"$HOST" "$@"
}

need_connection() {
    [ -n "$BS_DRY" ] && return 0
    if ! ssh -o ControlPath="$SOCK" -O check root@"$HOST" 2> /dev/null; then
        echo "Not connected. Run first:  sh build/bs.sh connect" >&2
        exit 1
    fi
}

# send <local base dir> <remote dir> <path..>  (paths relative to the base dir)
send() {
    base=$1; dest=$2; shift 2
    if [ -n "$BS_DRY" ]; then
        echo "would send to $dest:"
        (cd "$base" && tar -cf - --owner=0 --group=0 --exclude=__pycache__ --exclude='*.pyc' "$@" | tar -tf - | grep -v '/$' | sed 's/^/  /')
        return 0
    fi
    (cd "$base" && tar -cf - --owner=0 --group=0 --exclude=__pycache__ --exclude='*.pyc' "$@") |
        remote "mkdir -p \"$dest\" && tar -xf - -o -C \"$dest\" && sync"
    echo "sent $* to $dest"
}

cmd=${1:-}
[ $# -gt 0 ] && shift

case "$cmd" in
    connect)
        ssh -o ControlMaster=yes -o ControlPath="$SOCK" -o ControlPersist=2h \
            -o StrictHostKeyChecking=accept-new -fN root@"$HOST"
        echo "Connected for 2 hours. Close with: sh build/bs.sh close"
        ;;
    close)
        ssh -o ControlPath="$SOCK" -O exit root@"$HOST" 2> /dev/null && echo "Connection closed" || echo "Was not connected"
        ;;
    status)
        need_connection
        remote ". $CUR/tools.sh > /dev/null 2>&1
            echo \"Boomslang \$RINKHALS_VERSION on \$KOBRA_MODEL \$KOBRA_VERSION\"
            uptime
            free | sed -n 2p
            echo 'processes:'; ps | grep -E 'rinkhals-web|moonraker|lighttpd|rinkhals-ui|K3SysUi|gkapi|gklib' | grep -v grep | awk '{print \"  \" \$1, \$5, \$6}'"
        ;;
    ui)
        need_connection
        # Python and shell files only; images and fonts (assets/) and the
        # LVGL library rarely change and go with "core"
        send "$FILES/3-rinkhals/opt/rinkhals/ui" "$CUR/opt/rinkhals/ui" \
            $(cd "$FILES/3-rinkhals/opt/rinkhals/ui" && ls -d *.py *.sh)
        echo "Close the Boomslang screen and open it again to see the change."
        ;;
    core)
        need_connection
        send "$FILES/3-rinkhals/opt/rinkhals" "$CUR/opt/rinkhals" ui scripts tools patches
        send "$FILES/3-rinkhals" "$CUR" tools.sh start.sh stop.sh
        echo "Scripts apply the next time they run; start.sh and tools.sh at the next Boomslang start."
        ;;
    apps)
        need_connection
        [ $# -gt 0 ] || { echo "Usage: bs.sh apps <name> [name..]" >&2; exit 1; }
        for app in "$@"; do
            if [ -d "$APPS_REPO/apps/$app" ]; then
                send "$APPS_REPO/apps" "/useremain/home/rinkhals/apps" "$app"
            elif [ -d "$FILES/4-apps/home/rinkhals/apps/$app" ]; then
                send "$FILES/4-apps/home/rinkhals/apps" "$CUR/home/rinkhals/apps" "$app"
            else
                echo "No app named $app in $APPS_REPO/apps or $FILES/4-apps" >&2
                exit 1
            fi
            [ -n "$BS_DRY" ] && continue
            remote ". $CUR/tools.sh > /dev/null 2>&1
                chmod +x \$(get_app_root $app)/*.sh \$(get_app_root $app)/www/api/*.cgi 2> /dev/null
                if [ \"\$(is_app_enabled $app)\" = 1 ]; then stop_app $app; start_app $app; echo 'restarted $app'
                else echo '$app is installed but not enabled (enable it in Boomslang > Apps)'; fi"
        done
        ;;
    install)
        need_connection
        swu=${1:-}
        [ -f "$swu" ] || { echo "Usage: bs.sh install <path to update-*.swu>" >&2; exit 1; }
        echo "File: $swu ($(du -h "$swu" | cut -f1))"
        if [ -n "$BS_DRY" ]; then echo "would send it to /useremain/update.swu, unpack, install and reboot"; exit 0; fi
        if [ "$BS_YES" != 1 ]; then
            printf 'Install this on %s and reboot the printer? [y/N] ' "$HOST"
            read -r answer
            [ "$answer" = y ] || [ "$answer" = Y ] || { echo "Cancelled"; exit 1; }
        fi
        remote "cat > /useremain/update.swu && sync" < "$swu"
        echo "Uploaded, installing (the printer reboots when done)..."
        remote ". $CUR/tools.sh > /dev/null 2>&1
            case \"\$KOBRA_MODEL_CODE\" in
                K2P|K3|K3V2) P='U2FsdGVkX19deTfqpXHZnB5GeyQ/dtlbHjkUnwgCi+w=' ;;
                KS1|KS1M) P='U2FsdGVkX1+lG6cHmshPLI/LaQr9cZCjA8HZt6Y8qmbB7riY' ;;
                K3M) P='4DKXtEGStWHpPgZm8Xna9qluzAI8VJzpOsEIgd8brTLiXs8fLSu3vRx8o7fMf4h6' ;;
                *) echo \"Unknown model \$KOBRA_MODEL_CODE\"; exit 1 ;;
            esac
            set -e
            rm -rf /useremain/update_swu
            unzip -P \"\$P\" /useremain/update.swu -d /useremain > /dev/null || { echo 'Wrong package for this printer model'; rm -f /useremain/update.swu; exit 1; }
            rm -f /useremain/update.swu
            if [ -f /useremain/update_swu/setup.tar.gz.md5 ]; then
                [ \"\$(md5sum /useremain/update_swu/setup.tar.gz | cut -d' ' -f1)\" = \"\$(tr -d ' \\n' < /useremain/update_swu/setup.tar.gz.md5)\" ] || { echo 'Package checksum does not match'; exit 1; }
            fi
            tar zxf /useremain/update_swu/setup.tar.gz -C /useremain/update_swu
            chmod +x /useremain/update_swu/update.sh
            sed -i -e 's|rm -rf \${swu_path}/update.swu|echo|' -e 's|rm -f \$USB_PATH/update.swu||' -e 's|reboot|echo|' /useremain/update_swu/update.sh
            /useremain/update_swu/update.sh async
            mkdir -p /useremain/rinkhals
            : > /useremain/rinkhals/.reboot-marker
            sync
            echo 'Installed, rebooting now'
            reboot"
        ;;
    *)
        sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'
        exit 1
        ;;
esac

#!/bin/sh

function log() {
    echo "${*}"
    echo "$(date): ${*}" >> /useremain/rinkhals/rinkhals.log
}

log
log "Starting Boomslang..."

CALLER=$(cat /proc/$PPID/cmdline)
log "Boomslang startup was called from $CALLER ($PPID)"

if [ ! -f /useremain/rinkhals/.version ]; then
    log "Boomslang is installed but no version is selected to start"
    exit 1
fi

if [ -f /mnt/udisk/.enable-rinkhals ] || [ -f /useremain/rinkhals/.enable-rinkhals ]; then
    log "Forcing Boomslang startup with the .enable-rinkhals file"

    rm /mnt/udisk/.disable-rinkhals
    rm /useremain/rinkhals/.disable-rinkhals
fi

if [ ! -f /mnt/udisk/.disable-rinkhals ] && [ ! -f /useremain/rinkhals/.disable-rinkhals ]; then
    RINKHALS_VERSION=$(cat /useremain/rinkhals/.version)
    log "Boomslang version $RINKHALS_VERSION selected"

    if [ ! -d /useremain/rinkhals/$RINKHALS_VERSION ]; then
        log "Boomslang version $RINKHALS_VERSION does not exist"
        exit 1
    fi

    cd /useremain/rinkhals/$RINKHALS_VERSION

    chmod +x ./start.sh
    ./start.sh
fi

if [ -f /mnt/udisk/.disable-rinkhals ] || [ -f /useremain/rinkhals/.disable-rinkhals ]; then
    log "Boomslang startup was stopped with the .disable-rinkhals file, trying to start ADB..."

    adbd &
    exit 1
fi

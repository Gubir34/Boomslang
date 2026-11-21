# The stock screen's look (Settings > Stock screen look in Boomslang; off by default).
#
# Sourced by start.sh, which calls start_stock_screen instead of starting K3SysUi
# itself. With a look chosen, K3SysUi starts with that look's library preloaded
# (build/stock-look/stock_look.c): its style sheet colours become the look's
# (liquid, liquid-light, aero or aero-light).
#
# It is experimental, so it turns itself off: if the stock screen does not stay up
# for STOCK_LOOK_TRIAL seconds, the choice is set back to off and Boomslang starts
# again without it. The look is also off when the choice is not one of the looks,
# or its library is missing. To turn it off by hand:
#   rm /useremain/rinkhals/.stock-ui-look

STOCK_LOOK_FILE=/useremain/rinkhals/.stock-ui-look
STOCK_LOOK_LIB_DIR=/opt/rinkhals/lib
STOCK_LOOK_TRIAL=60

# Sets STOCK_LOOK and STOCK_LOOK_LIB, and succeeds, when a look is chosen and its library is there
stock_look_wanted() {
    STOCK_LOOK=$(cat $STOCK_LOOK_FILE 2> /dev/null | tr -d ' \n\r')
    case "$STOCK_LOOK" in
        liquid|liquid-light|aero|aero-light) ;;
        *) return 1 ;;
    esac
    STOCK_LOOK_LIB=$STOCK_LOOK_LIB_DIR/libboomslang-stock-look-$STOCK_LOOK.so
    [ -f "$STOCK_LOOK_LIB" ]
}

start_stock_screen() {
    if ! stock_look_wanted; then
        ./K3SysUi >> $RINKHALS_LOGS/K3SysUi.log 2>&1 &
        return
    fi

    log "  Stock screen look: $STOCK_LOOK (experimental)"
    LD_PRELOAD=$STOCK_LOOK_LIB ./K3SysUi >> $RINKHALS_LOGS/K3SysUi.log 2>&1 &
    STOCK_SCREEN_PID=$!

    # The watch: if the stock screen ends early, turn the look off and start again
    (
        WAITED=0
        while [ $WAITED -lt $STOCK_LOOK_TRIAL ]; do
            sleep 2
            WAITED=$((WAITED + 2))
            if ! kill -0 $STOCK_SCREEN_PID 2> /dev/null; then
                echo off > $STOCK_LOOK_FILE
                log "/!\ The stock screen stopped ${WAITED}s after starting with the $STOCK_LOOK look: the look is off again, restarting"
                setsid $RINKHALS_ROOT/start.sh > /dev/null 2>&1 < /dev/null &
                exit 0
            fi
        done
    ) &
}

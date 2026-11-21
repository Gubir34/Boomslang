#!/bin/sh
# Builds the stock screen look libraries (stock_look.c), one per look.
#
#   build/stock-look/build.sh                 the printer's (ARMv7, hard float), into the firmware files
#   build/stock-look/build.sh host LOOK OUT   this machine's, for the tests (LOOK: liquid, aero-light, ...)
#
# Needs arm-linux-gnueabihf-gcc for the printer's. No C library is linked: the only
# outside function is dlsym, which the printer's uClibc has in libc, already loaded
# by the stock screen.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
LOOKS="liquid liquid-light aero aero-light"
FLAGS="-shared -fPIC -O2 -nostdlib -fno-stack-protector -fvisibility=hidden -Wall -Wextra -Werror \
       -Wl,--version-script=$HERE/stock_look.map -Wl,--hash-style=both -Wl,-z,defs -Wl,--unresolved-symbols=ignore-all"

define() {    # liquid-light -> -DLOOK_LIQUID_LIGHT
    echo "-DLOOK_$(echo "$1" | tr 'a-z-' 'A-Z_')"
}

if [ "$1" = "host" ]; then
    gcc $FLAGS $(define "$2") -o "$3" "$HERE/stock_look.c"
    exit 0
fi

LIB=$HERE/../../files/3-rinkhals/opt/rinkhals/lib
mkdir -p "$LIB"
rm -f "$LIB/libboomslang-stock-look.so"         # the single-look build before the choices
for LOOK in $LOOKS; do
    OUT=$LIB/libboomslang-stock-look-$LOOK.so
    arm-linux-gnueabihf-gcc $FLAGS $(define $LOOK) -march=armv7-a -mfpu=vfpv4 -mfloat-abi=hard -marm -o "$OUT" "$HERE/stock_look.c"
    arm-linux-gnueabihf-strip --strip-unneeded "$OUT"
    echo "$OUT: $(wc -c < "$OUT") bytes"
done

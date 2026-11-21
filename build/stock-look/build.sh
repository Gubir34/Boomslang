#!/bin/sh
# Builds the stock screen look library (stock_look.c).
#
#   build/stock-look/build.sh            the printer's (ARMv7, hard float), into the firmware files
#   build/stock-look/build.sh host OUT   this machine's, for the tests
#
# Needs arm-linux-gnueabihf-gcc for the printer's. No C library is linked: the only
# outside function is dlsym, which the printer's uClibc has in libc, already loaded
# by the stock screen.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
FLAGS="-shared -fPIC -O2 -nostdlib -fno-stack-protector -fvisibility=hidden -Wall -Wextra -Werror \
       -Wl,--version-script=$HERE/stock_look.map -Wl,--hash-style=both -Wl,-z,defs -Wl,--unresolved-symbols=ignore-all"

if [ "$1" = "host" ]; then
    gcc $FLAGS -o "$2" "$HERE/stock_look.c"
    exit 0
fi

OUT=$HERE/../../files/3-rinkhals/opt/rinkhals/lib/libboomslang-stock-look.so
mkdir -p "$(dirname "$OUT")"
arm-linux-gnueabihf-gcc $FLAGS -march=armv7-a -mfpu=vfpv4 -mfloat-abi=hard -marm -o "$OUT" "$HERE/stock_look.c"
arm-linux-gnueabihf-strip --strip-unneeded "$OUT"
echo "$OUT: $(wc -c < "$OUT") bytes"

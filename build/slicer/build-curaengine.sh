#!/bin/sh
# Builds the slicing engine of the touch UI: CuraEngine 15.04.6, as a static
# ARM (armhf) binary, into files/3-rinkhals/opt/rinkhals/slicer/CuraEngine.
#
# Static, so it runs on the printer's uClibc system without any library from
# it. Needs a Debian or Ubuntu machine with the armhf cross compiler:
#   apt-get install g++-arm-linux-gnueabihf git make
#
#   sh build/slicer/build-curaengine.sh
set -e
TAG=15.04.6
HERE=$(cd "$(dirname "$0")" && pwd)
TARGET=$HERE/../../files/3-rinkhals/opt/rinkhals/slicer/CuraEngine
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

git clone --quiet --depth 1 --branch "$TAG" https://github.com/Ultimaker/CuraEngine "$WORK/CuraEngine"
cd "$WORK/CuraEngine"
make -j"$(nproc)" CXX=arm-linux-gnueabihf-g++ AR=arm-linux-gnueabihf-ar \
    LDFLAGS="-Lbuild/ -lclipper -static -s" \
    CFLAGS="-c -std=c++11 -O2 -march=armv7-a -mfpu=neon-vfpv4 -mfloat-abi=hard -isystem libs -DVERSION=\\\"$TAG\\\" -w"
cp build/CuraEngine "$TARGET"
chmod 755 "$TARGET"
echo "$TARGET: $(wc -c < "$TARGET") bytes"

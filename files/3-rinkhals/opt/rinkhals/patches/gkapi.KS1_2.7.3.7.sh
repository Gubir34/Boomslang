#!/bin/sh

# This script was automatically generated, don't modify it directly
# Before MD5: b677f599ac5f20ea0e8f7c1c4c648686
# After MD5: 6d84d536cfd09790700f3749cc9aca34

TARGET=$1

MD5=$(md5sum $TARGET | awk '{print $1}')
if [ "$MD5" = "6d84d536cfd09790700f3749cc9aca34" ]; then
    echo $TARGET is already patched, skipping...
    exit 0
fi
if [ "$MD5" != "b677f599ac5f20ea0e8f7c1c4c648686" ]; then
    echo $TARGET hash does not match, skipping patch...
    exit 1
fi

PATCH_FILE=/tmp/patch-$RANDOM.bin
echo '674=' | base64 -d > $PATCH_FILE

dd if=$PATCH_FILE skip=0 ibs=1 of=$TARGET seek=6813976 obs=1 count=2 conv=notrunc # 0x67f918 / 0x68f918 > 0xebbe

rm $PATCH_FILE

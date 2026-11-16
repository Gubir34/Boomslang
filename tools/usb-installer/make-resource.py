#!/usr/bin/env python3
"""Make rsrc_windows_amd64.syso: the program icon of boomslang-usb.exe.

Go links any *.syso file named for the target into the program, so the
Windows build shows the Boomslang icon in Explorer, the taskbar and the title
bar without any build tool. The result is committed; run this again only when
icon.png changes:

    python3 make-resource.py            (needs Pillow)

The file is a COFF object with one .rsrc section: a resource tree holding
RT_ICON images (PNG for 256 px, 32 bit bitmaps for the small sizes, which is
what every Windows version understands) and one RT_GROUP_ICON listing them.
"""
import io
import struct
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SIZES = (16, 24, 32, 48, 256)
RT_ICON, RT_GROUP_ICON, LANG_EN_US = 3, 14, 0x0409


def dib(image):
    """A 32 bit icon bitmap: header, BGRA rows bottom to top, then an empty AND mask."""
    w, h = image.size
    header = struct.pack('<IiiHHIIiiII', 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    rows = []
    pixels = image.convert('RGBA').load()
    for y in range(h - 1, -1, -1):
        rows.append(b''.join(struct.pack('<BBBB', pixels[x, y][2], pixels[x, y][1], pixels[x, y][0], pixels[x, y][3])
                             for x in range(w)))
    mask = b'\x00' * (((w + 31) // 32) * 4 * h)
    return header + b''.join(rows) + mask


def images():
    source = Image.open(HERE.parent.parent / 'icon.png').convert('RGBA')
    out = []
    for size in SIZES:
        scaled = source.resize((size, size), Image.LANCZOS)
        if size >= 256:
            buffer = io.BytesIO()
            scaled.save(buffer, 'PNG', optimize=True)
            out.append((size, buffer.getvalue()))
        else:
            out.append((size, dib(scaled)))
    return out


def align(value, to=4):
    return (value + to - 1) // to * to


def build():
    icons = images()
    # --- the resource tree: type -> name (id) -> language -> data entry --------
    #   root                  : RT_ICON, RT_GROUP_ICON
    #   RT_ICON level         : ids 1..n
    #   RT_GROUP_ICON level   : id 1
    #   language level        : one directory per icon and one for the group
    # The directories come first, so every offset is known before the data.
    n = len(icons)
    dir_size = lambda entries: 16 + 8 * entries
    root_at = 0
    icon_ids_at = root_at + dir_size(2)
    group_ids_at = icon_ids_at + dir_size(n)
    lang_at = [group_ids_at + dir_size(1) + i * dir_size(1) for i in range(n + 1)]   # icons, then the group
    entries_at = lang_at[-1] + dir_size(1)               # the data entries, 16 bytes each
    entry_at = [entries_at + i * 16 for i in range(n + 1)]
    data_at = align(entries_at + (n + 1) * 16)

    group = struct.pack('<HHH', 0, 1, n)
    blobs, positions, cursor = [], [], data_at
    for i, (size, data) in enumerate(icons):
        positions.append(cursor)
        blobs.append(data)
        cursor = align(cursor + len(data))
        edge = 0 if size >= 256 else size                # 0 means 256 in an icon directory
        group += struct.pack('<BBBBHHIH', edge, edge, 0, 0, 1, 32, len(data), i + 1)
    positions.append(cursor)                             # the group icon data
    blobs.append(group)
    cursor = align(cursor + len(group))

    section = bytearray(cursor)

    def directory(at, ids):
        struct.pack_into('<IIHHHH', section, at, 0, 0, 0, 0, 0, len(ids))
        for k, (ident, target, is_directory) in enumerate(ids):
            struct.pack_into('<II', section, at + 16 + 8 * k, ident, target | (0x80000000 if is_directory else 0))

    directory(root_at, [(RT_ICON, icon_ids_at, True), (RT_GROUP_ICON, group_ids_at, True)])
    directory(icon_ids_at, [(i + 1, lang_at[i], True) for i in range(n)])
    directory(group_ids_at, [(1, lang_at[n], True)])
    relocations = []
    for i in range(n + 1):
        directory(lang_at[i], [(LANG_EN_US, entry_at[i], False)])
        # data entry: the offset of the data in the section (the linker adds
        # the section's address, see the relocation below), size, code page
        struct.pack_into('<IIII', section, entry_at[i], positions[i], len(blobs[i]), 0, 0)
        relocations.append(entry_at[i])
        section[positions[i]:positions[i] + len(blobs[i])] = blobs[i]

    # --- the COFF object ------------------------------------------------------
    header_size, section_header = 20, 40
    raw_at = header_size + section_header
    reloc_at = raw_at + len(section)
    symbols_at = reloc_at + 10 * len(relocations)
    coff = struct.pack('<HHIIIHH', 0x8664, 1, 0, symbols_at, 1, 0, 0)
    coff += struct.pack('<8sIIIIIIHHI', b'.rsrc', 0, 0, len(section), raw_at, reloc_at, 0, len(relocations), 0, 0x40000040)
    coff += bytes(section)
    for at in relocations:
        coff += struct.pack('<IIH', at, 0, 0x0003)          # IMAGE_REL_AMD64_ADDR32NB against symbol 0
    coff += struct.pack('<8sIhHBB', b'$R000000', 0, 1, 0, 3, 0)   # a static symbol at the start of section 1
    coff += struct.pack('<I', 4)                             # no string table
    return coff


if __name__ == '__main__':
    out = HERE / 'rsrc_windows_amd64.syso'
    out.write_bytes(build())
    print(f'{out.name}: {out.stat().st_size} bytes, icons {SIZES}')

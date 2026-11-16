"""Unpack the setup archive of an update package (an extracted .swu).

A package holds update_swu/ with one of:

  setup.tar.gz  standard package; the stock USB updater reads it too
  setup.tar.xz  compressed package, a smaller download for the OTA of a
                running Boomslang. The printer's own busybox has no xz, so it
                is decompressed here with Python's lzma (part of Boomslang's
                Python) and streamed into tar, without a full .tar on disk.

and optionally <archive>.md5. The touch UI imports this; the web portal and
build/bs.sh run it:

  python swu_setup.py /useremain/update_swu

This file runs from the Boomslang that is installed, not from the package
being installed, so a compressed package can only be installed by a version
that has this file. Older versions only see the standard packages, which is
why releases carry both.
"""
import hashlib
import os
import subprocess
import sys

ARCHIVES = ('setup.tar.xz', 'setup.tar.gz')   # preferred first
CHUNK = 256 * 1024
OUTPUT_CHUNK = 1024 * 1024
# The build caps the xz dictionary at 16 MiB (build/tools.sh prepare_txz).
# A file asking for much more is not ours, or would starve the printer.
XZ_MEMLIMIT = 64 * 1024 * 1024


class SetupError(Exception):
    """A message that is fine to log and show."""


def md5_of(path):
    md5 = hashlib.md5()
    with open(path, 'rb') as f:
        while chunk := f.read(CHUNK):
            md5.update(chunk)
    return md5.hexdigest()


def find_archive(directory):
    for name in ARCHIVES:
        if os.path.isfile(os.path.join(directory, name)):
            return name
    return None


def verify(directory, name):
    md5_path = os.path.join(directory, name + '.md5')
    if not os.path.isfile(md5_path):
        return
    with open(md5_path) as f:
        words = f.read().split()
    expected = words[0].lower() if words else ''
    actual = md5_of(os.path.join(directory, name))
    if actual != expected:
        raise SetupError(f'{name} md5 does not match (got {actual}, want {expected})')


def _unpack_xz(path, directory, tar):
    import lzma
    process = subprocess.Popen([tar, '-xf', '-', '-C', directory], stdin=subprocess.PIPE)
    error = None
    try:
        decompressor = lzma.LZMADecompressor(memlimit=XZ_MEMLIMIT)
        with open(path, 'rb') as f:
            while not decompressor.eof:
                # Bounded output per step: a highly compressible part of the
                # archive must not turn into one huge buffer in memory
                if decompressor.needs_input:
                    chunk = f.read(CHUNK)
                    if not chunk:
                        break
                    data = decompressor.decompress(chunk, max_length=OUTPUT_CHUNK)
                else:
                    data = decompressor.decompress(b'', max_length=OUTPUT_CHUNK)
                if data:
                    process.stdin.write(data)
        if not decompressor.eof:
            error = SetupError(f'{os.path.basename(path)} is incomplete')
    except lzma.LZMAError as e:
        error = SetupError(f'{os.path.basename(path)} could not be decompressed: {e}')
    except BrokenPipeError:
        pass   # tar stopped early; its exit status says why
    finally:
        try:
            process.stdin.close()
        except BrokenPipeError:
            pass
        status = process.wait()
    if error:
        raise error
    if status != 0:
        raise SetupError(f'tar failed with status {status}')


def unpack_setup(directory, tar='tar'):
    """Check and unpack the setup archive into directory. Returns its name."""
    name = find_archive(directory)
    if not name:
        raise SetupError('The package has no setup archive')
    verify(directory, name)
    path = os.path.join(directory, name)
    if name.endswith('.xz'):
        _unpack_xz(path, directory, tar)
        os.remove(path)   # free the space before update.sh copies the files
    else:
        status = subprocess.run([tar, '-xzf', path, '-C', directory]).returncode
        if status != 0:
            raise SetupError(f'tar failed with status {status}')
    return name


def main(argv):
    if len(argv) != 2:
        print('Usage: swu_setup.py <update_swu directory>', file=sys.stderr)
        return 2
    try:
        name = unpack_setup(argv[1])
    except (SetupError, OSError) as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f'Unpacked {name}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

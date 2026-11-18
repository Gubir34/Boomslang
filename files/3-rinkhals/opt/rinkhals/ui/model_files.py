"""3D model files (STL, 3MF) for the touch UI, without a screen, so they are tested on a PC.

- stl_info / threemf_info: how big a model is, how many triangles or objects,
  and for a 3MF that was already sliced (Orca, Anycubic Slicer Next, Bambu
  Studio ...), its plates with their print time, filament and G-code
- fits: whether a model fits the printer's build volume
- sliced_for_problem: whether a sliced 3MF was made for this very printer.
  G-code drives the hardware: a file sliced for another printer can crash the
  nozzle into the bed or heat the wrong way, so anything else is refused
- extract_plate: a plate's G-code copied into the printer's files, with the
  same care as browser_tools.download_print_file (not while printing, enough
  free space, complete or nothing)

Build volumes and model names are the ones of OrcaSlicer's Anycubic printer
profiles (resources/profiles/Anycubic/machine, "printable_area" and
"printable_height"), which is also what the slicers write into a 3MF.
"""
import json
import os
import re
import struct
import zipfile
from xml.etree import ElementTree

import browser_tools

# model code: (the slicers' printer model name, (width, depth) mm, height mm)
PRINTERS = {
    'K2P': ('Anycubic Kobra 2 Pro', (220, 220), 250),
    'K3': ('Anycubic Kobra 3', (255, 255), 260),
    'K3V2': ('Anycubic Kobra 3 V2', (255, 255), 260),
    'K3M': ('Anycubic Kobra 3 Max', (426, 420), 501),
    'KS1': ('Anycubic Kobra S1', (250, 250), 250),
    'KS1M': ('Anycubic Kobra S1 Max', (350, 350), 350),
}

MODELS_DIR = '/useremain/home/rinkhals/models'
MODEL_EXTENSIONS = ('.stl', '.3mf')
MAX_MODEL_BYTES = 100 * 1024 * 1024        # models downloaded or read on the printer
MAX_TRIANGLES = 2_000_000                  # read for the size; a bigger mesh is not looked at further


class ModelError(Exception):
    """A reason, fine to show on the touch screen, why a model can't be used."""


def model_kind(url_or_path):
    """'stl', 'gcode.3mf', '3mf' or None, from the name."""
    from urllib.parse import unquote, urlparse
    path = unquote(urlparse(url_or_path or '').path or url_or_path or '').lower()
    if path.endswith('.gcode.3mf'):
        return 'gcode.3mf'
    if path.endswith('.3mf'):
        return '3mf'
    if path.endswith('.stl'):
        return 'stl'
    return None


def _size_of(bounds):
    (x0, y0, z0), (x1, y1, z1) = bounds
    return (round(x1 - x0, 1), round(y1 - y0, 1), round(z1 - z0, 1))


def _grow(bounds, x, y, z):
    if bounds is None:
        return [[x, y, z], [x, y, z]]
    lo, hi = bounds
    lo[0], lo[1], lo[2] = min(lo[0], x), min(lo[1], y), min(lo[2], z)
    hi[0], hi[1], hi[2] = max(hi[0], x), max(hi[1], y), max(hi[2], z)
    return bounds


# --- STL --------------------------------------------------------------------------------------

def stl_info(path):
    """{'kind': 'stl', 'triangles', 'size': (x, y, z) mm}. Binary and ASCII STL."""
    size = os.path.getsize(path)
    if size > MAX_MODEL_BYTES:
        raise ModelError(f'The model is too big to open on the printer ({size // 1048576} MB).')
    with open(path, 'rb') as f:
        head = f.read(84)
        if len(head) == 84:
            count = struct.unpack('<I', head[80:84])[0]
            # Binary when the triangle count matches the size. Some programs add bytes
            # at the end, and some binary files start with "solid" too: an ASCII STL
            # has "facet" near the start, a binary one does not.
            ascii_like = head.lstrip().startswith(b'solid') and b'facet' in head + f.read(200)
            if 84 + count * 50 <= size and not ascii_like and count:
                f.seek(84)
                return _binary_stl(f, count)
    return _ascii_stl(path)


def _binary_stl(f, count):
    if count > MAX_TRIANGLES:
        raise ModelError(f'The model has too many triangles to open on the printer ({count:,}).')
    bounds = None
    unpack = struct.Struct('<12x9f2x').unpack
    for _ in range(count):
        record = f.read(50)
        if len(record) < 50:
            raise ModelError('The STL file is cut off.')
        v = unpack(record)
        for i in (0, 3, 6):
            bounds = _grow(bounds, v[i], v[i + 1], v[i + 2])
    if bounds is None:
        raise ModelError('The STL file has no triangles.')
    return {'kind': 'stl', 'triangles': count, 'size': _size_of(bounds)}


_VERTEX = re.compile(rb'vertex\s+(\S+)\s+(\S+)\s+(\S+)')


def _ascii_stl(path):
    bounds, vertices = None, 0
    with open(path, 'rb') as f:
        for line in f:
            m = _VERTEX.search(line)
            if not m:
                continue
            try:
                x, y, z = float(m.group(1)), float(m.group(2)), float(m.group(3))
            except ValueError:
                raise ModelError('The STL file has a broken number in it.')
            bounds = _grow(bounds, x, y, z)
            vertices += 1
            if vertices > MAX_TRIANGLES * 3:
                raise ModelError('The model has too many triangles to open on the printer.')
    if bounds is None:
        raise ModelError('This is not an STL model.')
    return {'kind': 'stl', 'triangles': vertices // 3, 'size': _size_of(bounds)}


# --- 3MF ---------------------------------------------------------------------------------------

def _settings(archive):
    """The slicer's project settings (Orca, Bambu, Anycubic write Metadata/project_settings.config as JSON)."""
    for name in ('Metadata/project_settings.config', 'Metadata/Slic3r_PE.config'):
        if name in archive.namelist():
            raw = archive.read(name)[:4 * 1024 * 1024]
            try:
                return json.loads(raw.decode('utf-8', 'replace'))
            except ValueError:
                # PrusaSlicer's "; key = value" lines
                out = {}
                for line in raw.decode('utf-8', 'replace').splitlines():
                    m = re.match(r'^;\s*([\w-]+)\s*=\s*(.*)$', line)
                    if m:
                        out[m.group(1)] = m.group(2).strip()
                return out
    return {}


def _plates(archive):
    """Sliced plates: [{'index', 'gcode', 'time' s, 'weight' g, 'filament'}]."""
    gcodes = sorted((n for n in archive.namelist() if re.fullmatch(r'Metadata/plate_\d+\.gcode', n)),
                    key=lambda n: int(re.search(r'(\d+)', n).group(1)))
    info = {}
    if 'Metadata/slice_info.config' in archive.namelist():
        try:
            root = ElementTree.fromstring(archive.read('Metadata/slice_info.config')[:1024 * 1024])
            for plate in root.iter('plate'):
                meta = {m.get('key'): m.get('value') for m in plate.findall('metadata')}
                index = int(meta.get('index') or 0)
                filaments = [f.get('type') for f in plate.findall('filament') if f.get('type')]
                info[index] = {'time': _number(meta.get('prediction')), 'weight': _number(meta.get('weight')),
                               'filament': ', '.join(dict.fromkeys(filaments))}
        except ElementTree.ParseError:
            pass
    plates = []
    for name in gcodes:
        index = int(re.search(r'(\d+)', name).group(1))
        plate = {'index': index, 'gcode': name, 'time': None, 'weight': None, 'filament': ''}
        plate.update(info.get(index, {}))
        plates.append(plate)
    return plates


def _number(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _mesh_bounds(archive):
    """Size of the meshes of an unsliced 3MF (3D/3dmodel.model and the files it points to)."""
    bounds, objects, triangles = None, 0, 0
    names = [n for n in archive.namelist() if n.lower().endswith('.model')]
    for name in names:
        try:
            with archive.open(name) as f:
                for _, element in ElementTree.iterparse(f):
                    tag = element.tag.rsplit('}', 1)[-1]
                    if tag == 'vertex':
                        bounds = _grow(bounds, float(element.get('x', 0)), float(element.get('y', 0)),
                                       float(element.get('z', 0)))
                    elif tag == 'triangle':
                        triangles += 1
                    elif tag == 'object' and element.find('{*}mesh') is not None:
                        objects += 1
                    if tag in ('vertex', 'triangle'):
                        element.clear()
                    if triangles > MAX_TRIANGLES:
                        raise ModelError('The model has too many triangles to open on the printer.')
        except (ElementTree.ParseError, ValueError):
            raise ModelError('The 3MF model is broken.')
    return bounds, objects, triangles


def threemf_info(path):
    """{'kind', 'sliced', 'printer_model', 'plates', 'size', 'objects', 'triangles'}."""
    if os.path.getsize(path) > MAX_MODEL_BYTES * 3:
        raise ModelError('The 3MF file is too big to open on the printer.')
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        raise ModelError('This is not a 3MF file.')
    with archive:
        settings = _settings(archive)
        plates = _plates(archive)
        model = settings.get('printer_model') or ''
        info = {'kind': '3mf', 'sliced': bool(plates), 'printer_model': str(model), 'plates': plates,
                'size': None, 'objects': 0, 'triangles': 0}
        if not plates:
            bounds, info['objects'], info['triangles'] = _mesh_bounds(archive)
            if bounds is None:
                raise ModelError('The 3MF file has no model in it.')
            info['size'] = _size_of(bounds)
        return info


def model_file_name(url, existing=()):
    """A safe name for a downloaded model, keeping .stl / .3mf / .gcode.3mf, never overwriting."""
    from urllib.parse import unquote, urlparse
    name = os.path.basename(unquote(urlparse(url or '').path)) or 'model.stl'
    kind = model_kind(name) or 'stl'
    ext = '.' + kind
    stem = name[:-len(ext)] if name.lower().endswith(ext) else os.path.splitext(name)[0]
    stem = re.sub(r'[^\w\- .]', '_', stem).strip(' .')[:80] or 'model'
    candidate, n = stem + ext, 2
    while candidate in set(existing):
        candidate = f'{stem} ({n}){ext}'
        n += 1
    return candidate


def model_info(path):
    kind = model_kind(path)
    if kind == 'stl':
        return stl_info(path)
    if kind in ('3mf', 'gcode.3mf'):
        return threemf_info(path)
    raise ModelError('Only STL and 3MF models can be opened.')


# --- the printer ---------------------------------------------------------------------------------

def fits(size, model_code):
    """(True, '') or (False, why). size: (x, y, z) mm."""
    printer = PRINTERS.get((model_code or '').upper())
    if not printer or not size:
        return False, 'The size of this printer is not known.'
    _, (width, depth), height = printer
    x, y, z = size
    # turned by 90 degrees it may fit where it does not as it is
    if z > height:
        return False, f'It is {z:g} mm tall; the printer prints up to {height} mm.'
    if (x <= width and y <= depth) or (y <= width and x <= depth):
        return True, ''
    return False, f'It is {x:g} x {y:g} mm; the bed is {width} x {depth} mm.'


def sliced_for_problem(info, model_code):
    """None when a sliced 3MF was made for this printer, else why it must not be printed here."""
    printer = PRINTERS.get((model_code or '').upper())
    if not printer:
        return 'This printer model is not known, so no sliced file can be checked for it.'
    made_for = (info.get('printer_model') or '').strip()
    if not made_for:
        return 'The file does not say which printer it was sliced for, so it is not printed here.'
    if made_for.lower() != printer[0].lower():
        return f'It was sliced for the {made_for}, not for this {printer[0]}. Slice it again for this printer.'
    return None


def extract_plate(path, plate, model_code, folder=None, printing=lambda: False, free=browser_tools.free_bytes):
    """Copy a sliced plate's G-code into the printer's files. Returns the new file's path.

    Refused unless the 3MF was sliced for this printer, never while printing,
    and only with enough free space; written to a hidden .part file and
    renamed at the end, so the printer never lists half a file.
    """
    folder = folder or browser_tools.GCODE_DIR
    if printing():
        raise ModelError('The printer is printing. Copy the file when it is done.')
    info = threemf_info(path)
    problem = sliced_for_problem(info, model_code)
    if problem:
        raise ModelError(problem)
    chosen = next((p for p in info['plates'] if p['index'] == plate), None)
    if not chosen:
        raise ModelError(f'The file has no sliced plate {plate}.')
    stem = os.path.basename(path)
    for suffix in ('.gcode.3mf', '.3mf'):
        if stem.lower().endswith(suffix):
            stem = stem[:-len(suffix)]
    name = browser_tools.print_file_name(f'file:///{stem}-plate{plate}.gcode', os.listdir(folder))
    temporary = os.path.join(folder, f'.{name}.part')
    try:
        with zipfile.ZipFile(path) as archive:
            member = archive.getinfo(chosen['gcode'])
            if member.file_size > free(folder) - browser_tools.FREE_MARGIN_BYTES:
                raise ModelError('There is not enough free space on the printer for this file.')
            with archive.open(member) as source, open(temporary, 'wb') as target:
                while True:
                    chunk = source.read(65536)
                    if not chunk:
                        break
                    target.write(chunk)
        if printing():
            raise ModelError('A print started while copying; the file was not kept.')
        destination = os.path.join(folder, name)
        os.replace(temporary, destination)
        return destination
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def describe(info, model_code):
    """Lines for the screen about a model."""
    lines = []
    if info.get('sliced'):
        lines.append(f'Sliced for: {info.get("printer_model") or "unknown printer"}')
        for plate in info['plates']:
            parts = [f'Plate {plate["index"]}']
            if plate.get('time'):
                minutes = int(plate['time'] // 60)
                parts.append(f'{minutes // 60} h {minutes % 60} min' if minutes >= 60 else f'{minutes} min')
            if plate.get('weight'):
                parts.append(f'{plate["weight"]:g} g')
            if plate.get('filament'):
                parts.append(plate['filament'])
            lines.append(' · '.join(parts))
        return lines
    x, y, z = info['size']
    lines.append(f'Size: {x:g} x {y:g} x {z:g} mm')
    if info.get('triangles'):
        count = info['triangles']
        lines.append(f'{count:,} triangle{"" if count == 1 else "s"}' + (f' in {info["objects"]} objects' if info.get('objects', 0) > 1 else ''))
    ok, why = fits(info['size'], model_code)
    lines.append('It fits on this printer.' if ok else f'Too big for this printer: {why}')
    return lines

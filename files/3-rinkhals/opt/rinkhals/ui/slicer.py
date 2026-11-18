"""Slicing STL and 3MF models on the printer, for the printer, with CuraEngine.

The engine is CuraEngine 15.04 (AGPL-3.0, see opt/rinkhals/slicer/README.md),
a small C++ program built as a static ARM binary; this file is what tells it
what to do and checks what it made. No screen here, so it is tested on a PC.

    slice_model(model_path, model_code)  ->  the G-code file in the printer's files

One profile for now: PLA, 0.2 mm layers, a 0.4 mm nozzle, conservative
speeds. Temperatures, retraction and the start and end of a print are the
ones of OrcaSlicer's Anycubic profiles for each printer (Anycubic PLA,
0.4 nozzle), so a print starts the way it does from Anycubic's own slicer:
the Kobra 3 and S1 families with Anycubic's G9111 macro (heating, homing,
levelling, purge), the Kobra 2 Pro with the usual heat, home and purge line.

Nothing reaches the printer unless check_gcode passes: every move inside
the build volume, extrusion in the mode the file was written for, safe
temperatures. G-code drives the hardware; a wrong file must never print.
"""
import os
import re
import struct
import subprocess
import tempfile
import time
import zipfile
from xml.etree import ElementTree

import browser_tools
import model_files

ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'slicer', 'CuraEngine')
SLICE_TIMEOUT = 45 * 60          # seconds: a big model on the printer's CPU takes a while
EDGE_MARGIN = 6.0                # mm kept free around the model: the skirt is 3 mm away
TOP_MARGIN = 6.0                 # mm above the model: the engine lifts 5 mm when it is done
MIN_FREE_MEMORY_KB = 60 * 1024   # the engine holds the whole sliced model in memory
MAX_NOZZLE_TEMP = 260
MAX_BED_TEMP = 110
END_MARK = '; --- end of print ---'

# PLA, 0.4 mm nozzle (OrcaSlicer: Anycubic PLA @<printer> 0.4 nozzle, and the printer profile)
#           nozzle, first layer, bed, retraction mm, retraction mm/s, pressure advance K
PROFILES = {
    'K2P': dict(nozzle=200, first=220, bed=60, retract=1.5, retract_speed=30, k=0.07),
    'K3': dict(nozzle=210, first=220, bed=60, retract=1.0, retract_speed=60, k=0.051),
    'K3V2': dict(nozzle=210, first=220, bed=60, retract=1.0, retract_speed=60, k=0.051),
    'K3M': dict(nozzle=210, first=220, bed=65, retract=0.8, retract_speed=30, k=None),
    'KS1': dict(nozzle=205, first=215, bed=55, retract=0.8, retract_speed=40, k=None),
    'KS1M': dict(nozzle=220, first=230, bed=60, retract=0.4, retract_speed=30, k=None),
}
# where the head is parked at the end (OrcaSlicer's end G-code of each printer)
PARK = {'K2P': 'G1 X5 Y209 F6000', 'K3': 'G1 X250 Y220 F12000', 'K3V2': 'G1 X250 Y220 F12000',
        'K3M': 'G1 X420 Y420 F12000', 'KS1': 'G1 X44 Y270 F12000', 'KS1M': ''}
G9111_PRINTERS = ('K3', 'K3V2', 'K3M', 'KS1', 'KS1M')


class SliceError(Exception):
    """A reason, fine to show on the touch screen, why a model was not sliced."""


def start_gcode(model_code, profile):
    if model_code in G9111_PRINTERS:
        lines = [f'G9111 bedTemp={profile["bed"]} extruderTemp={profile["first"]} ; Anycubic: heat, home, level, purge',
                 'M117']
    else:
        lines = ['G90', 'M83', f'M140 S{profile["bed"]}', f'M190 S{profile["bed"]}',
                 f'M104 S{profile["first"]}', f'M109 S{profile["first"]}', 'G28', 'G1 Z0.28',
                 'G92 E0', 'G1 Y226 F1800', 'G1 X180 E25 F500 ; purge line', 'G92 E0', 'G1 E-0.2 F500',
                 'G1 X181 F4000', 'M117']
    if profile.get('k'):
        lines.append(f'M900 K{profile["k"]}')
    # The engine writes absolute extrusion; the start may have left relative mode on.
    lines += ['M82 ; absolute extrusion, as this file is written', 'G92 E0']
    return '\n'.join(lines) + '\n'


def end_gcode(model_code):
    lines = [END_MARK, 'M400', 'G92 E0', 'G1 E-2 F2400']
    if PARK.get(model_code):
        lines.append(PARK[model_code] + ' ; present the print')
    lines += ['M140 S0', 'M104 S0', 'M107', 'M84']
    return '\n'.join(lines) + '\n'


def engine_settings(model_code, profile):
    """The engine's settings (lengths in micrometres, speeds in mm/s)."""
    _, (width, depth), _ = model_files.PRINTERS[model_code]
    width_um = 420
    return {
        'nozzleSize': 400, 'layerThickness': 200, 'initialLayerThickness': 200,
        'filamentDiameter': 1750, 'filamentFlow': 100,
        'extrusionWidth': width_um, 'layer0extrusionWidth': 500,
        'insetCount': 3, 'downSkinCount': 4, 'upSkinCount': 5,
        'sparseInfillLineDistance': width_um * 100 // 15,         # 15 % infill
        'infillOverlap': 15,
        'skirtDistance': 3000, 'skirtLineCount': 2, 'skirtMinLength': 0,
        'initialSpeedupLayers': 3, 'initialLayerSpeed': 25,
        'printSpeed': 60, 'inset0Speed': 40, 'insetXSpeed': 60, 'infillSpeed': 80, 'skinSpeed': 50,
        'moveSpeed': 150,
        'retractionAmount': int(profile['retract'] * 1000), 'retractionSpeed': profile['retract_speed'],
        'retractionMinimalDistance': 1500, 'retractionZHop': 0,
        'fanFullOnLayerNr': 2, 'fanSpeedMin': 100, 'fanSpeedMax': 100,
        'minimalLayerTime': 6, 'minimalFeedrate': 10,
        'supportAngle': -1,                                      # no supports in this first profile
        'posx': int(width * 1000 / 2), 'posy': int(depth * 1000 / 2), 'autoCenter': 1,
        'gcodeFlavor': 0,                                        # RepRap / Klipper: G1 E in mm
    }


# --- 3MF -> STL ------------------------------------------------------------------------------

def _matrix(text):
    """A 3MF transform "m00 m01 m02 m10 m11 m12 m20 m21 m22 m30 m31 m32" -> function (x, y, z) -> (x, y, z)."""
    if not text:
        return lambda x, y, z: (x, y, z)
    m = [float(v) for v in text.split()]
    if len(m) != 12:
        raise model_files.ModelError('The 3MF model has a broken transform.')
    return lambda x, y, z: (x * m[0] + y * m[3] + z * m[6] + m[9],
                            x * m[1] + y * m[4] + z * m[7] + m[10],
                            x * m[2] + y * m[5] + z * m[8] + m[11])


def _compose(outer, inner):
    return lambda x, y, z: outer(*inner(x, y, z))


def threemf_to_stl(path, target):
    """Write the build of a 3MF (its objects where the build puts them) as a binary STL. Returns the triangle count."""
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        raise model_files.ModelError('This is not a 3MF file.')
    objects = {}           # (file, id) -> {'mesh': (vertices, triangles) or None, 'components': [(file, id, transform)]}
    main = '3D/3dmodel.model'
    with archive:
        names = [n for n in archive.namelist() if n.lower().endswith('.model')]
        if main not in names:
            raise model_files.ModelError('The 3MF file has no model in it.')
        builds = []
        for name in names:
            try:
                root = ElementTree.fromstring(archive.read(name))
            except ElementTree.ParseError:
                raise model_files.ModelError('The 3MF model is broken.')
            for obj in root.iter():
                if obj.tag.rsplit('}', 1)[-1] != 'object':
                    continue
                entry = {'mesh': None, 'components': []}
                mesh = next((c for c in obj if c.tag.endswith('mesh')), None)
                if mesh is not None:
                    vertices = [(float(v.get('x')), float(v.get('y')), float(v.get('z')))
                                for v in mesh.iter() if v.tag.endswith('}vertex') or v.tag == 'vertex']
                    triangles = [(int(t.get('v1')), int(t.get('v2')), int(t.get('v3')))
                                 for t in mesh.iter() if t.tag.endswith('}triangle') or t.tag == 'triangle']
                    entry['mesh'] = (vertices, triangles)
                for comp in obj.iter():
                    if comp.tag.endswith('}component') or comp.tag == 'component':
                        ref = next((v for k, v in comp.attrib.items() if k.endswith('path')), None)
                        entry['components'].append(((ref or '/' + name).lstrip('/'), comp.get('objectid'),
                                                    comp.get('transform')))
                objects[(name, obj.get('id'))] = entry
            if name == main:
                builds = [(i.get('objectid'), i.get('transform')) for i in root.iter()
                          if i.tag.endswith('}item') or i.tag == 'item']
    if not builds:
        raise model_files.ModelError('The 3MF file has nothing on its build plate.')

    out = []

    def emit(key, transform, depth=0):
        if depth > 4 or key not in objects:
            return
        entry = objects[key]
        if entry['mesh']:
            vertices, triangles = entry['mesh']
            for a, b, c in triangles:
                out.append((transform(*vertices[a]), transform(*vertices[b]), transform(*vertices[c])))
                if len(out) > model_files.MAX_TRIANGLES:
                    raise model_files.ModelError('The model has too many triangles to slice on the printer.')
        for file, oid, comp_transform in entry['components']:
            emit((file, oid), _compose(transform, _matrix(comp_transform)), depth + 1)

    for oid, transform in builds:
        emit((main, oid), _matrix(transform))
    if not out:
        raise model_files.ModelError('The 3MF file has no triangles to slice.')
    with open(target, 'wb') as f:
        f.write(b'Boomslang 3MF build'.ljust(80, b' '))
        f.write(struct.pack('<I', len(out)))
        pack = struct.Struct('<12f2x').pack
        for (a, b, c) in out:
            f.write(pack(0, 0, 0, *a, *b, *c))
    return len(out)


# --- checking what the engine made ---------------------------------------------------------------

_WORD = re.compile(r'([GMXYZEFS])(-?\d+(?:\.\d+)?)')


def check_gcode(path, model_code):
    """None when the G-code is safe for this printer, else what is wrong.

    Checked between the start and the end code (those are Anycubic's own):
    every X, Y inside the bed, Z above 0 and below the top, absolute
    extrusion set before the first extrusion and never switched off,
    nozzle and bed temperatures in a safe range, and at least one layer.
    """
    _, (width, depth), height = model_files.PRINTERS[model_code]
    seen_absolute = False
    layers = 0
    body = False
    extruded = False
    tolerance = 0.01
    with open(path, 'r', errors='replace') as f:
        for number, raw in enumerate(f, 1):
            line = raw.split(';', 1)[0].strip()
            if raw.startswith(';LAYER:'):
                layers += 1
                body = True
            if raw.startswith(END_MARK):
                break
            if not line:
                continue
            words = dict(_WORD.findall(line))
            command = line.split()[0].upper()
            if command == 'M82':
                seen_absolute = True
            elif command == 'M83' and seen_absolute:
                return f'Line {number}: relative extrusion after the start.'
            elif command in ('M104', 'M109') and 'S' in words and float(words['S']) > MAX_NOZZLE_TEMP:
                return f'Line {number}: nozzle temperature {words["S"]} is too high.'
            elif command in ('M140', 'M190') and 'S' in words and float(words['S']) > MAX_BED_TEMP:
                return f'Line {number}: bed temperature {words["S"]} is too high.'
            if not body or command not in ('G0', 'G1'):
                continue
            if 'E' in words and command == 'G1' and 'X' in words:
                if not seen_absolute:
                    return f'Line {number}: extrusion before absolute extrusion was set.'
                extruded = True
            if 'X' in words and not -tolerance <= float(words['X']) <= width + tolerance:
                return f'Line {number}: X {words["X"]} is outside the bed (0 to {width}).'
            if 'Y' in words and not -tolerance <= float(words['Y']) <= depth + tolerance:
                return f'Line {number}: Y {words["Y"]} is outside the bed (0 to {depth}).'
            if 'Z' in words and not 0 < float(words['Z']) <= height:
                return f'Line {number}: Z {words["Z"]} is outside the printer (0 to {height}).'
    if not layers or not extruded:
        return 'The engine made no layers to print.'
    return None


def _first_layer_done(path, profile):
    """After the first layer: the printing temperature (the first layer is printed hotter)."""
    temporary = path + '.temp'
    with open(path, 'r', errors='replace') as source, open(temporary, 'w') as target:
        for line in source:
            target.write(line)
            if line.startswith(';LAYER:1') and line.strip() == ';LAYER:1':
                target.write(f'M104 S{profile["nozzle"]} ; printing temperature from the second layer\n')
    os.replace(temporary, path)


# --- slicing ---------------------------------------------------------------------------------------

def memory_available_kb(meminfo='/proc/meminfo'):
    try:
        with open(meminfo) as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def print_time(output):
    """The engine's estimate in seconds, from what it prints ("Print time: 1234")."""
    found = re.search(r'Print time:\s*(\d+)', output or '')
    return int(found.group(1)) if found else None


def slice_model(model_path, model_code, folder=None, printing=lambda: False, run=subprocess.run,
                engine=None, free=browser_tools.free_bytes, available_kb=memory_available_kb):
    """Slice a model for this printer into its files. Returns (path, seconds or None).

    Refused while printing, for a printer without a profile, and for a model
    that does not fit with room for the skirt; the result must pass
    check_gcode, or nothing is kept.
    """
    folder = folder or browser_tools.GCODE_DIR
    code = (model_code or '').upper()
    if code not in PROFILES or code not in model_files.PRINTERS:
        raise SliceError('There is no slicing profile for this printer.')
    if printing():
        raise SliceError('The printer is printing. Slice the model when it is done.')
    engine = engine or ENGINE
    if not os.path.exists(engine):
        raise SliceError('The slicing engine is not installed.')
    info = model_files.model_info(model_path)
    if info.get('sliced'):
        raise SliceError('This file is already sliced: copy its plates instead.')
    _, (width, depth), height = model_files.PRINTERS[code]
    x, y, z = info['size']
    room = (width - 2 * EDGE_MARGIN, depth - 2 * EDGE_MARGIN)
    if z > height - TOP_MARGIN or not ((x <= room[0] and y <= room[1]) or (y <= room[0] and x <= room[1])):
        raise SliceError(f'It does not fit with room for the skirt: {x:g} x {y:g} x {z:g} mm, '
                         f'the printer takes {room[0]:g} x {room[1]:g} x {height - TOP_MARGIN:g} mm.')
    if free(folder) < browser_tools.FREE_MARGIN_BYTES:
        raise SliceError('There is not enough free space on the printer.')
    memory = available_kb()
    if memory is not None and memory < MIN_FREE_MEMORY_KB:
        raise SliceError(f'Not enough free memory to slice ({memory // 1024} MB). Stop an app or two and try again.')

    profile = PROFILES[code]
    work = tempfile.mkdtemp(prefix='.slice-', dir=folder)     # hidden: the printer does not list it
    try:
        stl = model_path
        if info['kind'] == '3mf':
            stl = os.path.join(work, 'model.stl')
            threemf_to_stl(model_path, stl)
        out = os.path.join(work, 'out.gcode')
        command = [engine, '-v']        # -v: it logs "Print time: <seconds>"
        for key, value in engine_settings(code, profile).items():
            command += ['-s', f'{key}={value}']
        command += ['-s', 'startCode=' + start_gcode(code, profile), '-s', 'endCode=' + end_gcode(code),
                    '-o', out, stl]
        try:
            # lowest priority: the screen and Klipper's helpers keep the CPU first
            result = run(command, capture_output=True, text=True, timeout=SLICE_TIMEOUT,
                         preexec_fn=lambda: os.nice(19))
        except subprocess.TimeoutExpired:
            raise SliceError('Slicing took too long and was stopped.')
        except OSError as e:
            raise SliceError(f'The slicing engine could not start: {e.strerror or e}')
        if getattr(result, 'returncode', 1) != 0 or not os.path.exists(out):
            # what the engine said, for the log (the screen gets the short reason)
            import logging
            logging.error('Slicing engine failed (exit %s): %s', getattr(result, 'returncode', None),
                          ((getattr(result, 'stderr', '') or '') + (getattr(result, 'stdout', '') or ''))[-2000:])
            raise SliceError('The slicing engine failed on this model.')
        _first_layer_done(out, profile)
        problem = check_gcode(out, code)
        if problem:
            raise SliceError(f'The result did not pass the safety check, so it was not kept. {problem}')
        if printing():
            raise SliceError('A print started while slicing; the result was not kept.')
        stem = os.path.basename(model_path)
        for suffix in ('.gcode.3mf', '.3mf', '.stl'):
            if stem.lower().endswith(suffix):
                stem = stem[:-len(suffix)]
                break
        name = browser_tools.print_file_name(f'file:///{stem}-PLA.gcode', os.listdir(folder))
        target = os.path.join(folder, name)
        os.replace(out, target)
        return target, print_time((getattr(result, 'stdout', '') or '') + (getattr(result, 'stderr', '') or ''))
    finally:
        for name in os.listdir(work):
            os.remove(os.path.join(work, name))
        os.rmdir(work)

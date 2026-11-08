"""Generate the installer progress sprites (snake-grid) and the error image
(snake-error) from the Boomslang mascot, as SVG. Render with rsvg-convert,
then convert to WebP; see branding/README.md."""
import sys

GREEN, DARK, BELLY = '#4fb548', '#3f9a3c', '#c9ea7f'
EYE, PUPIL, LINE, TONGUE = '#f6f2c8', '#2b2f36', '#2e6e2c', '#e0533f'


def head(cx, cy, s=1.0, dead=False):
    rx, ry = 56 * s, 42 * s
    out = [
        f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{GREEN}"/>',
        f'<path d="M{cx-rx+4*s} {cy-8*s} C {cx-rx+14*s} {cy-ry-14*s} {cx+rx-14*s} {cy-ry-14*s} {cx+rx-4*s} {cy-8*s} '
        f'C {cx+rx-24*s} {cy-20*s} {cx-rx+24*s} {cy-20*s} {cx-rx+4*s} {cy-8*s} Z" fill="{DARK}"/>',
    ]
    for side in (-1, 1):
        ex = cx + side * 25 * s
        out.append(f'<circle cx="{ex}" cy="{cy}" r="{21*s}" fill="{EYE}"/>')
        if dead:
            d = 9 * s
            out.append(f'<path d="M{ex-d} {cy-d} L {ex+d} {cy+d} M{ex+d} {cy-d} L {ex-d} {cy+d}" '
                       f'stroke="{PUPIL}" stroke-width="{5*s}" stroke-linecap="round"/>')
        else:
            out.append(f'<circle cx="{ex+side*-2*s}" cy="{cy+3*s}" r="{12.5*s}" fill="{PUPIL}"/>')
            out.append(f'<circle cx="{ex+side*-2*s+4*s}" cy="{cy-2*s}" r="{4*s}" fill="#ffffff"/>')
    out.append(f'<path d="M{cx-12*s} {cy+28*s} Q {cx} {cy+(30 if dead else 36)*s} {cx+12*s} {cy+28*s}" '
               f'fill="none" stroke="{LINE}" stroke-width="{3.5*s}" stroke-linecap="round"/>')
    if not dead:
        out.append(f'<path d="M{cx} {cy+33*s} L {cx} {cy+50*s} M{cx} {cy+47*s} L {cx-6*s} {cy+55*s} '
                   f'M{cx} {cy+47*s} L {cx+6*s} {cy+55*s}" fill="none" stroke="{TONGUE}" '
                   f'stroke-width="{3.5*s}" stroke-linecap="round" stroke-linejoin="round"/>')
    return out


def body(path, width=26, dash=True):
    out = [f'<path d="{path}" fill="none" stroke="{DARK}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>']
    if dash:
        out.append(f'<path d="{path}" fill="none" stroke="{BELLY}" stroke-width="{width*0.32:.1f}" '
                   f'stroke-linecap="round" stroke-dasharray="11 6"/>')
    return out


def grid():
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1280" viewBox="0 0 1024 1280">']
    for i in range(10):
        y0 = i * 128
        cx = 64 + i * 896 / 9
        base = y0 + 110
        # Tail curls up at the left, body runs along the bottom, neck rises into the head
        path = (f'M12 {base-30} Q 10 {base} 40 {base} L {cx-16:.1f} {base} '
                f'Q {cx:.1f} {base} {cx:.1f} {base-16} L {cx:.1f} {y0+60}')
        parts += body(path)
        parts += head(round(cx, 1), y0 + 49, s=0.9)
    parts.append('</svg>')
    return '\n'.join(parts)


def error():
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="411" height="290" viewBox="0 0 411 290">']
    parts += body('M20 236 Q 14 208 40 210 L 330 216 Q 348 217 352 200', width=24)
    parts += head(352, 196, s=0.95, dead=True)
    # "Not allowed" sign
    parts.append('<circle cx="160" cy="130" r="78" fill="#ffffff" stroke="#e23b2e" stroke-width="22"/>')
    parts.append('<path d="M106 76 L 214 184" stroke="#e23b2e" stroke-width="22" stroke-linecap="round"/>')
    parts.append('</svg>')
    return '\n'.join(parts)


if __name__ == '__main__':
    which = sys.argv[1]
    print(grid() if which == 'grid' else error())

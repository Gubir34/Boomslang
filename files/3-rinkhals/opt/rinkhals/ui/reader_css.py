"""CSS for the reader-mode browser.

The browser shows text and links, so only the CSS that changes those matters:
what a page hides, the colour and alignment of its text, a few text effects,
and whether an element starts a new line. Everything else is thrown away while
parsing, which is what keeps this fast and small on the printer.

What is understood:

  selectors    tag, .class, #id, [attr], [attr=value] (also ^= $= *= ~=), *,
               :root, compound selectors (p.note.big), descendant (a b) and
               child (a > b) combinators, selector lists (a, b)
  cascade      specificity, source order and !important, as in a browser
  at-rules     @media (width, colour scheme, screen/print), @supports and
               @layer blocks; the screen is treated as a small dark one, so a
               page's phone layout and its dark mode are the ones used
  variables    --name on :root / html / body, used through var(--name, fallback)
  properties   display, visibility, opacity and the usual "visually hidden"
               tricks; color, background-color, text-align, text-transform,
               text-decoration, white-space, font-size

Not understood, on purpose: sibling selectors, pseudo-classes other than
:root (a rule with :hover or :nth-child is skipped rather than applied to
everything), pseudo-elements, and layout.

How it stays fast (the printer has one slow core):

  - parsing jumps from brace to brace with a compiled regex instead of walking
    the text, and drops a rule as soon as none of its properties are of use
  - rules are filed by the id, class or tag of their last part, so an element
    only looks at rules that could match it instead of at every rule
  - the result is remembered per (tag, id, classes); pages repeat the same
    combinations thousands of times
"""
import re

MAX_CSS_BYTES = 150 * 1024    # of one stylesheet
MAX_CSS_RULES = 1500          # rules kept in total (only useful ones are kept)
VIEWPORT_WIDTH = 480          # px the page is told the screen is wide
MAX_NESTING = 4

PROPERTIES = frozenset((
    'display', 'visibility', 'opacity', 'color', 'background-color', 'background', 'text-align',
    'text-transform', 'text-decoration', 'text-decoration-line', 'white-space', 'font-size',
    # only read to recognise "visually hidden" text
    'position', 'clip', 'clip-path', 'width', 'height', 'max-height', 'overflow', 'left', 'text-indent',
))

NAMED_COLORS = {
    'white': (255, 255, 255), 'silver': (192, 192, 192), 'gray': (128, 128, 128), 'grey': (128, 128, 128),
    'red': (255, 80, 80), 'orange': (255, 165, 0), 'yellow': (255, 215, 0), 'gold': (255, 215, 0),
    'lime': (0, 255, 0), 'green': (60, 190, 60), 'teal': (0, 170, 170), 'cyan': (0, 255, 255),
    'aqua': (0, 255, 255), 'blue': (90, 140, 255), 'purple': (190, 110, 230), 'magenta': (255, 0, 255),
    'pink': (255, 150, 190), 'lightgray': (211, 211, 211), 'lightgrey': (211, 211, 211),
    'black': (0, 0, 0), 'navy': (0, 0, 128), 'maroon': (128, 0, 0), 'darkgray': (169, 169, 169),
    'darkgrey': (169, 169, 169), 'whitesmoke': (245, 245, 245), 'lightyellow': (255, 255, 224),
    'beige': (245, 245, 220), 'ivory': (255, 255, 240),
}

_IMPORTANT = re.compile(r'\s*!\s*important\s*$', re.I)
_COMMENT = re.compile(r'/\*.*?\*/', re.S)
_BRACE = re.compile(r'[{}]')
_HEX = re.compile(r'#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$')
_RGB = re.compile(r'rgba?\(\s*(\d+(?:\.\d+)?)(%?)\s*[, ]\s*(\d+(?:\.\d+)?)%?\s*[, ]\s*(\d+(?:\.\d+)?)%?[^)]*\)$')
_VAR = re.compile(r'var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*(?:\([^()]*\)[^()]*)*))?\)')
_LENGTH = re.compile(r'^(-?\d*\.?\d+)(px|em|rem|pt|%)?$')


# --- declarations ------------------------------------------------------------

def parse_declarations(text, important=None):
    """'color: red; display:none !important' -> {'color': 'red', 'display': 'none'}.

    Only properties of use are kept, plus custom properties (--name). The
    names of !important ones are added to the important set when one is given.
    """
    out = {}
    if not text or ':' not in text:
        return out
    for part in text.split(';'):
        key, sep, value = part.partition(':')
        if not sep:
            continue
        key = key.strip().lower()
        if key in PROPERTIES or key.startswith('--'):
            value = value.strip()
            if value.endswith(('t', 'T')) and '!' in value:   # ...!important
                stripped = _IMPORTANT.sub('', value)
                if stripped != value:
                    value = stripped
                    if important is not None:
                        important.add(key)
            out[key] = value if key.startswith('--') else value.lower()
    return out


def luminance(rgb):
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255


def parse_rgb(value):
    """Any CSS colour this understands -> (r, g, b), else None. Transparent is None."""
    value = (value or '').strip().lower()
    if not value:
        return None
    rgb = NAMED_COLORS.get(value)
    if rgb:
        return rgb
    m = _HEX.match(value)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = ''.join(c * 2 for c in h)
        if len(h) == 8 and h[6:] == '00':
            return None
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = _RGB.match(value)
    if m:
        scale = 2.55 if m.group(2) else 1
        return tuple(min(255, int(float(g) * scale)) for g in (m.group(1), m.group(3), m.group(4)))
    return None


def parse_color(value):
    """A text colour -> (r, g, b), or None when unknown or too dark to read on the dark screen."""
    rgb = parse_rgb(value)
    return rgb if rgb and luminance(rgb) >= 0.30 else None


def parse_length(value, base=16.0):
    """'24px', '1.5em', '150%' -> px, else None."""
    m = _LENGTH.match((value or '').strip().lower())
    if not m:
        return None
    number, unit = float(m.group(1)), m.group(2) or 'px'
    return number * {'px': 1, 'pt': 4 / 3, 'em': base, 'rem': base, '%': base / 100}[unit]


def hides(props):
    """Whether these declarations take an element off the screen."""
    display = props.get('display')
    if display == 'none':
        return True
    if props.get('visibility') in ('hidden', 'collapse'):
        return True
    opacity = props.get('opacity')
    if opacity in ('0', '0.0', '0%', '.0'):
        return True
    # "Visually hidden" text for screen readers: skip links, icon labels
    if props.get('position') in ('absolute', 'fixed'):
        clip = props.get('clip', '')
        if clip.startswith('rect(') and clip.replace(' ', '').startswith(('rect(0', 'rect(1px')):
            return True
        if props.get('clip-path', '').replace(' ', '') in ('inset(50%)', 'inset(100%)'):
            return True
        for key in ('left', 'text-indent'):
            length = parse_length(props.get(key, ''))
            if length is not None and length <= -999:
                return True
    if props.get('overflow') == 'hidden':
        for key in ('height', 'max-height', 'width'):
            if props.get(key, '') in ('0', '0px', '1px'):
                return True
    return False


# --- selectors ---------------------------------------------------------------

_COMPOUND = re.compile(r'([a-zA-Z][\w-]*|\*)?((?:[.#][\w-]+|\[[^\]]*\])*)$')
_SIMPLE = re.compile(r'[.#][\w-]+|\[[^\]]*\]')
_ATTR = re.compile(r'''\[\s*([\w-]+)\s*(?:([~^$*|]?=)\s*(?:"([^"]*)"|'([^']*)'|([^\]\s]*))\s*(?:[is]\s*)?)?\]$''')
_COMBINE = re.compile(r'\s*(>)\s*|\s+')


def _parse_compound(text):
    """'p.note#x[lang=en]' -> (tag, id, classes, attrs) or None when unsupported."""
    m = _COMPOUND.match(text)
    if not m or not (m.group(1) or m.group(2)):
        return None
    tag = (m.group(1) or '').lower()
    tag = None if tag in ('', '*') else tag
    element_id, classes, attrs = None, [], []
    for piece in _SIMPLE.findall(m.group(2)):
        if piece[0] == '.':
            classes.append(piece[1:])
        elif piece[0] == '#':
            element_id = piece[1:]
        else:
            a = _ATTR.match(piece)
            if not a:
                return None
            value = a.group(3) if a.group(3) is not None else a.group(4) if a.group(4) is not None else a.group(5)
            attrs.append((a.group(1).lower(), a.group(2), value))
    return tag, element_id, tuple(classes), tuple(attrs)


def parse_selector(text):
    """One selector -> (key compound, ancestors, specificity), or None when unsupported.

    ancestors is [(combinator, compound)] from the element outwards, where the
    combinator ('>' or ' ') says how that compound relates to the one before.
    """
    text = text.strip()
    if not text:
        return None
    if ':' in text:
        text = text.replace(':root', 'html')
        if ':' in text:
            return None      # a pseudo-class or pseudo-element this does not know
    if '+' in text or '~' in text.replace('~=', ''):
        return None          # sibling selectors
    parts, combinators, last = [], [], 0
    for m in _COMBINE.finditer(text):
        if '[' in text[last:m.start()] and ']' not in text[last:m.start()]:
            continue         # a space inside [attr="a b"]
        parts.append(text[last:m.start()])
        combinators.append('>' if m.group(1) else ' ')
        last = m.end()
    parts.append(text[last:])
    compounds = [_parse_compound(p) for p in parts]
    if not compounds or None in compounds:
        return None
    if any(c[3] for c in compounds[:-1]):
        return None          # attribute tests on ancestors are not kept track of
    specificity = 0
    for tag, element_id, classes, attrs in compounds:
        specificity += (10000 if element_id else 0) + 100 * (len(classes) + len(attrs)) + (1 if tag else 0)
    ancestors = [(combinators[i], compounds[i]) for i in range(len(compounds) - 2, -1, -1)]
    return compounds[-1], ancestors, specificity


def _attrs_match(tests, attrs):
    for name, op, wanted in tests:
        value = attrs.get(name)
        if value is None and name not in attrs:
            return False
        value = value or ''
        if op is None:
            continue
        if op == '=':
            ok = value == wanted
        elif op == '~=':
            ok = wanted in value.split()
        elif op == '^=':
            ok = bool(wanted) and value.startswith(wanted)
        elif op == '$=':
            ok = bool(wanted) and value.endswith(wanted)
        elif op == '*=':
            ok = bool(wanted) and wanted in value
        else:   # |=
            ok = value == wanted or value.startswith(wanted + '-')
        if not ok:
            return False
    return True


# --- media queries -------------------------------------------------------------

_FEATURE = re.compile(r'\(\s*([\w-]+)\s*(?::\s*([^)]+?))?\s*\)')
_RANGE = re.compile(r'\(\s*width\s*(<=|>=|<|>)\s*([^)]+?)\s*\)')


def _feature_matches(name, value, width):
    if name in ('max-width', 'max-device-width'):
        limit = parse_length(value)
        return limit is not None and width <= limit
    if name in ('min-width', 'min-device-width'):
        limit = parse_length(value)
        return limit is not None and width >= limit
    if name == 'prefers-color-scheme':
        return value == 'dark'              # the touch screen is dark
    if name == 'prefers-reduced-motion':
        return value == 'reduce'
    if name == 'orientation':
        return value == 'landscape'
    if name in ('hover', 'any-hover'):
        return value == 'none'              # a touch screen
    if name in ('pointer', 'any-pointer'):
        return value == 'coarse'
    return False


def media_matches(query, width=VIEWPORT_WIDTH):
    """Whether an @media query applies to the touch screen. Unknown queries do not."""
    for alternative in query.lower().split(','):
        alternative = alternative.strip()
        if not alternative:
            return True
        negate = alternative.startswith('not ')
        ok = True
        words = _FEATURE.sub(' ', _RANGE.sub(' ', alternative)).replace('only', ' ').replace('not', ' ').replace('and', ' ').split()
        for word in words:
            if word not in ('screen', 'all'):
                ok = False          # print, speech, or something unknown
        if '<' in _RANGE.sub(' ', alternative) or '>' in _RANGE.sub(' ', alternative):
            ok = False              # a range form this does not read, e.g. (400px <= width)
        for op, value in _RANGE.findall(alternative):
            limit = parse_length(value)
            ok = ok and limit is not None and {'<=': width <= limit, '>=': width >= limit,
                                                '<': width < limit, '>': width > limit}[op]
        for name, value in _FEATURE.findall(alternative):
            ok = ok and _feature_matches(name, (value or '').strip(), width)
        if ok != negate:
            return True
    return False


# --- stylesheet ----------------------------------------------------------------

def _blocks(css):
    """Yield (prelude, body) for each top-level { } block."""
    position, end = 0, len(css)
    search = _BRACE.search
    while True:
        m = search(css, position)
        if not m:
            return
        if css[m.start()] == '}':
            position = m.end()      # a stray closing brace
            continue
        start, depth, scan = m.start(), 1, m.end()
        while depth:
            m = search(css, scan)
            if not m:
                scan = end + 1
                break
            depth += 1 if css[m.start()] == '{' else -1
            scan = m.end()
        yield css[position:start], css[start + 1:scan - 1]
        position = scan


class Stylesheet:
    """The useful rules of a page, filed for fast lookup."""

    def __init__(self, width=VIEWPORT_WIDTH):
        self.width = width
        self.count = 0
        self.variables = {}
        self._by_id, self._by_class, self._by_tag, self._any = {}, {}, {}, []
        self._cache = {}

    # --- building ---
    def add(self, css, _depth=0):
        """Add a stylesheet's rules. Returns False once the rule limit is reached."""
        if _depth == 0:
            css = (css or '')[:MAX_CSS_BYTES]
            if '/*' in css:
                css = _COMMENT.sub('', css)
            self._cache.clear()
        for prelude, body in _blocks(css):
            if self.count >= MAX_CSS_RULES:
                return False
            if ';' in prelude:
                prelude = prelude.rsplit(';', 1)[-1]    # a preceding @import ...;
            prelude = prelude.strip()
            if not prelude:
                continue
            if prelude[0] == '@':
                name, _, condition = prelude[1:].partition(' ')
                name = name.lower()
                nested = (name == 'media' and media_matches(condition, self.width)) or name in ('supports', 'layer')
                if nested and _depth < MAX_NESTING and '{' in body:
                    if not self.add(body, _depth + 1):
                        return False
                continue
            if ':' not in body:
                continue
            important = set()
            props = parse_declarations(body, important)
            if not props:
                continue
            for selector in prelude.split(','):
                parsed = parse_selector(selector)
                if parsed:
                    self._file(parsed, props, important)
        return True

    def _file(self, parsed, props, important):
        (tag, element_id, classes, attrs), ancestors, specificity = parsed
        custom = [k for k in props if k.startswith('--')]
        if custom:
            # Variables are only followed from the top of the page
            if not ancestors and not classes and not attrs and not element_id and tag in ('html', 'body', None):
                for key in custom:
                    self.variables[key] = props[key]
            if len(custom) == len(props):
                return
            props = {k: v for k, v in props.items() if not k.startswith('--')}
        rule = (specificity, self.count, tag, element_id, classes, attrs, ancestors, props, frozenset(important))
        self.count += 1
        if element_id:
            self._by_id.setdefault(element_id, []).append(rule)
        elif classes:
            self._by_class.setdefault(classes[0], []).append(rule)
        elif tag:
            self._by_tag.setdefault(tag, []).append(rule)
        else:
            self._any.append(rule)

    @property
    def rules(self):
        """Every rule kept, in source order (for tests and debugging)."""
        out = list(self._any)
        for bucket in (self._by_id, self._by_class, self._by_tag):
            for rules in bucket.values():
                out += rules
        return sorted(out, key=lambda r: r[1])

    # --- lookup ---
    def resolve(self, value, _depth=0):
        """Replace var(--name, fallback) with its value."""
        if 'var(' not in value or _depth > 4:
            return value

        def substitute(m):
            found = self.variables.get(m.group(1))
            if found is None:
                found = (m.group(2) or '').strip()
            return self.resolve(found, _depth + 1)
        return _VAR.sub(substitute, value).strip().lower()

    def _candidates(self, tag, element_id, classes):
        key = (tag, element_id, classes)
        found = self._cache.get(key)
        if found is None:
            rules = list(self._any)
            if self._by_tag:
                rules += self._by_tag.get(tag, ())
            if element_id and self._by_id:
                rules += self._by_id.get(element_id, ())
            for name in classes:
                rules += self._by_class.get(name, ())
            rules = [r for r in rules
                     if (r[2] is None or r[2] == tag) and (r[3] is None or r[3] == element_id) and
                     (not r[4] or all(c in classes for c in r[4]))]
            rules.sort(key=lambda r: (r[0], r[1]))
            # When nothing depends on attributes or ancestors the answer is
            # the same for every such element: keep it ready
            ready = None
            if not any(r[5] or r[6] for r in rules):
                ready = self._merge(rules)
            found = (rules, ready)
            if len(self._cache) < 4000:
                self._cache[key] = found
        return found

    @staticmethod
    def _merge(rules):
        out, forced = {}, set()
        for rule in rules:
            important = rule[8]
            for key, value in rule[7].items():
                if key in forced and key not in important:
                    continue
                out[key] = value
                if key in important:
                    forced.add(key)
        return out, forced

    def declarations(self, tag, element_id, classes, attrs, ancestors):
        """The declarations that apply to an element, as (dict, important names).

        ancestors is the list of open elements, outermost first, each a dict
        with 'tag', 'id' and 'classes'. The returned dict must not be changed.
        """
        if not self.count:
            return _EMPTY
        rules, ready = self._candidates(tag, element_id, classes)
        if ready is not None:
            return ready
        matching = [r for r in rules
                    if (not r[5] or _attrs_match(r[5], attrs)) and (not r[6] or _ancestors_match(r[6], ancestors))]
        return self._merge(matching)


_EMPTY = ({}, set())


def _ancestors_match(wanted, ancestors):
    index = len(ancestors) - 1
    for combinator, (tag, element_id, classes, _attrs) in wanted:
        while True:
            if index < 0:
                return False
            entry = ancestors[index]
            index -= 1
            if ((tag is None or entry['tag'] == tag) and (element_id is None or entry.get('id') == element_id) and
                    (not classes or all(c in entry.get('classes', ()) for c in classes))):
                break
            if combinator == '>':
                return False
    return True


def parse_css(css, width=VIEWPORT_WIDTH):
    """The rules a stylesheet contributes, as [(tag, [classes], id, properties)] in source order.

    The tag, classes and id are those of the selector's last part.
    """
    sheet = Stylesheet(width)
    sheet.add(css)
    return [(r[2], list(r[4]), r[3], r[7]) for r in sheet.rules]

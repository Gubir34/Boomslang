/*
 * Boomslang stock screen look: recolours Anycubic's stock screen (K3SysUi).
 *
 * K3SysUi is a closed Qt 5 program. Its colours are style sheets that it hands to
 * QWidget::setStyleSheet (and QApplication::setStyleSheet), as text such as
 * "QPushButton { background-color: #3D3D3D; border-radius: 10px }". Loaded with
 * LD_PRELOAD (start.sh, only when Settings > Stock screen look is on), this library
 * stands in front of those two functions, swaps the stock colours in the text for
 * Liquid Plastic's and calls Qt's own function with the result.
 *
 * Kept deliberately small and careful, because it runs inside the printer's screen:
 *   - every swap keeps the length, so a style sheet never grows; a style sheet longer
 *     than the buffer, or anything unexpected, is passed on untouched
 *   - no allocation and no C library calls besides dlsym: nothing to fail
 *   - the functions it stands in front of are found by name with dlsym(RTLD_NEXT);
 *     if one can't be found, nothing is set (the stock screen keeps working, unstyled)
 *   - start.sh turns the look off again by itself if the stock screen does not stay up
 *
 * Only style sheet colours change: pictures (icons, backgrounds) are inside the
 * program and keep Anycubic's colours.
 *
 * Built by build.sh for the printer (ARMv7, hard float, uClibc) and for this machine
 * (the tests run it against real Qt through PyQt5).
 */
#include <stddef.h>

#define RTLD_NEXT ((void *) -1l)
extern void *dlsym(void *handle, const char *name);

/* Qt 5's QString: one pointer to a QArrayData header followed (at "offset") by UTF-16. */
typedef struct {
    int ref;            /* -1: static, 0: unsharable, else a count */
    int size;           /* in UTF-16 units */
    unsigned int alloc; /* capacity and a flag */
    ptrdiff_t offset;   /* from this header to the data */
} QArrayData;
typedef struct { QArrayData *d; } QString;

typedef void (*set_style_sheet_fn)(void *self, const QString *sheet);
typedef void (*from_utf16_fn)(QString *result, const unsigned short *text, int size);
#if __SIZEOF_POINTER__ == 8
typedef void (*deallocate_fn)(QArrayData *data, unsigned long object_size, unsigned long alignment);
#define DEALLOCATE "_ZN10QArrayData10deallocateEPS_mm"
#else
typedef void (*deallocate_fn)(QArrayData *data, unsigned int object_size, unsigned int alignment);
#define DEALLOCATE "_ZN10QArrayData10deallocateEPS_jj"
#endif

/* Stock colour -> Liquid Plastic colour. Same length on both sides, longest first,
   matched without regard to case. */
static const char *const SWAPS[][2] = {
    /* the dark greys of the background and the buttons become deep greens */
    {"rgb(28, 28, 28)", "rgb(11, 36, 20)"},
    {"#1c1c1c", "#0b2414"},
    {"#292929", "#10301c"},
    {"#333333", "#163a24"},
    {"#3d3d3d", "#1d4a2e"},
    {"#424242", "#215234"},
    {"#4b4b4b", "#275c3b"},
    {"#4d4d4d", "#295e3d"},
    /* Anycubic's blue accents become Boomslang's greens */
    {"#438dff", "#4fb548"},
    {"#2f97ff", "#3fa83a"},
    {"#43f8ff", "#9be86a"},
    {"#b4f3ff", "#d6f7b8"},
    /* grey text, a little green */
    {"#999999", "#a9c4ae"},
    {"#818799", "#8aa892"},
    {"#999", "#ace"},
    /* rounder corners */
    {"border-radius: 10px", "border-radius: 18px"},
    {"border-radius:10px", "border-radius:18px"},
    {"border-radius: 8px", "border-radius:14px"},
};
#define SWAP_COUNT (sizeof(SWAPS) / sizeof(SWAPS[0]))
#define MAX_UNITS 16384

static unsigned short buffer[MAX_UNITS];

static int is_hex(unsigned short c) {
    return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
}

static unsigned short lower(unsigned short c) {
    return (c >= 'A' && c <= 'Z') ? (unsigned short) (c + 32) : c;
}

/* Swaps in place; returns how many swaps were made. */
static int swap_colours(unsigned short *text, int size) {
    int swaps = 0;
    for (int i = 0; i < size; i++) {
        for (size_t s = 0; s < SWAP_COUNT; s++) {
            const char *from = SWAPS[s][0], *to = SWAPS[s][1];
            int n = 0;
            while (from[n] && i + n < size && lower(text[i + n]) == (unsigned short) from[n])
                n++;
            if (from[n])
                continue;
            /* "#999" must not take the start of "#9999ff" */
            if (from[0] == '#' && i + n < size && is_hex(text[i + n]))
                continue;
            for (int k = 0; k < n; k++)
                text[i + k] = (unsigned short) (unsigned char) to[k];
            i += n - 1;
            swaps++;
            break;
        }
    }
    return swaps;
}

static from_utf16_fn from_utf16;
static deallocate_fn deallocate;

static void forward(set_style_sheet_fn real, void *self, const QString *sheet) {
    if (!real)
        return;
    if (!from_utf16)
        from_utf16 = (from_utf16_fn) dlsym(RTLD_NEXT, "_ZN7QString9fromUtf16EPKti");
    if (!deallocate)
        deallocate = (deallocate_fn) dlsym(RTLD_NEXT, DEALLOCATE);
    QArrayData *d = sheet ? sheet->d : NULL;
    if (!from_utf16 || !deallocate || !d || d->size <= 0 || d->size > MAX_UNITS) {
        real(self, sheet);
        return;
    }
    const unsigned short *data = (const unsigned short *) ((const char *) d + d->offset);
    for (int i = 0; i < d->size; i++)
        buffer[i] = data[i];
    if (!swap_colours(buffer, d->size)) {
        real(self, sheet);
        return;
    }
    QString recoloured;
    from_utf16(&recoloured, buffer, d->size);
    real(self, &recoloured);
    /* QString's destructor, which is inline in Qt's headers */
    QArrayData *r = recoloured.d;
    if (r && r->ref != -1 && __atomic_sub_fetch(&r->ref, 1, __ATOMIC_ACQ_REL) == 0)
        deallocate(r, sizeof(unsigned short), _Alignof(QArrayData));
}

__attribute__((visibility("default")))
void _ZN7QWidget13setStyleSheetERK7QString(void *self, const QString *sheet) {
    static set_style_sheet_fn real;
    if (!real)
        real = (set_style_sheet_fn) dlsym(RTLD_NEXT, "_ZN7QWidget13setStyleSheetERK7QString");
    forward(real, self, sheet);
}

__attribute__((visibility("default")))
void _ZN12QApplication13setStyleSheetERK7QString(void *self, const QString *sheet) {
    static set_style_sheet_fn real;
    if (!real)
        real = (set_style_sheet_fn) dlsym(RTLD_NEXT, "_ZN12QApplication13setStyleSheetERK7QString");
    forward(real, self, sheet);
}

/* For the tests: the swap alone, on UTF-16 text. */
__attribute__((visibility("default")))
int boomslang_stock_look_swap(unsigned short *text, int size) {
    return swap_colours(text, size);
}

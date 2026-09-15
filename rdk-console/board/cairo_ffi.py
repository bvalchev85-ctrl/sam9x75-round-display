"""ctypes binding for the subset of libcairo the console draws with.

The image already ships libcairo.so.2 + libfreetype (EGT pulls them in), so the
UI can be drawn as live vector graphics instead of shipping pre-rendered
bitmaps.  Only the calls we actually use are declared.

`Ctx` wraps a cairo_t with pythonic methods; colours are "#rrggbb" strings or
(r, g, b[, a]) floats.
"""

import ctypes
import math

lib = ctypes.CDLL("libcairo.so.2")

FORMAT_ARGB32 = 0
FORMAT_RGB24 = 1

FONT_SLANT_NORMAL = 0
FONT_WEIGHT_NORMAL = 0
FONT_WEIGHT_BOLD = 1

LINE_CAP_BUTT = 0
LINE_CAP_ROUND = 1
LINE_JOIN_ROUND = 1

ANTIALIAS_DEFAULT = 1

_p = ctypes.c_void_p
_d = ctypes.c_double
_i = ctypes.c_int


def _fn(name, restype, *argtypes):
    f = getattr(lib, name)
    f.restype = restype
    f.argtypes = argtypes
    return f


class TextExtents(ctypes.Structure):
    _fields_ = [("x_bearing", _d), ("y_bearing", _d), ("width", _d),
                ("height", _d), ("x_advance", _d), ("y_advance", _d)]


class FontExtents(ctypes.Structure):
    _fields_ = [("ascent", _d), ("descent", _d), ("height", _d),
                ("max_x_advance", _d), ("max_y_advance", _d)]


surface_create_for_data = _fn("cairo_image_surface_create_for_data",
                              _p, _p, _i, _i, _i, _i)
image_surface_create = _fn("cairo_image_surface_create", _p, _i, _i, _i)
set_source_surface = _fn("cairo_set_source_surface", None, _p, _p, _d, _d)
mask_surface = _fn("cairo_mask_surface", None, _p, _p, _d, _d)
surface_destroy = _fn("cairo_surface_destroy", None, _p)
surface_write_to_png = _fn("cairo_surface_write_to_png", _i, _p,
                           ctypes.c_char_p)
surface_flush = _fn("cairo_surface_flush", None, _p)
surface_status = _fn("cairo_surface_status", _i, _p)

create = _fn("cairo_create", _p, _p)
destroy = _fn("cairo_destroy", None, _p)
status = _fn("cairo_status", _i, _p)
status_to_string = _fn("cairo_status_to_string", ctypes.c_char_p, _i)

save = _fn("cairo_save", None, _p)
restore = _fn("cairo_restore", None, _p)
translate = _fn("cairo_translate", None, _p, _d, _d)
scale = _fn("cairo_scale", None, _p, _d, _d)
rotate = _fn("cairo_rotate", None, _p, _d)
identity_matrix = _fn("cairo_identity_matrix", None, _p)

set_source_rgb = _fn("cairo_set_source_rgb", None, _p, _d, _d, _d)
set_source_rgba = _fn("cairo_set_source_rgba", None, _p, _d, _d, _d, _d)
set_source = _fn("cairo_set_source", None, _p, _p)
paint = _fn("cairo_paint", None, _p)
fill = _fn("cairo_fill", None, _p)
fill_preserve = _fn("cairo_fill_preserve", None, _p)
stroke = _fn("cairo_stroke", None, _p)
stroke_preserve = _fn("cairo_stroke_preserve", None, _p)
clip = _fn("cairo_clip", None, _p)
reset_clip = _fn("cairo_reset_clip", None, _p)

set_line_width = _fn("cairo_set_line_width", None, _p, _d)
set_line_cap = _fn("cairo_set_line_cap", None, _p, _i)
set_line_join = _fn("cairo_set_line_join", None, _p, _i)
set_dash = _fn("cairo_set_dash", None, _p, ctypes.POINTER(_d), _i, _d)
set_antialias = _fn("cairo_set_antialias", None, _p, _i)

new_path = _fn("cairo_new_path", None, _p)
new_sub_path = _fn("cairo_new_sub_path", None, _p)
close_path = _fn("cairo_close_path", None, _p)
move_to = _fn("cairo_move_to", None, _p, _d, _d)
line_to = _fn("cairo_line_to", None, _p, _d, _d)
curve_to = _fn("cairo_curve_to", None, _p, _d, _d, _d, _d, _d, _d)
rectangle = _fn("cairo_rectangle", None, _p, _d, _d, _d, _d)
arc = _fn("cairo_arc", None, _p, _d, _d, _d, _d, _d)
arc_negative = _fn("cairo_arc_negative", None, _p, _d, _d, _d, _d, _d)

pattern_create_radial = _fn("cairo_pattern_create_radial", _p,
                            _d, _d, _d, _d, _d, _d)
pattern_create_linear = _fn("cairo_pattern_create_linear", _p, _d, _d, _d, _d)
pattern_add_color_stop_rgba = _fn("cairo_pattern_add_color_stop_rgba", None,
                                  _p, _d, _d, _d, _d, _d)
pattern_destroy = _fn("cairo_pattern_destroy", None, _p)

select_font_face = _fn("cairo_select_font_face", None,
                       _p, ctypes.c_char_p, _i, _i)
set_font_size = _fn("cairo_set_font_size", None, _p, _d)
show_text = _fn("cairo_show_text", None, _p, ctypes.c_char_p)
text_extents = _fn("cairo_text_extents", None, _p, ctypes.c_char_p,
                   ctypes.POINTER(TextExtents))
font_extents = _fn("cairo_font_extents", None, _p,
                   ctypes.POINTER(FontExtents))

TAU = 2.0 * math.pi


def rgb(colour, alpha=None):
    """'#rrggbb' or (r,g,b[,a]) -> (r, g, b, a) floats in 0..1."""
    if isinstance(colour, str):
        s = colour.lstrip("#")
        r = int(s[0:2], 16) / 255.0
        g = int(s[2:4], 16) / 255.0
        b = int(s[4:6], 16) / 255.0
        a = 1.0 if len(s) < 8 else int(s[6:8], 16) / 255.0
    else:
        r, g, b = colour[0], colour[1], colour[2]
        a = colour[3] if len(colour) > 3 else 1.0
    if alpha is not None:
        a = alpha
    return r, g, b, a


class Ctx:
    """Thin pythonic wrapper around cairo_t drawing into a raw pixel buffer."""

    def __init__(self, addr=None, width=0, height=0, stride=0,
                 fmt=FORMAT_RGB24):
        # addr=None -> a standalone offscreen surface (used to cache the
        # static background); otherwise draw straight into the scanout buffer.
        if addr is None:
            self.surface = image_surface_create(fmt, width, height)
        else:
            self.surface = surface_create_for_data(addr, fmt, width, height,
                                                   stride)
        st = surface_status(self.surface)
        if st:
            raise RuntimeError("cairo surface: %s"
                               % status_to_string(st).decode())
        self.cr = create(self.surface)
        self.width = width
        self.height = height

    # ---- lifecycle ------------------------------------------------------
    def flush(self):
        surface_flush(self.surface)

    def write_png(self, path):
        """Dump what we drew - lets the panel be verified without a camera."""
        surface_flush(self.surface)
        st = surface_write_to_png(self.surface, str(path).encode())
        if st:
            raise RuntimeError("write_png: %s"
                               % status_to_string(st).decode())

    def check(self):
        st = status(self.cr)
        if st:
            raise RuntimeError("cairo: %s" % status_to_string(st).decode())

    def close(self):
        if self.cr:
            destroy(self.cr)
            self.cr = None
        if self.surface:
            surface_destroy(self.surface)
            self.surface = None

    # ---- state ----------------------------------------------------------
    def save(self):
        save(self.cr)

    def restore(self):
        restore(self.cr)

    def translate(self, x, y):
        translate(self.cr, x, y)

    def scale(self, sx, sy=None):
        scale(self.cr, sx, sx if sy is None else sy)

    def rotate(self, a):
        rotate(self.cr, a)

    def identity(self):
        """Drop any translate/scale - used to paint the untransformed buffer."""
        identity_matrix(self.cr)

    def colour(self, c, alpha=None):
        r, g, b, a = rgb(c, alpha)
        set_source_rgba(self.cr, r, g, b, a)

    def line_width(self, w):
        set_line_width(self.cr, w)

    def cap_round(self):
        set_line_cap(self.cr, LINE_CAP_ROUND)
        set_line_join(self.cr, LINE_JOIN_ROUND)

    def dash(self, pattern, offset=0.0):
        if not pattern:
            set_dash(self.cr, None, 0, 0.0)
        else:
            arr = (_d * len(pattern))(*pattern)
            set_dash(self.cr, arr, len(pattern), offset)

    def clip(self):
        """Clip to the current path (limits how much a blit has to composite)."""
        clip(self.cr)

    def clip_circle(self, cx, cy, r):
        new_path(self.cr)
        arc(self.cr, cx, cy, r, 0, TAU)
        clip(self.cr)

    def reset_clip(self):
        reset_clip(self.cr)

    # ---- paths ----------------------------------------------------------
    def new_path(self):
        new_path(self.cr)

    def move_to(self, x, y):
        move_to(self.cr, x, y)

    def line_to(self, x, y):
        line_to(self.cr, x, y)

    def curve_to(self, x1, y1, x2, y2, x3, y3):
        curve_to(self.cr, x1, y1, x2, y2, x3, y3)

    def close(self_path):  # noqa: N805 - keeps call sites terse
        close_path(self_path.cr)

    def rect(self, x, y, w, h):
        rectangle(self.cr, x, y, w, h)

    def arc(self, cx, cy, r, a1, a2):
        arc(self.cr, cx, cy, r, a1, a2)

    def arc_neg(self, cx, cy, r, a1, a2):
        arc_negative(self.cr, cx, cy, r, a1, a2)

    def circle(self, cx, cy, r):
        new_sub_path(self.cr)
        arc(self.cr, cx, cy, r, 0, TAU)

    def round_rect(self, x, y, w, h, r):
        r = min(r, w / 2.0, h / 2.0)
        new_sub_path(self.cr)
        arc(self.cr, x + w - r, y + r, r, -0.25 * TAU, 0.0)
        arc(self.cr, x + w - r, y + h - r, r, 0.0, 0.25 * TAU)
        arc(self.cr, x + r, y + h - r, r, 0.25 * TAU, 0.5 * TAU)
        arc(self.cr, x + r, y + r, r, 0.5 * TAU, 0.75 * TAU)
        close_path(self.cr)

    # ---- painting -------------------------------------------------------
    def paint(self):
        paint(self.cr)

    def fill(self, keep=False):
        fill_preserve(self.cr) if keep else fill(self.cr)

    def stroke(self, keep=False):
        stroke_preserve(self.cr) if keep else stroke(self.cr)

    def draw_surface(self, surf, x=0.0, y=0.0):
        """Blit a cached offscreen surface (used for the static background)."""
        set_source_surface(self.cr, surf, x, y)
        paint(self.cr)

    def mask(self, surf, x=0.0, y=0.0):
        """Paint the current colour through `surf`'s alpha channel.

        Lets one pre-rendered alpha sprite be tinted any colour - a radial
        gradient costs ~9 us/pixel on this core, a masked blit almost nothing.
        """
        mask_surface(self.cr, surf, x, y)

    def radial(self, cx0, cy0, r0, cx1, cy1, r1, stops):
        """stops = [(offset, colour, alpha), ...]; sets it as the source."""
        pat = pattern_create_radial(cx0, cy0, r0, cx1, cy1, r1)
        for off, col, alpha in stops:
            r, g, b, a = rgb(col, alpha)
            pattern_add_color_stop_rgba(pat, off, r, g, b, a)
        set_source(self.cr, pat)
        pattern_destroy(pat)

    def linear(self, x0, y0, x1, y1, stops):
        pat = pattern_create_linear(x0, y0, x1, y1)
        for off, col, alpha in stops:
            r, g, b, a = rgb(col, alpha)
            pattern_add_color_stop_rgba(pat, off, r, g, b, a)
        set_source(self.cr, pat)
        pattern_destroy(pat)

    # ---- text -----------------------------------------------------------
    def font(self, family="DejaVu Sans", size=20, bold=False):
        select_font_face(self.cr, family.encode(), FONT_SLANT_NORMAL,
                         FONT_WEIGHT_BOLD if bold else FONT_WEIGHT_NORMAL)
        set_font_size(self.cr, size)

    def measure(self, text):
        ext = TextExtents()
        text_extents(self.cr, text.encode(), ctypes.byref(ext))
        return ext

    def text(self, x, y, s):
        move_to(self.cr, x, y)
        show_text(self.cr, s.encode())

    def text_centred(self, cx, y, s, tracking=0.0):
        """Draw `s` horizontally centred on cx, baseline at y.

        `tracking` adds per-character letter-spacing (the mockup's monospace
        status line uses it); cairo's toy text API has no letter-spacing, so
        wide tracking is drawn a glyph at a time.
        """
        if not tracking:
            ext = self.measure(s)
            move_to(self.cr, cx - ext.width / 2.0 - ext.x_bearing, y)
            show_text(self.cr, s.encode())
            return
        widths = [self.measure(ch).x_advance + tracking for ch in s]
        total = sum(widths) - tracking
        x = cx - total / 2.0
        for ch, w in zip(s, widths):
            move_to(self.cr, x, y)
            show_text(self.cr, ch.encode())
            x += w

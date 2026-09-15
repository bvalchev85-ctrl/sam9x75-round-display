"""Screen drawing for the round console.

Layout is transcribed from preview/round-menu-720.html so the glass matches
the mockup.  The static background (gradient + sweep + rings) is rendered once
into an offscreen surface and blitted per frame - on this FPU-less ARM926 the
gradients cost far more than everything else combined.
"""

import ctypes
import math
import os
import zlib

import cairo_ffi as cf
import icons
import theme as T

TAU = 2.0 * math.pi

# Bump when the background drawing changes, so a stale cache is discarded.
BG_CACHE_VERSION = 2
BG_CACHE = "/var/cache/rdk-console/bg-v%d.zz" % BG_CACHE_VERSION

# Icons are pre-rendered into white alpha sprites and blitted tinted.
# Re-stroking a 188 px vector icon costs ~15 ms and letting cairo scale a mask
# costs ~31 ms, so sprites are cached per size bucket and blitted 1:1 (~2.7 ms).
ICON_SIZE_STEP = 8
ICON_NOMINAL = 188.0

# The band that moves during a carousel slide (glow, icons, labels).  Only this
# is repainted per animation frame; the rest of both buffers already holds
# identical static chrome.
SLIDE_BAND = (200, 610)

# Horizontal distance between carousel slots (centre -> side icon).
SLOT_DX = T.SIDE_RIGHT_CX - T.CX          # 199 px


def carousel_slot(s):
    """Geometry for an item `s` slots from the centre (s is continuous).

    s = 0 is the centre (large, opaque), s = -1/+1 the side icons, and by
    |s| = 2 the item has faded out.  Continuous so the carousel can be drawn
    mid-slide.
    """
    a = abs(s)
    x = T.CX + s * SLOT_DX
    if a <= 1.0:
        size = T.SIDE_ICON + (T.CENTRE_ICON - T.SIDE_ICON) * (1.0 - a)
        alpha = T.SIDE_ALPHA + (1.0 - T.SIDE_ALPHA) * (1.0 - a)
    else:
        size = T.SIDE_ICON
        alpha = max(0.0, T.SIDE_ALPHA * (2.0 - a))
    return x, size, alpha


class Renderer:
    def __init__(self, display, cache=BG_CACHE, offset=(0.0, 0.0)):
        self.d = display
        # One cairo context per dumb buffer; `ctx` follows the back buffer.
        self._ctxs = [cf.Ctx(b.addr, display.width, display.height, b.pitch)
                      for b in display.bufs]
        self.last_ctx = self._ctxs[0]
        self._bg = None
        self._bg_buf = None
        self._glow = None
        self._icons = {}
        self._chrome = None
        self._chrome_buf = None
        self._chrome_key = None
        self._ctx_override = None
        self.cache = cache
        # Fallback panel alignment: only used when the mode retiming in
        # kms.tune_mode() is unavailable, since shifting what we draw gives up
        # that many pixels at one edge.
        self.ox, self.oy = float(offset[0]), float(offset[1])
        if self.ox or self.oy:
            for c in self._ctxs:
                c.translate(self.ox, self.oy)

    @property
    def ctx(self):
        """The context for the buffer currently being drawn (the back one).

        `_ctx_override` redirects drawing into an offscreen surface while a
        cached layer (the menu chrome) is being built.
        """
        if self._ctx_override is not None:
            return self._ctx_override
        return self._ctxs[self.d.back]

    # ---- static background (cached) --------------------------------------
    def _build_background(self):
        """Draw (or load) the gradient+rings backdrop into an owned buffer.

        The two full-screen radial gradients cost ~10 s on this ARM926 (no FPU,
        soft-float), so the finished pixels are cached on disk: the buffer is
        ours (create_for_data over a ctypes buffer) which makes save/load a
        plain memcpy.
        """
        stride = T.W * 4
        size = stride * T.H
        self._bg_buf = ctypes.create_string_buffer(size)
        addr = ctypes.addressof(self._bg_buf)
        off = cf.Ctx(addr, T.W, T.H, stride)
        self._bg = off

        if self._load_cache(addr, size):
            return

        self._paint_background(off)
        off.flush()
        self._save_cache(addr, size)

    def _load_cache(self, addr, size):
        try:
            with open(self.cache, "rb") as f:
                raw = zlib.decompress(f.read())
        except (OSError, zlib.error):
            return False
        if len(raw) != size:
            return False
        ctypes.memmove(addr, raw, size)
        return True

    def _save_cache(self, addr, size):
        try:
            os.makedirs(os.path.dirname(self.cache), exist_ok=True)
            raw = ctypes.string_at(addr, size)
            tmp = self.cache + ".tmp"
            with open(tmp, "wb") as f:
                f.write(zlib.compress(raw, 6))
            os.replace(tmp, self.cache)
        except OSError:
            pass    # cache is an optimisation, never fatal

    def _paint_background(self, c):

        c.radial(T.BG_CENTRE[0], T.BG_CENTRE[1], 0.0,
                 T.BG_CENTRE[0], T.BG_CENTRE[1], T.BG_RADIUS, T.BG_STOPS)
        c.rect(0, 0, T.W, T.H)
        c.fill()

        # warm lower-left sweep
        c.radial(T.SWEEP_CENTRE[0], T.SWEEP_CENTRE[1], 0.0,
                 T.SWEEP_CENTRE[0], T.SWEEP_CENTRE[1], T.SWEEP_RADIUS,
                 [(0.0, T.SWEEP_COLOUR, T.SWEEP_ALPHA),
                  (0.55, T.SWEEP_COLOUR, T.SWEEP_ALPHA * 0.45),
                  (1.0, T.SWEEP_COLOUR, 0.0)])
        c.rect(0, 0, T.W, T.H)
        c.fill()

        c.line_width(1.0)
        c.dash(T.RING_DASH)
        c.colour(T.RING_DASHED, T.RING_DASHED_ALPHA)
        for r in (T.RING_R1, T.RING_R2):
            c.new_path()
            c.circle(T.CX, T.CY, r)
            c.stroke()
        c.dash(None)
        c.colour(T.RING_ACCENT, T.RING_ACCENT_ALPHA)
        c.new_path()
        c.circle(T.CX, T.CY, T.RING_R3)
        c.stroke()

    def background(self):
        if self._bg is None:
            self._build_background()
        if self.ox or self.oy:
            # Clear the whole buffer first: the offset background leaves a
            # band of stale pixels at one edge otherwise.
            c = self.ctx
            c.save()
            c.identity()
            c.colour("#000000")
            c.rect(0, 0, self.d.width, self.d.height)
            c.fill()
            c.restore()
        self.ctx.draw_surface(self._bg.surface, 0.0, 0.0)

    def present(self):
        """Finish the frame and page-flip it onto the panel."""
        c = self.ctx
        c.flush()
        self.last_ctx = c
        self.d.flip()

    # ---- icon sprites ----------------------------------------------------
    def _sized_sprite(self, name, icon_fn, size):
        """White alpha sprite for an icon at (a quantised) pixel size.

        Sprites are rendered at their final size and blitted 1:1 on purpose:
        letting cairo *scale* a mask costs 31 ms on this core versus 2.7 ms
        unscaled (measured), which is the difference between 8 fps and a smooth
        slide.  Sizes are bucketed to ICON_SIZE_STEP so the cache stays small;
        an 8 px step is invisible on a moving icon.
        """
        q = int(round(size / ICON_SIZE_STEP)) * ICON_SIZE_STEP
        q = max(ICON_SIZE_STEP, q)
        key = (name, q)
        sp = self._icons.get(key)
        if sp is None:
            n = q + 6                       # room for antialiased edges
            off = cf.Ctx(None, n, n, fmt=cf.FORMAT_ARGB32)
            icon_fn(off, n / 2.0, n / 2.0, float(q), "#ffffff", 1.0)
            off.flush()
            sp = (off, n)
            self._icons[key] = sp
        return sp

    def draw_icon(self, name, icon_fn, cx, cy, size, colour, alpha=1.0):
        """Blit an icon sprite, tinted.  Integer offsets keep the fast path."""
        if alpha <= 0.004:
            return
        sp, n = self._sized_sprite(name, icon_fn, size)
        c = self.ctx
        c.colour(colour, alpha)
        c.mask(sp.surface, float(int(cx - n / 2.0)), float(int(cy - n / 2.0)))

    def prewarm(self, items):
        """Build every icon sprite a slide will need, up front.

        Otherwise the first swipe pays for ~40 sprite renders and stutters.
        """
        steps = []
        s = T.SIDE_ICON
        while s <= T.CENTRE_ICON + ICON_SIZE_STEP:
            steps.append(s)
            s += ICON_SIZE_STEP
        for name, _label, icon_fn, _accent in items:
            for s in steps:
                self._sized_sprite(name, icon_fn, s)
        self._glow_sprite()

    # ---- shared chrome ---------------------------------------------------
    def status_line(self, text, bars=4):
        """Signal bars + monospace status text, centred like the mockup."""
        c = self.ctx
        c.font(T.STATUS_FONT, T.STATUS_SIZE)

        widths = [c.measure(ch).x_advance + T.STATUS_TRACKING for ch in text]
        text_w = sum(widths) - T.STATUS_TRACKING
        bars_w = len(T.BARS_HEIGHTS) * T.BARS_WIDTH \
            + (len(T.BARS_HEIGHTS) - 1) * T.BARS_GAP
        total = bars_w + T.BARS_TEXT_GAP + text_w
        x = T.CX - total / 2.0

        base = T.STATUS_BASELINE
        for i, h in enumerate(T.BARS_HEIGHTS):
            c.colour(T.BARS_COLOUR, 1.0 if i < bars else 0.22)
            c.new_path()
            c.rect(x, base - 2.0 - h, T.BARS_WIDTH, h)
            c.fill()
            x += T.BARS_WIDTH + T.BARS_GAP
        x += T.BARS_TEXT_GAP - T.BARS_GAP

        c.colour(T.STATUS_COLOUR)
        for ch, w in zip(text, widths):
            c.text(x, base, ch)
            x += w

    def label(self, text):
        c = self.ctx
        c.font(T.FONT, T.LABEL_SIZE, bold=True)
        c.colour(T.LABEL_COLOUR)
        c.text_centred(T.CX, T.LABEL_BASELINE, text)

    def dots(self, count, index):
        c = self.ctx
        widths = [T.DOT_ACTIVE_W if i == index else T.DOT_R * 2
                  for i in range(count)]
        total = sum(widths) + T.DOT_GAP * (count - 1)
        x = T.CX - total / 2.0
        for i, w in enumerate(widths):
            if i == index:
                c.colour(T.DOT_ON)
                c.new_path()
                c.round_rect(x, T.DOT_Y - T.DOT_R, w, T.DOT_R * 2, T.DOT_R)
                c.fill()
            else:
                c.colour(T.DOT_OFF)
                c.new_path()
                c.circle(x + T.DOT_R, T.DOT_Y, T.DOT_R)
                c.fill()
            x += w + T.DOT_GAP

    def _glow_sprite(self):
        """A white radial alpha ramp, built once and tinted at blit time."""
        if self._glow is None:
            r = T.CENTRE_GLOW_RADIUS
            n = int(r * 2.0)
            off = cf.Ctx(None, n, n, fmt=cf.FORMAT_ARGB32)
            off.radial(r, r, 0.0, r, r, r,
                       [(0.0, "#ffffff", T.CENTRE_GLOW_ALPHA),
                        (0.68, "#ffffff", 0.0)])
            off.new_path()
            off.circle(r, r, r)
            off.fill()
            off.flush()
            self._glow = off
        return self._glow

    def centre_glow(self, colour, cy=None):
        c = self.ctx
        r = T.CENTRE_GLOW_RADIUS
        cy = (T.CY - 18.0) if cy is None else cy
        c.colour(colour, 1.0)
        c.mask(self._glow_sprite().surface, T.CX - r, cy - r)

    # ---- cached menu chrome ---------------------------------------------
    def chrome_layer(self, status_text, bars, n, dots_i, glow=None):
        """Background + centre glow + status line + page dots, as one surface.

        During a slide none of these change, and redrawing them costs ~33 ms a
        frame (status line 15, dots 7, glow 10).  Cached, an animation frame
        only pays one blit.
        """
        key = (status_text, bars, n, dots_i, glow, self.ox, self.oy)
        if self._chrome_key == key and self._chrome is not None:
            return self._chrome
        if self._chrome is None:
            stride = T.W * 4
            self._chrome_buf = ctypes.create_string_buffer(stride * T.H)
            self._chrome = cf.Ctx(ctypes.addressof(self._chrome_buf),
                                  T.W, T.H, stride)
        # Draw the chrome unshifted; the panel offset is applied by the
        # destination context when this surface is blitted.
        saved_o = (self.ox, self.oy)
        self._ctx_override = self._chrome
        self.ox = self.oy = 0.0
        try:
            self.background()
            if glow:
                self.centre_glow(glow)
            self.status_line(status_text, bars)
            self.dots(n, dots_i)
            self._chrome.flush()
        finally:
            self._ctx_override = None
            self.ox, self.oy = saved_o
        self._chrome_key = key
        return self._chrome

    # ---- the carousel menu ----------------------------------------------
    def menu(self, items, index, status_text, bars=4):
        """items = [(name, label, icon_fn, accent), ...]"""
        self.menu_at(items, float(index), status_text, bars)

    def menu_at(self, items, p, status_text, bars=4, band=None,
                chrome_index=None):
        """Draw the carousel at continuous position `p` (p=1.5 is mid-slide).

        `band` limits the repaint to a (y0, y1) strip - used while sliding, when
        only the icon/label row changes and the rest of both buffers already
        holds the same chrome.

        `chrome_index` pins which item's glow and active dot the cached chrome
        shows.  A slide passes the starting index so the chrome never has to be
        rebuilt mid-animation (that rebuild is a ~47 ms hitch); the final frame
        is drawn without it and settles onto the new item.
        """
        n = len(items)
        near_i = chrome_index % n if chrome_index is not None \
            else int(round(p)) % n
        chrome = self.chrome_layer(status_text, bars, n, near_i,
                                   glow=items[near_i][3])
        c = self.ctx
        c.save()
        if band:
            c.rect(0, band[0], T.W, band[1] - band[0])
            c.clip()
        c.draw_surface(chrome.surface, 0.0, 0.0)

        base = int(math.floor(p))
        # One font selection for every label (fontconfig lookups are not free).
        c.font(T.FONT, T.LABEL_SIZE, bold=True)
        for k in range(base - 1, base + 3):
            s = k - p
            if abs(s) > 1.5:
                continue
            name, label, icon_fn, accent = items[k % n]
            x, size, alpha = carousel_slot(s)
            self.draw_icon(name, icon_fn, x, T.SIDE_CY, size, accent, alpha)

            # Labels cross-fade: only the one near the centre is legible.
            la = 1.0 - 2.0 * abs(s)
            if la > 0.01:
                c.colour(T.LABEL_COLOUR, la)
                c.text_centred(T.CX, T.LABEL_BASELINE, label)
        c.restore()

        # status line, dots and glow came in with the cached chrome
        self.present()

    # ---- security page ---------------------------------------------------
    def security(self, armed, motion, status_text, bars=4):
        """Big arm/disarm target with a state ring and a motion banner."""
        c = self.ctx
        self.background()

        state_col = T.ARMED if armed else T.DISARMED
        self.centre_glow(state_col)

        # state ring
        c.line_width(6.0)
        c.colour(state_col, 0.85)
        c.new_path()
        c.circle(T.CX, T.CY - 10.0, 132.0)
        c.stroke()

        icons.shield(c, T.CX, T.CY - 10.0, 150.0, state_col, 1.0, locked=armed)

        # Clear of the state ring (bottom at CY-10+132 = CY+122).
        c.font(T.FONT, 34.0, bold=True)
        c.colour(T.LABEL_COLOUR)
        c.text_centred(T.CX, T.CY + 166.0, "ARMED" if armed else "DISARMED")

        c.font(T.FONT, 20.0)
        c.colour(T.DIM)
        c.text_centred(T.CX, T.CY + 198.0, "tap to " +
                       ("disarm" if armed else "arm"))

        if motion:
            banner = "MOTION" if not armed else "MOTION - ALERT"
            col = T.ALERT if not armed else T.ARMED
            c.colour(col, 0.16)
            c.new_path()
            c.round_rect(T.CX - 150.0, 118.0, 300.0, 44.0, 22.0)
            c.fill()
            c.colour(col)
            c.line_width(1.5)
            c.new_path()
            c.round_rect(T.CX - 150.0, 118.0, 300.0, 44.0, 22.0)
            c.stroke()
            c.font(T.FONT, 21.0, bold=True)
            c.text_centred(T.CX, 147.0, banner)
        else:
            self.status_line(status_text, bars)

        self.exit_hint()
        self.present()

    # ---- settings page (camera controls) ---------------------------------
    def settings(self, controls, sel, status_text, bars=4):
        """controls = [(name, value, lo, hi), ...] laid out as arc sliders."""
        c = self.ctx
        self.background()
        self.status_line(status_text, bars)

        c.font(T.FONT, 24.0, bold=True)
        c.colour(T.LABEL_COLOUR)
        c.text_centred(T.CX, 150.0, "Camera")

        top = 208.0
        row = 74.0
        for i, (name, val, lo, hi) in enumerate(controls):
            y = top + i * row
            active = (i == sel)
            col = T.ACCENT_SETTINGS if active else T.DIM

            c.font(T.FONT, 19.0, bold=active)
            c.colour(T.LABEL_COLOUR if active else T.DIM)
            c.text(196.0, y - 12.0, name)

            txt = str(int(val))
            c.font(T.FONT, 19.0)
            c.colour(col)
            ext = c.measure(txt)
            c.text(524.0 - ext.x_advance, y - 12.0, txt)

            frac = 0.0 if hi <= lo else (float(val) - lo) / float(hi - lo)
            frac = max(0.0, min(1.0, frac))
            c.line_width(6.0)
            c.cap_round()
            c.colour("#ffffff", 0.10)
            c.new_path()
            c.move_to(196.0, y)
            c.line_to(524.0, y)
            c.stroke()
            if frac > 0.0:
                c.colour(col, 1.0 if active else 0.6)
                c.new_path()
                c.move_to(196.0, y)
                c.line_to(196.0 + 328.0 * frac, y)
                c.stroke()
            if active:
                c.colour(T.ACCENT_SETTINGS)
                c.new_path()
                c.circle(196.0 + 328.0 * frac, y, 9.0)
                c.fill()

        self.exit_hint()
        self.present()

    # ---- camera page (placeholder frame while gst owns the CRTC) ---------
    def camera_wait(self, message, status_text, bars=4):
        c = self.ctx
        self.background()
        self.status_line(status_text, bars)
        self.centre_glow(T.ACCENT_CAMERA)
        icons.camera(c, T.CX, T.CY - 20.0, 150.0, T.ACCENT_CAMERA)
        c.font(T.FONT, 22.0)
        c.colour(T.DIM)
        c.text_centred(T.CX, T.CY + 120.0, message)
        self.exit_hint()
        self.present()

    def exit_hint(self):
        """Text hint at the bottom - leaving a page is a double-tap now."""
        c = self.ctx
        c.font(T.FONT, 15.0)
        c.colour(T.DIM, 0.7)
        c.text_centred(T.CX, 664.0, "double-tap to exit", tracking=1.4)

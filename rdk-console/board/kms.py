"""Minimal pure-Python DRM/KMS dumb-framebuffer client.

Why this exists: the SAM9X75 RDK Buildroot image has **no /dev/fb0**
(CONFIG_FB_DEVICE is off - only the in-kernel DRM fbdev *emulation* is
registered) and ships no Python graphics bindings and no compiler.  So the
console talks to /dev/dri/card1 straight through ctypes + ioctl, allocates a
dumb scanout buffer, mmaps it, and hands the raw pointer to cairo.

Only the handful of ioctls we need are wired up.  Struct layouts are the
uapi ones from include/uapi/drm/drm{,_mode}.h; every ioctl number is derived
from ctypes.sizeof() at runtime so the 32-bit ARM padding is whatever the
kernel actually expects rather than something hand-counted.
"""

import ctypes
import fcntl
import mmap
import os
import select

u32 = ctypes.c_uint32
u64 = ctypes.c_uint64

DRM_IOCTL_BASE = 0x64

DRM_MODE_CONNECTED = 1
DRM_MODE_PAGE_FLIP_EVENT = 0x01


def _iowr(nr, struct_type):
    """_IOWR(DRM_IOCTL_BASE, nr, struct_type)"""
    return (3 << 30) | ((ctypes.sizeof(struct_type) & 0x3FFF) << 16) \
        | (DRM_IOCTL_BASE << 8) | nr


def _io(nr):
    """_IO(DRM_IOCTL_BASE, nr) - no payload."""
    return (DRM_IOCTL_BASE << 8) | nr


class ModeInfo(ctypes.Structure):
    _fields_ = [
        ("clock", u32),
        ("hdisplay", ctypes.c_uint16), ("hsync_start", ctypes.c_uint16),
        ("hsync_end", ctypes.c_uint16), ("htotal", ctypes.c_uint16),
        ("hskew", ctypes.c_uint16),
        ("vdisplay", ctypes.c_uint16), ("vsync_start", ctypes.c_uint16),
        ("vsync_end", ctypes.c_uint16), ("vtotal", ctypes.c_uint16),
        ("vscan", ctypes.c_uint16),
        ("vrefresh", u32),
        ("flags", u32),
        ("type", u32),
        ("name", ctypes.c_char * 32),
    ]


class CardRes(ctypes.Structure):
    _fields_ = [
        ("fb_id_ptr", u64), ("crtc_id_ptr", u64),
        ("connector_id_ptr", u64), ("encoder_id_ptr", u64),
        ("count_fbs", u32), ("count_crtcs", u32),
        ("count_connectors", u32), ("count_encoders", u32),
        ("min_width", u32), ("max_width", u32),
        ("min_height", u32), ("max_height", u32),
    ]


class GetConnector(ctypes.Structure):
    _fields_ = [
        ("encoders_ptr", u64), ("modes_ptr", u64),
        ("props_ptr", u64), ("prop_values_ptr", u64),
        ("count_modes", u32), ("count_props", u32),
        ("count_encoders", u32), ("encoder_id", u32),
        ("connector_id", u32), ("connector_type", u32),
        ("connector_type_id", u32), ("connection", u32),
        ("mm_width", u32), ("mm_height", u32),
        ("subpixel", u32), ("pad", u32),
    ]


class GetEncoder(ctypes.Structure):
    _fields_ = [
        ("encoder_id", u32), ("encoder_type", u32), ("crtc_id", u32),
        ("possible_crtcs", u32), ("possible_clones", u32),
    ]


class Crtc(ctypes.Structure):
    _fields_ = [
        ("set_connectors_ptr", u64),
        ("count_connectors", u32), ("crtc_id", u32), ("fb_id", u32),
        ("x", u32), ("y", u32), ("gamma_size", u32), ("mode_valid", u32),
        ("mode", ModeInfo),
    ]


class CreateDumb(ctypes.Structure):
    _fields_ = [
        ("height", u32), ("width", u32), ("bpp", u32), ("flags", u32),
        ("handle", u32), ("pitch", u32), ("size", u64),
    ]


class MapDumb(ctypes.Structure):
    _fields_ = [("handle", u32), ("pad", u32), ("offset", u64)]


class DestroyDumb(ctypes.Structure):
    _fields_ = [("handle", u32)]


class FbCmd(ctypes.Structure):
    _fields_ = [
        ("fb_id", u32), ("width", u32), ("height", u32), ("pitch", u32),
        ("bpp", u32), ("depth", u32), ("handle", u32),
    ]


class PageFlip(ctypes.Structure):
    _fields_ = [
        ("crtc_id", u32), ("fb_id", u32), ("flags", u32), ("reserved", u32),
        ("user_data", u64),
    ]


IOCTL_SET_MASTER = _io(0x1E)
IOCTL_DROP_MASTER = _io(0x1F)
IOCTL_GETRESOURCES = _iowr(0xA0, CardRes)
IOCTL_GETCRTC = _iowr(0xA1, Crtc)
IOCTL_SETCRTC = _iowr(0xA2, Crtc)
IOCTL_GETENCODER = _iowr(0xA6, GetEncoder)
IOCTL_GETCONNECTOR = _iowr(0xA7, GetConnector)
IOCTL_ADDFB = _iowr(0xAE, FbCmd)
IOCTL_RMFB = _iowr(0xAF, u32)
IOCTL_PAGE_FLIP = _iowr(0xB0, PageFlip)
IOCTL_CREATE_DUMB = _iowr(0xB2, CreateDumb)
IOCTL_MAP_DUMB = _iowr(0xB3, MapDumb)
IOCTL_DESTROY_DUMB = _iowr(0xB4, DestroyDumb)


class _Buffer:
    """One mapped dumb buffer plus the DRM framebuffer that wraps it."""

    __slots__ = ("handle", "fb_id", "pitch", "size", "mm", "view", "addr")

    def __init__(self, handle, fb_id, pitch, size, mm, view, addr):
        self.handle = handle
        self.fb_id = fb_id
        self.pitch = pitch
        self.size = size
        self.mm = mm
        self.view = view
        self.addr = addr


class Display:
    """A connected connector + CRTC + double-buffered dumb framebuffers.

    Draw into `addr` (the back buffer) and call `flip()` to present it.
    """

    def __init__(self, path="/dev/dri/card1", h_shift=0, v_shift=0, nbuf=2):
        self.h_shift = h_shift
        self.v_shift = v_shift
        self.nbuf = max(1, nbuf)
        self.bufs = []
        self.front = 0
        self.fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
        self._poll = select.poll()
        self._poll.register(self.fd, select.POLLIN)
        self._flip_pending = False
        self.fb_id = None
        self.saved = None
        try:
            self._setup()
        except Exception:
            self.close()
            raise

    # ---- ioctl plumbing -------------------------------------------------
    def _ioctl(self, req, arg):
        fcntl.ioctl(self.fd, req, arg)
        return arg

    def _connector(self, cid):
        """Two-pass GETCONNECTOR: first for the counts, then for the modes."""
        c = GetConnector(connector_id=cid)
        self._ioctl(IOCTL_GETCONNECTOR, c)
        n = c.count_modes
        modes = (ModeInfo * n)() if n else None
        c2 = GetConnector(connector_id=cid, count_modes=n)
        if n:
            c2.modes_ptr = ctypes.cast(modes, ctypes.c_void_p).value
        self._ioctl(IOCTL_GETCONNECTOR, c2)
        return c2, modes

    def _setup(self):
        try:
            fcntl.ioctl(self.fd, IOCTL_SET_MASTER, 0)
        except OSError:
            pass  # already master, or someone else holds it

        res = CardRes()
        self._ioctl(IOCTL_GETRESOURCES, res)
        if not res.count_connectors or not res.count_crtcs:
            raise RuntimeError("card exposes no connectors/crtcs")
        # Ask only for the two arrays we allocate: a non-zero count with a
        # NULL pointer makes the kernel copy into address 0 -> EFAULT.
        conn_ids = (u32 * res.count_connectors)()
        crtc_ids = (u32 * res.count_crtcs)()
        res2 = CardRes(count_connectors=res.count_connectors,
                       count_crtcs=res.count_crtcs)
        res2.connector_id_ptr = ctypes.cast(conn_ids, ctypes.c_void_p).value
        res2.crtc_id_ptr = ctypes.cast(crtc_ids, ctypes.c_void_p).value
        self._ioctl(IOCTL_GETRESOURCES, res2)

        chosen = None
        for cid in conn_ids:
            conn, modes = self._connector(cid)
            if conn.connection == DRM_MODE_CONNECTED and conn.count_modes:
                chosen = (conn, modes[0])
                break
        if not chosen:
            raise RuntimeError("no connected connector with a mode")
        conn, mode = chosen

        self.connector_id = conn.connector_id
        self.base_mode = ModeInfo.from_buffer_copy(mode)
        self.mode = mode
        self.width = mode.hdisplay
        self.height = mode.vdisplay
        if self.h_shift or self.v_shift:
            self.tune_mode(self.h_shift, self.v_shift)

        # Prefer the CRTC the connector's encoder already drives.
        crtc_id = 0
        if conn.encoder_id:
            enc = GetEncoder(encoder_id=conn.encoder_id)
            try:
                self._ioctl(IOCTL_GETENCODER, enc)
                crtc_id = enc.crtc_id
            except OSError:
                pass
        self.crtc_id = crtc_id or crtc_ids[0]

        # Remember the CRTC state so close() can hand the display back.
        saved = Crtc(crtc_id=self.crtc_id)
        try:
            self._ioctl(IOCTL_GETCRTC, saved)
            self.saved = saved
        except OSError:
            self.saved = None

        # Two XRGB8888 dumb buffers -> cairo CAIRO_FORMAT_RGB24.  Drawing
        # straight into the scanned-out buffer is visible as a flicker on every
        # repaint (and would make an animation tear), so we draw into the back
        # buffer and page-flip.
        for _ in range(self.nbuf):
            self.bufs.append(self._make_buffer())
        self.pitch = self.bufs[0].pitch
        self.size = self.bufs[0].size
        self.front = 0
        self.fb_id = self.bufs[0].fb_id

        self.set_crtc()

    def _make_buffer(self):
        dumb = CreateDumb(width=self.width, height=self.height, bpp=32)
        self._ioctl(IOCTL_CREATE_DUMB, dumb)

        fb = FbCmd(width=self.width, height=self.height, pitch=dumb.pitch,
                   bpp=32, depth=24, handle=dumb.handle)
        self._ioctl(IOCTL_ADDFB, fb)

        mp = MapDumb(handle=dumb.handle)
        self._ioctl(IOCTL_MAP_DUMB, mp)
        mm = mmap.mmap(self.fd, int(dumb.size), offset=int(mp.offset))
        view = (ctypes.c_char * int(dumb.size)).from_buffer(mm)
        addr = ctypes.addressof(view)
        ctypes.memset(addr, 0, int(dumb.size))
        return _Buffer(dumb.handle, fb.fb_id, dumb.pitch, int(dumb.size),
                       mm, view, addr)

    @property
    def back(self):
        """Index of the buffer to draw into."""
        return (self.front + 1) % self.nbuf

    @property
    def addr(self):
        """Address of the back buffer (what callers should draw into)."""
        return self.bufs[self.back].addr

    def _drain(self, timeout_ms):
        """Consume a queued page-flip completion event."""
        if self._poll.poll(timeout_ms):
            try:
                os.read(self.fd, 1024)
            except OSError:
                pass
            return True
        return False

    def flip(self, timeout_ms=120):
        """Show the back buffer.

        The completion event for the *previous* flip is collected here rather
        than after issuing this one, so the wait for vblank overlaps with the
        caller's drawing instead of adding a whole frame of latency.

        Falls back to a modeset if the driver has no page-flip support, so the
        console still works (with the old flicker) in that case.
        """
        if self._flip_pending:
            self._drain(timeout_ms)
            self._flip_pending = False

        nxt = self.back
        req = PageFlip(crtc_id=self.crtc_id, fb_id=self.bufs[nxt].fb_id,
                       flags=DRM_MODE_PAGE_FLIP_EVENT)
        try:
            self._ioctl(IOCTL_PAGE_FLIP, req)
        except OSError:
            self.front = nxt
            self.fb_id = self.bufs[nxt].fb_id
            try:
                self.set_crtc()
            except OSError:
                pass
            return False
        self._flip_pending = True
        self.front = nxt
        self.fb_id = self.bufs[nxt].fb_id
        return True

    def tune_mode(self, h_shift=0, v_shift=0, min_hsa=8, min_hbp=6,
                  min_vsa=2, min_vbp=2):
        """Move the active window earlier in the line/frame by `shift` pixels.

        This board's panel puts our framebuffer ~50 px to the right of the
        glass: it starts its active window before our RGB data arrives.  Sending
        the data earlier relative to sync fixes it, and the way to do that is to
        take pixels out of (sync + back porch) and hand them to the front porch.
        `htotal`/`vtotal` are left alone, so the pixel clock and refresh rate do
        not change - only where the active region sits.

        Returns the mode actually programmed, or raises ValueError if the
        requested shift needs more blanking than the mode has.
        """
        m = ModeInfo.from_buffer_copy(self.base_mode)

        if h_shift:
            hsa = m.hsync_end - m.hsync_start
            hbp = m.htotal - m.hsync_end
            target = hsa + hbp - h_shift
            if target < min_hsa + min_hbp:
                raise ValueError(
                    "h_shift %d needs %d px of sync+back porch, only %d "
                    "available (min %d)" % (h_shift, h_shift, hsa + hbp,
                                            min_hsa + min_hbp))
            new_hbp = max(min_hbp, min(hbp, target - min_hsa))
            new_hsa = target - new_hbp
            m.hsync_start = m.htotal - new_hsa - new_hbp
            m.hsync_end = m.hsync_start + new_hsa

        if v_shift:
            vsa = m.vsync_end - m.vsync_start
            vbp = m.vtotal - m.vsync_end
            target = vsa + vbp - v_shift
            if target < min_vsa + min_vbp:
                raise ValueError("v_shift %d exceeds available blanking"
                                 % v_shift)
            new_vbp = max(min_vbp, min(vbp, target - min_vsa))
            new_vsa = target - new_vbp
            m.vsync_start = m.vtotal - new_vsa - new_vbp
            m.vsync_end = m.vsync_start + new_vsa

        self.mode = m
        return m

    def describe_mode(self, m=None):
        m = m or self.mode
        return ("H %d | fp %d sync %d bp %d | total %d    "
                "V %d | fp %d sync %d bp %d | total %d"
                % (m.hdisplay, m.hsync_start - m.hdisplay,
                   m.hsync_end - m.hsync_start, m.htotal - m.hsync_end,
                   m.htotal,
                   m.vdisplay, m.vsync_start - m.vdisplay,
                   m.vsync_end - m.vsync_start, m.vtotal - m.vsync_end,
                   m.vtotal))

    def set_crtc(self):
        """Point the CRTC at our framebuffer with the panel's native mode."""
        conns = (u32 * 1)(self.connector_id)
        req = Crtc(crtc_id=self.crtc_id, fb_id=self.fb_id, x=0, y=0,
                   mode_valid=1, mode=self.mode, count_connectors=1,
                   set_connectors_ptr=ctypes.cast(conns, ctypes.c_void_p).value)
        self._ioctl(IOCTL_SETCRTC, req)

    def drop_master(self):
        """Release DRM master so another process (gst kmssink) can modeset."""
        if self._flip_pending:
            self._drain(50)
            self._flip_pending = False
        try:
            fcntl.ioctl(self.fd, IOCTL_DROP_MASTER, 0)
        except OSError:
            pass

    def set_master(self):
        """Re-take DRM master and restore our framebuffer."""
        fcntl.ioctl(self.fd, IOCTL_SET_MASTER, 0)
        self._flip_pending = False
        self.set_crtc()

    def close(self):
        for b in self.bufs:
            # The ctypes view must be dropped before the mmap it borrows from.
            b.view = None
            if b.mm is not None:
                try:
                    b.mm.close()
                except BufferError:
                    pass        # a cairo surface still holds it; leak the map
                b.mm = None
            try:
                fcntl.ioctl(self.fd, IOCTL_RMFB, u32(b.fb_id))
            except OSError:
                pass
            try:
                self._ioctl(IOCTL_DESTROY_DUMB, DestroyDumb(handle=b.handle))
            except OSError:
                pass
        self.bufs = []
        self.fb_id = None
        if self.fd is not None:
            try:
                self._poll.unregister(self.fd)
            except (OSError, KeyError):
                pass
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


if __name__ == "__main__":
    import sys
    shift = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    d = Display(h_shift=shift)
    print("connector", d.connector_id, "crtc", d.crtc_id,
          "%dx%d" % (d.width, d.height), "pitch", d.pitch, "size", d.size,
          "buffers", len(d.bufs))
    print("mode:", d.describe_mode())
    ok = d.flip()
    print("page flip:", "ok" if ok else "unsupported (fell back to modeset)")
    d.close()

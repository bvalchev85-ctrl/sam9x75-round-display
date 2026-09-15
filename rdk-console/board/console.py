"""RDK home-security console - main application.

Round 720x720 touch UI on the SAM9X75 Round Display Kit:

  Security   arm / disarm, motion banner
  Camera     live MJPEG from the PIC64 webcam (gst-launch + kmssink)
  Settings   camera sliders, pushed to the PIC64 control API

Swipe left/right (or tap a side icon) to move the carousel, tap the centre to
open a page, and double-tap anywhere to leave it.  Everything is drawn by cairo into
a DRM dumb buffer - see kms.py for why there is no /dev/fb0 involved.

    python3 console.py [--once] [--no-camera]
"""

import signal
import subprocess
import sys
import threading
import time

import cairo_ffi as cf
import config as C
import icons
import theme as T
from camera import Camera
from kms import Display
from screens import SLIDE_BAND, Renderer


def touch_backend(name):
    """Pick the touch implementation.

    'i2c' polls the GT9271 over I2C because this board's touch interrupt never
    fires (see phase4-console-app.md §5); 'evdev' is the normal path and works
    once that is fixed.  Both expose the same poll()/close() contract.
    """
    if name == "evdev":
        from touch import Touch
    else:
        from touch_i2c import Touch
    return Touch

MENU, SECURITY, CAMERA, SETTINGS = "menu", "security", "camera", "settings"

ITEMS = [
    (SECURITY, "Security", icons.shield, T.ACCENT_SECURITY),
    (CAMERA, "Camera", icons.camera, T.ACCENT_CAMERA),
    (SETTINGS, "Settings", icons.gear, T.ACCENT_SETTINGS),
]

# Hit zones (x, y, radius) on the 720x720 circle.
HIT_CENTRE = (T.CX, T.CY, 150.0)
HIT_LEFT = (T.SIDE_LEFT_CX, T.SIDE_CY, 70.0)
HIT_RIGHT = (T.SIDE_RIGHT_CX, T.SIDE_CY, 70.0)

SLIDER_X0, SLIDER_X1 = 196.0, 524.0
SLIDER_TOP, SLIDER_ROW = 208.0, 74.0

DUMP_PATH = "/tmp/rdk-frame.png"

SLIDE_MS = 260.0            # carousel slide duration
DOUBLE_TAP_MS = 380.0       # second tap within this window = exit the page
DOUBLE_TAP_DIST = 120       # px - the two taps must be roughly co-located


def ease_out_cubic(f):
    g = 1.0 - f
    return 1.0 - g * g * g


def hit(zone, x, y):
    cx, cy, r = zone
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def link_state(iface="eth0"):
    """(up, bars) for the status line."""
    try:
        with open("/sys/class/net/%s/operstate" % iface) as f:
            up = f.read().strip() == "up"
    except OSError:
        return False, 0
    if not up:
        return False, 0
    try:
        with open("/sys/class/net/%s/speed" % iface) as f:
            speed = int(f.read().strip())
    except (OSError, ValueError):
        speed = 0
    bars = 4 if speed >= 1000 else 3 if speed >= 100 else 2
    return True, bars


class App:
    def __init__(self, cfg, use_camera=True):
        self.cfg = cfg
        # This panel puts the framebuffer ~50 px right of the glass.  Retiming
        # the mode is the proper fix (keeps all 720 columns); if the kernel ever
        # refuses the tuned mode, fall back to shifting what we draw.
        offset = (0.0, 0.0)
        try:
            self.display = Display(h_shift=cfg["PANEL_H_SHIFT"],
                                   v_shift=cfg["PANEL_V_SHIFT"])
        except (OSError, ValueError) as exc:
            print("panel retiming failed (%s); using a drawing offset" % exc,
                  flush=True)
            self.display = Display()
            offset = (-float(cfg["PANEL_H_SHIFT"]),
                      -float(cfg["PANEL_V_SHIFT"]))
        if cfg["X_OFFSET"] or cfg["Y_OFFSET"]:
            offset = (float(cfg["X_OFFSET"]), float(cfg["Y_OFFSET"]))
        self.r = Renderer(self.display, offset=offset)

        Touch = touch_backend(cfg["TOUCH_BACKEND"])
        self.touch = Touch(width=self.display.width,
                           height=self.display.height,
                           swap_xy=cfg["TOUCH_SWAP_XY"],
                           invert_x=cfg["TOUCH_INVERT_X"],
                           invert_y=cfg["TOUCH_INVERT_Y"])
        self.cam = Camera(cfg) if use_camera else None

        state = C.read_state()
        self.armed = bool(state.get("armed", False))
        self.motion = False
        self.index = 1                  # start on Camera, like the mockup
        self.page = MENU
        self.sel = 0                    # selected slider on the settings page
        self.settings = {}
        self.dragging = False
        self.dirty = True
        self._status = ""
        self._status_at = 0.0
        self._bars = 0
        self.running = True
        self._dump = False          # set by SIGUSR1, serviced in the loop
        self._last_tap = None       # (x, y, t) for double-tap detection
        self._time_synced = False
        self._prober = None
        self._pending = None        # (fn, deadline) deferred single-tap action

    # ---- status ---------------------------------------------------------
    def status_text(self, force=False):
        now = time.monotonic()
        if force or not self._status or (now - self._status_at) > \
                self.cfg["STATUS_PERIOD"]:
            up, bars = link_state()
            self._bars = bars
            host = self.cam.host if self.cam else None
            where = "eth0" if up else "link down"
            if up and self.cam and not host:
                where = "no camera"
            # Until the clock is set there is no point showing 1970.
            clock = (time.strftime("%H:%M")
                     if time.gmtime().tm_year >= 2020 else "--:--")
            self._status = "%s  ·  %s" % (where, clock)
            self._status_at = now
            self.dirty = True
        return self._status

    # ---- background camera probe ----------------------------------------
    def start_prober(self):
        """Re-probe the camera off the UI thread.

        The console starts at boot (S99) moments after DHCP, so the first probe
        can easily run before the LAN is usable - and a failing probe blocks for
        up to 3 x PROBE_TIMEOUT, which would freeze the UI if done inline.  A
        daemon thread keeps `cam.host` fresh without stalling a frame.
        """
        if self.cam is None or self._prober is not None:
            return

        def loop():
            while self.running:
                had = self.cam.host
                try:
                    self.cam.probe(force=True)
                except Exception:
                    pass
                if self.cam.host != had:
                    self.status_text(force=True)
                self.sync_clock()
                waited = 0.0
                period = float(self.cfg["CAMERA_RETRY"])
                while self.running and waited < period:
                    time.sleep(0.25)
                    waited += 0.25

        self._prober = threading.Thread(target=loop, daemon=True)
        self._prober.start()

    def sync_clock(self):
        """Set the clock once, from the camera server's HTTP Date header."""
        if self._time_synced:
            return
        if time.gmtime().tm_year >= 2020:
            self._time_synced = True     # already sane (RTC or -SyncTime)
            return
        when = self.cam.server_time() if self.cam else None
        if when is None:
            return
        try:
            subprocess.run(["date", "-u", "-s",
                            when.strftime("%Y-%m-%d %H:%M:%S")],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return
        self._time_synced = True
        self.status_text(force=True)

    # ---- drawing --------------------------------------------------------
    def draw(self):
        st = self.status_text()
        if self.page == MENU:
            self.r.menu(ITEMS, self.index, st, self._bars)
        elif self.page == SECURITY:
            self.r.security(self.armed, self.motion, st, self._bars)
        elif self.page == SETTINGS:
            self.r.settings(self.controls(), self.sel, st, self._bars)
        elif self.page == CAMERA:
            # Only drawn while the feed is not up; gst owns the CRTC otherwise.
            if self.cam and self.cam.host:
                self.r.camera_wait("starting stream ...", st, self._bars)
            else:
                self.r.camera_wait("camera offline", st, self._bars)
        self.dirty = False

    def controls(self):
        out = []
        for label, key in self.cfg["CONTROLS"]:
            val = self.settings.get(key, 0)
            try:
                val = int(val)
            except (TypeError, ValueError):
                val = 0
            out.append((label, val, self.cfg["CONTROL_MIN"],
                        self.cfg["CONTROL_MAX"]))
        return out

    # ---- page transitions ------------------------------------------------
    def open_page(self, page):
        if page == CAMERA:
            self.enter_camera()
            return
        if page == SETTINGS:
            self.page = SETTINGS
            self.dirty = True
            self.draw()
            if self.cam:
                self.cam.probe()
                got = self.cam.get_settings()
                if got:
                    self.settings = got
            self.dirty = True
            return
        self.page = page
        self.dirty = True

    def enter_camera(self):
        self.page = CAMERA
        self.dirty = True
        self.draw()
        if not self.cam:
            return
        if not self.cam.probe(force=True):
            self.dirty = True
            return
        self.draw()
        if not self.cam.start(self.display):
            self.leave_camera()

    def leave_camera(self):
        # cam.stop() re-takes DRM master and re-points the CRTC at our dumb
        # buffer, which is still mapped - so the renderer (and its cached
        # background/glow surfaces) stays valid and is deliberately reused.
        if self.cam:
            self.cam.stop(self.display)
        self.page = MENU
        self.dirty = True

    def toggle_armed(self):
        self.armed = not self.armed
        C.write_state({"armed": self.armed})
        self.dirty = True

    def slide_to(self, step):
        """Animate the carousel one slot in `step` direction (+1 / -1)."""
        n = len(ITEMS)
        start = float(self.index)
        end = start + step
        # Both buffers must hold identical chrome before switching to
        # band-limited frames, or the strip outside the band shows the frame
        # from two flips ago.
        for _ in range(len(self.display.bufs)):
            self.r.menu_at(ITEMS, start, self._status, self._bars)
        t0 = time.monotonic()
        while True:
            f = (time.monotonic() - t0) * 1000.0 / SLIDE_MS
            if f >= 1.0:
                break
            p = start + (end - start) * ease_out_cubic(f)
            self.r.menu_at(ITEMS, p, self._status, self._bars,
                           band=SLIDE_BAND, chrome_index=self.index)
            # Keep the controller's report buffer drained so a queued stale
            # touch does not fire the moment the animation ends.
            self.touch.poll(0)
        self.index = int(end) % n
        # Land on a full frame so both buffers are consistent again.
        self.r.menu_at(ITEMS, float(self.index), self._status, self._bars)
        self.r.menu_at(ITEMS, float(self.index), self._status, self._bars)
        self.dirty = False

    # ---- tap arbitration -------------------------------------------------
    def defer(self, fn):
        """Run `fn` only if no second tap arrives (so a double-tap can exit)."""
        self._pending = (fn, time.monotonic() + DOUBLE_TAP_MS / 1000.0)

    def service_pending(self):
        if self._pending and time.monotonic() >= self._pending[1]:
            fn, _ = self._pending
            self._pending = None
            fn()

    def is_double_tap(self, x, y):
        last = self._last_tap
        now = time.monotonic()
        self._last_tap = (x, y, now)
        if not last:
            return False
        if (now - last[2]) * 1000.0 > DOUBLE_TAP_MS:
            return False
        return (abs(x - last[0]) <= DOUBLE_TAP_DIST
                and abs(y - last[1]) <= DOUBLE_TAP_DIST)

    def exit_page(self):
        self._pending = None
        self._last_tap = None
        if self.page == CAMERA:
            self.leave_camera()
        else:
            self.page = MENU
            self.dirty = True

    # ---- input ----------------------------------------------------------
    def on_event(self, kind, x, y, extra):
        # A double-tap leaves whatever page we are on (there is no back arrow).
        if kind == "tap" and self.page != MENU:
            if self.is_double_tap(x, y):
                self.exit_page()
                return

        if self.page == CAMERA:
            return              # gst owns the display; only the exit above

        if kind == "swipe" and self.page == MENU:
            self.slide_to(1 if extra == "left" else -1)
            return

        if self.page == MENU and kind == "tap":
            if hit(HIT_CENTRE, x, y):
                self.open_page(ITEMS[self.index][0])
            elif hit(HIT_LEFT, x, y):
                self.slide_to(-1)
            elif hit(HIT_RIGHT, x, y):
                self.slide_to(1)
            return

        if self.page == SECURITY and kind == "tap":
            if hit((T.CX, T.CY - 10.0, 140.0), x, y):
                # Deferred, so a double-tap exits instead of toggling twice.
                self.defer(self.toggle_armed)
            return

        if self.page == SETTINGS:
            row = self.row_at(y)
            if kind == "down" and row is not None and \
                    SLIDER_X0 - 24 <= x <= SLIDER_X1 + 24:
                self.sel = row
                self.dragging = True
                self.set_slider(row, x)
            elif kind == "move" and self.dragging:
                self.set_slider(self.sel, x)
            elif kind == "up" and self.dragging:
                self.dragging = False
                self.push_setting(self.sel)
            return

    def row_at(self, y):
        for i in range(len(self.cfg["CONTROLS"])):
            cy = SLIDER_TOP + i * SLIDER_ROW
            if abs(y - cy) <= 30:
                return i
        return None

    def set_slider(self, row, x):
        lo, hi = self.cfg["CONTROL_MIN"], self.cfg["CONTROL_MAX"]
        frac = (x - SLIDER_X0) / (SLIDER_X1 - SLIDER_X0)
        frac = min(max(frac, 0.0), 1.0)
        key = self.cfg["CONTROLS"][row][1]
        self.settings[key] = int(round(lo + frac * (hi - lo)))
        self.dirty = True

    def push_setting(self, row):
        """Send just this key - a whole-dict POST would clobber the others."""
        if not self.cam or not self.cam.host:
            return
        key = self.cfg["CONTROLS"][row][1]
        got = self.cam.set_settings({key: self.settings.get(key, 0)})
        if got:
            self.settings = got
        self.dirty = True

    # ---- main loop -------------------------------------------------------
    def run(self, once=False):
        if self.cam:
            self.cam.probe()
            self.start_prober()
        self.status_text(force=True)
        self.r.prewarm(ITEMS)       # so the first swipe does not stutter
        self.draw()
        if once:
            return
        while self.running:
            for ev in self.touch.poll(120):
                self.on_event(*ev)
            self.service_pending()
            if self._dump:
                self._dump = False
                try:
                    # last_ctx is the buffer just presented; self.ctx is the
                    # next (stale) back buffer.
                    self.r.last_ctx.write_png(DUMP_PATH)
                except Exception as exc:            # debug aid, never fatal
                    print("dump failed: %s" % exc, flush=True)
            if self.page == CAMERA and self.cam and not self.cam.alive() \
                    and self.cam.proc is not None:
                self.leave_camera()           # pipeline died on its own
            self.status_text()
            if self.dirty and self.page != CAMERA:
                self.draw()
            elif self.dirty and self.page == CAMERA and not \
                    (self.cam and self.cam.alive()):
                self.draw()

    def stop(self, *_):
        self.running = False

    def request_dump(self, *_):
        """SIGUSR1: write the current frame to DUMP_PATH.

        The panel can only be checked by eye otherwise; this makes the live
        screen inspectable over ssh (`kill -USR1 $(cat /var/run/rdk-console.pid)`).
        """
        self._dump = True

    def close(self):
        if self.cam:
            self.cam.stop(self.display, retake=False)
        self.touch.close()
        self.r.ctx.close()
        self.display.close()


def main():
    cfg = C.load()
    app = App(cfg, use_camera="--no-camera" not in sys.argv)
    signal.signal(signal.SIGTERM, app.stop)
    signal.signal(signal.SIGINT, app.stop)
    signal.signal(signal.SIGUSR1, app.request_dump)
    try:
        app.run(once="--once" in sys.argv)
    finally:
        app.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

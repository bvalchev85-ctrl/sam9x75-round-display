"""Touchscreen input, read straight from evdev (no python-evdev on the image).

The panel's Goodix GT9271 is a multitouch-B device; the console only needs one
finger, so slot 0 is tracked and the rest ignored.  Axis ranges come from
EVIOCGABS so coordinates are scaled to the 720x720 panel regardless of what
the controller reports.
"""

import fcntl
import os
import select
import struct
import time

# struct input_event: on 32-bit ARM this is {ulong sec; ulong usec; u16 type;
# u16 code; s32 value} - native sizes keep it correct on either word size.
EVENT_FMT = "llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FMT)

EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03

SYN_REPORT = 0x00
BTN_TOUCH = 0x14A

ABS_X = 0x00
ABS_Y = 0x01
ABS_MT_SLOT = 0x2F
ABS_MT_POSITION_X = 0x35
ABS_MT_POSITION_Y = 0x36
ABS_MT_TRACKING_ID = 0x39

TAP_MAX_MS = 600
TAP_MAX_MOVE = 28          # px - beyond this it is a drag, not a tap
SWIPE_MIN = 70             # px of travel to count as a swipe


def _eviocgabs(axis):
    """_IOR('E', 0x40 + axis, struct input_absinfo) - 6 x s32 = 24 bytes."""
    return (2 << 30) | (24 << 16) | (0x45 << 8) | (0x40 + axis)


def find_device(match="Goodix"):
    """Locate the touchscreen's event node from /proc/bus/input/devices."""
    try:
        with open("/proc/bus/input/devices") as f:
            blocks = f.read().split("\n\n")
    except OSError:
        blocks = []
    for b in blocks:
        if match.lower() in b.lower():
            for line in b.splitlines():
                if line.startswith("H:"):
                    for tok in line.split():
                        if tok.startswith("event"):
                            return "/dev/input/" + tok
    for cand in ("/dev/input/event0", "/dev/input/event1"):
        if os.path.exists(cand):
            return cand
    raise RuntimeError("no touch device found")


class Touch:
    """Pumps evdev and yields ('tap'|'swipe'|'down'|'move'|'up', x, y, extra).

    Coordinates are in panel pixels.  `swap_xy`/`invert_x`/`invert_y` correct
    a controller mounted at a different orientation than the display.
    """

    def __init__(self, path=None, width=720, height=720,
                 swap_xy=False, invert_x=False, invert_y=False):
        self.path = path or find_device()
        self.fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
        self.width = width
        self.height = height
        self.swap_xy = swap_xy
        self.invert_x = invert_x
        self.invert_y = invert_y

        self.rx = self._range(ABS_MT_POSITION_X) or self._range(ABS_X) \
            or (0, width - 1)
        self.ry = self._range(ABS_MT_POSITION_Y) or self._range(ABS_Y) \
            or (0, height - 1)

        self._slot = 0
        self._raw = [None, None]      # latest raw x, y
        self._down = False
        self._start = None            # (x, y, t) of the press
        self._last = None             # (x, y) scaled
        self._poll = select.poll()
        self._poll.register(self.fd, select.POLLIN)

    def _range(self, axis):
        buf = bytearray(24)
        try:
            fcntl.ioctl(self.fd, _eviocgabs(axis), buf)
        except OSError:
            return None
        _, lo, hi, _, _, _ = struct.unpack("6i", bytes(buf))
        if hi > lo:
            return (lo, hi)
        return None

    def _scale(self):
        if self._raw[0] is None or self._raw[1] is None:
            return None
        rx, ry = self._raw
        fx = (rx - self.rx[0]) / float(self.rx[1] - self.rx[0])
        fy = (ry - self.ry[0]) / float(self.ry[1] - self.ry[0])
        if self.invert_x:
            fx = 1.0 - fx
        if self.invert_y:
            fy = 1.0 - fy
        if self.swap_xy:
            fx, fy = fy, fx
        x = min(max(fx, 0.0), 1.0) * (self.width - 1)
        y = min(max(fy, 0.0), 1.0) * (self.height - 1)
        return (int(x), int(y))

    def poll(self, timeout_ms=0):
        """Return a list of gesture events seen since the last call."""
        out = []
        if not self._poll.poll(timeout_ms):
            return out
        try:
            data = os.read(self.fd, EVENT_SIZE * 64)
        except (BlockingIOError, OSError):
            return out

        for off in range(0, len(data) - EVENT_SIZE + 1, EVENT_SIZE):
            _s, _us, etype, code, value = struct.unpack_from(
                EVENT_FMT, data, off)

            if etype == EV_ABS:
                if code == ABS_MT_SLOT:
                    self._slot = value
                elif self._slot != 0:
                    continue          # only the first finger drives the UI
                elif code in (ABS_MT_POSITION_X, ABS_X):
                    self._raw[0] = value
                elif code in (ABS_MT_POSITION_Y, ABS_Y):
                    self._raw[1] = value
                elif code == ABS_MT_TRACKING_ID:
                    if value == -1 and self._slot == 0:
                        out.extend(self._release())
                    elif value != -1:
                        self._press()
            elif etype == EV_KEY and code == BTN_TOUCH:
                if value:
                    self._press()
                else:
                    out.extend(self._release())
            elif etype == EV_SYN and code == SYN_REPORT:
                pos = self._scale()
                if pos and self._down:
                    if self._start is None:
                        self._start = (pos[0], pos[1], time.monotonic())
                        out.append(("down", pos[0], pos[1], None))
                    elif pos != self._last:
                        out.append(("move", pos[0], pos[1], None))
                    self._last = pos
        return out

    def _press(self):
        self._down = True

    def _release(self):
        out = []
        if not self._down:
            return out
        self._down = False
        pos = self._last or self._scale()
        start = self._start
        self._start = None
        if pos is None:
            return out
        out.append(("up", pos[0], pos[1], None))
        if start is None:
            return out
        dx = pos[0] - start[0]
        dy = pos[1] - start[1]
        dt = (time.monotonic() - start[2]) * 1000.0
        dist = max(abs(dx), abs(dy))
        if dist <= TAP_MAX_MOVE and dt <= TAP_MAX_MS:
            out.append(("tap", pos[0], pos[1], None))
        elif abs(dx) >= SWIPE_MIN and abs(dx) > abs(dy):
            out.append(("swipe", pos[0], pos[1], "left" if dx < 0 else "right"))
        return out

    def close(self):
        if self.fd is not None:
            self._poll.unregister(self.fd)
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

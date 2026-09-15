"""Goodix GT9271 touch by polling I2C directly from userspace.

Why not the kernel driver: on this board the touch INT line never fires.  The
`gt9271` interrupt count in /proc/interrupts stays at 1 (the probe) no matter
how much you touch the panel, so `Goodix-TS` produces no input events.  Fixing
that properly means changing the interrupt spec in the DT overlay and rebuilding
the FIT image - which needs the cross-build host.  The controller itself answers
perfectly over I2C, so the console polls it instead:

    $ i2ctransfer -y 1 w2@0x14 0x81 0x40 r6
    0x39 0x32 0x37 0x31 0x60 0x10      # "9271", firmware 0x1060

The kernel driver must be unbound first, otherwise the address is busy:

    echo 1-0014 > /sys/bus/i2c/drivers/Goodix-TS/unbind

GT9271 register map used here:
    0x8140  product id (4 ASCII bytes) + 2 firmware bytes
    0x814E  buffer status: bit7 = data ready, bits 3:0 = number of points
    0x814F  point 0: id, x_lo, x_hi, y_lo, y_hi, w_lo, w_hi, reserved
    ...     8 bytes per additional point
After reading a report, 0 must be written back to 0x814E to release the buffer.

The gesture layer mirrors touch.py so the two are drop-in interchangeable.
"""

import ctypes
import fcntl
import os
import struct
import time

I2C_SLAVE = 0x0703
I2C_RDWR = 0x0707
I2C_M_RD = 0x0001

REG_ID = 0x8140
REG_STATUS = 0x814E
REG_POINT0 = 0x814F

DEFAULT_BUS = 1
DEFAULT_ADDR = 0x14
UNBIND_PATH = "/sys/bus/i2c/drivers/Goodix-TS/unbind"
UNBIND_NAME = "1-0014"

# Gesture thresholds - kept identical to touch.py.
TAP_MAX_MS = 600
TAP_MAX_MOVE = 28
SWIPE_MIN = 70


class _I2cMsg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16), ("buf", ctypes.c_void_p)]


class _I2cRdwr(ctypes.Structure):
    _fields_ = [("msgs", ctypes.c_void_p), ("nmsgs", ctypes.c_uint32)]


def unbind_kernel_driver():
    """Release 0x14 from Goodix-TS.  Harmless if already unbound."""
    try:
        with open(UNBIND_PATH, "w") as f:
            f.write(UNBIND_NAME)
        return True
    except OSError:
        return False


class GT9271:
    """Raw register access over /dev/i2c-N."""

    def __init__(self, bus=DEFAULT_BUS, addr=DEFAULT_ADDR):
        self.addr = addr
        self.fd = os.open("/dev/i2c-%d" % bus, os.O_RDWR)
        try:
            fcntl.ioctl(self.fd, I2C_SLAVE, addr)
        except OSError:
            pass        # I2C_RDWR carries the address per message anyway

    def read(self, reg, count):
        """Repeated-start write-then-read, the same shape the kernel uses."""
        wbuf = (ctypes.c_uint8 * 2)((reg >> 8) & 0xFF, reg & 0xFF)
        rbuf = (ctypes.c_uint8 * count)()
        msgs = (_I2cMsg * 2)(
            _I2cMsg(self.addr, 0, 2, ctypes.cast(wbuf, ctypes.c_void_p).value),
            _I2cMsg(self.addr, I2C_M_RD, count,
                    ctypes.cast(rbuf, ctypes.c_void_p).value))
        req = _I2cRdwr(ctypes.cast(msgs, ctypes.c_void_p).value, 2)
        fcntl.ioctl(self.fd, I2C_RDWR, req)
        return bytes(rbuf)

    def write(self, reg, data):
        payload = bytes([(reg >> 8) & 0xFF, reg & 0xFF]) + bytes(data)
        wbuf = (ctypes.c_uint8 * len(payload))(*payload)
        msgs = (_I2cMsg * 1)(
            _I2cMsg(self.addr, 0, len(payload),
                    ctypes.cast(wbuf, ctypes.c_void_p).value))
        req = _I2cRdwr(ctypes.cast(msgs, ctypes.c_void_p).value, 1)
        fcntl.ioctl(self.fd, I2C_RDWR, req)

    def product_id(self):
        d = self.read(REG_ID, 6)
        return d[:4].decode("ascii", "replace").strip("\x00"), \
            (d[5] << 8) | d[4]

    def points(self):
        """Return [(id, x, y, size), ...]; [] when there is no new report."""
        st = self.read(REG_STATUS, 1)[0]
        if not (st & 0x80):
            return None                      # no fresh data
        n = st & 0x0F
        out = []
        if n:
            raw = self.read(REG_POINT0, 8 * min(n, 10))
            for i in range(min(n, 10)):
                tid, x, y, w = struct.unpack_from("<BHHH", raw, i * 8)
                out.append((tid, x, y, w))
        self.write(REG_STATUS, b"\x00")      # release the buffer
        return out

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class Touch:
    """Polling drop-in for touch.Touch - same poll()/close() contract."""

    def __init__(self, bus=DEFAULT_BUS, addr=DEFAULT_ADDR,
                 width=720, height=720, swap_xy=False,
                 invert_x=False, invert_y=False, unbind=True):
        if unbind:
            unbind_kernel_driver()
        self.dev = GT9271(bus, addr)
        self.path = "/dev/i2c-%d@0x%02x" % (bus, addr)
        self.width = width
        self.height = height
        self.swap_xy = swap_xy
        self.invert_x = invert_x
        self.invert_y = invert_y
        # The controller reports in panel pixels already (the kernel driver's
        # ABS range came out 0..719), so no scaling - only orientation fixes.
        self.rx = (0, width - 1)
        self.ry = (0, height - 1)

        self._down = False
        self._start = None
        self._last = None
        self.errors = 0

    def _map(self, x, y):
        fx = x / float(self.width - 1)
        fy = y / float(self.height - 1)
        if self.invert_x:
            fx = 1.0 - fx
        if self.invert_y:
            fy = 1.0 - fy
        if self.swap_xy:
            fx, fy = fy, fx
        return (int(min(max(fx, 0.0), 1.0) * (self.width - 1)),
                int(min(max(fy, 0.0), 1.0) * (self.height - 1)))

    def poll(self, timeout_ms=0):
        """Read one report; sleeps up to timeout_ms so callers can idle."""
        out = []
        try:
            pts = self.dev.points()
        except OSError:
            self.errors += 1
            pts = None
        if pts is None:
            if timeout_ms:
                time.sleep(min(timeout_ms, 40) / 1000.0)
            return out

        if pts:
            x, y = self._map(pts[0][1], pts[0][2])
            if not self._down:
                self._down = True
                self._start = (x, y, time.monotonic())
                self._last = (x, y)
                out.append(("down", x, y, None))
            elif (x, y) != self._last:
                self._last = (x, y)
                out.append(("move", x, y, None))
        elif self._down:
            out.extend(self._release())
        return out

    def _release(self):
        out = []
        self._down = False
        pos = self._last
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
        if max(abs(dx), abs(dy)) <= TAP_MAX_MOVE and dt <= TAP_MAX_MS:
            out.append(("tap", pos[0], pos[1], None))
        elif abs(dx) >= SWIPE_MIN and abs(dx) > abs(dy):
            out.append(("swipe", pos[0], pos[1],
                        "left" if dx < 0 else "right"))
        return out

    def close(self):
        self.dev.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _selftest(seconds=20.0, watch=False):
    unbind_kernel_driver()
    t = Touch()
    name, ver = t.dev.product_id()
    print("GT9271 id=%s fw=0x%04x on %s" % (name, ver, t.path), flush=True)
    if watch:
        # Runs until killed; prints only press/tap/swipe so a drag does not
        # flood the log.  Used under a Monitor watch during bring-up.
        print("watching - touch the panel any time", flush=True)
        while True:
            for kind, x, y, extra in t.poll(20):
                if kind in ("down", "tap", "swipe"):
                    print("TOUCH %-6s x=%-4s y=%-4s %s"
                          % (kind, x, y, extra or ""), flush=True)
    print("polling %.0fs - touch the panel" % seconds, flush=True)
    end = time.monotonic() + seconds
    seen = 0
    while time.monotonic() < end:
        for ev in t.poll(20):
            seen += 1
            print("  %-6s %4s %4s %s" % ev, flush=True)
    print("events: %d   i2c errors: %d" % (seen, t.errors))
    t.close()


if __name__ == "__main__":
    import sys
    _selftest(watch="--watch" in sys.argv)

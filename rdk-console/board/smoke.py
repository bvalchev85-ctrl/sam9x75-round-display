"""Render the carousel menu on the panel and hold it, with timings.

    python3 smoke.py [hold_seconds] [index]
"""

import sys
import time

import icons
import theme as T
from kms import Display
from screens import Renderer

ITEMS = [
    ("security", "Security", icons.shield, T.ACCENT_SECURITY),
    ("camera", "Camera", icons.camera, T.ACCENT_CAMERA),
    ("settings", "Settings", icons.gear, T.ACCENT_SETTINGS),
]


def main():
    hold = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    index = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    d = Display()
    print("display: %dx%d pitch=%d connector=%d crtc=%d"
          % (d.width, d.height, d.pitch, d.connector_id, d.crtc_id))
    try:
        r = Renderer(d)

        t0 = time.monotonic()
        r.background()          # first call builds the cached surface
        t1 = time.monotonic()
        print("background build+blit: %.0f ms" % ((t1 - t0) * 1000))

        t0 = time.monotonic()
        r.menu(ITEMS, index, "eth0  ·  " + time.strftime("%H:%M"))
        t1 = time.monotonic()
        print("full menu frame:       %.0f ms" % ((t1 - t0) * 1000))

        t0 = time.monotonic()
        for i in range(5):
            r.menu(ITEMS, (index + i) % len(ITEMS),
                   "eth0  ·  " + time.strftime("%H:%M"))
        t1 = time.monotonic()
        print("steady-state frame:    %.0f ms" % ((t1 - t0) * 200))

        r.menu(ITEMS, index, "eth0  ·  " + time.strftime("%H:%M"))
        r.ctx.check()
        r.ctx.write_png("/tmp/frame-menu.png")

        r.security(True, True, "eth0  ·  " + time.strftime("%H:%M"))
        r.ctx.write_png("/tmp/frame-security.png")

        r.settings([("Brightness", 76, 0, 255), ("Contrast", 32, 0, 255),
                    ("Saturation", 60, 0, 255), ("Sharpness", 50, 0, 255)],
                   0, "eth0  ·  " + time.strftime("%H:%M"))
        r.ctx.write_png("/tmp/frame-settings.png")

        r.menu(ITEMS, index, "eth0  ·  " + time.strftime("%H:%M"))
        print("dumped /tmp/frame-*.png")
        print("holding %.0fs ..." % hold)
        time.sleep(hold)
    finally:
        d.close()


if __name__ == "__main__":
    main()

"""Touch calibration check.

Shows three targets in turn and logs where the tap actually landed, which
determines whether the Goodix axes need swapping/inverting relative to the
display.  Run it, tap each ring as it appears:

    python3 touchtest.py
"""

import sys
import time

import theme as T
from kms import Display
from screens import Renderer
from touch import Touch

TARGETS = [("top", 360, 150), ("right", 570, 360), ("bottom-left", 210, 560)]


def draw(r, name, tx, ty, dot=None, note=""):
    c = r.ctx
    r.background()

    c.colour(T.ACCENT_CAMERA, 0.25)
    c.line_width(3.0)
    c.new_path()
    c.circle(tx, ty, 54.0)
    c.stroke()
    c.colour(T.ACCENT_CAMERA)
    c.line_width(3.0)
    c.new_path()
    c.circle(tx, ty, 26.0)
    c.stroke()
    c.new_path()
    c.circle(tx, ty, 4.0)
    c.fill()

    c.font(T.FONT, 26.0, bold=True)
    c.colour(T.LABEL_COLOUR)
    c.text_centred(T.CX, 400.0, "tap the ring")
    c.font(T.FONT, 19.0)
    c.colour(T.DIM)
    c.text_centred(T.CX, 432.0, name)
    if note:
        c.text_centred(T.CX, 462.0, note)

    if dot:
        c.colour("#ffd166")
        c.new_path()
        c.circle(dot[0], dot[1], 9.0)
        c.fill()

    r.present()


def probe():
    """Print the device and its axis ranges without touching the display."""
    t = Touch()
    print("touch device: %s" % t.path)
    print("raw X range: %s   raw Y range: %s" % (t.rx, t.ry))
    print("watching for 8s - touch the panel now")
    end = time.monotonic() + 8.0
    seen = 0
    while time.monotonic() < end:
        for ev in t.poll(200):
            seen += 1
            print("  %-6s %4s %4s %s" % ev)
    if not seen:
        print("  (no events)")
    t.close()
    return 0


def main():
    if "--probe" in sys.argv:
        return probe()
    d = Display()
    try:
        r = Renderer(d)
        t = Touch(width=d.width, height=d.height)
        print("touch device: %s" % t.path)
        print("raw X range: %s   raw Y range: %s" % (t.rx, t.ry))

        results = []
        for name, tx, ty in TARGETS:
            draw(r, name, tx, ty)
            deadline = time.monotonic() + 40.0
            got = None
            last_dot = None
            while time.monotonic() < deadline and got is None:
                for kind, x, y, _extra in t.poll(120):
                    if kind in ("down", "move"):
                        if (x, y) != last_dot:
                            last_dot = (x, y)
                            draw(r, name, tx, ty, dot=(x, y))
                    elif kind == "tap":
                        got = (x, y)
            if got is None:
                print("%-12s target=(%d,%d)  TIMEOUT" % (name, tx, ty))
                results.append((tx, ty, None, None))
            else:
                print("%-12s target=(%d,%d)  measured=(%d,%d)"
                      % (name, tx, ty, got[0], got[1]))
                results.append((tx, ty, got[0], got[1]))
                draw(r, name, tx, ty, dot=got, note="got %d,%d" % got)
                time.sleep(0.6)

        good = [q for q in results if q[2] is not None]
        if len(good) >= 2:
            ex = sum(abs(q[0] - q[2]) for q in good) / len(good)
            ey = sum(abs(q[1] - q[3]) for q in good) / len(good)
            sx = sum(abs(q[0] - q[3]) for q in good) / len(good)
            sy = sum(abs(q[1] - q[2]) for q in good) / len(good)
            print("\nmean error  direct: x=%.0f y=%.0f   swapped: x=%.0f y=%.0f"
                  % (ex, ey, sx, sy))
            if max(ex, ey) <= 45:
                print("VERDICT: axes correct as-is")
            elif max(sx, sy) <= 45:
                print("VERDICT: needs swap_xy=True")
            else:
                print("VERDICT: needs inversion - compare the pairs above")
        t.close()
    finally:
        d.close()


if __name__ == "__main__":
    sys.exit(main())

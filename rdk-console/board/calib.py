"""Panel alignment ruler.

Vertical colour bars hide a uniform horizontal shift (the stripes just move),
so this draws a measurable pattern instead:

  * a circle at r=358 that should sit just inside the bezel all the way round
  * a horizontal and a vertical ruler through the centre, labelled every 50 px
  * corner-to-corner edge ticks at 0 and 719

Read off the numbers visible at the extreme left/right (and top/bottom) edges
of the glass: on a correctly aligned panel they are 0 and 719.

    python3 calib.py [hold_seconds] [x_offset] [y_offset]

x_offset/y_offset shift everything drawn, to confirm a compensation value.
"""

import math
import sys
import time

import cairo_ffi as cf
import theme as T
from kms import Display

STEP = 10
LABEL_EVERY = 50


def draw(c, ox=0.0, oy=0.0):
    c.colour("#000000")
    c.rect(0, 0, T.W, T.H)
    c.fill()

    c.save()
    c.translate(ox, oy)

    # Alignment circle: should just clear the bezel everywhere.
    c.colour("#34c9b8")
    c.line_width(2.0)
    c.new_path()
    c.circle(T.CX, T.CY, 358.0)
    c.stroke()

    # Inner reference circles every 100 px of radius.
    c.colour("#2a4a50")
    c.line_width(1.0)
    for r in (100.0, 200.0, 300.0):
        c.new_path()
        c.circle(T.CX, T.CY, r)
        c.stroke()

    # Crosshair.
    c.colour("#ff6b57")
    c.line_width(1.0)
    c.new_path()
    c.move_to(0, T.CY)
    c.line_to(T.W, T.CY)
    c.move_to(T.CX, 0)
    c.line_to(T.CX, T.H)
    c.stroke()

    # Horizontal ruler along the centre line.
    c.font("DejaVu Sans Mono", 15.0)
    for x in range(0, T.W, STEP):
        major = (x % LABEL_EVERY) == 0
        c.colour("#eaf3f4" if major else "#7c8f93")
        c.line_width(1.0)
        c.new_path()
        c.move_to(x + 0.5, T.CY - (14.0 if major else 6.0))
        c.line_to(x + 0.5, T.CY + (14.0 if major else 6.0))
        c.stroke()
        if major:
            c.text_centred(x, T.CY - 20.0, str(x))

    # Vertical ruler down the centre line.
    for y in range(0, T.H, STEP):
        major = (y % LABEL_EVERY) == 0
        c.colour("#eaf3f4" if major else "#7c8f93")
        c.line_width(1.0)
        c.new_path()
        c.move_to(T.CX - (14.0 if major else 6.0), y + 0.5)
        c.line_to(T.CX + (14.0 if major else 6.0), y + 0.5)
        c.stroke()
        if major and y:
            c.colour("#eaf3f4")
            c.text(T.CX + 20.0, y + 5.0, str(y))

    # Hard edge markers: 8px squares in every corner + edge midpoints.
    c.colour("#ffd166")
    for (mx, my) in ((0, T.CY - 4), (T.W - 8, T.CY - 4),
                     (T.CX - 4, 0), (T.CX - 4, T.H - 8)):
        c.new_path()
        c.rect(mx, my, 8, 8)
        c.fill()

    # First/last column and row, so a 1px clip is visible.
    c.colour("#ff6b57")
    c.line_width(1.0)
    c.new_path()
    c.move_to(0.5, 0)
    c.line_to(0.5, T.H)
    c.move_to(T.W - 0.5, 0)
    c.line_to(T.W - 0.5, T.H)
    c.stroke()

    c.restore()

    c.colour("#4bd3e8")
    c.font(T.FONT, 20.0, bold=True)
    c.text_centred(T.CX, T.CY + 250.0, "offset %+d , %+d" % (ox, oy))


def draw_sweep(c, ox, oy, tag):
    """Big, unambiguous concentricity target: the circle either hugs the round
    bezel evenly or it does not.  No small numbers to read."""
    c.colour("#000000")
    c.rect(0, 0, T.W, T.H)
    c.fill()

    c.save()
    c.translate(ox, oy)

    # Edge-hugging ring: 4px so a few px of misalignment is obvious.
    c.colour("#34c9b8")
    c.line_width(4.0)
    c.new_path()
    c.circle(T.CX, T.CY, 356.0)
    c.stroke()

    # Four spokes to the rim - the gap at each rim tells you which way it sits.
    c.colour("#ff6b57")
    c.line_width(3.0)
    c.new_path()
    for a in (0.0, 0.25, 0.5, 0.75):
        c.move_to(T.CX, T.CY)
        ang = a * cf.TAU
        c.line_to(T.CX + 356.0 * math.cos(ang),
                  T.CY + 356.0 * math.sin(ang))
    c.stroke()

    c.colour("#ffd166")
    c.new_path()
    c.circle(T.CX, T.CY, 8.0)
    c.fill()
    c.restore()

    # The tag is drawn WITHOUT the offset so it never runs off the glass.
    c.colour("#ffffff")
    c.font(T.FONT, 96.0, bold=True)
    c.text_centred(T.CX, T.CY + 150.0, tag)


def sweep(d, values, dwell):
    c = cf.Ctx(d.addr, d.width, d.height, d.pitch)
    print("sweeping x offsets: %s (%.1fs each)" % (values, dwell))
    for v in values:
        draw_sweep(c, float(v), 0.0, "%+d" % v)
        c.flush()
        print("  showing %+d" % v, flush=True)
        time.sleep(dwell)
    draw_sweep(c, 0.0, 0.0, "done")
    c.flush()
    c.close()


def shift_test(px, hold):
    """Program a mode with the active window moved `px` earlier in the line.

    Unlike a drawing offset this keeps all 720 columns usable - the panel is
    told to fetch our data sooner instead of us giving up pixels at one edge.
    """
    d = Display()
    try:
        print("base:  " + d.describe_mode(d.base_mode))
        try:
            d.tune_mode(h_shift=px)
        except ValueError as exc:
            print("cannot shift: %s" % exc)
            return 1
        print("tuned: " + d.describe_mode())
        try:
            d.set_crtc()
        except OSError as exc:
            print("SETCRTC rejected the tuned mode: %s" % exc)
            print("-> fall back to a drawing offset (X_OFFSET in config.py)")
            return 2
        print("mode accepted")
        c = cf.Ctx(d.addr, d.width, d.height, d.pitch)
        draw_sweep(c, 0.0, 0.0, "shift %d" % px)
        c.flush()
        c.write_png("/tmp/rdk-shift.png")
        print("holding %.0fs" % hold, flush=True)
        time.sleep(hold)
        c.close()
    finally:
        d.close()
    return 0


def main():
    if "--shift" in sys.argv:
        i = sys.argv.index("--shift")
        px = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 50
        hold = float(sys.argv[i + 2]) if len(sys.argv) > i + 2 else 45.0
        return shift_test(px, hold)

    if "--sweep" in sys.argv:
        d = Display()
        try:
            sweep(d, [0, 20, 40, 60, 80, -20, -40, -60, -80], 3.5)
        finally:
            d.close()
        return

    hold = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    ox = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    oy = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0

    d = Display()
    try:
        c = cf.Ctx(d.addr, d.width, d.height, d.pitch)
        m = d.mode
        print("mode %s  clock=%d" % (m.name.decode(), m.clock))
        print("  H: %d active | fp %d | sync %d | bp %d | total %d"
              % (m.hdisplay, m.hsync_start - m.hdisplay,
                 m.hsync_end - m.hsync_start, m.htotal - m.hsync_end,
                 m.htotal))
        print("  V: %d active | fp %d | sync %d | bp %d | total %d"
              % (m.vdisplay, m.vsync_start - m.vdisplay,
                 m.vsync_end - m.vsync_start, m.vtotal - m.vsync_end,
                 m.vtotal))
        draw(c, ox, oy)
        c.flush()
        c.write_png("/tmp/rdk-calib.png")
        print("drawn with offset %+d,%+d - holding %.0fs" % (ox, oy, hold))
        time.sleep(hold)
        c.close()
    finally:
        d.close()


if __name__ == "__main__":
    sys.exit(main() or 0)

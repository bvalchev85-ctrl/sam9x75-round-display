"""Vector icons, ported from the mockup's inline SVG.

Each icon draws inside a 24x24 unit box; callers scale it.  Stroke widths are
in those same 24-unit coordinates, so a 1.5 here matches the SVG's
stroke-width="1.5" regardless of the final pixel size.

`draw(ctx, cx, cy, size, colour, alpha)` centres the icon on (cx, cy) and
renders it `size` pixels across.
"""

import math

TAU = 2.0 * math.pi


def _begin(ctx, cx, cy, size, colour, alpha, width):
    ctx.save()
    ctx.translate(cx - size / 2.0, cy - size / 2.0)
    ctx.scale(size / 24.0)
    ctx.colour(colour, alpha)
    ctx.line_width(width)
    ctx.cap_round()


def camera(ctx, cx, cy, size, colour, alpha=1.0):
    """SVG: rounded body + lens hood bump + 3/4 lens arc + flash dot."""
    _begin(ctx, cx, cy, size, colour, alpha, 1.4)

    ctx.new_path()
    ctx.round_rect(2.2, 6.4, 19.6, 13.2, 3.2)
    ctx.stroke()

    ctx.new_path()
    ctx.move_to(8.4, 6.4)
    ctx.line_to(9.9, 4.0)
    ctx.line_to(14.1, 4.0)
    ctx.line_to(15.6, 6.4)
    ctx.stroke()

    # M15.2 13 a3.2 3.2 0 1 1 -3.2 -3.2  ->  centre (12,13), 0deg to 270deg.
    ctx.new_path()
    ctx.arc(12.0, 13.0, 3.2, 0.0, 0.75 * TAU)
    ctx.stroke()

    ctx.new_path()
    ctx.circle(17.6, 10.0, 0.9)
    ctx.fill()

    ctx.restore()


def shield(ctx, cx, cy, size, colour, alpha=1.0, locked=None):
    """Security shield.  `locked` True/False adds a padlock or an open ring."""
    _begin(ctx, cx, cy, size, colour, alpha, 1.5)

    ctx.new_path()
    ctx.move_to(12.0, 2.4)
    ctx.line_to(20.0, 5.7)
    ctx.line_to(20.0, 11.6)
    ctx.curve_to(20.0, 16.6, 16.4, 19.9, 12.0, 21.6)
    ctx.curve_to(7.6, 19.9, 4.0, 16.6, 4.0, 11.6)
    ctx.line_to(4.0, 5.7)
    ctx.close()
    ctx.stroke()

    if locked is not None:
        # Padlock: shackle arc above a small body.  Open shackle when unlocked.
        ctx.new_path()
        if locked:
            ctx.arc(12.0, 11.4, 2.1, 0.5 * TAU, 1.0 * TAU)
        else:
            ctx.arc(13.3, 11.4, 2.1, 0.5 * TAU, 0.87 * TAU)
        ctx.stroke()
        ctx.new_path()
        ctx.round_rect(9.0, 11.4, 6.0, 5.2, 1.1)
        ctx.stroke()

    ctx.restore()


def gear(ctx, cx, cy, size, colour, alpha=1.0):
    """SVG: sun/gear glyph - inner circle, 8 spokes, small satellite ring."""
    _begin(ctx, cx, cy, size, colour, alpha, 1.5)

    ctx.new_path()
    ctx.circle(10.0, 10.0, 3.0)
    ctx.stroke()

    spokes = [
        (10.0, 1.6, 10.0, 3.8), (10.0, 16.2, 10.0, 18.4),
        (2.6, 10.0, 0.4, 10.0), (19.6, 10.0, 17.4, 10.0),
        (4.8, 4.8, 3.2, 3.2), (16.8, 16.8, 15.2, 15.2),
        (4.8, 15.2, 3.2, 16.8), (16.8, 3.2, 15.2, 4.8),
    ]
    ctx.new_path()
    for x1, y1, x2, y2 in spokes:
        ctx.move_to(x1, y1)
        ctx.line_to(x2, y2)
    ctx.stroke()

    ctx.new_path()
    ctx.circle(18.5, 18.5, 2.2)
    ctx.stroke()

    ctx.restore()


def thermo(ctx, cx, cy, size, colour, alpha=1.0):
    """Thermometer (kept from the mockup for a future home-automation page).

    The stem sides meet the bulb circle exactly at y=14.25, so the outline is
    one continuous path with no seam.
    """
    _begin(ctx, cx, cy, size, colour, alpha, 1.5)

    ctx.new_path()
    ctx.move_to(14.0, 14.25)
    ctx.line_to(14.0, 3.5)
    ctx.arc_neg(12.0, 3.5, 2.0, 0.0, -0.5 * TAU)     # over the top
    ctx.line_to(10.0, 14.25)
    ctx.arc_neg(12.0, 17.6, 3.9,
                math.radians(-120.85), math.radians(-419.15))  # bulb
    ctx.close()
    ctx.stroke()

    ctx.restore()


def chevron(ctx, cx, cy, size, colour, alpha=1.0, left=True):
    """Carousel hint arrow."""
    _begin(ctx, cx, cy, size, colour, alpha, 2.0)
    ctx.new_path()
    if left:
        ctx.move_to(14.5, 5.0)
        ctx.line_to(9.0, 12.0)
        ctx.line_to(14.5, 19.0)
    else:
        ctx.move_to(9.5, 5.0)
        ctx.line_to(15.0, 12.0)
        ctx.line_to(9.5, 19.0)
    ctx.stroke()
    ctx.restore()


def play(ctx, cx, cy, size, colour, alpha=1.0):
    _begin(ctx, cx, cy, size, colour, alpha, 1.5)
    ctx.new_path()
    ctx.move_to(8.5, 5.5)
    ctx.line_to(18.0, 12.0)
    ctx.line_to(8.5, 18.5)
    ctx.close()
    ctx.fill()
    ctx.restore()


def back(ctx, cx, cy, size, colour, alpha=1.0):
    """Left arrow with a tail - 'return to menu'."""
    _begin(ctx, cx, cy, size, colour, alpha, 2.0)
    ctx.new_path()
    ctx.move_to(19.0, 12.0)
    ctx.line_to(6.0, 12.0)
    ctx.move_to(11.5, 6.5)
    ctx.line_to(6.0, 12.0)
    ctx.line_to(11.5, 17.5)
    ctx.stroke()
    ctx.restore()

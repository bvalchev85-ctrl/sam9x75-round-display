"""Per-operation timings, to find what is actually slow on this ARM926."""

import time

import cairo_ffi as cf
import icons
import theme as T
from kms import Display
from screens import ICON_NOMINAL, SLIDE_BAND, Renderer


def t(label, fn, n=5):
    fn()                                  # warm
    t0 = time.monotonic()
    for _ in range(n):
        fn()
    ms = (time.monotonic() - t0) * 1000.0 / n
    print("%-26s %7.1f ms" % (label, ms))
    return ms


def main():
    d = Display()
    try:
        r = Renderer(d)
        c = r.ctx
        r.background()                    # ensure cache built/loaded

        t("background blit", lambda: r.background())
        t("centre_glow radial", lambda: r.centre_glow(T.ACCENT_CAMERA))
        t("camera icon 188px", lambda: icons.camera(c, T.CX, T.CY,
                                                    T.CENTRE_ICON,
                                                    T.ACCENT_CAMERA))
        t("side icons x2", lambda: (
            icons.shield(c, T.SIDE_LEFT_CX, T.SIDE_CY, T.SIDE_ICON,
                         T.ACCENT_SECURITY, T.SIDE_ALPHA),
            icons.gear(c, T.SIDE_RIGHT_CX, T.SIDE_CY, T.SIDE_ICON,
                       T.ACCENT_SETTINGS, T.SIDE_ALPHA)))
        t("status line", lambda: r.status_line("eth0  Â·  12:34"))
        t("label", lambda: r.label("Camera"))
        t("dots", lambda: r.dots(3, 1))
        t("flush", lambda: r.present())

        def solid():
            c.colour("#000000")
            c.rect(0, 0, 720, 720)
            c.fill()
        t("full-screen solid fill", solid)

        # Which part of an icon blit is expensive: the scale, or the mask?
        sp = r._sized_sprite("camera", icons.camera, ICON_NOMINAL)[0]
        t("icon: mask scaled 0.46",
          lambda: r.draw_icon("camera", icons.camera, T.CX, T.CY, 86.0,
                              T.ACCENT_CAMERA, 0.62))
        t("icon: mask scaled 1.0",
          lambda: r.draw_icon("camera", icons.camera, T.CX, T.CY,
                              ICON_NOMINAL, T.ACCENT_CAMERA, 1.0))

        def mask_plain():
            c.colour(T.ACCENT_CAMERA, 1.0)
            c.mask(sp.surface, 260.0, 260.0)
        t("icon: mask unscaled", mask_plain)

        def blit_plain():
            c.draw_surface(sp.surface, 260.0, 260.0)
        t("icon: paint unscaled", blit_plain)
        print()

        items = [
            ("security", "Security", icons.shield, T.ACCENT_SECURITY),
            ("camera", "Camera", icons.camera, T.ACCENT_CAMERA),
            ("settings", "Settings", icons.gear, T.ACCENT_SETTINGS),
        ]
        st = "eth0  Â·  12:34"
        r.prewarm(items)
        r.menu_at(items, 1.0, st)          # warm the chrome + icon sprites
        print()
        ms = t("resting menu frame", lambda: r.menu_at(items, 1.0, st), 8)
        pos = [1.0]

        def anim():
            pos[0] += 0.13
            r.menu_at(items, pos[0], st, band=SLIDE_BAND, chrome_index=1)
        ms = t("animation frame (sliding)", anim, 12)
        print("  -> %.0f fps, %.0f frames in a %d ms slide"
              % (1000.0 / ms, 260.0 / ms, 260))
    finally:
        d.close()


if __name__ == "__main__":
    main()




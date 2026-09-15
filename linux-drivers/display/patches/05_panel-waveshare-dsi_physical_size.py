#!/usr/bin/env python3
"""Fix the panel's reported physical size (width_mm / height_mm).

Upstream drivers/gpu/drm/panel/panel-waveshare-dsi.c hardcodes

    connector->display_info.width_mm  = 154;
    connector->display_info.height_mm =  86;

in ws_panel_get_modes() for *every* model.  That is the 7-inch 800x480 DPI
panel's size, and it is wrong for all the others - including the 720x720 round
one on the SAM9X75 Round Display Kit, whose active area is a 72 x 72 mm square
(4" diagonal).

Why it is not cosmetic
----------------------
Anything that corrects for the display aspect ratio believes the pixels are
154/86 = 1.79x wider than tall and squeezes every frame's width to about 3/5.
GStreamer's kmssink does exactly this.  Measured on this board, reading the
committed atomic state from /sys/kernel/debug/dri/1/state:

    source 640x480  ->  crtc-pos=576x720+72+0   src-pos=384x480+0+0
    source 720x720  ->  crtc-pos=432x720+144+0  src-pos=432x720+0+0
    source 480x480  ->  crtc-pos=432x720+144+0  src-pos=288x480+0+0

i.e. even a perfectly square source is displayed as 432x720 with black bars
down both sides, and only the left 60% of the source columns are used.

No pipeline setting can undo it: render-rectangle, display-width/display-height
and plane-properties were all measured to make no difference, because kmssink
recomputes the rectangle and calls drmModeSetPlane on every frame.

This patch moves the size into struct ws_panel_data so each model carries its
own, sets 72 x 72 mm for the round panel, and keeps upstream's value as the
fallback for models nobody has measured.

Usage:
    python3 05_panel-waveshare-dsi_physical_size.py [path/to/panel-waveshare-dsi.c]
"""

import io
import sys

DEFAULT = ("/home/attila/sam9x75-rdk/buildroot/output/build/linux-custom/"
           "drivers/gpu/drm/panel/panel-waveshare-dsi.c")

EDITS = [
    # 1. per-model physical size in the descriptor
    ("""struct ws_panel_data {
	const struct drm_display_mode *mode;
	int lanes;
	unsigned long mode_flags;
};""",
     """struct ws_panel_data {
	const struct drm_display_mode *mode;
	int lanes;
	unsigned long mode_flags;
	/*
	 * Physical active-area size.  Upstream hardcoded 154x86 mm for every
	 * model in ws_panel_get_modes(); that is the 7" 800x480 DPI panel and
	 * is wrong for the others.  See the comment there for why it matters.
	 */
	u32 width_mm;
	u32 height_mm;
};"""),

    # 2. keep the descriptor around so get_modes() can read it
    ("""	const struct drm_display_mode *mode;
	enum drm_panel_orientation orientation;
};""",
     """	const struct drm_display_mode *mode;
	const struct ws_panel_data *data;
	enum drm_panel_orientation orientation;
};"""),

    # 3. the 720x720 round panel
    ("""static const struct ws_panel_data ws_panel_4_data = {
	.mode = &ws_panel_4_mode,""",
     """static const struct ws_panel_data ws_panel_4_data = {
	.mode = &ws_panel_4_mode,
	/* 720x720 round panel, 4" diagonal -> 72 x 72 mm square active area */
	.width_mm = 72,
	.height_mm = 72,"""),

    # 4. remember it at probe time
    ("""	ts->mode = _ws_panel_data->mode;
	if (!ts->mode)
		return -EINVAL;""",
     """	ts->mode = _ws_panel_data->mode;
	ts->data = _ws_panel_data;
	if (!ts->mode)
		return -EINVAL;"""),

    # 5. use it
    ("""	connector->display_info.width_mm = 154;
	connector->display_info.height_mm = 86;""",
     """	/*
	 * MUST match the panel actually fitted: anything that corrects for the
	 * display aspect ratio (GStreamer's kmssink, for one) will otherwise
	 * squeeze every frame's width - on the 720x720 round panel a square
	 * source came out 432x720 with bars down both sides.
	 */
	if (ts->data && ts->data->width_mm && ts->data->height_mm) {
		connector->display_info.width_mm = ts->data->width_mm;
		connector->display_info.height_mm = ts->data->height_mm;
	} else {
		/* upstream's value, for models nobody has measured yet */
		connector->display_info.width_mm = 154;
		connector->display_info.height_mm = 86;
	}"""),
]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    src = io.open(path, encoding="utf-8").read()

    if "ts->data->width_mm" in src:
        print("already patched: %s" % path)
        return 0

    for i, (old, new) in enumerate(EDITS, 1):
        n = src.count(old)
        if n != 1:
            print("EDIT %d ANCHOR COUNT %d - ABORT (expected 1)" % (i, n))
            return 1
        src = src.replace(old, new)

    io.open(path, "w", encoding="utf-8", newline="\n").write(src)
    print("PATCHED ok: %s" % path)
    print("  round panel now reports 72 x 72 mm instead of 154 x 86 mm")
    return 0


if __name__ == "__main__":
    sys.exit(main())

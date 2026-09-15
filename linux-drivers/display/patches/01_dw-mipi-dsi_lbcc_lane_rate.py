core = "/home/attila/sam9x75-rdk/buildroot/output/build/linux-custom/drivers/gpu/drm/bridge/synopsys/dw-mipi-dsi.c"
mchp = "/home/attila/sam9x75-rdk/buildroot/output/build/linux-custom/drivers/gpu/drm/bridge/dw-mipi-dsi-mchp.c"

# ---- FIX 1: core lbcc must use the ACTUAL lane rate in non-burst mode too ----
s = open(core).read()
old = """	if (dsi->mode_flags & MIPI_DSI_MODE_VIDEO_BURST) {
		/* lbcc based on lane_mbps */
		lbcc = hcomponent * dsi->lane_mbps * MSEC_PER_SEC / 8;
	} else {
		/* lbcc based on pixel clock rate */
		bpp = mipi_dsi_pixel_format_to_bpp(dsi->format);
		if (bpp < 0) {
			dev_err(dsi->dev, "failed to get bpp\\n");
			return 0;
		}

		lbcc = div_u64((u64)hcomponent * mode->clock * bpp, dsi->lanes * 8);
	}
"""
new = """	/*
	 * Line timing must always be derived from the ACTUAL lane rate.
	 * The old non-burst path used hcomponent * mode->clock * bpp /
	 * (lanes * 8); mode->clock then cancels in the division below,
	 * leaving hcomponent * bpp / (8 * lanes) -- i.e. it assumes
	 * lane_mbps == the theoretical minimum. get_lane_mbps() however
	 * programs the PHY with a margin (x10/8), so the host timed each
	 * line ~20% short of the real one => DPI underflow, squeezed or
	 * black image. Use lane_mbps for burst and non-burst alike.
	 */
	bpp = mipi_dsi_pixel_format_to_bpp(dsi->format);
	if (bpp < 0) {
		dev_err(dsi->dev, "failed to get bpp\\n");
		return 0;
	}

	lbcc = hcomponent * dsi->lane_mbps * MSEC_PER_SEC / 8;
"""
if s.count(old) != 1:
    print("CORE ANCHOR COUNT", s.count(old), "- ABORT")
    raise SystemExit(1)
open(core, "w").write(s.replace(old, new))
print("OK: core lbcc now uses lane_mbps in all modes")

# ---- FIX 2: restore the x10/8 margin in the mchp lane-rate calc ----
m = open(mchp).read()
old2 = """	/* sam9x75 RDK: NO margin. VID_HLINE_TIME is fixed at htotal*bpp/(8*lanes),
	 * so the DSI line time only matches the DPI line time when
	 * lane_mbps == mpclk * bpp/lanes exactly. Margin => squeezed/black image. */
	desired_mbps = mpclk * (bpp / lanes);"""
new2 = """	/* take 1/0.8, since mbps must be bigger than bandwidth of RGB */
	desired_mbps = mpclk * (bpp / lanes) * 10 / 8;"""
if m.count(old2) != 1:
    print("MCHP ANCHOR COUNT", m.count(old2), "- ABORT")
    raise SystemExit(1)
open(mchp, "w").write(m.replace(old2, new2))
print("OK: x10/8 lane margin restored")

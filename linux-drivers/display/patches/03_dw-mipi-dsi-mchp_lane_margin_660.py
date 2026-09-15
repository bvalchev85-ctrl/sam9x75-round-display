p = "/home/attila/sam9x75-rdk/buildroot/output/build/linux-custom/drivers/gpu/drm/bridge/dw-mipi-dsi-mchp.c"
s = open(p).read()

old = """	/* take 1/0.8, since mbps must be bigger than bandwidth of RGB */
	desired_mbps = mpclk * (bpp / lanes) * 10 / 8;"""
new = """	/*
	 * Only ~10% over the RGB bandwidth (Microchip's own bare-metal config
	 * for this panel uses 660 Mbps for a 50 MHz/24bpp/2-lane link, i.e.
	 * 600 Mbps minimum + 10%). The old 10/8 (=25%) margin makes the DSI
	 * drain each line ~25% faster than the DPI can fill it, which
	 * underruns the DPI buffer every frame (INT_ST1 dpi_buff_pld_under)
	 * and shows up as a per-frame flicker.
	 */
	desired_mbps = mpclk * (bpp / lanes) * 11 / 10;"""

if s.count(old) != 1:
    print("ANCHOR COUNT", s.count(old), "- ABORT")
    raise SystemExit(1)

open(p, "w").write(s.replace(old, new))
print("OK: lane margin 25% -> 10% (expect lane=660, HLINE=1838)")

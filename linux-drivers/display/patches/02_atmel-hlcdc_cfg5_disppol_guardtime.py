p = "/home/attila/sam9x75-rdk/buildroot/output/build/linux-custom/drivers/gpu/drm/atmel-hlcdc/atmel_hlcdc_crtc.c"
s = open(p).read()

old = """	} else {
		cfg |= state->dpi << 11;
	}
"""
new = """	} else {
		cfg |= state->dpi << 11;
		/*
		 * sam9x75 RDK / MIPI-DSI: the mainline driver lists DISPPOL,
		 * DISPDLY, VSPDLYS and GUARDTIME in the CFG(5) write mask but
		 * never sets them, so they are always cleared. Microchip's own
		 * working bare-metal config for this panel programs
		 * LCDCFG5 = GUARDTIME(1) | DPI(1) | MODE(5) | DISPDLY(1) |
		 *           DISPPOL(1) | VSPDLYS(1)  (= 0x10D94).
		 * Without DISPPOL in particular the DSI never latches valid
		 * pixels -> black screen with every other register correct.
		 */
		cfg |= ATMEL_HLCDC_DISPPOL | ATMEL_HLCDC_DISPDLY |
		       ATMEL_HLCDC_VSPDLYS;
		cfg |= 1 << 16;		/* GUARDTIME = 1 */
	}
"""

if s.count(old) != 1:
    print("ANCHOR COUNT", s.count(old), "- ABORT")
    raise SystemExit(1)

open(p, "w").write(s.replace(old, new))
print("OK: CFG(5) now matches the demo (expect LCDCFG5 = 0x10D94)")

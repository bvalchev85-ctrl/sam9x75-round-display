# Round Panel — Linux Bring-up Spec (Phase 2)

**Panel:** Waveshare **4inch DSI LCD (C)** — round, **720×720**, MIPI-DSI + Goodix GT9271 touch.
<https://www.waveshare.com/4inch-dsi-lcd-c.htm>

> **★ Status 2026-09-06:** The panel **DISPLAYS** (image proven on glass, correct colours).
> Remaining work is DSI/LCDC clock tuning. Everything below is **measured on this hardware**
> or taken from Microchip's own sources — not guesswork.
> Machine-readable: `reference/panel-bringup-spec.json`. Vendor source: `reference/waveshare-esp_lcd_dsi/`.

---

## 1. Authoritative sources (in order of trust)

1. **MGS demo source** — `github.com/mchpgfx/mgsh_sam9x7`, config
   `quickstart/firmware/src/config/dsi_xlcdc_rgba8888_ws_9x75_curiosity_720x720_round/`
   (`gfx/display/ws_touch_display.c`, `gfx/driver/controller/xlcdc/bridge/dsi/plib_dsi.c`,
   `gfx/driver/controller/xlcdc/plib/plib_xlcdc.c`). This is Microchip's own working driver
   for **this exact board + panel**. Cloned to VM `~/mgsh_sam9x7` (417 MB).
   > **Verified 2026-09-06:** the board-specific config
   > `mgs_quickstart/firmware/src/config/rdk/` (the actual **RDK** board, not the
   > Curiosity+panel variant) is **identical** on every value that matters — same `initSeq`,
   > same `brightSeq` (`0xAB=55`), same timing (HFP 330 / 50 MHz), same `DPHY_BIT_CLOCK 660000`,
   > same `LCDCFG0 = CLKPOL(1)|CLKBYP(1)|CLKDIV(0)` with GCK = PLLADIV2/8 = 50 MHz.
   > So there is **no board-variant ambiguity**. (A newer VS-Code fork of the same examples
   > exists at `github.com/mchpgfx/mgsh_sam9x75_vs` — same configs, nothing new.)
2. **Microchip AN5753** (DS00005753) "Adding Support for a Custom MIPI Display on a SAM9X7 under Linux" —
   the *Linux* procedure. **Its clock guidance is critical (see §4).**
3. **Waveshare `esp_lcd_dsi`** (`Waveshare-ESP32-components`) — vendor panel driver, confirms MCU seq.
4. Mainline `panel-waveshare-dsi.c` — the driver we patch.

---

## 2. What lights the panel

### (A) MCU init over I²C `0x45` (100 kHz) — **no AES**
Exactly the MGS `initSeq`, 1 ms apart:
```
0xC0=0x01   0xC2=0x01   0xAC=0x01   0xAD=0x01
```
Then **after** the DSI video is up (MGS `brightSeq`, +50 ms):
```
0xAB=55     0xAA=0x01
```
- `0xAB` is the **backlight PWM and it is INVERTED**: `0x00` = full bright, `0xFF` = **off**
  (verified live: writing `0xFF` killed the backlight). The stock RPi formula `0xff - brightness`
  is therefore *correct in direction*; the demo simply uses the value **55**.
- `0xAD/0xAC/0xC0/0xC2 = 0` turns the backlight **off** (verified live) — they are power/enable.
- **There is NO AES challenge-response** on this panel. That lock belongs only to the
  Raspberry-Pi MCU-bridge `.ko` variant. Dead end — do not revisit.

### (B) DSI link
2 data lanes, **RGB888**, **VIDEO + SYNC_PULSE** (demo `VID_MODE_TYPE(0)` = non-burst sync pulses),
**continuous clock** (demo `AUTO_CLKLANE_CTRL(0)`), **EoT packets OFF** (demo `EOTP_TX_EN(0)`).
In Linux that means panel `mode_flags`:
```c
MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_SYNC_PULSE | MIPI_DSI_MODE_NO_EOT_PACKET
```
(no `MIPI_DSI_CLOCK_NON_CONTINUOUS`). The dw-mipi-dsi core enables `EOTP_TX` **by default** unless
`MIPI_DSI_MODE_NO_EOT_PACKET` is set.

### (C) Timing — from the demo (`plib_dsi.c` + `plib_xlcdc.c`, they agree)
```
LCD_DCLK_KHZ 50000   (50 MHz)     720 x 720
H: front 330 | sync 32 | back 32  -> htotal 1114
V: front   8 | sync  4 | back 16  -> vtotal  748     (~60 Hz)
```
As a `drm_display_mode`:
```c
.clock = 50000,
.hsync_start = 720 + 330, .hsync_end = 720 + 330 + 32, .htotal = 720 + 330 + 32 + 32,
.vsync_start = 720 +   8, .vsync_end = 720 +   8 +  4, .vtotal = 720 +   8 +  4 + 16,
```
> The **330-cycle front porch** is panel-specific and unusual — every generic/AI-sourced timing
> (40/10/40, 120/200/32, etc.) is **wrong**. Use these values.

### (D) Clock polarity
Demo `LCDC_LCDCFG0 = CLKPOL(1) | CLKBYP(1)` = **0x3**. In Linux, CLKPOL comes from the panel's
bus flags, so the panel driver must set:
```c
connector->display_info.bus_flags |= DRM_BUS_FLAG_PIXDATA_DRIVE_NEGEDGE;
```
Without it `LCDCFG0 = 0x2` (CLKPOL=0) — tolerable at low pixel clocks, wrong at 50 MHz.

### (E) No DCS needed
The MGS demo sends **no DCS at all** (no `0x11`/`0x29`). The panel is driven purely by the
`0x45` MCU + the DSI video stream.

---

## 3. LCDC / GCLK clocking — the part that caused the most pain

The pixel clock is **GCLK ÷ CLKDIV** (`LCDC_LCDCFG0`), GCLK = generic clock on **peripheral
instance 25 (LCDC)**, whose **maximum is 75 MHz** (SAM9X7 peripheral table). Requests above that
are silently clamped (a 100 MHz request produced 75 MHz).

`atmel_hlcdc_crtc.c` (sam9x75 has `fixed_clksrc = true`) decides:
```c
div = DIV_ROUND_UP(sys_clk, mode_rate);
if (div < 2) { div = 2; }                 /* NO CLKBYP -> pixel = sys_clk / 2 */
else { ... if (div_low < 2) cfg |= ATMEL_XLCDC_CLKBYP; }   /* pixel = sys_clk */
```
Measured consequences:

| `assigned-clock-rates` | actual `lcd_gclk` | pixel clock | refresh |
|---|---|---|---|
| 50 MHz (== mode clock) | 50 MHz | **25 MHz** (÷2, no CLKBYP) | 30 Hz |
| 60 MHz *(AN5753)* | ~57–66 MHz | = GCLK (CLKBYP) | ~68–80 Hz |
| 66 MHz | 66.67 MHz | 66.67 MHz (CLKBYP) | 80 Hz |
| 100 MHz (clamped) | 75 MHz | 75 MHz (CLKBYP) | 90 Hz |

**Do not set GCLK equal to the mode clock** — it drops into the `÷2` path.

---

## 4. ★ AN5753 clock rule (the key insight)

AN5753 §5.2, for a panel whose `drm_display_mode.clock = 50000` (**same 50 MHz as ours**):

> "The pixel clock expected by the panel is 50 MHz. However, because of potential hardware
> limitations, experts recommend to program a **slightly higher clock frequency, 60 MHz** for
> example. In such case, the assigned clock rate is `<60000000>`."

Its reference node:
```dts
&hlcdc {
    clocks = <&pmc PMC_TYPE_PERIPHERAL 25>, <&pmc PMC_TYPE_GCK 25>, <&clk32k 1>;
    clock-names = "periph_clk", "sys_clk", "slow_clk";
    assigned-clocks = <&pmc PMC_TYPE_GCK 25>;
    assigned-clock-rates = <60000000>;
    status = "okay";
};
```
**Why it matters:** the GCLK is meant to run *above* the panel pixel clock. That headroom keeps the
DSI's DPI buffer fed. Forcing GCLK to exactly 50 MHz starves it → `INT_ST1` bit 19
(`dpi_buff_pld_under`) → **black screen**.

---

## 5. Debugging playbook (what actually worked)

**Serial:** `Workshop\serialcmd.ps1 -PerCmdMs <ms>` drives COM5 from `Workshop\rdk-cmds.txt`,
logs to `Workshop\rdk-shell.log`. Keep command lines **short** — long lines overrun the input
buffer and corrupt the echo.

**Hold a test pattern indefinitely** (for photos): make `modetest` the **last** line of the
cmds file (nothing after it), so it keeps waiting for Enter after the port closes:
```
fuser -k /dev/dri/card1 2>/dev/null
modetest -M atmel-hlcdc -s 49@47:720x720
```
Connector **49**, CRTC **47**. Measure real refresh with `-v` (prints `freq:`), which reveals the
*actual* pixel clock — the mode's nominal value can lie.

**Register peeks** (`devmem <addr> 32`):

| What | Address | Notes |
|---|---|---|
| `LCDC_LCDCFG0` | `0xf8038000` | b0 CLKPOL, b1 CLKBYP, [23:16] CLKDIV−2. Demo = **0x3** |
| DSI `PWR_UP` | `0xf8054004` | 1 = powered |
| DSI `MODE_CFG` | `0xf8054038`* | *`VID_MODE_CFG`; `0x3F00` = sync-pulse + LP blanking |
| DSI `VID_PKT_SIZE` | `0xf805403c` | 720 |
| DSI `VID_HSA/HBP/HLINE` | `0x48/0x4c/0x50` | `HLINE = htotal × lane_mbps / 400` |
| DSI `VID_VSA/VBP/VFP/VACT` | `0x54/0x58/0x5c/0x60` | 4 / 16 / 8 / 720 |
| DSI `PHY_STATUS` | `0xf80540b0` | **b0 = PLL lock**; `0x1529` = locked, clock lane active |
| DSI `INT_ST0/ST1` | `0xf80540bc/0xc0` | **ST1 b19 = `dpi_buff_pld_under`** |

**Clock tree:** `mount -t debugfs none /sys/kernel/debug` then
`grep lcd_gclk /sys/kernel/debug/clk/clk_summary`. (Rates are **read-only** — writing
`clk_rate` fails.)

**Panel-alive probe:** `cat /dev/urandom > /dev/fb0` fills the framebuffer with noise. Note the
console framebuffer is **black at boot** — that is *not* a failure; always judge with `modetest`.

---

## 6. Dead ends — do not repeat

- AES `0xB0` challenge/response (RPi-bridge variant only).
- Reverse-engineering `harmony.bin` (the only `mov #0x45` in 5.3 MB is a PNG parser `'E'` tag).
  The **MGS source** supersedes it entirely.
- Generic/AI-supplied panel timings (`clock-frequency = 32000000`, 40/10/40 porches) and
  `panel-simple` (cannot do the `0x45` MCU init).
- Setting GCLK == mode clock to get an "exact" pixel clock (drops into ÷2, starves the DSI).

---

## 7. Everything else on the RDK — WORKING

| Subsystem | Status | Key facts |
|---|---|---|
| Boot | ✅ root shell | kernel 6.18.x armv5tejl |
| Ethernet | ✅ 1 Gbps | **KSZ9131 @ MDIO 7** (not LAN8840@1); removed hardcoded `ethernet-phy@1` so `macb` auto-scans |
| Touch | ✅ | **Goodix GT9271** @ I²C `0x14` on **i2c7** (flexcom7 `f8014600`), IRQ pioC 15 |
| Camera | ✅ | PIC64 MJPEG @192.168.0.38 → GStreamer → `kmssink driver-name=atmel-hlcdc force-modesetting=true` |
| **Panel** | 🔧 displays, clock tuning | see §3–§4 |

DRM: **card0** = microchip-gfx2d (GPU, no output), **card1** = atmel-hlcdc. Busybox `pkill -f`
does **not** match `gst-launch-1.0` → a stale gst holds DRM master and later modesets get `EACCES`;
kill by PID via `fuser /dev/dri/card1`.

---

## 8. Build & deploy loop

VM `builder@BUILD-VM`. Driver source:
`~/sam9x75-rdk/buildroot/output/build/linux-custom/drivers/gpu/drm/panel/panel-waveshare-dsi.c`
(`.bak` = pristine; patched copy kept at `linux-image/panel-driver/panel-waveshare-dsi-rdk.c`).

```
# kernel change:
cd ~/sam9x75-rdk/buildroot && make HOSTCC=~/sam9x75-rdk/hostwrap/cc HOSTCXX=~/sam9x75-rdk/hostwrap/cxx linux-rebuild
# overlay-only change (DT):  (much faster - no kernel rebuild)
cd ~/SAM9X75-RDK/linux-image/buildroot && ./build.sh overlay
# then: scp the .itb to the PC, copy onto the SD FAT boot partition (mounts as E:) - NO reflash
```

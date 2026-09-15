# SAM9X75 Round Display Kit — Linux display & touch support

Everything needed to run the **Waveshare 4inch DSI LCD (C)** (720×720 round,
MIPI-DSI + Goodix GT9271 touch) on a **Microchip SAM9X75** under Linux.

Verified on hardware: SAM9X75 Curiosity / Round Display Kit, kernel
`6.18.17-linux4microchip-2026.04` (Buildroot BSP), 2026-09-07.

```
display/     panel driver + the DSI/LCDC fixes that make the image correct
touch/       GT9271 drivers (read the warning — the interrupt does not work)
dt-overlay/  device-tree overlay + FIT image entries
```

---

## 1. Display

The in-kernel driver `drivers/gpu/drm/panel/panel-waveshare-dsi.c`
(`CONFIG_DRM_PANEL_WAVESHARE_TOUCHSCREEN`) already knows this panel. It is an
**I²C** driver bound at `0x45` (the panel's power/backlight MCU) that finds the
DSI host through an of_graph endpoint — it is *not* a DSI child node.
`display/panel-waveshare-dsi-rdk.c` is that driver with this board's values;
`display/as-built/panel-waveshare-dsi.c` is the pristine upstream file to diff
against.

### What lights the panel

1. Six plain I²C writes to the MCU at `0x45`, 1 ms apart:
   `0xC0=01 0xC2=01 0xAC=01 0xAD=01`, then once video is running,
   `0xAB=55 0xAA=01`.
   - `0xAB` is the **backlight PWM and it is inverted**: `0x00` is full bright,
     `0xFF` is off. Microchip's demo uses `55`.
   - There is **no AES challenge/response** on this panel. That belongs only to
     the Raspberry-Pi MCU-bridge variant — a dead end, do not revisit.
2. DSI: **2 lanes, RGB888, video mode with sync pulses, continuous clock, EoT
   packets off** — in Linux terms
   `MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_SYNC_PULSE | MIPI_DSI_MODE_NO_EOT_PACKET`
   (the dw-mipi-dsi core enables EOTP by default unless you ask it not to).
3. **No DCS at all** — no `0x11`, no `0x29`. The MCU plus the video stream is
   the entire init.

### Timing — use exactly these values

```c
.clock = 50000,                          /* 50 MHz */
.hdisplay = 720, .hsync_start = 1050, .hsync_end = 1082, .htotal = 1114,
.vdisplay = 720, .vsync_start =  728, .vsync_end =  732, .vtotal =  748,
```

The **330-cycle horizontal front porch is panel-specific and unusual**. Every
generic or AI-sourced timing for this panel (40/10/40, 120/200/32, …) is wrong.
These come from Microchip's own MGS demo for this exact board and panel.

The panel also needs inverted pixel-clock polarity, which in DRM comes from the
panel's bus flags:

```c
connector->display_info.bus_flags |= DRM_BUS_FLAG_PIXDATA_DRIVE_NEGEDGE;
```

### The fixes in `display/patches/`

Applied to the kernel tree before building. Each is an idempotent Python script
that asserts on its anchor text, so it fails loudly instead of silently.

| Patch | Problem | Fix |
|---|---|---|
| `01_dw-mipi-dsi_lbcc_lane_rate.py` | Upstream's non-burst `lbcc` derives line timing from `mode->clock`, which cancels out and effectively assumes `lane_mbps` is the theoretical minimum. The PHY actually runs with margin, so the host timed every line ~20% short — a **horizontally squeezed, torn image**. | use `dsi->lane_mbps` for burst *and* non-burst, and restore the ×10/8 margin in the mchp lane-rate calculation |
| `02_atmel-hlcdc_cfg5_disppol_guardtime.py` | LCDC output polarity / guard time | match the MGS demo |
| `03_dw-mipi-dsi-mchp_lane_margin_660.py` | lane rate | target **660 Mbps** — exactly what the MGS demo programs (`DPHY_BIT_CLOCK 660000`), i.e. the 600 Mbps minimum + 10% |
| `04_atmel-hlcdc_clkbyp.py` | when `sys_clk == mode clock`, `atmel_hlcdc_crtc.c` takes its `div < 2` branch and outputs **pixel = sys_clk / 2** (25 MHz, 30 Hz) | set `ATMEL_XLCDC_CLKBYP` so the pixel clock is exactly the mode clock |

Patch `05_panel-waveshare-dsi_physical_size.py` is separate and is described
in its own section below - apply it too.

With 01-04 applied: `LCDCFG0 = 0x3` (CLKPOL|CLKBYP), DSI
`PHY_STATUS = 0x1529` (PLL locked, clock lane active), and
`VID_HLINE_TIME = 1839`, which is `htotal × lane_mbps / 400` as it should be.

### GCLK — do not set it equal to the mode clock

The pixel clock is GCLK ÷ CLKDIV on LCDC peripheral instance 25, whose maximum
is **75 MHz** (higher requests are silently clamped — a 100 MHz request yields
75 MHz). AN5753 recommends running GCLK *slightly above* the panel's pixel clock
so the DSI's DPI buffer stays fed; forcing GCLK to exactly the mode clock starves
it and sets `INT_ST1` bit 19 (`dpi_buff_pld_under`). With patch 04 the divider is
bypassed and 50 MHz is used directly, which works — bit 19 still latches but is
cosmetic at this timing, and the image is correct.

Measured behaviour, for reference:

| `assigned-clock-rates` | actual `lcd_gclk` | pixel clock | refresh |
|---|---|---|---|
| 50 MHz (== mode clock) | 50 MHz | 25 MHz (÷2, no CLKBYP) | 30 Hz |
| 60 MHz (AN5753's suggestion) | ~57–66 MHz | = GCLK | ~68–80 Hz |
| 100 MHz (clamped) | 75 MHz | 75 MHz | 90 Hz |

### A 50 px horizontal offset — and how to fix it without rebuilding

This panel places the framebuffer **~50 px to the right** of the glass. Vertical
colour bars hide this completely (the stripes simply move), so it only becomes
visible once you display something centred.

It can be corrected **entirely from userspace**, with no kernel or DT change, by
moving the active window earlier in the line: take pixels out of sync + back
porch and give them to the front porch, keeping `htotal` — and therefore the
pixel clock and refresh rate — unchanged.

```
base:  H 720 | fp 330  sync 32  bp 32 | total 1114
tuned: H 720 | fp 380  sync  8  bp  6 | total 1114
```

The kernel accepts this through a plain `DRM_IOCTL_MODE_SETCRTC` carrying a
modified `drm_mode_modeinfo`. To fix it in-kernel instead, bake the tuned porches
into the panel driver's mode.

### ⚠ The panel's reported physical size is wrong upstream — fix it first

`panel-waveshare-dsi.c` hardcodes `width_mm = 154; height_mm = 86` in
`ws_panel_get_modes()` for **every** model. That is the 7-inch 800×480 DPI
panel's size. This panel is a 720×720 round one whose active area is a **72 × 72
mm square**.

This is not cosmetic. Anything that corrects for the display aspect ratio
concludes the pixels are 154/86 = 1.79× wider than tall and squeezes every
frame's width to about 3/5. GStreamer's `kmssink` does exactly that. Measured on
this board from `/sys/kernel/debug/dri/1/state` (the committed atomic state —
`modetest -p` will not show you this):

| source fed to kmssink | destination on the CRTC | source columns used |
|---|---|---|
| 640×480 | `576x720+72+0` | `384x480+0+0` |
| **720×720 (square!)** | `432x720+144+0` | `432x720+0+0` |
| 480×480 | `432x720+144+0` | `288x480+0+0` |

So even a perfectly square source is displayed as 432×720 with black bars down
both sides, and only the left 60 % of the source columns survive.

**Nothing in the pipeline can work around it** — `render-rectangle`,
`display-width`/`display-height` and `plane-properties` were each measured to
make no difference whatsoever, because kmssink recomputes the rectangle and
calls `drmModeSetPlane` on every frame.

Apply `display/patches/05_panel-waveshare-dsi_physical_size.py`, which moves the
size into `struct ws_panel_data` so each model carries its own and sets 72 × 72
mm for the round panel. `display/panel-waveshare-dsi-rdk.c` already includes it.

### Hardware video plane — free YUV conversion and scaling

`modetest -M atmel-hlcdc -p` lists four planes. Three are RGB-only; the
**high-end overlay plane** (id 43 on this board) also advertises
`AYUV YUYV UYVY YVYU VYUY NV21 NV61 YU16 YU12` and has a hardware scaler.

Point `kmssink plane-id=43` at it and an MJPEG stream needs **no software colour
conversion and no software scaling** — worth ~130 ms per frame on this SoC
(measured: 298 ms/frame with a software convert+scale to 720×720, versus 123
ms/frame straight to the plane).

Two caveats:

- It only negotiates with **`force-modesetting=false`** and a CRTC that is
  already configured. With `force-modesetting=true` kmssink grabs the RGB-only
  primary plane and the pipeline dies with `not-negotiated (-4)`.
- kmssink always preserves the display aspect ratio, and a typical Buildroot
  build has no `videocrop`, `videobox` or `capssetter` — so a 4:3 feed on this
  square panel comes out letterboxed, with black bars left and right.

  The fix that works, at no cost: give kmssink a **render rectangle larger than
  the CRTC** and let DRM clip it — `render-rectangle=<-120,0,960,720>` for a
  640×480 source on a 720×720 panel. atmel-hlcdc clips the destination
  *symmetrically* and adjusts the source rectangle with it (verified on glass),
  so the result is a true **centre** crop that fills the panel with no
  distortion and no extra CPU: the round display then shows the largest circle
  that fits inside the camera's rectangular frame. Note that `modetest -p`
  prints `0,0` for the plane's legacy position fields either way, so it cannot
  be used to confirm this — only the panel can.

  A `pixel-aspect-ratio` capsfilter is **not** a usable alternative: a
  capsfilter can only restrict what upstream offers, and jpegdec only ever
  offers 1/1, so the pipeline dies with `not-negotiated (-4)`.

---

## 2. Touch — the interrupt does not work on this board

`Goodix-TS` binds correctly, identifies the chip and creates
`/dev/input/event0` with sane 0..719 axes — **and then emits nothing**, because
the interrupt never fires:

```
$ dmesg | grep -i goodix
Goodix-TS 1-0014: ID 9271, version: 1060
input: Goodix Capacitive TouchScreen as .../i2c-1/1-0014/input/input0

$ grep gt9271 /proc/interrupts
 37:          1     GPIO  15 Edge      gt9271          # stays at 1 for ever
```

The controller itself is perfectly healthy over I²C:

```
$ echo 1-0014 > /sys/bus/i2c/drivers/Goodix-TS/unbind
$ i2ctransfer -y 1 w2@0x14 0x81 0x40 r6
0x39 0x32 0x37 0x31 0x60 0x10        # "9271", firmware 0x1060
$ i2ctransfer -y 1 w2@0x14 0x81 0x4e r1
0x80                                  # buffer ready, 0 touch points
```

So `touch/touch-gt9271-i2c.py` **unbinds the kernel driver and polls the
controller directly**:

- `0x814E` — buffer status: bit 7 = data ready, bits 3:0 = number of points
- `0x814F` — points, 8 bytes each: `id, x_lo, x_hi, y_lo, y_hi, w_lo, w_hi, pad`
- write `0` back to `0x814E` to release the buffer

Pure stdlib Python talking to `/dev/i2c-N` with `I2C_RDWR` (no python-evdev, no
compiler needed); costs a few percent CPU at ~25 polls/second.
`touch/touch-evdev.py` is the same interface reading `/dev/input/eventN`, for
when the interrupt is fixed — the two are drop-in interchangeable.

**To fix it properly:** the overlay declares
`interrupts = <15 IRQ_TYPE_EDGE_FALLING>` on `pioC`. Try `IRQ_TYPE_EDGE_RISING`
or a level trigger, and confirm against the RDK schematic that the touch INT pin
really is **PC15** — that pin was inherited from the hx8394 kit's routing and has
never been verified against this board. Also consider wiring `reset-gpios`,
currently left out because the panel already answers at `0x14` so the
power-on address-select dance is unnecessary.

---

## 3. Device tree

`dt-overlay/sam9x75_curiosity_ws4round.dtso` — the panel at `0x45` and touch at
`0x14` on the DSI-FPC I²C bus, `&dsi` ports wired to `&hlcdc`, GPU enabled, and
the PWM backlight disabled (the panel MCU owns brightness).

Three things that cost time here:

- The panel/touch I²C bus is **`&i2c6`** in the device tree, and appears at
  runtime as adapter **`i2c-1`** (`f8014600.i2c`, flexcom7).
- The overlay needs `#include <dt-bindings/clock/at91.h>` for the `PMC_TYPE_*`
  macros, or `dtc` fails with `Unexpected 'PMC_TYPE_PERIPHERAL'`.
- A literal `*/` inside a block comment closes it early and breaks `dtc`.

`dt-overlay/sam9x75_curiosity.its.additions` holds the `fdt_ws4round` image and
`ws4round` configuration to splice into the BSP's FIT `.its`, after which
`sam9x75_curiosity.itb` is rebuilt with `mkimage`.

Select the overlay in U-Boot. This BSP runs
`bootcmd = run at91_display_detect; run bootcmd_boot`, so:

```
setenv at91_overlays_config '#ws4round'
setenv at91_display_detect 'run at91_prepare_bootargs'
```

The second line matters. It neutralises the automatic display probe — which
would otherwise append its own `#mipi` overlay and give you two panels — while
still running `at91_prepare_bootargs`, which sets the kernel bootargs.

---

## 4. Bring-up checklist

```sh
i2cdetect -y 1                       # expect 0x45 (panel MCU) and 0x14 (touch)
dmesg | grep -Ei 'waveshare|panel|dsi|goodix'
cat /sys/class/drm/card1-DSI-1/status    # connected
cat /sys/class/drm/card1-DSI-1/modes     # 720x720
modetest -M atmel-hlcdc -s <conn>@<crtc>:720x720      # colour bars
devmem 0xf8038000 32                 # LCDC_LCDCFG0  -> 0x00000003
devmem 0xf80540b0 32                 # DSI PHY_STATUS -> 0x1529 (PLL locked)
devmem 0xf80540c0 32                 # DSI INT_ST1, bit 19 = dpi_buff_pld_under
```

Useful register map (`devmem <addr> 32`):

| What | Address |
|---|---|
| `LCDC_LCDCFG0` (b0 CLKPOL, b1 CLKBYP, [23:16] CLKDIV−2) | `0xf8038000` |
| DSI `PWR_UP` | `0xf8054004` |
| DSI `VID_MODE_CFG` | `0xf8054038` |
| DSI `VID_PKT_SIZE` | `0xf805403c` |
| DSI `VID_HSA/HBP/HLINE_TIME` | `0xf8054048 / 4c / 50` |
| DSI `VID_VSA/VBP/VFP/VACT` | `0xf8054054 / 58 / 5c / 60` |
| DSI `PHY_STATUS` (b0 = PLL lock) | `0xf80540b0` |
| DSI `INT_ST0/ST1` | `0xf80540bc / c0` |

Notes that save time: DRM **card0** is microchip-gfx2d (the GPU, no output) and
**card1** is atmel-hlcdc. The console framebuffer is black at boot — that is not
a failure, always judge with `modetest`. Busybox `pkill -f` does not match
`gst-launch-1.0`, so free the display by file descriptor instead:
`fuser -k /dev/dri/card1`.

---

## 5. Dead ends, so nobody repeats them

- AES `0xB0` challenge/response — Raspberry-Pi MCU-bridge variant only.
- Reverse-engineering the bare-metal `harmony.bin`: the only `mov #0x45` in
  5.3 MB is a PNG parser's `'E'` tag. The MGS **source** supersedes it entirely.
- Generic panel timings and `panel-simple` — the latter cannot do the `0x45`
  MCU init at all.
- Setting GCLK equal to the mode clock to get an "exact" pixel clock: it drops
  into the ÷2 path and starves the DSI.

## 6. Sources

- Microchip MGS demo for this board — `github.com/mchpgfx/mgsh_sam9x7`, config
  `dsi_xlcdc_rgba8888_ws_9x75_curiosity_720x720_round`. The authoritative
  source for the panel's init sequence and timing.
- Microchip **AN5753** (DS00005753), "Adding Support for a Custom MIPI Display
  on a SAM9X7 under Linux" — the clocking guidance.
- Waveshare's own `esp_lcd_dsi` component — independently confirms the MCU
  sequence.
- Panel product page: <https://www.waveshare.com/4inch-dsi-lcd-c.htm>

# Phase 2 — Buildroot Linux image + round-panel bring-up

Boots Linux on the **SAM9X75 Round Display Kit** with the round 720×720
Waveshare panel and Goodix touch working, on a **spare** SD card. The bare-metal
MGS demo card is never touched. Work is **headless**: card reader + Ethernet only
(no serial, no SAM-BA).

> Build host: **Ubuntu 26.04 VM** at `builder@BUILD-VM` (same box as the
> Gaudi2 dev VM). Copy this folder up with `pscp -r`, drive it with `plink`.
> Buildroot tree lives at `~/sam9x75-rdk/`, artifacts at `~/SAM9X75-RDK/linux-image/`.
> (`build.sh` is path-agnostic, so WSL2 still works as a fallback.)

## What's in here

| Path | What it is |
|---|---|
| `dt-overlay/sam9x75_curiosity_ws4round.dtso` | DT overlay: Waveshare panel on `&i2c6@0x45` (of_graph → `&dsi`) + Goodix GT9271 on `&i2c6@0x14` |
| `dt-overlay/sam9x75_curiosity.its.additions` | FIT image + config nodes so the overlay is bootable |
| `buildroot/linux.config.fragment` | kernel config deltas: enable stock `CONFIG_DRM_PANEL_WAVESHARE_TOUCHSCREEN` + goodix + backlight |
| `buildroot/buildroot.config.fragment` | target packages (modetest, evtest, i2c-tools, GStreamer) |
| `buildroot/build.sh` | orchestration: deps → fetch → config → build → overlay → flash |
| `panel-driver/RETIRED/` | the abandoned custom driver (stock in-tree driver supersedes it — see that folder's README) |
| `boot-partition/README-boot-select.md` | how to select the overlay offline in the FAT boot partition |

## Design in one paragraph

The panel is the COTS **Waveshare 4inch DSI LCD (C)** (a Raspberry Pi
accessory) — a 2-lane, RGB888, video-mode DSI panel, 50 MHz dot clock, 720×720.
**No driver work is needed:** the pinned BSP kernel `linux4microchip-2026.04`
already ships the mainline/RPi `panel-waveshare-dsi.c`
(`CONFIG_DRM_PANEL_WAVESHARE_TOUCHSCREEN`), whose `ws_panel_4_mode` (720×720 /
2 lanes, compatible **`waveshare,4inch-panel`**) is exactly this panel, including
the on-board **0x45** MCU power/backlight sequence. That driver is an **I2C
driver**: the panel node lives on the DSI-connector I2C bus (`&i2c6`) at 0x45 and
finds the DW-MIPI-DSI host (behind the XLCDC `&hlcdc`) via an of_graph endpoint —
so, unlike the hx8394 kit, it is *not* a `&dsi` child and there is no PWM
backlight. Touch is a plain mainline **Goodix GT9271** at **0x14** on the same bus.

## Build (on the VM)

```bash
# from Windows: pscp -r linux-image up, then over plink/ssh on the VM:
cd ~/SAM9X75-RDK/linux-image/buildroot
./build.sh deps          # one-time apt prerequisites (needs sudo)
./build.sh all           # fetch + config + build (first build is long, ~1-3 h)
./build.sh overlay       # compile ws4round.dtbo (also run after editing the .dtso)
```

Then follow `dt-overlay/sam9x75_curiosity.its.additions` to add `fdt_ws4round` +
`ws4round` to the BSP's `.its` and rebuild `kernel.itb` with `mkimage`
(`build.sh overlay` prints the exact spot to do this).

## Flash the SPARE card + boot

```bash
lsblk                                   # identify the spare card device
./build.sh flash /dev/sdX               # DOUBLE-CHECK sdX — never the demo card
```
Select the overlay offline → **`boot-partition/README-boot-select.md`**.

## Bring-up checklist (SSH in after DHCP)

1. Find the IP: check the router's DHCP table or `arp -a` after boot.
2. `ssh` in (image ships openssh + dhcp).
3. Panel & touch:
   ```bash
   dmesg | grep -Ei 'dsi|panel|waveshare|hlcdc|xlcdc|goodix|gt9271'
   i2cdetect -l ; i2cdetect -y <busN>        # expect 0x14 (touch) + 0x45 (MCU)
   modetest -M atmel-hlcdc                    # expect a 720x720 connector
   modetest -M atmel-hlcdc -s <conn>:720x720 -v   # test pattern on the panel
   evtest                                     # GT9271 multitouch events
   ```
4. Decode/bench the PIC64 feed (proves the Phase 4 pipeline before writing it):
   ```bash
   gst-launch-1.0 souphttpsrc location='http://192.168.0.38/feed.php?token=<TOKEN>' \
     ! multipartdemux ! jpegdec ! fpsdisplaysink text-overlay=false sync=false
   ```
   Then swap `fpsdisplaysink` → `kmssink` to render on the round panel. Expect
   ≥ ~12 fps (ARMv5 software JPEG; XLCDC does any scaling on a hardware plane —
   never CPU-scale).

## Known verify-on-bench unknowns (small, mechanical)

- **Touch RESET GPIO** — left unwired in the overlay (the panel answers at 0x14
  without the reset address-select dance). If touch won't probe, set
  `reset-gpios` from the RDK schematic. Touch INT is on **PC15** (reused from the
  hx8394 kit's connector routing).
- **`kernel.itb` assembly path** — the exact place the BSP builds the `.itb`
  varies by release; `build.sh overlay` locates it and prints the `mkimage` step.
- **Boot-time overlay selection** — `uEnv.txt` vs `boot.scr` vs saved env: pick
  the one your built `sdcard.img` actually uses (all three documented in
  `boot-partition/`).

## Status

Artifacts corrected 2026-09-03 to use the stock in-tree Waveshare driver (custom
driver retired; DT overlay + build config fixed). **Base image building on the
VM** (`~/sam9x75-rdk/build.log`) — next: `build.sh overlay`, assemble
`kernel.itb`, flash the spare SD, then bench + bring-up on the board. See
`SAM9X75-RDK_MD/PHASE2-HANDOFF.md` for the resume checklist.

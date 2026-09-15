# SAM9X75 Round Display Kit — Linux, touch, camera & on-board console

Everything needed to bring up the **Waveshare 4inch DSI LCD (C)** — a 720×720
round MIPI-DSI panel with Goodix GT9271 touch — on a **Microchip SAM9X75** under
Linux, plus a small on-board Python/cairo console that shows the live feed from a
PIC64 webcam with arm/disarm and camera controls.

**Status (2026-09-07): panel, touch and camera all working on the bench; the
console auto-starts at boot.** Verified on SAM9X75 Curiosity / RDK, kernel
`6.18.17-linux4microchip-2026.04` (Buildroot BSP).

> **Start here for the reusable part:** [`linux-drivers/`](linux-drivers/) is
> self-contained — the panel driver, the DSI/LCDC fixes, the GT9271 touch driver
> and userspace poller, and the device-tree overlay, with a thorough
> [README](linux-drivers/README.md). If you only want this panel working on a
> SAM9X7, that folder is all you need.

## What's in here

| Phase | What | Where | State |
|---|---|---|---|
| 1 | PIC64 fan-out relay + LAN-token camera endpoints | `pic64-fanout/` | ✅ deployed |
| 2 | Buildroot image + round-panel bring-up | `linux-image/`, `linux-drivers/` | ✅ on hardware |
| 3 | PC-side PHP console | `console-php/` | ⚠ built, not yet run |
| 4 | On-board Python/cairo console | `rdk-console/` | ✅ auto-starts at boot |

Full documentation lives in **[`SAM9X75-RDK_MD/`](SAM9X75-RDK_MD/)** — see its
[index](SAM9X75-RDK_MD/README.md). The on-board app's live document is
[`phase4-console-app.md`](SAM9X75-RDK_MD/phase4-console-app.md); the
register-by-register panel bring-up is in `round-panel-linux-bringup.md`.

## Hardware

- **SoC:** Microchip SAM9X75 (Curiosity / Round Display Kit)
- **Panel:** Waveshare 4inch DSI LCD (C), 720×720 round, MIPI-DSI 2-lane RGB888
- **Touch:** Goodix GT9271 over I²C — *polled*, because the INT line does not fire
  on this board (see the driver README for the fix path)
- **Camera:** PIC64GX webcam serving MJPEG over the LAN

## Configuration — set your own secrets before use

This repository ships **placeholders, not real credentials.** Set your own before
deploying:

| Setting | File(s) | Placeholder |
|---|---|---|
| Board root password | `rdk-console/S40rdk-net` | `CHANGEME` |
| LAN shared-secret token | `pic64-fanout/webroot/config.append.php`, `console-php/src/config.php`, `rdk-console/board/config.py` | `CHANGE_ME_LAN_TOKEN` |
| PC console login | `console-php/src/config.php` | `admin` / `changeme` |

The LAN token gates the login-less camera endpoints (`feed.php` / `snapshot.php` /
`control_api.php`) and is additionally restricted to the `192.168.0.0/24` subnet.
Change it on the board and in every client, keeping the values identical. The IP
addresses in the docs (`192.168.0.38` camera, `192.168.0.39` board) are this
bench's static layout — adjust them to your own network.

## Not included in this repository

Large build outputs and third-party / proprietary material are excluded via
[`.gitignore`](.gitignore) — build them, or fetch them from the vendor:

- **Boot & build outputs** — `boot-images/` (including the ~900 MB `sdcard.img`
  and the `.itb` variants) and compiled `*.ko` / `*.dtbo`. Rebuild from
  `linux-image/` (Buildroot BSP).
- **Waveshare driver package** — `DesignFiles/Waveshare-DSI-LCD-main/`, the
  unmodified vendor package. It originates from Waveshare's **Raspberry Pi**
  driver and does **not** run on the SAM9X75 as-is; the working SAM9X75 port —
  the DSI frequency and screen-alignment changes — is in
  [`linux-drivers/`](linux-drivers/). A verbatim snapshot of the stock package
  is mirrored at
  <https://github.com/bvalchev85-ctrl/waveshare-dsi-lcd-mirror> (or get it from
  Waveshare, panel product page linked in the driver README).
- **Microchip demo firmware & user guides** — `DesignFiles/Firmware-Binaries/`,
  the bare-metal `baremetal-test/*.bin`, and the RDK `*.pdf` guides. These are
  Microchip's to distribute; get them from Microchip / the MPLAB Graphics Suite.

## Licensing & provenance

This repository mixes code of different origins — **no single licence is asserted
over all of it:**

- The **kernel driver sources** under `linux-drivers/display/` and
  `linux-drivers/touch/` derive from the mainline Linux kernel
  (`panel-waveshare-dsi.c`, `Goodix-TS`) and carry their original authors and
  **GPL-2.0** terms — see the file headers.
- **Panel init values and timings** come from Microchip's MGS demo for this board
  (`github.com/mchpgfx/mgsh_sam9x7`) and Microchip **AN5753**.
- The **console, deploy scripts and documentation** are this project's own work.

Before reusing or redistributing, add a top-level `LICENSE` that respects the
GPL-2.0 provenance of the kernel-derived files and the ownership of the Microchip
and Waveshare material.

## Sources

- Microchip MGS demo — `github.com/mchpgfx/mgsh_sam9x7`
- Microchip AN5753 (DS00005753) — *Adding Support for a Custom MIPI Display on a
  SAM9X7 under Linux*
- Waveshare 4inch DSI LCD (C) — <https://www.waveshare.com/4inch-dsi-lcd-c.htm>

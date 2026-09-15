# SAM9X75 Round Display Kit (RDK) — Reference Notes

_Source: Microchip "Round LCD Instrument Cluster Reference Design" page + SAM9x75 RDK
User's Guide (MGS Harmony), fetched via ProductInfoMcpServer 2026-09-02._

## What it is
Microchip **Round LCD Instrument Cluster** reference design — a round-display HMI demo
(motorbike/EV instrument cluster) running as a **bare-metal** application built with the
**Microchip Graphics Suite (MGS) Harmony**. Target markets: Automotive, Electric Vehicle,
Human Interface, 32-bit MPU.

> Note: Hardware design guides, files, and firmware are gated behind a request form on
> Microchip's site. Example GUI firmware is public on GitHub (below).

## Hardware platform — SAM9x75 Round Display Kit (RDK)
- MPU: **SAM9X75D2G** (SAM9X75 family)
- Currently demoed on the **SAM9x75 Curiosity Development Board** (`EV31H43A`); a
  form-factor board with an updated LCD + **maXTouch** is in development.

On-board peripherals:
- Gigabit Ethernet (with TSN)
- 2 Gbit SDRAM embedded in SiP
- **WILCS02PE** Wi-Fi
- **WBZ351PE** Bluetooth LE (with PTA)
- **MIPI-DSI display, 720 × 720**
- QSPI Flash
- NAND Flash

## MPU — SAM9X75
- ARM926EJ-S CPU, up to **800 MHz**, cost-optimized
- Display: **MIPI-DSI**, **LVDS**, **RGB** interfaces; **2D graphics acceleration** (GPU + LCD controller with multi-layer overlay)
- Displays up to **1024 × 768**
- Gigabit Ethernet w/ TSN, CAN-FD
- Targets: industrial, medical, home automation, security/access control (biometrics)

## Software stack
- **MGS Harmony** (Microchip Graphics Suite) — no per-unit license fees
- Built in **MPLAB X IDE**
- Uses on-chip GPU + LCD controller; multi-layer LCD used to overlay GUI (e.g. nav map
  under gauge needles)
- **Boot:** FAT32-format a microSD, copy `boot.bin` + `harmony.bin` to it, insert in the
  uSD slot on the **back** of the board.

## Example applications (public firmware)
GitHub: **https://github.com/mchpgfx/mgsh_sam9x7**
- **MGS Quickstart** — starting point for GUI dev — `mgs_quickstart/firmware/mgs_qs_9x75_rdk.X`
- **MGS Motorbike** — round instrument-cluster UI, vector gauge needles, simulated nav map overlay — `showcase/motorbike_rdk/`
- **MGS Coffee Maker** — smart-appliance UI, sliding overlay menu, low CPU — `showcase/coffeemaker_rdk/`
- Related demos: Home Automation HMI, IoT Thermostat
- Pre-built binary ZIPs per app (extract → `boot.bin` + `harmony.bin` → microSD).

## Key links
- Reference design: https://www.microchip.com/en-us/tools-resources/reference-designs/round-lcd-instrument-cluster-reference-design
- RDK User's Guide (MGS Harmony): https://developerhelp.microchip.com/xwiki/bin/view/software-tools/mgs/dev-kits/rdk-mgsh-ug/
- Curiosity board (EV31H43A): http://www.microchip.com/developmenttools/ProductDetails/EV31H43A
- Firmware repo: https://github.com/mchpgfx/mgsh_sam9x7

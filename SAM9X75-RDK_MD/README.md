# SAM9X75-RDK — project index

Home-security console on the **SAM9X75 Round Display Kit**: a 720×720 round
touch panel showing the live feed from the PIC64 webcam, with arm/disarm and
camera controls. The webcam stays viewable from the PC at the same time.

**Status 2026-09-07 — panel, touch and camera all working on the bench, and the
console starts by itself at boot.**

| Phase | What | State |
|---|---|---|
| 1 | PIC64 fan-out relay + LAN token (`pic64-fanout\`) | ✅ deployed on the webcam board |
| 2 | Buildroot Linux image + round-panel bring-up (`linux-image\`, `linux-drivers\`) | ✅ verified on hardware |
| 3 | PC-side PHP console (`console-php\`) | ⚠ built, never run — this PC has no PHP runtime |
| 4 | On-board console app (`rdk-console\`) | ✅ running, auto-starts at boot |

## Where to look first

| If you want to… | Read |
|---|---|
| understand or change the on-board app | **`phase4-console-app.md`** ← the live document |
| port the display/touch to another SAM9X75 board, or publish it | **`..\linux-drivers\README.md`** |
| know how the panel was brought up, register by register | `round-panel-linux-bringup.md` |
| rebuild the Linux image | `PHASE2-HANDOFF.md` (historical build record) |
| understand LAN vs direct-cable addressing | `networking-dual-mode.md` |
| recover the board / restore the demo card | `backup-and-recovery.md` |
| machine-readable panel/touch/plane facts | `..\reference\panel-bringup-spec.json` |

## Folder map

```
SAM9X75-RDK\
├── SAM9X75-RDK_MD\      all documentation (this folder)
├── linux-drivers\       display + touch + DT overlay, self-contained for GitHub
├── rdk-console\         Phase 4: the on-board Python/cairo console
│   ├── board\           what is deployed to /opt/rdk-console
│   ├── shots\           frames captured from the running panel
│   ├── deploy.ps1       sync / run / restart / install
│   ├── S40rdk-net       boot: static IP + sshd
│   └── S99rdk-console   boot: the console
├── pic64-fanout\        Phase 1: the webcam board's PHP endpoints
├── console-php\         Phase 3: the PC-side console
├── linux-image\         Buildroot build system (build.sh, config fragments)
├── boot-images\         the .itb variants + one base sdcard.img + p1 backup
├── baremetal-test\      Microchip MGS reference firmware (bare-metal demos)
├── reference\           panel spec JSON + Waveshare vendor source
├── preview\             HTML UI mockups (the design of record) + renders
└── DesignFiles\         datasheets, board photos, panel reference design
```

## The board, in one place

| | |
|---|---|
| Address | **192.168.0.39** (static, set by `S40rdk-net`) — same on the LAN and over a direct cable to the PIC64 |
| Login | `ssh root@192.168.0.39`, password `CHANGEME`; this PC's ed25519 key is installed |
| Serial | FTDI FT232 on **COM23** → `Workshop\rdk-serial.ps1 -File cmds.txt` |
| Camera | PIC64 webcam at **192.168.0.38** |
| Console | `/etc/init.d/S99rdk-console {start\|stop\|restart\|status}`, log `/tmp/rdk-console.log` |
| Screenshot | `kill -USR1 $(cat /var/run/rdk-console.pid)` → `/tmp/rdk-frame.png` |

## Things that will bite you again

- **No `/dev/fb0`**, no compiler, no PIL/numpy on the board — hence cairo via
  ctypes straight onto `/dev/dri/card1`.
- **`systemd` is installed but is not PID 1** — `systemctl` does nothing.
- **No `pkill`/`pgrep`** in this busybox. Free the display with
  `fuser -k /dev/dri/card1`.
- **No RTC and no `ntpd`** — the console takes the time from the PIC64's HTTP
  `Date` header.
- **cairo gradients cost ~9 µs/pixel** on this FPU-less ARM926, and letting
  cairo *scale* a mask costs 31 ms versus 2.7 ms unscaled. Cache, never compute
  per frame.
- **The build VM lives on the other PC.** Everything since 2026-09-07 was done
  from userspace for that reason — including the panel alignment fix.

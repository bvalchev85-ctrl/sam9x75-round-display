# Phase 4 — On-board console app (`rdk-console`)

The interactive home-security console that runs **on the SAM9X75 RDK** and shows
the PIC64 webcam feed, arm/disarm state and the camera sliders.

Source: `SAM9X75-RDK\rdk-console\`  → deployed to `/opt/rdk-console/` on the board.

---

## 1. Why it is written this way

The board image constrains the design hard. Verified on the running board
(2026-09-07):

| Constraint | Consequence |
|---|---|
| **No `/dev/fb0`** (`CONFIG_FB_DEVICE` off; only in-kernel DRM fbdev *emulation*) | Cannot write a framebuffer the easy way → talk to `/dev/dri/card1` via DRM dumb buffers |
| **No compiler on the board**, and the cross-build VM lives on the *other* PC | No native C/C++ (so no new EGT app), no kernel/DT rebuilds → everything must be userspace + interpreted |
| **No `PIL`, `numpy`, `gi`** in python3 (3.12.9) | No image/array libs → draw with **cairo via ctypes** (`libcairo.so.2` is present because EGT pulls it in) |
| **No gst `compositor` / `imagefreeze` / `multifilesrc`** | GStreamer cannot overlay UI on video → camera view is full-screen, UI is a separate mode |
| **No `pkill` / `pgrep`** in this busybox | Service control uses `start-stop-daemon` + pidfile, and `fuser -k /dev/dri/card1` |
| **ARM926EJ-S, no FPU** | cairo gradients cost **~9 µs/pixel** → never compute a gradient per frame (see §4) |

## 2. Layout

```
rdk-console\
├── board\                  # everything that is scp'd to /opt/rdk-console
│   ├── kms.py              # DRM/KMS dumb-buffer client (pure ctypes+ioctl)
│   ├── cairo_ffi.py        # ctypes binding for the cairo calls we use
│   ├── theme.py            # colours/geometry transcribed from the mockup
│   ├── icons.py            # vector icons ported from the mockup's SVG
│   ├── screens.py          # menu / security / settings / camera-wait pages
│   ├── touch.py            # evdev reader  (unused - see §5)
│   ├── touch_i2c.py        # GT9271 polled over I2C  (the one that works)
│   ├── camera.py           # PIC64 probe, control API, gst live view
│   ├── console.py          # main app + state machine
│   ├── config.py           # defaults, overridable by /etc/rdk-console.json
│   ├── smoke.py            # render the pages + dump PNGs
│   ├── bench.py            # per-operation timings
│   └── calib.py            # panel alignment ruler / sweep / mode retiming
├── shots\                  # PNGs pulled back from the board
├── deploy.ps1              # sync / run / restart / install / synctime
├── S40rdk-net              # boot: fixed MAC, DHCP, sshd  (see §8)
└── S99rdk-console          # boot: the console itself
```

## 3. UI

Design of record: `preview\round-menu-720.html` (rendered → `menu720.png`).
`theme.py` transcribes its CSS values, so the glass matches the mockup.

Three carousel pages; swipe left/right or tap a side icon to move (the
carousel slides, ~44 fps), tap the centre to open, and **double-tap**
anywhere to leave a page - there is no back arrow.

- **Security** — big shield target, tap to arm/disarm, motion banner. State is
  persisted to `/var/lib/rdk-console/state.json`.
- **Camera** — live MJPEG from the PIC64 board (see §6).
- **Settings** — Brightness / Contrast / Saturation / Sharpness arc sliders,
  pushed to the PIC64 control API. **Range is 0..100** (that is what
  `control_api.php` clamps to — not 0..255).

The mockup's left icon was a thermostat; this project has no thermostat, so it
is a **shield** (Security). `icons.thermo()` is kept for a future page.

## 4. Performance — the one thing that matters on this core

Measured with `bench.py` on the board:

| Operation | Before | After |
|---|---|---|
| full-screen radial gradient ×2 (background) | **9 776 ms** | 265 ms (disk cache) |
| centre glow radial (250×250) | **442 ms** | **9 ms** (alpha sprite + mask) |
| background blit (2 MB) | 13 ms | 13 ms |
| camera icon 188 px | 15 ms | 15 ms |
| side icons ×2 | 20 ms | 20 ms |
| status line (mono + tracking) | 14 ms | 14 ms |
| **steady-state frame** | **513 ms** | **84 ms (~12 fps)** |

Two rules came out of this:

1. **Never compute a gradient per frame.** The static background is rendered
   once into a buffer we own and cached zlib-compressed at
   `/var/cache/rdk-console/bg-v<N>.zz`; bump `BG_CACHE_VERSION` in `screens.py`
   when the drawing changes.
2. **Tint one alpha sprite instead of re-running a gradient.** The centre glow
   is a white radial-alpha sprite built once, then painted through
   `cairo_mask_surface()` in whatever accent colour the page needs — 48× faster
   and it made per-page accent colours free.

Then the carousel had to *slide* rather than snap, which needed another pass:

| Operation | Cost | Fix |
|---|---|---|
| scaled sprite blit (mask, 0.46x) | **31 ms** | pre-render per 8 px size bucket, blit 1:1 -> **2.7 ms** |
| status line + dots, every frame | 23 ms | fold into a cached `chrome_layer` surface -> one blit |
| centre glow, every frame | 10 ms | fold into the chrome too (keyed by accent colour) |
| waiting for the page-flip event | 16 ms | collect the *previous* flip's event so the vblank wait overlaps drawing |
| chrome rebuild mid-slide | 47 ms hitch | pin `chrome_index` to the start item for the whole slide |
| full-screen repaint per frame | 14 ms | clip to `SLIDE_BAND` - the rows that actually move |
| **animation frame** | **128 ms -> 22.6 ms** | **44 fps, 11 frames per 260 ms slide** |
| resting frame | 94 ms -> 26.6 ms | |

Two further findings worth keeping:

* **Never let cairo scale a mask.** A 0.46x scaled sprite blit costs 31 ms; the
  same sprite blitted 1:1 costs 2.7 ms. Sizes are bucketed to 8 px
  (`ICON_SIZE_STEP`) and prebuilt by `Renderer.prewarm()` so the first swipe
  does not stutter.
* **Single-buffering was visible.** Drawing into the scanned-out buffer made the
  10 s clock refresh flicker on the glass. `kms.Display` now allocates two dumb
  buffers and page-flips, which also made the slide tear-free. Band-limited
  frames are only safe because a full frame is drawn into *both* buffers before
  a slide starts.

## 5. Touch — the interrupt is dead, so we poll

`/proc/interrupts` shows the `gt9271` GPIO-15 edge interrupt at **1** since
boot and it never increments, no matter how much the panel is touched. So
`Goodix-TS` binds, creates `/dev/input/event0` with correct 0..719 axes, and
then emits nothing. `evtest` sees only its own capability header.

The controller itself is perfectly healthy over I²C:

```
# echo 1-0014 > /sys/bus/i2c/drivers/Goodix-TS/unbind
# i2ctransfer -y 1 w2@0x14 0x81 0x40 r6
0x39 0x32 0x37 0x31 0x60 0x10          # "9271", firmware 0x1060
# i2ctransfer -y 1 w2@0x14 0x81 0x4e r1
0x80                                    # buffer ready, 0 points
```

So `touch_i2c.py` unbinds the kernel driver and polls the GT9271 directly
(status `0x814E`, points from `0x814F`, write 0 back to release the buffer).
`touch.py` (evdev) is kept for the day the interrupt is fixed — the two expose
the same `poll()` contract.

**Proper fix, when the cross-build host is available again:** the DT overlay
declares `interrupts = <15 IRQ_TYPE_EDGE_FALLING>` on `pioC`; try
`IRQ_TYPE_EDGE_RISING` / `LEVEL_LOW`, and confirm the touch INT pin really is
PC15 against the RDK schematic. Until then polling costs a few % CPU and works.

## 6. Camera

Contract (from `pic64-fanout\webroot\`, Phase 1):

| Endpoint | Use |
|---|---|
| `GET /feed.php?token=…` | `multipart/x-mixed-replace` MJPEG, boundary `ffmpeg` |
| `GET /snapshot.php?token=…` | one JPEG |
| `GET /control_api.php?token=…` | `{"ok":true,"settings":{…}}` |
| `POST /control_api.php?token=…` | JSON body of changed keys → new settings |

Gated by LAN token + `192.168.0.0/24`, no login. Host candidates are tried in
order `pic64cam.local` → `10.42.0.1` → `192.168.0.38` so the same build works
on the LAN and over a direct RJ45 cable (`networking-dual-mode.md`).

The live view is a `gst-launch-1.0` pipeline. kmssink must be DRM master, so the
console **drops master**, runs gst, and takes master back on exit
(`camera.py`). While gst owns the CRTC the console cannot draw, so the camera
page has no overlay - a **double-tap** returns to the menu.

### Latency - what the delay actually was

Measured on the board, 40-50 frames per run:

| Stage | ms/frame | rate |
|---|---|---|
| feed arrival alone (`multipartdemux ! fakesink`) | 142 | 7.1 fps |
| + `jpegdec` | 169 | 5.9 fps |
| + software convert+scale to 720x720 (bilinear) | **298** | **3.4 fps** |
| + software convert+scale, nearest, BGRx 640 | 217 | 4.6 fps |
| **jpegdec straight to the hardware overlay plane** | **123** | **8.1 fps** |

The delay was **growing without bound**, for two reasons:

1. The software upscale cost 130 ms/frame, making the pipeline (3.4 fps) slower
   than the producer (7.1 fps), so frames queued for ever.
2. Nothing dropped frames, and kmssink synced on timestamps.

Fixes, all in `camera.py` / `config.py`:

* **`kmssink plane-id=43`** - the XLCDC **high-end overlay plane** takes
  jpegdec's I420 (`YU12`) natively *and* has a hardware scaler, so the whole
  convert+scale disappears. Confirm with `modetest -M atmel-hlcdc -p`: plane 43
  lists `AYUV YUYV UYVY YVYU VYUY NV21 NV61 YU16 YU12`; the other three planes
  are RGB-only.
  It only negotiates with **`force-modesetting=false`** *and* a CRTC that is
  already configured - which is exactly the console's handoff (it drops master
  but leaves the mode set). With `force-modesetting=true` kmssink grabs the
  RGB-only primary plane and the pipeline dies with `not-negotiated (-4)`.
* **`queue leaky=downstream max-size-buffers=2`** ahead of the decoder, so the
  newest frame always wins and latency stays bounded.
* **`sync=false`** so the sink renders on arrival instead of waiting on PTS.
* Software fallback (`CAMERA_PLANE_ID = 0`) uses `method=0` (nearest) to BGRx at
  `CAMERA_SW_SIZE` - the best of the software options measured.

Verify the whole handoff without touching the panel:
`python3 camera.py 20` (prints the pipeline, streams, reports gst's log).

### Filling a square panel with a 4:3 feed

kmssink always preserves the display aspect ratio, and this build has no
`videocrop`, no `videobox` and no `capssetter` - so a 640x480 feed on the 720x720
panel is letterboxed with black bars left and right.

A `pixel-aspect-ratio` capsfilter does **not** work: a capsfilter can only
restrict what upstream offers, and jpegdec only ever offers 1/1, so negotiation
fails with `not-negotiated (-4)`.

What works, at zero cost: give kmssink a **render rectangle larger than the
CRTC** and let DRM clip it. `render-rectangle=<-120,0,960,720>` scales the
640x480 frame to 960x720 - its true proportions - and the plane shows the middle
720x720. Full screen, no distortion, sides cropped, hardware scaler still doing
all the work.

**This does not work yet, and the reason is a panel-driver bug.** Reading the
committed atomic state (`/sys/kernel/debug/dri/1/state` - `modetest -p` shows
nothing useful here) while streaming:

| source fed to kmssink | destination | source columns used |
|---|---|---|
| 640x480 | `576x720+72+0` | `384x480+0+0` |
| **720x720 (square)** | `432x720+144+0` | `432x720+0+0` |
| 480x480 | `432x720+144+0` | `288x480+0+0` |

Every source is squeezed to 3/5 of its width and only the left 60% of its
columns are used - even a square one. `render-rectangle`, `display-width`/
`display-height` and `plane-properties` all measured as making **no difference**,
because kmssink recomputes the rectangle and calls `drmModeSetPlane` per frame.

Cause: `panel-waveshare-dsi.c` reports `width_mm = 154, height_mm = 86` for this
720x720 round panel (whose active area is a 72x72 mm square) - upstream hardcodes
the 7-inch DPI panel's size for every model. kmssink correctly corrects for a
display it is told is 1.79:1.

Fix written and verified against the pristine upstream file:
`linux-drivers/display/patches/05_panel-waveshare-dsi_physical_size.py`. It needs
**one kernel rebuild**, so it is pending the build host. Until then the camera
view is letterboxed with bars left and right, and `CAMERA_FIT = "fill"` is inert
(it starts working by itself once the kernel carries the fix). `Camera.render_rect()` computes it from the camera's own reported
resolution, so it follows a resolution change made from the Settings page.
`CAMERA_FIT = "fit"` restores the letterboxed, whole-frame view.

**Trap that cost a round trip:** `render_rect()` needs the feed's aspect, which
came only from `get_settings()` - and that is called when the *Settings* page is
opened. Boot straight into the Camera page and `last_resolution` was still
`None`, so no rectangle was emitted and the view was silently letterboxed again.
Fixed two ways: `start()` now does one cheap `get_settings()` first, and
`CAMERA_SRC_ASPECT` (default `4/3`) is used if that call fails.
The lesson for testing this: an empty gst log only proves the pipeline did not
crash - **print the built pipeline and check the arguments are actually there.**

`CAMERA_HOSTS` puts `192.168.0.38` first, because the board's static address is
in the camera's own /24 and so the IP is the primary path in both LAN and
direct-cable mode; each dead candidate ahead of it costs `PROBE_TIMEOUT`
(measured: `pic64cam.local` fails in 0.23 s, `10.42.0.1` burns the full 1.5 s).

**The producer is now the limit.** `sharpness=75` runs an unsharp filter per
frame on the PIC64 and caps the feed at ~7 fps; lowering it - the console's
Settings page does this live - raises the rate directly.

Only the settings POST sends **just the changed key**: a whole-dict POST would
overwrite the camera's other tuned values (learned in Phase 3).

## 7. Running it

```powershell
.\deploy.ps1                     # sync board\*.py
.\deploy.ps1 -SyncTime -Install  # + set the clock, install the init script
.\deploy.ps1 -Restart            # restart the service
.\deploy.ps1 -Run                # foreground, for tracebacks
.\deploy.ps1 -Board 192.168.0.99 # when DHCP moves it
```

On the board: `/etc/init.d/S99rdk-console {start|stop|restart|status}`,
log at `/tmp/rdk-console.log`.

**Screenshot the live screen** (the panel cannot otherwise be inspected
remotely):

```
kill -USR1 $(cat /var/run/rdk-console.pid)   # writes /tmp/rdk-frame.png
```

`smoke.py` also dumps `/tmp/frame-{menu,security,settings}.png`.

## 8. Board access notes

- **Serial console:** FTDI FT232 on **COM23** of this PC (was COM5 on the old
  one). Drive it with `Workshop
dk-serial.ps1 -Cmd "..."` / `-File cmds.txt`.
  Keep command lines short, and pass commands via `-File` rather than `-Cmd`
  when they contain `$` (PowerShell eats it). The helper sends Ctrl-C first so a
  half-typed line or a `>` continuation prompt cannot wedge it.
- **Network: static, and persistent.** `/etc/init.d/S40rdk-net` pins the MAC to
  `02:9c:75:00:00:01`, brings `eth0` up, assigns **192.168.0.39/24**, fixes
  `/etc/resolv.conf`, generates host keys and starts `sshd`.
  It is static *by design*: the board has to reach the camera both over the
  house LAN and over a **single RJ45 cable straight to the PIC64**, where there
  is no DHCP server at all - DHCP left `eth0` with no IPv4 address and the
  console showed `no camera`. One static address in the camera's /24 behaves
  identically both ways, so nothing has to be switched when you re-cable.
  `USE_DHCP=1` in the script restores a lease if you ever need one.
  *Gotcha:* killing a running `udhcpc` makes it run its `deconfig` hook, which
  flushes **every** address on the interface - including a static one added
  afterwards.
  This was needed because the stock image starts **no network and no sshd**,
  root has **no password**, and the SoC has **no MAC in fuses** - so macb
  invented a random one each boot and DHCP handed out a different address every
  time (the board rebooted mid-session and vanished from the LAN).
- **Credentials:** root password `CHANGEME`; this PC's ed25519 key is in
  `/root/.ssh/authorized_keys`, so `ssh root@192.168.0.39` is keyless.
  `plink -batch` hangs on the host-key prompt - use OpenSSH `ssh`/`scp`.
- **No RTC, and this image has no `ntpd`** (only busybox `rdate`, which speaks
  RFC-868 on TCP/37 - nothing on this LAN serves it), so the clock starts in
  1970. The console therefore takes the time from the **PIC64 camera's HTTP
  `Date` header** (`camera.server_time()`), which is correct, local and needs no
  internet; it does this once, as soon as the camera is reachable. Until then
  the status line shows `--:--` rather than a bogus 1970 clock.
  `deploy.ps1 -SyncTime` can also push this PC's UTC time.
- `systemd` is installed but is **not PID 1** - `systemctl` does not work.
- This busybox has **no `pkill`/`pgrep`** (only `killall`, `start-stop-daemon`,
  `fuser`), and `fuser -k /dev/dri/card1` is the reliable way to free the
  display before taking DRM master.

## 9. Panel alignment - fixed in the mode, not in software

The panel put the framebuffer **50 px to the right** of the glass. Vertical
colour bars hide this completely (the stripes just move), so it only showed up
once a centred UI was on screen.

Measured with `calib.py --sweep`, which steps a drawing offset and prints a huge
number for each step - the round bezel makes a concentric ring the most sensitive
possible target.

The fix is **not** a drawing offset (that would give up 50 px of glass). Instead
`kms.tune_mode()` moves the active window 50 px earlier in the line by taking
pixels out of sync+back porch and giving them to the front porch, keeping
`htotal` (and so the pixel clock and refresh rate) identical:

```
base:  H 720 | fp 330 sync 32 bp 32 | total 1114
tuned: H 720 | fp 380 sync  8 bp  6 | total 1114
```

The kernel accepts this through a plain `DRM_IOCTL_MODE_SETCRTC` with a modified
`drm_mode_modeinfo`, so **no kernel or DT rebuild was needed** - which mattered,
because the cross-build VM is on the other PC. Set by `PANEL_H_SHIFT = 50` in
`config.py`; `X_OFFSET`/`Y_OFFSET` remain as a drawing-offset fallback if a
future kernel refuses the tuned mode.

Check it any time with `python3 calib.py --shift 50 30`.

## 10. Two late fixes worth knowing

* **The camera was only probed once, at startup.** The console starts at S99,
  moments after DHCP, so that probe often ran before the LAN was usable and the
  menu then said `no camera` for ever. A failing probe blocks for up to
  3 x `PROBE_TIMEOUT`, so it cannot be done inline in the UI loop - it now runs
  on a daemon thread (`App.start_prober`) every `CAMERA_RETRY` seconds.
* **`reboot` proved both init scripts.** The board came back on its own at
  192.168.0.39 with the pinned MAC, sshd listening, and the console drawing the
  menu - verified 2026-09-07.

## 11. Open items

- **Touch orientation** is un-inverted and correct as-is, but was only confirmed
  by using the UI; `touchtest.py` will quantify it if it ever looks off.
- **Motion detection** is not implemented on the board (no cheap source without
  numpy/PIL). `screens.security()` already renders the banner; feed it from the
  PC console's state or a snapshot-diff worker.
- **Phase 3 PC console** still has no PHP runtime on this PC, so it has never
  run end to end.
- **Fix the touch interrupt properly** (§5) when the cross-build host is back,
  then flip `TOUCH_BACKEND` to `"evdev"`.
- **UI over live video** is now actually possible: the console draws on the
  primary plane and the camera uses overlay plane 43, so the hardware could
  composite both at once. It needs the console to own DRM master while feeding
  video, i.e. moving the pipeline in-process (appsink or a gst plugin), which is
  a bigger change than this pass.

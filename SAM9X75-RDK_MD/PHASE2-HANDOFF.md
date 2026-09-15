# Phase 2 - Session handoff

## ★★ 2026-09-07 - PHASE 2 IS COMPLETE, AND PHASE 4 IS RUNNING ON THE BOARD

Verified on the bench today, with the build VM **unavailable** (it lives on the
old PC), so everything below was achieved from userspace - no kernel or DT
rebuild:

- **Panel: DONE.** `modetest` colour bars are clean, full and stable. The booted
  image is `sam9x75_curiosity_bestshot.itb` (md5 `02274be2...`, confirmed by
  hashing `/mnt/b/sam9x75_curiosity.itb` on the card). Mode in use is exactly the
  MGS timing: `H 720 | fp 330 sync 32 bp 32 | total 1114`, `V 720 | 8/4/16 | 748`,
  50 MHz, lane rate 660 Mbps, `LCDCFG0 = 0x3`, `PHY_STATUS = 0x1529`.
  `INT_ST1` bit 19 (`dpi_buff_pld_under`) does still latch, but it is **cosmetic
  at this timing** - the image is correct.
- **A residual 50 px horizontal offset was found and fixed** (colour bars hid
  it; a centred UI exposed it). Fixed by retiming the mode from userspace -
  see `phase4-console-app.md` §9.
- **Touch: working**, but *not* through the kernel driver - the GT9271 interrupt
  never fires. The console polls the controller over I²C instead
  (`phase4-console-app.md` §5).
- **Camera: working**, live MJPEG from the PIC64 at 192.168.0.38, now on the
  XLCDC hardware overlay plane for ~2x lower latency (§"Latency" in the Phase 4 doc).
- **Networking + sshd are now persistent** across reboots, with a pinned MAC so
  the DHCP address stops moving: board is **192.168.0.233**.

The Phase 4 console (`rdk-console`) auto-starts at boot via
`/etc/init.d/S99rdk-console`. **Read `phase4-console-app.md` first** - it is the
live document now. Everything below is the historical build record.

---

Phase 2 = Buildroot Linux image + round-panel bring-up. This file is the
self-contained record to resume cleanly.

## ★ 2026-09-06 — PANEL BRING-UP SEQUENCE IS NOW KNOWN (definitive)
Boot, ethernet, touch, and the PIC64 camera feed all **work** from Linux. The one remaining
blocker — the dark round panel — is now **solved on paper**, cross-checked from three sources
(Microchip MGS `curiosity_ws_4in_round`, Waveshare's own `esp_lcd_dsi` driver, and the in-kernel
`panel-waveshare-dsi.c`). **There is NO AES lock and NO giant vendor DCS table** — those were
wrong turns. The real sequence: six plain I²C writes to MCU `0x45`
(`C0=01,C2=01,AC=01,AB=00,AA=01,AD=01`) + **1000 ms delay**, then DSI 2-lane RGB888 video at
720×720 (MGS timing: 50 MHz, H 200/120/32, V 8/4/16), then DCS `0x36`→`0x11`(+120 ms)→`0x29`(+20 ms).
- **Full details:** `SAM9X75-RDK_MD\round-panel-linux-bringup.md` (§1–§3).
- **Machine-readable:** `reference\panel-bringup-spec.json`.
- **Vendor source (local):** `reference\waveshare-esp_lcd_dsi\`.
- **NEXT (user-gated on hardware):** patch `panel-waveshare-dsi.c` (drop AES → 6 MCU writes +
  `msleep(1000)`; fix `ws_panel_4_mode` timing to MGS values), rebuild, copy `.itb` to card E:,
  boot, verify with `modetest` + `dmesg`.

## ✅ 2026-09-05 — BASE CARD FLASHED + DISPLAY-READY IMAGE PREPPED
- **Base `sdcard.img` flashed to the SPARE 64GB USB SD** (Windows `\\.\PhysicalDrive2`,
  the 60GB USB disk; NOT the NVMe/WD system disks). Flasher: `Workshop\flash-sd-auto.ps1`
  (elevated; safety guards USB+non-system+<128GB; `diskpart clean` then raw write; verified
  MBR sig). Layout: p1=16MB FAT32 boot (boot.bin, sam9x75_curiosity.itb, u-boot.bin,
  uboot.env), p2=900MB ext4 rootfs. **Base card = NO round-panel overlay yet** (panel blank
  on first boot — expected).
- **ws4round overlay FIXED + baked into a display-ready image.** DTC error was a missing
  `#include <dt-bindings/clock/at91.h>` in the .dtso (added). `./build.sh overlay` now
  auto-splices `fdt_ws4round` image + `ws4round` config into the FIT `.its` and rebuilds
  `sam9x75_curiosity.itb` (verified: `Configuration 0 (ws4round)`), then prints the deploy
  recipe. Built **`sdcard-ws4round.img`** (base image with the new .itb swapped into the FAT
  p1). On PC: `SAM9X75-RDK\sdcard-ws4round.img` (917MB) + `sam9x75_curiosity_ws4round.itb`
  (5.8MB, for live deploy). On VM: `output/images/sdcard-ws4round.img` + `.itb`.
- **BOOT-SELECT mechanism (this BSP):** U-Boot runs
  `bootcmd = run at91_display_detect; run bootcmd_boot`;
  `bootcmd_boot = fatload mmc 0:1 0x24000000 sam9x75_curiosity.itb; bootm 0x24000000#kernel_dtb${at91_overlays_config}#${eth_phy}#${wilc_S02}`.
  `at91_display_detect` runs lvdstest/mipitest → sets `display_var` → appends `#${display_var}`
  to `at91_overlays_config`, AND runs `at91_prepare_bootargs` (sets kernel bootargs — must NOT
  be skipped). **To select our panel:** set `at91_overlays_config='#ws4round'` and neutralise
  auto display-detect without losing bootargs: `at91_display_detect='run at91_prepare_bootargs'`.
  Set via `fw_setenv` on the booted board or by editing `/boot/uboot.env` (mkenvimage). Do NOT
  leave the stock at91_display_detect or it may also append `#mipi` → double panel overlay.
- **NEXT (needs the board booted):** boot base card → SSH in (find DHCP IP) → replace
  `/boot/sam9x75_curiosity.itb` with the ws4round one → set the two env vars → reboot →
  verify panel: `dmesg | grep -Ei 'dsi|panel|waveshare|hlcdc|goodix'`, `i2cdetect` (0x45+0x14),
  `modetest -M atmel-hlcdc`, `evtest`. Fix unverified pins (touch INT/RESET, i2c bus) per the
  round-panel notes. Once it lights up, that's the verified overlay → keep `sdcard-ws4round.img`.

## ✅ 2026-09-04 — BASE IMAGE BUILT
`~/sam9x75-rdk/buildroot/output/images/sdcard.img` = **~917 MB** (961544192 bytes),
built on the VM after the crash + 15 resumes; every fix persisted in build.sh. Boot
chain all present in output/images/ (at91bootstrap.bin, boot.bin, u-boot.bin,
sam9x75_curiosity.itb, zImage, at91-sam9x75_curiosity.dtb, all BSP .dtbo). The
autonomous watchdog loop stopped here per plan.
**NOT yet flashed or booted.** Immediate next (Phase-2 step 2) is BLOCKED on a small
overlay bug: `build.sh cmd_overlay` fails compiling `dt-overlay/sam9x75_curiosity_ws4round.dtso`
with DTC "Unexpected 'PMC_TYPE_PERIPHERAL' / 'PMC_TYPE_GCK'" (lines 66/68) — the overlay
references AT91 PMC clock macros but the cpp step isn't resolving them. Fix: ensure the
dtso `#include <dt-bindings/clock/at91.h>` and that cmd_overlay's `cpp -I` paths cover
`$ktree/include`; then re-run `./build.sh overlay`, splice fdt into kernel.itb, repackage
boot partition. (Does NOT affect the already-built sdcard.img.) Then step 3: flash SPARE
SD + bench bring-up.

## CRASH RECOVERY 2026-09-03 (PC crashed mid-build) — done, build re-running
The PC (hence the VM) crashed while Buildroot was mid-build (~13:09). On reboot the
build was NOT running. Resuming `./build.sh build` failed in stages because the crash
had **truncated files to 0 bytes** while they were being written — Buildroot's stamps
still marked those packages "done", so a plain resume never re-made them:
- `libxml2-2.13.6` build dir left with a targetless Makefile → `make: No targets` →
  fixed with `make libxml2-dirclean`.
- **libvpx** + **libvorbis** staging installs truncated: `libvpx.so.9.1.0`,
  `libvorbis*.so*` and their `vpx.pc`/`vorbis*.pc` were all **0 bytes**, so ffmpeg's
  configure died with `vorbis not found using pkg-config`. Found via a whole-staging
  zero-byte sweep (`find output/host/*/sysroot -size 0`; only those 2 pkgs + the
  legit-empty python `__init__.py` files). Fixed: `make libvpx-dirclean
  libvorbis-dirclean ffmpeg-dirclean`, deleted the stale 0-byte staged files, relaunched.
- **Lesson if it crashes again:** don't trust stamps — sweep staging for 0-byte
  `*.pc`/`*.so*`/`*.a` (`find output/host/arm-buildroot-linux-gnueabi/sysroot -size 0`),
  `<pkg>-dirclean` each hit + its consumers (here ffmpeg), then re-run `./build.sh build`.
  Build log banners `===== RESUME3 post-dirclean =====` mark the restarts.
- **Sequel (RESUME5):** the first sweep only checked `*.so*`/`*.pc`/`*.a`, NOT
  headers. gst1-plugins-good later failed meson (`libvpx was built without any
  encoder/decoder features` / `unknown type name vpx_codec_iface_t`) because the 11
  **vpx headers** in `staging/usr/include/vpx/*.h` were 0-byte — and a dirclean+rebuild
  of libvpx re-staged the `.so` but did NOT overwrite those headers. Fixed by copying
  the intact build-dir headers over them (`cp output/build/libvpx-1.15.0/vpx/*.h
  $SYS/usr/include/vpx/`), then `gst1-plugins-good-dirclean` + resume. **Sweep ALL
  file types next time:** `find output/host/*/sysroot output/target -type f -size 0 |
  grep -vE '__init__.py|doxygen-build.stamp'` — after the fix that count is 0.

## More gcc-15 / version-skew unblocks 2026-09-04 (all persisted in build.sh)
Once the crash damage was cleared the build ran deep (152/155 target pkgs) and hit a
run of environment-skew failures, each fixed and made persistent so a clean rebuild
won't repeat them:
- **host-systemd 256.7** — `errno-to-name.h [-Werror=override-init]` (intentional
  EWOULDBLOCK==EAGAIN dups) fatal under host gcc 15.2. Bare `-Wno-error` does NOT
  cancel a specific `-Werror=override-init` (tested); the host wrapper now appends
  **`-w`** after `"$@"` (suppresses all warnings on host build-tools only). NOTE the
  trap that cost a cycle: `build.sh cmd_build` REGENERATES the hostwrap/cc,cxx scripts
  each run — editing them by hand is futile; fix the generator in build.sh and re-scp.
- **openssh 9.9p2** — target compile `sorry, unimplemented: ... -fzero-call-used-regs
  on this target` (arm926ej-s/ARMv5, gcc 13.3.0). Buildroot only drops openssh
  hardening when `BR2_TOOLCHAIN_HAS_GCC_BUG_110934=y`, unset for 13.3.0. Fix: made the
  `--without-hardening` line in `package/openssh/openssh.mk` unconditional (build.sh
  cmd_config re-applies it; local.mk is NOT honored by buildroot 2025.02).
- **strace 6.13** — `struct mnt_id_req has no member named spare` (listmount.c vs this
  toolchain's kernel headers). BSP debug tool, not needed for bring-up → disabled.
- **v4l2loopback 0.13.2** — out-of-tree module too old for the kernel
  (del_timer_sync/setup_timer removed, v4l2_fh_add/del sig change). BSP extra, nothing
  selects it, and we DISPLAY the MJPEG feed (no loopback device needed) → disabled.
- **Trimmed from the BSP graphics defconfig so far:** host-gdb, strace, v4l2loopback.
  Core image (kernel + Waveshare panel + Goodix touch + GStreamer MJPEG + openssh +
  gdbserver) intact. **Kernel already built** (zImage + at91-sam9x75_curiosity.dtb +
  u-boot.bin in output/images/); resumed as `RESUME11 v4l2loopback-disabled` finishing
  the last module/rootfs packages before `sdcard.img`.

## plplot download fixed 2026-09-04 (SourceForge git broken; cached a tarball)
plplot (a dependency of **EGT**, the Microchip graphics toolkit) would not download:
buildroot fetches it by git from SourceForge (`git://` then, after our edit,
`https://git.code.sf.net/p/plplot/plplot`), and the full clone (fetches ALL refs)
dies mid-transfer with `fetch-pack: unexpected disconnect / early EOF`; the
`sources.buildroot.net` tarball mirror 404s. `git ls-remote` works and a **shallow
clone of the tag succeeds** — only the big all-refs clone fails. Robust git config
(HTTP/1.1, http.postBuffer 1G, low-speed tolerance) did NOT help.
**Fix applied:** shallow-cloned the tag on the VM and handed buildroot the tarball it
expects (plplot has **no .hash file**, so no checksum to match):
```
git clone --depth 1 --branch plplot-5.15.0 https://git.code.sf.net/p/plplot/plplot /tmp/plplot-shallow
git -C /tmp/plplot-shallow archive --prefix=plplot-plplot-5.15.0-git4/ HEAD | gzip -n \
   > ~/sam9x75-rdk/buildroot/dl/plplot/plplot-plplot-5.15.0-git4.tar.gz
```
`make plplot-source` then accepts it (warns "no hash file"). The tarball lives in the
persistent `dl/` cache, so it survives rebuilds unless `dl/plplot` is wiped — if it is,
re-run the two commands. (Also left plplot.mk switched to https + SITE_METHOD=git.)
Resumed as `RESUME13 plplot-tarball-cached`; plplot+EGT then built OK.

## libcamera-mchp IPA-sign path fixed 2026-09-04
After plplot+EGT built, **libcamera-mchp** failed at target-install: "Could not open
file ... ipa-priv-key.pem". Its `.mk` IPA-signing hook hardcodes the meson build dir
as `buildroot-build`, but buildroot 2025.02 uses `build` — the key really sits at
`build/src/ipa-priv-key.pem`. Fixed by repointing the hook
(`sed 's#/buildroot-build/#/build/#g'` on
`buildroot-external-microchip/package/libcamera-mchp/libcamera-mchp.mk`; persisted in
build.sh cmd_config). Resumed as `RESUME14 libcamera-signkey-path-fix`.

Then **mchpcam-apps** hit the SAME bug at install (`install: No such file or
directory` for `buildroot-build/src/apps/mchpcam/mchpcam-still`). It's BSP-wide, so
generalized the fix: sweep ALL `buildroot-external-microchip/package/*/*.mk` replacing
`buildroot-build`→`build` (also hit plplot + pic64gx_amp_examples*, the latter not
selected). Persisted as a loop in build.sh cmd_config. Resumed `RESUME15`.

**Monitor note:** the ssh-loop completion monitors kept HANGING (even timeout-wrapped
they didn't fire — build sat finished ~30 min unnoticed). **Dropped them.** Watch is
now the **ScheduleWakeup heartbeat** (harness-managed, reliable) running an autonomous
watchdog: every ~20-25 min it checks build.log + images/sdcard.img, auto-fixes+resumes
a failed package in this session's style, persists the fix in build.sh, and reschedules;
on sdcard.img it push-notifies Attila and stops. Don't trust "no ping" = "still
building" — verify with a direct `tail build.log` + `ls images/sdcard.img`.

## host-gdb disabled 2026-09-03 (genuine toolchain bug, not the crash)
After the corruption fixes, the build then failed at **host-gdb-15.1** `CXXLD gdb`
with `g++: error: unrecognized command-line option '-rpath'` — gdb's own Makefile
emits a bare `-rpath` (needs `-Wl,-rpath`) to the g++ driver when linking against the
host shared libs (libxxhash/libexpat). Reproducible, unrelated to the crash (host
gcc 15.2). `host-gdb` is the PC-side cross-debugger, is **not** in the target image,
and nothing selects it — so it's disabled to unblock. **Target `gdbserver` +
on-target `gdb` (`BR2_PACKAGE_GDB_DEBUGGER`) stay enabled.** Made persistent in
`build.sh cmd_config` (a `# ... is not set` line can't ride the fragment — the merge
greps out comments). Relaunched as `RESUME4 host-gdb-disabled`. ⚠️ watch the later
**target** gdb build for a similar rpath wall; if it hits, disable `GDB_DEBUGGER` and
keep `GDB_SERVER`.

## Overall project status

| Phase | State |
|---|---|
| 1 — PIC64 fan-out relay + LAN token | ✅ DONE & deployed on board .38 (`pic64-camstream.service`) |
| 3 — PC PHP console (`console-php\`) | ✅ BUILT; PC has no PHP runtime yet → never run E2E |
| 2 — Buildroot Linux image + round panel | 🔧 base image BUILDING on the VM; artifacts corrected (see below) |
| 4 — EGT app (`egt-app\`) | ⬜ not started |

## Build host — the Ubuntu VM (NOT WSL anymore)

The build runs on the Ubuntu 26.04 VM (same box as the Gaudi2 dev VM):

```
ssh builder@BUILD-VM        # pass in memory: sam9x75-build-vm-access / gaudi2-vm-access
```

- Non-interactive from Windows we drive it with PuTTY:
  `plink.exe -ssh -batch -pw <pw> builder@BUILD-VM "<cmd>"` and copy files
  with `pscp.exe -batch -pw <pw> ...`. (`sshpass` isn't on Windows; plink is.)
- Deps installed 2026-09-03 (`build.sh deps` set): build-essential git bc bison
  flex libssl-dev device-tree-compiler u-boot-tools rsync cpio unzip wget file
  python3 libncurses-dev gawk. `dtc`/`bison`/`flex`/`mkimage` confirmed present.
- Artifacts copied to the VM at `~/SAM9X75-RDK/linux-image/` (pscp -r from
  `D:\ClaudeFiles\SAM9X75-RDK\linux-image\`); fix CRLF + exec bit on `build.sh`
  after any re-copy (`sed -i 's/\r$//'; chmod +x`).
- Buildroot working tree: `~/sam9x75-rdk/` (buildroot 2025.02 + external
  `buildroot-external-microchip` master `6c78b1b`). Build log: `~/sam9x75-rdk/build.log`.

> The old PC's WSL notes no longer apply. If you ever fall back to WSL, `build.sh`
> is path-agnostic (derives its own location); the only WSL-specific item was the
> corp-VPN network fix — see memory `wsl-corp-network-fix` if needed.

## KEY DISCOVERY 2026-09-03 — no custom driver needed

The pinned BSP kernel **`linux4microchip-2026.04`** already ships the mainline/RPi
**Waveshare DSI panel driver** `drivers/gpu/drm/panel/panel-waveshare-dsi.c`
(`CONFIG_DRM_PANEL_WAVESHARE_TOUCHSCREEN`). Its model table has
`ws_panel_4_mode` = **720×720 @ 50 MHz, 2 DSI lanes** (htotal 1072, vtotal 748 —
matches our capture), plus the same **I2C 0x45** MCU power/backlight sequence
(`0xab=0xff-brightness`, `0xaa=0x01`). It is bound to DT compatible
**`waveshare,4inch-panel`** (NOT `waveshare,4.0inch-panel`, which is a different
480×640 panel).

Consequences (all applied to the artifacts):
- The custom `panel-waveshare-4inch-round.c` + its Kconfig/Makefile fragments are
  **retired** → `linux-image/panel-driver/RETIRED/`. No kernel patching, and the
  orphaned `post-extract.sh` injection (which Buildroot never actually ran) is gone.
- `linux-image/buildroot/linux.config.fragment` now enables the **stock** driver
  (`CONFIG_DRM_PANEL_WAVESHARE_TOUCHSCREEN=y`) + Goodix + backlight.
- The driver is an **I2C driver**: the panel node lives on the DSI-connector I2C
  bus at **0x45** and finds the DSI host via an of_graph endpoint — it is NOT a
  DSI child node. `sam9x75_curiosity_ws4round.dtso` was rewritten accordingly:
  `&dsi` port@1 `dsi_out` → `ws_panel_in` (endpoint under `panel@45` on `&i2c6`,
  `compatible="waveshare,4inch-panel"`). Goodix GT9271 stays at `@0x14`.

## Config-clobber fix 2026-09-03

The original `build.sh config` overrode three BSP list-valued vars and would have
silently broken the image. Fixed to be additive; the running build already uses
the corrected `.config`:
- `BR2_GLOBAL_PATCH_DIR` — keep the BSP value `$(BR2_EXTERNAL_MCHP_PATH)/patches`
  (do NOT repoint it; that loses the BSP's per-package patches).
- `BR2_ROOTFS_POST_BUILD_SCRIPT` — keep the BSP's at91 + sam9x post_build scripts
  (do NOT blank it).
- `BR2_LINUX_KERNEL_CONFIG_FRAGMENT_FILES` — **append** our fragment to the BSP's
  `at91/libcamera.fragment` (do NOT replace; that drops libcamera).

## RESUME checklist

**1. Is the base build done?**
```
plink.exe -ssh -batch -pw <pw> builder@BUILD-VM \
  "tail -5 ~/sam9x75-rdk/build.log; ls -l ~/sam9x75-rdk/buildroot/output/images/sdcard.img"
```
`build.log` ends with `EXIT_0` on success and `sdcard.img` exists.
If it failed, read the tail, fix, and re-run `./build.sh build`.

**2. Compile the overlay + assemble kernel.itb**
```
cd ~/SAM9X75-RDK/linux-image/buildroot && ./build.sh overlay
```
Then add the `fdt_ws4round` image + `ws4round` config from
`dt-overlay/sam9x75_curiosity.its.additions` into the BSP `.its` (locate it:
`find ~/sam9x75-rdk/buildroot/output/build -name '*.its' -path '*sam9x75*'`),
rebuild `kernel.itb` with `mkimage`, and repackage the boot partition so the new
`kernel.itb` lands in `sdcard.img`.

**3. Flash the SPARE SD (never the demo card) + bring-up**
- `./build.sh flash /dev/sdX` (double-confirm the device).
- Select the overlay offline in the FAT boot partition
  (`boot-partition/README-boot-select.md`); boot; find the DHCP IP; SSH in.
- Verify: `dmesg | grep -Ei 'dsi|panel|waveshare|hlcdc|goodix'`,
  `modetest -M atmel-hlcdc -s <conn>:720x720 -v`, `evtest`,
  `i2cdetect -y <bus>` (expect 0x14 + 0x45), and bench the PIC64 feed with the
  `gst-launch-1.0 souphttpsrc … ! multipartdemux ! jpegdec ! kmssink` pipeline
  (README.md has it).

## Verify-on-bench unknowns (small, mechanical)
- Touch INT/RESET GPIOs + the exact I2C bus index (`&i2c6` inherited from the
  hx8394 kit routing) — confirm from the RDK schematic if touch won't probe.
- The DSI-host↔panel of_graph binding on the DW-MIPI-DSI host (Microchip
  `dw-mipi-dsi-mchp`) — the RPi driver attaches via `devm_mipi_dsi_attach`; expect
  it to bind, confirm on `dmesg`.
- Exact `kernel.itb` assembly path + boot-time overlay-select mechanism for this
  BSP release (uEnv.txt vs boot.scr vs saved env) — match what `sdcard.img` uses.

## Pointers
- Panel/DSI capture + driver notes: `SAM9X75-RDK_MD\round-panel-linux-bringup.md`
- Reference overlay we modeled on:
  `D:\ClaudeFiles\PIC64_WebCam\pathB\vendor\dt-overlay-mchp\sam9x75_curiosity\sam9x75_curiosity_mipi_display.dtso`
- Memory: `sam9x75-rdk-project`, `sam9x75-build-vm-access`, `gaudi2-vm-access`.

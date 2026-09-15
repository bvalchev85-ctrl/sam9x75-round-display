#!/usr/bin/env bash
# =============================================================================
# SAM9X75 RDK — Phase 2 Buildroot image + round-panel build (Ubuntu / WSL2)
# =============================================================================
# Produces output/images/sdcard.img for the SPARE SD card, with:
#   * the STOCK in-tree Waveshare DSI panel driver enabled
#     (CONFIG_DRM_PANEL_WAVESHARE_TOUCHSCREEN; compatible waveshare,4inch-panel
#     == our 720x720 round panel) — no custom driver is injected,
#   * the ws4round DT overlay compiled to .dtbo and added to kernel.itb,
#   * Goodix touch + GStreamer decode/bench tools enabled.
#
# Non-destructive: writes only under $WORK. Never touches the board or SD until
# you run the explicit `flash` step at the very end.
#
# Usage:
#   ./build.sh deps        # one-time: apt build prerequisites
#   ./build.sh fetch       # clone buildroot + buildroot-external-microchip
#   ./build.sh config      # clean defconfig + merge our fragments (additive)
#   ./build.sh build       # full make (long: first build ~1-3 h)
#   ./build.sh overlay     # (re)compile ws4round.dtbo + rebuild kernel.itb
#   ./build.sh all         # fetch -> config -> build -> overlay
#   ./build.sh flash /dev/sdX   # DANGEROUS: dd sdcard.img to the spare card
#
# Verify the BR_EXT branch / buildroot tag below against Linux4SAM release notes
# for your SAM9X75 BSP before the first run.
# -----------------------------------------------------------------------------
set -euo pipefail

# --- config (edit if the BSP release differs) --------------------------------
WORK="${WORK:-$HOME/sam9x75-rdk}"
BR_URL="https://gitlab.com/buildroot.org/buildroot.git"
BR_TAG="${BR_TAG:-2025.02}"                     # match the BSP's tested tag
BREXT_URL="https://github.com/linux4sam/buildroot-external-microchip.git"
BREXT_BRANCH="${BREXT_BRANCH:-master}"          # e.g. linux4sam-2025.x
DEFCONFIG="sam9x75_curiosity_graphics_defconfig"

# This script lives in linux-image/buildroot/ ; sources are relative to it.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LI="$(cd "$HERE/.." && pwd)"                     # .../linux-image
DTSO="$LI/../linux-drivers/dt-overlay/sam9x75_curiosity_ws4round.dtso"
LINUX_FRAG="$LI/buildroot/linux.config.fragment"
BR_FRAG="$LI/buildroot/buildroot.config.fragment"

BR="$WORK/buildroot"
BREXT="$WORK/buildroot-external-microchip"

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

cmd_deps() {
  log "Installing build prerequisites (sudo apt)"
  sudo apt-get update
  sudo apt-get install -y build-essential git bc bison flex libssl-dev \
    device-tree-compiler u-boot-tools rsync cpio unzip wget file python3 \
    libncurses-dev gawk
}

cmd_fetch() {
  mkdir -p "$WORK"
  [ -d "$BR/.git" ]    || git clone --depth 1 -b "$BR_TAG"       "$BR_URL"    "$BR"
  [ -d "$BREXT/.git" ] || git clone --depth 1 -b "$BREXT_BRANCH" "$BREXT_URL" "$BREXT"
  log "Buildroot: $(git -C "$BR" describe --tags 2>/dev/null || echo "$BR_TAG")"
  log "BR2_EXTERNAL: $(git -C "$BREXT" rev-parse --short HEAD)"
  [ -f "$BREXT/configs/$DEFCONFIG" ] || \
    die "$DEFCONFIG not found in $BREXT/configs — check BREXT_BRANCH."
}

cmd_config() {
  [ -d "$BR" ] || die "run: $0 fetch  first"

  # The round panel uses the STOCK in-tree driver
  # (drivers/gpu/drm/panel/panel-waveshare-dsi.c,
  # CONFIG_DRM_PANEL_WAVESHARE_TOUCHSCREEN) already present in the pinned BSP
  # kernel linux4microchip-2026.04 — its model table has the 720x720 round mode
  # under compatible "waveshare,4inch-panel". So there is NO custom driver to
  # inject; we only (a) enable that symbol + Goodix touch via our kernel
  # fragment, and (b) add bring-up packages via the buildroot fragment. Both are
  # merged WITHOUT clobbering the BSP's own list-valued config vars.

  log "make $DEFCONFIG (clean)"
  rm -f "$BR/.config"
  make -C "$BR" BR2_EXTERNAL="$BREXT" "$DEFCONFIG"

  # Capture the BSP's own kernel config fragment(s) so we can APPEND, not replace.
  local orig_frag
  orig_frag="$(sed -n 's/^BR2_LINUX_KERNEL_CONFIG_FRAGMENT_FILES="\(.*\)"$/\1/p' "$BR/.config")"

  log "Merging Buildroot package fragment (additive)"
  grep -vE '^\s*(#|$)' "$BR_FRAG" >> "$BR/.config"

  log "Appending our kernel config fragment alongside the BSP's"
  # Do NOT touch BR2_GLOBAL_PATCH_DIR or BR2_ROOTFS_POST_BUILD_SCRIPT — the BSP
  # sets those to lists we must preserve.
  sed -i '/^BR2_LINUX_KERNEL_CONFIG_FRAGMENT_FILES=/d' "$BR/.config"
  echo "BR2_LINUX_KERNEL_CONFIG_FRAGMENT_FILES=\"$orig_frag $LINUX_FRAG\"" >> "$BR/.config"

  # Disable host-gdb (the PC-side cross-debugger). The BSP graphics defconfig
  # enables BR2_PACKAGE_HOST_GDB, but host-gdb-15.1's final `CXXLD gdb` link
  # fails on this host toolchain (host gcc 15.2): gdb's Makefile emits a bare
  # `-rpath` to the g++ driver -> "g++: error: unrecognized command-line option
  # '-rpath'". host-gdb is not part of the target image (nothing selects it, and
  # target gdbserver + on-target gdb stay enabled), so we drop it to unblock.
  # A `# ... is not set` line can't ride in via buildroot.config.fragment (the
  # fragment merge greps out '#'-comment lines), so it lives here.
  sed -i 's/^BR2_PACKAGE_HOST_GDB=y/# BR2_PACKAGE_HOST_GDB is not set/' "$BR/.config"
  sed -i '/^BR2_PACKAGE_HOST_GDB_TUI=y/d;/^BR2_PACKAGE_HOST_GDB_PYTHON3=y/d;/^BR2_PACKAGE_HOST_GDB_SIM=y/d' "$BR/.config"

  # Disable strace (BSP-provided debug tool, not needed for bring-up). strace 6.13
  # fails to compile against this toolchain's kernel headers: listmount.c uses
  # struct mnt_id_req.spare, a field absent from the headers -> "struct mnt_id_req
  # has no member named spare". Nothing selects strace; dropping it is harmless.
  # (Re-add + bump/patch strace later if you want it on the target.)
  sed -i 's/^BR2_PACKAGE_STRACE=y/# BR2_PACKAGE_STRACE is not set/' "$BR/.config"

  # Disable v4l2loopback (BSP-provided out-of-tree kernel module, not needed: we
  # DISPLAY the PIC64 MJPEG feed, we don't create a virtual /dev/video loopback).
  # v4l2loopback 0.13.2 is too old for the pinned kernel (linux4microchip-2026.04,
  # Linux 6.15+): del_timer_sync/setup_timer removed, v4l2_fh_add/del signatures
  # changed -> won't compile. Nothing selects it. (Re-add via a newer v4l2loopback
  # if a loopback device is ever wanted.)
  sed -i 's/^BR2_PACKAGE_V4L2LOOPBACK=y/# BR2_PACKAGE_V4L2LOOPBACK is not set/' "$BR/.config"
  sed -i '/^BR2_PACKAGE_V4L2LOOPBACK_UTILS=y/d' "$BR/.config"

  # Disable ble-bluez-hci-apps (BSP Bluetooth-LE demo: BLE UART + DFU apps). Nothing
  # in this project uses Bluetooth. It fails to build anyway — it #includes BlueZ
  # *internal* headers (gdbus/gdbus.h, shared/shell.h) that bluez5_utils does not
  # export to staging -> "fatal error: gdbus/gdbus.h: No such file or directory".
  # Nothing selects it. (Re-enable + provide the bluez internal headers if BLE is
  # ever needed.)
  sed -i 's/^BR2_PACKAGE_BLE_BLUEZ_HCI_APPS=y/# BR2_PACKAGE_BLE_BLUEZ_HCI_APPS is not set/' "$BR/.config"

  # Force openssh --without-hardening. openssh's configure auto-adds
  # -fzero-call-used-regs=used, which the arm926ej-s (ARMv5) target gcc 13.3.0
  # rejects with "sorry, unimplemented: argument used is not supported for
  # -fzero-call-used-regs on this target". Buildroot only disables openssh
  # hardening when BR2_TOOLCHAIN_HAS_GCC_BUG_110934=y, and that symbol isn't set
  # for our 13.3.0 toolchain (its version gate misses 13.3), so we make the
  # existing `--without-hardening` line unconditional in the vendored openssh.mk.
  # (This edits the buildroot working tree, which `fetch` re-clones — hence here.)
  local osmk="$BR/package/openssh/openssh.mk"
  if [ -f "$osmk" ] && grep -q '^ifeq ($(BR2_TOOLCHAIN_HAS_GCC_BUG_110934),y)' "$osmk"; then
    sed -i '/^ifeq (\$(BR2_TOOLCHAIN_HAS_GCC_BUG_110934),y)/{N;N;s/^ifeq (\$(BR2_TOOLCHAIN_HAS_GCC_BUG_110934),y)\n\(OPENSSH_CONF_OPTS += --without-hardening\)\nendif/# SAM9X75 RDK: forced (gcc -fzero-call-used-regs unimplemented on arm926)\n\1/}' "$osmk"
    log "openssh.mk: --without-hardening forced unconditional"
  fi

  # Fix the BSP's stale meson/cmake build-dir name. Several buildroot-external-
  # microchip packages (libcamera-mchp IPA-sign hook, mchpcam-apps install,
  # plplot, pic64gx_amp_examples*) hardcode the build dir as 'buildroot-build',
  # but buildroot 2025.02 builds in 'build'. So their install/sign/native-dir
  # steps reference files that don't exist -> "install: No such file or
  # directory" / "Could not open ... ipa-priv-key.pem". Repoint every BSP .mk to
  # the real dir. (BSP external tree, re-cloned by fetch — hence here.)
  local n=0
  for mk in "$BREXT"/package/*/*.mk; do
    if [ -f "$mk" ] && grep -q 'buildroot-build' "$mk"; then
      sed -i 's#buildroot-build#build#g' "$mk"; n=$((n+1))
    fi
  done
  [ "$n" -gt 0 ] && log "BSP .mk build-dir path fixed (buildroot-build -> build) in $n file(s)"

  make -C "$BR" olddefconfig
  log "config done. Review with: make -C $BR menuconfig / linux-menuconfig"
  echo ">> BSP kernel fragment(s) preserved: $orig_frag"
  echo ">> Our kernel fragment appended:      $LINUX_FRAG"
}

cmd_build() {
  [ -f "$BR/.config" ] || die "run: $0 config  first"
  # Host-gcc >= 15 defaults to C23, which breaks the old gnulib bundled in some
  # host packages (e.g. host-m4 1.4.19: gl_oset.h _GL_ATTRIBUTE_NODISCARD). Force
  # host compiles to the pre-C23 standard via tiny WRAPPER scripts, so that:
  #   * the C compiler gets the C std and the C++ compiler the C++ std (a C
  #     '-std=gnu17' handed to g++ only warns, but that warning poisons libtool's
  #     stderr-sensitive dlopen checks -> host-gcc-initial plugin.cc dlclose error);
  #   * HOSTCC/HOSTCXX stay single valid PATHS (CMake rejects a compiler string
  #     that carries an embedded flag, e.g. "g++ -std=gnu++17").
  # Override with HOSTCC_STD="" to disable if a future host no longer needs it.
  #
  # Host-gcc >= 15 also turns several once-benign warnings into hard errors under
  # the per-warning -Werror=X that upstream host packages self-impose (e.g.
  # host-systemd 256.7: errno-to-name.h "initialized field overwritten
  # [-Werror=override-init]", from the intentional EWOULDBLOCK==EAGAIN duplicates).
  # A bare -Wno-error does NOT cancel a specific -Werror=override-init (tested), so
  # we append -w AFTER the package's own args ("$@"): -w inhibits ALL warnings, so
  # nothing remains to promote to an error regardless of which -Werror=X the
  # package injects. It affects warnings only (never real errors) on host-only
  # build tools, is valid for C and C++, and reduces the stderr noise that could
  # poison libtool's dlopen checks noted above. Override with HOSTCC_WSUPPRESS="".
  local cstd="${HOSTCC_STD:--std=gnu17}"
  local hwno="${HOSTCC_WSUPPRESS:--w}"
  local hcc="gcc" hcxx="g++"
  if [ -n "$cstd" ]; then
    local wrap="$WORK/hostwrap"
    mkdir -p "$wrap"
    printf '#!/bin/sh\nexec gcc %s "$@" %s\n' "$cstd"            "$hwno" > "$wrap/cc"
    printf '#!/bin/sh\nexec g++ %s "$@" %s\n' "${cstd/gnu/gnu++}" "$hwno" > "$wrap/cxx"
    chmod +x "$wrap/cc" "$wrap/cxx"
    hcc="$wrap/cc"; hcxx="$wrap/cxx"
  fi
  log "Building (this is the long one). HOSTCC='$hcc'  Logs: $BR/build.log"
  make -C "$BR" BR2_EXTERNAL="$BREXT" HOSTCC="$hcc" HOSTCXX="$hcxx" -j"$(nproc)"
  log "Base image: $BR/output/images/sdcard.img"
  cmd_overlay
}

# Compile our overlay with the kernel tree's dtc and splice it into kernel.itb.
cmd_overlay() {
  local out="$BR/output"
  local ktree; ktree="$(ls -d "$out"/build/linux-* 2>/dev/null | head -1)"
  [ -n "$ktree" ] || die "kernel build dir not found — run '$0 build' first"
  local dtc="$ktree/scripts/dtc/dtc"
  local img="$out/images"
  [ -x "$dtc" ] || die "kernel dtc not built at $dtc"

  log "Compiling ws4round overlay -> .dtbo"
  # Preprocess includes (dt-bindings) then compile as an overlay (-@ symbols).
  cpp -nostdinc -undef -x assembler-with-cpp \
      -I "$ktree/include" \
      -I "$ktree/scripts/dtc/include-prefixes" \
      "$DTSO" -o "$img/ws4round.pp.dts"
  "$dtc" -@ -I dts -O dtb -o "$img/sam9x75_curiosity_ws4round.dtbo" \
      "$img/ws4round.pp.dts"
  log "Overlay built: $img/sam9x75_curiosity_ws4round.dtbo"

  # --- Splice fdt_ws4round into the BSP FIT (.its) and rebuild kernel.itb ---
  # The BSP boots: bootm <addr>#kernel_dtb${at91_overlays_config}#... , applying
  # extra FIT *configs* by name. We add an image node + a `ws4round` config so the
  # panel overlay can be selected via `at91_overlays_config=#ws4round`.
  local its="$img/sam9x75_curiosity.its"
  [ -f "$its" ] || die "FIT source not found: $its (run '$0 build' first)"
  [ -f "$its.bak" ] || cp "$its" "$its.bak"
  printf 'fdt_ws4round {\ndescription = "Waveshare 4inch round 720x720 DSI panel";\ndata = /incbin/("./sam9x75_curiosity/sam9x75_curiosity_ws4round.dtbo");\ntype = "flat_dt";\narch = "arm";\ncompression = "none";\nload = <0x23190000>;\nhash {\nalgo = "sha256";\n};\n};\n' > "$img/.ws_img.txt"
  printf 'ws4round {\ndescription = "FDT overlay: Waveshare 4inch round DSI panel";\nfdt = "fdt_ws4round";\n};\n' > "$img/.ws_cfg.txt"
  # Insert image after `images {`, config AFTER the `default = "kernel_dtb";`
  # property (a subnode must not precede a property -> dtc "Properties must
  # precede subnodes").
  awk -v imgf="$img/.ws_img.txt" -v cfgf="$img/.ws_cfg.txt" '
    function dump(f,  l){ while((getline l < f) > 0) print l; close(f) }
    { print }
    /^[ \t]*images[ \t]*\{[ \t]*$/ && !di { dump(imgf); di=1 }
    /default = "kernel_dtb";/        && !dc { dump(cfgf); dc=1 }
  ' "$its.bak" > "$its"
  # mkimage needs every /incbin/ file present at its relative path
  ( cd "$img" && mkdir -p sam9x75_curiosity && for f in *.dtbo; do ln -sf "../$f" "sam9x75_curiosity/$f"; done
    mkimage -f sam9x75_curiosity.its sam9x75_curiosity.itb >/dev/null )
  if mkimage -l "$img/sam9x75_curiosity.itb" 2>/dev/null | grep -q '(ws4round)'; then
    log "kernel.itb rebuilt WITH ws4round config: $img/sam9x75_curiosity.itb"
  else
    die "ws4round config missing from rebuilt kernel.itb — check $its"
  fi

  cat <<NEXT

kernel.itb now contains the ws4round config. To get it onto a card / running board:
  A) Display-ready IMAGE (no re-genimage): copy sdcard.img, loop-mount its FAT
     boot partition (p1) and drop in the new sam9x75_curiosity.itb:
        cp sdcard.img sdcard-ws4round.img
        LOOP=\$(sudo losetup -Pf --show sdcard-ws4round.img)
        sudo mount \${LOOP}p1 /mnt && sudo cp $img/sam9x75_curiosity.itb /mnt/ \\
          && sync && sudo umount /mnt && sudo losetup -d \$LOOP
  B) Live on the booted board (SSH): replace /boot/sam9x75_curiosity.itb with the
     new one, then select the overlay in the U-Boot env (fw_setenv, or edit
     /boot/uboot.env):
        at91_display_detect='run at91_prepare_bootargs'   # keep bootargs, skip auto display-detect
        at91_overlays_config='#ws4round'                  # apply the round-panel overlay
     then reboot. (Leaving default at91_display_detect risks it also appending
     #mipi and double-applying a panel overlay.)
NEXT
}

cmd_flash() {
  local dev="${1:-}"
  [ -n "$dev" ] || die "usage: $0 flash /dev/sdX   (the SPARE card, NOT the demo)"
  local img="$BR/output/images/sdcard.img"
  [ -f "$img" ] || die "no sdcard.img — build first"
  log "About to write $img -> $dev"
  lsblk -o NAME,SIZE,MODEL,TRAN "$dev" || true
  read -r -p "Type the device again to confirm ($dev): " c
  [ "$c" = "$dev" ] || die "mismatch — aborted"
  sudo dd if="$img" of="$dev" bs=4M conv=fsync status=progress
  sync
  log "Done. Eject, boot the board, find its DHCP IP, then SSH in."
}

case "${1:-}" in
  deps) cmd_deps ;;
  fetch) cmd_fetch ;;
  config) cmd_config ;;
  build) cmd_build ;;
  overlay) cmd_overlay ;;
  all) cmd_fetch; cmd_config; cmd_build ;;
  flash) shift; cmd_flash "${1:-}" ;;
  *) grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//' | head -40 ;;
esac

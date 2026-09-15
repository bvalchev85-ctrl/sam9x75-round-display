# Selecting the round-panel overlay at boot — headless (card reader only)

We have **no serial console**, so the DT overlay must be selected by editing the
**FAT boot partition** of the spare SD card offline, then booting. This is the
one genuinely board-specific step; confirm the exact mechanism against the FAT
partition of the `sdcard.img` you actually built (mechanisms below, most likely
first for the Linux4SAM SAM9X7 BSP).

## Boot chain recap

```
BOOT.BIN (at91bootstrap) → u-boot.bin → loads kernel.itb (FIT) from FAT part 1
                                        → bootm <addr>#kernel_dtb#<overlay>
```

The FIT (`kernel.itb`) carries the base DTB (config `kernel_dtb`) and every
overlay as its own config (`mipi`, `lan8840`, … and now **`ws4round`** once you
add it — see `dt-overlay/sam9x75_curiosity.its.additions`). Which overlay is
applied is decided by the extra `#<config>` names U-Boot passes to `bootm`.

## Prereq: the overlay must be *in* kernel.itb

`build.sh overlay` compiles `sam9x75_curiosity_ws4round.dtbo`. It must then be
added to the `.its` (image node `fdt_ws4round` + config `ws4round`) and the
`.itb` rebuilt with `mkimage`. Verify it landed:

```bash
# on WSL, against the built image:
dumpimage -l output/images/kernel.itb | grep -i ws4round
```

You should see the `fdt_ws4round` image and `ws4round` configuration.

## Then pick ONE of these to select it (inspect the FAT partition first)

Mount the boot partition read-only first and look at what's there:

```bash
mkdir -p /mnt/boot && sudo mount -o loop,ro,offset=$((<part1_start_sector>*512)) \
    output/images/sdcard.img /mnt/boot
ls /mnt/boot        # expect: BOOT.BIN u-boot.bin kernel.itb  (+ uEnv.txt or boot.scr?)
```

### Option A — `uEnv.txt` present (easiest, no recompile)
Add/append the overlay config name to the U-Boot boot command variable. The
Microchip default `bootcmd` typically expands an `overlays`/`fit_config` var:

```
# /mnt/boot/uEnv.txt
overlays=ws4round
```
If the BSP instead hard-codes the config in `bootcmd`, override it, e.g.:
```
uenvcmd=fatload mmc 0:1 0x22000000 kernel.itb; bootm 0x22000000#kernel_dtb#ws4round
```
Also add the GMAC PHY overlay for your board if Ethernet needs it (stack them):
`#kernel_dtb#ws4round#lan8840` (confirm the correct gmac config for the RDK).

### Option B — `boot.scr` present (compiled boot script)
Edit the source `boot.cmd`, set the overlay, and regenerate:
```bash
# make the bootm line read: ...#kernel_dtb#ws4round
mkimage -C none -A arm -T script -d boot.cmd boot.scr
sudo cp boot.scr /mnt/boot/
```

### Option C — only a saved `uboot.env` / compiled-in env
Rewrite the env offline with the U-Boot host tools:
```bash
# create fw_env.config pointing at the uboot.env file, then:
fw_setenv -c fw_env.config bootcmd \
  'fatload mmc 0:1 0x22000000 kernel.itb; bootm 0x22000000#kernel_dtb#ws4round'
```
(Most fragile — prefer A or B. If neither uEnv.txt nor boot.scr exists, consider
adding `uEnv.txt` support, or just set the default `.its` config to `ws4round`
so no env edit is needed at all — but that couples the image to this panel.)

## Boot and verify (SSH in — see ../README.md)

```bash
dmesg | grep -Ei 'dsi|panel|waveshare|hlcdc|xlcdc|goodix|gt9271'
modetest -M atmel-hlcdc            # expect a 720x720 connector/mode
modetest -M atmel-hlcdc -s <conn>:720x720 -v   # test pattern on the round panel
evtest                             # GT9271 multitouch on /dev/input/eventN
i2cdetect -y <busN>                # expect 0x14 (touch) and 0x45 (panel MCU)
```

`<busN>` is the i2c6 controller's Linux bus number — find it with
`ls /sys/bus/i2c/devices/` / `i2cdetect -l` (the FPC connector bus).

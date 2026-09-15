# Phase 0 — Back up the running demo microSD (DO THIS FIRST, non-destructive)

**Goal:** make a full byte-for-byte image of the SD card that currently boots the RDK demo,
keep the **original card untouched**, and do all Linux work on a **spare** card. We never
reflash on-board QSPI/NAND.

## What you need
- The demo microSD (pulled from the slot on the **back** of the board).
- A microSD card reader on the PC.
- A **spare** microSD ≥ 4 GB, Class 10 / UHS-I (Linux image is ~900 MB rootfs + boot).

## Option A — Win32DiskImager (simplest on Windows)
1. Insert the demo card. Note its drive letter (it shows a small FAT boot volume).
2. Open **Win32DiskImager** → set **Image File** to:
   `C:\ClaudeFiles\PROJECTS\SAM9X75-RDK\backup\sam9x75-demo-2026-09-02.img`
3. Select the card's device, click **Read** (NOT Write). This clones the whole card to the .img.
4. Wait for "Read Successful".

## Option B — WSL2 `dd` (full-card clone, most reliable)
In WSL2 (Ubuntu). Find the disk first — be careful to pick the SD, not your system disk:
```bash
# In an *admin* PowerShell, list physical disks to identify the card's number:
#   wmic diskdrive list brief        (or) Get-Disk
# Say the card is PhysicalDrive2  →  in WSL it's /dev/sdX after mounting, OR use:
sudo dd if=/dev/sdX of=/mnt/c/ClaudeFiles/PROJECTS/SAM9X75-RDK/backup/sam9x75-demo-2026-09-02.img \
        bs=4M status=progress conv=noerror,sync
sync
```
> `bs=4M` speeds it up; `conv=noerror,sync` keeps going past bad blocks. Double-check `sdX`.

## Option C — balenaEtcher "Clone drive"
Etcher → **Clone drive** → source = demo card → target file = the .img path above.

## Verify the backup (read-only)
Mount the image read-only and confirm the demo boot files are present:
```bash
# WSL2
mkdir -p /tmp/demoimg
# find the FAT partition offset:
fdisk -lu /mnt/c/ClaudeFiles/PROJECTS/SAM9X75-RDK/backup/sam9x75-demo-2026-09-02.img
# mount the first (boot/FAT) partition read-only using its start sector * 512 as offset:
sudo mount -o ro,loop,offset=$((START_SECTOR*512)) \
     /mnt/c/ClaudeFiles/PROJECTS/SAM9X75-RDK/backup/sam9x75-demo-2026-09-02.img /tmp/demoimg
ls -la /tmp/demoimg      # expect boot.bin + harmony.bin (bare-metal MGS demo)
sudo umount /tmp/demoimg
```
Expected on a bare-metal MGS demo card: **`boot.bin`** and **`harmony.bin`** in the FAT root.

## After backup
- **Reinsert the original demo card once**, power the board, confirm the demo still runs, then
  set that card aside — it is the golden copy. All Phase 2 Linux work uses the **spare** card.
- Record what you found in `CAPTURED_STATE.txt` (template alongside this file).

## Notes
- Imaging is a **read** of the card; it does not modify it. Safe to redo.
- Keep the .img — it lets us restore the demo to any card at any time (Etcher → Flash).

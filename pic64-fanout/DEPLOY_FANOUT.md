# PIC64 Fan-out — Deploy Notes (Phase 1)

Turns the PIC64 webcam from **single-viewer** (per-request ffmpeg, last-viewer-wins on
`/dev/video0`) into a **fan-out**: one persistent producer owns the camera and writes a shared
frame to tmpfs; the SAM9X75 display, the PC console, and the existing login site all read that
same frame at once. Adds login-less **LAN-token** endpoints for the display/PC.

> Develop/test here first. Board docroot is `/var/www/pic64webcam` (owner www-data). **Never
> overwrite the board's `data/settings.json`** — it holds the user's tuned values.

## New / changed files (in `pic64-fanout/webroot/`)
| File | Role |
|---|---|
| `camstream.php` | **Producer.** php-cli long process (run by systemd). One ffmpeg `/dev/video0` → `-update 1` → `/run/pic64cam/latest.jpg`. Watches settings.json; relaunches ffmpeg only when saturation/sharpness/mirror/flip/bw/resolution change. |
| `feed.php` | LAN-token MJPEG (`multipart/x-mixed-replace`) built from the shared frame. Any number of concurrent clients. |
| `snapshot.php` | LAN-token single latest JPEG. |
| `control_api.php` | LAN-token camera controls (mirror of `controls.php`, no session). Live subdev push + persists to settings.json. |
| `lib_lan.php` | `lan_gate()` = token + subnet (192.168.0.0/24) check. |
| `stream.php` | **Replaces** the board's `stream.php`: now a session-gated *reader* of the shared frame (no more ffmpeg spawn / pkill). `viewer.php` needs no change. |
| `config.append.php` | Constants to merge into the board's `config.php` (`LAN_TOKEN`, `LAN_SUBNET`, `CAMSTREAM_FILE`). |

`lib_source.php`, `config.php` (base), `controls.php`, `auth.php`, `apply-live.sh`,
`set-resolution.sh` are **reused unchanged** from the PIC64_WebCam project.

## Deploy steps (from this PC, Git Bash)
1. **Merge config constants.** Add the three constants from `config.append.php` into the board's
   `config.php` (edit the copy in `C:\ClaudeFiles\PROJECTS\PIC64_WebCam\webroot\config.php` first so the
   source of truth stays correct, then redeploy it). **Change `LAN_TOKEN`** to a fresh secret and
   use the SAME value in the PC console config.
2. **Copy the new/changed web files** to the board:
   ```bash
   cd /c/ClaudeFiles/PROJECTS/SAM9X75-RDK/pic64-fanout/webroot
   scp camstream.php feed.php snapshot.php control_api.php lib_lan.php stream.php \
       ubuntu@192.168.0.38:/tmp/fanout/
   ssh ubuntu@192.168.0.38 'sudo cp /tmp/fanout/*.php /var/www/pic64webcam/ && \
       sudo chown www-data:www-data /var/www/pic64webcam/*.php'
   ```
   (Deploy the edited `config.php` the same way — file-by-file, never `data/`.)
3. **Install the producer service:**
   ```bash
   scp /c/ClaudeFiles/PROJECTS/SAM9X75-RDK/pic64-fanout/systemd/pic64-camstream.service \
       ubuntu@192.168.0.38:/tmp/
   ssh ubuntu@192.168.0.38 'sudo cp /tmp/pic64-camstream.service /etc/systemd/system/ && \
       sudo systemctl daemon-reload && sudo systemctl enable --now pic64-camstream'
   ```
4. **Verify:**
   ```bash
   ssh ubuntu@192.168.0.38 'systemctl status pic64-camstream --no-pager; \
       ls -l /run/pic64cam/; journalctl -u pic64-camstream -n 20 --no-pager'
   ```
   Expect `latest.jpg` present and growing/refreshing.

## Test matrix (proves fan-out)
- **Simultaneous viewers:** open the login site (`http://192.168.0.38` → viewer) in one browser
  AND `http://192.168.0.38/feed.php?token=<LAN_TOKEN>` in another tab / second machine at the same
  time → **both** show live video, no stalls. (This is the whole point — impossible before.)
- **Auth gate:** `feed.php` with a wrong/absent token → **403**; a request from off-subnet → 403.
- **Live control:** `POST control_api.php?token=..` `{"brightness":90}` → running feed brightens
  with no restart. `{"saturation":80}` → brief relaunch (~1 s) then continues.
- **Snapshot:** `snapshot.php?token=..` returns one JPEG.
- **Login site still works** for the existing admin UI (sliders, snapshot, fullscreen, exit).

## Rollback
- `sudo systemctl disable --now pic64-camstream` and restore the original `stream.php`
  (in `C:\ClaudeFiles\PROJECTS\PIC64_WebCam\snapshot\webroot\stream.php`) to return to single-viewer.

## Notes / rationale
- **Why a shared file, not a relay:** `/dev/video0` is single-open; a file on tmpfs is the
  simplest robust fan-out and survives any number of readers. Readers validate JPEG SOI/EOI so a
  frame caught mid-write is skipped, not shown as garbage.
- **Live vs restart controls unchanged:** brightness/contrast/exposure/wb still go straight to the
  hardware subdevs (`apply-live.sh`) with no restart; only ffmpeg-side look settings relaunch the
  encoder — now inside the producer, invisibly, instead of per request.

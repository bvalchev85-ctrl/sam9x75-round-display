# SAM9X75-RDK — PC Security Console (Phase 3)

Browser console that runs on the **home PC** and shows the live PIC64 webcam
(`192.168.0.38`) alongside **arm/disarm**, a **motion/alert banner**, and
**camera-control sliders** proxied to the PIC64. It shares the same fan-out feed
that the SAM9X75 round display (Phase 4) and any browser use — no device
contention.

This is the PC half of the plan (`fuzzy-knitting-dijkstra.md`, Phase 3). It talks
to the LAN-token endpoints deployed on the board in Phase 1
(`feed.php` / `snapshot.php` / `control_api.php`).

## Layout

```
console-php/
├─ public/                 web docroot (php -S -t public)
│  ├─ index.php            dashboard UI (login-gated)
│  ├─ login.php / logout.php
│  ├─ api/
│  │  ├─ status.php        GET armed+motion; POST arm/disarm/motion/clear -> data/state.json
│  │  ├─ controls.php      GET/POST -> proxied to PIC64 control_api.php (token added server-side)
│  │  ├─ snapshot.php      single JPEG, proxied (no token in browser)
│  │  └─ config.php        hands the tokenized feed URL to an authenticated session only
│  └─ assets/              app.css, app.js  (local, no CDNs — R7)
├─ src/
│  ├─ config.php           PIC64 URL + LAN token, console login, motion tuning
│  ├─ auth.php             session login (mirrors PIC64 login site)
│  └─ lib.php              state persistence + PIC64 HTTP proxy (curl/stream fallback)
├─ data/state.json         armed / motion_last / event ring  (runtime state)
├─ bin/motion-worker.php   optional frame-diff motion detector (GD)
├─ run.ps1                 dev server launcher (finds PHP, serves public\)
└─ README.md
```

## Prerequisites

PHP 8.x with **curl** (proxy) and, for real motion detection, **gd**.
The PC has no PHP yet — install once (internet only for this step):

1. Download the Windows PHP zip (x64, Thread Safe) from <https://windows.php.net/download/>.
2. Extract into `console-php\php\` so that `console-php\php\php.exe` exists
   (offline-first per R7 — keep it inside the project). Any PATH/XAMPP PHP also works.
3. In that `php\` folder: copy `php.ini-development` → `php.ini` and uncomment
   `extension=curl` and `extension=gd` (and set `extension_dir = "ext"`).

## Run

```powershell
cd C:\ClaudeFiles\PROJECTS\SAM9X75-RDK\console-php
.\run.ps1                       # http://localhost:8080  (also on the LAN for the board)
```

Open <http://localhost:8080>, sign in (defaults **admin / changeme** — change in
`src\config.php`).

## How the pieces talk

- **Live video** is fetched by the browser **directly** from the board
  (`http://192.168.0.38/feed.php?token=…`). The built-in `php -S` server is
  single-threaded and can't proxy a never-ending MJPEG stream without blocking, so
  we keep the stream off it. The token is handed only to a logged-in session via
  `api/config.php` (not baked into static HTML). On the LAN this is fine; to hide
  the token fully, front the console with Apache/nginx and reverse-proxy `/feed`.
- **Controls** POST plain JSON to `api/controls.php`, which adds the LAN token and
  forwards to the board's `control_api.php`. Brightness/contrast/exposure/WB apply
  live; saturation/sharpness/mirror/flip/B&W/resolution restart the encoder (~1 s,
  marked `↻` in the UI).
- **Arm/disarm + motion** live in `data/state.json`. `alert = armed && motion`.

## Motion detection

MVP works with the **Test motion** button (or `POST /api/status {action:"motion"}`).
For real detection, run the worker (needs GD):

```powershell
php bin\motion-worker.php --verbose
```

It polls `snapshot.php`, diffs a 32×32 luma grid, and stamps `motion_last` when
enough cells change. Tune `MOTION_DIFF_THRESHOLD` / `MOTION_CHANGED_RATIO` /
`MOTION_HOLD_SECS` in `src\config.php`.

## API contract (also used by the Phase 4 EGT app)

| Endpoint | Method | Body / Query | Returns |
|---|---|---|---|
| `/api/status.php`   | GET  | – | `{ok,armed,motion,alert,motion_age,armed_at,updated,now}` |
| `/api/status.php`   | POST | `{action:"arm"\|"disarm"\|"motion"\|"clear"}` | same status view |
| `/api/controls.php` | GET  | `?defaults=1` optional | `{ok,settings}` / `{ok,defaults}` |
| `/api/controls.php` | POST | `{brightness:0-100,…,wb,resolution,mirror,flip,bw}` | `{ok,settings}` |
| `/api/snapshot.php` | GET  | – | `image/jpeg` |
| `/api/config.php`   | GET  | – | `{ok,feed_url,snapshot_url,pic64_base}` |

## Security notes (LAN appliance)

- Console login is a single shared account compared with `hash_equals` — change
  `CONSOLE_USER`/`CONSOLE_PASS` in `src\config.php`.
- The board also enforces token **+ subnet** (`192.168.0.0/24`) on every camera
  endpoint, so a leaked token off-LAN still 403s.
- Nothing here is meant to face the open internet.

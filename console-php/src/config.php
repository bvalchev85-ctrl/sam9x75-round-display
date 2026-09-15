<?php
/**
 * SAM9X75-RDK PC Console — configuration.
 *
 * Runs on the home PC (php -S or Apache). Talks to the PIC64 webcam at .38 over
 * the LAN-token endpoints deployed in Phase 1 (feed.php / snapshot.php /
 * control_api.php). Keep this file OUT of the web docroot (it lives in ../src).
 */

// ---- PIC64 camera (Phase 1 fan-out endpoints) --------------------------------
const PIC64_BASE  = 'http://192.168.0.38';                     // board IP
const LAN_TOKEN   = 'CHANGE_ME_LAN_TOKEN';        // must match board config.php
const LAN_SUBNET  = '192.168.0.0/24';                          // informational (the board enforces it)

// Camera endpoints on the board
const PIC64_FEED     = PIC64_BASE . '/feed.php';        // MJPEG multipart stream
const PIC64_SNAPSHOT = PIC64_BASE . '/snapshot.php';    // single JPEG
const PIC64_CONTROL  = PIC64_BASE . '/control_api.php'; // GET settings / POST changes

// ---- Console login (LAN appliance) -------------------------------------------
// This is a LAN-only home console. Change these before first use. Plaintext is
// compared with hash_equals(); good enough behind the home router, not the open net.
const CONSOLE_USER = 'admin';
const CONSOLE_PASS = 'changeme';        // <-- CHANGE ME
const SESSION_NAME = 'sam9x75console';

// ---- Paths -------------------------------------------------------------------
const STATE_FILE = __DIR__ . '/../data/state.json';

// ---- Motion / alert behaviour ------------------------------------------------
// A motion detection is considered "active" for this many seconds after the last
// trip (so the banner doesn't flicker between frames). The motion worker updates
// state.motion_last; the API derives the effective motion flag from it.
const MOTION_HOLD_SECS = 6;

// Frame-diff sensitivity for bin/motion-worker.php (only used by the worker).
const MOTION_DIFF_THRESHOLD = 12;   // mean per-pixel luma delta (0..255) to count a changed cell
const MOTION_CHANGED_RATIO  = 0.02; // fraction of cells that must change to call it motion (2%)
const MOTION_POLL_MS        = 700;  // worker snapshot poll interval

// ---- HTTP proxy behaviour ----------------------------------------------------
const PIC64_HTTP_TIMEOUT = 5;       // seconds for control/snapshot proxy calls

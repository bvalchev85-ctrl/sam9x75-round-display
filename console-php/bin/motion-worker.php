<?php
/**
 * SAM9X75-RDK PC Console — motion detection worker (CLI, optional).
 *
 * Polls the PIC64 snapshot endpoint, does a cheap frame-diff (downscaled
 * grayscale mean-delta), and writes `motion_last` into the shared state.json
 * when movement is detected. The API/UI derive the live `motion`/`alert` flags
 * from that timestamp (see lib.php motion_active()).
 *
 * This is intentionally decoupled: the console works without it (Test-motion
 * button + /api/status "motion" action cover the MVP). Run it when you want real
 * detection:
 *
 *     php bin/motion-worker.php                 # runs until Ctrl-C
 *     php bin/motion-worker.php --verbose       # prints per-frame diff score
 *
 * Requires the GD extension (bundled with most PHP builds; enable php_gd in
 * php.ini if missing — the script tells you if it's not there).
 */
require_once __DIR__ . '/../src/config.php';
require_once __DIR__ . '/../src/lib.php';

$verbose = in_array('--verbose', $argv, true);

if (!extension_loaded('gd')) {
    fwrite(STDERR, "[motion] GD extension not loaded. Enable 'extension=gd' in php.ini.\n");
    fwrite(STDERR, "[motion] Until then, use the console's 'Test motion' button / POST {action:'motion'}.\n");
    exit(1);
}

const GRID = 32; // downscale to GRID x GRID luma cells for comparison

/** Fetch a snapshot JPEG from the board, or null. */
function fetch_snapshot(): ?string {
    [$code, $body, , $err] = pic64_http(pic64_url(PIC64_SNAPSHOT), 'GET');
    if ($err !== null || $code !== 200 || $body === '') return null;
    return $body;
}

/** Reduce a JPEG to a GRID*GRID array of luma values (0..255), or null. */
function luma_grid(string $jpeg): ?array {
    $img = @imagecreatefromstring($jpeg);
    if (!$img) return null;
    $small = imagecreatetruecolor(GRID, GRID);
    imagecopyresampled($small, $img, 0, 0, 0, 0, GRID, GRID, imagesx($img), imagesy($img));
    imagedestroy($img);
    $out = [];
    for ($y = 0; $y < GRID; $y++) {
        for ($x = 0; $x < GRID; $x++) {
            $rgb = imagecolorat($small, $x, $y);
            $r = ($rgb >> 16) & 0xFF; $g = ($rgb >> 8) & 0xFF; $b = $rgb & 0xFF;
            $out[] = (int)(0.299 * $r + 0.587 * $g + 0.114 * $b);
        }
    }
    imagedestroy($small);
    return $out;
}

fwrite(STDERR, "[motion] worker started; polling {$GLOBALS['argv'][0]} every " . MOTION_POLL_MS . " ms\n");
$prev = null;
$pollUs = MOTION_POLL_MS * 1000;

while (true) {
    $jpg = fetch_snapshot();
    if ($jpg === null) { usleep($pollUs); continue; }

    $grid = luma_grid($jpg);
    if ($grid === null) { usleep($pollUs); continue; }

    if ($prev !== null) {
        $changed = 0; $n = count($grid);
        for ($i = 0; $i < $n; $i++) {
            if (abs($grid[$i] - $prev[$i]) >= MOTION_DIFF_THRESHOLD) $changed++;
        }
        $ratio = $changed / $n;
        if ($verbose) fwrite(STDERR, sprintf("[motion] changed=%.3f (%d/%d)\n", $ratio, $changed, $n));
        if ($ratio >= MOTION_CHANGED_RATIO) {
            $s = load_state();
            $s['motion_last'] = time();
            log_event($s, 'motion', sprintf('worker %.1f%%', $ratio * 100));
            save_state($s);
            if ($verbose) fwrite(STDERR, "[motion] >>> MOTION trip\n");
        }
    }
    $prev = $grid;
    usleep($pollUs);
}

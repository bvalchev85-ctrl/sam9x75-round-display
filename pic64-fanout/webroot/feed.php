<?php
/**
 * PIC64 fan-out — LAN-token MJPEG stream built from the shared producer frame.
 *
 * Reads CAMSTREAM_FILE (tmpfs latest.jpg, updated ~16 fps by camstream.php) and
 * emits multipart/x-mixed-replace. Because it never touches /dev/video0, any
 * number of these can run at once (display + PC + extra browsers) with no
 * contention. No login — gated by LAN token + subnet (see lib_lan.php).
 *
 * Usage: GET /feed.php?token=<LAN_TOKEN>
 */
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/lib_lan.php';
lan_gate();

$OUT = defined('CAMSTREAM_FILE') ? CAMSTREAM_FILE : '/run/pic64cam/latest.jpg';
$FPS = defined('FRAME_RATE') ? (int)FRAME_RATE : 16;
if ($FPS < 1) $FPS = 16;
$frameUs   = (int)(1000000 / $FPS);
$boundary  = 'ffmpeg';               // same token the login viewer already expects

// Streaming HTTP setup: no buffering, no gzip, no time limit.
@ini_set('zlib.output_compression', '0');
@ini_set('output_buffering', '0');
@ini_set('implicit_flush', '1');
if (function_exists('apache_setenv')) { @apache_setenv('no-gzip', '1'); }
while (ob_get_level() > 0) { @ob_end_clean(); }
set_time_limit(0);
ignore_user_abort(false);

header('Content-Type: multipart/x-mixed-replace; boundary=' . $boundary);
header('Cache-Control: no-cache, private');
header('Connection: close');
header('X-Accel-Buffering: no');
header('Pragma: no-cache');

/** Read a complete JPEG (SOI..EOI) or null if the file is mid-write / absent. */
function read_valid_jpeg(string $path): ?string {
    $d = @file_get_contents($path);
    if ($d === false || strlen($d) < 4) return null;
    // SOI = FFD8 at start, EOI = FFD9 at end. -update writes in place, so a reader
    // can occasionally catch a partial frame; skip those rather than send garbage.
    if (substr($d, 0, 2) !== "\xFF\xD8") return null;
    if (substr($d, -2)   !== "\xFF\xD9") return null;
    return $d;
}

// Pace by frame interval and dedup by content. NOTE: we deliberately do NOT gate
// on filemtime() — PHP's filemtime has 1-second granularity, which would throttle
// the stream to ~1 fps even though the producer refreshes ~16 fps. Instead we read
// each interval and only send when the bytes actually changed.
$lastHash = '';
$idleUs = 0;
while (!connection_aborted()) {
    clearstatcache(false, $OUT);
    $jpg = read_valid_jpeg($OUT);
    if ($jpg !== null) {
        $h = md5($jpg);
        if ($h !== $lastHash) {
            $lastHash = $h;
            $idleUs = 0;
            echo "--{$boundary}\r\n";
            echo "Content-Type: image/jpeg\r\n";
            echo 'Content-Length: ' . strlen($jpg) . "\r\n\r\n";
            echo $jpg;
            echo "\r\n";
            flush();
            usleep($frameUs);
            continue;
        }
    }
    // Same frame (or mid-write) — short nap, then look again.
    $nap = (int)($frameUs / 4);
    usleep($nap);
    $idleUs += $nap;
    if ($idleUs > 5000000) break; // producer down ~5 s → let the client reconnect
}

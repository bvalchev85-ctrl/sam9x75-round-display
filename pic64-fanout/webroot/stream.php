<?php
/**
 * PIC64_WebCam — MJPEG stream for the LOGIN site (viewer.php), REWORKED for fan-out.
 *
 * BEFORE: this spawned a per-request ffmpeg on /dev/video0 and pkill'd any other
 * ffmpeg (last-viewer-wins) — which blocked the SAM9X75 display and PC from
 * viewing at the same time. NOW it is a pure reader of the shared producer frame
 * (CAMSTREAM_FILE) maintained by pic64-camstream.service, exactly like feed.php
 * but gated by the browser session instead of a LAN token. No device access here.
 */
require_once __DIR__ . '/auth.php';
require_once __DIR__ . '/lib_source.php';
require_login();

// Release the session lock before the (infinite) stream loop so slider saves and
// logout aren't serialized behind this never-ending request (see original note).
session_write_close();

$OUT = defined('CAMSTREAM_FILE') ? CAMSTREAM_FILE : '/run/pic64cam/latest.jpg';
$FPS = defined('FRAME_RATE') ? (int)FRAME_RATE : 16;
if ($FPS < 1) $FPS = 16;
$frameUs  = (int)(1000000 / $FPS);
$boundary = 'ffmpeg';

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

function read_valid_jpeg(string $path): ?string {
    $d = @file_get_contents($path);
    if ($d === false || strlen($d) < 4) return null;
    if (substr($d, 0, 2) !== "\xFF\xD8") return null;
    if (substr($d, -2)   !== "\xFF\xD9") return null;
    return $d;
}

// Pace by frame interval + dedup by content (filemtime has 1-second granularity,
// which would throttle to ~1 fps — see feed.php note).
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
    $nap = (int)($frameUs / 4);
    usleep($nap);
    $idleUs += $nap;
    if ($idleUs > 5000000) break;
}

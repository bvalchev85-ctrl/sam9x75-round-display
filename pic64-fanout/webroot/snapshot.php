<?php
/**
 * PIC64 fan-out — single latest JPEG (LAN token + subnet gated).
 * Trivial now that camstream.php maintains a shared frame on tmpfs.
 * Usage: GET /snapshot.php?token=<LAN_TOKEN>
 */
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/lib_lan.php';
lan_gate();

$OUT = defined('CAMSTREAM_FILE') ? CAMSTREAM_FILE : '/run/pic64cam/latest.jpg';

// Retry briefly in case we catch the file mid-write.
$jpg = null;
for ($i = 0; $i < 5; $i++) {
    $d = @file_get_contents($OUT);
    if ($d !== false && strlen($d) > 3
        && substr($d, 0, 2) === "\xFF\xD8" && substr($d, -2) === "\xFF\xD9") {
        $jpg = $d;
        break;
    }
    usleep(30000);
}

if ($jpg === null) {
    http_response_code(503);
    header('Content-Type: text/plain');
    echo "503 no frame available (producer down?)\n";
    exit;
}

header('Content-Type: image/jpeg');
header('Content-Length: ' . strlen($jpg));
header('Cache-Control: no-cache, private');
echo $jpg;

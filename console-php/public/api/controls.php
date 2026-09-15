<?php
/**
 * /api/controls.php — server-side proxy to the PIC64 camera control API.
 *
 * The LAN token never reaches the browser: the page POSTs plain JSON here, this
 * endpoint adds the token and forwards to PIC64 control_api.php over the LAN.
 *
 *   GET                 -> current camera settings {ok, settings:{...}}
 *   GET ?defaults=1     -> factory defaults        {ok, defaults:{...}}
 *   POST {brightness:.} -> applies, returns updated {ok, settings:{...}}
 *
 * Validation is intentionally light here (the board's control_api.php is the
 * authority and re-validates every key); we just relay the body.
 */
require_once __DIR__ . '/../../src/auth.php';
require_once __DIR__ . '/../../src/lib.php';
require_login(true);

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $raw = file_get_contents('php://input');
    // Ensure we forward valid JSON (fall back to form post).
    $in = json_decode($raw, true);
    if (!is_array($in)) $in = $_POST;
    unset($in['token']); // token is added server-side only
    $body = json_encode($in);

    [$code, $resp, $ct, $err] = pic64_http(pic64_url(PIC64_CONTROL), 'POST', $body, 'application/json');
    if ($err !== null || $code === 0) {
        json_out(['ok' => false, 'error' => 'pic64_unreachable', 'detail' => $err], 502);
    }
    // Pass the board's JSON straight through (already {ok, settings}).
    http_response_code($code);
    header('Content-Type: application/json');
    header('Cache-Control: no-store');
    echo $resp !== '' ? $resp : json_encode(['ok' => false, 'error' => 'empty_response']);
    exit;
}

// GET (optionally ?defaults=1)
$q = [];
if (($_GET['defaults'] ?? '') === '1') $q['defaults'] = '1';
[$code, $resp, $ct, $err] = pic64_http(pic64_url(PIC64_CONTROL, $q), 'GET');
if ($err !== null || $code === 0) {
    json_out(['ok' => false, 'error' => 'pic64_unreachable', 'detail' => $err], 502);
}
http_response_code($code);
header('Content-Type: application/json');
header('Cache-Control: no-store');
echo $resp !== '' ? $resp : json_encode(['ok' => false, 'error' => 'empty_response']);

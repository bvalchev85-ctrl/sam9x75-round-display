<?php
/**
 * PIC64 fan-out — LAN-token camera control API for the SAM9X75 display and the
 * PC console. Same behaviour as the login-protected controls.php, but gated by
 * LAN token + subnet instead of a browser session.
 *
 *   GET  /control_api.php?token=..            -> {"ok":true,"settings":{...}}
 *   GET  /control_api.php?token=..&defaults=1 -> {"ok":true,"defaults":{...}}
 *   POST /control_api.php?token=.. (JSON body {brightness:70,...})
 *                                             -> {"ok":true,"settings":{...}}
 *
 * Live controls (brightness/contrast/exposure/wb) take effect immediately on the
 * running stream via apply-live.sh (cam_apply_native). Restart controls
 * (saturation/sharpness/mirror/flip/bw/resolution) are persisted to settings.json;
 * camstream.php notices and relaunches ffmpeg within ~1 s.
 */
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/lib_source.php';
require_once __DIR__ . '/lib_lan.php';
lan_gate();

header('Content-Type: application/json');

function load_settings(): array {
    $s = @json_decode(@file_get_contents(SETTINGS_FILE), true);
    if (!is_array($s)) $s = [];
    return array_merge(default_settings(), $s);
}
function save_settings(array $s): bool {
    @mkdir(dirname(SETTINGS_FILE), 0775, true);
    return @file_put_contents(SETTINGS_FILE, json_encode($s, JSON_PRETTY_PRINT)) !== false;
}
function clampi($v, $lo, $hi) { $v = (int)$v; return max($lo, min($hi, $v)); }

if (($_GET['defaults'] ?? '') === '1') {
    echo json_encode(['ok' => true, 'defaults' => default_settings()]);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $raw = file_get_contents('php://input');
    $in  = json_decode($raw, true);
    if (!is_array($in)) $in = $_POST;
    unset($in['token']); // never a setting

    $s   = load_settings();
    $def = default_settings();

    foreach ($in as $k => $v) {
        if (!array_key_exists($k, $def)) continue; // ignore unknown keys
        switch ($k) {
            case 'wb':
                $allowed = ['auto','incandescent','daylight','cloudy'];
                if (in_array($v, $allowed, true)) $s[$k] = $v;
                break;
            case 'resolution':
                if (in_array($v, cam_allowed_resolutions(), true)) $s[$k] = $v;
                break;
            case 'mirror':
            case 'flip':
            case 'bw':
                $s[$k] = filter_var($v, FILTER_VALIDATE_BOOLEAN);
                break;
            default: // numeric sliders 0..100
                $s[$k] = clampi($v, 0, 100);
        }
    }
    $ok = save_settings($s);
    cam_apply_native($s); // live subdev push (brightness/contrast/exposure/wb)
    echo json_encode(['ok' => $ok, 'settings' => $s]);
    exit;
}

// GET
echo json_encode(['ok' => true, 'settings' => load_settings()]);

<?php
/**
 * /api/status.php — arm/disarm + motion state for the console and the EGT app.
 *
 *   GET                          -> {ok, armed, motion, alert, motion_age, ...}
 *   POST {"action":"arm"}        -> arms, returns status
 *   POST {"action":"disarm"}     -> disarms
 *   POST {"action":"motion"}     -> manual/simulated motion trip (MVP + testing)
 *   POST {"action":"clear"}      -> clears motion immediately
 *
 * The board's EGT app and the browser UI both poll this. Login-gated (session);
 * the EGT app can authenticate once and reuse the cookie, or we relax this to a
 * LAN token later if needed.
 */
require_once __DIR__ . '/../../src/auth.php';
require_once __DIR__ . '/../../src/lib.php';
require_login(true); // JSON 401 rather than redirect

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $raw = file_get_contents('php://input');
    $in  = json_decode($raw, true);
    if (!is_array($in)) $in = $_POST;
    $action = $in['action'] ?? '';

    $s = load_state();
    switch ($action) {
        case 'arm':
            $s['armed'] = true;
            $s['armed_at'] = time();
            log_event($s, 'arm');
            break;
        case 'disarm':
            $s['armed'] = false;
            log_event($s, 'disarm');
            break;
        case 'motion':
            $s['motion_last'] = time();
            log_event($s, 'motion', 'manual');
            break;
        case 'clear':
            $s['motion_last'] = 0;
            log_event($s, 'clear');
            break;
        default:
            json_out(['ok' => false, 'error' => 'unknown_action'], 400);
    }
    save_state($s);
    json_out(status_view($s));
}

// GET
json_out(status_view(load_state()));

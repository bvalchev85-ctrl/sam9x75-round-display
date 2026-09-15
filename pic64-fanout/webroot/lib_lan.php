<?php
/**
 * PIC64 fan-out — LAN token + subnet gate for the login-less endpoints
 * (feed.php, snapshot.php, control_api.php) that the SAM9X75 display and the PC
 * console call. These bypass the cookie session on purpose (the display is a
 * headless native app, not a browser), so access is gated two ways:
 *   1. a shared secret token (LAN_TOKEN in config.php), AND
 *   2. the caller's REMOTE_ADDR must sit inside LAN_SUBNET (192.168.0.0/24).
 * Both must pass. Neither is a substitute for real auth on the open internet —
 * this is a LAN-only home appliance.
 */
require_once __DIR__ . '/config.php';

/** True if $ip (IPv4, incl. ::ffff: mapped) is inside CIDR "a.b.c.d/nn". */
function ip_in_cidr(string $ip, string $cidr): bool {
    // Normalise IPv4-mapped IPv6 (e.g. ::ffff:192.168.0.5)
    if (stripos($ip, '::ffff:') === 0) $ip = substr($ip, 7);
    if (strpos($cidr, '/') === false) return hash_equals($cidr, $ip);
    [$net, $bits] = explode('/', $cidr, 2);
    $ipL  = ip2long($ip);
    $netL = ip2long($net);
    if ($ipL === false || $netL === false) return false;
    $bits = (int)$bits;
    if ($bits <= 0)  return true;
    if ($bits >= 32) return $ipL === $netL;
    $mask = -1 << (32 - $bits);
    return ($ipL & $mask) === ($netL & $mask);
}

/** Enforce the token+subnet gate or emit 403 and exit. Call at the top of every
 *  login-less endpoint, BEFORE any streaming headers. */
function lan_gate(): void {
    $tok = $_GET['token'] ?? $_POST['token'] ?? '';
    $okTok = defined('LAN_TOKEN') && LAN_TOKEN !== '' && is_string($tok)
             && hash_equals(LAN_TOKEN, $tok);

    $ip = $_SERVER['REMOTE_ADDR'] ?? '';
    $subnet = defined('LAN_SUBNET') ? LAN_SUBNET : '192.168.0.0/24';
    $okIp = $ip !== '' && ip_in_cidr($ip, $subnet);

    if (!$okTok || !$okIp) {
        http_response_code(403);
        header('Content-Type: text/plain');
        echo "403 Forbidden\n";
        exit;
    }
}

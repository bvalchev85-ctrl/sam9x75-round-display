<?php
/**
 * SAM9X75-RDK PC Console — shared helpers: state persistence + PIC64 HTTP proxy.
 */
require_once __DIR__ . '/config.php';

// ---- JSON output -------------------------------------------------------------
function json_out(array $a, int $code = 200): void {
    http_response_code($code);
    header('Content-Type: application/json');
    header('Cache-Control: no-store');
    echo json_encode($a);
    exit;
}

// ---- Console state (armed / motion) -----------------------------------------
function default_state(): array {
    return [
        'armed'       => false,
        'armed_at'    => 0,
        'motion_last' => 0,   // unix ts of most recent motion trip (0 = never)
        'updated'     => 0,
        'events'      => [],  // capped ring of {t, type, msg}
    ];
}

function load_state(): array {
    $raw = @file_get_contents(STATE_FILE);
    $s = is_string($raw) ? json_decode($raw, true) : null;
    if (!is_array($s)) $s = [];
    return array_merge(default_state(), $s);
}

/** Atomic write with an exclusive lock so the worker and API don't clobber each other. */
function save_state(array $s): bool {
    $s['updated'] = time();
    @mkdir(dirname(STATE_FILE), 0775, true);
    $tmp = STATE_FILE . '.tmp';
    $json = json_encode($s, JSON_PRETTY_PRINT);
    $fp = @fopen($tmp, 'wb');
    if (!$fp) return false;
    $ok = flock($fp, LOCK_EX) && (fwrite($fp, $json) !== false);
    fflush($fp);
    flock($fp, LOCK_UN);
    fclose($fp);
    if (!$ok) { @unlink($tmp); return false; }
    return @rename($tmp, STATE_FILE);
}

function log_event(array &$s, string $type, string $msg = ''): void {
    $s['events'][] = ['t' => time(), 'type' => $type, 'msg' => $msg];
    // keep last 50
    if (count($s['events']) > 50) $s['events'] = array_slice($s['events'], -50);
}

/** Effective motion flag: true only if the last trip is within the hold window. */
function motion_active(array $s): bool {
    return $s['motion_last'] > 0 && (time() - (int)$s['motion_last']) <= MOTION_HOLD_SECS;
}

/** Public status view derived from stored state. */
function status_view(array $s): array {
    $motion = motion_active($s);
    return [
        'ok'         => true,
        'armed'      => (bool)$s['armed'],
        'armed_at'   => (int)$s['armed_at'],
        'motion'     => $motion,
        'motion_age' => $s['motion_last'] > 0 ? (time() - (int)$s['motion_last']) : -1,
        'alert'      => ((bool)$s['armed']) && $motion,   // armed + motion = alarm
        'updated'    => (int)$s['updated'],
        'now'        => time(),
    ];
}

// ---- PIC64 HTTP proxy --------------------------------------------------------
/** Append the LAN token to a PIC64 endpoint URL. */
function pic64_url(string $base, array $query = []): string {
    $query['token'] = LAN_TOKEN;
    return $base . '?' . http_build_query($query);
}

/**
 * Do an HTTP request to the PIC64. Prefers cURL, falls back to stream context.
 * Returns [int $httpCode, string $body, ?string $contentType, ?string $error].
 */
function pic64_http(string $url, string $method = 'GET', ?string $body = null, string $contentType = 'application/json'): array {
    if (function_exists('curl_init')) {
        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_HEADER         => false,
            CURLOPT_TIMEOUT        => PIC64_HTTP_TIMEOUT,
            CURLOPT_CONNECTTIMEOUT => PIC64_HTTP_TIMEOUT,
            CURLOPT_CUSTOMREQUEST  => $method,
        ]);
        if ($method === 'POST' || $body !== null) {
            curl_setopt($ch, CURLOPT_POSTFIELDS, (string)$body);
            curl_setopt($ch, CURLOPT_HTTPHEADER, ['Content-Type: ' . $contentType]);
        }
        $resp = curl_exec($ch);
        $code = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $ct   = curl_getinfo($ch, CURLINFO_CONTENT_TYPE) ?: null;
        $err  = $resp === false ? curl_error($ch) : null;
        curl_close($ch);
        return [$code, $resp === false ? '' : $resp, $ct, $err];
    }

    // Fallback: stream context (needs allow_url_fopen).
    $opts = ['http' => [
        'method'        => $method,
        'timeout'       => PIC64_HTTP_TIMEOUT,
        'ignore_errors' => true,
        'header'        => 'Content-Type: ' . $contentType . "\r\n",
    ]];
    if ($body !== null) $opts['http']['content'] = $body;
    $ctx  = stream_context_create($opts);
    $resp = @file_get_contents($url, false, $ctx);
    $code = 0; $ct = null;
    if (isset($http_response_header) && is_array($http_response_header)) {
        foreach ($http_response_header as $h) {
            if (preg_match('#^HTTP/\S+\s+(\d+)#', $h, $m)) $code = (int)$m[1];
            if (stripos($h, 'Content-Type:') === 0) $ct = trim(substr($h, 13));
        }
    }
    $err = $resp === false ? 'request_failed' : null;
    return [$code, $resp === false ? '' : $resp, $ct, $err];
}

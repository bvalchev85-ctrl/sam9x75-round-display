<?php
/**
 * /api/snapshot.php — proxies a single JPEG from the PIC64 (token added
 * server-side). Short request, safe to relay through php -S.
 */
require_once __DIR__ . '/../../src/auth.php';
require_once __DIR__ . '/../../src/lib.php';
require_login(true);

[$code, $resp, $ct, $err] = pic64_http(pic64_url(PIC64_SNAPSHOT), 'GET');
if ($err !== null || $code === 0 || $code >= 400 || $resp === '') {
    http_response_code(502);
    header('Content-Type: text/plain');
    echo "snapshot unavailable\n";
    exit;
}
header('Content-Type: ' . ($ct ?: 'image/jpeg'));
header('Content-Length: ' . strlen($resp));
header('Cache-Control: no-store');
echo $resp;

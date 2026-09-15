<?php
/**
 * /api/config.php — hands runtime config (incl. the tokenized feed URL) to an
 * AUTHENTICATED session only. Keeps the LAN token out of the static index.php
 * HTML: it is only ever emitted to a logged-in console user (DevTools on the LAN
 * can still see it — a reverse proxy would hide it fully, see README).
 *
 * The live MJPEG must be fetched by the browser directly from the board, because
 * `php -S` is single-threaded and cannot proxy a long-lived stream without
 * blocking every other request. Short requests (snapshot) are proxied instead.
 */
require_once __DIR__ . '/../../src/auth.php';
require_once __DIR__ . '/../../src/lib.php';
require_login(true);

json_out([
    'ok'           => true,
    'feed_url'     => pic64_url(PIC64_FEED),        // direct browser -> board MJPEG
    'snapshot_url' => 'api/snapshot.php',           // proxied (no token in browser)
    'pic64_base'   => PIC64_BASE,
]);

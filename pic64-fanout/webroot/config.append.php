<?php
// ===========================================================================
// PIC64 fan-out additions — MERGE these constants into the board's config.php
// (paste inside the top <?php block, e.g. just after SETTINGS_FILE).
// Do NOT ship this file as-is; it exists to document the additions.
// ===========================================================================

// Shared secret for the login-less LAN endpoints (feed.php / snapshot.php /
// control_api.php). The SAM9X75 display and the PC console send ?token=<this>.
// CHANGE THIS before deploy; keep it identical in the PC console's config.
const LAN_TOKEN  = 'CHANGE_ME_LAN_TOKEN';

// Only callers whose REMOTE_ADDR is inside this CIDR may use the token endpoints.
const LAN_SUBNET = '192.168.0.0/24';

// Where camstream.php (the persistent producer) writes the shared latest frame.
// tmpfs; created by the pic64-camstream.service RuntimeDirectory=pic64cam.
const CAMSTREAM_FILE = '/run/pic64cam/latest.jpg';

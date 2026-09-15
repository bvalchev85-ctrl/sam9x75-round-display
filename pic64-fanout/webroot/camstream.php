#!/usr/bin/env php
<?php
/**
 * PIC64 fan-out — persistent MJPEG producer (run by systemd, php-cli).
 *
 * WHY: the original stream.php spawned a per-request ffmpeg that opened the
 * single-open /dev/video0 and killed any other ffmpeg (last-viewer-wins). That
 * makes it impossible for the SAM9X75 display AND the home PC to view at once.
 *
 * This process owns /dev/video0 ONCE and continuously overwrites a single JPEG on
 * tmpfs (CAMSTREAM_FILE, default /run/pic64cam/latest.jpg). Every web reader
 * (feed.php MJPEG, snapshot.php, the login site's stream.php) then just reads that
 * shared frame -> unlimited simultaneous viewers, no device contention.
 *
 * Live image controls (brightness/contrast/exposure/wb) still change the RUNNING
 * stream with no restart, because they are applied to the hardware subdevs by
 * scripts/apply-live.sh (see cam_apply_native). Only the ffmpeg-side "restart"
 * settings (saturation/sharpness/mirror/flip/bw/resolution) require relaunching
 * the encoder; this loop watches settings.json and does that automatically.
 */

$WEBROOT = __DIR__;
require_once $WEBROOT . '/config.php';
require_once $WEBROOT . '/lib_source.php';

if (!defined('CAMSTREAM_FILE')) {
    fwrite(STDERR, "camstream: CAMSTREAM_FILE not defined in config.php\n");
    exit(2);
}
$OUT = CAMSTREAM_FILE;
@mkdir(dirname($OUT), 0755, true);

/* The subset of settings that live in the ffmpeg filter chain / capture geometry.
 * A change in any of these requires relaunching ffmpeg. brightness/contrast/
 * exposure/wb are NOT here — they go live to the subdevs and never restart. */
function vf_signature(array $s): string {
    $keys = ['saturation', 'sharpness', 'mirror', 'flip', 'bw', 'resolution'];
    $sub = [];
    foreach ($keys as $k) $sub[$k] = $s[$k] ?? null;
    return md5(json_encode($sub));
}

function load_current_settings(): array {
    $s = @json_decode(@file_get_contents(SETTINGS_FILE), true);
    if (!is_array($s)) $s = [];
    return array_merge(default_settings(), $s);
}

function build_cmd(array $s, string $out): string {
    $input = cam_input_args($s);                 // -f v4l2 ... /dev/video0 (uses saved resolution)
    $vf    = cam_vf($s);                          // saturation/sharpness/mirror/flip/bw
    $vfarg = $vf !== '' ? '-vf ' . escapeshellarg($vf) . ' ' : '';
    // -update 1 : keep overwriting a single file in place (continuous latest frame).
    // -f image2 with a fixed filename + -update 1 is the canonical "latest.jpg" pattern.
    // Prefix `exec ` so the sh -c that proc_open() spawns REPLACES itself with ffmpeg.
    // Without it, proc_terminate() would signal the shell and leave an orphaned ffmpeg
    // holding /dev/video0 on every settings-triggered restart (two ffmpegs fighting).
    return sprintf(
        'exec ffmpeg -hide_banner -loglevel error %s %s-q:v %d -f image2 -update 1 -y %s',
        $input,
        $vfarg,
        (int)JPEG_QUALITY,
        escapeshellarg($out)
    );
}

/* -------- graceful shutdown so systemd stop/restart is clean -------- */
$CHILD = null;
$RUNNING = true;
if (function_exists('pcntl_signal')) {
    pcntl_async_signals(true);
    $stop = function ($sig) use (&$RUNNING) { $RUNNING = false; };
    pcntl_signal(SIGTERM, $stop);
    pcntl_signal(SIGINT, $stop);
}

fwrite(STDERR, "camstream: starting, output=$OUT\n");

while ($RUNNING) {
    $s   = load_current_settings();
    $sig = vf_signature($s);

    // csi: retarget the media pipeline to the saved resolution while WE own the
    // device (no other ffmpeg is running), then push live subdev controls.
    cam_apply_resolution($s);
    usleep(100000);
    cam_apply_native($s);

    $cmd = build_cmd($s, $OUT);
    fwrite(STDERR, "camstream: launch: $cmd\n");

    $descr = [0 => ['file', '/dev/null', 'r'],
              1 => ['file', '/dev/null', 'w'],
              2 => ['file', '/dev/null', 'w']];
    $proc = proc_open($cmd, $descr, $pipes);
    if (!is_resource($proc)) {
        fwrite(STDERR, "camstream: proc_open failed; retry in 2s\n");
        sleep(2);
        continue;
    }

    // Supervise: poll ffmpeg liveness and watch for a vf/resolution change.
    while ($RUNNING) {
        $st = proc_get_status($proc);
        if (!$st['running']) {
            fwrite(STDERR, "camstream: ffmpeg exited (code {$st['exitcode']}); relaunch\n");
            break;
        }
        // Cheap change-detection: re-read settings once per second.
        clearstatcache();
        $now = load_current_settings();
        if (vf_signature($now) !== $sig) {
            fwrite(STDERR, "camstream: vf/resolution changed; restarting ffmpeg\n");
            break;
        }
        sleep(1);
    }

    // Tear down this ffmpeg before relaunching or exiting.
    $st = proc_get_status($proc);
    if ($st['running']) {
        proc_terminate($proc, SIGTERM);
        for ($i = 0; $i < 20; $i++) { // up to ~2s for a clean exit
            usleep(100000);
            if (!proc_get_status($proc)['running']) break;
        }
        if (proc_get_status($proc)['running']) proc_terminate($proc, SIGKILL);
    }
    proc_close($proc);

    if ($RUNNING) usleep(200000); // brief settle so /dev/video0 is released before reopen
}

@unlink($OUT); // don't serve a stale frame after the producer stops
fwrite(STDERR, "camstream: stopped\n");
exit(0);

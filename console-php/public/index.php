<?php
require_once __DIR__ . '/../src/auth.php';
require_login(); // redirects browsers to login.php
?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SAM9X75 Security Console</title>
<link rel="stylesheet" href="assets/app.css">
</head>
<body>
<header class="topbar">
  <div class="brand">SAM9X75 <span>Security Console</span></div>
  <div class="topbar-status">
    <span id="pill-armed" class="pill pill-off">DISARMED</span>
    <span id="pill-motion" class="pill pill-clear">NO MOTION</span>
    <span id="pill-link" class="pill pill-clear">CAM ?</span>
    <a class="logout" href="logout.php">Sign out</a>
  </div>
</header>

<main class="layout">
  <section class="stage">
    <div id="video-wrap" class="video-wrap">
      <img id="feed" alt="Live camera feed">
      <div id="banner" class="banner hidden">⚠ MOTION DETECTED</div>
      <div id="feed-msg" class="feed-msg">Connecting to camera…</div>
    </div>
    <div class="stage-actions">
      <button id="btn-arm" class="btn btn-arm">ARM</button>
      <button id="btn-snap" class="btn">Snapshot</button>
      <button id="btn-test-motion" class="btn btn-ghost" title="Simulate a motion trip">Test motion</button>
    </div>
  </section>

  <aside class="panel">
    <h2>Camera controls</h2>
    <p class="hint">Live: brightness / contrast / exposure / white balance apply instantly.
       Others restart the encoder (~1&nbsp;s).</p>

    <div class="ctrl-group" id="sliders"></div>

    <div class="ctrl-row">
      <label for="wb">White balance</label>
      <select id="wb" data-key="wb">
        <option value="auto">Auto</option>
        <option value="incandescent">Incandescent</option>
        <option value="daylight">Daylight</option>
        <option value="cloudy">Cloudy</option>
      </select>
    </div>

    <div class="ctrl-row">
      <label for="resolution">Resolution</label>
      <select id="resolution" data-key="resolution">
        <option value="640x480">640×480</option>
        <option value="800x600">800×600</option>
        <option value="960x540">960×540</option>
        <option value="1280x720">1280×720</option>
      </select>
    </div>

    <div class="ctrl-toggles">
      <label><input type="checkbox" data-key="mirror"> Mirror</label>
      <label><input type="checkbox" data-key="flip"> Flip</label>
      <label><input type="checkbox" data-key="bw"> B&amp;W</label>
    </div>

    <div class="panel-actions">
      <button id="btn-defaults" class="btn btn-ghost">Reset defaults</button>
      <span id="ctrl-msg" class="ctrl-msg"></span>
    </div>
  </aside>
</main>

<script src="assets/app.js"></script>
</body>
</html>

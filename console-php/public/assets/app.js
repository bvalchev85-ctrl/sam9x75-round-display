/* SAM9X75-RDK PC Console — front-end logic (vanilla JS, no deps, offline-first). */
(() => {
  'use strict';

  const SLIDERS = [
    { key: 'brightness', label: 'Brightness', live: true },
    { key: 'contrast',   label: 'Contrast',   live: true },
    { key: 'exposure',   label: 'Exposure',   live: true },
    { key: 'saturation', label: 'Saturation', live: false },
    { key: 'sharpness',  label: 'Sharpness',  live: false },
  ];

  const $ = (id) => document.getElementById(id);
  const feed   = $('feed');
  const wrap   = $('video-wrap');
  const banner = $('banner');
  const pillArmed  = $('pill-armed');
  const pillMotion = $('pill-motion');
  const pillLink   = $('pill-link');
  const btnArm = $('btn-arm');
  const ctrlMsg = $('ctrl-msg');

  let armed = false;

  // ---- helpers --------------------------------------------------------------
  async function api(path, opts) {
    const r = await fetch(path, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts));
    if (r.status === 401) { location.href = 'login.php'; throw new Error('auth'); }
    return r;
  }
  const jpost = (path, obj) => api(path, { method: 'POST', body: JSON.stringify(obj) }).then(r => r.json());
  const jget  = (path) => api(path).then(r => r.json());

  function setCtrlMsg(text, cls) {
    ctrlMsg.textContent = text;
    ctrlMsg.className = 'ctrl-msg' + (cls ? ' ' + cls : '');
    if (text) setTimeout(() => { if (ctrlMsg.textContent === text) { ctrlMsg.textContent = ''; ctrlMsg.className = 'ctrl-msg'; } }, 2500);
  }

  // ---- live feed ------------------------------------------------------------
  async function initFeed() {
    try {
      const cfg = await jget('api/config.php');
      if (!cfg.ok) throw new Error('cfg');
      feed.onload  = () => { wrap.classList.add('live'); pillLink.textContent = 'CAM LIVE'; pillLink.className = 'pill pill-good'; };
      feed.onerror = () => { wrap.classList.remove('live'); pillLink.textContent = 'CAM DOWN'; pillLink.className = 'pill pill-bad'; };
      // Cache-bust so a reconnect restarts the multipart stream.
      feed.src = cfg.feed_url + '&_=' + Date.now();
      $('btn-snap').onclick = () => window.open(cfg.snapshot_url + '?_=' + Date.now(), '_blank');
    } catch (e) {
      $('feed-msg').textContent = 'Camera config unavailable.';
      pillLink.textContent = 'CAM DOWN'; pillLink.className = 'pill pill-bad';
    }
  }

  // ---- status poll ----------------------------------------------------------
  function renderStatus(s) {
    armed = !!s.armed;
    pillArmed.textContent = armed ? 'ARMED' : 'DISARMED';
    pillArmed.className = 'pill ' + (armed ? 'pill-armed' : 'pill-off');
    btnArm.textContent = armed ? 'DISARM' : 'ARM';
    btnArm.classList.toggle('armed', armed);

    pillMotion.textContent = s.motion ? 'MOTION' : 'NO MOTION';
    pillMotion.className = 'pill ' + (s.motion ? 'pill-motion' : 'pill-clear');

    const alert = !!s.alert;
    banner.classList.toggle('hidden', !alert);
    wrap.classList.toggle('alarm', alert);
  }

  async function pollStatus() {
    try { renderStatus(await jget('api/status.php')); }
    catch (e) { /* leave last state on transient error */ }
  }

  btnArm.onclick = async () => {
    try { renderStatus(await jpost('api/status.php', { action: armed ? 'disarm' : 'arm' })); }
    catch (e) {}
  };
  $('btn-test-motion').onclick = async () => {
    try { renderStatus(await jpost('api/status.php', { action: 'motion' })); } catch (e) {}
  };

  // ---- camera controls ------------------------------------------------------
  function buildSliders() {
    const host = $('sliders');
    host.innerHTML = '';
    for (const s of SLIDERS) {
      const wrapEl = document.createElement('div');
      wrapEl.className = 'ctrl-slider';
      wrapEl.innerHTML =
        `<label for="s-${s.key}"><span>${s.label}${s.live ? '' : ' <em style="color:var(--warn)">↻</em>'}</span>` +
        `<span class="val" id="v-${s.key}">–</span></label>` +
        `<input type="range" id="s-${s.key}" data-key="${s.key}" min="0" max="100" step="1">`;
      host.appendChild(wrapEl);
    }
  }

  let debounce = {};
  function onControlChange(key, value) {
    const obj = {}; obj[key] = value;
    clearTimeout(debounce[key]);
    debounce[key] = setTimeout(async () => {
      try {
        const r = await jpost('api/controls.php', obj);
        if (r.ok) setCtrlMsg('Applied ' + key, 'ok');
        else setCtrlMsg('Failed: ' + (r.error || key), 'bad');
      } catch (e) { setCtrlMsg('Camera unreachable', 'bad'); }
    }, 180);
  }

  function applySettingsToUI(st) {
    for (const s of SLIDERS) {
      if (st[s.key] === undefined) continue;
      const el = $('s-' + s.key), v = $('v-' + s.key);
      if (el) el.value = st[s.key];
      if (v) v.textContent = st[s.key];
    }
    if (st.wb !== undefined) $('wb').value = st.wb;
    if (st.resolution !== undefined) $('resolution').value = st.resolution;
    document.querySelectorAll('input[type=checkbox][data-key]').forEach(cb => {
      if (st[cb.dataset.key] !== undefined) cb.checked = !!st[cb.dataset.key];
    });
  }

  function wireControls() {
    // sliders
    document.querySelectorAll('#sliders input[type=range]').forEach(el => {
      el.addEventListener('input', () => { $('v-' + el.dataset.key).textContent = el.value; });
      el.addEventListener('change', () => onControlChange(el.dataset.key, parseInt(el.value, 10)));
    });
    // selects
    ['wb', 'resolution'].forEach(id => {
      $(id).addEventListener('change', (e) => onControlChange(id, e.target.value));
    });
    // toggles
    document.querySelectorAll('input[type=checkbox][data-key]').forEach(cb => {
      cb.addEventListener('change', () => onControlChange(cb.dataset.key, cb.checked));
    });
    $('btn-defaults').onclick = async () => {
      try {
        const r = await jget('api/controls.php?defaults=1');
        if (r.ok && r.defaults) {
          const post = await jpost('api/controls.php', r.defaults);
          if (post.ok) { applySettingsToUI(post.settings); setCtrlMsg('Defaults restored', 'ok'); }
        }
      } catch (e) { setCtrlMsg('Camera unreachable', 'bad'); }
    };
  }

  async function initControls() {
    buildSliders();
    wireControls();
    try {
      const r = await jget('api/controls.php');
      if (r.ok && r.settings) applySettingsToUI(r.settings);
    } catch (e) { setCtrlMsg('Camera controls offline', 'bad'); }
  }

  // ---- boot -----------------------------------------------------------------
  initFeed();
  initControls();
  pollStatus();
  setInterval(pollStatus, 1500);
})();

"""Console configuration.

Defaults live here; anything in /etc/rdk-console.json overrides them, so the
token or camera address can change without editing code on the board.
"""

import json
import os

OVERRIDE_FILE = "/etc/rdk-console.json"

# Camera candidates, tried in order - covers LAN (router), a direct RJ45 cable
# and the last-known address.  See SAM9X75-RDK_MD/networking-dual-mode.md.
# The board now has a static address in the camera's own /24, so the camera's IP
# is the primary path in *both* LAN and direct-cable mode - try it first.  The
# other two are kept as fallbacks (mDNS if avahi is ever added, and the
# 10.42.0.x direct-link scheme); each dead candidate costs PROBE_TIMEOUT.
CAMERA_HOSTS = ["192.168.0.38", "pic64cam.local", "10.42.0.1"]
CAMERA_PORT = 80
PROBE_TIMEOUT = 1.5

# Shared secret for the login-less LAN endpoints on the PIC64 board
# (feed.php / snapshot.php / control_api.php).
LAN_TOKEN = "CHANGE_ME_LAN_TOKEN"
FEED_PATH = "/feed.php"
SNAPSHOT_PATH = "/snapshot.php"
CONTROL_PATH = "/control_api.php"

# 'fill' asks kmssink for a render rectangle larger than the CRTC (a 4:3 feed
# becomes 960x720 at x=-120) so DRM clips it and the middle of the frame covers
# all 720x720, at no CPU cost.
#
# !! Currently INERT !!  The panel driver reports the wrong physical size
# (154x86 mm for a square 720x720 panel), so kmssink squeezes every frame's
# width to ~3/5 and ignores the render rectangle - verified by reading
# /sys/kernel/debug/dri/1/state.  The video is letterboxed with bars left and
# right until the kernel carries
# linux-drivers/display/patches/05_panel-waveshare-dsi_physical_size.py,
# after which this setting starts working as described.
# 'fit' keeps the whole frame and letterboxes deliberately.
CAMERA_FIT = "fill"
# The feed's aspect is read from the camera's control API at runtime; this is
# the fallback used before that call succeeds (640x480 -> 4/3).
CAMERA_SRC_ASPECT = "4/3"



# --- live-view latency ----------------------------------------------------
# Measured on this board: the feed arrives every ~142 ms (7 fps), jpegdec costs
# 27 ms, and a software convert+scale to 720x720 costs another 130 ms - which
# makes the pipeline slower than the producer, so frames pile up and the delay
# grows the longer you watch.
#
# CAMERA_PLANE_ID points kmssink at the XLCDC high-end overlay plane, which
# takes jpegdec's I420 natively and scales in hardware (~123 ms/frame, no
# conversion at all).  It only negotiates when the CRTC is *already* configured,
# which is true in the console's flow (it drops DRM master but leaves the mode
# set) - hence CAMERA_FORCE_MODESET = False when a plane is used.
# Set CAMERA_PLANE_ID = 0 to fall back to software convert+scale.
CAMERA_PLANE_ID = 43
CAMERA_FORCE_MODESET = False
CAMERA_QUEUE = 2                # leaky queue depth: keep only newest frames
# Software-fallback output size/format (measured best: BGRx 640x640, 217 ms).
CAMERA_SW_SIZE = 640
CAMERA_SW_FORMAT = "BGRx"

# Touch backend: "i2c" polls the GT9271 directly (the panel's INT line never
# fires on this board, so the kernel driver emits no events - see
# SAM9X75-RDK_MD/phase4-console-app.md §5).  "evdev" uses /dev/input/eventN and
# is the right choice once the interrupt is fixed in the DT overlay.
TOUCH_BACKEND = "i2c"

# Touch orientation, set from touchtest.py's verdict.
TOUCH_SWAP_XY = False
TOUCH_INVERT_X = False
TOUCH_INVERT_Y = False

# Panel alignment.  This panel places the framebuffer ~50 px right of the glass.
# PANEL_H_SHIFT moves the active window earlier in the line (sync+back porch ->
# front porch) which is the proper fix and keeps all 720 columns; measured with
# `calib.py --sweep`.  If the tuned mode is ever rejected, set it to 0 and use
# X_OFFSET/Y_OFFSET instead, which shifts what we draw and gives up that many
# pixels at one edge.
PANEL_H_SHIFT = 50
PANEL_V_SHIFT = 0
X_OFFSET = 0
Y_OFFSET = 0

STATE_FILE = "/var/lib/rdk-console/state.json"

# Sliders exposed on the settings page; the PIC64 API takes 0..100.
CONTROLS = [
    ("Brightness", "brightness"),
    ("Contrast", "contrast"),
    ("Saturation", "saturation"),
    ("Sharpness", "sharpness"),
]
CONTROL_MIN = 0
CONTROL_MAX = 100

STATUS_PERIOD = 10.0        # seconds between status-line refreshes
CAMERA_RETRY = 20.0         # seconds between camera reachability probes


def load():
    """Return this module's settings as a dict, with overrides applied."""
    cfg = {k: v for k, v in globals().items()
           if k.isupper() and not k.startswith("_")}
    try:
        with open(OVERRIDE_FILE) as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def read_state():
    try:
        with open(STATE_FILE) as f:
            s = json.load(f)
        if isinstance(s, dict):
            return s
    except (OSError, ValueError):
        pass
    return {}


def write_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, STATE_FILE)
    except OSError:
        pass

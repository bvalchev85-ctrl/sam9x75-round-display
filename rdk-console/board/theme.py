"""Colours and geometry for the round console, taken from the design mockup.

Source of truth for the look: preview/round-menu-720.html (rendered to
menu720.png).  The CSS values are transcribed here so the on-glass UI matches
the mockup rather than drifting from it.
"""

W = H = 720
CX = CY = 360.0

# ---- background -------------------------------------------------------
# CSS: radial-gradient(circle at 50% 42%, #123033 0, #0b1a1e 42%,
#      #05090b 72%, #000 100%) - farthest-corner radius from (360, 302.4).
BG_CENTRE = (360.0, 302.4)
BG_RADIUS = 551.0
BG_STOPS = [
    (0.00, "#123033", 1.0),
    (0.42, "#0b1a1e", 1.0),
    (0.72, "#05090b", 1.0),
    (1.00, "#000000", 1.0),
]

# The mockup's blurred conic "sweep" (from 210deg, rgba(214,160,72,.22)).
# cairo has neither conic gradients nor a blur, so it is approximated by a
# soft radial glow in the lower-left where that wedge lands.
SWEEP_CENTRE = (150.0, 565.0)
SWEEP_RADIUS = 330.0
SWEEP_COLOUR = (214 / 255.0, 160 / 255.0, 72 / 255.0)
SWEEP_ALPHA = 0.22

# ---- rings ------------------------------------------------------------
RING_DASHED = "#96c8cd"          # rgba(150,200,205,.16)
RING_DASHED_ALPHA = 0.16
RING_ACCENT = "#c4963c"          # rgba(196,150,60,.45)
RING_ACCENT_ALPHA = 0.45
RING_R1 = 320.0                  # 640px box
RING_R2 = 250.0                  # 500px box
RING_R3 = 180.0                  # 360px box, solid accent
RING_DASH = [4.0, 7.0]

# ---- status line ------------------------------------------------------
STATUS_COLOUR = "#93a5a8"
STATUS_SIZE = 19.0
STATUS_BASELINE = 96.0
STATUS_TRACKING = 2.7            # .14em at 19px
STATUS_FONT = "DejaVu Sans Mono"
BARS_COLOUR = "#34c9b8"
BARS_HEIGHTS = [5.0, 8.0, 11.0, 14.0]
BARS_WIDTH = 3.0
BARS_GAP = 2.0
BARS_TEXT_GAP = 10.0

# ---- centre -----------------------------------------------------------
CENTRE_GLOW = "#3ac4dc"          # rgba(58,196,220,.16)
CENTRE_GLOW_ALPHA = 0.16
CENTRE_GLOW_RADIUS = 125.0
CENTRE_ICON = 188.0

# ---- side icons -------------------------------------------------------
SIDE_ICON = 86.0
SIDE_LEFT_CX = 161.0             # left:118px + 86/2
SIDE_RIGHT_CX = 559.0            # right:118px - 86/2
SIDE_CY = 360.0
SIDE_ALPHA = 0.62

# ---- label + dots -----------------------------------------------------
LABEL_COLOUR = "#eaf3f4"
LABEL_SIZE = 30.0
LABEL_BASELINE = 566.0
DOT_Y = 604.0
DOT_R = 4.0
DOT_ACTIVE_W = 22.0
DOT_GAP = 12.0
DOT_OFF = "#3a4a4e"
DOT_ON = "#34c9b8"

FONT = "DejaVu Sans"

# ---- accents per screen ----------------------------------------------
ACCENT_CAMERA = "#4bd3e8"
ACCENT_SECURITY = "#9b7fe0"
ACCENT_SETTINGS = "#8f7fd8"

# Semantic colours for the security screen.
ARMED = "#ff6b57"
DISARMED = "#34c9b8"
ALERT = "#ffb03a"
DIM = "#7c8f93"

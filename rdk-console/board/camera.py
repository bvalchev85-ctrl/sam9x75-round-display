"""PIC64 camera: reachability probe, live view, and the control API.

The live view is a `gst-launch-1.0` pipeline ending in kmssink, because nothing
in this image can decode MJPEG from Python at a useful rate (no compiler, no
numpy, ARM926 with no FPU).  gst needs to be DRM master to modeset, so the
console drops master for the duration and takes it back afterwards.
"""

import email.utils
import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request


class Camera:
    def __init__(self, cfg):
        self.cfg = cfg
        self.host = None
        self._last_probe = 0.0
        self.proc = None
        self.last_resolution = None

    # ---- reachability ----------------------------------------------------
    def probe(self, force=False):
        """Find the first camera candidate that accepts a TCP connection."""
        now = time.monotonic()
        if not force and self.host and (now - self._last_probe) < 30.0:
            return self.host
        if not force and (now - self._last_probe) < self.cfg["CAMERA_RETRY"]:
            return self.host
        self._last_probe = now
        for host in self.cfg["CAMERA_HOSTS"]:
            try:
                s = socket.create_connection((host, self.cfg["CAMERA_PORT"]),
                                             self.cfg["PROBE_TIMEOUT"])
                s.close()
                self.host = host
                return host
            except OSError:
                continue
        self.host = None
        return None

    def url(self, path, extra=""):
        return "http://%s:%d%s?token=%s%s" % (
            self.host, self.cfg["CAMERA_PORT"], path,
            self.cfg["LAN_TOKEN"], extra)

    # ---- control API -----------------------------------------------------
    def get_settings(self, timeout=4.0):
        if not self.host:
            return None
        try:
            with urllib.request.urlopen(self.url(self.cfg["CONTROL_PATH"]),
                                        timeout=timeout) as r:
                data = json.loads(r.read().decode())
            if data.get("ok"):
                got = data.get("settings") or {}
                if got.get("resolution"):
                    self.last_resolution = got["resolution"]
                return got
        except (OSError, ValueError, urllib.error.URLError):
            pass
        return None

    def set_settings(self, values, timeout=5.0):
        """POST only the keys we changed - a full POST would clobber the rest."""
        if not self.host:
            return None
        body = json.dumps(values).encode()
        req = urllib.request.Request(
            self.url(self.cfg["CONTROL_PATH"]), data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode())
            if data.get("ok"):
                got = data.get("settings") or {}
                if got.get("resolution"):
                    self.last_resolution = got["resolution"]
                return got
        except (OSError, ValueError, urllib.error.URLError):
            pass
        return None

    def server_time(self, timeout=4.0):
        """UTC datetime from the camera server's HTTP Date header, or None.

        This board has no RTC and the image has no ntpd - only busybox rdate,
        which speaks RFC-868 (TCP/37) that nothing on this LAN serves.  The
        PIC64 webcam does keep real time and stamps every HTTP response, so its
        Date header is the cheapest correct source and needs no internet.
        """
        if not self.host:
            return None
        try:
            with urllib.request.urlopen(self.url(self.cfg["CONTROL_PATH"]),
                                        timeout=timeout) as r:
                date = r.headers.get("Date")
                r.read(1)
        except (OSError, ValueError, urllib.error.URLError):
            return None
        if not date:
            return None
        try:
            return email.utils.parsedate_to_datetime(date)
        except (TypeError, ValueError):
            return None

    # ---- live view -------------------------------------------------------
    def pipeline(self, width, height):
        """Lowest-latency MJPEG path this SoC can manage.

        Measured on the board (50 frames each): the PIC64 feed arrives every
        142 ms (~7 fps), jpegdec adds 27 ms, and a *software* upscale to
        720x720 added 130 ms - making the pipeline slower than the producer, so
        frames queued and the delay grew without bound.

        The XLCDC's high-end overlay plane (43 here) accepts I420/YU12 natively
        and has a hardware scaler, so jpegdec output goes straight to it: no
        videoconvert, no videoscale, 130 ms/frame saved.  A leaky queue keeps
        only the newest frame so latency stays bounded even when the decoder
        falls behind, and sync=false stops the sink waiting on timestamps.
        """
        feed = self.url(self.cfg["FEED_PATH"])
        plane = int(self.cfg.get("CAMERA_PLANE_ID") or 0)
        depth = int(self.cfg.get("CAMERA_QUEUE", 2))
        fill = self.cfg.get("CAMERA_FIT") == "fill"
        cmd = [
            "gst-launch-1.0", "-q",
            "souphttpsrc", "location=" + feed, "is-live=true",
            "timeout=5", "retries=2",
            "!", "multipartdemux",
            "!", "image/jpeg",
            "!", "queue", "leaky=downstream",
            "max-size-buffers=%d" % depth,
            "max-size-time=0", "max-size-bytes=0",
            "!", "jpegdec",
        ]

        if not plane:
            # No YUV-capable plane: convert+scale in software with the cheapest
            # filter (nearest, method=0).  Measured per frame at 640x640:
            # BGRx 217 ms, RGB16 298 ms, default bilinear 720x720 298 ms.
            sz = int(self.cfg.get("CAMERA_SW_SIZE") or min(width, height))
            fmt = self.cfg.get("CAMERA_SW_FORMAT") or "BGRx"
            cmd += ["!", "videoconvertscale", "method=0",
                    "!", "video/x-raw,format=%s,width=%d,height=%d"
                    % (fmt, sz, sz)]
        modeset = self.cfg.get("CAMERA_FORCE_MODESET")
        if modeset is None:
            modeset = not plane
        cmd += ["!", "kmssink", "driver-name=atmel-hlcdc",
                "force-modesetting=%s" % ("true" if modeset else "false"),
                "sync=false"]
        if plane:
            cmd.append("plane-id=%d" % plane)
        if fill:
            rect = self.render_rect(width, height)
            if rect:
                cmd.append("render-rectangle=%s" % rect)
        return cmd

    def render_rect(self, width, height):
        """kmssink render rectangle that fills a square panel, uncropped sides.

        kmssink always preserves the display aspect ratio, and this build has
        neither videocrop nor capssetter, so a 4:3 feed on a 1:1 panel is
        letterboxed with black bars left and right.

        The trick: ask for a destination rectangle that is *larger* than the
        CRTC and let DRM clip it.  A 640x480 feed scaled to 960x720 at x=-120
        keeps its true proportions and the plane shows the middle 720x720 - a
        centre crop that fills the glass, with the hardware scaler still doing
        all the work.  Returns None when nothing is known or no crop is needed.
        """
        res = str(self.last_resolution or "")
        try:
            sw, sh = (int(v) for v in res.lower().split("x", 1))
        except (TypeError, ValueError):
            # Not asked the camera yet - fall back to the configured aspect,
            # otherwise the very first camera view of a session would be
            # letterboxed (which is exactly what used to happen).
            try:
                a, b = str(self.cfg.get("CAMERA_SRC_ASPECT") or "4/3").split("/")
                sw, sh = int(a), int(b)
            except (TypeError, ValueError):
                return None
        if sw <= 0 or sh <= 0:
            return None
        if sw * height == sh * width:
            return None                       # already the panel's aspect
        if sw * height > sh * width:          # source wider - overscan width
            w = int(round(height * sw / float(sh)))
            h = height
        else:                                 # source taller - overscan height
            w = width
            h = int(round(width * sh / float(sw)))
        x = (width - w) // 2
        y = (height - h) // 2
        return "<%d,%d,%d,%d>" % (x, y, w, h)

    def start(self, display, log="/tmp/rdk-camera.log"):
        """Hand the display to gst and start streaming.  True if it launched."""
        if not self.host:
            return False
        if self.last_resolution is None:
            # One cheap GET so render_rect() knows the real feed aspect rather
            # than relying on the fallback.
            self.get_settings(timeout=2.5)
        self.stop(display, retake=False)
        display.drop_master()
        try:
            fh = open(log, "wb")
        except OSError:
            fh = subprocess.DEVNULL
        try:
            self.proc = subprocess.Popen(
                self.pipeline(display.width, display.height),
                stdout=fh, stderr=fh, stdin=subprocess.DEVNULL,
                start_new_session=True)
        except OSError:
            self.proc = None
            display.set_master()
            return False
        return True

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self, display, retake=True):
        """Kill the pipeline and take the display back."""
        if self.proc is not None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except OSError:
                try:
                    self.proc.terminate()
                except OSError:
                    pass
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                except OSError:
                    pass
                try:
                    self.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            self.proc = None
        if retake:
            # busybox pkill does not match 'gst-launch-1.0', so anything still
            # holding DRM master is cleared by PID via /dev/dri fuser instead.
            _free_drm(display)
            try:
                display.set_master()
            except OSError:
                time.sleep(0.4)
                display.set_master()


def _free_drm(display, node="/dev/dri/card1"):
    """Kill any leftover process holding DRM master on the card."""
    try:
        out = subprocess.run(["fuser", node], capture_output=True,
                             timeout=4).stdout.decode()
    except (OSError, subprocess.SubprocessError):
        return
    me = os.getpid()
    for tok in out.split():
        try:
            pid = int(tok.strip().rstrip("celmrtF"))
        except ValueError:
            continue
        if pid != me:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


if __name__ == "__main__":
    # Exercise the real handoff: the display keeps the mode configured while
    # DRM master is dropped, which is the only state where kmssink can
    # negotiate I420 onto the overlay plane.
    import sys

    import config as C
    from kms import Display

    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    cfg = C.load()
    cam = Camera(cfg)
    host = cam.probe(force=True)
    print("camera host: %s" % host)
    d = Display(h_shift=cfg["PANEL_H_SHIFT"], v_shift=cfg["PANEL_V_SHIFT"])
    try:
        print("pipeline:")
        print("  " + " ".join(cam.pipeline(d.width, d.height)))
        if not host:
            raise SystemExit("camera unreachable")
        if not cam.start(d):
            raise SystemExit("failed to launch gst")
        print("streaming for %.0fs ..." % secs, flush=True)
        time.sleep(secs)
        print("alive after %.0fs: %s" % (secs, cam.alive()))
    finally:
        cam.stop(d)
        d.close()
    try:
        with open("/tmp/rdk-camera.log") as f:
            out = f.read().strip()
        print("--- gst log ---")
        print(out[:1200] if out else "(empty)")
    except OSError:
        pass

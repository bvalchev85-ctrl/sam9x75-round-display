# RDK ↔ PIC64 camera — dual-mode networking

The RDK display must reach the PIC64_WebCam MJPEG stream in **two** deployment modes:

1. **LAN mode** — both on a home/office network: DHCP server, gateway, DNS. Camera at
   `192.168.0.38` today.
2. **Direct mode** — a single RJ45 cable straight from the RDK to the PIC64. **No DHCP,
   no DNS, no gateway.** Just two NICs back-to-back.

Goal: **one configuration, no manual switching.** Plug either way and the camera app finds
the stream.

## Strategy — address by NAME, not a fixed IP

Use **mDNS/zeroconf** so the camera answers to a stable name in both modes, and give both
NICs a **DHCP-with-link-local fallback** so they always get an address.

- **Primary address: `pic64cam.local`** (mDNS, resolved by avahi). Works with a router
  *and* over a bare cable — mDNS is link-local multicast, it needs no DNS server.
- **DHCP + IPv4LL fallback** on each NIC: with a router → normal DHCP lease (LAN). With a
  bare cable → no DHCP, both self-assign `169.254.x.x` (RFC-3927 link-local) and mDNS still
  resolves `pic64cam.local` across the link.
- **Auto-MDIX**: both PHYs auto-swap TX/RX, so an ordinary straight patch cable works for
  the direct link — **no crossover cable needed.**
- **Static direct-link subnet** as belt-and-suspenders (in case mDNS is ever disabled):
  camera `10.42.0.1/24`, RDK `10.42.0.2/24` on the direct profile.

## App resolution order (both the preview and the EGT app)

Try candidates in order, use the first that streams; fall back to the on-screen test
pattern only when all fail:

1. `http://pic64cam.local[:port]/stream.php`   ← mDNS, works in LAN **and** direct
2. `http://10.42.0.1[:port]/stream.php`        ← direct-cable static fallback
3. `http://192.168.0.38[:port]/stream.php`     ← last-known LAN IP fallback

(The preview's Settings has **Auto / LAN / Direct** chips that reorder this list; `Auto`
is the default and covers both.)

## RDK side (Buildroot image) — to add when we resume the build

- **Packages:** `BR2_PACKAGE_AVAHI` + `BR2_PACKAGE_AVAHI_DAEMON` (mDNS responder/resolver).
  For transparent `getaddrinfo("pic64cam.local")` from GStreamer/curl/the EGT app, either
  add glibc **nss-mdns** (nsswitch `hosts: ... mdns4_minimal [NOTFOUND=return] dns ...`), or
  have the app resolve via `avahi-resolve-host-name -4 pic64cam.local` then dial the IP.
  (Simplest for the EGT app: resolve-then-connect via avahi, avoids the NSS dependency.)
- **Interface config (systemd-networkd)** — one profile that does both:
  ```
  # /etc/systemd/network/10-eth.network
  [Match]
  Name=eth0
  [Network]
  DHCP=ipv4
  LinkLocalAddressing=ipv4      # 169.254.x.x when no DHCP (direct cable)
  MulticastDNS=yes
  [DHCPv4]
  RouteMetric=100
  ```
  Optional explicit direct-link static (activated only when chosen):
  `Address=10.42.0.2/24`.
- Confirm the on-board bring-up brings `eth0` up early (before the camera app starts).

## PIC64 side (asked of the PIC64_WebCam session)

- Set the board **hostname `pic64cam`** and run **avahi-daemon** so it publishes
  `pic64cam.local` (Ubuntu usually has avahi already).
- Give its camera-facing NIC the **same DHCP + IPv4LL fallback** (+ optional static
  `10.42.0.1/24` on the direct profile) so it's reachable over a bare cable.
- Keep `stream.php` bound to all interfaces (0.0.0.0), not just the LAN IP.
- Confirm whether the stream stays **login-gated** in direct mode; if so the RDK app must
  hold a session. A **token/no-auth LAN path** would simplify the embedded client — open
  question raised with them.

## RESOLVED 2026-09-07 — a static address, not mDNS

Tested on the bench with a bare cable between the RDK and the PIC64. None of the
plan above worked, for concrete reasons:

- **No DHCP server on a bare cable**, so `udhcpc` got no lease and `eth0` ended
  up with **no IPv4 address at all** — the console showed `no camera`.
- **mDNS is not available on the RDK.** avahi was never added to the image, and
  adding it needs a Buildroot rebuild — the build VM is on the other PC. So
  `pic64cam.local` cannot resolve on the board.
- **IPv6 link-local discovery** (ping `ff02::1%eth0`, then read the neighbour
  table) would need no configuration at all and was the elegant option, but this
  busybox `ping` has **no `-6`** and no `ping6` applet.

What is deployed instead: `/etc/init.d/S40rdk-net` gives the RDK the **static
address 192.168.0.39/24**, in the camera's own /24. That satisfies the original
goal — *one configuration, no manual switching* — because it is identical on the
LAN and on a bare cable:

| | LAN (router) | direct cable to the PIC64 |
|---|---|---|
| RDK | 192.168.0.39 (static) | 192.168.0.39 (static) |
| PIC64 | 192.168.0.38 | 192.168.0.38 |
| works? | yes | yes — 0.7 ms ping, camera API answers |

`CAMERA_HOSTS` in `rdk-console/board/config.py` still tries `pic64cam.local` and
`10.42.0.1` as fallbacks, so nothing is lost if mDNS is added later.

Two side effects worth remembering:

- Killing a running `udhcpc` triggers its `deconfig` hook, which **flushes every
  address on the interface**, static ones included.
- Bringing the link down/up (re-cabling) drops manually added addresses, which is
  why this has to live in the boot script rather than being typed in once.

## Status
- Preview app: candidate resolution + Auto/LAN/Direct modes implemented (2026-09-05).
- RDK: **static 192.168.0.39 deployed and verified both ways** (2026-09-07).
- avahi/mDNS on the RDK: still not present; only needed if the camera's address
  should stop being fixed.
- Related: [[sam9x75-rdk-project]], [[pic64-webcam-project]].

"""
Wooting <-> Windows virtual desktop two-way sync.

- Windows desktop changes (Stream Deck, Win+Ctrl+arrow, Task View) -> keyboard profile
- Keyboard profile changes (Mode key, Fn+1..4)                     -> Windows desktop

Config lives in config.json next to this file. Desktop and profile numbers are
1-based there (what you see in Windows / Wootility); zero-based internally.

Talks to the keyboard the same way Wootility does (HID feature reports on the
config interface) and to Windows through VirtualDesktopAccessor.dll.
"""
import ctypes
import json
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

import hid

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
LOG_PATH = os.path.join(HERE, "sync.log")

# --- Wooting protocol (from wooting-rgb-sdk / wootility) ---------------------
WOOTING_VID = 0x31E3
WOOTING_80HE_PID = 0x1400          # alt PIDs 0x1401 / 0x1402 also exist
CFG_USAGE_PAGES = (0x1337, 0xFF55)
CMD_GET_PROFILE = 11               # GetCurrentKeyboardProfileIndex
CMD_ACTIVATE_PROFILE = 23          # ActivateProfile <0-based slot>; do NOT follow with cmd 7 (ReloadProfile0)
ONBOARD_SLOTS = 4
RESPONSE_SIZE = 2047
READ_TIMEOUT_MS = 1000

log = logging.getLogger("wds")


def setup_logging():
    h = RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=2, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    h.setFormatter(fmt)
    log.addHandler(h)
    if sys.stdout is not None:
        c = logging.StreamHandler(sys.stdout)
        c.setFormatter(fmt)
        log.addHandler(c)
    log.setLevel(logging.INFO)


class Keyboard:
    def __init__(self):
        self.dev = None
        self.multi_report = True

    def _find_path(self):
        for info in hid.enumerate(WOOTING_VID, 0):
            pid = info["product_id"]
            if (pid & 0xFFF0) != WOOTING_80HE_PID and (pid & 0xFF00) not in (0x1200, 0x1300, 0x1500):
                continue
            if info["usage_page"] in CFG_USAGE_PAGES:
                self.multi_report = info["usage_page"] == 0xFF55
                return info["path"]
        return None

    def connect(self):
        if self.dev:
            return True
        path = self._find_path()
        if not path:
            return False
        try:
            d = hid.device()
            d.open_path(path)
            d.set_nonblocking(0)
            self.dev = d
            log.info("keyboard connected (%s)", path.decode(errors="ignore") if isinstance(path, bytes) else path)
            return True
        except Exception:  # noqa: BLE001
            self.dev = None
            return False

    def close(self):
        if self.dev:
            try:
                self.dev.close()
            except Exception:  # noqa: BLE001
                pass
        self.dev = None

    def _send(self, cmd, a=0, b=0, c=0, d=0):
        """Send a command and return the matching response (header validated),
        skipping any unsolicited reports the board pushes on this interface."""
        rid = 1 if self.multi_report else 0
        magic = (0xD1, 0xDA) if self.multi_report else (0xD0, 0xDA)
        # verified against Wootility on the 80HE: d1 da <cmd> <arg> 00 00 00
        buf = bytes([rid, magic[0], magic[1], cmd, a, b, c, d])
        # drain anything already queued so we never read a stale packet
        for _ in range(32):  # bounded: the 80HE streams reports on this interface
            if not self.dev.read(RESPONSE_SIZE, 1):
                break
        n = self.dev.send_feature_report(buf)
        if n != len(buf):
            raise IOError(f"feature report short write {n}")
        deadline = time.monotonic() + READ_TIMEOUT_MS / 1000.0
        while time.monotonic() < deadline:
            resp = self.dev.read(RESPONSE_SIZE, 50)
            if not resp:
                continue
            body = resp[1:] if self.multi_report else resp
            # response: magic(2, little-endian D1DA/D0DA) command(1) ?(1) length(1) data...
            if len(body) >= 5 and body[0] == magic[0] and body[1] == magic[1] and body[2] == cmd:
                return body
        return None

    def get_profile(self):
        """0-based active profile index, or None."""
        if not self.connect():
            return None
        try:
            body = self._send(CMD_GET_PROFILE)
            if not body:
                return None
            off = 5 + (1 if self.multi_report else 0)
            if len(body) > off and 0 <= body[off] < ONBOARD_SLOTS:
                return body[off]
            log.debug("odd profile response: %s", list(body[:12]))
            return None
        except Exception as e:  # noqa: BLE001
            log.warning("get_profile failed: %s", e)
            self.close()
            return None

    def set_profile(self, idx):
        if not self.connect():
            return False
        try:
            self._send(CMD_ACTIVATE_PROFILE, idx)   # exactly what Wootility sends
            time.sleep(0.3)
            got = self.get_profile()
            if got != idx:
                log.warning("set_profile(%d): board reports %s afterwards", idx + 1, None if got is None else got + 1)
                return False
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("set_profile failed: %s", e)
            self.close()
            return False


class Desktops:
    def __init__(self):
        self.lib = ctypes.WinDLL(os.path.join(HERE, "VirtualDesktopAccessor.dll"))
        self.lib.GetCurrentDesktopNumber.restype = ctypes.c_int
        self.lib.GoToDesktopNumber.restype = ctypes.c_int
        self.lib.GoToDesktopNumber.argtypes = [ctypes.c_int]
        self.lib.GetDesktopCount.restype = ctypes.c_int

    def current(self):
        n = self.lib.GetCurrentDesktopNumber()
        return n if n >= 0 else None

    def go(self, n):
        return self.lib.GoToDesktopNumber(n) == 0

    def count(self):
        return self.lib.GetDesktopCount()


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    # {"1": 1, "2": 4, "3": 2}  desktop -> profile, both 1-based
    d2p = {int(k) - 1: int(v) - 1 for k, v in cfg["desktop_to_profile"].items()}
    p2d = {}
    for d, p in d2p.items():
        p2d.setdefault(p, d)  # first desktop wins if a profile is reused
    return cfg, d2p, p2d


def main():
    setup_logging()
    cfg, d2p, p2d = load_config()
    poll = cfg.get("poll_ms", 250) / 1000.0
    kb = Keyboard()
    vd = Desktops()
    log.info("started. desktops=%d map(desktop->profile)=%s", vd.count(), {k + 1: v + 1 for k, v in d2p.items()})

    last_d = vd.current()
    last_p = kb.get_profile()
    log.info("initial desktop=%s profile=%s", None if last_d is None else last_d + 1,
             None if last_p is None else last_p + 1)

    # On start, make the keyboard match the desktop.
    if last_d is not None and last_d in d2p and last_p != d2p[last_d]:
        if kb.set_profile(d2p[last_d]):
            last_p = d2p[last_d]
            log.info("startup: keyboard -> profile %d", last_p + 1)

    settle_kb_until = 0.0   # ignore keyboard readings briefly after WE changed the keyboard
    settle_vd_until = 0.0   # ignore desktop readings briefly after WE changed the desktop
    pending_p = None        # debounce: keyboard change must be seen twice in a row
    kb_down = False
    while True:
        time.sleep(poll)
        now = time.monotonic()
        d = vd.current()
        p = kb.get_profile()

        if p is None:
            if not kb_down:
                log.info("keyboard unavailable (Wootility open?) - pausing keyboard side")
                kb_down = True
            time.sleep(1.5)
            continue
        if kb_down:
            kb_down = False
            last_p, last_d, pending_p = p, d, None
            log.info("keyboard back. re-baselined desktop=%s profile=%s", d + 1 if d is not None else None, p + 1)
            continue

        # --- desktop changed by the user (deck, hotkey, task view) -> follow with keyboard
        if d is not None and d != last_d:
            if now < settle_vd_until:
                last_d = d          # our own desktop change landing; don't echo it
            else:
                last_d = d
                want = d2p.get(d)
                log.info("desktop -> %d", d + 1)
                if want is not None and want != p:
                    if kb.set_profile(want):
                        last_p = want
                        settle_kb_until = now + 0.8
                        log.info("  keyboard -> profile %d", want + 1)
                continue

        # --- keyboard changed by the user (Mode / Fn+#) -> follow with desktop
        if p != last_p:
            if now < settle_kb_until:
                last_p = p          # our own keyboard change landing; don't echo it
                continue
            if p != pending_p:
                pending_p = p
                continue
            pending_p = None
            last_p = p
            want = p2d.get(p)
            log.info("keyboard -> profile %d", p + 1)
            if want is not None and want != d:
                if vd.go(want):
                    last_d = want
                    settle_vd_until = now + 0.8
                    log.info("  desktop -> %d", want + 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:  # noqa: BLE001
        log.exception("fatal")
        raise

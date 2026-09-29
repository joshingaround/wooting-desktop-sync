"""Foreground test: python test_profile.py 2   -> tries to switch the board to slot 2 and reports back."""
import sys, time, logging
import wooting_desktop_sync as w  # noqa: E402
logging.basicConfig(level=logging.INFO, format="%(message)s")
kb = w.Keyboard()
if not kb.connect():
    sys.exit("keyboard not found (is a Wootility tab open?)")
print("before:", kb.get_profile() + 1)
idx = int(sys.argv[1]) - 1
kb._send(w.CMD_ACTIVATE_PROFILE, idx); time.sleep(0.3)
print("after activate:", kb.get_profile() + 1)
time.sleep(1.0)
print("1s later:", kb.get_profile() + 1)

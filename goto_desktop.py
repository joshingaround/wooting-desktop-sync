"""Jump straight to virtual desktop N (1-based). For Stream Deck 'Open' actions:
    pythonw.exe C:\\path\\to\\wooting-desktop-sync\\goto_desktop.py 2
The sync service sees the desktop change and flips the keyboard profile."""
import ctypes, os, sys

n = int(sys.argv[1]) - 1
lib = ctypes.WinDLL(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VirtualDesktopAccessor.dll"))
lib.GoToDesktopNumber.argtypes = [ctypes.c_int]
sys.exit(0 if lib.GoToDesktopNumber(n) == 0 else 1)

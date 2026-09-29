# Wooting Desktop Sync

Two-way link between **Windows virtual desktops** and **Wooting keyboard profiles**.

- Switch desktops (Stream Deck, `Win+Ctrl+←/→`, Task View) → the keyboard changes profile
- Press **Mode** or **Fn+1–4** on the keyboard → Windows changes desktop

One desktop per context, one lighting/actuation profile per desktop, and they stay in step no matter which side you touch.

Built and tested on a **Wooting 80HE** (Windows 11, Wootility 5.x). Other Wooting boards on the same firmware family should work — see [Compatibility](#compatibility).

## Why

Wootility can link a profile to a *focused app*, but it has no idea about virtual desktops, and nothing on the PC side can press `Fn` for you — that key never leaves the keyboard's firmware. This tool talks to the board the same way Wootility does (a HID feature report on the config interface) and to Windows through [VirtualDesktopAccessor](https://github.com/Ciantic/VirtualDesktopAccessor), so a single background process keeps both sides in sync.

## Install

Requirements: Windows 10/11, Python 3.10+, PowerShell 7.

```powershell
git clone https://github.com/joshingaround/wooting-desktop-sync
cd wooting-desktop-sync
pwsh -File .\install.ps1
```

The installer installs `hidapi`, downloads `VirtualDesktopAccessor.dll`, copies `config.example.json` to `config.json`, and registers a hidden Task Scheduler job (**Wooting Desktop Sync**) that starts at logon and restarts itself if it dies.

## Configure

`config.json` — desktop number → profile slot, both 1-based exactly as Windows and Wootility show them:

```json
{
  "desktop_to_profile": { "1": 1, "2": 2, "3": 3 },
  "poll_ms": 250
}
```

Slots you don't list are free-floating (a gaming profile, say): selecting one on the board leaves the desktop alone.

After editing:

```powershell
Stop-ScheduledTask 'Wooting Desktop Sync'; Start-ScheduledTask 'Wooting Desktop Sync'
```

## Stream Deck

Stream Deck's built-in desktop switching is relative (it replays `Win+Ctrl+arrow`), so it drifts the moment you switch by hand. Use `goto_desktop.py` for absolute jumps instead — a **System → Open** action:

- App: `pythonw.exe` (full path from `(Get-Command pythonw).Source`)
- Arguments: `C:\path\to\wooting-desktop-sync\goto_desktop.py 2`

The sync service sees the desktop change and flips the keyboard.

## Troubleshooting

- `Get-Content .\sync.log -Tail 8` shows every switch and why.
- `python .\test_profile.py 2` switches the board to slot 2 in the foreground and prints what it read back.
- While a Wootility tab has the keyboard paired, the service can't open it. It logs `keyboard unavailable`, waits, and re-baselines when the board comes back — close the tab and it resumes.

## Compatibility

Tested: **80HE**. The code matches any Wooting VID `0x31E3` device whose config interface is on usage page `0x1337` or `0xFF55` (60HE/60HE+/Two HE/UwU families), but only the 80HE has been verified. If it works on yours, open an issue and say so.

## Protocol notes

Recorded here because none of it was documented anywhere when this was built.

- Feature report on the config interface, report ID 1: `01 d1 da <cmd> <arg> 00 00 00`. The argument is the byte **immediately after** the command — the byte order in the `wooting-profile-switcher` crate is wrong for this firmware.
- Activate profile: cmd `0x17` (23), arg = 0-based slot. That alone switches the board; no reload or RGB refresh needed.
- Get active profile: cmd `0x0B` (11); the index is at offset 6 of the response body.
- Don't send cmd `7` after activating — on this firmware it's "reload profile 0" and snaps the board back to slot 1.
- The board streams unsolicited reports on the same interface, so always check that a response header echoes your command before trusting it.
- Captured by hooking `HIDDevice.prototype.sendFeatureReport` in a wootility.io tab and switching profiles.

## Support

If this saved you an afternoon, [buy me a coffee](https://ko-fi.com/joshfriesen). One time or monthly, whatever you feel like.

## License

MIT. `VirtualDesktopAccessor.dll` is © Ciantic, MIT, downloaded from its own releases and not redistributed here.

# GoFlight MCP Pro for MSFS 2024

A small bridge that makes the GoFlight MCP Pro work with Microsoft Flight Simulator 2024 (and 2020), with full support for the PMDG 737 through its official SDK.

GoFlight is gone, their drivers are hard to find, and the paid tools I tried left the MCP Pro displays dark with the PMDG 737 in MSFS 2024. So I wrote this. It talks to the panel directly over USB and to the sim over SimConnect. No GoFlight drivers, no extra Python packages.

Tested with MSFS 2024 (Microsoft Store), PMDG 737-800 v4.0.63 and an MCP Pro (USB id 09F3:0064) on Windows 11.

## What it does

With the PMDG 737:

- All six displays show the real MCP values: course, IAS/Mach, heading, altitude, V/S. The IAS and V/S windows blank when the aircraft blanks them, and the flashing 8 (overspeed) or A (underspeed) shows up like in the real thing.
- All annunciator LEDs: CMD A/B, CWS A/B, LNAV, VNAV, HDG SEL, APP, ALT HLD, V/S, LVL CHG, SPEED, N1, VOR LOC, A/T ARM and both F/D.
- Every MCP button, including ALT INTV, SPD INTV and C/O.
- F/D left and right, A/T ARM and the A/P disengage bar follow the physical switches.
- Knobs set the exact value in the aircraft, usually within 50 ms. Altitude moves 100 ft per click and V/S uses the 737 steps (50 fpm below 1000, 100 above). Turning faster moves faster, the panel handles that.
- Pushing the HEADING knob cycles the bank angle limit (10 to 30).
- MCP off when the aircraft has no power, panel dark when the sim is not running.

With any other aircraft there is a basic generic mode using the default MSFS autopilot: heading, altitude, speed/Mach, V/S, both courses, AP master, HDG, ALT, APP, NAV, V/S, FLC, speed hold, N1, F/D and autothrottle arm.

It also starts by itself with MSFS (through `exe.xml`), runs minimized, and closes when you quit the sim.

While it runs there is a live view at http://localhost:8737 with a virtual copy of the panel, the aircraft values, everything sent to the sim and a small explorer to try events and variables. See [Live view](#live-view).

## What it doesn't do

- Only the MCP Pro. No EFIS, GF-166 or other GoFlight modules.
- PMDG 777 is not supported (different SDK). It falls back to generic mode, which the 777 mostly ignores.
- Generic mode is basic. VNAV, CWS, ALT INTV and SPD INTV do nothing there, and LNAV and VOR LOC both map to NAV hold. Aircraft with their own autopilot logic (Fenix, iFly, some of the new MSFS 2024 airliners) ignore the default events and need their own mapping. The explorer in the live view is the easiest way to find out what a given aircraft listens to.
- Windows only. No X-Plane, P3D or FSX.
- Steam installs and MSFS 2020 should work (the paths are handled) but I have only tested MSFS 2024 from the Microsoft Store.

## Requirements

- Windows 10 or 11
- [Python 3.9 or newer](https://www.python.org/downloads/), nothing else to install
- The MSFS SDK, only to get `SimConnect.dll`. In MSFS enable Developer Mode (Options, General, Developers), then use the SDK installer from the Help menu. The 2020 or 2024 SDK both work.
- For the PMDG 737, load it at least once before running the installer so its options file exists.

## Install

1. Download the repo (Code, Download ZIP) and unzip it somewhere permanent, for example `C:\GoFlightMCP`.
2. Close MSFS, plug in the MCP Pro and run:

   ```
   python install.py
   ```

   It backs up everything it touches, then:
   - copies `SimConnect.dll` from the MSFS SDK,
   - enables the PMDG 737 SDK (`EnableDataBroadcast=1` in `737_Options.ini`),
   - adds the bridge to the MSFS `exe.xml` so it starts with the sim,
   - creates a desktop shortcut.

   `python install.py --dry-run` shows what it would do without changing anything.
3. Start MSFS and load the 737. The panel comes alive when the aircraft has power.

### Manual install

If you prefer to do it by hand:

- Copy `SimConnect.dll` from `MSFS SDK\SimConnect SDK\lib\` into the project folder.
- Add this at the end of `737_Options.ini`. For MSFS 2024 from the Store it lives in `%LOCALAPPDATA%\Packages\Microsoft.Limitless_8wekyb3d8bbwe\LocalState\WASM\MSFS2024\pmdg-aircraft-738\work\`.

  ```ini
  [SDK]
  EnableDataBroadcast=1
  ```

- To start with the sim, add this block inside `<SimBase.Document>` in `exe.xml` (Store version: `%LOCALAPPDATA%\Packages\Microsoft.Limitless_8wekyb3d8bbwe\LocalCache\exe.xml`):

  ```xml
  <Launch.Addon>
    <Name>GoFlight MCP Pro</Name>
    <Disabled>False</Disabled>
    <Path>C:\path\to\python.exe</Path>
    <CommandLine>"C:\GoFlightMCP\gfmcp.py" --auto</CommandLine>
    <NewConsole>True</NewConsole>
  </Launch.Addon>
  ```

## Usage

Normally there is nothing to do, MSFS starts it. Other ways to run it:

| Command | |
|---|---|
| `GoFlight MCP.bat` or the desktop shortcut | Run it by hand, if you don't use auto start |
| `python gfmcp.py --verbose` | Log every input and every MCP change, for troubleshooting |
| `Panel test.bat` | Light test, then knobs and buttons work locally without the sim |

The last session is logged to `gfmcp.log`.

### Live view

Open http://localhost:8737 while the bridge is running. It only listens on localhost.

- **Panel**: the six displays and all LEDs exactly as they are sent to the hardware, the physical switch positions and the sim state of each switch. Buttons flash when you press them on the real panel. Clicking a button, a switch or the +/- under a display does the same as the hardware (shift click on +/- moves 10).
- **Aircraft values**: the MCP data coming from the PMDG SDK, or the default autopilot variables in generic mode. Changed values are highlighted.
- **Sent to the sim**: every event the bridge sends, with its value. The header shows the knob latency, from your last click until the sim reports the new value.
- **Explorer**: send any event by name (`AP_MASTER`, `HEADING_BUG_SET`, PMDG names like `CMD_A_SWITCH`, or a numeric id) and watch any variable, including L:vars. Handy to figure out how an unsupported aircraft works before mapping it.
- **Log**: same as the console window.
- **Test mode** (big button at the top of the page): with no aircraft loaded, the panel works on its own. Knobs change the numbers, buttons toggle their lights and switches light their LEDs, on the page and on the hardware. Nothing is sent to the sim, and it turns itself off when an aircraft gets linked.

### Settings

`config.ini`:

| Option | Default | |
|---|---|---|
| `[panel] brightness` | 15 | Display brightness, 0 to 15 |
| `[pmdg] knob_mode` | set | `set` sends exact values, `wheel` emulates the mouse wheel on the virtual MCP |
| `[pmdg] hdg_push` | bank_angle | What pushing the HEADING knob does, `bank_angle` or `none` |
| `[steps] alt` | 100 | Feet per altitude click |
| `[steps] alt_fast_threshold`, `alt_fast` | 99, 1000 | Optional extra altitude acceleration, 99 means off |
| `[web] enabled`, `port` | yes, 8737 | Live view in the browser |

## How it works

There are four parts.

**Panel (`panel.py`, `hidwin.py`).** The MCP Pro is a plain HID device, so it is opened with the Windows HID API through ctypes. One thread reads input reports (knobs, buttons, switches) and another writes displays and LEDs, each on its own handle. Only what changed gets written, plus a slow background refresh of one report every half second.

**Simulator (`simconnect.py`).** A thin ctypes wrapper around `SimConnect.dll`. With the PMDG it subscribes to the `PMDG_NG3_Data` client data area and sends PMDG control events. In generic mode it reads the standard autopilot variables and sends the standard key events.

**Live view (`web.py`, `ui.html`).** A small HTTP server inside the bridge pushes the current state to the page ten times a second. Clicks on the page are queued and run on the main loop, exactly like hardware input.

**Logic (`gfmcp.py`, `pmdg737.py`).** It detects which aircraft is loaded, maps panel events to sim events and builds what the displays should show. The PMDG data layout is computed at startup from the `PMDG_NG3_SDK.h` that ships with the aircraft, so a PMDG update that moves fields around doesn't break it. When you turn a knob the display shows your new value right away and keeps it until the sim confirms it, so it never jumps back while the sim catches up.

A few things about this panel that took some time to figure out:

- The firmware sometimes never answers a display write if it arrives while the panel is sending a knob or button report. Windows then waits 5 seconds before giving up and everything freezes. Writes here time out after 150 ms, get cancelled and are sent again.
- A broken write once left one display with brightness 0, so brightness is sent again as part of the background refresh.
- The panel runs on USB power only. With every segment and every decimal point lit at once it browns out and reports switches that nobody touched. The startup light test leaves the decimal points off.
- You can't ask the panel where the switches are. Their position arrives with the first input report, and at that point F/D and A/T ARM in the sim are lined up with the hardware.
- PMDG numbers the F/D switch positions the opposite way from what you'd expect, so the bridge clicks the virtual switch only when sim and hardware disagree.

## Troubleshooting

- **Panel stays dark.** Expected while the sim is not running or no aircraft is loaded. With the PMDG the MCP needs electrical power.
- **"PMDG 737 loaded but no SDK data"** in the log. `EnableDataBroadcast=1` is missing from `737_Options.ini`, or the aircraft is still loading.
- **A display goes dark.** It should come back within a few seconds. If not, restart the bridge.
- **Switches toggling by themselves or odd behaviour.** Use a USB port on the motherboard or a powered hub, or lower the brightness in `config.ini`.

## MCP Pro USB protocol

In case you want to drive the panel from your own code. VID 0x09F3, PID 0x0064. On Windows the outputs are feature reports (`HidD_SetFeature`):

| Report id | Content |
|---|---|
| 3, 7, 13 | Course left, heading, course right: 3 bytes of 7 segment data, bit 0x80 is the decimal point |
| 5, 9, 11 | IAS/Mach, altitude, V/S: 5 bytes of 7 segment data |
| 14 | Brightness, 0 to 15 |
| 15 | LEDs: `15, 0, bottom row, middle row, top row` |

Input is report 1, 8 bytes. Bytes 1 to 3 hold the knobs as signed 4 bit click counts since the last report (heading and course left, V/S and IAS, course right and altitude). Bytes 5 to 7 hold buttons and switches, and are only valid in reports with no knob movement. See `panel.py` for the full bit map.

## Credits

- The MCP Pro protocol was first worked out in [benrussell/GF_MCP_Pro](https://github.com/benrussell/GF_MCP_Pro), an X-Plane plugin.
- The PMDG 737 SDK belongs to PMDG Simulations and is not included. The bridge reads the header that comes with your copy of the aircraft.
- `SimConnect.dll` belongs to Microsoft and is not included. The installer copies it from your MSFS SDK.

Not affiliated with GoFlight, PMDG or Microsoft. For flight simulation use only.

## License

MIT, see [LICENSE](LICENSE).

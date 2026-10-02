"""Sets up the bridge on this PC. Everything it modifies is backed up first.

1. Copies SimConnect.dll from the MSFS SDK.
2. Enables the PMDG 737 SDK (EnableDataBroadcast=1 in 737_Options.ini).
3. Adds the bridge to the MSFS exe.xml so it starts with the sim.
4. Creates a desktop shortcut.

python install.py            install
python install.py --dry-run  only show what would be done
"""
import glob
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DRY = "--dry-run" in sys.argv
LA = os.environ.get("LOCALAPPDATA", "")
AD = os.environ.get("APPDATA", "")

# (name, folder holding exe.xml, 737_Options.ini patterns)
SIMS = [
    ("MSFS 2024 (Microsoft Store)", os.path.join(LA, r"Packages\Microsoft.Limitless_8wekyb3d8bbwe\LocalCache"),
     [os.path.join(LA, r"Packages\Microsoft.Limitless_8wekyb3d8bbwe\LocalState\WASM\MSFS2024\pmdg-aircraft-73*\work\737_Options.ini")]),
    ("MSFS 2024 (Steam)", os.path.join(AD, "Microsoft Flight Simulator 2024"),
     [os.path.join(AD, r"Microsoft Flight Simulator 2024\WASM\MSFS2024\pmdg-aircraft-73*\work\737_Options.ini")]),
    ("MSFS 2020 (Microsoft Store)", os.path.join(LA, r"Packages\Microsoft.FlightSimulator_8wekyb3d8bbwe\LocalCache"),
     [os.path.join(LA, r"Packages\Microsoft.FlightSimulator_8wekyb3d8bbwe\LocalState\packages\pmdg-aircraft-73*\work\737_Options.ini")]),
    ("MSFS 2020 (Steam)", os.path.join(AD, "Microsoft Flight Simulator"),
     [os.path.join(AD, r"Microsoft Flight Simulator\Packages\pmdg-aircraft-73*\work\737_Options.ini")]),
]

ADDON = """  <Launch.Addon>
    <Name>GoFlight MCP Pro</Name>
    <Disabled>False</Disabled>
    <Path>{python}</Path>
    <CommandLine>"{script}" --auto</CommandLine>
    <NewConsole>True</NewConsole>
  </Launch.Addon>
"""
EXE_XML = """<?xml version="1.0" encoding="Windows-1252"?>
<SimBase.Document Type="Launch" version="1,0">
  <Descr>Launch</Descr>
  <Filename>exe.xml</Filename>
  <Disabled>False</Disabled>
  <Launch.ManualLoad>False</Launch.ManualLoad>
{addon}</SimBase.Document>
"""


def say(msg):
    print(("[dry run] " if DRY else "") + msg)


def backup(path):
    dst = f"{path}.backup-goflight-{time.strftime('%Y%m%d-%H%M%S')}"
    if not DRY:
        shutil.copy2(path, dst)
    return dst


def sim_running():
    out = subprocess.run(["tasklist"], capture_output=True, text=True, errors="ignore").stdout.lower()
    return "flightsimulator" in out


def step_simconnect():
    dst = os.path.join(HERE, "SimConnect.dll")
    if os.path.exists(dst):
        say("SimConnect.dll: already here.")
        return
    roots = [os.environ.get(v) for v in ("MSFS_SDK", "MSFS2024_SDK")]
    roots += [rf"{d}:\MSFS SDK" for d in "CDEFG"] + [rf"{d}:\MSFS 2024 SDK" for d in "CDEFG"]
    for root in filter(None, roots):
        src = os.path.join(root, r"SimConnect SDK\lib\SimConnect.dll")
        if os.path.exists(src):
            say(f"SimConnect.dll: copied from {src}")
            if not DRY:
                shutil.copy2(src, dst)
            return
    say("SimConnect.dll: NOT found. Install the MSFS SDK or copy SimConnect.dll into this folder.")


def step_pmdg(patterns):
    found = False
    for pat in patterns:
        for ini in glob.glob(pat):
            found = True
            text = open(ini, encoding="latin-1").read()
            if "EnableDataBroadcast=1" in text:
                say(f"PMDG 737: SDK already enabled in {ini}")
                continue
            b = backup(ini)
            say(f"PMDG 737: enabling the SDK in {ini} (backup {os.path.basename(b)})")
            if not DRY:
                with open(ini, "a", encoding="latin-1") as f:
                    f.write("\n[SDK]\nEnableDataBroadcast=1\n")
    return found


def step_exe_xml(cache_dir):
    exe = os.path.join(cache_dir, "exe.xml")
    addon = ADDON.format(python=sys.executable, script=os.path.join(HERE, "gfmcp.py"))
    if not os.path.exists(exe):
        say(f"exe.xml: created {exe}")
        if not DRY:
            with open(exe, "w", encoding="cp1252") as f:
                f.write(EXE_XML.format(addon=addon))
        return
    text = open(exe, encoding="cp1252", errors="replace").read()
    if "gfmcp.py" in text:
        say(f"exe.xml: already starts the bridge ({exe})")
        return
    if "</SimBase.Document>" not in text:
        say(f"exe.xml: unexpected format, leaving it alone ({exe}). Add the block from the README by hand.")
        return
    b = backup(exe)
    say(f"exe.xml: adding the bridge to {exe} (backup {os.path.basename(b)})")
    if not DRY:
        i = text.rindex("</SimBase.Document>")
        with open(exe, "w", encoding="cp1252") as f:
            f.write(text[:i] + addon + text[i:])


def step_shortcut():
    ps = (
        "$d=[Environment]::GetFolderPath('Desktop');$s=(New-Object -ComObject WScript.Shell)"
        ".CreateShortcut(\"$d\\GoFlight MCP Pro (MSFS).lnk\");"
        f"$s.TargetPath='{os.path.join(HERE, 'GoFlight MCP.bat')}';$s.WorkingDirectory='{HERE}';"
        "$s.IconLocation='C:\\Windows\\System32\\joy.cpl,0';$s.Save()"
    )
    say("Desktop shortcut: GoFlight MCP Pro (MSFS)")
    if not DRY:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)


def main():
    print("GoFlight MCP Pro bridge setup\n")
    if sim_running() and not DRY:
        print("Close Microsoft Flight Simulator first, it rewrites its files on exit.")
        sys.exit(1)
    step_simconnect()
    sims = [(n, c, p) for n, c, p in SIMS if os.path.isdir(c)]
    if not sims:
        say("No MSFS 2020/2024 installation found.")
    pmdg = False
    for name, cache, patterns in sims:
        print(f"\n{name}")
        step_exe_xml(cache)
        pmdg |= step_pmdg(patterns)
    if sims and not pmdg:
        say("\nPMDG 737: 737_Options.ini not found. Load the 737 once in the sim and run this again.")
    print()
    step_shortcut()
    print("\nDone. Plug in the MCP Pro and start MSFS, the bridge starts on its own.")


if __name__ == "__main__":
    main()

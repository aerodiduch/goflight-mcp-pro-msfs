"""GoFlight MCP Pro bridge for Microsoft Flight Simulator 2024 / 2020.

python gfmcp.py            run the bridge
python gfmcp.py --auto     started by MSFS (exe.xml): minimized, exits when the sim closes
python gfmcp.py --verbose  log every input and every MCP change
python gfmcp.py --test     panel test without the simulator
"""
import collections
import configparser
import ctypes
import itertools
import os
import queue
import re
import struct
import sys
import time

import panel as mcp
import pmdg737
import simconnect as sc_api
import web
from simconnect import SimConnect, SimConnectError

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "gfmcp.log")
LOG_LINES = collections.deque(maxlen=400)
_log_seq = itertools.count(1)
_logf = None


def stamp(now=None):
    now = time.time() if now is None else now
    return time.strftime("%H:%M:%S", time.localtime(now)) + ".%03d" % int((now % 1) * 1000)


def log(msg, console=True):
    global _logf
    line = stamp() + " " + msg
    LOG_LINES.append((next(_log_seq), line))
    if not console:
        return
    print(line, flush=True)
    try:
        if _logf is None:
            _logf = open(LOG_PATH, "w", encoding="utf-8")
        _logf.write(line + "\n")
        _logf.flush()
    except OSError:
        pass


def load_config():
    cfg = configparser.ConfigParser()
    cfg.read_dict({
        "general": {"verbose": "no"},
        "panel": {"brightness": "15"},
        "pmdg": {"knob_mode": "set", "wheel_up_increases": "yes", "hdg_push": "bank_angle"},
        "steps": {"alt": "100", "alt_fast": "1000", "alt_fast_threshold": "99"},
        "web": {"enabled": "yes", "port": "8737"},
    })
    cfg.read(os.path.join(HERE, "config.ini"), encoding="utf-8")
    return cfg


def single_instance():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    h = k32.CreateMutexW(None, False, "Local\\GoFlightMCPProBridge")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return h


REQ_PMDG, REQ_GENERIC, REQ_TITLE, REQ_AIRCRAFT = 1, 2, 3, 4
DEF_TITLE, DEF_GENERIC = 10, 11
EV_AIRCRAFT_LOADED = 2
GEN_BASE = 2000

GENERIC_VARS = [
    ("AUTOPILOT HEADING LOCK DIR", "degrees"),
    ("AUTOPILOT ALTITUDE LOCK VAR", "feet"),
    ("AUTOPILOT AIRSPEED HOLD VAR", "knots"),
    ("AUTOPILOT MACH HOLD VAR", "number"),
    ("AUTOPILOT MANAGED SPEED IN MACH", "bool"),
    ("AUTOPILOT VERTICAL HOLD VAR", "feet/minute"),
    ("NAV OBS:1", "degrees"),
    ("NAV OBS:2", "degrees"),
    ("AUTOPILOT MASTER", "bool"),
    ("AUTOPILOT HEADING LOCK", "bool"),
    ("AUTOPILOT ALTITUDE LOCK", "bool"),
    ("AUTOPILOT APPROACH HOLD", "bool"),
    ("AUTOPILOT NAV1 LOCK", "bool"),
    ("AUTOPILOT VERTICAL HOLD", "bool"),
    ("AUTOPILOT FLIGHT LEVEL CHANGE", "bool"),
    ("AUTOPILOT AIRSPEED HOLD", "bool"),
    ("AUTOPILOT THROTTLE ARM", "bool"),
    ("AUTOPILOT FLIGHT DIRECTOR ACTIVE", "bool"),
    ("AUTOPILOT TAKEOFF POWER ACTIVE", "bool"),
    ("GPS DRIVES NAV1", "bool"),
]
GENERIC_KEYS = ["hdg", "alt", "ias", "mach", "in_mach", "vs", "crs_l", "crs_r", "ap", "hdg_hold", "alt_hold",
                "app", "nav1", "vs_hold", "flc", "spd_hold", "at_arm", "fd", "n1", "gps_nav"]
GENERIC_EVENTS = ["HEADING_BUG_SET", "VOR1_SET", "VOR2_SET", "AP_ALT_VAR_SET_ENGLISH", "AP_SPD_VAR_SET",
                  "AP_MACH_VAR_SET", "AP_VS_VAR_SET_ENGLISH", "AP_MASTER", "AP_PANEL_HEADING_HOLD",
                  "AP_PANEL_ALTITUDE_HOLD", "AP_APR_HOLD", "AP_NAV1_HOLD", "AP_PANEL_VS_HOLD",
                  "FLIGHT_LEVEL_CHANGE", "AP_PANEL_SPEED_HOLD", "AUTO_THROTTLE_ARM", "TOGGLE_FLIGHT_DIRECTOR",
                  "AP_N1_HOLD", "AUTOPILOT_DISENGAGE_SET", "AP_MANAGED_SPEED_IN_MACH_TOGGLE"]
GEN = {name: GEN_BASE + i for i, name in enumerate(GENERIC_EVENTS)}

PMDG_BUTTONS = {
    "speed": "SPEED_SWITCH", "lvl_chg": "LVL_CHG_SWITCH", "hdg_sel": "HDG_SEL_SWITCH", "app": "APP_SWITCH",
    "alt_hld": "ALT_HOLD_SWITCH", "vs": "VS_SWITCH", "alt_intv": "ALT_INTV_SWITCH", "cws_a": "CWS_A_SWITCH",
    "cws_b": "CWS_B_SWITCH", "n1": "N1_SWITCH", "vnav": "VNAV_SWITCH", "lnav": "LNAV_SWITCH",
    "cmd_a": "CMD_A_SWITCH", "cmd_b": "CMD_B_SWITCH", "co": "CO_SWITCH", "spd_intv": "SPD_INTV_SWITCH",
    "vor_loc": "VOR_LOC_SWITCH",
}
PMDG_SWITCHES = {"fd_l": "FD_SWITCH_L", "fd_r": "FD_SWITCH_R", "at_arm": "AT_ARM_SWITCH",
                 "disengage": "DISENGAGE_BAR"}
PMDG_SELECTORS = {"hdg": "HEADING_SELECTOR", "crs_l": "COURSE_SELECTOR_L", "crs_r": "COURSE_SELECTOR_R",
                  "alt": "ALTITUDE_SELECTOR", "ias": "SPEED_SELECTOR", "vs": "VS_SELECTOR"}
GENERIC_BUTTONS = {
    "speed": "AP_PANEL_SPEED_HOLD", "lvl_chg": "FLIGHT_LEVEL_CHANGE", "hdg_sel": "AP_PANEL_HEADING_HOLD",
    "app": "AP_APR_HOLD", "alt_hld": "AP_PANEL_ALTITUDE_HOLD", "vs": "AP_PANEL_VS_HOLD",
    "vor_loc": "AP_NAV1_HOLD", "lnav": "AP_NAV1_HOLD", "cmd_a": "AP_MASTER", "cmd_b": "AP_MASTER",
    "n1": "AP_N1_HOLD", "co": "AP_MANAGED_SPEED_IN_MACH_TOGGLE",
}

EVENT_NAMES = {eid: "PMDG " + name for name, eid in pmdg737.EVT.items()}
EVENT_NAMES.update({eid: name for name, eid in GEN.items()})
CUSTOM_EVENT_BASE = 5000
WATCH_BASE = 100

TARGET_HOLD_S = 1.5
SWITCH_DEBOUNCE_S = 0.12


class SimClosed(Exception):
    pass


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def vs_step(v, clicks):
    # 737 V/S wheel: 50 fpm steps below 1000 fpm, 100 fpm above
    s = 1 if clicks > 0 else -1
    for _ in range(abs(clicks)):
        if abs(v) < 1000 or (abs(v) == 1000 and v * s < 0):
            v += 50 * s
        else:
            v += 100 * s
    return clamp(v, -7900, 6000)


class Bridge:
    def __init__(self, cfg):
        self.cfg = cfg
        self.verbose = cfg.getboolean("general", "verbose")
        self.sc = SimConnect(os.path.join(HERE, "SimConnect.dll"))
        self.layout = pmdg737.load_layout(log)
        self.panel = None
        self.next_panel_try = 0.0
        self.next_sim_try = 0.0
        self.reset_sim_state()
        self.pending_switch = {}
        self.switch_committed = {}
        self.status = None
        self.exit_with_sim = False
        self.actions = queue.Queue()
        self.snapshot = {}
        self.next_publish = 0.0
        self.traffic = collections.deque(maxlen=60)
        self.flash = {}
        self.knob_seen = {}
        self.latency_ms = None
        self.watches = []
        self.watch_ids = itertools.count(WATCH_BASE)

    def reset_sim_state(self):
        self.pmdg = None
        self.generic = None
        self.title = ""
        self.aircraft_path = ""
        self.targets = {}
        self.next_pmdg_request = 0.0
        self.custom_events = {}

    def is_pmdg737(self):
        # livery titles don't say PMDG ("737-800 PAX BW HD"), the aircraft path does
        s = (self.aircraft_path + " " + self.title).lower()
        return "pmdg" in s and re.search(r"73[6789]|737|ng3|bbj", s) is not None

    def mode(self):
        if not self.sc.connected:
            return "nosim"
        known_other = bool(self.aircraft_path) and "pmdg" not in self.aircraft_path.lower()
        if self.pmdg is not None and not known_other:
            return "pmdg"
        if self.is_pmdg737():
            return "pmdg_wait"
        if self.generic is not None:
            return "generic"
        return "waiting"

    def set_status(self):
        txt = {
            "nosim": "Waiting for Microsoft Flight Simulator...",
            "waiting": "Connected to MSFS, waiting for an aircraft...",
            "pmdg": "PMDG 737 detected, MCP linked through the PMDG SDK. Ready.",
            "pmdg_wait": "PMDG 737 loaded but no SDK data yet. Check EnableDataBroadcast=1 in "
                         "737_Options.ini, or wait until the aircraft finishes loading.",
            "generic": f"Aircraft: {self.title or '?'} (generic mode, default MSFS autopilot).",
        }[self.mode()]
        if self.panel is None:
            txt = "MCP Pro not connected. " + txt
        if txt != self.status:
            self.status = txt
            log(txt)

    def ensure_panel(self):
        if self.panel is not None or time.monotonic() < self.next_panel_try:
            return
        self.next_panel_try = time.monotonic() + 2.0
        try:
            self.panel = mcp.MCPPro(log=log, brightness=self.cfg.getint("panel", "brightness"))
            log("MCP Pro connected.")
            self.panel.light_test()
            self.panel.start()
            self.switch_committed = {}
            self.pending_switch = {}
        except OSError as e:
            self.panel = None
            if self.verbose:
                log(f"Panel: {e}")

    def drop_panel(self, why):
        log(f"Lost the MCP Pro ({why}), retrying...")
        try:
            self.panel.close(blank=False)
        except Exception:
            pass
        self.panel = None

    def ensure_sim(self):
        if self.sc.connected or time.monotonic() < self.next_sim_try:
            return
        self.next_sim_try = time.monotonic() + 3.0
        if not self.sc.open():
            return
        try:
            self.setup_sim()
        except SimConnectError as e:
            log(f"SimConnect setup failed: {e}")
            self.sc.close()

    def setup_sim(self):
        sc = self.sc
        self.reset_sim_state()
        sc.subscribe_system_event(EV_AIRCRAFT_LOADED, "AircraftLoaded")
        sc.request_system_state(REQ_AIRCRAFT, "AircraftLoaded")
        sc.add_data_def(DEF_TITLE, "TITLE", None, sc_api.DATATYPE_STRING256)
        sc.request_data(REQ_TITLE, DEF_TITLE, sc_api.PERIOD_SECOND, sc_api.DATA_REQUEST_FLAG_CHANGED)
        for name, units in GENERIC_VARS:
            sc.add_data_def(DEF_GENERIC, name, units)
        sc.request_data(REQ_GENERIC, DEF_GENERIC, sc_api.PERIOD_VISUAL_FRAME, sc_api.DATA_REQUEST_FLAG_CHANGED)
        for name, eid in GEN.items():
            sc.map_event(eid, name)
        for eid in pmdg737.EVT.values():
            sc.map_event(eid, f"#{eid}")
        sc.map_client_data(pmdg737.DATA_NAME, pmdg737.DATA_ID)
        sc.add_client_data_def(pmdg737.DATA_DEFINITION, 0, self.layout["_size"])
        self.request_pmdg()
        for w in self.watches:
            self.register_watch(w)
        log("Connected to Microsoft Flight Simulator.")

    def request_pmdg(self):
        self.sc.request_client_data(pmdg737.DATA_ID, REQ_PMDG, pmdg737.DATA_DEFINITION,
                                    sc_api.CLIENT_DATA_PERIOD_ON_SET, sc_api.CLIENT_DATA_REQUEST_FLAG_CHANGED)
        self.next_pmdg_request = time.monotonic() + 5.0

    def drop_sim(self, why):
        log(f"Disconnected from MSFS ({why}).")
        self.sc.close()
        self.reset_sim_state()
        self.next_sim_try = time.monotonic() + 5.0
        if self.exit_with_sim:
            raise SimClosed()

    def aircraft_changed(self):
        self.pmdg = None
        self.targets.clear()
        if self.sc.connected:
            try:
                self.request_pmdg()
            except SimConnectError:
                pass

    def pump_sim(self):
        if not self.sc.connected:
            return
        try:
            for rid, raw in self.sc.dispatch():
                self.on_recv(rid, raw)
            # the PMDG data area only exists once the aircraft has loaded
            if self.mode() == "pmdg_wait" and time.monotonic() > self.next_pmdg_request:
                self.request_pmdg()
        except SimConnectError as e:
            self.drop_sim(str(e))

    def on_recv(self, rid, raw):
        if rid == sc_api.RECV_ID_CLIENT_DATA:
            req, _define, payload = sc_api.parse_object_data(raw)
            if req == REQ_PMDG and len(payload) >= self.layout["_size"]:
                prev = self.pmdg
                self.pmdg = pmdg737.decode(self.layout, payload)
                if prev is None:
                    log("Receiving PMDG 737 SDK data.")
                elif self.verbose:
                    diff = {k: v for k, v in self.pmdg.items() if prev.get(k) != v}
                    if diff:
                        log(f"PMDG: {diff}")
        elif rid == sc_api.RECV_ID_SIMOBJECT_DATA:
            req, _define, payload = sc_api.parse_object_data(raw)
            if req >= WATCH_BASE:
                for w in self.watches:
                    if w["id"] == req:
                        if w["units"] == "string":
                            w["value"] = payload[:256].split(b"\0", 1)[0].decode("utf-8", "replace")
                        else:
                            w["value"] = struct.unpack_from("<d", payload, 0)[0]
            elif req == REQ_GENERIC:
                vals = struct.unpack_from("<%dd" % len(GENERIC_VARS), payload, 0)
                self.generic = dict(zip(GENERIC_KEYS, vals))
            elif req == REQ_TITLE:
                title = payload[:256].split(b"\0", 1)[0].decode("utf-8", "replace")
                if title != self.title:
                    log(f"Aircraft loaded: {title}")
                    had_title = bool(self.title)
                    self.title = title
                    if had_title:
                        self.aircraft_changed()
        elif rid == sc_api.RECV_ID_SYSTEM_STATE:
            req, _i, _f, s = sc_api.parse_system_state(raw)
            if req == REQ_AIRCRAFT:
                self.aircraft_path = s
        elif rid == sc_api.RECV_ID_EVENT_FILENAME:
            ev, s = sc_api.parse_filename_event(raw)
            if ev == EV_AIRCRAFT_LOADED and s != self.aircraft_path:
                self.aircraft_path = s
                self.aircraft_changed()
        elif rid == sc_api.RECV_ID_EXCEPTION:
            exc, send_id, index = sc_api.parse_exception(raw)
            log(f"SimConnect exception {exc} (packet {send_id}, parameter {index})", console=self.verbose)
        elif rid == sc_api.RECV_ID_QUIT:
            self.drop_sim("simulator closed")

    def base(self, name, sim_value):
        # keep showing/using our last requested value until the sim catches up
        t = self.targets.get(name)
        if t:
            age = time.monotonic() - t[1]
            if t[0] == sim_value or age > TARGET_HOLD_S:
                if t[0] == sim_value:
                    self.latency_ms = round(age * 1000)
                del self.targets[name]
                return sim_value
            return t[0]
        return sim_value

    def set_target(self, name, value):
        self.targets[name] = (value, time.monotonic())

    def send(self, event_id, data=0):
        if not self.sc.connected:
            return
        self.traffic.append({"t": stamp(), "event": EVENT_NAMES.get(event_id, str(event_id)), "data": data})
        t = time.perf_counter()
        try:
            self.sc.transmit(event_id, data)
        except SimConnectError as e:
            self.drop_sim(str(e))
        dt = time.perf_counter() - t
        if dt > 0.3:
            log(f"MSFS took {dt * 1000:.0f} ms to accept an event (sim stutter).")

    def pmdg_click(self, evt):
        eid = pmdg737.EVT[evt]
        self.send(eid, pmdg737.MOUSE_LEFTSINGLE)
        self.send(eid, pmdg737.MOUSE_LEFTRELEASE)

    def handle_events(self, events):
        for ev in events:
            if self.verbose:
                log(f"Panel: {ev}")
            kind = ev[0]
            if kind == "knob":
                self.knob_seen[ev[1]] = (ev[2], time.monotonic())
                self.on_knob(ev[1], ev[2])
            elif kind in ("press", "release"):
                name = ev[1]
                if name in mcp.SWITCHES:
                    self.pending_switch[name] = (kind == "press", time.monotonic())
                elif kind == "press":
                    self.flash[name] = time.monotonic()
                    self.on_button(name)
            elif kind == "switch_init":
                # first report after connecting: line up F/D and A/T ARM with the hardware
                name, on = ev[1], ev[2]
                self.switch_committed[name] = on
                if name != "disengage" and self.mode() in ("pmdg", "generic"):
                    self.on_switch(name, on)

    def apply_actions(self):
        while True:
            try:
                a = self.actions.get_nowait()
            except queue.Empty:
                return
            kind, name = a.get("type"), str(a.get("name", "")).strip()
            active = self.mode() in ("pmdg", "generic")
            if kind in ("press", "knob", "switch") and not active:
                log(f"Live view: {name} ignored, no aircraft linked")
            elif kind == "press" and name in mcp.INPUTS and name not in mcp.SWITCHES:
                self.flash[name] = time.monotonic()
                self.on_button(name)
            elif kind == "knob" and name in mcp.KNOBS:
                delta = clamp(int(a.get("delta", 1)), -50, 50)
                self.knob_seen[name] = (delta, time.monotonic())
                self.on_knob(name, delta)
            elif kind == "switch" and name in mcp.SWITCHES:
                self.on_switch(name, bool(a.get("on")))
            elif kind == "event" and name:
                self.send_custom(name, a.get("value", 0))
            elif kind == "watch" and name:
                self.add_watch(name, str(a.get("units") or "number").strip())
            elif kind == "unwatch":
                self.remove_watch(name)

    def send_custom(self, name, value):
        if not self.sc.connected:
            log("Live view: not connected to MSFS")
            return
        try:
            data = int(str(value).strip() or "0", 0)
        except ValueError:
            log(f"Live view: bad value {value!r}")
            return
        key = name.upper()
        if key in pmdg737.EVT:
            eid = pmdg737.EVT[key]
        else:
            sim_name = "#" + name if name.isdigit() else key
            if sim_name not in self.custom_events:
                eid = CUSTOM_EVENT_BASE + len(self.custom_events)
                try:
                    self.sc.map_event(eid, sim_name)
                except SimConnectError as e:
                    log(f"Live view: {e}")
                    return
                self.custom_events[sim_name] = eid
                EVENT_NAMES[eid] = sim_name
            eid = self.custom_events[sim_name]
        log(f"Live view: sending {name} = {data}")
        self.send(eid, data)

    def add_watch(self, name, units):
        if any(w["name"] == name for w in self.watches):
            return
        w = {"id": next(self.watch_ids), "name": name, "units": units, "value": None}
        self.watches.append(w)
        if self.sc.connected:
            self.register_watch(w)

    def register_watch(self, w):
        try:
            if w["units"] == "string":
                self.sc.add_data_def(w["id"], w["name"], None, sc_api.DATATYPE_STRING256)
            else:
                self.sc.add_data_def(w["id"], w["name"], w["units"])
            self.sc.request_data(w["id"], w["id"], sc_api.PERIOD_VISUAL_FRAME, sc_api.DATA_REQUEST_FLAG_CHANGED)
        except SimConnectError as e:
            log(f"Live view: could not watch {w['name']} ({e})")

    def remove_watch(self, name):
        for w in list(self.watches):
            if w["name"] == name:
                self.watches.remove(w)
                if self.sc.connected:
                    try:
                        self.sc.request_data(w["id"], w["id"], sc_api.PERIOD_NEVER, 0)
                    except SimConnectError:
                        pass

    def sim_switches(self):
        m = self.mode()
        if m == "pmdg":
            d = self.pmdg
            return {"fd_l": d["MCP_FDSw"][0], "fd_r": d["MCP_FDSw"][1], "at_arm": d["MCP_ATArmSw"],
                    "disengage": d["MCP_DisengageBar"]}
        if m == "generic":
            g = self.generic
            return {"fd_l": bool(g["fd"]), "fd_r": bool(g["fd"]), "at_arm": bool(g["at_arm"]), "disengage": False}
        return {}

    def publish(self, vals, leds):
        now = time.monotonic()
        reports = mcp.build_reports(vals, leds)
        self.snapshot = {
            "t": time.time(),
            "status": self.status,
            "mode": self.mode(),
            "panel": self.panel is not None,
            "sim": self.sc.connected,
            "aircraft": self.title,
            "path": self.aircraft_path,
            "displays": {name: list(reports[name][1:]) for name in mcp.DISPLAYS},
            "leds": sorted(leds),
            "hw_switches": self.panel.switch_state if self.panel else {},
            "sim_switches": self.sim_switches(),
            "pressed": [k for k, t in self.flash.items() if now - t < 0.35],
            "knobs": {k: d for k, (d, t) in self.knob_seen.items() if now - t < 0.6},
            "values": self.pmdg if self.mode() == "pmdg" else self.generic,
            "traffic": list(self.traffic)[-25:],
            "watches": [{"name": w["name"], "units": w["units"], "value": w["value"]} for w in self.watches],
            "latency_ms": self.latency_ms,
        }

    def commit_switches(self):
        now = time.monotonic()
        for name, (state, t) in list(self.pending_switch.items()):
            if now - t < SWITCH_DEBOUNCE_S:
                continue
            del self.pending_switch[name]
            if not self.panel or self.panel.switch_state.get(name) != state:
                continue
            if self.switch_committed.get(name) == state:
                continue
            self.switch_committed[name] = state
            self.on_switch(name, state)

    def on_knob(self, name, n):
        m = self.mode()
        if m == "pmdg":
            self.pmdg_knob(name, n)
        elif m == "generic":
            self.generic_knob(name, n)

    def on_button(self, name):
        m = self.mode()
        if m == "pmdg":
            if name in PMDG_BUTTONS:
                self.pmdg_click(PMDG_BUTTONS[name])
            elif name == "hdg_push" and self.cfg.get("pmdg", "hdg_push") == "bank_angle":
                sel = (self.pmdg["MCP_BankLimitSel"] + 1) % 5
                self.send(pmdg737.EVT["BANK_ANGLE_SELECTOR"], sel)
                log(f"Bank angle {10 + sel * 5}")
        elif m == "generic":
            evt = GENERIC_BUTTONS.get(name)
            if evt:
                self.send(GEN[evt], 0)

    def on_switch(self, name, on):
        m = self.mode()
        if m == "pmdg":
            # PMDG switch positions are inverted for these, so click only when sim and hardware differ
            d = self.pmdg
            cur = {"fd_l": d["MCP_FDSw"][0], "fd_r": d["MCP_FDSw"][1], "at_arm": d["MCP_ATArmSw"],
                   "disengage": d["MCP_DisengageBar"]}[name]
            if bool(cur) != on:
                self.pmdg_click(PMDG_SWITCHES[name])
            if self.verbose:
                log(f"Switch {name} {'ON' if on else 'OFF'} (sim {'ON' if cur else 'OFF'})")
        elif m == "generic" and self.generic:
            g = self.generic
            if name in ("fd_l", "fd_r") and bool(g["fd"]) != on:
                self.send(GEN["TOGGLE_FLIGHT_DIRECTOR"], 0)
            elif name == "at_arm" and bool(g["at_arm"]) != on:
                self.send(GEN["AUTO_THROTTLE_ARM"], 0)
            elif name == "disengage":
                self.send(GEN["AUTOPILOT_DISENGAGE_SET"], 1 if on else 0)

    def alt_step(self, n):
        if abs(n) >= self.cfg.getint("steps", "alt_fast_threshold"):
            return self.cfg.getint("steps", "alt_fast")
        return self.cfg.getint("steps", "alt")

    def pmdg_knob(self, name, n):
        d = self.pmdg
        if self.cfg.get("pmdg", "knob_mode") == "wheel":
            up = self.cfg.getboolean("pmdg", "wheel_up_increases")
            flag = pmdg737.MOUSE_WHEEL_UP if (n > 0) == up else pmdg737.MOUSE_WHEEL_DOWN
            for _ in range(abs(n)):
                self.send(pmdg737.EVT[PMDG_SELECTORS[name]], flag)
            return
        if name == "hdg":
            v = (self.base(name, d["MCP_Heading"]) + n) % 360
            self.set_target(name, v)
            self.send(pmdg737.EVT["HDG_SET"], v)
        elif name in ("crs_l", "crs_r"):
            i = 0 if name == "crs_l" else 1
            v = (self.base(name, d["MCP_Course"][i]) + n) % 360
            self.set_target(name, v)
            self.send(pmdg737.EVT["CRS_L_SET" if i == 0 else "CRS_R_SET"], v)
        elif name == "alt":
            v = clamp(round((self.base(name, d["MCP_Altitude"]) + n * self.alt_step(n)) / 100) * 100, 0, 50000)
            self.set_target(name, v)
            self.send(pmdg737.EVT["ALT_SET"], v)
        elif name == "ias":
            if d["MCP_IASBlank"]:
                return
            m = d["MCP_IASMach"]
            if m < 10.0:
                v = clamp(self.base("mach", round(m * 100)) + n, 40, 99)
                self.set_target("mach", v)
                self.send(pmdg737.EVT["MACH_SET"], v)
            else:
                v = clamp(self.base("ias", int(round(m))) + n, 100, 399)
                self.set_target("ias", v)
                self.send(pmdg737.EVT["IAS_SET"], v)
        elif name == "vs":
            if d["MCP_VertSpeedBlank"]:
                return
            v = vs_step(self.base(name, d["MCP_VertSpeed"]), n)
            self.set_target(name, v)
            self.send(pmdg737.EVT["VS_SET"], v + 10000)

    def generic_knob(self, name, n):
        g = self.generic
        if name in ("hdg", "crs_l", "crs_r"):
            v = (self.base(name, int(round(g[name])) % 360) + n) % 360
            self.set_target(name, v)
            self.send(GEN[{"hdg": "HEADING_BUG_SET", "crs_l": "VOR1_SET", "crs_r": "VOR2_SET"}[name]], v)
        elif name == "alt":
            v = clamp(round((self.base(name, int(round(g["alt"]))) + n * self.alt_step(n)) / 100) * 100, 0, 50000)
            self.set_target(name, v)
            self.send(GEN["AP_ALT_VAR_SET_ENGLISH"], v)
        elif name == "ias":
            if g["in_mach"]:
                v = clamp(self.base("mach", int(round(g["mach"] * 100))) + n, 10, 99)
                self.set_target("mach", v)
                self.send(GEN["AP_MACH_VAR_SET"], v)
            else:
                v = clamp(self.base("ias", int(round(g["ias"]))) + n, 0, 399)
                self.set_target("ias", v)
                self.send(GEN["AP_SPD_VAR_SET"], v)
        elif name == "vs":
            v = vs_step(self.base(name, int(round(g["vs"]))), n)
            self.set_target(name, v)
            self.send(GEN["AP_VS_VAR_SET_ENGLISH"], v)

    def view(self):
        m = self.mode()
        if m == "pmdg":
            return self.pmdg_view(self.pmdg)
        if m == "generic":
            return self.generic_view(self.generic)
        return {}, set()

    def pmdg_view(self, d):
        if not d["MCP_indication_powered"]:
            return {}, set()
        vals = {
            "crs_l": "%03d" % self.base("crs_l", d["MCP_Course"][0]),
            "crs_r": "%03d" % self.base("crs_r", d["MCP_Course"][1]),
            "hdg": "%03d" % self.base("hdg", d["MCP_Heading"]),
            "alt": str(self.base("alt", d["MCP_Altitude"])),
        }
        if not d["MCP_IASBlank"]:
            m = d["MCP_IASMach"]
            if m < 10.0:
                text = ".%02d" % self.base("mach", round(m * 100))
            else:
                text = str(self.base("ias", int(round(m))))
            # flashing 8 = overspeed, A = underspeed, right before the first digit
            sym = "8" if d["MCP_IASOverspeedFlash"] else "A" if d["MCP_IASUnderspeedFlash"] else None
            if sym:
                lit = (time.monotonic() % 0.6) < 0.3
                cells = mcp.encode(text, 4)
                while cells and cells[0] == 0:
                    cells.pop(0)
                vals["ias"] = [mcp.SEG[sym] if lit else 0] + cells
            else:
                vals["ias"] = text
        if not d["MCP_VertSpeedBlank"]:
            vals["vs"] = str(self.base("vs", d["MCP_VertSpeed"]))
        leds = {name for name, key in (
            ("speed", "MCP_annunSPEED"), ("lvl_chg", "MCP_annunLVL_CHG"), ("hdg_sel", "MCP_annunHDG_SEL"),
            ("app", "MCP_annunAPP"), ("alt_hld", "MCP_annunALT_HOLD"), ("vs", "MCP_annunVS"),
            ("vnav", "MCP_annunVNAV"), ("lnav", "MCP_annunLNAV"), ("vor_loc", "MCP_annunVOR_LOC"),
            ("cmd_a", "MCP_annunCMD_A"), ("cmd_b", "MCP_annunCMD_B"), ("cws_a", "MCP_annunCWS_A"),
            ("cws_b", "MCP_annunCWS_B"), ("n1", "MCP_annunN1"), ("at_arm", "MCP_annunATArm"),
        ) if d[key]}
        if d["MCP_annunFD"][0]:
            leds.add("fd_l")
        if d["MCP_annunFD"][1]:
            leds.add("fd_r")
        return vals, leds

    def generic_view(self, g):
        vals = {
            "crs_l": "%03d" % (self.base("crs_l", int(round(g["crs_l"])) % 360)),
            "crs_r": "%03d" % (self.base("crs_r", int(round(g["crs_r"])) % 360)),
            "hdg": "%03d" % (self.base("hdg", int(round(g["hdg"])) % 360)),
            "alt": str(self.base("alt", int(round(g["alt"])))),
            "vs": str(self.base("vs", int(round(g["vs"])))),
        }
        if g["in_mach"]:
            vals["ias"] = ".%02d" % self.base("mach", int(round(g["mach"] * 100)))
        else:
            vals["ias"] = str(self.base("ias", int(round(g["ias"]))))
        leds = set()
        for led, key in (("cmd_a", "ap"), ("hdg_sel", "hdg_hold"), ("alt_hld", "alt_hold"), ("app", "app"),
                         ("vs", "vs_hold"), ("lvl_chg", "flc"), ("speed", "spd_hold"), ("at_arm", "at_arm"),
                         ("fd_l", "fd"), ("fd_r", "fd"), ("n1", "n1")):
            if g[key]:
                leds.add(led)
        if g["nav1"] and not g["app"]:
            leds.add("lnav" if g["gps_nav"] else "vor_loc")
        return vals, leds

    def run(self):
        log("GoFlight MCP Pro bridge started. Keep this window open while flying (Ctrl+C to quit).")
        while True:
            self.ensure_panel()
            self.ensure_sim()
            events = []
            if self.panel is not None and self.panel.error is not None:
                self.drop_panel(self.panel.error)
            if self.panel is not None:
                events = self.panel.poll(5)
            else:
                time.sleep(0.05)
            t = time.perf_counter()
            self.pump_sim()
            dt = time.perf_counter() - t
            if dt > 0.3:
                log(f"MSFS took {dt * 1000:.0f} ms to respond (sim stutter).")
            if events:
                self.handle_events(events)
            self.apply_actions()
            self.commit_switches()
            self.set_status()
            vals, leds = self.view()
            if self.panel is not None:
                self.panel.show(vals, leds)
            if time.monotonic() >= self.next_publish:
                self.next_publish = time.monotonic() + 0.1
                self.publish(vals, leds)

    def shutdown(self):
        if self.panel is not None:
            self.panel.close(blank=True)
        self.sc.close()


def test_mode():
    p = mcp.MCPPro(log=print)
    print("Light test...")
    p.light_test(2.0)
    p.start()
    vals = {"crs_l": 0, "ias": 250, "hdg": 0, "alt": 10000, "vs": 0, "crs_r": 0}
    leds = set()
    print("Test mode: turn the knobs and press the buttons. Ctrl+C to quit.")
    try:
        while True:
            for ev in p.poll(20):
                print("  ", ev)
                if ev[0] == "knob":
                    k, n = ev[1], ev[2]
                    if k in ("hdg", "crs_l", "crs_r"):
                        vals[k] = (vals[k] + n) % 360
                    elif k == "alt":
                        vals[k] = clamp(vals[k] + n * 100, 0, 50000)
                    elif k == "vs":
                        vals[k] = vs_step(vals[k], n)
                    else:
                        vals[k] = clamp(vals[k] + n, 100, 399)
                elif ev[0] in ("press", "release", "switch_init"):
                    name = ev[1]
                    if name in mcp.SWITCHES and name in mcp.LEDS:
                        on = ev[0] == "press" or (ev[0] == "switch_init" and ev[2])
                        (leds.add if on else leds.discard)(name)
                    elif ev[0] == "press" and name in mcp.LEDS:
                        leds.symmetric_difference_update({name})
            text = {k: ("%03d" % v if k in ("hdg", "crs_l", "crs_r") else str(v)) for k, v in vals.items()}
            p.show(text, leds)
    except KeyboardInterrupt:
        pass
    finally:
        p.close()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    os.system("title GoFlight MCP Pro - MSFS")
    if "--test" in sys.argv:
        test_mode()
        return
    if single_instance() is None:
        print("The bridge is already running in another window.")
        time.sleep(5)
        return
    cfg = load_config()
    if "--verbose" in sys.argv:
        cfg.set("general", "verbose", "yes")
    bridge = Bridge(cfg)
    if cfg.getboolean("web", "enabled"):
        web.WebUI(bridge, LOG_LINES, cfg.getint("web", "port"), log).start()
    if "--auto" in sys.argv:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        bridge.exit_with_sim = True
    try:
        bridge.run()
    except KeyboardInterrupt:
        log("Exiting.")
    except SimClosed:
        log("MSFS closed, exiting.")
    finally:
        bridge.shutdown()


if __name__ == "__main__":
    main()

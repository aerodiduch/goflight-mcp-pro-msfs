"""GoFlight MCP Pro: displays, LEDs, knobs, buttons and switches over raw HID."""
import queue
import threading
import time

import hidwin

VID, PID = 0x09F3, 0x0064

# display -> (feature report id, digits)
DISPLAYS = {"crs_l": (3, 3), "ias": (5, 5), "hdg": (7, 3), "alt": (9, 5), "vs": (11, 5), "crs_r": (13, 3)}
LED_REPORT = 15
BRIGHTNESS_REPORT = 14

# LED -> (byte in the LED block, mask)
LEDS = {
    "speed": (0, 0x01), "lvl_chg": (0, 0x02), "hdg_sel": (0, 0x04), "app": (0, 0x08),
    "alt_hld": (0, 0x10), "vs": (0, 0x20), "fd_r": (0, 0x80),
    "cws_a": (1, 0x02), "cws_b": (1, 0x04), "fd_l": (1, 0x40), "n1": (1, 0x80),
    "vnav": (2, 0x01), "lnav": (2, 0x02), "cmd_a": (2, 0x04), "cmd_b": (2, 0x08),
    "at_arm": (2, 0x10), "vor_loc": (2, 0x80),
}

# knob -> (input byte, nibble shift), value is a signed 4 bit click count
KNOBS = {"hdg": (1, 0), "crs_l": (1, 4), "vs": (2, 0), "ias": (2, 4), "crs_r": (3, 0), "alt": (3, 4)}

# button or switch -> (input byte, mask)
INPUTS = {
    "speed": (5, 0x01), "lvl_chg": (5, 0x02), "hdg_sel": (5, 0x04), "app": (5, 0x08),
    "alt_hld": (5, 0x10), "vs": (5, 0x20), "disengage": (5, 0x40), "fd_r": (5, 0x80),
    "alt_intv": (6, 0x01), "cws_a": (6, 0x02), "cws_b": (6, 0x04), "ias_push": (6, 0x08),
    "hdg_push": (6, 0x10), "alt_push": (6, 0x20), "fd_l": (6, 0x40), "n1": (6, 0x80),
    "vnav": (7, 0x01), "lnav": (7, 0x02), "cmd_a": (7, 0x04), "cmd_b": (7, 0x08),
    "at_arm": (7, 0x10), "co": (7, 0x20), "spd_intv": (7, 0x40), "vor_loc": (7, 0x80),
}
SWITCHES = {"fd_l", "fd_r", "at_arm", "disengage"}

SEG = {"0": 0x3F, "1": 0x06, "2": 0x5B, "3": 0x4F, "4": 0x66, "5": 0x6D, "6": 0x7D, "7": 0x07,
       "8": 0x7F, "9": 0x67, " ": 0x00, "-": 0x40, "_": 0x08, "A": 0x77, "b": 0x7C, "C": 0x39,
       "d": 0x5E, "E": 0x79, "F": 0x71, "H": 0x76, "L": 0x38, "n": 0x54, "o": 0x5C, "P": 0x73,
       "r": 0x50, "t": 0x78, "U": 0x3E}
DP = 0x80

REFRESH_STEP_S = 0.5
INPUT_QUIET_S = 0.3
WRITE_TIMEOUT_MS = 150


def encode(text, digits):
    """Right aligned 7 segment cells. A '.' sets the decimal point of the previous cell."""
    cells = []
    for ch in text:
        if ch == ".":
            if cells:
                cells[-1] |= DP
            else:
                cells.append(DP)
        else:
            cells.append(SEG.get(ch, 0))
    cells = cells[-digits:]
    return [0] * (digits - len(cells)) + cells


def build_reports(values, leds, brightness=15):
    out = {}
    for name, (rid, digits) in DISPLAYS.items():
        text = values.get(name)
        if isinstance(text, list):
            cells = ([0] * digits + text)[-digits:]
        else:
            cells = encode(text, digits) if text else [0] * digits
        out[name] = bytes([rid] + cells)
    block = [0, 0, 0]
    for name in leds:
        i, bit = LEDS[name]
        block[i] |= bit
    out["leds"] = bytes([LED_REPORT, 0] + block)
    out["bright"] = bytes([BRIGHTNESS_REPORT, brightness & 0x0F])
    return out


class MCPPro:
    """Reads input and writes displays on separate threads and handles.

    The firmware sometimes leaves a display write hanging when it collides with an input
    report, so writes time out and get resent instead of blocking everything else.
    """

    def __init__(self, log=None, brightness=15):
        dev = next(hidwin.enumerate_devices(VID, PID), None)
        if dev is None:
            raise OSError("GoFlight MCP Pro not found on USB")
        self.log = log or (lambda m: None)
        self.brightness = brightness
        self.rd = hidwin.HidDevice(dev["path"])
        self.wr = hidwin.HidDevice(dev["path"])
        self.events = queue.Queue()
        self.error = None
        self._alive = True
        self._buttons = None
        self._last_input = 0.0
        self._desired = None
        self._dirty = False
        self._cv = threading.Condition()
        self._threads = []

    def start(self):
        for fn in (self._reader, self._writer):
            t = threading.Thread(target=fn, daemon=True)
            t.start()
            self._threads.append(t)

    def close(self, blank=True):
        self._alive = False
        with self._cv:
            self._cv.notify_all()
        for t in self._threads:
            t.join(timeout=1.0)
        if blank:
            try:
                for rep in build_reports({}, set(), self.brightness).values():
                    self.wr.set_feature_timeout(rep, WRITE_TIMEOUT_MS)
            except OSError:
                pass
        self.rd.close()
        self.wr.close()

    def show(self, values, leds):
        reports = build_reports(values, leds, self.brightness)
        with self._cv:
            if reports != self._desired:
                self._desired = reports
                self._dirty = True
                self._cv.notify()

    def write_now(self, values, leds):
        for rep in build_reports(values, leds, self.brightness).values():
            if not self.wr.set_feature_timeout(rep, WRITE_TIMEOUT_MS):
                self.wr.set_feature_timeout(rep, WRITE_TIMEOUT_MS)

    def light_test(self, seconds=0.6):
        # no decimal points: every segment plus every dot is too much for USB power
        self.write_now({k: "8" * d for k, (_r, d) in DISPLAYS.items()}, set(LEDS))
        time.sleep(seconds)
        self.write_now({}, set())
        time.sleep(0.2)
        while self.rd.read(0) is not None:
            pass
        self._buttons = None

    def _writer(self):
        sent = {}
        last_refresh = 0.0
        slot = 0
        while self._alive:
            with self._cv:
                if not self._dirty:
                    self._cv.wait(timeout=0.05)
                desired = self._desired
                self._dirty = False
            if not self._alive:
                break
            if desired is None:
                continue
            for key, rep in desired.items():
                if sent.get(key) != rep:
                    sent[key] = rep if self._write(key, rep) else None
            # slow background refresh, one report at a time, never right after an input
            now = time.monotonic()
            if now - last_refresh >= REFRESH_STEP_S and now - self._last_input > INPUT_QUIET_S:
                keys = list(desired)
                key = keys[slot % len(keys)]
                slot += 1
                last_refresh = now
                self._write(key, desired[key])

    def _write(self, key, rep):
        try:
            ok = self.wr.set_feature_timeout(rep, WRITE_TIMEOUT_MS)
        except OSError as e:
            self.log(f"Panel rejected a display write ({key}): {e}")
            return False
        if not ok:
            self.log(f"Panel did not answer in time ({key}), resending.")
        return ok

    def _reader(self):
        while self._alive:
            try:
                rep = self.rd.read(100)
            except OSError as e:
                self.error = e
                return
            if rep is None:
                continue
            self._last_input = time.monotonic()
            for ev in self._decode(rep):
                self.events.put(ev)

    def poll(self, timeout_ms=0):
        """Pending events, with consecutive turns of the same knob merged into one."""
        out = []
        try:
            ev = self.events.get(timeout=timeout_ms / 1000.0) if timeout_ms else self.events.get_nowait()
        except queue.Empty:
            return out
        while True:
            if ev[0] == "knob" and out and out[-1][0] == "knob" and out[-1][1] == ev[1]:
                out[-1] = ("knob", ev[1], out[-1][2] + ev[2])
            else:
                out.append(ev)
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                return out

    def _decode(self, rep):
        if len(rep) < 8:
            return []
        ev = []
        if rep[1] or rep[2] or rep[3]:
            # button bytes are not reliable in knob reports
            for name, (idx, shift) in KNOBS.items():
                n = (rep[idx] >> shift) & 0x0F
                if n:
                    ev.append(("knob", name, n - 16 if n >= 8 else n))
            return ev
        state = {name: bool(rep[idx] & mask) for name, (idx, mask) in INPUTS.items()}
        prev = self._buttons
        self._buttons = state
        if prev is None:
            for name, on in state.items():
                if name in SWITCHES:
                    ev.append(("switch_init", name, on))
                elif on:
                    ev.append(("press", name))
            return ev
        for name, on in state.items():
            if on != prev[name]:
                ev.append(("press" if on else "release", name))
        return ev

    @property
    def switch_state(self):
        b = self._buttons
        if b is None:
            return {}
        return {k: v for k, v in b.items() if k in SWITCHES}

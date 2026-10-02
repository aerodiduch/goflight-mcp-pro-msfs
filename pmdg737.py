"""PMDG 737 SDK: MCP data layout and control events.

The layout is read from the PMDG_NG3_SDK.h that ships with the aircraft, so it follows
PMDG updates. If the header can't be found the offsets of v4.0.63 are used.
"""
import glob
import os
import re
import struct

DATA_NAME = "PMDG_NG3_Data"
DATA_ID = 0x4E473331
DATA_DEFINITION = 0x4E473332
CONTROL_NAME = "PMDG_NG3_Control"
CONTROL_ID = 0x4E473333
CONTROL_DEFINITION = 0x4E473334

BASE = 0x00011000  # THIRD_PARTY_EVENT_ID_MIN

MOUSE_LEFTSINGLE = 0x20000000
MOUSE_LEFTRELEASE = 0x00020000
MOUSE_WHEEL_UP = 0x00004000
MOUSE_WHEEL_DOWN = 0x00002000

EVT = {
    "COURSE_SELECTOR_L": BASE + 376,
    "FD_SWITCH_L": BASE + 378,
    "AT_ARM_SWITCH": BASE + 380,
    "N1_SWITCH": BASE + 381,
    "SPEED_SWITCH": BASE + 382,
    "CO_SWITCH": BASE + 383,
    "SPEED_SELECTOR": BASE + 384,
    "VNAV_SWITCH": BASE + 386,
    "SPD_INTV_SWITCH": BASE + 387,
    "BANK_ANGLE_SELECTOR": BASE + 389,
    "HEADING_SELECTOR": BASE + 390,
    "LVL_CHG_SWITCH": BASE + 391,
    "HDG_SEL_SWITCH": BASE + 392,
    "APP_SWITCH": BASE + 393,
    "ALT_HOLD_SWITCH": BASE + 394,
    "VS_SWITCH": BASE + 395,
    "VOR_LOC_SWITCH": BASE + 396,
    "LNAV_SWITCH": BASE + 397,
    "ALTITUDE_SELECTOR": BASE + 400,
    "VS_SELECTOR": BASE + 401,
    "CMD_A_SWITCH": BASE + 402,
    "CMD_B_SWITCH": BASE + 403,
    "CWS_A_SWITCH": BASE + 404,
    "CWS_B_SWITCH": BASE + 405,
    "DISENGAGE_BAR": BASE + 406,
    "FD_SWITCH_R": BASE + 407,
    "COURSE_SELECTOR_R": BASE + 409,
    "ALT_INTV_SWITCH": BASE + 885,
    "CRS_L_SET": BASE + 14500,
    "CRS_R_SET": BASE + 14501,
    "IAS_SET": BASE + 14502,
    "MACH_SET": BASE + 14503,
    "HDG_SET": BASE + 14504,
    "ALT_SET": BASE + 14505,
    "VS_SET": BASE + 14506,
}

# name -> (offset, struct format, count)
FALLBACK_LAYOUT = {
    "_size": 916,
    "MCP_Course": (416, "H", 2),
    "MCP_IASMach": (420, "f", 1),
    "MCP_IASBlank": (424, "?", 1),
    "MCP_IASOverspeedFlash": (425, "?", 1),
    "MCP_IASUnderspeedFlash": (426, "?", 1),
    "MCP_Heading": (428, "H", 1),
    "MCP_Altitude": (430, "H", 1),
    "MCP_VertSpeed": (432, "h", 1),
    "MCP_VertSpeedBlank": (434, "?", 1),
    "MCP_FDSw": (435, "?", 2),
    "MCP_ATArmSw": (437, "?", 1),
    "MCP_BankLimitSel": (438, "B", 1),
    "MCP_DisengageBar": (439, "?", 1),
    "MCP_annunFD": (440, "?", 2),
    "MCP_annunATArm": (442, "?", 1),
    "MCP_annunN1": (443, "?", 1),
    "MCP_annunSPEED": (444, "?", 1),
    "MCP_annunVNAV": (445, "?", 1),
    "MCP_annunLVL_CHG": (446, "?", 1),
    "MCP_annunHDG_SEL": (447, "?", 1),
    "MCP_annunLNAV": (448, "?", 1),
    "MCP_annunVOR_LOC": (449, "?", 1),
    "MCP_annunAPP": (450, "?", 1),
    "MCP_annunALT_HOLD": (451, "?", 1),
    "MCP_annunVS": (452, "?", 1),
    "MCP_annunCMD_A": (453, "?", 1),
    "MCP_annunCWS_A": (454, "?", 1),
    "MCP_annunCMD_B": (455, "?", 1),
    "MCP_annunCWS_B": (456, "?", 1),
    "MCP_indication_powered": (457, "?", 1),
}

_CTYPES = {"bool": (1, "?"), "char": (1, "b"), "signed char": (1, "b"), "unsigned char": (1, "B"),
           "short": (2, "h"), "unsigned short": (2, "H"), "int": (4, "i"), "unsigned int": (4, "I"),
           "long": (4, "i"), "unsigned long": (4, "I"), "float": (4, "f"), "double": (8, "d")}


def find_sdk_header():
    la = os.environ.get("LOCALAPPDATA", "")
    ad = os.environ.get("APPDATA", "")
    roots = []
    for cfg in (os.path.join(la, r"Packages\Microsoft.Limitless_8wekyb3d8bbwe\LocalCache\UserCfg.opt"),
                os.path.join(ad, r"Microsoft Flight Simulator 2024\UserCfg.opt"),
                os.path.join(la, r"Packages\Microsoft.FlightSimulator_8wekyb3d8bbwe\LocalCache\UserCfg.opt"),
                os.path.join(ad, r"Microsoft Flight Simulator\UserCfg.opt")):
        try:
            with open(cfg, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("InstalledPackagesPath"):
                        roots.append(line.split('"')[1])
        except OSError:
            pass
    for root in roots:
        for pat in ("Community/pmdg-aircraft-73*/Documentation/SDK/PMDG_NG3_SDK.h",
                    "Community/*/pmdg-aircraft-73*/Documentation/SDK/PMDG_NG3_SDK.h"):
            hits = sorted(glob.glob(os.path.join(root, pat)))
            if hits:
                return hits[0]
    return None


def layout_from_header(path):
    src = open(path, encoding="latin-1").read()
    body = re.search(r"struct PMDG_NG3_Data\s*\{(.*?)\n\};", src, re.S).group(1)
    body = re.sub(r"//[^\n]*", "", body)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    off, maxal, out = 0, 1, {}
    for decl in body.split(";"):
        decl = " ".join(decl.split())
        if not decl:
            continue
        m = re.match(r"^((?:unsigned |signed )?(?:bool|char|short|int|float|long|double))\s+(\w+)"
                     r"\s*(?:\[(\d+)\])?\s*(?:\[(\d+)\])?$", decl)
        if not m:
            raise ValueError(f"unexpected declaration in SDK header: {decl!r}")
        typ, name, d1, d2 = m.groups()
        size, fmt = _CTYPES[typ]
        n = (int(d1) if d1 else 1) * (int(d2) if d2 else 1)
        off = (off + size - 1) // size * size
        out[name] = (off, fmt, n)
        off += size * n
        maxal = max(maxal, size)
    out["_size"] = (off + maxal - 1) // maxal * maxal
    missing = [k for k in FALLBACK_LAYOUT if k not in out]
    if missing:
        raise ValueError(f"fields missing from SDK header: {missing}")
    return out


def load_layout(log=print):
    path = find_sdk_header()
    if path:
        try:
            lay = layout_from_header(path)
            log(f"PMDG 737 SDK header: {path} ({lay['_size']} bytes)")
            return lay
        except Exception as e:
            log(f"Could not parse the PMDG SDK header ({e}), using built in offsets.")
    else:
        log("PMDG 737 SDK header not found, using built in offsets (v4.0.63).")
    return dict(FALLBACK_LAYOUT)


def decode(layout, payload):
    d = {}
    for name in FALLBACK_LAYOUT:
        if name == "_size":
            continue
        off, fmt, n = layout[name]
        vals = struct.unpack_from("<" + fmt * n, payload, off)
        d[name] = vals if n > 1 else vals[0]
    return d

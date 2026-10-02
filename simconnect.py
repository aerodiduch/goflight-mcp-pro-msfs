"""Minimal ctypes wrapper for SimConnect.dll. Works with MSFS 2020 and 2024."""
import ctypes
import os
import struct
from ctypes import wintypes

RECV_ID_EXCEPTION = 1
RECV_ID_OPEN = 2
RECV_ID_QUIT = 3
RECV_ID_EVENT = 4
RECV_ID_EVENT_FILENAME = 6
RECV_ID_SIMOBJECT_DATA = 8
RECV_ID_SYSTEM_STATE = 15
RECV_ID_CLIENT_DATA = 16

PERIOD_ONCE = 1
PERIOD_VISUAL_FRAME = 2
PERIOD_SIM_FRAME = 3
PERIOD_SECOND = 4
CLIENT_DATA_PERIOD_ON_SET = 3
CLIENT_DATA_PERIOD_SECOND = 4
DATA_REQUEST_FLAG_CHANGED = 1
CLIENT_DATA_REQUEST_FLAG_CHANGED = 1

DATATYPE_INT32 = 1
DATATYPE_FLOAT64 = 4
DATATYPE_STRING256 = 9

OBJECT_ID_USER = 0
GROUP_PRIORITY_HIGHEST = 1
EVENT_FLAG_GROUPID_IS_PRIORITY = 0x10
UNUSED = 0xFFFFFFFF

E_FAIL = -2147467259


class SimConnectError(Exception):
    pass


class SimConnect:
    def __init__(self, dll_path=None):
        if dll_path is None:
            dll_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SimConnect.dll")
        self.dll = ctypes.WinDLL(dll_path)
        d = self.dll
        H = wintypes.HANDLE
        D = wintypes.DWORD
        d.SimConnect_Open.argtypes = [ctypes.POINTER(H), ctypes.c_char_p, wintypes.HWND, D, H, D]
        d.SimConnect_Close.argtypes = [H]
        d.SimConnect_GetNextDispatch.argtypes = [H, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(D)]
        d.SimConnect_MapClientEventToSimEvent.argtypes = [H, D, ctypes.c_char_p]
        d.SimConnect_TransmitClientEvent.argtypes = [H, D, D, D, D, D]
        d.SimConnect_MapClientDataNameToID.argtypes = [H, ctypes.c_char_p, D]
        d.SimConnect_AddToClientDataDefinition.argtypes = [H, D, D, D, ctypes.c_float, D]
        d.SimConnect_RequestClientData.argtypes = [H, D, D, D, D, D, D, D, D]
        d.SimConnect_AddToDataDefinition.argtypes = [H, D, ctypes.c_char_p, ctypes.c_char_p, D, ctypes.c_float, D]
        d.SimConnect_RequestDataOnSimObject.argtypes = [H, D, D, D, D, D, D, D, D]
        d.SimConnect_SubscribeToSystemEvent.argtypes = [H, D, ctypes.c_char_p]
        d.SimConnect_RequestSystemState.argtypes = [H, D, ctypes.c_char_p]
        for fn in ("SimConnect_Open", "SimConnect_Close", "SimConnect_GetNextDispatch",
                   "SimConnect_MapClientEventToSimEvent", "SimConnect_TransmitClientEvent",
                   "SimConnect_MapClientDataNameToID", "SimConnect_AddToClientDataDefinition",
                   "SimConnect_RequestClientData", "SimConnect_AddToDataDefinition",
                   "SimConnect_RequestDataOnSimObject", "SimConnect_SubscribeToSystemEvent",
                   "SimConnect_RequestSystemState"):
            getattr(d, fn).restype = ctypes.c_long
        self.h = None

    @property
    def connected(self):
        return self.h is not None

    def _chk(self, hr, what):
        if hr < 0:
            raise SimConnectError(f"{what} failed (0x{hr & 0xFFFFFFFF:08X})")

    def open(self, name="GoFlight MCP Pro Bridge"):
        h = wintypes.HANDLE()
        hr = self.dll.SimConnect_Open(ctypes.byref(h), name.encode(), None, 0, None, 0)
        if hr < 0:
            return False
        self.h = h
        return True

    def close(self):
        if self.h is not None:
            try:
                self.dll.SimConnect_Close(self.h)
            finally:
                self.h = None

    def map_event(self, event_id, name):
        self._chk(self.dll.SimConnect_MapClientEventToSimEvent(self.h, event_id, name.encode()), f"MapEvent {name}")

    def transmit(self, event_id, data=0):
        self._chk(self.dll.SimConnect_TransmitClientEvent(self.h, OBJECT_ID_USER, event_id, data & 0xFFFFFFFF,
                                                          GROUP_PRIORITY_HIGHEST, EVENT_FLAG_GROUPID_IS_PRIORITY),
                  "TransmitClientEvent")

    def map_client_data(self, name, client_data_id):
        self._chk(self.dll.SimConnect_MapClientDataNameToID(self.h, name.encode(), client_data_id), "MapClientDataNameToID")

    def add_client_data_def(self, define_id, offset, size):
        self._chk(self.dll.SimConnect_AddToClientDataDefinition(self.h, define_id, offset, size, 0.0, UNUSED),
                  "AddToClientDataDefinition")

    def request_client_data(self, client_data_id, request_id, define_id,
                            period=CLIENT_DATA_PERIOD_ON_SET, flags=CLIENT_DATA_REQUEST_FLAG_CHANGED):
        self._chk(self.dll.SimConnect_RequestClientData(self.h, client_data_id, request_id, define_id,
                                                        period, flags, 0, 0, 0), "RequestClientData")

    def add_data_def(self, define_id, name, units, datatype=DATATYPE_FLOAT64, epsilon=0.0):
        self._chk(self.dll.SimConnect_AddToDataDefinition(self.h, define_id, name.encode(),
                                                          units.encode() if units else None,
                                                          datatype, epsilon, UNUSED), f"AddToDataDefinition {name}")

    def request_data(self, request_id, define_id, period=PERIOD_SECOND, flags=DATA_REQUEST_FLAG_CHANGED):
        self._chk(self.dll.SimConnect_RequestDataOnSimObject(self.h, request_id, define_id, OBJECT_ID_USER,
                                                             period, flags, 0, 0, 0), "RequestDataOnSimObject")

    def subscribe_system_event(self, event_id, name):
        self._chk(self.dll.SimConnect_SubscribeToSystemEvent(self.h, event_id, name.encode()), f"Subscribe {name}")

    def request_system_state(self, request_id, name):
        self._chk(self.dll.SimConnect_RequestSystemState(self.h, request_id, name.encode()), f"SystemState {name}")

    def dispatch(self):
        """Yield (recv_id, raw bytes) for each pending message."""
        while self.h is not None:
            p = ctypes.c_void_p()
            n = wintypes.DWORD()
            hr = self.dll.SimConnect_GetNextDispatch(self.h, ctypes.byref(p), ctypes.byref(n))
            if hr < 0:
                if hr == E_FAIL:
                    return  # nothing pending
                raise SimConnectError(f"GetNextDispatch 0x{hr & 0xFFFFFFFF:08X}")
            if not p.value or n.value < 12:
                return
            raw = ctypes.string_at(p.value, n.value)
            _size, _ver, rid = struct.unpack_from("<III", raw, 0)
            yield rid, raw


def parse_object_data(raw):
    """SIMOBJECT_DATA or CLIENT_DATA -> (request_id, define_id, payload)."""
    req, _obj, define, _flags, _entry, _outof, _count = struct.unpack_from("<7I", raw, 12)
    return req, define, raw[40:]


def parse_event(raw):
    group, event, data = struct.unpack_from("<III", raw, 12)
    return event, data


def parse_exception(raw):
    exc, send_id, index = struct.unpack_from("<III", raw, 12)
    return exc, send_id, index


def parse_system_state(raw):
    req, integer, flt = struct.unpack_from("<IIf", raw, 12)
    s = raw[24:24 + 260].split(b"\0", 1)[0].decode("latin-1", "replace")
    return req, integer, flt, s


def parse_filename_event(raw):
    group, event, data = struct.unpack_from("<III", raw, 12)
    s = raw[24:24 + 260].split(b"\0", 1)[0].decode("latin-1", "replace")
    return event, s

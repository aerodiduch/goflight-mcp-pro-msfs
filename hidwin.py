"""Small Windows HID wrapper on top of ctypes, no external packages."""
import ctypes
from ctypes import wintypes

setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x1
FILE_SHARE_WRITE = 0x2
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
DIGCF_PRESENT = 0x2
DIGCF_DEVICEINTERFACE = 0x10
ERROR_IO_PENDING = 997
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x102
IOCTL_HID_SET_FEATURE = 0x000B0191


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", GUID),
                ("Flags", wintypes.DWORD), ("Reserved", ctypes.c_void_p)]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Size", wintypes.ULONG), ("VendorID", wintypes.USHORT),
                ("ProductID", wintypes.USHORT), ("VersionNumber", wintypes.USHORT)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [("Usage", wintypes.USHORT), ("UsagePage", wintypes.USHORT),
                ("InputReportByteLength", wintypes.USHORT),
                ("OutputReportByteLength", wintypes.USHORT),
                ("FeatureReportByteLength", wintypes.USHORT),
                ("Reserved", wintypes.USHORT * 17),
                ("NumberLinkCollectionNodes", wintypes.USHORT),
                ("NumberInputButtonCaps", wintypes.USHORT),
                ("NumberInputValueCaps", wintypes.USHORT),
                ("NumberInputDataIndices", wintypes.USHORT),
                ("NumberOutputButtonCaps", wintypes.USHORT),
                ("NumberOutputValueCaps", wintypes.USHORT),
                ("NumberOutputDataIndices", wintypes.USHORT),
                ("NumberFeatureButtonCaps", wintypes.USHORT),
                ("NumberFeatureValueCaps", wintypes.USHORT),
                ("NumberFeatureDataIndices", wintypes.USHORT)]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE)]


setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID),
                                                 wintypes.DWORD, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [wintypes.HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
                                                      ctypes.c_void_p, wintypes.DWORD,
                                                      ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                 wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                              ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(OVERLAPPED)]
kernel32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                     ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                     ctypes.POINTER(OVERLAPPED)]
kernel32.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED),
                                         ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.ResetEvent.argtypes = [wintypes.HANDLE]
kernel32.CancelIo.argtypes = [wintypes.HANDLE]
kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
hid.HidD_GetAttributes.argtypes = [wintypes.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
hid.HidP_GetCaps.restype = wintypes.LONG
hid.HidD_GetProductString.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]


def _open_path(path, access):
    return kernel32.CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                                OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)


def enumerate_devices(vid=None, pid=None):
    guid = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    devs = setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if devs == INVALID_HANDLE_VALUE:
        return
    try:
        idx = 0
        while True:
            ifd = SP_DEVICE_INTERFACE_DATA()
            ifd.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
            if not setupapi.SetupDiEnumDeviceInterfaces(devs, None, ctypes.byref(guid), idx, ctypes.byref(ifd)):
                break
            idx += 1
            needed = wintypes.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(devs, ctypes.byref(ifd), None, 0, ctypes.byref(needed), None)
            buf = ctypes.create_string_buffer(needed.value)
            # cbSize of SP_DEVICE_INTERFACE_DETAIL_DATA_W
            ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if not setupapi.SetupDiGetDeviceInterfaceDetailW(devs, ctypes.byref(ifd), buf, needed, None, None):
                continue
            path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            h = _open_path(path, 0)
            if h == INVALID_HANDLE_VALUE:
                continue
            try:
                attr = HIDD_ATTRIBUTES()
                attr.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
                if not hid.HidD_GetAttributes(h, ctypes.byref(attr)):
                    continue
                if vid is not None and attr.VendorID != vid:
                    continue
                if pid is not None and attr.ProductID != pid:
                    continue
                sbuf = ctypes.create_unicode_buffer(128)
                product = sbuf.value if hid.HidD_GetProductString(h, sbuf, ctypes.sizeof(sbuf)) else ""
                yield {"path": path, "vid": attr.VendorID, "pid": attr.ProductID,
                       "version": attr.VersionNumber, "product": product}
            finally:
                kernel32.CloseHandle(h)
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(devs)


class HidDevice:
    def __init__(self, path):
        self.path = path
        self.handle = _open_path(path, GENERIC_READ | GENERIC_WRITE)
        if self.handle == INVALID_HANDLE_VALUE:
            raise OSError(ctypes.get_last_error(), "Could not open the HID device (in use by another program?)")
        pp = ctypes.c_void_p()
        hid.HidD_GetPreparsedData(self.handle, ctypes.byref(pp))
        caps = HIDP_CAPS()
        hid.HidP_GetCaps(pp, ctypes.byref(caps))
        hid.HidD_FreePreparsedData(pp)
        self.caps = caps
        self.in_len = caps.InputReportByteLength
        self._rd_event = kernel32.CreateEventW(None, True, False, None)
        self._wr_event = kernel32.CreateEventW(None, True, False, None)
        self._rd_ov = None
        self._rd_buf = None
        self._leaked = []

    def set_feature_timeout(self, data, timeout_ms=150):
        """Send a feature report. Returns False if the device did not complete it in time.

        A request that never completes would otherwise block for the 5 s USB timeout.
        Cancelling it aborts the control transfer and the next SETUP resets the endpoint.
        """
        flen = self.caps.FeatureReportByteLength or len(data)
        buf = bytes(data)[:flen].ljust(flen, b"\0")
        cbuf = ctypes.create_string_buffer(buf, len(buf))
        ov = OVERLAPPED()
        ov.hEvent = self._wr_event
        kernel32.ResetEvent(self._wr_event)
        n = wintypes.DWORD()
        if kernel32.DeviceIoControl(self.handle, IOCTL_HID_SET_FEATURE, cbuf, len(buf), None, 0,
                                    ctypes.byref(n), ctypes.byref(ov)):
            return True
        err = ctypes.get_last_error()
        if err != ERROR_IO_PENDING:
            raise OSError(err, "Feature report write failed")
        if kernel32.WaitForSingleObject(self._wr_event, timeout_ms) == WAIT_OBJECT_0:
            if not kernel32.GetOverlappedResult(self.handle, ctypes.byref(ov), ctypes.byref(n), False):
                raise OSError(ctypes.get_last_error(), "Feature report write failed")
            return True
        kernel32.CancelIoEx(self.handle, ctypes.byref(ov))
        if kernel32.WaitForSingleObject(self._wr_event, 6000) != WAIT_OBJECT_0:
            self._leaked.append((cbuf, ov))  # still owned by the driver
        else:
            kernel32.GetOverlappedResult(self.handle, ctypes.byref(ov), ctypes.byref(n), False)
        return False

    def read(self, timeout_ms=0):
        """Next input report (report id first) or None on timeout."""
        if self._rd_ov is None:
            self._rd_buf = ctypes.create_string_buffer(self.in_len)
            self._rd_ov = OVERLAPPED()
            self._rd_ov.hEvent = self._rd_event
            kernel32.ResetEvent(self._rd_event)
            n = wintypes.DWORD()
            ok = kernel32.ReadFile(self.handle, self._rd_buf, self.in_len, ctypes.byref(n), ctypes.byref(self._rd_ov))
            if not ok:
                err = ctypes.get_last_error()
                if err != ERROR_IO_PENDING:
                    self._rd_ov = None
                    raise OSError(err, "Read failed (device unplugged?)")
        if kernel32.WaitForSingleObject(self._rd_event, timeout_ms) == WAIT_TIMEOUT:
            return None
        n = wintypes.DWORD()
        ok = kernel32.GetOverlappedResult(self.handle, ctypes.byref(self._rd_ov), ctypes.byref(n), False)
        self._rd_ov = None
        if not ok:
            raise OSError(ctypes.get_last_error(), "Read failed (device unplugged?)")
        return self._rd_buf.raw[: n.value]

    def close(self):
        if self.handle and self.handle != INVALID_HANDLE_VALUE:
            kernel32.CancelIo(self.handle)
            kernel32.CloseHandle(self.handle)
            self.handle = None
        for ev in (self._rd_event, self._wr_event):
            if ev:
                kernel32.CloseHandle(ev)
        self._rd_event = self._wr_event = None

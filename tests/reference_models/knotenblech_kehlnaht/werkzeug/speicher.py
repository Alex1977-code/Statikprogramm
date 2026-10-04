# -*- coding: utf-8 -*-
"""Speicherangaben unter Windows ohne psutil (02.10.2026)."""
import ctypes
from ctypes import wintypes


class _PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


class _MS(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


GB = float(2 ** 30)


def prozess() -> dict:
    """Arbeitssatz und Commit dieses Prozesses, jeweils jetzt und Spitze, in GB."""
    k32 = ctypes.WinDLL("kernel32")
    psapi = ctypes.WinDLL("psapi")
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    c = _PMC()
    c.cb = ctypes.sizeof(c)
    psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return {"arbeitssatz_GB": round(c.WorkingSetSize / GB, 2),
            "spitze_arbeitssatz_GB": round(c.PeakWorkingSetSize / GB, 2),
            "commit_GB": round(c.PagefileUsage / GB, 2),
            "spitze_commit_GB": round(c.PeakPagefileUsage / GB, 2)}


def system() -> dict:
    """Physischer Speicher und Commit-Grenze des Rechners, in GB."""
    k32 = ctypes.WinDLL("kernel32")
    s = _MS()
    s.dwLength = ctypes.sizeof(s)
    k32.GlobalMemoryStatusEx(ctypes.byref(s))
    return {"gesamt_GB": round(s.ullTotalPhys / GB, 1), "frei_GB": round(s.ullAvailPhys / GB, 1),
            "commit_grenze_GB": round(s.ullTotalPageFile / GB, 1),
            "commit_frei_GB": round(s.ullAvailPageFile / GB, 1)}

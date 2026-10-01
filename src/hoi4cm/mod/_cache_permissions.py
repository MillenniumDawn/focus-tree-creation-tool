"""Restrict scan-cache directories without optional runtime dependencies."""

import ctypes
import os
import sys
from ctypes import wintypes


def restrict_directory(path: str) -> None:
    """Make an existing directory private, or raise before opening its cache."""
    # A sys.platform branch lets type checkers skip the Windows-only ctypes API.
    if sys.platform != "win32":
        os.chmod(path, 0o700)
        return
    # chmod only changes the read-only attribute on Windows. Replace the DACL,
    # protecting it from parent inheritance, and inherit our ACE to children.
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    pointer = ctypes.c_void_p
    pointer_out = ctypes.POINTER(pointer)
    dword_out = ctypes.POINTER(wintypes.DWORD)
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [pointer]
    kernel.LocalFree.restype = pointer
    advapi.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        pointer,
        wintypes.DWORD,
        dword_out,
    ]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.ConvertSidToStringSidW.argtypes = [
        pointer,
        ctypes.POINTER(wintypes.LPWSTR),
    ]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        pointer_out,
        dword_out,
    ]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    advapi.GetSecurityDescriptorDacl.argtypes = [
        pointer,
        ctypes.POINTER(wintypes.BOOL),
        pointer_out,
        ctypes.POINTER(wintypes.BOOL),
    ]
    advapi.GetSecurityDescriptorDacl.restype = wintypes.BOOL
    advapi.SetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        pointer,
        pointer,
        pointer,
        pointer,
    ]
    advapi.SetNamedSecurityInfoW.restype = wintypes.DWORD

    token = wintypes.HANDLE()
    sid_text = wintypes.LPWSTR()
    descriptor = pointer()
    try:
        # TOKEN_QUERY, then TokenUser. The first TOKEN_USER field is its SID.
        if not advapi.OpenProcessToken(
            kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        if ctypes.get_last_error() != 122:  # ERROR_INSUFFICIENT_BUFFER
            raise ctypes.WinError(ctypes.get_last_error())
        user = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, user, size, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        sid = ctypes.cast(user, pointer_out)[0]
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(sid_text)):
            raise ctypes.WinError(ctypes.get_last_error())
        sddl = f"D:P(A;OICI;FA;;;{sid_text.value})"
        if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(descriptor), None
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        present, defaulted = wintypes.BOOL(), wintypes.BOOL()
        dacl = pointer()
        if not advapi.GetSecurityDescriptorDacl(
            descriptor,
            ctypes.byref(present),
            ctypes.byref(dacl),
            ctypes.byref(defaulted),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        # SE_FILE_OBJECT; DACL_SECURITY_INFORMATION with
        # PROTECTED_DACL_SECURITY_INFORMATION prevents parent inheritance.
        # Unlike SetFileSecurity, this propagates inheritable ACEs to existing files.
        error = advapi.SetNamedSecurityInfoW(
            path, 1, 0x80000004, None, None, dacl, None
        )
        if error:
            raise ctypes.WinError(error)
    finally:
        if descriptor:
            kernel.LocalFree(descriptor)
        if sid_text:
            kernel.LocalFree(sid_text)
        if token:
            kernel.CloseHandle(token)

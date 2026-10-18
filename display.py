"""Native Windows DPI setup and explicit conversion of layout pixels.

Import this module before creating the first Tk window. Fonts stay in points;
only pixel dimensions go through px(), so Windows never stretches a bitmap
of the whole interface to make it fit a high density display.
"""
from __future__ import annotations

import sys


def _windows_display_scale():
    if sys.platform != "win32":
        return 1.0
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    try:
        aware = user32.SetProcessDpiAwarenessContext
        aware.argtypes = (ctypes.c_void_p,)
        aware.restype = wintypes.BOOL
        # Windows 10: per-monitor v2. Access denied means a host or manifest
        # already chose an awareness mode; changing it again is unsupported.
        if not aware(ctypes.c_void_p(-4)) and ctypes.get_last_error() != 5:
            raise OSError("Per-monitor DPI context is unavailable")
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            user32.SetProcessDPIAware()
    try:
        return max(1.0, user32.GetDpiForSystem() / 96)
    except AttributeError:
        user32.GetDC.argtypes = (wintypes.HWND,)
        user32.GetDC.restype = wintypes.HDC
        user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
        ctypes.windll.gdi32.GetDeviceCaps.argtypes = (wintypes.HDC, ctypes.c_int)
        dc = user32.GetDC(None)
        try:
            return max(1.0, ctypes.windll.gdi32.GetDeviceCaps(dc, 88) / 96)
        finally:
            user32.ReleaseDC(None, dc)


SCALE = _windows_display_scale()


def px(value):
    """Convert a layout distance (or padding tuple) to native screen pixels."""
    if isinstance(value, (tuple, list)):
        return tuple(px(part) for part in value)
    return round(value * SCALE)


def window_geometry(window, width, height, margin=60, x=25, y=25):
    """Fit a logical window size within the current native screen resolution."""
    width = min(px(width), window.winfo_screenwidth() - px(margin))
    height = min(px(height), window.winfo_screenheight() - px(margin + 10))
    return f"{width}x{height}+{px(x)}+{px(y)}"

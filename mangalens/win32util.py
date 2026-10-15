"""Win32 底层封装（ctypes），不依赖第三方库。"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes as wt

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

# 少数句柄类型在 ctypes.wintypes 里没有定义，统一用 HANDLE 代替
HCURSOR = getattr(wt, "HCURSOR", wt.HANDLE)
HBRUSH = getattr(wt, "HBRUSH", wt.HANDLE)
HICON = getattr(wt, "HICON", wt.HANDLE)

# 窗口样式
WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

SW_SHOWNOACTIVATE = 4
SW_HIDE = 0

HWND_TOPMOST = -1
SWP_NOACTIVATE = 0x0010
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001

ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0
AC_SRC_ALPHA = 1
DIB_RGB_COLORS = 0

#: 让窗口不被屏幕截图/录屏捕获（Windows 10 2004+）
WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011

WM_DESTROY = 0x0002
WM_HOTKEY = 0x0312
WM_APP = 0x8000

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

VK_F6, VK_F7, VK_F8, VK_F9, VK_F10, VK_F11, VK_F12 = (
    0x75,
    0x76,
    0x77,
    0x78,
    0x79,
    0x7A,
    0x7B,
)

SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79


class POINT(ctypes.Structure):
    _fields_ = [("x", wt.LONG), ("y", wt.LONG)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wt.LONG), ("cy", wt.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wt.LONG),
        ("top", wt.LONG),
        ("right", wt.LONG),
        ("bottom", wt.LONG),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", wt.LONG),
        ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_byte),
        ("BlendFlags", ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat", ctypes.c_byte),
    ]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT),
        ("style", wt.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", HICON),
        ("hCursor", HCURSOR),
        ("hbrBackground", HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
        ("hIconSm", HICON),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wt.HWND),
        ("message", wt.UINT),
        ("wParam", wt.WPARAM),
        ("lParam", wt.LPARAM),
        ("time", wt.DWORD),
        ("pt", POINT),
        ("lPrivate", wt.DWORD),
    ]


def _declare() -> None:
    u, g = user32, gdi32
    u.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    u.RegisterClassExW.restype = wt.ATOM
    u.UnregisterClassW.argtypes = [wt.LPCWSTR, wt.HINSTANCE]
    u.CreateWindowExW.argtypes = [
        wt.DWORD,
        wt.LPCWSTR,
        wt.LPCWSTR,
        wt.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wt.HWND,
        wt.HMENU,
        wt.HINSTANCE,
        ctypes.c_void_p,
    ]
    u.CreateWindowExW.restype = wt.HWND
    u.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    u.DefWindowProcW.restype = LRESULT
    u.DestroyWindow.argtypes = [wt.HWND]
    u.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    u.SetWindowPos.argtypes = [
        wt.HWND,
        wt.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wt.UINT,
    ]
    u.GetMessageW.argtypes = [ctypes.POINTER(MSG), wt.HWND, wt.UINT, wt.UINT]
    u.GetMessageW.restype = ctypes.c_int
    u.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    u.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    u.DispatchMessageW.restype = LRESULT
    u.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    u.PostQuitMessage.argtypes = [ctypes.c_int]
    u.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
    u.RegisterHotKey.restype = wt.BOOL
    u.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
    u.GetDC.argtypes = [wt.HWND]
    u.GetDC.restype = wt.HDC
    u.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
    u.UpdateLayeredWindow.argtypes = [
        wt.HWND,
        wt.HDC,
        ctypes.POINTER(POINT),
        ctypes.POINTER(SIZE),
        wt.HDC,
        ctypes.POINTER(POINT),
        wt.DWORD,
        ctypes.POINTER(BLENDFUNCTION),
        wt.DWORD,
    ]
    u.UpdateLayeredWindow.restype = wt.BOOL
    u.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    u.SetWindowDisplayAffinity.argtypes = [wt.HWND, wt.DWORD]
    u.SetWindowDisplayAffinity.restype = wt.BOOL
    u.GetSystemMetrics.argtypes = [ctypes.c_int]
    u.GetSystemMetrics.restype = ctypes.c_int
    g.CreateCompatibleDC.argtypes = [wt.HDC]
    g.CreateCompatibleDC.restype = wt.HDC
    g.DeleteDC.argtypes = [wt.HDC]
    g.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
    g.SelectObject.restype = wt.HGDIOBJ
    g.DeleteObject.argtypes = [wt.HGDIOBJ]
    g.CreateDIBSection.argtypes = [
        wt.HDC,
        ctypes.POINTER(BITMAPINFO),
        wt.UINT,
        ctypes.POINTER(ctypes.c_void_p),
        wt.HANDLE,
        wt.DWORD,
    ]
    g.CreateDIBSection.restype = wt.HBITMAP


_declare()

# 方便使用的模块级别名
RegisterClassExW = user32.RegisterClassExW
CreateWindowExW = user32.CreateWindowExW
DefWindowProcW = user32.DefWindowProcW
DestroyWindow = user32.DestroyWindow
ShowWindow = user32.ShowWindow
SetWindowPos = user32.SetWindowPos
GetMessageW = user32.GetMessageW
TranslateMessage = user32.TranslateMessage
DispatchMessageW = user32.DispatchMessageW
PostMessageW = user32.PostMessageW
PostQuitMessage = user32.PostQuitMessage
UpdateLayeredWindow = user32.UpdateLayeredWindow
SetWindowDisplayAffinity = user32.SetWindowDisplayAffinity


def enable_dpi_awareness() -> None:
    """让截图坐标和窗口坐标都使用物理像素。"""

    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except Exception:
        user32.SetProcessDPIAware()


def virtual_screen() -> tuple[int, int, int, int]:
    """整个桌面的 (left, top, width, height)。"""

    g = user32.GetSystemMetrics
    left, top = g(SM_XVIRTUALSCREEN), g(SM_YVIRTUALSCREEN)
    return left, top, g(SM_CXVIRTUALSCREEN), g(SM_CYVIRTUALSCREEN)


def cursor_pos() -> tuple[int, int]:
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


_SINGLE_INSTANCE_MUTEX = None


def acquire_single_instance(name: str = "MangaLensSingleInstance") -> bool:
    """同一时间只允许运行一个实例。返回 False 表示已经有实例在跑。"""
    global _SINGLE_INSTANCE_MUTEX
    if os.name != "nt":
        return True
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
    kernel32.CreateMutexW.restype = wt.HANDLE
    _SINGLE_INSTANCE_MUTEX = kernel32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != 183


def message_box(text: str, title: str = "MangaLens", flags: int = 0x40) -> None:
    """弹一个系统提示框（0x40 = 信息图标）。"""
    try:
        user32.MessageBoxW.argtypes = [wt.HWND, wt.LPCWSTR, wt.LPCWSTR, wt.UINT]
        user32.MessageBoxW(None, text, title, flags)
    except Exception:
        pass


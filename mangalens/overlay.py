"""置顶、点击穿透的覆盖层窗口（Win32 分层窗口 + UpdateLayeredWindow）。"""

from __future__ import annotations

import ctypes
import queue
import threading
from ctypes import wintypes as wt

import numpy as np

from . import APP_NAME
from .win32util import (
    AC_SRC_ALPHA,
    AC_SRC_OVER,
    BITMAPINFO,
    BLENDFUNCTION,
    DIB_RGB_COLORS,
    HWND_TOPMOST,
    MOD_NOREPEAT,
    MSG,
    POINT,
    SIZE,
    SW_HIDE,
    SW_SHOWNOACTIVATE,
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOSIZE,
    ULW_ALPHA,
    WDA_EXCLUDEFROMCAPTURE,
    WM_APP,
    WM_DESTROY,
    WM_HOTKEY,
    WNDCLASSEXW,
    WNDPROC,
    WS_EX_LAYERED,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    WS_EX_TOPMOST,
    WS_EX_TRANSPARENT,
    WS_POPUP,
    DefWindowProcW,
    DestroyWindow,
    DispatchMessageW,
    PostMessageW,
    PostQuitMessage,
    RegisterClassExW,
    ShowWindow,
    TranslateMessage,
    UpdateLayeredWindow,
    enable_dpi_awareness,
    gdi32,
    user32,
)

WM_FRAME = WM_APP + 1
WM_VISIBLE = WM_APP + 2
WM_CLOSE = WM_APP + 3

_CLASS_NAME = f"{APP_NAME}OverlayWindow"


def to_premultiplied_bgra(rgba: np.ndarray, opacity: float = 1.0) -> bytes:
    """RGBA -> 预乘 alpha 的 BGRA 字节串（UpdateLayeredWindow 需要）。"""

    if rgba.dtype != np.uint8:
        rgba = rgba.astype(np.uint8, copy=False)
    alpha = rgba[:, :, 3].astype(np.uint16)
    if opacity < 1.0:
        alpha = (alpha * max(0.0, opacity)).astype(np.uint16)
    out = np.empty(rgba.shape, np.uint8)
    scale = alpha[:, :, None]
    # RGB 预乘 alpha，并按 BGRA 排列
    for src, dst in ((2, 0), (1, 1), (0, 2)):
        out[:, :, dst] = (rgba[:, :, src].astype(np.uint16) * scale[:, :, 0] // 255).astype(
            np.uint8
        )
    out[:, :, 3] = alpha.astype(np.uint8)
    return out.tobytes()


class Overlay:
    """覆盖层窗口，必须在自己的线程里创建和刷新。"""

    def __init__(
        self,
        hotkeys: dict[str, tuple[int, int, str]] | None = None,
        hide_from_capture: bool = True,
    ) -> None:
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.hotkeys = dict(hotkeys or {})
        self.hide_from_capture = hide_from_capture
        self._hwnd: int | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._frame: tuple[int, int, int, int, bytes] | None = None
        self._visible = True
        self._ready = threading.Event()
        self._hotkey_names: dict[int, str] = {}
        self.excluded_from_capture = False
        self._wndproc = None  # 保持引用，避免被回收
        self._mem_dc = None
        self._dib = None
        self._dib_size = (0, 0)
        self._screen_dc = None
        self._win_rect: tuple[int, int, int, int] | None = None

    # ------------------------------------------------------------------ 生命周期
    @property
    def hwnd(self) -> int | None:
        return self._hwnd

    def start(self, timeout: float = 5.0) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="overlay", daemon=True
        )
        self._thread.start()
        self._ready.wait(timeout)

    def stop(self) -> None:
        if self._hwnd:
            PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None

    # ------------------------------------------------------------------ 线程
    def _run(self) -> None:
        enable_dpi_awareness()
        self._wndproc = WNDPROC(self._on_message)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = None
        wc.lpszClassName = _CLASS_NAME
        if not RegisterClassExW(ctypes.byref(wc)):
            # 类名已存在时也能继续用
            if ctypes.get_last_error() not in (1410,):
                self._ready.set()
        ex_style = (
            WS_EX_LAYERED
            | WS_EX_TRANSPARENT
            | WS_EX_TOPMOST
            | WS_EX_TOOLWINDOW
            | WS_EX_NOACTIVATE
        )
        hwnd = user32.CreateWindowExW(
            ex_style,
            _CLASS_NAME,
            APP_NAME,
            WS_POPUP,
            0,
            0,
            1,
            1,
            None,
            None,
            None,
            None,
        )
        self._hwnd = hwnd
        self._screen_dc = user32.GetDC(None)
        self._mem_dc = gdi32.CreateCompatibleDC(self._screen_dc)
        self.excluded_from_capture = bool(
            self.hide_from_capture
            and user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        )
        self.events.put(("capture_exclusion", self.excluded_from_capture))
        ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        self._register_hotkeys(hwnd)
        self._ready.set()

        msg = MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            TranslateMessage(ctypes.byref(msg))
            DispatchMessageW(ctypes.byref(msg))
        self._cleanup()

    def _register_hotkeys(self, hwnd) -> None:
        for index, (name, spec) in enumerate(self.hotkeys.items(), start=1):
            modifiers, vk = spec[0], spec[1]
            ok = user32.RegisterHotKey(hwnd, index, modifiers | MOD_NOREPEAT, vk)
            if ok:
                self._hotkey_names[index] = name
            else:
                self.events.put(("hotkey_failed", name))

    def _on_message(self, hwnd, msg, wparam, lparam):
        if msg == WM_FRAME:
            self._paint()
            return 0
        if msg == WM_VISIBLE:
            self._visible = bool(wparam)
            ShowWindow(hwnd, SW_SHOWNOACTIVATE if wparam else SW_HIDE)
            return 0
        if msg == WM_HOTKEY:
            name = self._hotkey_names.get(int(wparam))
            if name:
                self.events.put(("hotkey", name))
            return 0
        if msg == WM_CLOSE:
            DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            PostQuitMessage(0)
            return 0
        return DefWindowProcW(hwnd, msg, wparam, lparam)

    def _cleanup(self) -> None:
        for index in list(self._hotkey_names):
            user32.UnregisterHotKey(self._hwnd, index)
        if self._dib:
            gdi32.DeleteObject(self._dib)
            self._dib = None
            self._dib_size = (0, 0)
        if self._mem_dc:
            gdi32.DeleteDC(self._mem_dc)
            self._mem_dc = None
        if self._screen_dc:
            user32.ReleaseDC(None, self._screen_dc)
            self._screen_dc = None

    # ------------------------------------------------------------------ 绘制
    def _ensure_dib(self, width: int, height: int) -> bool:
        if self._dib_size == (width, height) and self._dib:
            return True
        if self._dib:
            gdi32.DeleteObject(self._dib)
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(info.bmiHeader)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height  # 自上而下
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0  # BI_RGB
        self._bits = ctypes.c_void_p()
        self._dib = gdi32.CreateDIBSection(
            self._screen_dc,
            ctypes.byref(info),
            DIB_RGB_COLORS,
            ctypes.byref(self._bits),
            None,
            0,
        )
        if not self._dib:
            self._dib_size = (0, 0)
            return False
        gdi32.SelectObject(self._mem_dc, self._dib)
        self._dib_size = (width, height)
        return True

    def _paint(self) -> None:
        with self._lock:
            frame = self._frame
        if not frame or not self._hwnd:
            return
        x, y, width, height, payload = frame
        if not self._ensure_dib(width, height):
            return
        ctypes.memmove(self._bits, payload, len(payload))

        if self._win_rect != (x, y, width, height):
            user32.SetWindowPos(
                self._hwnd,
                HWND_TOPMOST,
                x,
                y,
                width,
                height,
                SWP_NOACTIVATE,
            )
            self._win_rect = (x, y, width, height)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        dst = POINT(x, y)
        size = SIZE(width, height)
        src = POINT(0, 0)
        UpdateLayeredWindow(
            self._hwnd,
            self._screen_dc,
            ctypes.byref(dst),
            ctypes.byref(size),
            self._mem_dc,
            ctypes.byref(src),
            0,
            ctypes.byref(blend),
            ULW_ALPHA,
        )

    # ------------------------------------------------------------------ 对外
    def push(
        self,
        rect: tuple[int, int, int, int],
        overlay_rgba: np.ndarray,
        opacity: float = 1.0,
    ) -> None:
        """rect = 屏幕坐标 (left, top, width, height)。"""

        x, y, width, height = (int(v) for v in rect)
        if overlay_rgba.shape[0] != height or overlay_rgba.shape[1] != width:
            return
        payload = to_premultiplied_bgra(overlay_rgba, opacity)
        with self._lock:
            self._frame = (x, y, width, height, payload)
        if self._hwnd:
            PostMessageW(self._hwnd, WM_FRAME, 0, 0)

    def set_visible(self, visible: bool) -> None:
        if self._hwnd:
            PostMessageW(self._hwnd, WM_VISIBLE, 1 if visible else 0, 0)

    def raise_above(self, other_hwnd: int) -> None:
        """把自己压到某个窗口下面，避免挡住控制面板。"""

        if self._hwnd and other_hwnd:
            user32.SetWindowPos(
                self._hwnd,
                other_hwnd,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )

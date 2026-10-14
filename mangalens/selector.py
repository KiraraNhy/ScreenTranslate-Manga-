"""全屏拖拽框选区域。"""

from __future__ import annotations

import tkinter as tk

from .win32util import virtual_screen


def pick_region(root: tk.Misc) -> tuple[int, int, int, int] | None:
    """弹出全屏遮罩让用户拖一个矩形，返回屏幕坐标 (left, top, width, height)。"""

    left, top, width, height = virtual_screen()
    result: dict[str, tuple[int, int, int, int] | None] = {"rect": None}

    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    try:
        win.attributes("-alpha", 0.28)
    except tk.TclError:
        pass
    win.geometry(f"{width}x{height}+{left}+{top}")
    canvas = tk.Canvas(win, bg="#0d1b2a", highlightthickness=0, cursor="crosshair")
    canvas.pack(fill="both", expand=True)

    state: dict[str, object] = {"start": None, "rect_id": None, "text_id": None}

    def redraw(x0: int, y0: int, x1: int, y1: int) -> None:
        for key in ("rect_id", "text_id"):
            item = state.get(key)
            if item:
                canvas.delete(item)
        state["rect_id"] = canvas.create_rectangle(
            x0, y0, x1, y1, outline="#4cc9f0", width=2
        )
        state["text_id"] = canvas.create_text(
            x0 + 8,
            max(14, y0 - 12),
            text=f"{abs(x1 - x0)} x {abs(y1 - y0)}",
            fill="#caf0f8",
            anchor="w",
        )

    def on_press(event) -> None:
        state["start"] = (event.x, event.y)
        redraw(event.x, event.y, event.x, event.y)

    def on_drag(event) -> None:
        start = state.get("start")
        if start:
            redraw(start[0], start[1], event.x, event.y)

    def on_release(event) -> None:
        start = state.get("start")
        if not start:
            win.destroy()
            return
        x0, y0 = start
        x1, y1 = event.x, event.y
        rx0, rx1 = sorted((x0, x1))
        ry0, ry1 = sorted((y0, y1))
        if rx1 - rx0 < 24 or ry1 - ry0 < 24:
            win.destroy()
            return
        result["rect"] = (left + rx0, top + ry0, rx1 - rx0, ry1 - ry0)
        win.destroy()

    def on_cancel(_event=None) -> None:
        win.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    canvas.bind("<ButtonPress-3>", on_cancel)
    win.bind("<Escape>", on_cancel)
    win.focus_force()
    win.grab_set()
    root.wait_window(win)
    return result["rect"]

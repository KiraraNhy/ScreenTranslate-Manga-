"""应用装配：控制面板 + 覆盖层 + 翻译流程。"""

from __future__ import annotations

import queue
import time
import os
import tkinter as tk

from .border import cached_border
from .config import LANGUAGES, TARGETS, Config
from .hotkeys import HOTKEYS
from .overlay import Overlay
from .pipeline import Pipeline, Settings, resolve_region
from .selector import pick_region
from .ui import ControlPanel
from .win32util import enable_dpi_awareness, virtual_screen


class App:
    def __init__(self, cfg: Config) -> None:
        enable_dpi_awareness()
        self.cfg = cfg
        self.events: queue.Queue = queue.Queue()
        self.overlay = Overlay(HOTKEYS, hide_from_capture=bool(cfg.hide_from_capture))
        self.overlay.start()
        self.settings = Settings(cfg)
        self._panel_rect: tuple[int, int, int, int] | None = None
        self.pipeline = Pipeline(
            self.settings, self.overlay, self.events, panel_rect=lambda: self._panel_rect
        )
        self.root = tk.Tk()
        self.panel = ControlPanel(self.root, self)
        if cfg.panel_pos and len(cfg.panel_pos) == 2:
            self._apply_panel_pos(cfg.panel_pos)
        self._save_job = None
        self._last_raise = 0.0
        self._engine_info = ""
        self._failed_hotkeys: list[str] = []
        self._debug = bool(os.environ.get("MANGALENS_DEBUG"))
        self._last_stats = ""
        self.pipeline.start()
        self.panel.set_status(self._describe())
        try:
            # 立刻回写一次：把旧配置里可能残留的明文密钥搬进加密文件
            self.cfg.save()
        except Exception:
            pass
        self.root.after(80, self._poll)

    # ------------------------------------------------------------------ 生命周期
    def run(self) -> None:
        self.root.mainloop()

    def _apply_panel_pos(self, pos) -> None:
        """把控制面板限制在可见屏幕内（换显示器或改分辨率后不会跑到屏幕外）。"""
        self.root.update_idletasks()
        left, top, width, height = virtual_screen()
        panel_w = max(320, self.root.winfo_width())
        panel_h = max(200, self.root.winfo_height())
        x = min(max(int(pos[0]), left), max(left, left + width - panel_w))
        y = min(max(int(pos[1]), top), max(top, top + height - panel_h))
        self.root.geometry(f"+{x}+{y}")

    def action_quit(self) -> None:
        try:
            self._save_now()
        except Exception:
            pass
        self.pipeline.stop()
        self.overlay.stop()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ 动作
    def action_pick(self) -> None:
        self.overlay.set_visible(False)
        self.root.attributes("-topmost", False)
        try:
            rect = pick_region(self.root)
        finally:
            self.root.attributes("-topmost", True)
            self.overlay.set_visible(self.cfg.enabled)
        if rect:
            self.apply_config(region=list(rect), mode="region")
            self.set_enabled(True)  # 圈定区域后直接开始翻译
            self._show_border()
            self.panel.sync_enabled(True)
            self.pipeline.clear()
            self.pipeline.force_refresh()

    def action_fullscreen(self) -> None:
        mode = "region" if self.cfg.mode == "fullscreen" else "fullscreen"
        if mode == "region" and not self.cfg.region:
            self.panel.set_status("还没有框选区域")
            return
        self.apply_config(mode=mode)
        self.set_enabled(True)
        self._show_border()
        self.panel.sync_enabled(True)
        self.pipeline.clear()
        self.pipeline.force_refresh()

    def action_refresh(self) -> None:
        self.pipeline.force_refresh()

    def action_clear(self) -> None:
        self.pipeline.clear()

    def action_toggle(self) -> None:
        """开始 / 暂停翻译。"""

        self.set_enabled(not self.cfg.enabled)
        self.panel.sync_enabled(self.cfg.enabled)

    def set_enabled(self, value: bool) -> None:
        self.apply_config(enabled=bool(value))
        self.overlay.set_visible(bool(value))
        if not value:
            self.pipeline.clear()
        else:
            self.pipeline.force_refresh()

    def _show_border(self) -> None:
        """立刻把选区描边画出来（不用等下一次识别）。"""

        region = resolve_region(self.cfg)
        if not region:
            return
        left, top, width, height = region
        try:
            self.overlay.push(region, cached_border(int(width), int(height)), 1.0)
        except Exception:
            pass

    def _on_hotkey(self, name: str) -> None:
        if name == "toggle":
            self.action_toggle()
        elif name == "pick":
            self.action_pick()
        elif name == "mode":
            self.action_fullscreen()
        elif name == "refresh":
            self.action_refresh()

    # ------------------------------------------------------------------ 配置
    def apply_config(self, **changes) -> None:
        for key, value in changes.items():
            setattr(self.cfg, key, value)
        self.settings.update(self.cfg)
        self._schedule_save()
        self.panel.set_status(self._describe())

    def _schedule_save(self) -> None:
        if self._save_job is not None:
            try:
                self.root.after_cancel(self._save_job)
            except Exception:
                pass
        self._save_job = self.root.after(1200, self._save_now)

    def _save_now(self) -> None:
        self._save_job = None
        try:
            self.cfg.panel_pos = [
                int(self.root.winfo_rootx()),
                int(self.root.winfo_rooty()),
            ]
        except Exception:
            pass
        try:
            self.cfg.save()
        except Exception:
            pass

    # ------------------------------------------------------------------ 状态
    def _describe(self) -> str:
        region = resolve_region(self.cfg)
        size = f"{region[2]}x{region[3]}" if region else "未选择"
        source = LANGUAGES.get(self.cfg.source_lang, self.cfg.source_lang)
        target = TARGETS.get(self.cfg.target_lang, self.cfg.target_lang)
        if region is None:
            state = "待框选"
        elif self.cfg.enabled:
            state = "翻译中"
        else:
            state = "已暂停"
        parts = [f"{state}", f"区域 {size}", f"{source} -> {target}"]
        if self._engine_info:
            parts.append(self._engine_info)
        if self._failed_hotkeys:
            parts.append("快捷键被占用：" + "、".join(self._failed_hotkeys))
        return " ｜ ".join(parts) + self._hint()

    def _hint(self) -> str:
        if not self.cfg.region and self.cfg.mode != "fullscreen":
            return " ｜ 每次启动都要重新框选区域"
        return ""

    def _refresh_panel_rect(self) -> None:
        try:
            if self.root.state() == "iconic":
                self._panel_rect = None
                return
            self._panel_rect = (
                int(self.root.winfo_rootx()),
                int(self.root.winfo_rooty()),
                int(self.root.winfo_width()),
                int(self.root.winfo_height()),
            )
        except tk.TclError:
            self._panel_rect = None

    def _keep_above_panel(self) -> None:
        try:
            hwnd = int(self.root.winfo_id())
        except tk.TclError:
            return
        self.overlay.raise_above(hwnd)

    # ------------------------------------------------------------------ 轮询
    def _poll(self) -> None:
        self._refresh_panel_rect()
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                text = str(payload)
                if text.startswith("识别引擎："):
                    self._engine_info = text
                self.panel.set_status(self._describe() + f" ｜ {text}")
                if self._debug:
                    print("[status]", text, flush=True)
            elif kind == "stats":
                self._last_stats = self._format_stats(payload)
                self.panel.set_stats(self._last_stats)
                if self._debug:
                    print("[stats]", self._last_stats, flush=True)
            elif kind == "stage":
                stage = str(payload)
                self.panel.set_stats(f"正在{stage}…")
                if self._debug:
                    print("[stage]", stage, flush=True)
        while True:
            try:
                kind, payload = self.overlay.events.get_nowait()
            except queue.Empty:
                break
            if kind == "hotkey":
                self._on_hotkey(str(payload))
            elif kind == "hotkey_failed":
                name = str(payload)
                if name not in self._failed_hotkeys:
                    self._failed_hotkeys.append(name)
                self.panel.set_status(self._describe())
                if self._debug:
                    print("[hotkey] 注册失败:", name, flush=True)

        now = time.monotonic()
        if now - self._last_raise > 2.0:
            self._last_raise = now
            self._keep_above_panel()
        self.root.after(90, self._poll)

    @staticmethod
    def _format_stats(payload) -> str:
        timings = payload.get("timings", {})
        return (
            f"{payload.get('blocks', 0)} 个文本块，已译 {payload.get('translated', 0)} 个 ｜ "
            f"识别 {timings.get('ocr', 0):.0f}ms  翻译 {timings.get('translate', 0):.0f}ms  "
            f"绘制 {timings.get('render', 0):.0f}ms  合计 {payload.get('total_ms', 0):.0f}ms"
        )

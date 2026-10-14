"""控制面板。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import APP_TITLE
from . import ocr as ocr_registry
from . import translate as tr_registry
from .config import LANGUAGES, TARGETS


class ControlPanel:
    def __init__(self, root: tk.Tk, app) -> None:
        self.root = root
        self.app = app
        root.title(APP_TITLE)
        root.resizable(False, False)
        root.attributes("-topmost", True)
        try:
            ttk.Style().theme_use("vista")
        except tk.TclError:
            pass

        cfg = app.cfg
        self.var_source = tk.StringVar(value=LANGUAGES.get(cfg.source_lang, "自动检测"))
        self.var_target = tk.StringVar(value=TARGETS.get(cfg.target_lang, "简体中文"))
        self.var_ocr = tk.StringVar(value=self._ocr_label(cfg.ocr_backend))
        self.var_tr = tk.StringVar(value=tr_registry.label_of(cfg.translator))
        self.var_fps = tk.DoubleVar(value=float(cfg.fps))
        self.var_opacity = tk.DoubleVar(value=float(cfg.opacity) * 100)
        self.var_scale = tk.DoubleVar(value=float(cfg.font_scale) * 100)
        self.var_erase = tk.BooleanVar(value=cfg.erase_original)
        self.var_outline = tk.BooleanVar(value=cfg.outline)
        self.var_horizontal = tk.BooleanVar(value=getattr(cfg, "force_horizontal", True))
        self.var_enabled = tk.BooleanVar(value=cfg.enabled)
        self.var_toggle = tk.StringVar()
        self.var_status = tk.StringVar(value="准备中…")
        self.var_stats = tk.StringVar(value="")

        frame = ttk.Frame(root, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)

        ttk.Label(frame, text="原文").grid(row=0, column=0, sticky="w", pady=3)
        source_box = ttk.Combobox(
            frame,
            textvariable=self.var_source,
            values=list(LANGUAGES.values()),
            state="readonly",
            width=12,
        )
        source_box.grid(row=0, column=1, sticky="ew", padx=(6, 12))
        source_box.bind("<<ComboboxSelected>>", self._on_source)

        ttk.Label(frame, text="译成").grid(row=0, column=2, sticky="w", pady=3)
        target_box = ttk.Combobox(
            frame,
            textvariable=self.var_target,
            values=list(TARGETS.values()),
            state="readonly",
            width=12,
        )
        target_box.grid(row=0, column=3, sticky="ew", padx=(6, 0))
        target_box.bind("<<ComboboxSelected>>", self._on_target)

        ttk.Label(frame, text="识别").grid(row=1, column=0, sticky="w", pady=3)
        ocr_box = ttk.Combobox(
            frame,
            textvariable=self.var_ocr,
            values=self._ocr_choices(),
            state="readonly",
            width=22,
        )
        ocr_box.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(6, 0))
        ocr_box.bind("<<ComboboxSelected>>", self._on_ocr)

        ttk.Label(frame, text="翻译").grid(row=2, column=0, sticky="w", pady=3)
        tr_box = ttk.Combobox(
            frame,
            textvariable=self.var_tr,
            values=[tr_registry.label_of(n) for n in tr_registry.names()],
            state="readonly",
            width=22,
        )
        tr_box.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(6, 6))
        tr_box.bind("<<ComboboxSelected>>", self._on_translator)
        ttk.Button(frame, text="设置", width=6, command=self.open_translate_settings).grid(
            row=2, column=3, sticky="ew"
        )

        buttons = ttk.Frame(frame)
        try:
            ttk.Style().configure(
                "Toggle.TButton",
                font=("Microsoft YaHei UI", 10, "bold"),
                padding=(8, 6),
            )
            toggle_style = "Toggle.TButton"
        except tk.TclError:
            toggle_style = "TButton"
        self.toggle_button = ttk.Button(
            frame,
            textvariable=self.var_toggle,
            command=self._on_toggle,
            style=toggle_style,
        )
        self.toggle_button.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(12, 6))
        self._sync_toggle_label()

        buttons.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(0, 4))
        for index in range(4):
            buttons.columnconfigure(index, weight=1)
        ttk.Button(buttons, text="框选区域", command=app.action_pick).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(buttons, text="全屏", command=app.action_fullscreen).grid(
            row=0, column=1, sticky="ew", padx=4
        )
        ttk.Button(buttons, text="重新翻译", command=app.action_refresh).grid(
            row=0, column=2, sticky="ew", padx=4
        )
        ttk.Button(buttons, text="清空", command=app.action_clear).grid(
            row=0, column=3, sticky="ew", padx=(4, 0)
        )

        self._slider(
            frame, 5, "检查频率", self.var_fps, 0.5, 10.0, 0.5, self._on_fps, "帧/秒"
        )
        self._slider(frame, 6, "不透明", self.var_opacity, 20, 100, 5, self._on_opacity, "%")
        self._slider(frame, 7, "字号", self.var_scale, 60, 180, 5, self._on_scale, "%")

        checks = ttk.Frame(frame)
        checks.grid(row=8, column=0, columnspan=4, sticky="w", pady=(6, 2))
        ttk.Checkbutton(
            checks, text="抹除原文", variable=self.var_erase, command=self._on_erase
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Checkbutton(
            checks, text="文字描边", variable=self.var_outline, command=self._on_outline
        ).grid(row=0, column=1, sticky="w", padx=10)
        ttk.Checkbutton(
            checks,
            text="中文横排",
            variable=self.var_horizontal,
            command=self._on_horizontal,
        ).grid(row=0, column=2, sticky="w", padx=(10, 0))

        ttk.Separator(frame, orient="horizontal").grid(
            row=9, column=0, columnspan=4, sticky="ew", pady=8
        )
        ttk.Label(
            frame, textvariable=self.var_status, wraplength=380, justify="left"
        ).grid(row=10, column=0, columnspan=4, sticky="w")
        ttk.Label(
            frame, textvariable=self.var_stats, wraplength=380, justify="left"
        ).grid(row=11, column=0, columnspan=4, sticky="w")

        root.protocol("WM_DELETE_WINDOW", app.action_quit)

    # ------------------------------------------------------------------ 组件
    def _slider(self, parent, row, label, variable, low, high, step, command, unit):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        scale = ttk.Scale(
            parent,
            from_=low,
            to=high,
            variable=variable,
            command=lambda _v: command(),
        )
        scale.grid(row=row, column=1, columnspan=3, sticky="ew", padx=(6, 40))
        text = ttk.Label(parent, textvariable=variable, width=6)
        text.grid(row=row, column=3, sticky="e")
        variable.trace_add("write", lambda *_: text.configure(text=f"{variable.get():.0f}{unit}"))
        text.configure(text=f"{variable.get():.0f}{unit}")

    def _ocr_choices(self) -> list[str]:
        self._ocr_map = {"auto": "自动选择"}
        for name in ocr_registry.all_names():
            available = name in ocr_registry.available_names()
            label = ocr_registry.label_of(name)
            self._ocr_map[label if available else f"{label}（未安装）"] = name
        return list(self._ocr_map)

    def _ocr_label(self, name: str) -> str:
        if not hasattr(self, "_ocr_map"):
            self._ocr_choices()
        for label, value in self._ocr_map.items():
            if value == name:
                return label
        return self._ocr_map.get("auto", "自动选择")

    # ------------------------------------------------------------------ 回调
    def _on_source(self, _event=None) -> None:
        for code, label in LANGUAGES.items():
            if label == self.var_source.get():
                self.app.apply_config(source_lang=code)
                return

    def _on_target(self, _event=None) -> None:
        for code, label in TARGETS.items():
            if label == self.var_target.get():
                self.app.apply_config(target_lang=code)
                return

    def _on_ocr(self, _event=None) -> None:
        name = self._ocr_map.get(self.var_ocr.get(), "auto")
        self.app.apply_config(ocr_backend=name)

    def _on_translator(self, _event=None) -> None:
        label = self.var_tr.get()
        for name in tr_registry.names():
            if tr_registry.label_of(name) == label:
                self.app.apply_config(translator=name)
                if name in ("llm", "deepl", "mymemory") and not self._is_configured(name):
                    self.open_translate_settings()
                return

    def _is_configured(self, name: str) -> bool:
        cfg = self.app.cfg
        if name == "llm":
            return bool(cfg.llm_api_key) or cfg.llm_preset == "ollama"
        if name == "deepl":
            return bool(cfg.deepl_api_key)
        return True

    # ------------------------------------------------------------- 翻译设置
    def open_translate_settings(self) -> None:
        cfg = self.app.cfg
        dialog = tk.Toplevel(self.root)
        dialog.title("翻译服务设置")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)

        body = ttk.Frame(dialog, padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        preset_names = [v[0] for v in tr_registry.LLM_PRESETS.values()]
        current = tr_registry.LLM_PRESETS.get(cfg.llm_preset)
        var_preset = tk.StringVar(value=current[0] if current else preset_names[0])
        var_key = tk.StringVar(value=cfg.llm_api_key)
        var_model = tk.StringVar(value=cfg.llm_model)
        var_email = tk.StringVar(value=getattr(cfg, "memory_email", ""))

        ttk.Label(body, text="大模型服务商").grid(row=0, column=0, sticky="w", pady=4)
        preset_box = ttk.Combobox(
            body,
            textvariable=var_preset,
            values=preset_names,
            state="readonly",
            width=26,
        )
        preset_box.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        ttk.Label(body, text="API Key").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(body, textvariable=var_key, width=34, show="*").grid(
            row=1, column=1, sticky="ew", padx=(8, 0)
        )

        ttk.Label(body, text="模型名").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(body, textvariable=var_model, width=34).grid(
            row=2, column=1, sticky="ew", padx=(8, 0)
        )

        ttk.Separator(body, orient="horizontal").grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=10
        )

        ttk.Label(body, text="MyMemory 邮箱").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(body, textvariable=var_email, width=34).grid(
            row=4, column=1, sticky="ew", padx=(8, 0)
        )
        ttk.Label(
            body,
            text="留空时免费额度约 5000 字符/天，填邮箱提升到 5 万",
            foreground="#666666",
        ).grid(row=5, column=0, columnspan=2, sticky="w")

        def apply_preset(_event=None) -> None:
            for name, (label, base_url, model) in tr_registry.LLM_PRESETS.items():
                if label == var_preset.get():
                    var_model.set(model)
                    return

        preset_box.bind("<<ComboboxSelected>>", apply_preset)

        def save() -> None:
            changes = {
                "llm_api_key": var_key.get().strip(),
                "llm_model": var_model.get().strip(),
                "memory_email": var_email.get().strip(),
            }
            for name, (label, base_url, _model) in tr_registry.LLM_PRESETS.items():
                if label == var_preset.get():
                    changes["llm_preset"] = name
                    changes["llm_base_url"] = base_url
                    break
            self.app.apply_config(**changes)
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="取消", command=dialog.destroy).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(buttons, text="保存", command=save).grid(row=0, column=1)
        dialog.grab_set()

    def _on_fps(self) -> None:
        self.app.apply_config(fps=round(float(self.var_fps.get()), 1))

    def _on_opacity(self) -> None:
        self.app.apply_config(opacity=round(float(self.var_opacity.get()) / 100.0, 2))

    def _on_scale(self) -> None:
        self.app.apply_config(font_scale=round(float(self.var_scale.get()) / 100.0, 2))

    def _on_erase(self) -> None:
        self.app.apply_config(erase_original=bool(self.var_erase.get()))

    def _on_outline(self) -> None:
        self.app.apply_config(outline=bool(self.var_outline.get()))

    def _on_horizontal(self) -> None:
        self.app.apply_config(force_horizontal=bool(self.var_horizontal.get()))

    def _on_toggle(self) -> None:
        self.app.action_toggle()

    def _sync_toggle_label(self) -> None:
        running = bool(self.var_enabled.get())
        self.var_toggle.set("暂停翻译" if running else "开始翻译")

    # ------------------------------------------------------------------ 状态
    def set_status(self, text: str) -> None:
        self.root.after(0, lambda: self.var_status.set(text))

    def set_stats(self, text: str) -> None:
        self.root.after(0, lambda: self.var_stats.set(text))

    def sync_enabled(self, value: bool) -> None:
        self.var_enabled.set(value)
        self._sync_toggle_label()

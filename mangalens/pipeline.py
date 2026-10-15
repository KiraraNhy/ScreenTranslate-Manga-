"""主流程：抓屏 -> 变化检测 -> OCR -> 翻译 -> 渲染 -> 覆盖层。"""

from __future__ import annotations

import queue
import os
import threading
import time
from dataclasses import dataclass, field, replace

import numpy as np

from . import ocr as ocr_registry
from . import translate as tr_registry
from .border import apply_border, cached_border
from .capture import Capturer, downscale_gray
from .compose import Style, compose
from .config import Config
from .layout import Block, group_lines, is_translatable, normalize_source_text
from .win32util import virtual_screen

#: 与"预期画面"差异小于该值 => 屏幕没有变化，不用做任何事
IDLE_THRESHOLD = 1.5
#: 差异大于该值 => 还在滚动/翻页，继续等它停下来
MOVE_THRESHOLD = 6.0
#: 两次识别之间的最小间隔，避免画面轻微抖动时反复识别
MIN_PROCESS_INTERVAL = 0.4


@dataclass
class Outcome:
    blocks: list[Block] = field(default_factory=list)
    overlay: np.ndarray | None = None
    timings: dict[str, float] = field(default_factory=dict)
    translated: int = 0


def resolve_region(cfg: Config) -> tuple[int, int, int, int] | None:
    if cfg.mode == "fullscreen":
        return virtual_screen()
    if cfg.region and len(cfg.region) == 4:
        left, top, width, height = (int(v) for v in cfg.region)
        if width > 8 and height > 8:
            return left, top, width, height
    return None


def style_of(cfg: Config) -> Style:
    return Style(
        font_path=cfg.font_path,
        font_scale=cfg.font_scale,
        erase_original=cfg.erase_original,
        outline=cfg.outline,
        force_horizontal=getattr(cfg, "force_horizontal", True),
    )


def translate_frame(
    frame: np.ndarray,
    backend,
    translator,
    cfg: Config,
    skip_rects: list[tuple[int, int, int, int]] | None = None,
    blocked_texts: set[str] | None = None,
    progress=None,
) -> Outcome:
    """识别+翻译一帧，返回文本块和覆盖层。"""

    outcome = Outcome()
    if progress:
        progress("识别")
    start = time.perf_counter()
    lines = backend.read(frame, cfg.source_lang)
    lines = [ln for ln in lines if ln.height >= cfg.min_text_height]
    if blocked_texts:
        lines = [ln for ln in lines if ln.text.strip() not in blocked_texts]
    for line in lines:
        line.text = normalize_source_text(line.text).strip()
    lines = [ln for ln in lines if ln.text]
    outcome.timings["ocr"] = (time.perf_counter() - start) * 1000

    blocks = [
        block
        for block in group_lines(lines)
        if is_translatable(block.text_src)
    ]
    if not blocks:
        outcome.overlay = np.zeros((*frame.shape[:2], 4), np.uint8)
        return outcome

    start = time.perf_counter()
    if progress:
        progress("翻译")
    translated = translator.translate(
        [block.text_src for block in blocks], cfg.source_lang, cfg.target_lang
    )
    outcome.timings["translate"] = (time.perf_counter() - start) * 1000
    for block, text in zip(blocks, translated):
        block.text_dst = text
        block.failed = not text
    outcome.translated = sum(1 for block in blocks if block.text_dst)

    start = time.perf_counter()
    if progress:
        progress("绘制")
    outcome.overlay = compose(frame, blocks, style_of(cfg), skip_rects=skip_rects)
    outcome.timings["render"] = (time.perf_counter() - start) * 1000
    outcome.blocks = blocks
    return outcome


def flatten(frame: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    """把覆盖层合成到原图，用于预览/保存。"""

    alpha = overlay[:, :, 3:4].astype(np.float32) / 255.0
    out = frame.astype(np.float32) * (1 - alpha) + overlay[:, :, :3].astype(np.float32) * alpha
    return out.astype(np.uint8)


def overlay_mask_thumbnail(
    overlay: np.ndarray, size: tuple[int, int], threshold: int = 8
) -> np.ndarray:
    """把"我们画了东西"的区域缩成缩略图遮罩（True = 被译文盖住的地方）。

    变化检测会跳过这些区域：不管屏幕截图里有没有我们的覆盖层，
    比较结果都一样，所以不会出现"画上->撤掉->再画上"的循环。
    """

    import cv2

    alpha = cv2.resize(overlay[:, :, 3], size, interpolation=cv2.INTER_AREA)
    mask = alpha > threshold
    if mask.any():
        grown = cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1)
        mask = grown > 0
    return mask


def masked_mean_abs(
    a: np.ndarray, b: np.ndarray, mask: np.ndarray | None = None
) -> float:
    """两张缩略灰度图的平均差异，忽略遮罩区域。"""

    diff = np.abs(a.astype(np.int16) - b.astype(np.int16))
    if mask is None or not mask.any():
        return float(diff.mean())
    valid = ~mask
    if int(valid.sum()) < diff.size * 0.05:
        # 遮罩几乎盖满画面，退化成整体比较
        return float(diff.mean())
    return float(diff[valid].mean())


class Settings:
    """线程安全的配置快照容器。"""

    def __init__(self, cfg: Config) -> None:
        self._lock = threading.Lock()
        self._cfg = replace(cfg)
        self._version = 0

    def snapshot(self) -> Config:
        with self._lock:
            return replace(self._cfg)

    def update(self, cfg: Config) -> None:
        with self._lock:
            self._cfg = replace(cfg)
            self._version += 1

    @property
    def version(self) -> int:
        with self._lock:
            return self._version


class Pipeline(threading.Thread):
    def __init__(
        self,
        settings: Settings,
        overlay,
        events: queue.Queue,
        panel_rect=None,
    ) -> None:
        super().__init__(name="pipeline", daemon=True)
        self.settings = settings
        self.overlay = overlay
        self.events = events
        self.panel_rect = panel_rect
        self._stop = threading.Event()
        self._force = threading.Event()
        self._clear_request = threading.Event()
        self._drawn = False
        self._signature: tuple | None = None
        self._backend = None
        self._translator = None
        self._shown_texts: set[str] = set()
        self._border_region: tuple[int, int, int, int] | None = None
        self._verbose = bool(os.environ.get("MANGALENS_DEBUG_PIPELINE"))
        self.capturer = Capturer()

    # ------------------------------------------------------------------ 控制
    def stop(self) -> None:
        self._stop.set()

    def force_refresh(self) -> None:
        self._force.set()

    def clear(self) -> None:
        self._clear_request.set()

    # ------------------------------------------------------------------ 引擎
    def _signature_of(self, cfg: Config) -> tuple:
        return (
            cfg.ocr_backend,
            cfg.source_lang,
            cfg.translator,
            cfg.llm_base_url,
            cfg.llm_api_key,
            cfg.llm_model,
            cfg.deepl_api_key,
            cfg.proxy,
        )

    def _ensure_engines(self, cfg: Config):
        signature = self._signature_of(cfg)
        if signature == self._signature and self._backend is not None:
            return
        self.events.put(("status", "正在加载识别引擎…"))
        backend = ocr_registry.create(cfg.ocr_backend, cfg.source_lang)
        self.events.put(("status", f"识别引擎：{ocr_registry.label_of(backend.name)}"))
        raw_translator = tr_registry.create(cfg.translator, cfg)
        translator = tr_registry.CachedTranslator(
            raw_translator, tr_registry.TranslationCache()
        )
        if self._translator is not None:
            try:
                self._translator.close()
            except Exception:
                pass
        self._backend = backend
        self._translator = translator
        self._signature = signature
        try:
            self._force.set()
        except Exception:
            pass

    # ------------------------------------------------------------------ 主循环
    def run(self) -> None:  # noqa: C901 - 主循环保持线性更好读
        base: np.ndarray | None = None  # 上次识别时的画面（没画译文）
        mask: np.ndarray | None = None  # 译文盖住的区域，比较时要跳过
        stable = 0
        last_process = 0.0
        while not self._stop.is_set():
            cfg = self.settings.snapshot()
            region = resolve_region(cfg)
            interval = 1.0 / max(0.5, min(20.0, float(cfg.fps)))

            if self._clear_request.is_set():
                self._clear_request.clear()
                self._blank(region, cfg)
                base, mask = None, None
                stable = 0

            if not cfg.enabled or region is None:
                # 暂停时也在选区周围留一圈描边，让用户看得见范围
                if region is not None and self._border_region != tuple(region):
                    self._blank(region, cfg)
                time.sleep(0.15)
                continue

            try:
                self._ensure_engines(cfg)
            except Exception as exc:
                self.events.put(("status", f"引擎加载失败：{exc}"))
                time.sleep(1.0)
                continue

            try:
                frame = self.capturer.grab(region)
            except Exception as exc:
                self.events.put(("status", f"抓屏失败：{exc}"))
                time.sleep(0.5)
                continue

            small = downscale_gray(frame)
            if base is not None and base.shape == small.shape:
                diff = masked_mean_abs(small, base, mask)
            else:
                diff = None
            if self._verbose:
                shown = "无" if diff is None else f"{diff:.2f}"
                print(
                    f"[tick] diff={shown} base={'有' if base is not None else '无'}"
                    f" stable={stable} drawn={self._drawn}",
                    flush=True,
                )

            forced = self._force.is_set()
            now = time.monotonic()

            # 屏幕还是我们预料的那个样子 => 什么都不用做
            if diff is not None and diff <= IDLE_THRESHOLD and not forced:
                stable = 0
                time.sleep(interval)
                continue

            if diff is not None and diff > MOVE_THRESHOLD:
                stable = 0
            else:
                stable += 1

            # 画面变了：先撤掉旧译文，让下一帧抓到没有覆盖层的干净画面
            if self._drawn:
                self._blank(region, cfg)
                base, mask = None, None
                stable = 0
                time.sleep(min(0.2, interval))
                continue

            if stable < max(1, int(cfg.settle_frames)):
                time.sleep(interval)
                continue
            if now - last_process < MIN_PROCESS_INTERVAL:
                time.sleep(interval)
                continue

            last_process = now
            self._force.clear()
            overlay = self._process(frame, region, cfg)
            base = small
            if overlay is not None and overlay.any():
                mask = overlay_mask_thumbnail(overlay, (small.shape[1], small.shape[0]))
            else:
                mask = None

            time.sleep(interval)

    def _blank(self, region, cfg: Config) -> None:
        """清空译文，只留选区描边。"""

        self._drawn = False
        self._shown_texts.clear()
        if region is None:
            return
        width, height = int(region[2]), int(region[3])
        self._border_region = (region[0], region[1], width, height)
        self._push(region, cached_border(width, height), cfg, 0)

    def _push(self, region, overlay, cfg: Config, count: int) -> None:
        try:
            self.overlay.push(region, overlay, cfg.opacity)
        except Exception as exc:
            self.events.put(("status", f"绘制失败：{exc}"))

    def _process(self, frame: np.ndarray, region, cfg: Config):
        started = time.perf_counter()
        skip_rects = None
        if self.panel_rect is not None:
            rect = self.panel_rect()
            if rect:
                left, top, _, _ = region
                skip_rects = [(rect[0] - left, rect[1] - top, rect[2], rect[3])]
        try:
            outcome = translate_frame(
                frame,
                self._backend,
                self._translator,
                cfg,
                skip_rects=skip_rects,
                blocked_texts=self._shown_texts,
                progress=lambda stage: self.events.put(("stage", stage)),
            )
        except Exception as exc:
            self.events.put(("status", f"识别/翻译失败：{exc}"))
            return None
        if outcome.overlay is None:
            return None
        self._shown_texts = {
            block.text_dst.strip() for block in outcome.blocks if block.text_dst
        }
        width, height = int(region[2]), int(region[3])
        border = cached_border(width, height)
        outcome.overlay = apply_border(outcome.overlay, border)
        self._border_region = (region[0], region[1], width, height)
        self._drawn = outcome.translated > 0
        self._push(region, outcome.overlay, cfg, outcome.translated)
        failed = len(outcome.blocks) - outcome.translated
        if failed > 0:
            reason = getattr(self._translator, "last_error", "") or "网络不稳定或额度不足"
            self.events.put(
                ("status", f"{failed}/{len(outcome.blocks)} 条译文没拿到：{reason}")
            )
        total = (time.perf_counter() - started) * 1000
        self.events.put(
            (
                "stats",
                {
                    "blocks": len(outcome.blocks),
                    "translated": outcome.translated,
                    "total_ms": total,
                    "timings": outcome.timings,
                },
            )
        )
        return outcome.overlay

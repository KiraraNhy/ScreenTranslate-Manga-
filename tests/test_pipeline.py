"""端到端自检：识别 -> 分组 -> 翻译(占位) -> 排版，并校验"不影响整体布局"。"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mangalens import ocr as ocr_registry  # noqa: E402
from mangalens import translate as tr_registry  # noqa: E402
from mangalens.capture import downscale_gray  # noqa: E402
from mangalens.config import Config  # noqa: E402
from mangalens.pipeline import (  # noqa: E402
    IDLE_THRESHOLD,
    MOVE_THRESHOLD,
    flatten,
    masked_mean_abs,
    overlay_mask_thumbnail,
    translate_frame,
)

SAMPLE = ROOT / "tests" / "sample_ja.png"


def main() -> int:
    if not SAMPLE.exists():
        sys.path.insert(0, str(ROOT / "tools"))
        from make_sample import build

        build(SAMPLE)

    frame = np.asarray(Image.open(SAMPLE).convert("RGB"))
    cfg = Config()
    cfg.source_lang = "ja"
    cfg.ocr_backend = "rapidocr"
    cfg.translator = "echo"

    backend = ocr_registry.create(cfg.ocr_backend, cfg.source_lang)
    translator = tr_registry.create(cfg.translator, cfg)
    outcome = translate_frame(frame, backend, translator, cfg)
    overlay = outcome.overlay

    print(f"识别到 {len(outcome.blocks)} 个文本块：")
    for block in outcome.blocks:
        x0, y0, x1, y1 = (int(v) for v in block.bbox)
        direction = "竖排" if block.vertical else "横排"
        print(f"  [{x0:4d},{y0:4d} {x1 - x0:4d}x{y1 - y0:4d}] {direction} {block.text_src!r}")

    assert len(outcome.blocks) >= 4, "文本块数量太少，识别或分组有问题"
    assert all(block.text_dst for block in outcome.blocks), "有文本块没拿到译文"
    assert any(block.vertical for block in outcome.blocks), "没有识别出竖排文本块"

    # 译文必须落在对应文本框范围内
    for block in outcome.blocks:
        x0, y0, x1, y1 = (int(v) for v in block.bbox)
        pad = 12
        region = overlay[max(0, y0 - pad) : y1 + pad, max(0, x0 - pad) : x1 + pad]
        assert region[:, :, 3].sum() > 0, f"文本框 {block.bbox} 里没有画出任何内容"

    # 关键要求：只改原文位置，其它像素保持原样（不影响整体布局）
    composited = flatten(frame, overlay)
    diff = np.abs(composited.astype(np.int16) - frame.astype(np.int16)).max(axis=2)
    changed = diff > 8
    allowed = np.zeros(changed.shape, bool)
    for block in outcome.blocks:
        x0, y0, x1, y1 = (int(v) for v in block.bbox)
        # 贴图会在文本框外留边距；竖排改横排时最多向左右各借用 40% 宽度
        pad = max(20, int(0.08 * max(x1 - x0, y1 - y0)))
        grow = int(round((x1 - x0) * 0.45))
        allowed[
            max(0, y0 - pad) : min(changed.shape[0], y1 + pad),
            max(0, x0 - pad - grow) : min(changed.shape[1], x1 + pad + grow),
        ] = True
    outside = int((changed & ~allowed).sum())
    print(f"改变像素：{int(changed.sum())}，其中落在文本框之外的：{outside}")
    assert outside == 0, "有文字被画到了原文区域之外，会破坏整体布局"
    assert changed.sum() < frame.shape[0] * frame.shape[1] * 0.08, "改动面积过大"

    # 竖排原文必须改用横排：同一行里要能放下好几个字
    vertical_blocks = [b for b in outcome.blocks if b.vertical]
    assert vertical_blocks, "样例里没有竖排文本块"
    vblock = vertical_blocks[0]
    x0, y0, x1, y1 = (int(v) for v in vblock.bbox)
    pad, grow = 20, int(round((x1 - x0) * 0.45))
    region = changed[
        max(0, y0 - pad) : y1 + pad,
        max(0, x0 - pad - grow) : x1 + pad + grow,
    ]
    char_size = float(np.median([max(1.0, ln.width) for ln in vblock.lines]))
    row_span = int(region.sum(axis=1).max())  # 单行里最宽的一行墨迹
    print(f"竖排块一个字约 {char_size:.0f}px，单行最宽墨迹 {row_span}px")
    assert row_span >= char_size * 1.8, "竖排原文的译文没有排成横排"

    # 变化检测：把译文覆盖的区域排除后，静止画面必须判为"没变化"
    painted = flatten(frame, overlay)
    clean = downscale_gray(frame)
    size = (clean.shape[1], clean.shape[0])
    mask = overlay_mask_thumbnail(overlay, size)
    print(f"译文覆盖了缩略图的 {mask.mean() * 100:.1f}%")
    assert mask.any(), "遮罩是空的，说明没检测到我们画过的区域"

    # 情况一：屏幕截图里包含我们的译文
    idle_captured = masked_mean_abs(downscale_gray(painted), clean, mask)
    # 情况二：屏幕截图里不包含译文（覆盖层被系统排除在截图之外）
    idle_hidden = masked_mean_abs(clean, clean, mask)
    print(f"静止画面差异（截图含译文）：{idle_captured:.2f}")
    print(f"静止画面差异（截图不含译文）：{idle_hidden:.2f}")
    assert idle_captured <= IDLE_THRESHOLD, "截图含译文时会被误判成画面变化，导致反复重译"
    assert idle_hidden <= IDLE_THRESHOLD, "截图不含译文时会被误判成画面变化，导致反复重译"

    scrolled = np.roll(frame, 120, axis=0)
    moved_diff = masked_mean_abs(downscale_gray(scrolled), clean, mask)
    print(f"翻页后差异（应较大）：{moved_diff:.2f}")
    assert moved_diff > MOVE_THRESHOLD, "翻页后没有检测到画面变化"

    out = ROOT / "tests" / "out_pipeline.png"
    Image.fromarray(painted).save(out)
    print(f"已保存：{out}")
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

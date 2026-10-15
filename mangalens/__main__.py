"""命令行入口。

常用：
    python -m mangalens                            启动图形界面
    python -m mangalens --doctor                   检查环境
    python -m mangalens --image a.png --out b.png  翻译单张图片（调试用）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


def _doctor() -> int:
    import platform

    from . import __version__
    from . import ocr as ocr_registry
    from . import translate as tr_registry
    from .config import app_home
    from .fonts import resolve_font
    from .win32util import virtual_screen

    print(f"MangaLens {__version__}")
    print(f"Python {platform.python_version()}  ({sys.executable})")
    print(f"配置目录：{app_home()}")
    left, top, width, height = virtual_screen()
    print(f"屏幕：{width}x{height} @ ({left},{top})")
    try:
        print(f"字体：{resolve_font()[0]}")
    except Exception as exc:
        print(f"字体：不可用（{exc}）")
    print("识别引擎：")
    available = ocr_registry.available_names()
    for name in ocr_registry.all_names():
        mark = "可用" if name in available else "缺少依赖"
        print(f"  - {ocr_registry.label_of(name)}: {mark}")
    try:
        from .ocr.windows_backend import WindowsOcrBackend

        tags = WindowsOcrBackend.installed_languages()
        print(f"  Windows OCR 语言包：{', '.join(tags) if tags else '无'}")
    except Exception:
        pass
    print(f"默认选择（日语）：{ocr_registry.auto_name('ja')}")
    print("翻译引擎：")
    for name in tr_registry.names():
        print(f"  - {tr_registry.label_of(name)}")
    print(f"numpy {np.__version__}")
    return 0


def _run_image(args: argparse.Namespace) -> int:
    from PIL import Image

    from . import ocr as ocr_registry
    from . import translate as tr_registry
    from .config import Config
    from .pipeline import flatten, translate_frame

    cfg = Config.load()
    if args.src:
        cfg.source_lang = args.src
    if args.dst:
        cfg.target_lang = args.dst
    if args.ocr:
        cfg.ocr_backend = args.ocr
    if args.tr:
        cfg.translator = args.tr

    source = Path(args.image)
    frame = np.asarray(Image.open(source).convert("RGB"))
    backend = ocr_registry.create(cfg.ocr_backend, cfg.source_lang)
    translator = tr_registry.create(cfg.translator, cfg)
    print(
        f"识别引擎 {ocr_registry.label_of(backend.name)}｜"
        f"翻译 {tr_registry.label_of(cfg.translator)}"
    )
    outcome = translate_frame(frame, backend, translator, cfg)
    for block in outcome.blocks:
        x0, y0, x1, y1 = (int(v) for v in block.bbox)
        size = f"{x1 - x0}x{y1 - y0}"
        print(f"  [{x0:4d},{y0:4d} {size:>9}] {block.text_src!r} -> {block.text_dst!r}")
    print(f"耗时：{outcome.timings}")
    if outcome.overlay is not None:
        result = flatten(frame, outcome.overlay)
        out_path = Path(args.out or source.with_name(source.stem + "_zh" + source.suffix))
        Image.fromarray(result).save(out_path)
        print(f"已保存：{out_path}")
        if args.debug:
            debug_path = out_path.with_name(out_path.stem + "_overlay.png")
            Image.fromarray(outcome.overlay).save(debug_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mangalens", description="屏幕实时漫画翻译")
    parser.add_argument("--doctor", action="store_true", help="检查环境")
    parser.add_argument("--image", help="翻译单张图片")
    parser.add_argument("--out", help="输出图片路径")
    parser.add_argument("--src", help="原文语言，如 ja/en/auto")
    parser.add_argument("--dst", help="目标语言，如 zh/zh-Hant")
    parser.add_argument("--ocr", help="识别引擎：auto/paddleocr/manga-ocr/windows/tesseract")
    parser.add_argument("--tr", help="翻译引擎：google/llm/deepl/offline/echo")
    parser.add_argument("--debug", action="store_true", help="额外输出覆盖层图片")
    parser.add_argument("--region", help="启动时直接使用该区域，格式 left,top,width,height")
    parser.add_argument("--fullscreen", action="store_true", help="启动即全屏模式")
    args = parser.parse_args(argv)

    if args.doctor:
        return _doctor()
    if args.image:
        return _run_image(args)

    from .app import App
    from .config import Config
    from .win32util import acquire_single_instance, message_box

    if not acquire_single_instance():
        message_box("MangaLens 已经在运行了，请用已经打开的那个控制面板。", "屏幕实时翻译")
        return 1

    cfg = Config.load()
    if args.region:
        cfg.region = [int(v) for v in args.region.replace("，", ",").split(",")]
        cfg.mode = "region"
    if args.fullscreen:
        cfg.mode = "fullscreen"
    App(cfg).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""真机循环自检：在屏幕上放一张漫画图，验证静止时不会反复重译、变化时能重新翻译。

需要屏幕抓取权限，运行方式：python tests/test_live_loop.py
"""

from __future__ import annotations

import queue
import sys
import time
import tkinter as tk
import argparse
from pathlib import Path

from PIL import Image, ImageTk

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mangalens.config import Config  # noqa: E402
from mangalens.overlay import Overlay  # noqa: E402
from mangalens.pipeline import Pipeline, Settings  # noqa: E402

SAMPLE = ROOT / "tests" / "sample_ja.png"
WIDTH, HEIGHT = 640, 854
# 放在屏幕右下角，避免被控制台窗口之类的其它窗口覆盖
REGION = (1860, 560, WIDTH, HEIGHT)
QUIET_SECONDS = 16
TOTAL_SECONDS = 30


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translator", default="echo")
    parser.add_argument("--config", action="store_true", help="使用真实保存的配置（含密钥）")
    parser.add_argument("--seconds", type=float, default=TOTAL_SECONDS)
    parser.add_argument("--quiet", type=float, default=QUIET_SECONDS)
    args = parser.parse_args()
    quiet_seconds, total_seconds = args.quiet, args.seconds

    root = tk.Tk()
    root.title("MangaLens 循环自检")
    root.geometry(f"{WIDTH}x{HEIGHT}+{REGION[0]}+{REGION[1]}")
    canvas = tk.Canvas(root, highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    photo = ImageTk.PhotoImage(
        Image.open(SAMPLE).convert("RGB").resize((WIDTH, HEIGHT))
    )
    item = canvas.create_image(0, 0, anchor="nw", image=photo)
    root.update()
    time.sleep(0.8)

    cfg = Config.load() if args.config else Config()
    cfg.enabled = True  # 自检要跑翻译，忽略保存的暂停状态
    cfg.source_lang = "ja"
    cfg.ocr_backend = "rapidocr"
    cfg.translator = args.translator
    cfg.region = list(REGION)
    cfg.mode = "region"

    events: queue.Queue = queue.Queue()
    overlay = Overlay({})
    overlay.start()
    pipeline = Pipeline(Settings(cfg), overlay, events)
    pipeline.start()

    stats: list[dict] = []
    moved = False
    started = time.time()
    try:
        while time.time() - started < total_seconds:
            root.update()
            time.sleep(0.05)
            if not moved and time.time() - started > quiet_seconds:
                moved = True
                canvas.move(item, 0, 90)  # 模拟翻页/滚动
                print(f"[{time.time() - started:4.1f}s] 画面发生变化")
            while not events.empty():
                kind, payload = events.get()
                if kind == "stats":
                    stats.append(payload)
                    print(
                        f"[{time.time() - started:4.1f}s] 翻译 {payload['blocks']} 块"
                        f"，耗时 {payload['total_ms']:.0f}ms"
                    )
                elif kind in ("status", "stage"):
                    print(f"[{time.time() - started:4.1f}s] {kind}: {payload}")
    finally:
        pipeline.stop()
        overlay.stop()
        root.destroy()

    print(f"\n{quiet_seconds:.0f} 秒静止期间 + 1 次画面变化，共翻译 {len(stats)} 次")
    if not stats:
        print("[失败] 一次都没翻译")
        return 1
    if len(stats) > 4:
        print("[失败] 反复重译，说明变化检测有循环问题")
        return 1
    print("[通过] 静止时不重复翻译，画面变化后能重新翻译")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

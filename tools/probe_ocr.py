"""对比各 OCR 引擎在样例图片上的识别结果与耗时。"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mangalens import ocr as registry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", nargs="?", default="tests/sample_ja.png")
    parser.add_argument("--engine", default="windows")
    parser.add_argument("--lang", default="ja")
    parser.add_argument("--version", default="PP-OCRv5")
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()

    frame = np.asarray(Image.open(args.image).convert("RGB"))
    kwargs = {}
    if args.engine == "paddleocr" and args.version:
        kwargs["ocr_version"] = args.version
    backend = registry.create(args.engine, args.lang, **kwargs)
    backend.warmup(args.lang)

    total = 0.0
    for _ in range(max(1, args.repeat)):
        start = time.perf_counter()
        lines = backend.read(frame, args.lang)
        total += time.perf_counter() - start
    print(f"引擎 {registry.label_of(backend.name)}｜语言 {args.lang}｜"
          f"{total / max(1, args.repeat):.0f} ms/帧｜{len(lines)} 行")
    for line in lines:
        x0, y0, x1, y1 = (int(v) for v in line.bbox)
        flag = "纵" if line.vertical else "横"
        print(f"  [{x0:4d},{y0:4d} {x1 - x0:4d}x{y1 - y0:4d}] {flag} {line.text!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

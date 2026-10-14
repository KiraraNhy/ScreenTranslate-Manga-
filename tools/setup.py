"""一键安装依赖（由 install.bat 调用）。

中文提示统一在这里输出：批处理文件按系统代码页解析，直接写中文会乱码，
而 Python 会按控制台编码输出，中文显示正常。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"


def run(cmd: list[str]) -> int:
    print("    " + " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-pip", action="store_true", help="跳过依赖安装，只做自检")
    args = parser.parse_args()

    print("=" * 46)
    print("  MangaLens 屏幕实时翻译 - 安装")
    print("=" * 46)
    print()

    if sys.version_info < (3, 10):
        print(f"[错误] 当前 Python 是 {sys.version.split()[0]}，需要 3.10 或以上。")
        return 1
    print(f"Python {sys.version.split()[0]}  ({sys.executable})")
    print()

    if not args.skip_pip:
        print("正在检查并安装依赖（已装过的会跳过，首次可能需要几分钟）...")
        code = run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-r",
                str(ROOT / "requirements.txt"),
                "--disable-pip-version-check",
            ]
        )
        if code != 0:
            print()
            print("直连 PyPI 失败，改用国内镜像重试...")
            code = run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    str(ROOT / "requirements.txt"),
                    "--disable-pip-version-check",
                    "-i",
                    MIRROR,
                ]
            )
        if code != 0:
            print()
            print("[错误] 依赖安装失败，请把上面的报错信息发给我。")
            return 1
        print()

    print("环境自检：")
    print()
    code = run([sys.executable, "-m", "mangalens", "--doctor"])
    print()
    if code != 0:
        print("[警告] 自检没有正常结束，见上面的信息。")
        return code

    print("=" * 46)
    print("  安装完成！")
    print()
    print("  以后双击 run.bat 即可启动。")
    print("  用法：启动后点控制面板上的「框选区域」，框住漫画正文。")
    print("=" * 46)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

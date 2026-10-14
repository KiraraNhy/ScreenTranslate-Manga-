"""配置读写。"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import APP_NAME


_HOME_CACHE: Path | None = None


def _candidates() -> list[Path]:
    override = os.environ.get("MANGALENS_HOME")
    if override:
        return [Path(override)]
    if os.name == "nt":
        candidates: list[Path] = []
        roaming = os.environ.get("APPDATA")
        local = os.environ.get("LOCALAPPDATA")
        if roaming:
            candidates.append(Path(roaming) / APP_NAME)
        if local:
            candidates.append(Path(local) / APP_NAME)
        candidates.append(Path(tempfile.gettempdir()) / APP_NAME)
        # 刻意不使用程序所在目录，避免配置（含密钥）随目录被复制出去
        return candidates
    return [Path.home() / ".config" / APP_NAME, Path(tempfile.gettempdir()) / APP_NAME]


def app_home() -> Path:
    """配置/缓存目录。可用 MANGALENS_HOME 环境变量覆盖。

    某个位置不可写时（权限受限、只读盘等）自动退到下一个候选目录，保证程序能启动。
    """

    global _HOME_CACHE
    if _HOME_CACHE is not None:
        return _HOME_CACHE
    for base in _candidates():
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        _HOME_CACHE = base
        return base
    fallback = Path(tempfile.gettempdir()) / APP_NAME
    _HOME_CACHE = fallback
    return fallback


# 可选原文语言
LANGUAGES: dict[str, str] = {
    "auto": "自动检测",
    "ja": "日语",
    "en": "英语",
    "ko": "韩语",
    "zh-Hant": "繁体中文",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "it": "意大利语",
    "pt": "葡萄牙语",
    "ru": "俄语",
    "ar": "阿拉伯语",
    "th": "泰语",
    "vi": "越南语",
}

TARGETS: dict[str, str] = {
    "zh": "简体中文",
    "zh-Hant": "繁体中文",
}

#: 配置结构版本号，用于把旧配置里的参数升级到新的默认值
CONFIG_VERSION = 3

#: 这些字段只在内存里用，不写进配置文件（选区每次启动都要重新圈定）
VOLATILE_FIELDS = ("region", "mode")

#: 这些字段加密存放到 secrets.bin，不写进 config.json
SECRET_FIELDS = ("llm_api_key", "deepl_api_key")


@dataclass
class Config:
    config_version: int = CONFIG_VERSION
    # 语言
    source_lang: str = "ja"
    target_lang: str = "zh"
    # 引擎
    ocr_backend: str = "auto"
    translator: str = "mymemory"
    # 采集
    mode: str = "region"  # region | fullscreen
    region: list[int] | None = None  # [left, top, width, height] 屏幕坐标
    fps: float = 5.0  # 每秒检查几次屏幕有没有变化
    settle_frames: int = 1  # 画面连续稳定多少帧后才开始识别
    # 显示
    enabled: bool = True
    opacity: float = 1.0
    font_scale: float = 1.0
    font_path: str = ""
    erase_original: bool = True
    outline: bool = True
    #: 中文一律横排（从左到右、从上到下），不跟随日文竖排顺序
    force_horizontal: bool = True
    min_text_height: int = 9
    # 翻译后端参数
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_preset: str = "deepseek"
    deepl_api_key: str = ""
    memory_email: str = ""
    proxy: str = ""
    # 界面
    panel_pos: list[int] | None = None
    keep_above_panel: bool = True
    # 设为 true 时译文不会被屏幕截图/录屏捕获（系统支持时生效）。
    # 默认 false：截图/录屏能看到译文，同时变化检测会跳过译文区域，不会反复重译。
    hide_from_capture: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    # ---------------------------------------------------------------- 读写
    @classmethod
    def load(cls) -> "Config":
        path = app_home() / "config.json"
        cfg = cls()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            known = set(cls.__dataclass_fields__)
            for key, value in data.items():
                if key in known:
                    setattr(cfg, key, value)
            _migrate(cfg, int(data.get("config_version", 1)))
        saved = secret_store().load()
        for field in SECRET_FIELDS:
            if saved.get(field):
                setattr(cfg, field, saved[field])
        # 选区要求每次启动重新圈定
        cfg.region = None
        cfg.mode = "region"
        return cfg

    def save(self) -> None:
        path = app_home() / "config.json"
        tmp = path.with_suffix(".json.tmp")
        data = asdict(self)
        secrets = {field: str(data.pop(field, "") or "") for field in SECRET_FIELDS}
        for field in VOLATILE_FIELDS:
            data.pop(field, None)
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        secret_store().save(secrets)


_STORE = None


def secret_store():
    """密钥存放器（DPAPI 加密，绑定本机当前用户）。"""

    global _STORE
    if _STORE is None:
        from .secrets import SecretStore

        _STORE = SecretStore(app_home() / "secrets.bin")
    return _STORE


def _migrate(cfg: "Config", version: int) -> None:
    """把旧版本保存下来的调节参数升级到新默认值（用户改过的保持不动）。"""

    if version < 2:
        # 旧默认：每秒检查 3 次、要连续稳定 2 帧才识别
        if abs(float(cfg.fps) - 3.0) < 1e-6:
            cfg.fps = 5.0
        if int(cfg.settle_frames) == 2:
            cfg.settle_frames = 1
    cfg.config_version = CONFIG_VERSION

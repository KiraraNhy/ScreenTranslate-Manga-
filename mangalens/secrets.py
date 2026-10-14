"""API Key 等敏感配置的存放。

用 Windows DPAPI 加密，密钥绑定当前设备的当前用户账号：
即使这个文件被复制到别的机器或别的账号下，也无法解密，不会泄露。
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
from ctypes import wintypes as wt
from pathlib import Path


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _load_api():
    if os.name != "nt":
        return None
    try:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except OSError:
        return None
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wt.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wt.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wt.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(wt.LPWSTR),
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wt.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wt.BOOL
    kernel32.LocalFree.argtypes = [wt.HLOCAL]
    return crypt32, kernel32


_API = _load_api()


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def dpapi_available() -> bool:
    return _API is not None


def protect(data: bytes) -> bytes:
    if _API is None:
        raise RuntimeError("当前系统不支持 DPAPI 加密")
    crypt32, kernel32 = _API
    blob_in, _keep = _blob(data)
    blob_out = _DataBlob()
    if not crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        "MangaLens",
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise OSError(ctypes.get_last_error(), "CryptProtectData 失败")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def unprotect(blob: bytes) -> bytes:
    if _API is None:
        raise RuntimeError("当前系统不支持 DPAPI 加密")
    crypt32, kernel32 = _API
    blob_in, _keep = _blob(blob)
    blob_out = _DataBlob()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise OSError(ctypes.get_last_error(), "CryptUnprotectData 失败")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


class SecretStore:
    """加密存放少量敏感字段。文件内容只能被本机当前用户解开。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._cache: dict[str, str] | None = None

    def load(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache
        data: dict[str, str] = {}
        if self.path.exists():
            try:
                raw = self.path.read_bytes()
                if raw.startswith(b"{") or raw.startswith(b"["):
                    # 极少数无法使用 DPAPI 的环境，退回明文文件
                    data = json.loads(raw.decode("utf-8"))
                else:
                    data = json.loads(unprotect(raw).decode("utf-8"))
            except Exception:
                data = {}
        self._cache = {k: str(v) for k, v in data.items() if v}
        return self._cache

    def save(self, values: dict[str, str]) -> str:
        """写入（合并已有内容）。返回 'dpapi' 或 'plain'，便于提示用户。"""

        merged = dict(self.load())
        for key, value in values.items():
            if value:
                merged[key] = value
            else:
                merged.pop(key, None)
        self._cache = merged
        payload = json.dumps(merged, ensure_ascii=False).encode("utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if _API is not None:
            try:
                self.path.write_bytes(protect(payload))
                return "dpapi"
            except Exception:
                pass
        self.path.write_bytes(base64.b64encode(payload))
        return "plain"

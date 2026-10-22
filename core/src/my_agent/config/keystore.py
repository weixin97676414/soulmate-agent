























from __future__ import annotations

import ctypes
import json
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)



_CRYPTPROTECT_UI_FORBIDDEN = 0x01




_ENTROPY = b"my-agent-core/models.json/api_key"




class _DataBlob(ctypes.Structure):
    
    
    
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.c_void_p)]


_api: tuple[Any, Any] | None = None
_api_probed = False


def _get_api() -> tuple[Any, Any] | None:

    global _api, _api_probed
    if _api_probed:
        return _api
    _api_probed = True

    if sys.platform != "win32":
        return None
    try:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except OSError as exc:  
        logger.debug("加载 crypt32 失败，DPAPI 不可用: %s", exc)
        return None

    blob_ptr = ctypes.POINTER(_DataBlob)
    crypt32.CryptProtectData.argtypes = [
        blob_ptr,  
        ctypes.c_wchar_p,  
        blob_ptr,  
        ctypes.c_void_p,  
        ctypes.c_void_p,  
        ctypes.c_uint32,  
        blob_ptr,  
    ]
    crypt32.CryptProtectData.restype = ctypes.c_int
    crypt32.CryptUnprotectData.argtypes = [
        blob_ptr,
        ctypes.POINTER(ctypes.c_wchar_p),  
        blob_ptr,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        blob_ptr,
    ]
    crypt32.CryptUnprotectData.restype = ctypes.c_int
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    _api = (crypt32, kernel32)
    return _api


def is_available() -> bool:

    return _get_api() is not None


def _make_blob(data: bytes) -> tuple[Any, _DataBlob]:





    buffer = ctypes.create_string_buffer(data, len(data))
    return buffer, _DataBlob(len(data), ctypes.cast(buffer, ctypes.c_void_p))


def _entropy_blob() -> tuple[Any, _DataBlob]:
    return _make_blob(_ENTROPY)


def protect(plaintext: bytes) -> bytes | None:

    if not plaintext:
        return None
    api = _get_api()
    if api is None:
        return None
    crypt32, kernel32 = api

    _in_buffer, blob_in = _make_blob(plaintext)
    _ent_buffer, blob_ent = _entropy_blob()
    blob_out = _DataBlob()

    ok = crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        "my-agent model keys",
        ctypes.byref(blob_ent),
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(blob_out),
    )
    if not ok:
        logger.warning("DPAPI 加密失败（错误码 %s）", ctypes.get_last_error())
        return None

    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        
        kernel32.LocalFree(blob_out.pbData)


def unprotect(blob: bytes) -> bytes | None:






    if not blob:
        return None
    api = _get_api()
    if api is None:
        return None
    crypt32, kernel32 = api

    _in_buffer, blob_in = _make_blob(blob)
    _ent_buffer, blob_ent = _entropy_blob()
    blob_out = _DataBlob()

    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        ctypes.byref(blob_ent),
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(blob_out),
    )
    if not ok:
        logger.debug("DPAPI 解密失败（错误码 %s）", ctypes.get_last_error())
        return None

    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def dump_keys(keys: dict[str, str]) -> bytes | None:

    return protect(json.dumps(keys, ensure_ascii=False).encode("utf-8"))


def load_keys(blob: bytes) -> dict[str, str]:

    plain = unprotect(blob)
    if plain is None:
        return {}
    try:
        data = json.loads(plain.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("密钥文件内容无法解析，已忽略: %s", exc)
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str) and v}

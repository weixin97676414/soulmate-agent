"""用 Windows DPAPI 加密独立运行模式下的 API Key。

## 为什么需要它

Electron 客户端模式下，密钥由主进程用 ``safeStorage`` 保管 —— 它在 Windows 上
**就是 DPAPI**。但独立运行后端时（开发调试、命令行、把核心单独部署）没有那层托管，
密钥只能明文写进 ``models.json``：把这个目录拷走就等于拿到了全部 Key。

这里给独立模式补上同样强度的保护：直接用 DPAPI 加密，密钥与**当前 Windows 用户
账户**绑定 —— 换了账户或换了机器都解不开。

## 为什么用 ctypes 手写，而不是装 pywin32

这里只需要两个函数（``CryptProtectData`` / ``CryptUnprotectData``），
而 pywin32 是个几十 MB 的编译依赖。安装包已经为了 chromadb 涨到 179 MB，
为两个函数再塞一个重量级依赖不划算。

## 降级路径（重要）

非 Windows、或系统没提供可用实现时，``is_available()`` 返回 False，
调用方退回"**明文 + 明确告警**"的既有行为 ——
加密不可用绝不能让应用起不来，那会把"少一层保护"变成"完全不能用"。
"""

from __future__ import annotations

import ctypes
import json
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)

# 让 DPAPI 不要弹任何 UI。服务端/后台进程里弹窗会直接卡死，
# 而调用方永远不会知道它在等一个看不见的对话框。
_CRYPTPROTECT_UI_FORBIDDEN = 0x01

# 固定熵。DPAPI 本身只保证"同一用户可解"，这台机器上的**其它程序**同样能调
# CryptUnprotectData —— 加一段固定熵之后，想解开就必须知道这段熵，
# 顺手捡到文件的程序解不开。
_ENTROPY = b"my-agent-core/models.json/api_key"

# 解密失败时的报错里不带系统原文，而是转成用户能看懂的原因（见 unprotect）


class _DataBlob(ctypes.Structure):
    # 刻意用 ``ctypes.c_uint32`` / ``c_void_p`` 而不是 ``wintypes.DWORD``：
    # ``ctypes.wintypes`` 在非 Windows 上**导入就会失败**，而本模块需要能被
    # 无条件导入（这样调用方不必在导入前判断平台）。
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.c_void_p)]


_api: tuple[Any, Any] | None = None
_api_probed = False


def _get_api() -> tuple[Any, Any] | None:
    """惰性加载 crypt32 / kernel32。只探测一次。"""
    global _api, _api_probed
    if _api_probed:
        return _api
    _api_probed = True

    if sys.platform != "win32":
        return None
    try:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except OSError as exc:  # pragma: no cover - 极老的 Windows 才会走到
        logger.debug("加载 crypt32 失败，DPAPI 不可用: %s", exc)
        return None

    blob_ptr = ctypes.POINTER(_DataBlob)
    crypt32.CryptProtectData.argtypes = [
        blob_ptr,  # pDataIn
        ctypes.c_wchar_p,  # szDataDescr
        blob_ptr,  # pOptionalEntropy
        ctypes.c_void_p,  # pvReserved
        ctypes.c_void_p,  # pPromptStruct
        ctypes.c_uint32,  # dwFlags
        blob_ptr,  # pDataOut
    ]
    crypt32.CryptProtectData.restype = ctypes.c_int
    crypt32.CryptUnprotectData.argtypes = [
        blob_ptr,
        ctypes.POINTER(ctypes.c_wchar_p),  # ppszDataDescr（用不到，传 None）
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
    """本机能不能用 DPAPI。"""
    return _get_api() is not None


def _make_blob(data: bytes) -> tuple[Any, _DataBlob]:
    """建一个指向 ``data`` 的 DATA_BLOB。

    返回 ``(buffer, blob)`` —— **调用方必须持有 buffer**：它一旦被回收，
    blob 里的指针就悬空了，而 DPAPI 不会察觉，只会读到一片垃圾。
    """
    buffer = ctypes.create_string_buffer(data, len(data))
    return buffer, _DataBlob(len(data), ctypes.cast(buffer, ctypes.c_void_p))


def _entropy_blob() -> tuple[Any, _DataBlob]:
    return _make_blob(_ENTROPY)


def protect(plaintext: bytes) -> bytes | None:
    """加密。失败或不可用时返回 ``None``（调用方据此退回明文路径）。"""
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
        # 输出缓冲由系统分配，必须还给系统 —— 它不会进 Python 的 GC
        kernel32.LocalFree(blob_out.pbData)


def unprotect(blob: bytes) -> bytes | None:
    """解密。失败返回 ``None``。

    最常见的失败原因是**换了 Windows 账户或换了机器** —— DPAPI 的密钥由用户
    配置文件派生，绑定之后就搬不走。这时唯一的出路是让用户重填 Key，
    所以调用方要把话说明白，不能只说"解密失败"。
    """
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
    """把 ``{模型 id: api_key}`` 打包加密。"""
    return protect(json.dumps(keys, ensure_ascii=False).encode("utf-8"))


def load_keys(blob: bytes) -> dict[str, str]:
    """解密并还原成字典。任何异常都收敛成空字典 —— 密钥读不出来不该让应用起不来。"""
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

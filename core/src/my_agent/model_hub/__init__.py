"""本地模型中心：清单（``catalog``）+ 运行期下载器（``downloader``）+ 路由（``routes``）。

语音模型与嵌入模型**不再随安装包分发**（产品约定），改由用户在首启引导页
按需下载，落到 ``%APPDATA%/Soulmate Agent/models/<模型名>/``。不下载也能用客户端，
只是语音与长期记忆不工作（引导页提供"跳过"）。

⚠️ 打包配置里那两个模型要**同时**从 datas 移除（``core/build/agent-core.spec``）——
留着的话"按需下载"就变成了"包里其实已经有"，下载进度条纯粹是浪费用户时间。
"""

from .catalog import ALL, EMBEDDING, VOICE, ModelSpec, get, keys
from .downloader import ModelDownloader, install_root

__all__ = [
    "ALL",
    "EMBEDDING",
    "VOICE",
    "ModelDownloader",
    "ModelSpec",
    "get",
    "install_root",
    "keys",
]

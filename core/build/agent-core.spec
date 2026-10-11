# -*- mode: python ; coding: utf-8 -*-
"""Agent Core 的 PyInstaller 打包配置。

产物：`core/dist/agent-core/agent-core.exe`（**onedir 而非 onefile**）。
Electron 的 electron-builder 配置里 `extraResources` 就是取这个目录。

## 为什么必须用 onedir

onefile 每次启动都要把几百 MB 解压到临时目录，冷启动会从 1~2 秒变成十几秒；
而且「自己解压自己」的行为在不少杀软眼里就是可疑动作，容易被拦。

## 为什么需要这么多 hiddenimports

PyInstaller 靠静态分析找依赖，以下三类它**必然扫不到**，漏了就是运行时报
ModuleNotFoundError（而且往往只在打包后才暴露）：

1. **本项目内部的字符串导入**：`discover_builtin_skills()` 用
   `importlib.import_module("my_agent.skill.builtin.office.excel")` 这样的字符串路径
   加载技能，静态分析看不到——漏掉的后果是"打包后技能全都不见了"，
   界面看起来正常，只是模型一个工具都没有；
2. **uvicorn 的运行时挑选**：loop / protocol / lifespan 实现是按平台名拼出来的
   （`uvicorn.loops.auto` → `uvicorn.loops.asyncio`）；
3. **MCP SDK 的传输与协议实现**：同样是运行期按名字选择。
"""

import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

SPEC_DIR = os.path.abspath(SPECPATH)
PROJECT_DIR = os.path.dirname(SPEC_DIR)
SRC_DIR = os.path.join(PROJECT_DIR, "src")

datas = []
binaries = []
hiddenimports = []

# ---- 1) 本项目全部子模块 -------------------------------------------------- #
# 用 collect_submodules 而不是逐个列举：技能、路由都是按名字动态加载的，
# 手工维护列表迟早会漏，而漏掉的症状（技能静默消失）非常难排查。
#
# ⚠️ 扫之前**必须先把源码目录塞进 sys.path**：spec 是在 `Analysis` 之前执行的，
# 这一刻 PyInstaller 还没应用下面那个 `pathex=[SRC_DIR]`，所以
# `collect_submodules("my_agent")` 完全取决于"当前解释器能不能 import my_agent"，
# 而 venv 里那份 editable 安装（`.pth` 写的是**绝对路径**）一旦失效，它就悄悄
# 变成**空列表**。
#
# 实测踩过一次：仓库目录改名之后 `.pth` 指向的老路径没了，构建**照常成功**、
# exe 也照常启动，只是里面的技能从 14 个变成 1 个（其余全是 ModuleNotFoundError）
# —— 只有 verify:core 能发现。所以这里显式插路径，并且加一条兜底断言。
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

hiddenimports += collect_submodules("my_agent")

# 兜底：真扫不到就**构建失败**，绝不产出一个"界面看着正常、模型手里一个工具都没有"的包。
_SCANNED_MUST_HAVE = (
    "my_agent.skill.builtin.system",
    "my_agent.skill.builtin.task_tools",
    "my_agent.skill.builtin.life.expense",
    "my_agent.skill.builtin.office.excel",
    "my_agent.server.routes.tasks",
    "my_agent.agent.evolution_tasks",
)
_scanned = set(hiddenimports)
_scanned_missing = [name for name in _SCANNED_MUST_HAVE if name not in _scanned]
if _scanned_missing:
    raise SystemExit(
        "collect_submodules('my_agent') 没扫到这些模块：\n  "
        + "\n  ".join(_scanned_missing)
        + "\n它们不会报构建错，只会在**打包之后**以 ModuleNotFoundError 的形式出现。\n"
        + f"先确认这份源码可导入：python -c \"import my_agent\"（源码目录：{SRC_DIR}）"
    )

# ---- 1.5) 内置只读资源（心鉴学技能正文 / 地点库）--------------------------- #
# ``collect_submodules`` 只认 .py，这些 .md / .json **不会被带进去**；不带进去的
# 后果是打包后 `utils/resources.py::read_text` 直接抛 FileNotFoundError ——
# 心鉴学专属技能与地点核对在真机上"装上了但一调就报资源缺失"。
# 目标路径必须与 `utils/resources.py::resources_dir()` 的拼法一致：
# `<bundle>/my_agent/resources/…`（见该模块 docstring 的"打包侧必须同步"）。
resources_src = os.path.join(SRC_DIR, "my_agent", "resources")
datas.append((resources_src, "my_agent/resources"))

# ---- 2) uvicorn ---------------------------------------------------------- #
hiddenimports += collect_submodules("uvicorn")

# ---- 3) MCP SDK 与办公文档库 --------------------------------------------- #
for package in ("mcp", "openpyxl", "docx", "pypdf", "sse_starlette"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    except Exception:  # noqa: BLE001 - 可选依赖缺失时跳过，不影响主流程
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# anyio 的后端也是按名字挑的
hiddenimports += ["anyio._backends._asyncio"]

# ---- 5) 浏览器自动化（Playwright）----------------------------------------- #
# 用**系统** Edge/Chrome（channel="msedge"/"chrome"），**不打包 Chromium**
# （省约 300MB；Edge 是 Win10/11 自带）。
#
# Playwright 的 Node 驱动（driver/node.exe + driver/package/）**必须随包分发**，
# collect_all 会把它们当数据文件带进来。运行期靠相对路径定位驱动，
# 不额外联网下载浏览器 —— 这是"浏览器能力能不能离线用"的关键。
for package in ("playwright", "pyee"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    except Exception:  # noqa: BLE001 - 可选依赖缺失时跳过，不阻断主流程
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# ---- 4) 长期记忆（chromadb）：默认**排除**，需要时显式打开 ----------------- #
#
# 实测裸装约 265 MB：
#   kubernetes 74 + chromadb Rust 绑定 60.5 + onnxruntime 44 + numpy 51
#   + grpcio 12.8 + hf_xet 9 + tokenizers 7.8 + huggingface_hub 6.3 + …
# 打进安装包会让体积从 135 MB 涨到 300 MB 量级，**直接击穿 ≤250MB 的交付预算**。
# 所以默认排除；`my_agent/memory/long_term.py` 是惰性导入，排除后功能会
# 优雅降级成"未安装依赖，附启用说明"，而不是崩溃。
#
# **默认开启**（产品决定：长期记忆随安装包分发）。
# 想要精简版（约 73 MB 而不是 217 MB）时显式关掉：
#   $env:AGENT_WITH_MEMORY="0"; npm run build:core
WITH_MEMORY = os.environ.get("AGENT_WITH_MEMORY", "1").strip().lower() not in ("0", "false", "no")

if WITH_MEMORY:
    # 防呆：开了长期记忆却没装 chromadb 时**必须直接失败**。
    # 否则 collect_all 会静默跳过，产出一个"看起来正常但没有知识库"的包 ——
    # 这种静默降级比构建失败难查得多（用户点开知识库才发现用不了）。
    try:
        import chromadb  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            "AGENT_WITH_MEMORY 已开启，但当前环境没有安装 chromadb，"
            "拒绝产出一个缺失长期记忆的包。\n"
            f"原因：{exc}\n"
            '解决：pip install -e ".[memory]"\n'
            "或者显式关闭：$env:AGENT_WITH_MEMORY=\"0\"; npm run build:core"
        ) from exc

if WITH_MEMORY:
    for package in ("chromadb", "onnxruntime", "tokenizers"):
        try:
            pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
        except Exception:  # noqa: BLE001 - 没装就跳过，构建照常
            continue
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden

    # ---- 嵌入模型：**2026-10-08 起不再随包**（见下面那段说明，两段一起看） --- #
    #
    # ⚠️ 这里**故意什么都不做**。上面的 chromadb / onnxruntime / tokenizers
    # 仍然照常随包（用户口径：只有"语音模型 / 嵌入模型"两个模型改成按需下载，
    # 其余依赖都随包分发）。

# ---- 语音模型 / 嵌入模型**不再随包分发**（2026-10-08，第七十九批） -------- #
#
# 用户口径：**只有语音模型与嵌入模型改成用户按需下载**，其余（chromadb /
# onnxruntime / tokenizers / sherpa-onnx / playwright 驱动…）照旧随包分发。
#
# 为什么移出：两者合计约 820 MB，是安装包体积的大头；而"装了却从没用过语音 /
# 长期记忆"的用户占多数。现在由首启引导页按线路（国内 ModelScope / 国外
# HuggingFace）下载到 ``%APPDATA%/Soulmate Agent/models/``，见 ``my_agent/model_hub/``。
#
# ⚠️ **不要把它们加回 datas**。加回来之后：
#   1) "按需下载"变成"包里其实已经有"，那条进度条纯粹在浪费用户时间；
#   2) 下载到用户目录的那份在读取侧**优先级更高**（见下面两条候选路径），
#      包里这份会被永久遮蔽 —— 于是"到底跑的哪份模型"要查两个地方。
#
# ⚠️ **曾经有过的东西，别再抄回来**：
#   · 嵌入模型的"缺失即 SystemExit"防呆；
#   · 语音模型的 ``VOICE_MODEL_ROOT`` / ``_VOICE_ITEMS`` / ``_VOICE_OPTIONAL``
#     与 ``AGENT_SKIP_VOICE`` 逃生口。
#   模型不随包之后，"缺失"是**正常状态**，为它报构建失败会把每次打包都拦下来。
#   （Kokoro 朗读模型早在 2026-10-04 就被用户剔除，只剩识别模型；现在连识别
#   模型也不随包了。）
#
# ⚠️ **读取侧仍保留"随包兜底"候选**（``voice/models.py::candidate_roots`` 与
# ``memory/local_embedding.py::candidate_dirs`` 里的 ``sys._MEIPASS/models/...``）：
# 那是给"开发机手动把模型放进 ``core/models/`` 再打包"这种**本地验证路径**
# 留的口子。产品主路径是用户目录，两边顺序不能反。

# ---- 明确排除：绝不把开发期依赖打进安装包 ---------------------------------- #
# pytest 只差一个 import 就会被链进来，多出十几 MB 且毫无用处。
excludes = [
    "pytest",
    "_pytest",
    "pytest_asyncio",
    "respx",
    "tkinter",
    "matplotlib",
    "pandas",
    "scipy",
    "IPython",
    "jupyter",
    "notebook",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    # kubernetes（74 MB）：只服务 Chroma Cloud，本地 PersistentClient 根本不用。
    # 两种模式都安全，能省下最大的一块纯死重。
    "kubernetes",
    #
    # ⚠️ `opentelemetry` **绝对不能排**。
    # 它看起来像"死重"（chromadb 只用它做可选追踪），但它是 `mcp` 的**必需依赖**
    # （mcp 2.2.0 的元数据里明写 `opentelemetry-api>=1.28.0`），且
    # `mcp/server/lowlevel/server.py:57` 是在**模块顶层**
    # `from mcp.server._otel import OpenTelemetryMiddleware`，
    # 而 `mcp/server/_otel.py:6` 又无条件 `from opentelemetry.trace import ...`。
    # 排掉它的后果是 MCP **整个不可用**（`import mcp` 直接 ModuleNotFoundError），
    # 报错还发生在与 OpenTelemetry 毫不相干的模块里，极难定位。
    # 这个坑是本轮**实际构建 + 跑 verify:core 之后**才暴露的，静态分析看不出来。
]

if not WITH_MEMORY:
    # 不带长期记忆时，把整个 chromadb 依赖树排除干净，
    # 否则 long_term.py 里那句惰性 `import chromadb` 会被静态分析发现并链进来。
    #
    # `numpy` 必须在这里排掉：chromadb 会把它带进来，而本项目**刻意不用 numpy**
    # （图表是纯 Python 生成 SVG）。漏排的代价是产物直接涨 31 MB —— 实测过一次，
    # 57.3 MB → 88.3 MB。它不在上面的基础列表里，就是为了留给 WITH_MEMORY 分支。
    excludes += ["chromadb", "onnxruntime", "tokenizers", "huggingface_hub", "numpy"]
    # grpcio（12.8 MB）/ hf_xet（9 MB）同样只服务 chromadb，
    # 不带长期记忆时一并排掉。放在这里而不是基础列表里，是因为
    # WITH_MEMORY 模式下 chromadb 可能真的会用到它们。
    excludes += ["grpcio", "hf_xet"]
else:
    # chromadb 需要 numpy，这时不能排它
    excludes += ["pandas", "matplotlib", "scipy"]

a = Analysis(  # noqa: F821 - spec 文件由 PyInstaller 执行，这些名字由它注入
    [os.path.join(SPEC_DIR, "entry.py")],
    pathex=[SRC_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="agent-core",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX 压缩会被杀软大量误报，宁可包大一点
    console=True,  # 必须为 True：Electron 主进程靠 stdout 读取端口握手
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="agent-core",
)

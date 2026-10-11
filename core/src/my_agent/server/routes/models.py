"""模型服务商管理接口（设置中心「模型服务商」页签使用）。

⚠️ **``api_key`` 现在以明文下发**（用户明确要求）。这里曾经是脱敏预览，
配套一套"这个 Key 我没改过"的判定逻辑，而那套逻辑**反复出事故** ——
详见 ``_preserve_api_keys`` 的说明。

存储侧不变：磁盘上密钥走 DPAPI 加密的 ``secrets.bin``，``models.json`` 里恒为空串
（见 ``config/secrets.py`` 的 ``strip_secrets``）。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...config.schemas import ModelsConfig, ModelSpec
from ...errors import ConfigError
from ...security.urls import validate_endpoint
from ..deps import get_runtime
from ..runtime import AppRuntime

logger = logging.getLogger(__name__)


def _require_safe_endpoint(url: str, *, field: str = "base_url") -> None:
    """校验端点并把 ``ConfigError`` 转成 400。

    ``ConfigError`` 的默认状态码是 500，但这里的原因是**用户填错了**，
    返回 500 会让人以为服务端出了故障，然后去查日志而不是改配置。
    """
    try:
        validate_endpoint(url, field=field)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

router = APIRouter(tags=["models"], prefix="/v1/models")

# 设置中心里「添加服务商」用的预设，省去用户手填 base_url。
#
# ``token_limit`` 是**新建模型时的默认上下文窗口**。关于它有两条经验，都值得写下来：
#
# 1. **必须逐家给，不能用一个统一数字。** Moonshot 预设里的模型就叫
#    ``moonshot-v1-32k``（名字中的 32k 就是窗口），本地 Ollama 跑 8B 模型通常
#    也只有 32K；而云端旗舰普遍 128K 起步。用一个数，要么浪费前者、要么饿死后者。
# 2. **宁可偏大，不要偏小。** 设小了是"过早把老对话压成摘要"——一种**安静的**
#    能力损失，用户只会觉得模型变笨了，根本联想不到是配置；设大了最坏是撞到厂商
#    报错，而那条路已经由 ``agent/context.py`` 的"压缩后重试"兜住了。
#    **可自愈的失败，好过静默的损失。**
#
# 顺带说明：这些数字是写进来的**默认值**，用户在「设置 → 模型」里可以改。
# 厂商调整窗口上限很频繁，所以不要把这里的数字当成权威 —— 它只负责让首次配置
# 就落在一个合理范围，而不是让用户自己去查。
#
# ``models`` 清单同样是**出厂快照**（按各家官方文档核对），真正的
# 权威是「同步」按钮（``POST /sync``，用已存的 Key 实时拉取）。快照的职责：
# 用户**还没填 Key** 时也能看到一个可用的候选列表 —— 多数厂商的列表接口
# 要鉴权，没 Key 时实时拉不到，这是快照唯一存在的原因。
PRESETS: list[dict[str, Any]] = [
    {
        # 产品要求把硅基流动加回来，并放在 DeepSeek **上方**：
        # 它有免费额度，是"先试试看"最省事的一家 —— 新用户不该先被"去充值"拦住。
        # 名字里的括号备注是给用户看的**利益点**，不是说明文档：所以直接写进
        # ``name``（列表里就看得到），而不是塞进 hover 提示里。
        "provider": "siliconflow",
        "name": "硅基流动（领16元免费token）",
        "base_url": "https://api.siliconflow.cn/v1",
        # ⚠️ **只有 deepseek**，且 `deepseek-v4-flash` 放首位（产品要求：
        # 这家默认就用它）。
        #
        # 为什么清单里不列 Qwen / GLM 那些：硅基流动的模型广场是"几十家厂商的合集"，
        # 全都列出来等于让用户在配置**一家服务商**时面对一整片目录，真正要用的
        # 被淹没。界面侧还会对"获取模型"的结果做同样的过滤（见
        # desktop 的 `filterDiscoveredModels`）；这里守住"没填 Key 时的候选"那一份。
        # 想在这家上跑别的模型，直接在模型名输入框里手打即可 —— 收窄列表不等于禁用。
        "models": [
            "deepseek-v4-flash",
            "deepseek-ai/DeepSeek-V4-Flash",
        ],
        # ⚠️ 这里是用户的**邀请注册**链接（带邀请码）。它同时当 docs 与 apply_url：
        # 这家没有独立的"控制台首页"值得跳，「获取 Key」直接落到注册/登录后
        # 能创建密钥的那一页，用户少绕一圈。
        "docs": "https://cloud.siliconflow.cn/i/hFzKx7Px",
        "apply_url": "https://cloud.siliconflow.cn/i/hFzKx7Px",
        "token_limit": 131072,
    },
    {
        # 产品要求：服务商名写成"中文名（品牌名）"的形式。
        # 光写 `DeepSeek` 对不认识它的用户就是一串字母，而这一栏是他挑服务商时
        # 唯一能看到的说明 —— 沿用上面硅基流动那套做法（括注写进 `name`，
        # 不做"要 hover 才看得到"的提示）。
        #
        # ⚠️ `provider` 值**一个字都不能动**：它是适配器路由、平台 Profile、
        # `filterDiscoveredModels` 的键，改了会让这一家的模型整个连不上。
        "provider": "deepseek",
        "name": "深度求索（DeepSeek）",
        "base_url": "https://api.deepseek.com/v1",
        # 2026-09 按官方定价页核实：当前在售 deepseek-flash（V4.1-Flash）与
        # deepseek-v4-pro，均为 1M 上下文。旧的 deepseek-chat/reasoner 已不在
        # 在售清单里（旧请求会被映射，但新配置不该再用旧名）。
        "models": ["deepseek-flash", "deepseek-v4-pro"],
        "docs": "https://platform.deepseek.com",
        "apply_url": "https://platform.deepseek.com/api_keys",
        "token_limit": 1048576,
    },
    {
        # 同上：让不认识 OpenAI 的用户一眼知道这就是 ChatGPT 那家。
        # （用户原话写的是 `ChatGpt`，按标准拼写落成 `ChatGPT`；`provider` 值不动。）
        "provider": "openai",
        "name": "OpenAI（ChatGPT）",
        "base_url": "https://api.openai.com/v1",
        # 2026-09 核实：当前旗舰 gpt-5.2 系列；gpt-4o 系列已进入退役通道
        "models": ["gpt-5.2", "gpt-5.1", "gpt-5-mini", "gpt-4.1"],
        "docs": "https://platform.openai.com",
        "apply_url": "https://platform.openai.com/api-keys",
        "token_limit": 400000,
    },
    {
        "provider": "dashscope",
        "name": "通义千问（阿里云百炼）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen3.8-max", "qwen-max", "qwen-plus", "qwen-turbo", "qwen3-vl-plus"],
        "docs": "https://bailian.console.aliyun.com",
        # 百炼控制台是单页应用，「创建 API Key」靠这个 hash 直接落到那一屏；
        # 只给根地址的话用户还得自己在控制台里找一圈。
        "apply_url": "https://bailian.console.aliyun.com/?apiKey=1#/api-key",
        "token_limit": 262144,
    },
    # ---- 按产品要求补齐主流服务商（4 → 17 家）------ #
    #
    # 三条口径（产品定下的，**改动前先读**）：
    #
    # ① **本次是口径反转**：Kimi / 智谱 / 豆包 曾经被要求从这里剔除（那时整个列表只有 4 家），
    #    现在产品要求把主流服务商补齐 —— 连同 MiniMax / 混元 / 文心 / 阶跃，
    #    以及国外的 Claude / Gemini / Grok / OpenRouter / Groq / Mistral 一起加回来。
    #    上面那 4 家**顺序一个字没动**（硅基流动在 DeepSeek 上方是用户先前的要求），
    #    新增的按"国内 → 国外"排在后半段。
    #
    # ② **新增的这几家 `models` 留空**（用户明确选的）：宁可让用户点一次「获取模型」
    #    或手打模型名，也不要预设里写一个**可能不存在**的模型名 ——
    #    那种错的表现是"照着预设选了却报模型不存在"，而用户完全不知道该怪谁。
    #    留空时界面不给默认值、保存会被 `canSubmit` 拦住，用户看得见自己还差哪一步。
    #
    # ③ **思考强度按各家文档写**（映射在 `llm/platform.py` 的 `_PROFILES`）：
    #    能确认的用各家真字段（豆包 / 智谱的 `thinking` 对象、OpenRouter 的
    #    `reasoning.effort`、Claude 走原生扩展思考）；确认不了的走 OpenAI 风格
    #    `reasoning_effort` + 自适应回退（回退时档位失效但对话不中断）。
    #
    # ④ **申请页地址在 用真实请求逐家点过一遍**（用户开代理让我核的，不是猜的）：
    #    17 家全部可达；`base_url` 也一并探过（不带 Key 请求 `/models`：401/403 = 端点存在）。
    #    - `openai` / `xai` 被 Cloudflare 反爬挡在命令行外（**浏览器里正常**，403 不等于坏链）；
    #    - `mistral` 的命令行响应是"登录跳转"（`return_to` 指回 api-keys 页）⇒ **链接是对的**；
    #    - `gemini` 的 OpenAI 兼容面**没有** `GET /models`（实测 404），但
    #      `POST /chat/completions` 回的是"model is not specified"⇒ 端点本身没问题，
    #      只是这家**用不了「获取模型」**，模型名要手填 —— 这是它的实现，不是我们配错。
    #      据此改准了两处：火山方舟 → 直达 API Key 管理页；Claude → 新域名 `platform.claude.com`。
    #    另有两处**故意不动**：硅基流动仍用**邀请注册**链接（用户当初的取舍：新用户先拿到
    #    免费额度比直达 AK 页更重要）；Kimi 仍用 `platform.moonshot.cn`（国内域名，它自己会
    #    200 跳到新控制台 `platform.kimi.com`；换成新域名反而要担"国内能不能连"的风险）。
    {
        "provider": "moonshot",
        "name": "月之暗面（Kimi）",
        "base_url": "https://api.moonshot.cn/v1",
        "models": [],
        "docs": "https://platform.moonshot.cn",
        "apply_url": "https://platform.moonshot.cn/console/api-keys",
        "token_limit": 262144,
    },
    {
        "provider": "zhipu",
        "name": "智谱（GLM）",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": [],
        "docs": "https://docs.bigmodel.cn",
        "apply_url": "https://open.bigmodel.cn/usercenter/apikeys",
        "token_limit": 131072,
    },
    {
        "provider": "volcengine",
        "name": "豆包（火山方舟）",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": [],
        "docs": "https://www.volcengine.com/docs/82379",
        # 直达「API Key 管理」那一屏（实测 200）；
        # 只给控制台首页 `console.volcengine.com/ark` 的话用户还得在左侧菜单里找一圈
        "apply_url": "https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey",
        "token_limit": 262144,
    },
    {
        "provider": "minimax",
        "name": "MiniMax（海螺）",
        "base_url": "https://api.minimaxi.com/v1",
        "models": [],
        "docs": "https://platform.minimaxi.com",
        "apply_url": "https://platform.minimaxi.com/user-center/basic-information/interface-key",
        "token_limit": 204800,
    },
    {
        "provider": "hunyuan",
        "name": "腾讯混元（Hunyuan）",
        "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "models": [],
        "docs": "https://cloud.tencent.com/document/product/1729",
        "apply_url": "https://console.cloud.tencent.com/hunyuan/api-key",
        "token_limit": 131072,
    },
    {
        "provider": "qianfan",
        "name": "百度文心（千帆）",
        "base_url": "https://qianfan.baidubce.com/v2",
        "models": [],
        "docs": "https://cloud.baidu.com/doc/qianfan-api",
        "apply_url": "https://console.bce.baidu.com/iam/#/iam/apikey/list",
        "token_limit": 131072,
    },
    {
        "provider": "stepfun",
        "name": "阶跃星辰（StepFun）",
        "base_url": "https://api.stepfun.com/v1",
        "models": [],
        "docs": "https://platform.stepfun.com/docs",
        "apply_url": "https://platform.stepfun.com/interface-key",
        "token_limit": 131072,
    },
    {
        # ⚠️ Claude 是**唯一走自己原生协议**的一家：它的请求/响应结构与 OpenAI
        # 兼容格式不同（`/v1/messages`、content blocks、扩展思考 `budget_tokens`），
        # 所以这里必须标 `adapter`，否则会用 OpenAI 兼容路径去请求、必然 404。
        # 见 `llm/adapters/anthropic.py` 与 `ModelSettings.tsx::newModelFromPreset`。
        "provider": "anthropic",
        "name": "Anthropic（Claude）",
        "base_url": "https://api.anthropic.com",
        "adapter": "anthropic",
        "models": [],
        "docs": "https://docs.claude.com",
        # ⚠️ 控制台已迁到 `platform.claude.com`（实测：
        # `console.anthropic.com/settings/keys` 会 200 跳到这个新地址）。
        # 直接写新地址少一跳，也免得旧域名哪天真的下线。
        "apply_url": "https://platform.claude.com/settings/keys",
        "token_limit": 200000,
    },
    {
        "provider": "gemini",
        "name": "Google（Gemini）",
        # Gemini 的 OpenAI 兼容端点（官方提供），路径里就带着 openai
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": [],
        "docs": "https://ai.google.dev/gemini-api/docs",
        "apply_url": "https://aistudio.google.com/apikey",
        "token_limit": 1048576,
    },
    {
        "provider": "xai",
        "name": "xAI（Grok）",
        "base_url": "https://api.x.ai/v1",
        "models": [],
        "docs": "https://docs.x.ai",
        "apply_url": "https://console.x.ai",
        "token_limit": 131072,
    },
    {
        "provider": "openrouter",
        "name": "OpenRouter（聚合网关）",
        "base_url": "https://openrouter.ai/api/v1",
        "models": [],
        "docs": "https://openrouter.ai/docs",
        "apply_url": "https://openrouter.ai/settings/keys",
        # 聚合网关背后是不同的厂商，窗口差别极大 —— 取一个中间值，用户可改
        "token_limit": 131072,
    },
    {
        "provider": "groq",
        "name": "Groq（超快推理）",
        "base_url": "https://api.groq.com/openai/v1",
        "models": [],
        "docs": "https://console.groq.com/docs",
        "apply_url": "https://console.groq.com/keys",
        "token_limit": 131072,
    },
    {
        "provider": "mistral",
        "name": "Mistral（欧洲模型）",
        "base_url": "https://api.mistral.ai/v1",
        "models": [],
        "docs": "https://docs.mistral.ai",
        "apply_url": "https://console.mistral.ai/api-keys",
        "token_limit": 131072,
    },
    # 本地 Ollama 预设仍按产品决策不出现：不再作为内置服务商（产品要求）。
    # ``_discover_local`` 与 loopback 探测逻辑保留为内部能力
    # （本机地址仍然可用，"添加服务商"里手填 localhost 即可）。
]


class TestModelRequest(BaseModel):
    """支持两种用法：测试已保存的模型（``model_id``）或测试尚未保存的草稿。"""

    model_id: str | None = None
    spec: ModelSpec | None = None


class DiscoverRequest(BaseModel):
    base_url: str
    api_key: str = Field("", description="可为空，本地端点通常不需要")


def _mask(spec: ModelSpec) -> dict[str, Any]:
    """把一条模型交给前端展示。

    ⚠️ **``api_key`` 这里是明文，不是脱敏预览。**

    历史上下发的是 ``sk-a******klmn`` 这种预览，再靠请求里的
    ``api_key_unchanged`` 标记回传"我没改过"。那套约定反复出事故：任何一次
    "空值被当成新值提交"都会把真 Key 覆盖掉，而症状是"模型突然不能用了"，
    用户完全不知道自己做错了什么（他自己也不知道刚才点了什么）。

    用户的要求是把这件事变简单：**明文常显**。字段里永远是真字符，
    自动保存提交的也永远是真值 —— **"用户改没改"这个判断环节整个消失**，
    那一整类 bug 就从结构上不可能发生（要求 1、2）。

    安全性说明：渲染层本来就能按条取明文（``bridge.revealSecret``），
    这里只是把"一次一条、需确认"放宽成"随列表下发"。这是**用户明确选择的**
    可用性取舍；密钥的**存储**没有降级（仍是 DPAPI 加密的 ``secrets.bin``，
    磁盘上不是明文）。
    """
    data = spec.model_dump(mode="json")
    data["api_key"] = spec.api_key
    data["has_api_key"] = bool(spec.api_key)
    data["display_name"] = spec.display_name()
    return data


def _preserve_api_keys(old: ModelsConfig, new: ModelsConfig) -> ModelsConfig:
    """守住一条铁律：**空值永远不清除密钥**。

    清除只能由用户**显式动作**触发 —— 前端为那条 spec 带上
    ``clear_api_key=True``（界面上是「清除密钥」按钮，而且要二次确认）。

    ## 为什么把"空值 = 清除"这个语义删掉

    它曾经是本项目的**反复事故源**。旧实现的两条判据（``api_key_unchanged``
    标记、掩码串比对）都建立在"前端手里是脱敏预览"这个前提上，而那个前提很脆：

    - Electron 侧与 Python 侧的掩码格式曾经不一致 → "没改过"被判成"改过了"，
      掩码串被当成真 Key 写进配置。症状是**保存后立刻连不上、重启又好了**。
    - 只要 ``has_api_key`` 因为任何原因（密钥库条目缺失、注入时机、正在刷新）
      是 false，前端就不会带 ``api_key_unchanged``，于是一次普通自动保存就把
      Key 清成了空串。用户的原话正是"不知道操作了什么，密钥就被清空了"。
    - 明文回填走的是异步 IPC，存在"回填还没到、自动保存先到"的竞态。

    三条都指向同一个结论：**不该存在任何"用空值表达删除"的路径。**
    所以现在即使前端把每个值都提交成空串，密钥也一个都不会丢（要求 3）。

    ## 现在只有两条判据

    1. ``spec.clear_api_key`` 为真 → 真的清掉（用户显式点的「清除密钥」）。
    2. 其他任何情况 → 提交值为空就沿用旧值，非空就用新值。
    """
    for spec in new.models:
        previous = old.get(spec.id)
        if previous is None:
            # 新加的模型：可能是「同步」新增的条目，显式声明从旧配置的
            # 某条继承 Key（前端现在拿得到明文，但"同步"是一次批量操作，
            # 由锚点继承比让前端逐条复制更不容易漏）。
            if spec.inherit_key_from:
                source = old.get(spec.inherit_key_from)
                if source is not None and source.api_key:
                    spec.api_key = source.api_key
            spec.api_key_unchanged = False
            spec.clear_api_key = False
            continue

        if spec.clear_api_key:
            # 用户显式要求的删除。这是**唯一**能删掉密钥的路径。
            spec.api_key = ""
            logger.info("用户显式清除了模型 %s 的密钥", spec.id)
        elif spec.api_key and spec.api_key == previous.masked_api_key():
            # 兜底：老前端（或浏览器缓存里的旧页面）可能原样回传脱敏预览。
            # 新前端不会再拿到预览，但"把 ``sk-r******7890`` 当成真 Key 存进去"
            # 的后果是**模型直接不可用**，而这一条判断的成本几乎为零 —— 留着。
            spec.api_key = previous.api_key
        elif (spec.api_key_unchanged or not spec.api_key) and previous.api_key:
            # **空值不清除**：保住旧 Key。
            #
            # 这里特意留一条日志：这一类问题以前只能靠猜（"用户不知道操作了什么"），
            # 有了这条记录，下次再出现就能直接看出是谁在什么时候提交了空值。
            spec.api_key = previous.api_key
            logger.info(
                "模型 %s 本次提交的密钥为空，已沿用已保存的密钥（空值不再表示删除）",
                spec.id,
            )

        # 标记是请求元数据，别让它留在内存里的配置对象上
        spec.api_key_unchanged = False
        spec.clear_api_key = False
    return new


@router.get("")
async def list_models(request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    config = runtime.config.models
    return {
        "default_model": config.default_model,
        "effective_default": runtime.registry.default_id,
        "models": [_mask(m) for m in config.models],
        "presets": PRESETS,
    }


@router.put("")
async def save_models(payload: ModelsConfig, request: Request) -> dict[str, Any]:
    """整体替换模型配置（设置中心的保存动作）。

    前端持有完整列表，整体替换比逐条 PATCH 更不容易出现中间态不一致。
    """
    runtime: AppRuntime = get_runtime(request)
    merged = _preserve_api_keys(runtime.config.models, payload)
    try:
        await runtime.reload_models(merged)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    return {
        "default_model": runtime.config.models.default_model,
        "effective_default": runtime.registry.default_id,
        "models": [_mask(m) for m in runtime.config.models.models],
    }


def _fast(spec: ModelSpec) -> ModelSpec:
    """给"测试连通性 / 获取模型 / 同步"用的**短超时**副本。

    这三个动作都只是拉一次模型列表，正常都是秒级；沿用模型对话的
    120s 超时会让用户在断网上干等两分钟才看到报错。15s 足够覆盖
    最慢的厂商，也足够快地暴露"连不上"。
    """
    return spec.model_copy(update={"timeout": 15.0})


@router.post("/test")
async def test_model(payload: TestModelRequest, request: Request) -> dict[str, Any]:
    """连通性测试：调用端点的 ``GET /models``，返回延迟与可用模型列表。"""
    runtime: AppRuntime = get_runtime(request)

    spec: ModelSpec | None = None
    if payload.spec is not None:
        spec = payload.spec
    elif payload.model_id:
        spec = runtime.config.models.get(payload.model_id)
        if spec is None:
            raise HTTPException(status_code=404, detail=f"模型 {payload.model_id} 不存在")

    if spec is None:
        raise HTTPException(status_code=400, detail="必须提供 model_id 或 spec")

    # ``base_url`` 来自请求体，而服务端会按它发请求 —— 这是 SSRF 的入口。
    # 校验放在这里（输入边界）而不是 test_model 内部：那边拿到的还可能是
    # 配置里已存的地址，报错口径不一样（那里该提示"配置有问题"而不是"参数不合法"）
    _require_safe_endpoint(spec.base_url)

    result = await runtime.test_model(_fast(spec))
    if result.get("ok"):
        models = result.get("models") or []
        if models and spec.model_name not in models:
            result["warning"] = (
                f"端点可用，但模型列表中未包含「{spec.model_name}」。"
                f"请确认模型名是否正确。"
            )
    return result


def _is_loopback(url: str) -> bool:
    """是否是本机地址（Ollama / LM Studio / vLLM 这类本地推理服务）。"""
    from ...llm.adapters.openai_compat import is_loopback_url

    return is_loopback_url(url)


async def _discover_local(
    runtime: AppRuntime, base_url: str, api_key: str
) -> dict[str, Any] | None:
    """本机推理服务的模型列表；不是本机地址就返回 None 交给通用逻辑。

    **为什么要单独处理**：Ollama 的模型列表在 ``/api/tags`` 上，跟 OpenAI 兼容的
    ``/v1/models`` 不是一回事。用户填的地址又常常带 ``/v1``（照着兼容接口的习惯），
    拼出来是 ``/v1/models`` —— 部分版本有这个路由、部分没有，于是表现为
    "明明装了 Ollama 却拿不到模型列表"，而报错只是个 404，很容易被误判成
    "Ollama 不支持"。

    所以这里先按 Ollama 的原生接口试，再退回 OpenAI 兼容接口（后者覆盖
    LM Studio、vLLM 这些只提供兼容端点的服务）。
    """
    from ...memory.embedding import list_ollama_models, normalize_ollama_url

    names = list_ollama_models(base_url)
    if names:
        return {"models": names, "latency_ms": None, "backend": "ollama"}

    # 不是 Ollama：补上 /v1 再按兼容接口试一次（用户可能只填了地址和端口）
    root = normalize_ollama_url(base_url)
    for candidate in (base_url, f"{root}/v1"):
        spec = ModelSpec(
            id="_discover",
            base_url=candidate,
            api_key=api_key,
            model_name="_discover",
            adapter="openai_compat",
        )
        result = await runtime.test_model(_fast(spec))
        if result.get("ok"):
            result["backend"] = "openai_compat"
            result["base_url"] = candidate
            return result
    return None


@router.post("/discover")
async def discover_models(payload: DiscoverRequest, request: Request) -> dict[str, Any]:
    """根据 base_url + api_key 拉取该端点可用的模型名，用于「添加服务商」时自动填充。"""
    runtime: AppRuntime = get_runtime(request)
    _require_safe_endpoint(payload.base_url)

    if _is_loopback(payload.base_url):
        # 连不上要给出**人话**，而不是底层异常 —— 本机用户最容易卡在"没启动"上
        local = await _discover_local(runtime, payload.base_url, payload.api_key)
        if local is not None:
            return local
        raise HTTPException(
            status_code=400,
            detail=(
                "连不上本机推理服务。请确认它已经启动"
                "（例如 Ollama 需要先运行，默认地址 http://127.0.0.1:11434），"
                "并且地址填写正确。"
            ),
        )

    spec = ModelSpec(
        id="_discover",
        base_url=payload.base_url,
        api_key=payload.api_key,
        model_name="_discover",
        adapter="openai_compat",
    )
    result = await runtime.test_model(_fast(spec))
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "连接失败"))
    return {"models": result.get("models", []), "latency_ms": result.get("latency_ms")}


class SyncRequest(BaseModel):
    """以某条已保存的模型为凭据，同步它所在服务商的真实模型清单。"""

    model_id: str


@router.post("/sync")
async def sync_provider_models(payload: SyncRequest, request: Request) -> dict[str, Any]:
    """拉取某服务商**当前真实提供**的模型清单（设置中心「同步」按钮）。

    与 ``/discover`` 的分工：discover 服务"添加时"（地址和 Key 都在手上），
    sync 服务"已保存的配置"—— 从已存的条目里取地址与 Key，不用前端重传，
    也就不会把 Key 再广播一遍。

    Ollama 走本地接口**免 Key**；云端厂商的列表接口要鉴权，没 Key 的条目
    会得到一句明确的人话，而不是一个 401 原始报错。
    """
    runtime: AppRuntime = get_runtime(request)
    spec = runtime.config.models.get(payload.model_id)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"模型 {payload.model_id} 不存在")

    _require_safe_endpoint(spec.base_url)

    if _is_loopback(spec.base_url):
        local = await _discover_local(runtime, spec.base_url, spec.api_key)
        if local is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "连不上本机推理服务。请确认它已经启动"
                    "（例如 Ollama 需要先运行，默认地址 http://127.0.0.1:11434）。"
                ),
            )
        return {"models": local["models"], "backend": local.get("backend", "local")}

    if not spec.api_key:
        raise HTTPException(
            status_code=400,
            detail=(
                "这家厂商的模型列表接口需要 API Key。请先在该服务商的任意一个"
                "模型里填好 Key，再点「同步」。（本地 Ollama 不需要 Key）"
            ),
        )

    result = await runtime.test_model(_fast(spec))
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "同步失败"))
    models = result.get("models", [])
    return {"models": models, "latency_ms": result.get("latency_ms")}

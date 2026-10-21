




























from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field




from ...security.interaction import KIND_SECRET, InteractionRequest
from ...security.secret_ref import SECRET_NAME_PATTERN
from ..base import BaseSkill, SkillContext
from ..decorator import skill


class _Field(BaseModel):


    name: str = Field(
        ...,
        pattern=SECRET_NAME_PATTERN,
        description=(
            "引用名：之后模型在请求里写 {{secret:这个名字}} 来使用它。"
            "只用英文字母、数字、下划线、短横，见名知意（如 wallet_private_key、api_secret）。"
            "⚠️ 这个名字会留在对话记录里，所以**别把真实密钥写进名字**。"
        ),
    )
    label: str = Field(..., description="给用户看的字段名（中文），如「钱包私钥」")
    hint: str = Field("", description="一句话提示：去哪儿找、长什么样、注意什么")
    multiline: bool = Field(False, description="内容很长时设为 true（如整份 JSON 凭据）")


class _Input(BaseModel):
    fields: list[_Field] = Field(
        ...,
        min_length=1,
        max_length=6,
        description="要用户提供的字段，1 到 6 项。只列真正需要的，别顺手多要几个。",
    )
    reason: str = Field(
        ...,
        description=(
            "为什么需要它 —— 会显示在弹窗顶部。写清「用来做什么」，用户才判断得出该不该给："
            "「用来调用你的交易所接口查余额」比「需要密钥」可信得多。"
        ),
    )


@skill(
    name="request_secret",
    display_name="请你提供密钥",
    description=(
        "当你需要用户提供**敏感凭据**（私钥、API Secret、访问令牌、密码等）时用它。"
        "它会弹出一个输入弹窗让用户安全地粘贴：内容只存在这台电脑上，"
        "**你永远看不到明文**，也不会发给模型厂商。"
        "用户提交后你会拿到一个引用名，之后在 http_request / http_fetch 的 url、"
        "headers 或 body 里写 {{secret:名字}} 即可，真正发请求时会在本地换成明文。"
        "⚠️ **绝不要**让用户在聊天里把私钥打给你，也不要把它写进回答 —— 用这个技能。"
    ),
    params_model=_Input,
    category="system",
    permission_level="safe",
    
    timeout=86400,
    tags=["交互", "密钥", "安全"],
)
class RequestSecretSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = _Input(**params)

        request = InteractionRequest(
            request_id=uuid4().hex,
            skill_name="request_secret",
            display_name="请你提供密钥",
            kind=KIND_SECRET,
            payload={
                "reason": args.reason,
                "fields": [
                    {
                        "name": item.name,
                        "label": item.label,
                        "hint": item.hint,
                        "multiline": item.multiline,
                    }
                    for item in args.fields
                ],
            },
            prompt=args.reason,
        )
        answer = await ctx.ask_interaction(request)

        
        
        
        
        return {"ok": True, "result": _describe(answer, [item.name for item in args.fields])}


def _describe(answer: dict[str, Any], asked: list[str]) -> str:





    if answer.get("cancelled"):
        if answer.get("interrupted"):
            return "用户没有提供（这次任务被停止或会话被关闭了）。如果需要，请重新问一次。"
        if answer.get("reason") == "no_channel":
            return (
                "当前环境没有可用的输入弹窗（例如定时任务里没人能作答），用户无法提供密钥。"
                "请改用不需要这个凭据的做法；如果确实非它不可，就告诉用户"
                "「这件事需要你提供一个凭据，请在正常对话里让我发起这个请求」。"
            )
        return "用户取消了，没有提供。不要重试、也不要换个说法再要一次；如需继续，先问他是否愿意。"

    names = [str(item) for item in (answer.get("names") or []) if str(item).strip()]
    if not names:
        
        
        return "用户提交了，但没有带回可用的引用名。请重新发起一次。"

    listed = "、".join(f"`{item}`" for item in names)
    missing = [item for item in asked if item not in names]
    text = (
        f"已收到（存在本机，我看不到内容）：{listed}。"
        f"需要用它时，在 http_request / http_fetch 的 url、headers 或 body 里写 "
        f"{{{{secret:{names[0]}}}}} 就行 —— 真正发请求时会在本地替换成明文，"
        "不会出现在对话记录里。"
    )
    if missing:
        
        
        text += f" ⚠️ 这几位用户没有提供：{'、'.join(missing)} —— 引用它们会失败，需要的话再问一次。"
    return text

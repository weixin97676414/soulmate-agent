









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





    try:
        validate_endpoint(url, field=field)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

router = APIRouter(tags=["models"], prefix="/v1/models")





















PRESETS: list[dict[str, Any]] = [
    {
        
        
        
        
        "provider": "siliconflow",
        "name": "硅基流动（领16元免费token）",
        "base_url": "https://api.siliconflow.cn/v1",
        
        
        
        
        
        
        
        
        
        
        
        
        "models": [
            "deepseek-v4-flash",
            "deepseek-ai/DeepSeek-V4-Flash",
        ],
        
        
        
        "docs": "https://cloud.siliconflow.cn/i/hFzKx7Px",
        "apply_url": "https://cloud.siliconflow.cn/i/hFzKx7Px",
        "token_limit": 131072,
    },
    {
        
        
        
        
        
        
        
        "provider": "deepseek",
        "name": "深度求索（DeepSeek）",
        "base_url": "https://api.deepseek.com/v1",
        
        
        
        "models": ["deepseek-flash", "deepseek-v4-pro"],
        "docs": "https://platform.deepseek.com",
        "apply_url": "https://platform.deepseek.com/api_keys",
        "token_limit": 1048576,
    },
    {
        
        
        "provider": "openai",
        "name": "OpenAI（ChatGPT）",
        "base_url": "https://api.openai.com/v1",
        
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
        
        
        "apply_url": "https://bailian.console.aliyun.com/?apiKey=1#/api-key",
        "token_limit": 262144,
    },
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
]


class TestModelRequest(BaseModel):


    model_id: str | None = None
    spec: ModelSpec | None = None


class DiscoverRequest(BaseModel):
    base_url: str
    api_key: str = Field("", description="可为空，本地端点通常不需要")


def _mask(spec: ModelSpec) -> dict[str, Any]:


















    data = spec.model_dump(mode="json")
    data["api_key"] = spec.api_key
    data["has_api_key"] = bool(spec.api_key)
    data["display_name"] = spec.display_name()
    return data


def _preserve_api_keys(old: ModelsConfig, new: ModelsConfig) -> ModelsConfig:

























    for spec in new.models:
        previous = old.get(spec.id)
        if previous is None:
            
            
            
            if spec.inherit_key_from:
                source = old.get(spec.inherit_key_from)
                if source is not None and source.api_key:
                    spec.api_key = source.api_key
            spec.api_key_unchanged = False
            spec.clear_api_key = False
            continue

        if spec.clear_api_key:
            
            spec.api_key = ""
            logger.info("用户显式清除了模型 %s 的密钥", spec.id)
        elif spec.api_key and spec.api_key == previous.masked_api_key():
            
            
            
            spec.api_key = previous.api_key
        elif (spec.api_key_unchanged or not spec.api_key) and previous.api_key:
            
            
            
            
            spec.api_key = previous.api_key
            logger.info(
                "模型 %s 本次提交的密钥为空，已沿用已保存的密钥（空值不再表示删除）",
                spec.id,
            )

        
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






    return spec.model_copy(update={"timeout": 15.0})


@router.post("/test")
async def test_model(payload: TestModelRequest, request: Request) -> dict[str, Any]:

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

    from ...llm.adapters.openai_compat import is_loopback_url

    return is_loopback_url(url)


async def _discover_local(
    runtime: AppRuntime, base_url: str, api_key: str
) -> dict[str, Any] | None:











    from ...memory.embedding import list_ollama_models, normalize_ollama_url

    names = list_ollama_models(base_url)
    if names:
        return {"models": names, "latency_ms": None, "backend": "ollama"}

    
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

    runtime: AppRuntime = get_runtime(request)
    _require_safe_endpoint(payload.base_url)

    if _is_loopback(payload.base_url):
        
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


    model_id: str


@router.post("/sync")
async def sync_provider_models(payload: SyncRequest, request: Request) -> dict[str, Any]:









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

"""天气查询技能。

默认走 `wttr.in <https://wttr.in>`_：它**不需要 API Key**，装上就能用。
这一点很重要——如果要求用户先去注册和风天气再拿 Key，这个技能在"第一次
打开应用"时就是不可用的，体验上等于没有。

自动补充穿衣建议，因为"今天杭州适合穿什么"才是用户的真实诉求，
单纯报温度等于把判断工作丢回给用户。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field

from ....errors import SkillExecutionError
from ....skill.base import BaseSkill, SkillContext
from ....skill.decorator import skill
from ....utils.http import async_client

WTTR_ENDPOINT = "https://wttr.in/{city}"
TIMEOUT = 20.0


def _clothing_advice(temp: float, description: str, wind_kmph: float) -> str:
    """按温度给出穿衣建议。"""
    if temp >= 30:
        base = "短袖短裤，尽量待在阴凉处"
    elif temp >= 26:
        base = "短袖、薄裤，注意补水"
    elif temp >= 22:
        base = "长袖衬衫或薄T恤，早晚可加一件薄外套"
    elif temp >= 17:
        base = "长袖 + 薄外套，体感偏凉"
    elif temp >= 12:
        base = "针织衫或夹克，建议穿长裤"
    elif temp >= 7:
        base = "厚外套或毛衣，注意保暖"
    elif temp >= 0:
        base = "棉服或薄羽绒服"
    else:
        base = "厚羽绒服、围巾手套，注意防寒"

    hints: list[str] = []
    if any(keyword in description for keyword in ("雨", "阵雨", "雷")):
        hints.append("有降水，记得带伞")
    if "雪" in description:
        hints.append("有雪，注意路面湿滑")
    if wind_kmph >= 30:
        hints.append("风力较大，建议穿防风外套")
    if any(keyword in description for keyword in ("晴", "太阳")) and temp >= 26:
        hints.append("紫外线较强，注意防晒")

    return "；".join([base, *hints]) if hints else base


class WeatherParams(BaseModel):
    city: str = Field(..., description="城市名称，中文或英文均可，例如「杭州」「Shanghai」")
    days: int = Field(1, ge=1, le=3, description="预报天数，1 表示只看今天，最多 3 天")


@skill(
    name="weather_query",
    display_name="查询天气",
    description=(
        "查询指定城市的实时天气与未来几天的预报，并附带穿衣建议。"
        "当用户问「今天天气怎么样」「明天要下雨吗」「去北京要穿什么」时使用。"
        "不需要 API Key，直接用城市名查询即可。"
    ),
    params_model=WeatherParams,
    category="life",
    permission_level="safe",
    tags=["天气", "出行"],
)
class WeatherQuerySkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = WeatherParams(**params)
        city = args.city.strip()
        if not city:
            raise SkillExecutionError("请提供城市名称。")

        try:
            async with async_client(timeout=TIMEOUT, follow_redirects=True) as client:
                response = await client.get(
                    WTTR_ENDPOINT.format(city=city),
                    params={"format": "j1", "lang": "zh"},
                    headers={"User-Agent": "curl/8.0"},
                )
        except httpx.HTTPError as exc:
            raise SkillExecutionError(
                f"查询天气失败，无法连接天气服务：{exc}。请确认网络可用，或稍后重试。"
            ) from exc

        if response.status_code != 200:
            if response.status_code == 404:
                raise SkillExecutionError(
                    f"找不到城市「{city}」。请确认城市名是否正确，可尝试用拼音或英文名。"
                )
            raise SkillExecutionError(f"天气服务返回 {response.status_code}，请稍后重试。")

        try:
            data = response.json()
        except ValueError as exc:
            raise SkillExecutionError("天气服务返回了非预期的内容，请稍后重试。") from exc

        current_list = data.get("current_condition") or []
        if not current_list:
            raise SkillExecutionError(f"没有查到「{city}」的天气数据。")
        current = current_list[0]

        def number(source: dict[str, Any], key: str, default: float = 0.0) -> float:
            try:
                return float(source.get(key, default))
            except (TypeError, ValueError):
                return default

        description = ""
        desc_list = current.get("lang_zh") or current.get("weatherDesc") or []
        if desc_list:
            description = str(desc_list[0].get("value", "")).strip()

        temperature = number(current, "temp_C")
        wind = number(current, "windspeedKmph")

        forecast: list[dict[str, Any]] = []
        for day in (data.get("weather") or [])[: args.days]:
            # wttr.in 的每日描述藏在 hourly 里，索引 4 对应正午时段
            hourly = day.get("hourly") or []
            noon = hourly[4] if len(hourly) > 4 else (hourly[0] if hourly else {})
            day_desc_list = (noon.get("lang_zh") or noon.get("weatherDesc") or [])
            day_desc = str(day_desc_list[0].get("value", "")).strip() if day_desc_list else ""
            max_temp = number(day, "maxtempC")
            min_temp = number(day, "mintempC")
            forecast.append(
                {
                    "date": day.get("date"),
                    "max_temp": max_temp,
                    "min_temp": min_temp,
                    "description": day_desc,
                    "chance_of_rain": number(noon, "chanceofrain"),
                    "clothing_advice": _clothing_advice(max_temp, day_desc, wind),
                }
            )

        nearest = data.get("nearest_area") or []
        resolved_area = ""
        if nearest:
            area_names = nearest[0].get("areaName") or []
            if area_names:
                resolved_area = str(area_names[0].get("value", "")).strip()

        # 穿衣建议用「当前温度 + 今天整体天气」来算：
        # 此刻是多云、但今天有雷阵雨时，只按"多云"给建议会漏掉带伞提醒。
        today_description = (forecast[0]["description"] if forecast else "") or description

        return {
            "city": city,
            "resolved_area": resolved_area or None,
            "observed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "current": {
                "temperature": temperature,
                "feels_like": number(current, "FeelsLikeC"),
                "description": description,
                "humidity": number(current, "humidity"),
                "wind_kmph": wind,
                "wind_direction": current.get("winddir16Point"),
                "visibility_km": number(current, "visibility"),
                "precipitation_mm": number(current, "precipMM"),
            },
            "clothing_advice": _clothing_advice(temperature, today_description, wind),
            "forecast": forecast,
            "data_source": "wttr.in",
        }

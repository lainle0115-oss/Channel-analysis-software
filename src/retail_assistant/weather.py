from __future__ import annotations

import json
import ssl
from datetime import datetime
from typing import Callable
from urllib.parse import urlencode
from urllib.request import urlopen

import certifi


LOCATIONS = {
    "上海": (31.2304, 121.4737),
    "苏州": (31.2989, 120.5853),
}

WEATHER_CODES = {
    0: "晴",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    80: "阵雨",
    81: "较强阵雨",
    82: "强阵雨",
    95: "雷暴",
    96: "雷暴伴冰雹",
    99: "强雷暴伴冰雹",
}


def weather_code_label(code: object) -> str:
    try:
        return WEATHER_CODES.get(int(code), "天气变化")
    except (TypeError, ValueError):
        return "天气变化"


def fetch_city_weather(
    city: str,
    opener: Callable[..., object] = urlopen,
) -> dict[str, object]:
    latitude, longitude = LOCATIONS[city]
    query = urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,wind_gusts_10m",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code,wind_gusts_10m_max",
        "timezone": "Asia/Shanghai",
        "forecast_days": 7,
    })
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    with opener(f"https://api.open-meteo.com/v1/forecast?{query}", timeout=8, context=ssl_context) as response:
        payload = json.loads(response.read().decode("utf-8"))

    current = payload.get("current", {})
    daily = payload.get("daily", {})
    highs = [float(value) for value in daily.get("temperature_2m_max", []) if value is not None]
    gusts = [float(value) for value in daily.get("wind_gusts_10m_max", []) if value is not None]
    max_temperature = max(highs, default=float(current.get("temperature_2m", 0) or 0))
    max_gust = max(gusts, default=float(current.get("wind_gusts_10m", 0) or 0))
    risks: list[str] = []
    if max_temperature >= 35:
        risks.append(f"未来 7 天有高温风险，最高约 {max_temperature:.0f}°C")
    if max_gust >= 62:
        risks.append(f"未来 7 天有强风/台风风险提示，最大阵风约 {max_gust:.0f} km/h，需以气象部门预警为准")
    if not risks:
        risks.append("未来 7 天暂未识别高温或强风风险")
    return {
        "城市": city,
        "当前天气": weather_code_label(current.get("weather_code")),
        "当前温度": float(current.get("temperature_2m", 0) or 0),
        "体感温度": float(current.get("apparent_temperature", 0) or 0),
        "当前风速": float(current.get("wind_speed_10m", 0) or 0),
        "最大阵风": max_gust,
        "未来最高温": max_temperature,
        "风险提示": "；".join(risks),
        "更新时间": str(current.get("time") or datetime.now().strftime("%Y-%m-%dT%H:%M")),
    }


def fetch_regional_weather(opener: Callable[..., object] = urlopen) -> tuple[list[dict[str, object]], list[str]]:
    rows: list[dict[str, object]] = []
    errors: list[str] = []
    for city in LOCATIONS:
        try:
            rows.append(fetch_city_weather(city, opener))
        except Exception as exc:
            errors.append(f"{city}天气自动获取失败：{exc}")
    return rows, errors


def format_weather_note(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "上海、苏州天气自动获取失败，请人工补充。"
    return "；".join(
        f"{row['城市']} {row['当前天气']}，{row['当前温度']:.0f}°C（体感 {row['体感温度']:.0f}°C），{row['风险提示']}"
        for row in rows
    )

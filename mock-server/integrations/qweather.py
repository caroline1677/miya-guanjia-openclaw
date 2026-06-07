# mock-server/integrations/qweather.py
import os
import requests

QWEATHER_KEY = os.getenv("QWEATHER_KEY", "")
SHENZHEN_ID = "101280601"
BASE_DEV = "https://devapi.qweather.com/v7"

def get_now_sync() -> dict:
    """当前实时天气（同步），供 SandboxEngine real_weather_fn 使用"""
    try:
        resp = requests.get(
            f"{BASE_DEV}/weather/now",
            params={"location": SHENZHEN_ID, "key": QWEATHER_KEY},
            timeout=4,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "200":
            return _fallback_weather()
        now = data["now"]
        return {
            "condition": now.get("text", ""),
            "temp_c": int(now.get("temp", 0)),
            "wind": now.get("windDir", "") + now.get("windScale", "") + "级",
            "humidity": now.get("humidity", ""),
        }
    except Exception:
        return _fallback_weather()

def get_warning() -> list:
    """灾害预警列表"""
    try:
        resp = requests.get(
            f"{BASE_DEV}/warning/now",
            params={"location": SHENZHEN_ID, "key": QWEATHER_KEY},
            timeout=4,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "200":
            return []
        return [
            {
                "type": w.get("typeName", ""),
                "level": w.get("level", ""),
                "text": w.get("text", ""),
            }
            for w in data.get("warning", [])
        ]
    except Exception:
        return []

def get_forecast_3d() -> list:
    """3天预报"""
    try:
        resp = requests.get(
            f"{BASE_DEV}/weather/3d",
            params={"location": SHENZHEN_ID, "key": QWEATHER_KEY},
            timeout=4,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "200":
            return []
        return [
            {
                "date": d["fxDate"],
                "day_text": d["textDay"],
                "night_text": d["textNight"],
                "max_temp": d["tempMax"],
                "min_temp": d["tempMin"],
            }
            for d in data.get("daily", [])
        ]
    except Exception:
        return []

def _fallback_weather() -> dict:
    return {"condition": "晴", "temp_c": 28, "wind": "东南风3级", "humidity": "65"}

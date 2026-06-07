import json
import os
import requests

LONGCAT_BASE = os.getenv("LONGCAT_BASE", "https://api.longcat.chat/openai/v1")
LONGCAT_KEY  = os.getenv("LONGCAT_KEY",  "YOUR_LONGCAT_KEY")
MODEL        = os.getenv("LONGCAT_MODEL", "LongCat-2.0-Preview")

_PROFILE_PROMPT = """你是一个餐厅模拟引擎。根据餐厅名称生成真实的运营档案。

餐厅名称：{name}

返回严格的 JSON（不要任何其他文字，不要 markdown 代码块）：
{{
  "table_types": {{
    "small":  {{"seats": 2, "total": 20, "avg_dining_min": 45}},
    "medium": {{"seats": 4, "total": 15, "avg_dining_min": 75}},
    "large":  {{"seats": 8, "total": 5,  "avg_dining_min": 120}}
  }},
  "customer_mix": {{"small": 0.4, "medium": 0.45, "large": 0.15}},
  "peak_hours": [
    {{"start": "11:30", "end": "13:30", "multiplier": 2.0}},
    {{"start": "17:30", "end": "21:00", "multiplier": 3.0}}
  ],
  "base_arrival_rate": 8,
  "personality": "一句话描述这家餐厅的排队特点"
}}"""

_EVENT_PROMPT = """你是餐厅模拟引擎的事件生成器。

餐厅：{name}
当前虚拟时间：{virtual_time}
排队：小桌{small_w}组、中桌{medium_w}组、大桌{large_w}组

生成一个真实的突发事件，影响排队状态。返回严格的 JSON（不要任何其他文字，不要 markdown 代码块）：
{{
  "description":  "事件描述（内部用）",
  "user_message": "对用户友好的说明（1句话，中文）",
  "effects": {{
    "arrival_multiplier":       1.0,
    "small_dining_multiplier":  1.0,
    "medium_dining_multiplier": 1.0,
    "large_dining_multiplier":  1.0,
    "extra_groups": {{"small": 0, "medium": 0, "large": 0}}
  }},
  "duration_ticks": 3
}}

arrival_multiplier > 1 来客增加，< 1 减少。dining_multiplier > 1 用餐变慢，< 1 翻台加速。"""

_NOTIFICATION_PROMPT = """你是喵管家 Miya，一个深圳本地生活管家。

餐厅：{restaurant}
用户号码：{queue_number}（{table_type_cn}）
当前排在第 {position} 位，预计还需等 {estimated_min} 分钟
近期事件：{event_message}
用户偏好：{user_prefs}

生成 2-3 句自然友好的中文推送消息，包含：当前排队状态、建议出门时间、是否需要叫车。
只输出消息文本，不要 JSON，不要任何格式标记。"""

DEFAULT_PROFILE = {
    "table_types": {
        "small":  {"seats": 2, "total": 20, "avg_dining_min": 45},
        "medium": {"seats": 4, "total": 15, "avg_dining_min": 75},
        "large":  {"seats": 8, "total": 5,  "avg_dining_min": 120},
    },
    "customer_mix": {"small": 0.4, "medium": 0.45, "large": 0.15},
    "peak_hours": [
        {"start": "11:30", "end": "13:30", "multiplier": 2.0},
        {"start": "17:30", "end": "21:00", "multiplier": 3.0},
    ],
    "base_arrival_rate": 8,
    "personality": "热门餐厅，高峰期排队较长",
}


def _call_llm(prompt: str, max_tokens: int = 1024) -> str:
    resp = requests.post(
        f"{LONGCAT_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {LONGCAT_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8,
            "max_tokens": max_tokens,
        },
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    # Strip markdown code fences if model wraps output
    if content.startswith("```"):
        lines = content.splitlines()
        content = "\n".join(lines[1:])
        content = content.rsplit("```", 1)[0].strip()
    return content


def generate_profile(restaurant_name: str) -> dict:
    try:
        text = _call_llm(_PROFILE_PROMPT.format(name=restaurant_name))
        return json.loads(text)
    except Exception as e:
        print(f"[llm_gen] profile gen failed ({e}), using default")
        return DEFAULT_PROFILE.copy()


def generate_event(restaurant_name: str, virtual_time: str, table_types: dict) -> dict:
    prompt = _EVENT_PROMPT.format(
        name=restaurant_name,
        virtual_time=virtual_time,
        small_w=table_types.get("small",  {}).get("waiting", 0),
        medium_w=table_types.get("medium", {}).get("waiting", 0),
        large_w=table_types.get("large",  {}).get("waiting", 0),
    )
    text = _call_llm(prompt, max_tokens=512)
    return json.loads(text)


def generate_notification(
    restaurant: str,
    queue_number: str,
    table_type_cn: str,
    position: int,
    estimated_min: int,
    event_message: str = "",
    user_prefs: str = "",
) -> str:
    prompt = _NOTIFICATION_PROMPT.format(
        restaurant=restaurant,
        queue_number=queue_number,
        table_type_cn=table_type_cn,
        position=position,
        estimated_min=estimated_min,
        event_message=event_message or "暂无特殊情况",
        user_prefs=user_prefs or "无特殊偏好",
    )
    return _call_llm(prompt, max_tokens=256)

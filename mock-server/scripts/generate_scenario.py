"""
离线用 LLM 生成演示剧本 JSON。
用法：python generate_scenario.py --scene haidilao_demo
      python generate_scenario.py --all
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests

LONGCAT_BASE = "https://api.longcat.chat/openai/v1"
LONGCAT_KEY = "YOUR_LONGCAT_KEY"

SCENARIOS = {
    "haidilao_demo": {
        "description": "周末晚餐高峰，海底捞福田排队从8桌逐渐下降到2桌，共6个tick",
        "ticks": 6,
        "start_time": "18:00",
        "restaurant": "海底捞福田",
        "constraints": [
            "排队从8桌开始，整体趋势下降，第3个tick（index=2，18:10）必须降到或低于5桌",
            "打车 eta_minutes 从8分钟逐渐增加到12分钟，surge 从1.0涨到1.3，accept_rate 从0.85降到0.7",
            "前4个tick的weather_overlay为null；第5、6个tick出现小雨: {\"condition\": \"小雨\", \"warning\": \"\"}",
        ],
    },
    "weather_event": {
        "description": "下午户外活动突然出现暴雨预警，共4个tick",
        "ticks": 4,
        "start_time": "14:00",
        "restaurant": "深圳湾餐厅",
        "constraints": [
            "前2个tick的weather_overlay为null（真实天气晴）",
            "第3个tick（index=2）weather_overlay变为暴雨: {\"condition\": \"大雨\", \"warning\": \"暴雨橙色预警\"}",
            "第4个tick保持暴雨，打车accept_rate降到0.4，eta_minutes增加到20",
            "restaurants中等位因下雨微减少",
        ],
    },
    "taxi_surge": {
        "description": "工作日下班高峰，打车涨价，共5个tick",
        "ticks": 5,
        "start_time": "18:00",
        "restaurant": "南山区餐厅",
        "constraints": [
            "打车surge从1.0逐渐涨到2.0，eta_minutes从8涨到20，accept_rate从0.9降到0.3",
            "餐厅等位人数稳定在6-8桌（下班高峰吃饭的人多）",
            "所有tick的weather_overlay均为null",
        ],
    },
}

PROMPT_TEMPLATE = """为本地生活沙盒生成演示剧本。
场景：{description}
餐厅名称：{restaurant}
共 {ticks} 个 tick，每 tick 代表 5 分钟虚拟时间，从 {start_time} 开始。

约束条件：
{constraints}

输出严格的 JSON 数组，不要输出其他任何文字，不要 markdown 代码块。
每个元素必须包含以下字段：
- "index": 整数，从0开始
- "virtual_time": 字符串，格式"HH:MM"
- "restaurants": 对象，包含 "{restaurant}" 键，值为 {{"waiting": 整数, "estimated_min": 整数}}
- "taxi": 对象，包含 {{"eta_minutes": 整数, "surge": 浮点数保留1位小数, "accept_rate": 浮点数保留2位小数}}
- "weather_overlay": null 或 {{"condition": 字符串, "warning": 字符串}}

只输出JSON数组。"""


def generate_via_llm(scene_key: str) -> list:
    cfg = SCENARIOS[scene_key]
    constraints_str = "\n".join(f"- {c}" for c in cfg["constraints"])
    prompt = PROMPT_TEMPLATE.format(
        description=cfg["description"],
        restaurant=cfg["restaurant"],
        ticks=cfg["ticks"],
        start_time=cfg["start_time"],
        constraints=constraints_str,
    )

    resp = requests.post(
        f"{LONGCAT_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {LONGCAT_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "LongCat-2.0-Preview",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()

    # Strip markdown fence if present
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    return json.loads(content)


def validate_script(script: list, scene_key: str) -> bool:
    """Basic validation that the script has required fields."""
    cfg = SCENARIOS[scene_key]
    if len(script) != cfg["ticks"]:
        print(f"  WARNING: Expected {cfg['ticks']} ticks, got {len(script)}")
    for tick in script:
        assert "index" in tick, "Missing 'index'"
        assert "virtual_time" in tick, "Missing 'virtual_time'"
        assert "restaurants" in tick, "Missing 'restaurants'"
        assert "taxi" in tick, "Missing 'taxi'"
        assert "weather_overlay" in tick or tick.get("weather_overlay") is None
        restaurant = cfg["restaurant"]
        assert restaurant in tick["restaurants"], f"Missing restaurant '{restaurant}'"
        assert "waiting" in tick["restaurants"][restaurant], "Missing 'waiting'"
        assert "eta_minutes" in tick["taxi"], "Missing 'eta_minutes'"
        assert "surge" in tick["taxi"], "Missing 'surge'"
    return True


def create_fallback(scene_key: str, output_dir: Path):
    """Create a hardcoded fallback if LLM fails."""
    fallbacks = {
        "haidilao_demo": [
            {"index": 0, "virtual_time": "18:00", "restaurants": {"海底捞福田": {"waiting": 8, "estimated_min": 45}}, "taxi": {"eta_minutes": 8, "surge": 1.0, "accept_rate": 0.85}, "weather_overlay": None},
            {"index": 1, "virtual_time": "18:05", "restaurants": {"海底捞福田": {"waiting": 7, "estimated_min": 40}}, "taxi": {"eta_minutes": 9, "surge": 1.1, "accept_rate": 0.80}, "weather_overlay": None},
            {"index": 2, "virtual_time": "18:10", "restaurants": {"海底捞福田": {"waiting": 5, "estimated_min": 28}}, "taxi": {"eta_minutes": 10, "surge": 1.1, "accept_rate": 0.78}, "weather_overlay": None},
            {"index": 3, "virtual_time": "18:15", "restaurants": {"海底捞福田": {"waiting": 4, "estimated_min": 20}}, "taxi": {"eta_minutes": 11, "surge": 1.2, "accept_rate": 0.75}, "weather_overlay": None},
            {"index": 4, "virtual_time": "18:20", "restaurants": {"海底捞福田": {"waiting": 3, "estimated_min": 15}}, "taxi": {"eta_minutes": 12, "surge": 1.2, "accept_rate": 0.72}, "weather_overlay": {"condition": "小雨", "warning": ""}},
            {"index": 5, "virtual_time": "18:25", "restaurants": {"海底捞福田": {"waiting": 2, "estimated_min": 10}}, "taxi": {"eta_minutes": 12, "surge": 1.3, "accept_rate": 0.70}, "weather_overlay": {"condition": "小雨", "warning": ""}},
        ],
        "weather_event": [
            {"index": 0, "virtual_time": "14:00", "restaurants": {"深圳湾餐厅": {"waiting": 3, "estimated_min": 15}}, "taxi": {"eta_minutes": 8, "surge": 1.0, "accept_rate": 0.90}, "weather_overlay": None},
            {"index": 1, "virtual_time": "14:05", "restaurants": {"深圳湾餐厅": {"waiting": 3, "estimated_min": 15}}, "taxi": {"eta_minutes": 9, "surge": 1.0, "accept_rate": 0.88}, "weather_overlay": None},
            {"index": 2, "virtual_time": "14:10", "restaurants": {"深圳湾餐厅": {"waiting": 2, "estimated_min": 10}}, "taxi": {"eta_minutes": 15, "surge": 1.5, "accept_rate": 0.60}, "weather_overlay": {"condition": "大雨", "warning": "暴雨橙色预警"}},
            {"index": 3, "virtual_time": "14:15", "restaurants": {"深圳湾餐厅": {"waiting": 1, "estimated_min": 5}}, "taxi": {"eta_minutes": 20, "surge": 1.8, "accept_rate": 0.40}, "weather_overlay": {"condition": "大雨", "warning": "暴雨橙色预警"}},
        ],
        "taxi_surge": [
            {"index": 0, "virtual_time": "18:00", "restaurants": {"南山区餐厅": {"waiting": 6, "estimated_min": 30}}, "taxi": {"eta_minutes": 8, "surge": 1.0, "accept_rate": 0.90}, "weather_overlay": None},
            {"index": 1, "virtual_time": "18:05", "restaurants": {"南山区餐厅": {"waiting": 7, "estimated_min": 35}}, "taxi": {"eta_minutes": 12, "surge": 1.4, "accept_rate": 0.65}, "weather_overlay": None},
            {"index": 2, "virtual_time": "18:10", "restaurants": {"南山区餐厅": {"waiting": 7, "estimated_min": 35}}, "taxi": {"eta_minutes": 15, "surge": 1.7, "accept_rate": 0.50}, "weather_overlay": None},
            {"index": 3, "virtual_time": "18:15", "restaurants": {"南山区餐厅": {"waiting": 8, "estimated_min": 40}}, "taxi": {"eta_minutes": 18, "surge": 1.9, "accept_rate": 0.35}, "weather_overlay": None},
            {"index": 4, "virtual_time": "18:20", "restaurants": {"南山区餐厅": {"waiting": 8, "estimated_min": 40}}, "taxi": {"eta_minutes": 20, "surge": 2.0, "accept_rate": 0.30}, "weather_overlay": None},
        ],
    }
    script = fallbacks[scene_key]
    out_path = output_dir / f"{scene_key}.json"
    out_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Fallback saved: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成演示剧本 JSON")
    parser.add_argument("--scene", choices=list(SCENARIOS.keys()), help="指定剧本")
    parser.add_argument("--all", action="store_true", help="生成所有剧本")
    args = parser.parse_args()

    if not args.all and not args.scene:
        parser.print_help()
        sys.exit(1)

    scenes = list(SCENARIOS.keys()) if args.all else [args.scene]
    output_dir = Path(__file__).parent.parent / "scenarios"
    output_dir.mkdir(exist_ok=True)

    for scene in scenes:
        print(f"生成剧本: {scene} ...", end=" ", flush=True)
        try:
            script = generate_via_llm(scene)
            validate_script(script, scene)
            out_path = output_dir / f"{scene}.json"
            out_path.write_text(
                json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            first_waiting = list(script[0]["restaurants"].values())[0]["waiting"]
            print(f"OK ({len(script)} ticks, T0 waiting={first_waiting}) -> {out_path}")
        except Exception as e:
            print(f"FAILED: {e}")
            # Create a fallback script manually
            print(f"  Using fallback script for {scene}")
            create_fallback(scene, output_dir)

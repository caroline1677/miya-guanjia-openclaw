#!/usr/bin/env python3
"""
plan_outing.py — 行程编排核心逻辑

读取候选活动 JSON，根据约束条件过滤、排序，输出 2-3 个行程方案。

用法:
  python3 plan_outing.py --candidates candidates.json --duration half_day --interests "美食,看展" --budget 300 --weather sunny --pet-friendly true

输入 candidates.json 格式:
{
  "activities": [
    {
      "name": "海上世界",
      "type": "景点",
      "address": "南山区蛇口",
      "coordinates": "113.923,22.487",
      "rating": 4.5,
      "duration_hours": 2,
      "indoor": false,
      "pet_friendly": true,
      "tags": ["拍照", "海边", "逛街"],
      "requires_booking": false,
      "opening_hours": "10:00-22:00",
      "estimated_cost": 0
    }
  ]
}

输出: JSON 格式的 2-3 个行程方案
"""

import json
import sys
import argparse
from datetime import datetime, timedelta


def load_candidates(path: str) -> list:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('activities', [])


def filter_by_duration(activities: list, duration: str) -> list:
    """根据时长过滤活动"""
    duration_map = {
        '2h': (0, 2),
        'half_day': (2, 5),
        'full_day': (5, 10),
        'evening': (1, 4),
    }
    min_h, max_h = duration_map.get(duration, (0, 10))
    return [a for a in activities if min_h <= a.get('duration_hours', 2) <= max_h]


def filter_by_pet_friendly(activities: list, pet_friendly: bool) -> list:
    if not pet_friendly:
        return activities
    return [a for a in activities if a.get('pet_friendly', False)]


def filter_by_weather(activities: list, weather: str) -> tuple:
    """根据天气过滤户外活动，返回 (适合的活动, 被剔除的活动)"""
    if weather in ('sunny', 'cloudy', 'overcast'):
        return activities, []
    
    rainy_weather = {'rain', 'heavy_rain', 'thunderstorm', 'drizzle'}
    if weather in rainy_weather:
        indoor = [a for a in activities if a.get('indoor', False)]
        outdoor = [a for a in activities if not a.get('indoor', False)]
        return indoor, outdoor
    
    # 高温天气：减少长时间户外活动
    if weather in ('hot', 'heatwave'):
        filtered = []
        removed = []
        for a in activities:
            if not a.get('indoor', False) and a.get('duration_hours', 2) > 2:
                removed.append(a)
            else:
                filtered.append(a)
        return filtered, removed
    
    return activities, []


def filter_by_budget(activities: list, budget: float) -> list:
    """根据预算过滤"""
    return [a for a in activities if a.get('estimated_cost', 0) <= budget]


def filter_by_interests(activities: list, interests: list) -> list:
    """根据兴趣标签过滤，至少匹配一个标签"""
    if not interests:
        return activities
    
    scored = []
    for a in activities:
        tags = set(a.get('tags', []))
        activity_type = a.get('type', '')
        match_count = sum(1 for i in interests if i in tags or i in activity_type)
        if match_count > 0:
            scored.append((match_count, a))
    
    scored.sort(key=lambda x: -x[0])
    return [a for _, a in scored]


def generate_plan_a(activities: list, interests: list, meals_needed: int) -> dict:
    """生成方案A：兴趣优先，按兴趣标签密度排列"""
    plan = {
        "id": "A",
        "title": "",
        "stops": [],
        "theme": "",
        "total_duration": 0,
        "total_cost": 0,
        "meal_count": 0
    }
    
    # 确定主题
    if interests:
        plan["theme"] = f"{interests[0]}主线"
        plan["title"] = f"方案A：{interests[0]}主线"
    else:
        plan["theme"] = "综合体验"
        plan["title"] = "方案A：综合体验"
    
    # 选 top 活动（最多4个）
    selected = activities[:4]
    current_time = datetime.strptime("09:00", "%H:%M")
    
    meal_times = ["11:30", "17:30"]
    meal_idx = 0
    
    for i, act in enumerate(selected):
        stop = {
            "time": current_time.strftime("%H:%M"),
            "name": act["name"],
            "type": act.get("type", "活动"),
            "address": act.get("address", ""),
            "duration_hours": act.get("duration_hours", 1),
            "rating": act.get("rating", 0),
            "indoor": act.get("indoor", False),
            "pet_friendly": act.get("pet_friendly", False),
            "tags": act.get("tags", []),
            "reason": act.get("reason", f"评分 {act.get('rating', 'N/A')}，适合{act.get('type', '体验')}")
        }
        plan["stops"].append(stop)
        plan["total_duration"] += act.get("duration_hours", 1)
        plan["total_cost"] += act.get("estimated_cost", 0)
        
        current_time += timedelta(hours=act.get("duration_hours", 1))
        
        # 插入用餐 stop
        if meals_needed > 0 and meal_idx < len(meal_times):
            meal_time = datetime.strptime(meal_times[meal_idx], "%H:%M")
            if current_time >= meal_time or i == len(selected) - 1:
                plan["stops"].append({
                    "time": meal_times[meal_idx],
                    "name": "[用餐]",
                    "type": "restaurant",
                    "address": "",
                    "duration_hours": 1,
                    "rating": 0,
                    "indoor": True,
                    "pet_friendly": False,
                    "tags": [],
                    "reason": "此处插入餐厅推荐（调用 consumption-decision）"
                })
                plan["meal_count"] += 1
                plan["total_duration"] += 1
                current_time = meal_time + timedelta(hours=1)
                meal_idx += 1
        
        # 活动间交通时间
        if i < len(selected) - 1:
            current_time += timedelta(minutes=20)
    
    return plan


def generate_plan_b(activities: list, interests: list, meals_needed: int) -> dict:
    """生成方案B：地理优先，按区域聚集减少通勤"""
    plan = {
        "id": "B",
        "title": "方案B：地理优化线",
        "stops": [],
        "theme": "减少通勤",
        "total_duration": 0,
        "total_cost": 0,
        "meal_count": 0
    }
    
    # 按区域分组（简化：按地址前两个字分组）
    area_groups = {}
    for act in activities:
        area = act.get("address", "")[:2]
        if area not in area_groups:
            area_groups[area] = []
        area_groups[area].append(act)
    
    # 选最大的区域组作为主区域
    main_area = max(area_groups, key=lambda k: len(area_groups[k]))
    main_acts = area_groups[main_area][:4]
    other_acts = [a for k, v in area_groups.items() if k != main_area for a in v][:2]
    
    # 主区域活动 + 1-2个其他区域活动
    ordered = main_acts[:3] + other_acts[:1]
    
    current_time = datetime.strptime("09:30", "%H:%M")  # 方案B稍晚出发
    meal_times = ["12:00", "18:00"]
    meal_idx = 0
    
    for i, act in enumerate(ordered):
        stop = {
            "time": current_time.strftime("%H:%M"),
            "name": act["name"],
            "type": act.get("type", "活动"),
            "address": act.get("address", ""),
            "duration_hours": act.get("duration_hours", 1),
            "rating": act.get("rating", 0),
            "indoor": act.get("indoor", False),
            "pet_friendly": act.get("pet_friendly", False),
            "tags": act.get("tags", []),
            "reason": act.get("reason", f"位于{main_area}片区，减少通勤")
        }
        plan["stops"].append(stop)
        plan["total_duration"] += act.get("duration_hours", 1)
        plan["total_cost"] += act.get("estimated_cost", 0)
        
        current_time += timedelta(hours=act.get("duration_hours", 1))
        
        # 用餐
        if meals_needed > 0 and meal_idx < len(meal_times):
            meal_time = datetime.strptime(meal_times[meal_idx], "%H:%M")
            if current_time >= meal_time or i == len(ordered) - 1:
                plan["stops"].append({
                    "time": meal_times[meal_idx],
                    "name": "[用餐]",
                    "type": "restaurant",
                    "address": "",
                    "duration_hours": 1,
                    "rating": 0,
                    "indoor": True,
                    "pet_friendly": False,
                    "tags": [],
                    "reason": f"在主区域{main_area}附近用餐（调用 consumption-decision）"
                })
                plan["meal_count"] += 1
                plan["total_duration"] += 1
                current_time = meal_time + timedelta(hours=1)
                meal_idx += 1
        
        if i < len(ordered) - 1:
            current_time += timedelta(minutes=15)  # 同区域交通时间短
    
    return plan


def generate_plan_c(activities: list, interests: list, meals_needed: int) -> dict:
    """生成方案C：混搭/备选"""
    # 混合A和B的特点，稍晚出发，节奏更轻松
    plan = {
        "id": "C",
        "title": "方案C：慢节奏混搭",
        "stops": [],
        "theme": "轻松随性",
        "total_duration": 0,
        "total_cost": 0,
        "meal_count": 0
    }
    
    # 选评分最高的3个活动
    by_rating = sorted(activities, key=lambda a: -a.get('rating', 0))[:3]
    
    current_time = datetime.strptime("10:00", "%H:%M")  # 最懒的出发时间
    
    for i, act in enumerate(by_rating):
        stop = {
            "time": current_time.strftime("%H:%M"),
            "name": act["name"],
            "type": act.get("type", "活动"),
            "address": act.get("address", ""),
            "duration_hours": act.get("duration_hours", 1),
            "rating": act.get("rating", 0),
            "indoor": act.get("indoor", False),
            "pet_friendly": act.get("pet_friendly", False),
            "tags": act.get("tags", []),
            "reason": act.get("reason", f"高分推荐 ⭐{act.get('rating', 'N/A')}")
        }
        plan["stops"].append(stop)
        plan["total_duration"] += act.get("duration_hours", 1)
        plan["total_cost"] += act.get("estimated_cost", 0)
        
        current_time += timedelta(hours=act.get("duration_hours", 1))
        
        # 只在中间安排一次用餐
        if i == 0 and meals_needed > 0:
            current_time += timedelta(hours=0.5)
            plan["stops"].append({
                "time": current_time.strftime("%H:%M"),
                "name": "[午餐]",
                "type": "restaurant",
                "address": "",
                "duration_hours": 1,
                "rating": 0,
                "indoor": True,
                "pet_friendly": False,
                "tags": [],
                "reason": "午餐推荐（调用 consumption-decision）"
            })
            plan["meal_count"] += 1
            plan["total_duration"] += 1.5
            current_time += timedelta(hours=1)
        
        if i < len(by_rating) - 1:
            current_time += timedelta(minutes=30)
    
    return plan


def determine_meals_needed(duration: str) -> int:
    """根据时长确定需要几个用餐 stop"""
    return {
        '2h': 0,
        'half_day': 1,
        'full_day': 2,
        'evening': 1,
    }.get(duration, 1)


def main():
    parser = argparse.ArgumentParser(description='行程编排引擎')
    parser.add_argument('--candidates', required=True, help='候选活动 JSON 文件路径')
    parser.add_argument('--duration', default='half_day', help='时长: 2h / half_day / full_day / evening')
    parser.add_argument('--interests', default='', help='兴趣标签，逗号分隔')
    parser.add_argument('--budget', type=float, default=500, help='预算上限')
    parser.add_argument('--weather', default='sunny', help='天气: sunny / cloudy / rain / hot')
    parser.add_argument('--pet-friendly', type=lambda x: x.lower() == 'true', default=True, help='是否宠物友好')
    args = parser.parse_args()
    
    # 加载候选
    activities = load_candidates(args.candidates)
    if not activities:
        print(json.dumps({"error": "No activities found in candidates file"}, ensure_ascii=False))
        sys.exit(1)
    
    # 过滤
    filtered = filter_by_duration(activities, args.duration)
    filtered = filter_by_pet_friendly(filtered, args.pet_friendly)
    filtered = filter_by_budget(filtered, args.budget)
    
    # 天气过滤
    weather_filtered, removed_by_weather = filter_by_weather(filtered, args.weather)
    if weather_filtered:
        filtered = weather_filtered
    
    # 兴趣排序
    interests = [i.strip() for i in args.interests.split(',') if i.strip()]
    filtered = filter_by_interests(filtered, interests)
    
    if len(filtered) < 2:
        print(json.dumps({
            "error": "Not enough activities match the criteria",
            "total_input": len(activities),
            "after_filter": len(filtered),
            "suggestion": "Try relaxing constraints: increase budget, remove pet-friendly filter, or broaden interests"
        }, ensure_ascii=False))
        sys.exit(1)
    
    # 生成方案
    meals_needed = determine_meals_needed(args.duration)
    
    plan_a = generate_plan_a(filtered, interests, meals_needed)
    plan_b = generate_plan_b(filtered, interests, meals_needed)
    plan_c = generate_plan_c(filtered, interests, meals_needed)
    
    output = {
        "plans": [plan_a, plan_b, plan_c],
        "metadata": {
            "duration": args.duration,
            "interests": interests,
            "budget": args.budget,
            "weather": args.weather,
            "pet_friendly": args.pet_friendly,
            "total_candidates": len(filtered),
            "weather_removed": len(removed_by_weather),
            "note": "[用餐] 标记的 stop 需要调用 consumption-decision skill 填充具体餐厅"
        }
    }
    
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
import json
import math
import sys


def parse_location(location):
    lng, lat = location.split(",")
    return float(lng), float(lat)


def haversine_m(a, b):
    lng1, lat1 = parse_location(a)
    lng2, lat2 = parse_location(b)

    r = 6371000
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)

    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(2 * r * math.atan2(math.sqrt(x), math.sqrt(1 - x)))


def reorder_nearest(origin, stops):
    remaining = stops[:]
    ordered = []
    current = origin

    while remaining:
        next_stop = min(
            remaining,
            key=lambda item: haversine_m(current["location"], item["location"])
        )
        ordered.append(next_stop)
        remaining.remove(next_stop)
        current = next_stop

    return ordered


def choose_mode(options, preferences):
    walking = options.get("walking")
    transit = options.get("transit")
    driving = options.get("driving")

    candidates = []

    if walking and walking["distance_m"] <= 1500:
        candidates.append({
            **walking,
            "mode": "walking",
            "mode_label": "步行",
            "score": 80 - walking["distance_m"] / 100
        })

    if transit:
        score = 70
        risks = []

        if preferences.get("cheapest"):
            score += 15

        if preferences.get("less_walking") and transit.get("walking_distance_m", 0) > 900:
            score -= 20
            risks.append("步行距离略长")

        if transit.get("segments_count", 0) >= 4:
            score -= 10
            risks.append("换乘较多")

        candidates.append({
            **transit,
            "mode": "transit",
            "mode_label": "公交/地铁",
            "score": score,
            "risks": risks
        })

    if driving:
        score = 65
        mode = "taxi"
        label = "打车"
        risks = []

        if preferences.get("fastest"):
            score += 15

        if preferences.get("pet_friendly"):
            score += 20

        if preferences.get("self_driving"):
            mode = "driving"
            label = "开车"
            score += 15

        candidates.append({
            **driving,
            "mode": mode,
            "mode_label": label,
            "score": score,
            "risks": risks
        })

    if not candidates:
        return None

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[0]


def format_minutes(seconds):
    return round(seconds / 60)


def ensure_polyline(selected, from_point, to_point):
    polyline = selected.get("polyline") or []
    if len(polyline) >= 2:
        return polyline, None

    return [
        from_point["location"],
        to_point["location"]
    ], "该路线图为示意图，不代表真实道路曲线"


def build_reason(selected, preferences):
    mode = selected["mode"]

    if mode == "walking":
        return "距离较短，步行比等车更省事"

    if mode == "transit":
        if selected.get("walking_distance_m", 0) > 900:
            return "费用较低，但步行距离略长"
        return "整体性价比高，适合城市内移动"

    if mode == "taxi":
        if preferences.get("pet_friendly"):
            return "考虑到宠物同行，打车更稳妥"
        if preferences.get("fastest"):
            return "节省时间，适合赶时间或跨区移动"
        return "综合耗时和舒适度更合适"

    if mode == "driving":
        return "适合自驾多点移动，路线控制更灵活"

    return "综合耗时、距离和偏好后推荐"


def assign_point_ids(points):
    output = []
    for index, point in enumerate(points, start=1):
        output.append({
            "id": index,
            "name": point["name"],
            "location": point["location"],
            "type": point.get("type", "stop"),
            "address": point.get("address")
        })
    return output


def main():
    payload = json.load(sys.stdin)

    title = payload.get("title", "多目的地路线规划")
    origin = {**payload["origin"], "type": "origin"}
    destination = payload.get("destination")
    stops = payload.get("stops", [])
    preferences = payload.get("preferences", {})
    pair_routes = payload.get("pair_routes", {})

    if payload.get("allow_reorder"):
        stops = reorder_nearest(origin, stops)

    ordered_points = [origin] + stops

    if destination:
        ordered_points.append({**destination, "type": "destination"})
    elif payload.get("return_to_origin"):
        ordered_points.append({**origin, "type": "destination"})

    points = assign_point_ids(ordered_points)

    segments = []
    total_duration_s = 0
    total_distance_m = 0
    visualization_notes = []

    for index in range(len(ordered_points) - 1):
        from_point = ordered_points[index]
        to_point = ordered_points[index + 1]
        key = f"{from_point['name']} -> {to_point['name']}"
        options = pair_routes.get(key, {})

        selected = choose_mode(options, preferences)

        if not selected:
            segments.append({
                "from": from_point["name"],
                "to": to_point["name"],
                "mode": "unknown",
                "mode_label": "待确认",
                "duration_min": None,
                "distance_km": None,
                "polyline": [from_point["location"], to_point["location"]],
                "reason": "暂时无法获得有效路线",
                "risks": ["路线数据缺失"]
            })
            visualization_notes.append("部分路段缺少真实路线数据")
            continue

        polyline, note = ensure_polyline(selected, from_point, to_point)
        if note:
            visualization_notes.append(note)

        duration_s = selected.get("duration_s", 0)
        distance_m = selected.get("distance_m", 0)

        total_duration_s += duration_s
        total_distance_m += distance_m

        segments.append({
            "from": from_point["name"],
            "to": to_point["name"],
            "mode": selected["mode"],
            "mode_label": selected["mode_label"],
            "duration_min": format_minutes(duration_s),
            "distance_km": round(distance_m / 1000, 1),
            "cost": selected.get("cost"),
            "taxi_cost": selected.get("taxi_cost"),
            "polyline": polyline,
            "reason": build_reason(selected, preferences),
            "risks": selected.get("risks", [])
        })

    result = {
        "title": title,
        "visualization_ready": all(point.get("location") for point in ordered_points),
        "points": points,
        "segments": segments,
        "summary": {
            "ordered_stops": [point["name"] for point in ordered_points],
            "total_transit_time_min": format_minutes(total_duration_s),
            "total_distance_km": round(total_distance_m / 1000, 1)
        },
        "visualization": {
            "recommended": True,
            "handoff_skill": "route_visualization",
            "preferred_outputs": ["svg", "html", "geojson"],
            "notes": list(dict.fromkeys(visualization_notes))
        }
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
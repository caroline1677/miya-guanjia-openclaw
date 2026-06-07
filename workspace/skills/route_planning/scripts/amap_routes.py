#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.parse
import urllib.request

# ============================================================
# 从 .env 文件加载 AMAP_KEY（优先于 shell 环境变量）
# ============================================================
_env_file = os.path.join(os.path.expanduser("~"), ".openclaw", ".env")
if os.path.exists(_env_file):
    for _line in open(_env_file, "r"):
        _line = _line.strip()
        if _line.startswith("AMAP_KEY=") and not os.environ.get("AMAP_KEY"):
            os.environ["AMAP_KEY"] = _line.split("=", 1)[1].strip().strip('"').strip("'")
        elif _line.startswith("AMAP_KEY="):
            # .env 优先，覆盖环境变量
            os.environ["AMAP_KEY"] = _line.split("=", 1)[1].strip().strip('"').strip("'")

AMAP_KEY = os.environ.get("AMAP_KEY")
BASE = "https://restapi.amap.com/v3"
def request(path, params):
    if not AMAP_KEY:
        raise RuntimeError("AMAP_KEY is not configured")
    params["key"] = AMAP_KEY
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("status") != "1":
        raise RuntimeError(data.get("info") or "Amap API error")
    return data
def split_polyline(polyline):
    if not polyline:
        return []
    return [item for item in polyline.split(";") if item]
def collect_step_polylines(steps):
    points = []
    for step in steps or []:
        points.extend(split_polyline(step.get("polyline")))
    return points
def resolve_place(name, city=None):
    data = request("/place/text", {
        "keywords": name,
        "city": city or "",
        "offset": 5,
        "page": 1,
        "extensions": "base"
    })
    pois = data.get("pois", [])
    if not pois:
        return None
    poi = pois[0]
    return {
        "name": poi.get("name"),
        "address": poi.get("address"),
        "location": poi.get("location"),
        "cityname": poi.get("cityname"),
        "adname": poi.get("adname"),
        "type": poi.get("type")
    }
def route_driving(origin, destination):
    data = request("/direction/driving", {
        "origin": origin,
        "destination": destination,
        "extensions": "base",
        "strategy": 10
    })
    route = data.get("route", {})
    path = (route.get("paths") or [{}])[0]
    return {
        "mode": "driving",
        "distance_m": int(path.get("distance", 0) or 0),
        "duration_s": int(path.get("duration", 0) or 0),
        "taxi_cost": route.get("taxi_cost"),
        "polyline": collect_step_polylines(path.get("steps"))
    }
def route_walking(origin, destination):
    data = request("/direction/walking", {
        "origin": origin,
        "destination": destination
    })
    route = data.get("route", {})
    path = (route.get("paths") or [{}])[0]
    return {
        "mode": "walking",
        "distance_m": int(path.get("distance", 0) or 0),
        "duration_s": int(path.get("duration", 0) or 0),
        "polyline": collect_step_polylines(path.get("steps"))
    }
def route_transit(origin, destination, city, cityd=None):
    data = request("/direction/transit/integrated", {
        "origin": origin,
        "destination": destination,
        "city": city,
        "cityd": cityd or city,
        "strategy": 0,
        "extensions": "base"
    })
    route = data.get("route", {})
    transits = route.get("transits") or []
    if not transits:
        return None
    transit = transits[0]
    polyline = []
    for segment in transit.get("segments", []):
        walking = segment.get("walking") or {}
        polyline.extend(collect_step_polylines(walking.get("steps")))
        bus = segment.get("bus") or {}
        for busline in bus.get("buslines", []):
            polyline.extend(split_polyline(busline.get("polyline")))
    return {
        "mode": "transit",
        "distance_m": int(transit.get("distance", 0) or 0),
        "duration_s": int(transit.get("duration", 0) or 0),
        "cost": transit.get("cost"),
        "walking_distance_m": int(transit.get("walking_distance", 0) or 0),
        "segments_count": len(transit.get("segments", [])),
        "polyline": polyline
    }
def route_pair(payload):
    origin = payload["origin"]
    destination = payload["destination"]
    city = payload.get("city")

    # 如果传入的是地址而非坐标，先解析坐标
    if not re.match(r'^\d+\.\d+,\d+\.\d+$', str(origin)):
        origin_resolved = resolve_place(origin, city)
        if origin_resolved:
            origin = origin_resolved["location"]
    if not re.match(r'^\d+\.\d+,\d+\.\d+$', str(destination)):
        dest_resolved = resolve_place(destination, city)
        if dest_resolved:
            destination = dest_resolved["location"]

    result = {
        "driving": route_driving(origin, destination),
        "walking": route_walking(origin, destination)
    }
    if city:
        try:
            result["transit"] = route_transit(origin, destination, city)
        except Exception as exc:
            result["transit_error"] = str(exc)
    return result
def main():
    payload = json.load(sys.stdin)
    action = payload.get("action")
    if action == "resolve_place":
        result = resolve_place(payload["name"], payload.get("city"))
    elif action == "route_pair":
        result = route_pair(payload)
    else:
        raise RuntimeError("Unsupported action")
    print(json.dumps(result, ensure_ascii=False, indent=2))
if __name__ == "__main__":
    main()
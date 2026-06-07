# mock-server/integrations/amap.py
import os
import requests

AMAP_KEY = os.getenv("AMAP_KEY", "")
BASE = "https://restapi.amap.com"

def plan_transit(origin: str, destination: str) -> dict:
    """
    公共交通路径规划。
    origin/destination 格式："经度,纬度"，例如 "114.0579,22.5431"
    返回：{"duration_min": int, "distance_km": float, "walking_distance_m": int}
    """
    resp = requests.get(
        f"{BASE}/v5/direction/transit/integrated",
        params={
            "origin": origin,
            "destination": destination,
            "city1": "深圳",
            "city2": "深圳",
            "key": AMAP_KEY,
            "show_fields": "cost,navi",
        },
        timeout=5,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "1":
        return {"error": data.get("info", "高德 API 错误")}
    route = data["route"]["transits"][0] if data["route"].get("transits") else {}
    duration_sec = int(route.get("cost", {}).get("duration", 0))
    distance_m = int(route.get("distance", 0))
    return {
        "duration_min": duration_sec // 60,
        "distance_km": round(distance_m / 1000, 1),
        "walking_distance_m": int(route.get("walking_distance", 0)),
    }

def search_poi(keyword: str, location: str = "113.9270,22.5346",
               radius: int = 5000) -> list:
    """
    POI 搜索。返回最多5条 [{"name","address","location","rating","distance_m"}]
    """
    resp = requests.get(
        f"{BASE}/v3/place/around",
        params={
            "keywords": keyword,
            "location": location,
            "radius": radius,
            "city": "深圳",
            "offset": 5,
            "page": 1,
            "key": AMAP_KEY,
            "extensions": "all",
        },
        timeout=5,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "1":
        return []
    return [
        {
            "name": p.get("name"),
            "address": p.get("address"),
            "location": p.get("location"),
            "rating": p.get("biz_ext", {}).get("rating", "暂无评分"),
            "distance_m": int(p.get("distance", 0)),
        }
        for p in data.get("pois", [])
    ]

def geocode(address: str) -> str:
    """地址 → '经度,纬度'"""
    resp = requests.get(
        f"{BASE}/v3/geocode/geo",
        params={"address": address, "city": "深圳", "key": AMAP_KEY},
        timeout=5,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "1" or not data.get("geocodes"):
        return ""
    return data["geocodes"][0]["location"]

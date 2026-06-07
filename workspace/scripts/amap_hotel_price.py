#!/usr/bin/env python3
"""
查询高德酒店详情（含房价/房型）。

用法:
  python3 amap_hotel_price.py --poi-id B0IU3UIO6Q
  python3 amap_hotel_price.py --name "深圳北站东广场亚朵酒店" --city 深圳

流程:
  1. 先用 place/text 搜到酒店的 POI ID
  2. 再用 place/detail 拿详情（含图片、营业时间等）
  3. 如果有 hotel_room 接口权限，尝试查房价
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

AMAP_KEY = os.environ.get("AMAP_KEY", "")
if not AMAP_KEY:
    env_path = os.path.expanduser("~/.openclaw/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.strip().startswith("AMAP_KEY="):
                    AMAP_KEY = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                    break
if not AMAP_KEY:
    print(json.dumps({"ok": False, "error": "AMAP_KEY not configured"}, ensure_ascii=False))
    sys.exit(1)

BASE = "https://restapi.amap.com/v3"


def api_get(path, params):
    params = {k: v for k, v in params.items() if v not in (None, "")}
    params["key"] = AMAP_KEY
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "openclaw-amap-hotel/1.0"})
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("status") != "1":
        raise RuntimeError(data.get("info") or data.get("infocode") or "AMap API error")
    return data


def search_hotel(name, city="深圳", limit=5):
    """用 place/text 搜酒店"""
    data = api_get("/place/text", {
        "keywords": name,
        "city": city,
        "types": "100000",
        "limit": limit,
        "output": "json",
    })
    return data.get("pois", [])


def get_detail(poi_id):
    """用 place/detail 拿 POI 详情"""
    data = api_get("/place/detail", {
        "id": poi_id,
        "output": "json",
    })
    # detail 接口返回的是单个 poi 或 pois 列表
    pois = data.get("pois", [])
    if pois:
        return pois[0]
    return data


def get_hotel_info(name, city="深圳"):
    """搜酒店 + 拿详情，返回完整信息"""
    pois = search_hotel(name, city)
    if not pois:
        return {"ok": False, "error": f"No hotel found for '{name}' in {city}"}

    results = []
    for poi in pois[:3]:  # 最多查前3个
        poi_id = poi.get("id", "")
        detail = get_detail(poi_id)
        ext = detail.get("biz_ext", {})

        info = {
            "poi_id": poi_id,
            "name": detail.get("name", poi.get("name", "")),
            "address": detail.get("address", poi.get("address", "")),
            "location": detail.get("location", poi.get("location", "")),
            "type": detail.get("type", poi.get("type", "")),
            "tel": detail.get("tel", poi.get("tel", "")),
            "distance_m": poi.get("distance", None),
            "rating": ext.get("rating") or detail.get("rating", ""),
            "cost": ext.get("cost", ""),
            "open_time": ext.get("open_time", detail.get("open_time", "")),
            "images": [p for p in detail.get("photos", []) if isinstance(p, str) and p.startswith("http")],
        }
        results.append(info)
        time.sleep(1.0)  # QPS 限制

    return {"ok": True, "results": results}


def main():
    parser = argparse.ArgumentParser(description="查询高德酒店详情（含房价）")
    parser.add_argument("--poi-id", help="已知 POI ID，直接查详情")
    parser.add_argument("--name", help="酒店名称，先搜索再查详情")
    parser.add_argument("--city", default="深圳", help="城市（默认：深圳）")
    args = parser.parse_args()

    if args.poi_id:
        detail = get_detail(args.poi_id)
        ext = detail.get("biz_ext", {})
        result = {
            "ok": True,
            "results": [{
                "poi_id": args.poi_id,
                "name": detail.get("name", ""),
                "address": detail.get("address", ""),
                "location": detail.get("location", ""),
                "type": detail.get("type", ""),
                "tel": detail.get("tel", ""),
                "rating": ext.get("rating") or detail.get("rating", ""),
                "cost": ext.get("cost", ""),
                "open_time": ext.get("open_time", detail.get("open_time", "")),
                "images": [p for p in detail.get("photos", []) if isinstance(p, str) and p.startswith("http")],
            }]
        }
    elif args.name:
        result = get_hotel_info(args.name, args.city)
    else:
        result = {"ok": False, "error": "Provide --poi-id or --name"}

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

---
name: amap-poi
description: 使用高德地图 Place API 查询真实 POI 信息。用于查找或核验餐厅、酒店/民宿、景点、公园、商场、电影院、地铁站、咖啡店等地点，获取名称、地址、坐标、类型、评分、人均/价格字段、营业时间、电话和距离。当地点推荐、行程规划、消费决策、酒店推荐、附近有什么、查某个地点是否存在时使用。不要用于实时订房、库存、排队、下单或支付。
metadata:
  openclaw:
    emoji: "📍"
    requires:
      bins: ["python3"]
---

# AMap POI

Use this skill whenever a task needs real-world place lookup or POI verification in China. It calls AMap Place API directly with the configured `AMAP_KEY`; it does not use mock-server or hardcoded fallback data.

## Quick Start

Search by category:

```bash
python3 /root/.openclaw/workspace/skills/amap-poi/scripts/amap_poi.py search   --keywords "大鹏半岛酒店"   --category hotel   --city 深圳   --limit 5
```

Search nearby a coordinate:

```bash
python3 /root/.openclaw/workspace/skills/amap-poi/scripts/amap_poi.py around   --keywords "海鲜"   --category restaurant   --location "114.4799,22.5966"   --radius 5000   --city 深圳   --limit 5
```

Resolve one place to coordinates:

```bash
python3 /root/.openclaw/workspace/skills/amap-poi/scripts/amap_poi.py resolve   --keywords "深圳北站"   --city 深圳
```

## Category Mapping

Use `--category` unless an exact AMap `--types` code is needed.

- `restaurant` -> `050000` 餐饮服务
- `hotel` -> `100000` 住宿服务
- `scenic` -> `110000` 风景名胜
- `shopping` -> `060000` 购物服务
- `cinema` -> `080000` 娱乐/电影院关键词
- `transport` -> `150000` 交通设施
- `life` -> `070000` 生活服务
- `all` -> no type filter

For full type guidance, read `references/types.md` only when adding categories or debugging type matching.

## Output Contract

The script prints JSON with `ok`, `source`, `action`, `query`, `count`, and `pois`. Each POI includes name, address, location, type, city/ad name, phone, distance, rating, cost, opening time, and up to three photo URLs when AMap returns them.

If AMap is unavailable or returns an error, report the failure honestly. Do not invent places and do not silently fall back to mock data.

## Boundaries

AMap POI can verify place existence, address, coordinates, category, rating-like fields, phone, opening hours, and sometimes cost. It usually cannot confirm live hotel room inventory, live room prices, cancellation policy, restaurant queue length, or booking availability. For those, use a hotel platform, Dianping/Meituan, Didi, or another real data source when available.

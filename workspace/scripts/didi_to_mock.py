#!/usr/bin/env python3
"""
didi_to_mock.py — 滴滴官方 Skill → Mock Server 桥接脚本

三步完成：自动解析坐标 → 真实数据 → 注入模拟司机

用法:
  # 只用起点终点名字（自动查坐标）
  python3 didi_to_mock.py --from '东莞站' --to '深圳北站'

  # 或指定城市+坐标
  python3 didi_to_mock.py --from '东莞站' --to '深圳北站' --city 东莞市 \
    --from-lng 113.878 --from-lat 23.090 \
    --to-lng 114.025 --to-lat 22.608
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request


def call_mcporter(tool, args_obj):
    """调 mcporter 调用滴滴 MCP 工具"""
    mcp_key = os.environ.get("DIDI_MCP_KEY", "")
    if not mcp_key:
        print(json.dumps({"error": "DIDI_MCP_KEY 未配置"}))
        sys.exit(1)
    mcp_url = f"https://mcp.didichuxing.com/mcp-servers?key={mcp_key}"
    args_json = json.dumps(args_obj, ensure_ascii=False)
    cmd = ["mcporter", "call", mcp_url, tool, "--args", args_json]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        print(json.dumps({"error": f"{tool} 超时"}))
        sys.exit(1)
    if r.returncode != 0:
        err = (r.stderr or r.stdout).strip()
        print(json.dumps({"error": f"{tool} 失败", "detail": err}))
        sys.exit(1)
    return r.stdout


def resolve_coordinates(name, city=""):
    """用 maps_textsearch 把地名转成坐标"""
    kw = name
    c = city if city else name[:2] + "市"  # "东莞站" -> "东莞市"
    args = {"keywords": kw, "city": c}
    output = call_mcporter("maps_textsearch", args)
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return None, None, name
    # maps_textsearch 返回列表 [{display_name, location: {lng, lat}}]
    if isinstance(data, list) and len(data) > 0:
        poi = data[0]
        display = poi.get("display_name", "") or poi.get("displayName", name)
        loc = poi.get("location", {})
        lng = loc.get("lng") or loc.get("longitude", "")
        lat = loc.get("lat") or loc.get("latitude", "")
        if lng and lat:
            return str(lng), str(lat), display
    # structuredContent 格式
    sc = data.get("structuredContent") or data if isinstance(data, dict) else {}
    if isinstance(sc, dict):
        pois = sc.get("poi_list") or sc.get("pois") or []
        if pois:
            poi = pois[0]
            display = poi.get("displayName", "") or poi.get("name", name)
            loc = poi.get("location", "")
            if not loc and poi.get("lat") and poi.get("lng"):
                loc = f"{poi['lng']},{poi['lat']}"
            if loc and "," in str(loc):
                parts = str(loc).split(",")
                if len(parts) == 2:
                    return parts[0].strip(), parts[1].strip(), display
    return None, None, name


def parse_driving_output(output):
    """从 maps_direction_driving 提取真实距离/时长"""
    text = output
    # 从大段文本中直接搜索 distance 和 duration
    m_dist = re.search(r'"value"\s*:\s*(\d+)', text[text.find('"distance"'):text.find('"distance"')+200]) if '"distance"' in text else None
    m_dur = re.search(r'"value"\s*:\s*(\d+)', text[text.find('"duration"'):text.find('"duration"')+200]) if '"duration"' in text else None
    try:
        data = json.loads(output)
        distance = data.get("distance", {})
        duration = data.get("duration", {})
        dist_km = round(distance.get("value", 0) / 1000, 1) if distance.get("value") else 0
        dur_min = round(duration.get("value", 0) / 60) if duration.get("value") else 0
        return dist_km, dur_min
    except json.JSONDecodeError:
        # fallback: regex
        pass
    if m_dist and m_dur:
        return round(int(m_dist.group(1))/1000, 1), round(int(m_dur.group(1))/60)
    return None, None


def parse_estimate_output(output):
    """从 taxi_estimate 提取 traceId 和真实价格"""
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return "", []
    sc = data.get("structuredContent") or data
    if not isinstance(sc, dict):
        return "", []
    trace_id = sc.get("traceId", "")
    items_raw = sc.get("items", [])
    items = []
    for item in items_raw:
        if isinstance(item, dict):
            items.append({
                "productName": item.get("productName", ""),
                "productCategory": int(item.get("productCategory", 0)),
                "priceText": str(item.get("priceText", "0")),
            })
    return trace_id, items


def inject_mock(mock_url, origin, destination, from_lng, from_lat, to_lng, to_lat,
                product_category, real_data):
    """注入 Mock Server"""
    body = {
        "origin": origin, "destination": destination,
        "origin_lng": float(from_lng), "origin_lat": float(from_lat),
        "dest_lng": float(to_lng), "dest_lat": float(to_lat),
        "product_category": int(product_category),
        "real_data": real_data,
    }
    url = f"{mock_url}/taxi/scenario"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8")[:500]
        return {"error": True, "message": f"HTTP {e.code}", "body": body_text}
    except Exception as e:
        return {"error": True, "message": str(e)}


def main():
    parser = argparse.ArgumentParser(description="滴滴真实数据 + Mock司机 一键叫车")
    parser.add_argument("--from", dest="from_name", required=True, help="起点名称（如'东莞站'）")
    parser.add_argument("--to", dest="to_name", required=True, help="终点名称（如'深圳北站'）")
    parser.add_argument("--from-lng", help="起点经度（可选，不传则自动查坐标）")
    parser.add_argument("--from-lat", help="起点纬度（可选）")
    parser.add_argument("--to-lng", help="终点经度（可选）")
    parser.add_argument("--to-lat", help="终点纬度（可选）")
    parser.add_argument("--city", default="", help="城市名（可选，用于坐标查询）")
    parser.add_argument("--product", type=int, default=1, help="车型品类（默认1=快车）")
    parser.add_argument("--mock-url", default=os.environ.get("MOCK_SERVER_URL", "http://mock-server:5001"))
    args = parser.parse_args()

    from_lng, from_lat = args.from_lng, args.from_lat
    to_lng, to_lat = args.to_lng, args.to_lat
    from_display = args.from_name
    to_display = args.to_name

    # Step 0: 自动查坐标（如果没传）
    if not from_lng or not from_lat:
        print(f"[0/3] 查起点坐标: {args.from_name}...", file=sys.stderr)
        from_lng, from_lat, from_display = resolve_coordinates(args.from_name, args.city)
        if not from_lng:
            print(json.dumps({"error": f"无法解析起点「{args.from_name}」的坐标，请手动指定 --from-lng --from-lat"}))
            sys.exit(1)
        print(f"     → {from_display} ({from_lng}, {from_lat})", file=sys.stderr)
    if not to_lng or not to_lat:
        print(f"[0/3] 查终点坐标: {args.to_name}...", file=sys.stderr)
        to_lng, to_lat, to_display = resolve_coordinates(args.to_name, args.city)
        if not to_lng:
            print(json.dumps({"error": f"无法解析终点「{args.to_name}」的坐标，请手动指定 --to-lng --to-lat"}))
            sys.exit(1)
        print(f"     → {to_display} ({to_lng}, {to_lat})", file=sys.stderr)

    # Step 1: 真实驾车距离
    print(f"[1/3] 滴滴驾车路线: {from_display} → {to_display}", file=sys.stderr)
    driving_output = call_mcporter("maps_direction_driving", {
        "origin": f"{from_lng},{from_lat}",
        "destination": f"{to_lng},{to_lat}",
        "need_geo": "false",
    })
    distance_km, duration_min = parse_driving_output(driving_output)
    if not distance_km:
        print(json.dumps({"error": "未能解析驾车路线距离"}))
        sys.exit(1)
    print(f"     📏 {distance_km}km | ⏱️ {duration_min}分钟", file=sys.stderr)

    # Step 2: 真实价格
    print(f"[2/3] 滴滴价格预估: {from_display} → {to_display}", file=sys.stderr)
    estimate_output = call_mcporter("taxi_estimate", {
        "from_name": from_display, "from_lat": from_lat, "from_lng": from_lng,
        "to_name": to_display, "to_lat": to_lat, "to_lng": to_lng,
    })
    trace_id, items = parse_estimate_output(estimate_output)
    if not items:
        print(json.dumps({"error": "未能解析滴滴价格数据"}))
        sys.exit(1)
    for item in items:
        print(f"     [{item['productCategory']:>3}] {item['productName']:<10}: {item['priceText']}元", file=sys.stderr)

    # Step 3: 注入 Mock Server
    real_data = {
        "traceId": trace_id,
        "distance_km": distance_km,
        "duration_min": duration_min,
        "items": items,
    }
    print(f"[3/3] 注入 Mock → 分配假司机...", file=sys.stderr)
    result = inject_mock(
        args.mock_url,
        from_display, to_display,
        from_lng, from_lat,
        to_lng, to_lat,
        args.product, real_data,
    )

    # 输出
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result.get("ok") and result.get("order"):
        o = result["order"]
        est = result.get("estimate", {})
        print("\n" + "=" * 50, file=sys.stderr)
        print("🚕 模拟打车订单已创建！（数据来源: 滴滴官方API）", file=sys.stderr)
        print(f"   📋 订单号: {o['order_id']}", file=sys.stderr)
        print(f"   📍 {est.get('origin','?')} → {est.get('destination','?')}", file=sys.stderr)
        print(f"   📏 {est.get('distance_km','?')}公里 | ⏱️ {duration_min}分钟", file=sys.stderr)
        print(f"   🚗 {o.get('product_name','?')} | 👤 {o['driver']['name']} | 🔢 {o['driver']['car_plate']}", file=sys.stderr)
        print(f"   💰 {o.get('estimated_price','?')}元（滴滴真实价格）", file=sys.stderr)
        print(f"   ⚠️ 司机为模拟数据，非真实打车", file=sys.stderr)
        print("=" * 50, file=sys.stderr)
        print(file=sys.stderr)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""测试真实距离计算和DiDi价格"""
import math, json, subprocess, sys, os, urllib.request

# 东莞站到深圳北站
origin = "东莞站"
dest = "深圳北站"
from_lat, from_lng = "23.090", "113.878"
to_lat, to_lng = "22.608", "114.025"

# 1. 算距离
R = 6371
dlat = math.radians(float(to_lat) - float(from_lat))
dlng = math.radians(float(to_lng) - float(from_lng))
a = math.sin(dlat/2)**2 + math.cos(math.radians(float(from_lat))) * math.cos(math.radians(float(to_lat))) * math.sin(dlng/2)**2
c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
straight = R * c
road_km = round(straight * 1.3, 1)
print(f"直线距离: {straight:.1f}km")
print(f"驾车估算(×1.3): {road_km}km")

# 2. 调DiDi
mcp_key = os.environ.get("DIDI_MCP_KEY", "2cenYJVMIdAMrrCxi3gQYxr4")
mcp_url = f"https://mcp.didichuxing.com/mcp-servers?key={mcp_key}"
args_json = json.dumps({
    "from_name": origin, "from_lat": from_lat, "from_lng": from_lng,
    "to_name": dest, "to_lat": to_lat, "to_lng": to_lng,
}, ensure_ascii=False)

cmd = ["mcporter", "call", mcp_url, "taxi_estimate", "--args", args_json]
print(f"\n调DiDi: {origin} -> {dest}")
result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

if result.returncode != 0:
    print("ERROR:", result.stderr[:300])
    sys.exit(1)

data = json.loads(result.stdout)
sc = data.get("structuredContent") or data
items = sc.get("items", [])
for item in items:
    name = item.get("productName", "?")
    price = item.get("priceText", "?")
    cat = item.get("productCategory", "?")
    print(f"  [{cat:>3}] {name:8s}: {price}元")

# 3. 注入Mock
print(f"\n注入Mock Server...")
real_data = {
    "traceId": sc.get("traceId", ""),
    "distance_km": road_km,
    "duration_min": max(5, int(road_km / 25 * 60)),
    "items": items,
}
body = json.dumps({
    "origin": origin, "destination": dest,
    "origin_lat": float(from_lat), "origin_lng": float(from_lng),
    "dest_lat": float(to_lat), "dest_lng": float(to_lng),
    "product_category": 1,
    "real_data": real_data,
}, ensure_ascii=False)

req = urllib.request.Request(
    "http://mock-server:5001/taxi/scenario",
    data=body.encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    est = result.get("estimate", {})
    order = result.get("order", {})
    print(f"  ✓ 叫车成功!")
    print(f"  距离: {est.get('distance_km')}km")
    print(f"  快车: {[p for p in est.get('product_list',[]) if p.get('product_category')==1][0]['total_price']}元")
    print(f"  来源: {[p for p in est.get('product_list',[]) if p.get('product_category')==1][0]['price_source']}")
except Exception as e:
    print(f"  ✗ {e}")

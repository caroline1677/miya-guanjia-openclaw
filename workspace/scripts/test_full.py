#!/usr/bin/env python3
"""测试全链路：东莞站->深圳北站"""
import json, math, subprocess, os, urllib.request

o, d = "东莞站", "深圳北站"
fla, fln = "23.090", "113.878"
tla, tln = "22.608", "114.025"

# 1. 距离
R = 6371
dlat = math.radians(float(tla) - float(fla))
dlng = math.radians(float(tln) - float(fln))
a = math.sin(dlat/2)**2 + math.cos(math.radians(float(fla))) * math.cos(math.radians(float(tla))) * math.sin(dlng/2)**2
c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
road = round(R * c * 1.3, 1)
print("=" * 50)
print("1. 距离计算")
print("   直线: %.1fkm" % (R * c))
print("   驾车(×1.3): %.1fkm" % road)

# 2. 调DiDi
print("\n2. 滴滴真实价格:")
print("   路线: %s -> %s" % (o, d))
key = os.environ["DIDI_MCP_KEY"]
url = "https://mcp.didichuxing.com/mcp-servers?key=" + key
args = json.dumps({"from_name": o, "from_lat": fla, "from_lng": fln, "to_name": d, "to_lat": tla, "to_lng": tln})
r = subprocess.run(["mcporter", "call", url, "taxi_estimate", "--args", args], capture_output=True, text=True, timeout=30)
sc = json.loads(r.stdout).get("structuredContent", {})
items = sc.get("items", [])
for i in items:
    print("   [%3s] %-10s: %s元" % (i["productCategory"], i["productName"], i["priceText"]))

# 3. 注入Mock
print("\n3. 注入Mock Server:")
body = json.dumps({
    "origin": o, "destination": d,
    "origin_lat": float(fla), "origin_lng": float(fln),
    "dest_lat": float(tla), "dest_lng": float(tln),
    "product_category": 1,
    "real_data": {
        "traceId": sc.get("traceId", ""),
        "distance_km": road,
        "duration_min": max(5, int(road / 25 * 60)),
        "items": items
    }
})
req = urllib.request.Request("http://mock-server:5001/taxi/scenario", data=body.encode(), headers={"Content-Type": "application/json"})
resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
est = resp["estimate"]
print("   Mock返回product_list:")
for p in est["product_list"]:
    print("     [%3s] %-10s: %s元 (来源:%s)" % (p["product_category"], p["product_name"], p["total_price"], p["price_source"]))

order = resp["order"]
print("\n4. 订单结果:")
print("   订单: %s" % order["order_id"])
print("   车型: %s" % order["product_name"])
print("   价格: %s元" % order["estimated_price"])
print("   来源: %s" % order["price_source"])
print("   司机: %s (%s)" % (order["driver"]["name"], order["driver"]["car_plate"]))
print("   ETA: %s分钟" % order["eta_min"])

# 验证结果
assert abs(est["distance_km"] - road) < 0.1, "距离不对!"
kuai_items = [p for p in est["product_list"] if p["product_category"] == 1]
assert len(kuai_items) > 0, "找不到快车!"
assert kuai_items[0]["price_source"] == "real", "价格不是real来源!"
print("\n✅ 验证通过！真实滴滴价格注入成功！")

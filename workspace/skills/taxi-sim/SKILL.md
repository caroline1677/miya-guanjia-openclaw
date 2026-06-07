---
name: taxi-sim
description: "打车全流程模拟 — 价格预估→司机接单→到达上车→行程中→完成。当用户说"演示模式"或"模拟叫车"时使用，不走真实滴滴订单。用于演示叫车完整流程。"
metadata:
  openclaw:
    emoji: "🚕"
---

# 打车模拟（演示用）

当滴滴官方沙箱无法查询指定地址时，使用本 skill 获取模拟打车数据。

## 命令

### 预估打车价格

```bash
curl -s -X POST http://mock-server:5001/taxi/start \
  -H "Content-Type: application/json" \
  -d '{"origin":"起点","destination":"终点"}'
```

### 叫车（一键场景）

```bash
curl -s -X POST http://mock-server:5001/taxi/scenario \
  -H "Content-Type: application/json" \
  -d '{"origin":"起点","destination":"终点","product_category":1}'
```

### 查订单 / 查司机

```bash
curl -s http://mock-server:5001/taxi/order
curl -s http://mock-server:5001/taxi/driver
```

## 输出示例

estimate 返回：
```json
{
  "distance_km": 4.7,
  "product_list": [
    {"product_name": "快车", "total_price": 42.7},
    {"product_name": "专车", "total_price": 75.6}
  ]
}
```

scenario 返回（含司机信息）：
```json
{
  "order": {
    "order_id": "DIDI2026...",
    "driver": {"name": "张师傅", "car_plate": "粤B·12345"},
    "eta_min": 5
  }
}
```

## 支持任意地址

起终点可以是深圳市任意地点，mock-server 会根据距离自动生成模拟的打车数据。

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

美团黑客松赛题：**小深** — 住在飞书/微信里的深圳本地生活管家。基于 OpenClaw Agent 框架，具备记忆、技能、后台7×24监控能力。

## Architecture

```
用户（飞书/微信）
    ↓
OpenClaw（Docker，腾讯云 43.136.88.201:18789）
├── 管家人设: workspace/butler/SOUL.md + IDENTITY.md
├── 记忆: workspace/users/{userId}/profile.json + tasks.json + memory/YYYY-MM-DD.md
└── Skills: workspace/scripts/*.js（Node.js，在容器内运行）
        ↓ HTTP（容器内 http://mock-server:5001）
Mock API Server（Python Flask，mock-server/app.py）
├── SandboxEngine（mock-server/engine/sandbox.py）— 确定性剧本驱动
└── Integrations: 高德地图 API + 和风天气 API
```

**关键设计**：SandboxEngine 按"剧本"（tick 数组）推进，每 tick 代表5分钟虚拟时间。Watcher 注册条件（如排队≤5桌），满足时触发回调（一次性，`fired=True` 后不再触发）。`weather_overlay: null` 时使用真实天气，有值时覆盖。

## Commands

### Mock Server（在 `mock-server/` 目录下）

```bash
# 本地运行
python app.py                                    # 启动在 0.0.0.0:5001

# 测试
pytest test_sandbox.py -v                        # 运行全部测试
pytest test_sandbox.py::test_watcher_fires -v   # 运行单个测试

# 生成演示剧本
python scripts/generate_scenario.py --scene haidilao_demo
python scripts/generate_scenario.py --all

# Docker
docker build -t mock-server .
docker run -p 5001:5001 -e AMAP_KEY=xxx -e QWEATHER_KEY=xxx mock-server
```

### Mock Server Admin API（演示控制）

```bash
# 启动剧本（默认 haidilao_demo，每3秒一个tick）
curl -X POST http://localhost:5001/admin/start -H 'Content-Type: application/json' \
  -d '{"scenario": "haidilao_demo", "interval": 3.0}'

# 应急手动覆盖（保底用）
curl -X POST http://localhost:5001/admin/set -H 'Content-Type: application/json' \
  -d '{"path": "restaurants.海底捞福田.waiting", "value": 3}'

# 查看当前状态
curl http://localhost:5001/admin/state

# 查询端点（供 Skills 调用）
curl http://localhost:5001/restaurant/海底捞福田/queue
curl http://localhost:5001/taxi/estimate
curl http://localhost:5001/weather
```

### Skills（在 OpenClaw 容器内，Node.js）

```bash
# 餐厅排队查询 / 注册监控
node /workspace/scripts/restaurant_monitor.js check --restaurant "海底捞福田"
node /workspace/scripts/restaurant_monitor.js register \
  --user-id {userId} --restaurant "海底捞福田" --threshold 5

# 出行规划（调高德 + 和风）
node /workspace/scripts/trip_planner.js --user-id {userId} \
  --destination "深圳湾公园" --activity "日料" --budget 200

# 天气活动检查
node /workspace/scripts/weather_activity.js --check
node /workspace/scripts/weather_activity.js --warnings

# 记忆更新（每次对话后调用）
node /workspace/scripts/smart_memory.js --user-id {userId} \
  --conversation "用户说不吃辣，预算150"
```

### OpenClaw 服务器管理

```bash
ssh tencent                                       # SSH 别名（~/.ssh/config 已配置）
sudo docker logs openclaw --tail 50
sudo docker restart openclaw
sudo docker exec openclaw openclaw pairing approve feishu [配对码]
```

## Key Files

| 文件 | 说明 |
|------|------|
| `mock-server/engine/sandbox.py` | SandboxEngine：tick推进、Watcher触发、admin_set |
| `mock-server/engine/models.py` | Tick / Watcher dataclass |
| `mock-server/app.py` | Flask API：查询端点 + /admin/* 控制端点 |
| `mock-server/scenarios/*.json` | 演示剧本（haidilao_demo / weather_event / taxi_surge） |
| `mock-server/integrations/amap.py` | 高德：plan_transit / search_poi / geocode |
| `mock-server/integrations/qweather.py` | 和风天气：get_now / get_warning |
| `mock-server/scripts/generate_scenario.py` | 用 LLM 离线生成剧本 JSON |
| `workspace/butler/SOUL.md` | 管家全局人设（所有用户共享） |
| `workspace/TOOLS.md` | Skills 调用手册（agent 读取） |
| `workspace/users/_template/` | 用户记忆文件模板 |

## Environment Variables

```bash
AMAP_KEY=your_amap_key         # 高德地图 API Key
QWEATHER_KEY=your_qweather_key # 和风天气 API Key
WORKSPACE_PATH=/workspace      # 默认值，容器内路径
```

服务器上配置在 `~/qzqwork/.env`（参考 `.env.example`）。

## SandboxEngine 数据模型

Watcher 路径格式为点分字符串，如 `restaurants.海底捞福田.waiting`，支持操作符 `<=`、`>=`、`==`。剧本 JSON 每个 tick 必须包含：`index`、`virtual_time`、`restaurants`（含餐厅名及 `waiting`/`estimated_min`）、`taxi`（含 `eta_minutes`/`surge`/`accept_rate`）、`weather_overlay`（null 或 `{condition, warning}`）。

## 演示剧本（5个场景）

| 场景 | 触发 | 文件 |
|------|------|------|
| 海底捞排队监控 | Watcher≤5桌 → 推送+叫车 | `haidilao_demo.json` |
| 天气突变取消户外 | 暴雨预警 overlay | `weather_event.json` |
| 打车高峰涨价 | surge≥1.5 | `taxi_surge.json` |
| 周末出行规划 | 对话触发 | 高德+和风实时 |
| 记忆自动学习 | 每次对话后 | smart_memory.js |

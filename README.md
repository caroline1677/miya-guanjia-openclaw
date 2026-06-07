# 喵管家 Miya · 深圳本地生活管家

> Agent 很热闹，生产现场很骨感。这是我们在 36 小时内构建的一个**真正可运行**的 Multi-Agent Harness。

**美团黑客松 2026** · 赛题：基于 OpenClaw 的本地生活管家

---

## 一句话介绍

喵管家 Miya 是一个**住在飞书里**的深圳本地生活 AI 管家，能处理餐厅排队监控、打车叫号、路线规划、天气提醒等复合本地生活场景。它有记忆、有技能、能在后台 7×24 运行。

---

## 系统架构

```
用户（飞书）
    │
    ▼
OpenClaw Gateway（WebSocket）
    │
    ├── Miya Agent（LongCat-2.0-Preview）
    │       ├── SOUL.md + IDENTITY.md + USER.md    ← 人格 + 记忆
    │       ├── AGENTS.md + ERRORS.md              ← 行为规范 + 错误库
    │       └── workspace/skills/                  ← Skill Registry
    │
    ├── cron 调度器（monitor-poller，每 30 秒）
    │
    └── scripts/（工具层）
            restaurant_monitor.js / trip_planner.js / smart_memory.js

Mock Server（Python Flask, :5001）
    ├── RestaurantSimulator（泊松 + LLM 随机事件）
    ├── TaxiSimulator（全流程 + 真实价格注入）
    └── SandboxEngine（JSON 剧本驱动）
```

---

## 三层记忆体系

| 层级 | 文件 | 生命周期 | 内容 |
|------|------|---------|------|
| Session Cache | `users/{id}/session_cache.md` | 跨轮（覆盖写） | 上轮问题 + 关键信息 + 待跟进 |
| Daily Memory | `users/{id}/memory/YYYY-MM-DD.md` | 当天 | 决策流水 + 偏好更新 |
| Long-term Profile | `users/{id}/profile.json` | 永久 | 口味/预算/宠物/交通偏好标签 |

记忆读写通过 SOUL.md 硬性规则强制执行，不依赖 Agent 自觉。

---

## 已注册 Skill

| Skill | 触发场景 | 数据源 |
|-------|---------|--------|
| `outing-planner` 🎯 | 周末去哪 / 一日游 / 帮我安排行程 | **编排** amap-poi + route_planning + restaurant-recommender |
| `route_planning` | 多目的地路线规划 / 怎么走 | 高德路径规划 API（真实）|
| `route_visualization` | 把路线画出来 / 生成路线图 | route_plan → HTML 路线图 |
| `amap-poi` | 查地点 / 核验餐厅景点 / 附近有什么 | 高德 Place API（真实）|
| `restaurant-queue` | 帮我取号 / 排队监控 | Mock Server（RestaurantSimulator）|
| `restaurant-recommender` | 找餐厅 / 吃什么 | xhs-cli + 高德 POI |
| `qweather` | 查天气 / 带伞吗 | 和风天气 API（真实）|
| `dianping-query` | 大众点评评分 / 人均 | agent-browser |
| `xhs` | 小红书攻略 / 真实评价 | xiaohongshu-cli |
| `amap-taxi` | 叫车 / 打车预估 | 高德 API + TaxiSimulator |

> **编排亮点**：`outing-planner` 是编排型 Skill，不直接调 API，而是协调底层 Skill 完成一日游规划。各 Skill 通过标准化 `route_plan` 数据结构解耦（`compatible_skills` + `output_schema` 声明），一个 Skill 的输出直接作为另一个的输入，无需胶水代码。

---

## 典型演示场景

### 场景：周六晚上聚餐全程托管

```
用户 → "周六晚上带朋友去南山吃火锅，帮我安排"
  ↓
Miya 搜小红书 → 提取餐厅名 → 高德查 POI → 返回推荐
  ↓
用户确认"就去海底捞福田"
  ↓
Miya 取号 B004（第 12 位）→ 立即注册 cron 监控
  ↓
（后台每 30 秒轮询）
  ↓
position ≤ 5 → 飞书推送"快到了！叫车吗？"
  ↓
用户确认 → 叫车 → 张师傅·粤B12345·ETA 6分钟
```

### 启动演示剧本

```bash
# 启动海底捞剧本（每 3 秒推进 5 分钟虚拟时间）
curl -X POST http://localhost:5001/admin/start \
  -H 'Content-Type: application/json' \
  -d '{"scenario": "haidilao_demo", "interval": 3.0}'

# 查看实时沙盒状态
curl http://localhost:5001/admin/state

# 应急手动覆盖
curl -X POST http://localhost:5001/admin/set \
  -d '{"path": "restaurants.海底捞福田.waiting", "value": 3}'
```

---

## 服务启动

```bash
# 在腾讯云服务器
cd ~/.openclaw

# 启动所有服务
docker compose up -d

# 查看状态
docker compose ps
docker logs openclaw --tail 20
docker logs mock-server --tail 10
```

---

## 技术亮点

1. **三层兜底降级**：xhs-cli → agent-browser → web_search，任何一层失败自动降级
2. **跨进程限速**：xhs 包装器用文件锁确保全局 ≥15 秒间隔，防止验证码触发
3. **双模式沙盒**：剧本驱动（可重现）+ 动态模拟（泊松过程 + LLM 随机事件）
4. **强制进度反馈**：AGENTS.md 规定调用慢工具前必须先发消息，15 秒无回复 = 违规
5. **挂载卷持久化**：所有工具二进制装在挂载卷，docker recreate 不丢失
6. **ERRORS.md 知识库**：已踩坑写入文件，Agent 每次启动必读

---

## 目录结构

```
~/.openclaw/
├── docker-compose.yml       # 服务编排（openclaw + mock-server）
├── workspace/               # Miya 工作区（挂载卷）
│   ├── SOUL.md              # 人格 + 决策原则
│   ├── IDENTITY.md          # 角色定义
│   ├── AGENTS.md            # 会话规则 + 强制反馈协议
│   ├── ERRORS.md            # 已知错误知识库
│   ├── TOOLS.md             # 工具调用手册
│   ├── skills/              # Skill Registry
│   │   ├── restaurant-queue/
│   │   ├── restaurant-recommender/
│   │   ├── qweather/
│   │   ├── dianping-query/
│   │   └── xhs/
│   ├── scripts/             # Node.js 工具脚本
│   └── users/               # 用户记忆（三层）
├── mock-server/             # Python Flask 沙盒服务器
│   ├── engine/
│   │   ├── sandbox.py       # 剧本驱动引擎
│   │   ├── restaurant_sim.py # 动态餐厅模拟
│   │   └── taxi_sim.py      # 打车全流程模拟
│   └── scenarios/           # JSON 演示剧本
└── bin/                     # 持久化工具二进制（挂载卷）
    ├── xhs                  # 限速包装器
    └── uv                   # Python 包管理
```

---

## 团队

何晴 / 韩翼俊

部署：腾讯云 · 框架：OpenClaw · 模型：LongCat-2.0-Preview

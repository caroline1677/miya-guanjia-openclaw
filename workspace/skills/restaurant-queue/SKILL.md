---
name: restaurant-queue
description: >
  餐厅排队取号与智能调度。当用户选定餐厅后需要取号排队、监控排队进度、
  快到号时自动触发叫车建议时使用。
  触发词："取号"、"排队"、"等位"、"帮我排个队"、"取个号"、"到号叫我"、
  "排到了吗"、"还有几桌"。
  完整链路：取号 → 注册轮询 → 到达阈值 → LLM 生成通知 → 打车 ETA 联动 → 推送用户。
  依赖 LM 后端（mock-server:5001）提供排队 API。
---

# 餐厅排队取号 & 智能调度

后端地址：`http://mock-server:5001`（容器内网络）

---

## 上游衔接

本 skill 由 `restaurant-recommender` 触发：
- 推荐餐厅 → 用户选定 → 用户说"帮我取号" → 触发本 skill
- 推荐结果中的 `name` 作为 `--restaurant`，`address` 作为 `--restaurant-addr`

也可以独立触发（用户直接说"帮我在 XX 排队"）。

---

## 完整流程

### Step 1: 取号

**首次调用会触发 LLM 生成该餐厅档案，耗时约 5-10 秒，执行前告知用户"帮你取号中，稍等一下～"**

```bash
node /root/.openclaw/workspace/scripts/restaurant_monitor.js take \
  --user-id {userId} \
  --restaurant "海底捞福田" \
  --party-size 4
```

`--table-type` 可省略（自动按人数推断：1-2 人→小桌/small，3-5 人→中桌/medium，6+ 人→大桌/large）

返回示例：
```json
{
  "queue_number": "B004",
  "table_type": "medium",
  "table_type_cn": "中桌",
  "position": 4,
  "estimated_min": 60,
  "virtual_time": "18:00",
  "personality": "晚高峰极热，排队区有免费小吃和娱乐设施"
}
```

取号成功后立即告知用户：

> 已帮你取到 **{table_type_cn} {queue_number}** 号！当前排在第 **{position}** 位，预计等待约 **{estimated_min}** 分钟。我会一直盯着，快到了第一时间通知你 🐱

---

### Step 2: 启动后台轮询（含打车联动）

取号成功后，**立即**启动 `monitor_poller.js`（不要等用户再问）：

```bash
node /root/.openclaw/workspace/scripts/monitor_poller.js \
  --user-id {userId} \
  --restaurant "海底捞福田" \
  --queue-number {queue_number} \
  --threshold 5 \
  --table-type-cn "中桌" \
  --restaurant-addr "福田区xxx路xxx号" \
  --user-loc "南山区xxx"
```

`monitor_poller.js` 会：
- **每 30 秒**查询 `GET /restaurant/{餐厅名}/queue/{queue_number}`
- 当 `position ≤ threshold` 时：
  1. 调用 `POST /notification/queue` → LLM 生成通知文案
  2. **查询打车 ETA**（DiDi MCP，从用户位置到餐厅地址）
  3. **时间匹配决策**：剩余等待 ≈ 打车 ETA + 4 分钟缓冲 → 建议叫车
  4. 写入 HEARTBEAT.md → OpenClaw 自动推送给用户
- 检测到 `status: "seated"` / `"expired"` / `"cancelled"` 时自动结束

**参数说明**：
| 参数 | 必填 | 说明 |
|------|------|------|
| `--user-id` | ✅ | 用户标识 |
| `--restaurant` | ✅ | 餐厅名 |
| `--queue-number` | ✅ | 取号返回的号码 |
| `--threshold` | ✅ | 触发通知的桌数阈值（建议 5） |
| `--table-type-cn` | ❌ | 桌型中文（小桌/中桌/大桌，默认中桌） |
| `--restaurant-addr` | ❌ | 餐厅地址（用于查打车 ETA） |
| `--user-loc` | ❌ | 用户当前位置（缺省时读 profile.json） |

**时间匹配公式**：
```
剩余等待 = position × 每桌平均耗时（小桌 8min、中桌 12min、大桌 20min）
打车总耗时 = taxi_eta + 4min 缓冲
如果 打车总耗时 ≥ 剩余等待 - 2min → 建议叫车
```

---

### Step 3: 用户主动查进度（按需）

用户问"现在排到哪了"：

```bash
node /root/.openclaw/workspace/scripts/restaurant_monitor.js status \
  --restaurant "海底捞福田" \
  --number B004
```

返回示例：
```json
{
  "queue_number": "B004",
  "table_type_cn": "中桌",
  "position": 2,
  "estimated_min": 25,
  "status": "waiting",
  "virtual_time": "18:45",
  "current_event": "附近演唱会散场，突然涌入很多客人"
}
```

`status` 变为 `"seated"` 时表示已入座（position=0, estimated_min=0）。

若有 `current_event`，自然地告知用户（如"刚才附近散场，人突然多了，预计稍微晚一点"）。

---

### Step 4: 查餐厅整体排队（可选）

用户问"海底捞现在多少桌在排"：

```bash
node /root/.openclaw/workspace/scripts/restaurant_monitor.js check \
  --restaurant "海底捞福田"
```

返回大/中/小桌分列的等候数、就餐数、预估时间，以及当前突发事件说明。

---

### Step 5: 取消取号

用户不想等了：

```bash
node /root/.openclaw/workspace/scripts/restaurant_monitor.js cancel \
  --restaurant "海底捞福田" \
  --user-id {userId}
```

---

## 字段速查

| 字段 | 含义 |
|------|------|
| `queue_number` | 号码（如 B004），B=中桌，A=小桌，C=大桌 |
| `position` | 当前排在第几位（0=已入座） |
| `estimated_min` | 预计还需等多少分钟 |
| `status` | `waiting`=排队中，`seated`=已入座，`expired`=过号 |
| `current_event` | 当前突发事件描述（null=无） |
| `personality` | LLM 生成的餐厅排队特点（取号时返回） |

## 桌型对照

| table_type | 中文 | 号码前缀 | 适合人数 | 每桌平均耗时 |
|------------|------|----------|----------|-------------|
| small      | 小桌 | A        | 1-2 人   | 8 分钟      |
| medium     | 中桌 | B        | 3-5 人   | 12 分钟     |
| large      | 大桌 | C        | 6+ 人    | 20 分钟     |

## 降级策略

| 场景 | 处理方式 |
|------|---------|
| LM 后端不可达 | 告知用户无法线上取号，建议直接到店排队 |
| 餐厅不支持取号 | 告知用户该店暂不支持线上取号 |
| 重复取号（409） | 告知用户已有一个有效取号，继续监控 |
| poller 超时 | 建议用户手动查看或重新取号 |
| /notification/queue 失败 | 使用兜底文案（脚本自动降级） |
| DiDi MCP 不可用 | 跳过打车联动，只发排队通知 |

## 注意事项

- **不要使用旧接口** `/queue/take`、`/queue/status`、`/queue/cancel` —— 这些已废弃
- 取号后必须立刻启动 poller（Step 2），否则到号无法自动通知
- `--queue-number` 必须传入，否则 poller 无法精准追踪用户自己的号
- 暴露技术细节（API 路径、mock-server）给用户是**禁止**的，只说结果
- 打车联动只在 `position ≤ threshold` 时触发一次，避免重复通知

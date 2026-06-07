# TOOLS.md — 工具手册

脚本位置（容器内）：/root/.openclaw/workspace/scripts/
Mock Server：http://mock-server:5001（容器内网络，脚本已封装）
所有文件位置（服务器）：~/.openclaw/workspace/

---

## 用户记忆路径

- 偏好：~/.openclaw/workspace/users/{userId}/profile.json
- 任务：~/.openclaw/workspace/users/{userId}/tasks.json
- 日记：~/.openclaw/workspace/users/{userId}/memory/YYYY-MM-DD.md
- 群组：~/.openclaw/workspace/groups/{groupId}/

容器内等价路径：/root/.openclaw/workspace/users/ 等

---

## 1. restaurant_monitor.js — 餐厅排队全流程

### 标准调用顺序（用户说"帮我在X排队"）

```
第一步：取号（首次调用会触发 LLM 生成餐厅档案，约5-10秒）
  node /root/.openclaw/workspace/scripts/restaurant_monitor.js take \
    --user-id {userId} --restaurant "海底捞福田" --party-size 4
  输出：{ "queue_number": "B004", "table_type_cn": "中桌", "position": 4,
          "estimated_min": 60, "virtual_time": "18:00",
          "personality": "晚高峰极热，排队区有免费小吃和娱乐" }

第二步：注册后台监控（拿到 queue_number 后立即注册）
  node /root/.openclaw/workspace/scripts/restaurant_monitor.js register \
    --user-id {userId} --restaurant "海底捞福田" --threshold 5 \
    --queue-number "B004" --table-type "medium"
  输出：{ "ok": true, "task_id": "task_xxx" }
```

后台 monitor_poller 每30秒自动轮询。当 position ≤ threshold 时，
调用 LLM 生成通知文案并写入 HEARTBEAT.md，OpenClaw 自动推送给用户。

### 其他命令

查询餐厅整体排队状态（大/中/小桌分列）：
```
node /root/.openclaw/workspace/scripts/restaurant_monitor.js check \
  --restaurant "海底捞福田"
```
输出：
```json
{
  "restaurant": "海底捞福田",
  "virtual_time": "18:30",
  "waiting": 8,
  "estimated_min": 75,
  "table_types": {
    "small":  { "waiting": 2, "dining": 19, "estimated_min": 30 },
    "medium": { "waiting": 5, "dining": 14, "estimated_min": 75 },
    "large":  { "waiting": 1, "dining": 4,  "estimated_min": 120 }
  },
  "current_event": { "message": "附近演唱会散场，突然涌入很多客人", "remaining_ticks": 3 }
}
```

查询某个号码的当前位置：
```
node /root/.openclaw/workspace/scripts/restaurant_monitor.js status \
  --restaurant "海底捞福田" --number "B004"
```
输出：
```json
{
  "queue_number": "B004",
  "table_type_cn": "中桌",
  "position": 2,
  "estimated_min": 25,
  "status": "waiting",
  "virtual_time": "18:45",
  "current_event": "厨房出餐加快了"
}
```
`status` 变为 `"seated"` 时表示已入座（position=0, estimated_min=0）。

### table_type 说明
| table_type | 中文 | 号码前缀 | 适合人数 |
|------------|------|----------|----------|
| small      | 小桌 | A        | 1-2 人   |
| medium     | 中桌 | B        | 3-5 人   |
| large      | 大桌 | C        | 6+ 人    |

---

## 2. trip_planner.js — 出行规划

  node /root/.openclaw/workspace/scripts/trip_planner.js \
    --user-id {userId} --destination "深圳湾公园" --activity "日料" --budget 200
输出：POI推荐 + 地铁路线 + 天气的 JSON。

---

## 3. qweather / weather_qweather.js — 真实天气（和风天气 QWeather）

这是正式天气 skill 的主路径，直接调用和风天气，不走 mock-server。

当前天气：
  node /root/.openclaw/workspace/skills/qweather/scripts/weather_qweather.js now --location 深圳

3 天预报：
  node /root/.openclaw/workspace/skills/qweather/scripts/weather_qweather.js forecast --location 深圳

天气预警：
  node /root/.openclaw/workspace/skills/qweather/scripts/weather_qweather.js warnings --location 深圳

一次性查实时 + 预报 + 预警：
  node /root/.openclaw/workspace/skills/qweather/scripts/weather_qweather.js all --location 深圳

支持深圳各区：
  node /root/.openclaw/workspace/skills/qweather/scripts/weather_qweather.js all --location 南山区
  node /root/.openclaw/workspace/skills/qweather/scripts/weather_qweather.js now --location 大鹏新区

已支持：福田区、罗湖区、南山区、盐田区、宝安区、龙岗区、龙华区、坪山区、光明区、大鹏新区。

输出：JSON，包含 `condition` / `temp_c` / `forecast_days` / `warnings` 等字段。

---

## 4. smart_memory.js — 记忆更新

每次对话结束后调用：
  node /root/.openclaw/workspace/scripts/smart_memory.js \
    --user-id {userId} --conversation "用户说不吃辣，预算150"
输出：{"ok":true,"updates":{"diet.spicy":false,"budget.max":150}}

给管家起昵称：
  node /root/.openclaw/workspace/scripts/smart_memory.js \
    --user-id {userId} --set-nickname "小橘"

---

## 5. social_guide.js — 泛内容与攻略检索 (模拟小红书/马蜂窝)

用于在初期帮助用户寻找灵感、提取网红商圈或推荐菜系。
必须结合用户的长时记忆（如口味、是否养宠）来传递参数过滤。

  node /root/.openclaw/workspace/scripts/social_guide.js search \
    --user-id {userId} \
    --keywords "周末 探店" \
    --tag-filters "Mexican, 小龙虾" \
    --require-pet-friendly true

输出示例：
```json
{
  "results": [
    {"post_id": "p101", "content": "科技园附近新开的墨西哥塔可店，Fajitas绝赞，室外区域允许带猫！涉及实体店：[Taco Libre]"},
    {"post_id": "p102", "content": "周末解压必去的十三香小龙虾，营业到凌晨。涉及实体店：[大钳门排挡]"}
  ],
  "extracted_pois": ["Taco Libre", "大钳门排挡"]
}
```

---

## 6. poi_checker.js — 实体店状态查验 (模拟大众点评/美团)

拿到 `social_guide.js` 提取的 POI（实体店名）后，必须调用此工具验证真实营业状态与排队情况，绝不能直接向用户推荐未验证的店铺。

  node /root/.openclaw/workspace/scripts/poi_checker.js verify \
    --poi-name "Taco Libre" \
    --user-location "深圳湾"

输出示例：
```json
{
  "poi_name": "Taco Libre",
  "status": "OPEN",
  "is_pet_friendly": true,
  "current_queue": 2,
  "eta_mins": 15,
  "per_capita": 120,
  "tags": ["墨西哥菜", "户外就餐"]
}
```

---

## 群聊记忆聚合

加载 /root/.openclaw/workspace/groups/{groupId}/members.json，
聚合所有成员 public 字段：取最低预算、合并忌口、多数交通偏好为主。

---

## 7. xhs - 小红书原生搜索 (真实 API)

Cookie 已配置，直接使用。

重要：运行时出现 WARNING [Cookie refresh failed; using existing cookies (age: 7+ days)] 属正常现象，不代表 cookie 失效，忽略即可。只看 ok: true/false。

  xhs search "深圳南山美食"     # 搜索笔记
  xhs read <note_id>            # 读取笔记详情
  xhs comments <note_id>        # 查看评论
  xhs status                    # 检查登录状态

每次请求有 8-15 秒随机延迟（保护账号），执行前必须先告知用户正在搜索中。

---

## 8. amap-taxi — 高德打车（已弃用，改用滴滴）

已迁移至滴滴官方 skill，详见 didi-ride-skill-official。

---

## 9. didi-ride-skill — 滴滴出行（MCP）

打车、查价、叫车、查订单、路线规划（公交/驾车/步行/骑行），走滴滴官方 MCP：

  MCP_URL="https://mcp.didichuxing.com/mcp-servers?key=$DIDI_MCP_KEY"
  mcporter call "$MCP_URL" taxi_estimate --args {...}
  mcporter call "$MCP_URL" taxi_create_order --args {...}
  mcporter call "$MCP_URL" taxi_query_order --args {...}
  mcporter call "$MCP_URL" taxi_cancel_order --args {...}
---

## 9. amap-poi / amap_poi.py — 高德真实 POI 查询

这是通用高德 Place API 入口，不走 mock-server，不返回硬编码兜底数据。

文本搜索：
  python3 /root/.openclaw/workspace/skills/amap-poi/scripts/amap_poi.py search --keywords "大鹏半岛酒店" --category hotel --city 深圳 --limit 5

周边搜索：
  python3 /root/.openclaw/workspace/skills/amap-poi/scripts/amap_poi.py around --keywords "海鲜" --category restaurant --location "114.4799,22.5966" --radius 5000 --city 深圳 --limit 5

地点解析：
  python3 /root/.openclaw/workspace/skills/amap-poi/scripts/amap_poi.py resolve --keywords "深圳北站" --city 深圳

常用 category：restaurant=餐饮，hotel=住宿，scenic=景点，shopping=商场，cinema=影院，transport=交通设施。

边界：高德 POI 可查名称、地址、坐标、类型、评分、人均/价格字段、营业时间、电话和距离；不能确认酒店实时库存/房价、餐厅实时排队、预约/下单状态。


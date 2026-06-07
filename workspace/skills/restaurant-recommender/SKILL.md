---
name: restaurant-recommender
description: >
  餐厅推荐 — 综合小红书笔记搜索 + 高德地图 POI 数据，为用户生成个性化餐厅推荐。
  当用户请求"推荐餐厅"、"附近好吃的"、"南山美食"、"找餐厅"、"吃什么"时触发。
  流程：小红书搜笔记 → 提取餐厅名 → 高德查详情(人均/评分/营业时间) → 结合用户偏好排序推荐。
metadata:
  openclaw:
    emoji: "🍽️"
    requires:
      bins: ["python3", "node"]
---

# 餐厅推荐 Skill

综合小红书 UGC 内容与高德地图 POI 数据，为用户生成个性化餐厅推荐。

## 前置依赖

| 依赖 | 说明 |
|------|------|
| `xhs` Python 库 | 小红书搜索/读取（`xiaohongshu-cli`，需已认证） |
| `AMAP_KEY` | 高德 Web API Key（`~/.openclaw/.env`） |
| `python3` | 3.10+ |

**重要**：首次使用或 cookie 过期时，需先运行 `xhs login` 完成认证。脚本会在触发验证码时提示用户。

## 快速开始

```bash
python3 scripts/restaurant_recommender.py \
  --user-id <userId> \
  --location "后海地铁站" \
  --area "南山区" \
  --keywords "美食 探店" \
  --top-n 8 \
  --budget-max 200
```

## 工作流程

### Step 1: 小红书搜索

通过 `xhs search` 搜索区域美食笔记，按 popularity 和 general 各搜一轮，去重后过滤出区域相关的笔记。

```bash
xhs search "南山区 美食 探店" --sort popular --json
xhs search "南山区 美食 探店" --sort general --json
```

过滤关键词：南山、蛇口、后海、海岸城、深圳湾、南头、西丽、华侨城、科技园。

### Step 2: 读取笔记正文 & 提取餐厅

逐条读取笔记正文（优先用 `xhs read <id> --json`，超时则用 Python 库 `XhsClient.get_note_by_id()`），用正则提取餐厅名。

```bash
xhs read <note_id> --json
```

提取规则：
- 过滤 `#` 标签行、空行、纯英文短词
- 保留含中文且长度 4-40 字符的行
- 合并相同餐厅的提及次数

### Step 3: 高德 POI 查询

对提取到的每个餐厅名，调用高德文本搜索 API：

```bash
curl "https://restapi.amap.com/v3/place/text?key=$AMAP_KEY&keywords=<餐厅名>&city=深圳&limit=3"
```

提取字段：名称、地址、类型、人均(`biz_ext.cost`)、评分(`biz_ext.rating`)、营业时间(`biz_ext.open_time`)、电话、坐标。

**QPS 注意**：高德免费 API QPS 较低，每次请求间隔 ≥1.5s。

### Step 4: 推荐排序

根据用户偏好画像打分：
- 价格匹配度（是否在预算内）
- 评分加成
- 辣味偏好（火锅/川菜/湘菜/重庆/麻辣/酸汤 加权 +15）
- 海鲜偏好（海鲜/鱼/虾/蟹 加权 +10）
- 小红书提及次数（多次提及 = 更热门，最多 +15）

### Step 5: 输出格式

JSON 输出，结构如下：

```json
{
  "query": { "location": "...", "area": "...", "keywords": "...", "top_n": 8, "budget_max": 200 },
  "stats": { "xhs_notes_found": 24, "xhs_notes_read": 15, "restaurants_extracted": 42, "restaurants_with_amap": 35 },
  "recommendations": [
    {
      "name": "珮姐重庆火锅（南山直营店）",
      "address": "后海滨路3019凯宾斯基酒店裙楼2层",
      "type": "餐饮服务;中餐厅;火锅店",
      "per_capita": "123",
      "rating": "4.7",
      "open_time": "11:00-24:00",
      "tel": "18118710367",
      "location": "113.939,22.518",
      "mention_count": 3,
      "xhs_sources": ["深圳南山美食合集", "南山探店笔记"],
      "score": 42
    }
  ]
}
```

## Agent 输出规范

向用户展示推荐时：
1. **先给结论**：基于你的位置和偏好，推荐以下 N 家
2. **分类展示**：🔥强烈推荐 / 👍值得一试 / ☕休闲放松
3. **每家包含**：名称 + 步行/地铁距离 + 人均 + 评分 + 推荐菜 + 营业时间
4. **结尾追问**：是否需要查某家的排队情况 / 帮你规划探店路线

### Step 6: 衔接 restaurant-queue（取号）

用户选定某家餐厅并说"帮我取号"、"排队"、"取个号"时，自动触发 `restaurant-queue` skill：

**从推荐结果中提取关键参数传给取号脚本**：
- **餐厅名** → 推荐结果的 `name` 字段
- **餐厅地址** → 推荐结果的 `address` 字段（用于后续打车 ETA 查询）
- **用户位置** → 推荐时的 `location` 参数

**调用链**：
```
restaurant-recommender (推荐 → 用户选定)
    │  "帮我取号"
    ↓
restaurant-queue (take → monitor_poller → 通知 + 叫车)
```

> 示例：用户选了「珮姐重庆火锅（南山直营店）」并说"帮我取号，4个人"
> → 调用 `restaurant_monitor.js take --restaurant "珮姐重庆火锅（南山直营店）" --party-size 4`
> → 取号成功后立即启动 `monitor_poller.js`，传入 `--restaurant-addr` 为该店地址

**禁止**：
- 不要 1:1 搬运笔记原文
- 不要推荐没有高德数据且笔记中只出现一次的餐厅（可信度不足）
- 不要在用户未确认时执行预约/下单等高风险操作

## 参考资料

- 用户偏好画像：`~/.openclaw/workspace/USER.md`
- 高德 API 文档：[ lbs.amap.com](https://lbs.amap.com/)
- xhs CLI 文档：`xhs --help` 或 [xiaohongshu-cli](https://github.com/jackwener/xiaohongshu-cli)

## 降级策略

| 场景 | 降级方案 |
|------|---------|
| xhs 未认证 | 提示用户先执行 `xhs login` |
| 高德 QPS 超限 | 跳过高德查询，仅基于小红书数据推荐 |
| 小红书搜不到 | 扩大关键词范围（去掉区域限定） |
| 高德无 POI 数据 | 保留小红书信息，标注"暂无详细数据" |


## 小红书数据源三层兜底

xhs 出现验证码或失败时，按顺序降级，不放弃搜索，不直接报错：

**第一层：xhs（默认）**
正常情况直接用。出现 verification_required 或 not_authenticated 时立即停止，不重试，进入第二层。

**第二层：agent-browser 抓小红书搜索页**
  agent-browser open 'https://www.xiaohongshu.com/search_result?keyword=<关键词>'
  agent-browser get url
Chrome 崩溃或超时则进入第三层。

**第三层：web_search（保底，必定可用）**
使用内置 web_search 搜索：
  - site:xiaohongshu.com <区域> 餐厅推荐
  - <区域> <菜系> 好吃的

降级时只告知用户：小红书直连受限，已切换备用方式，不暴露技术细节。


---
name: route_planning
title: 多目的地路径规划
description: 使用高德地图 API 为多个目的地规划合理路线，并输出兼容路线可视化 skill 的标准路线结构。
version: 1.1.0
language: zh-CN
entrypoint: SKILL.md
scripts:
  - scripts/normalize_stops.py
  - scripts/amap_routes.py
  - scripts/plan_route.py
compatible_skills:
  - route_visualization
output_schema:
  - route_plan
  - visualization_ready_route
---
# 多目的地路径规划 Skill
## 适用场景
当用户提出以下需求时使用本 skill：
- “帮我规划一日游路线”
- “这几个地方怎么走比较顺”
- “A、B、C 三个点之间怎么安排交通”
- “帮我比较打车、地铁、步行哪个合适”
- “我有一份行程，但地点之间缺少交通方式”
- “规划完后顺便生成路线图”
## 核心目标
将多个目的地转化为一份可执行、可视化兼容的路线方案，包括：
- 每个地点的准确位置和坐标
- 推荐游玩顺序
- 每段交通方式
- 每段耗时、距离、费用
- 每段路线 polyline，如高德 API 可返回
- 风险提示
- 可直接交给 `route_visualization` 使用的标准 JSON
## 输入信息
优先提取：
- 起点
- 终点，若没有则默认最后一个目的地
- 多个目的地
- 城市
- 出发时间
- 是否允许调整游玩顺序
- 是否需要返回起点
- 是否需要生成路线图
- 交通偏好：少走路、少花钱、最快、舒服、适合带宠物、适合雨天
- 是否自驾
如果缺少城市或起点，且无法从上下文推断，应自然追问。
## 输出兼容要求
本 skill 的最终结构化输出必须兼容 `route_visualization`。
标准输出字段：
```json
{
  "title": "路线标题",
  "visualization_ready": true,
  "points": [
    {
      "id": 1,
      "name": "地点名",
      "location": "经度,纬度",
      "type": "origin | stop | destination"
    }
  ],
  "segments": [
    {
      "from": "A",
      "to": "B",
      "mode": "walking | transit | taxi | driving",
      "mode_label": "步行 / 公交地铁 / 打车 / 开车",
      "duration_min": 12,
      "distance_km": 3.4,
      "cost": "费用，如可用",
      "polyline": ["经度,纬度", "经度,纬度"],
      "reason": "推荐该交通方式的原因",
      "risks": ["风险提示"]
    }
  ],
  "summary": {
    "ordered_stops": ["A", "B", "C"],
    "total_transit_time_min": 86,
    "total_distance_km": 28.6
  },
  "visualization": {
    "recommended": true,
    "preferred_outputs": ["svg", "html", "geojson"],
    "handoff_skill": "route_visualization"
  }
}
规划原则
1. 先补全地点
所有地点必须解析为高德坐标。

如果一个地点存在多个可能结果，应优先选择：

与指定城市匹配
POI 类型符合上下文
评分或热度更高
距离起点更合理
若地点歧义过大，应询问用户确认。

2. 再决定顺序
如果用户明确给出顺序，默认尊重。

如果用户允许“帮我排顺一点”，可以根据距离、交通耗时和营业时间重新排序。

排序目标：

减少折返
避开明显绕路
降低通勤时间
保留用户指定强约束，例如“晚上去海边”
3. 每段比较交通方式
每两个相邻地点之间至少比较：

步行：适合 1.5 公里以内
公交/地铁：适合城市内、预算敏感、天气正常
打车：适合赶时间、雨天、夜间、带宠物、多人同行
开车：适合自驾、跨区、郊区、多点行程
最终只输出最适合的 1 个主方案，可附 1 个备选。

4. 可视化兼容
如果高德返回真实路线 polyline，应写入每段 segments[].polyline。

如果没有 polyline：

使用起点和终点坐标作为直线降级
设置 visualization_note: "该路线图为示意图，不代表真实道路曲线"
## 规划完成后：自动调用 route_visualization

当路径规划完成并输出 `route_plan.json` 后，**必须**调用 `route_visualization` skill 生成路线图并上传飞书：

```bash
python3 ~/.openclaw/workspace/skills/route_visualization/scripts/visualize_route.py route_plan.json
```

如果返回 `image_key`，在飞书回复中发送图片消息（使用飞书 image 消息类型）。
如果上传失败或缺少凭证，回退到文字路线方案，并说明"路线图暂时没发出来，但文字路线已经整理好"。

## 降级策略
如果高德 API 不可用：

不编造实时路线、费用或换乘
可以给出粗略地点顺序
visualization_ready 设为 false
如果公交数据不可用：

使用打车/开车/步行方案兜底
标注公交换乘暂时无法确认
如果某个地点无法识别：

单独列出无法识别地点
询问用户补充城市、商圈或准确名称
# 路线可视化生成 Skill

## 适用场景

当路径规划已经完成，并且用户需要更直观地查看路线时使用本 skill。

典型请求：

- "把这个一日游路线画出来"
- "能不能生成一张路线图"
- "把每段交通方式可视化一下"
- "输出成 HTML 给我"
- "我想把路线嵌到回复里"

## 输入前提

本 skill 不负责重新规划路线，只负责展示。

输入应来自路径规划结果（`route_plan.json`），至少包含：

- 起点、终点、途经点
- 每个点的名称和坐标
- 每段路线的交通方式
- 每段路线的距离和耗时
- 如有条件，提供高德返回的 polyline 路径坐标

## 输出格式（飞书优先）

**飞书渠道默认输出 PNG 图片**，通过飞书图片 API 发送给用户。

### 完整流程

```
route_plan.json
    ↓ render_route_svg.py
route.svg
    ↓ convert_svg_to_png.py (sharp → ImageMagick 降级)
route.png
    ↓ upload_feishu_image.py (需要 FEISHU_APP_ID / APP_SECRET)
image_key → 发送飞书图片消息
```

### 一键执行

```bash
python3 scripts/visualize_route.py <route_plan_plan.json>
```

输出 JSON：

```json
{
  "ok": true,
  "steps": {
    "svg": {"ok": true, "output": "./route.svg"},
    "png": {"ok": true, "output": "./route.png", "engine": "sharp"},
    "upload": {"ok": true, "output": "{\"image_key\": \"xxx\"}"}
  },
  "image_key": "xxx",
  "png_path": "./route.png"
}
```

### 降级策略

- 如果上传失败：回退到文字路线方案，告知用户"路线图暂时没发出来，但文字路线已经整理好"
- 如果 PNG 转换失败：尝试发送 SVG（部分渠道支持），或回退文字
- 如果 SVG 生成失败：直接输出结构化行程卡片

## 可视化原则

- 路线顺序必须清晰
- 每个目的地必须标注序号
- 每段交通方式必须可区分
- 不展示 API Key、接口错误或底层调试信息
- 如果缺少真实路径 polyline，可使用点到点连线作为降级展示
- 如果坐标缺失，不生成地图，只输出结构化行程卡片

## 推荐颜色

- 步行：绿色 `#4CAF50`
- 公交/地铁：蓝色 `#2196F3`
- 打车：橙色 `#FF9800`
- 开车：红色 `#F44336`
- 未知方式：灰色 `#9E9E9E`

## 脚本清单

| 脚本 | 作用 |
|------|------|
| `scripts/render_route_svg.py <plan.json> <out.svg>` | 纯 Python 字符串生成 SVG |
| `scripts/convert_svg_to_png.py <in.svg> <out.png>` | sharp → ImageMagick 降级转换 |
| `scripts/upload_feishu_image.py <png>` | 飞书图片上传，返回 image_key |
| `scripts/visualize_route.py <plan.json>` | 一键执行上面三步 |

## 飞书图片上传配置

需要环境变量：

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`

如果未配置，`visualize_route.py` 仍会生成 PNG，但跳过上传步骤，在输出中标记 `"skipped": true`。

## 降级策略

如果无法生成 HTML 地图：

- 继续生成 SVG 简图
- 告知主 Agent："已生成简化路线图，真实道路弯折需要地图数据补全。"

如果缺少 polyline：

- 使用 POI 坐标直线连接
- 在摘要中标注："该路线图为示意图，不代表真实道路曲线。"

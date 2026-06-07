# 餐厅推荐详细流程

## 第一步：小红书搜索笔记

### 搜索策略
- 使用 `xhs search` 按 popular 和 general 各搜一轮
- 关键词格式：`{area} {keywords}`，如 "南山区 美食 探店"
- 每次搜索 limit=20

### 区域过滤
过滤出标题包含以下关键词的笔记：
- 南山、蛇口、后海、海岸城、深圳湾、南头、西丽、华侨城、科技园

### 注意
- xhs search 可能触发验证码（Captcha），需等待冷却
- 两次搜索间隔 ≥2s
- 如果 xhs 未认证，提示用户先 `xhs login`

## 第二步：读取笔记正文

### 优先级
1. 先试 `xhs read <id> --json`（CLI 方式）
2. 如果超时/失败，用 Python 库：
   ```python
   from xhs_cli.client import XhsClient
   client = XhsClient(cookies=cookies)
   result = client.get_note_by_id(note_id, xsec_token=xsec_token)
   ```

### 餐厅提取规则
从笔记正文（desc 字段）中提取餐厅名：
- 按行分割
- 过滤：空行、`#` 标签行、长度 <4 或 >40
- 去掉 emoji 和特殊符号
- 保留含中文的行
- 去重：相同餐厅合并，记录 mention_count

### 注意
- 每篇笔记读取间隔 ≥2s
- 最多读 15 篇（避免时间过长）
- 有些笔记正文为空（图片为主的笔记），跳过

## 第三步：高德 POI 查询

### API
- 文本搜索：`https://restapi.amap.com/v3/place/text`
- 参数：key, keywords, city, limit=3

### 提取字段
- `name` → 餐厅名
- `address` → 地址
- `type` → 类型
- `biz_ext.cost` → 人均
- `biz_ext.rating` → 评分
- `biz_ext.open_time` → 营业时间
- `tel` → 电话
- `location` → 经纬度

### QPS 限制
- 免费 API QPS 较低
- 每次请求间隔 ≥1.5s
- 如果返回 `CUQPS_HAS_EXCEEDED_THE_LIMIT`，等待 10s 后重试

## 第四步：推荐打分

### 评分规则
| 维度 | 条件 | 分数 |
|------|------|------|
| 价格匹配 | 人均 ≤ 预算 | +10 |
| 价格接近 | 人均 ≤ 预算×1.5 | +5 |
| 评分 | rating × 2 | 0-10 |
| 嗜辣偏好 | 火锅/川菜/湘菜/重庆/麻辣/酸汤/贵州 | +15 |
| 海鲜偏好 | 海鲜/鱼/虾/蟹/蛙 | +10 |
| 热度 | mention_count × 3（最多+15） | 0-15 |

### 用户偏好
从 USER.md 提取：
- 嗜辣 → spicy=True
- 海鲜 → seafood=True
- 预算 → budget_max=200（默认）
- 带猫 → 推荐时标注宠物友好

## 第五步：输出格式

### Agent 展示规范
1. 分类展示：🔥强烈推荐 / 👍值得一试 / ☕休闲放松
2. 每家包含：名称 + 距离 + 人均 + 评分 + 推荐菜 + 营业时间
3. 结尾追问：是否需要查排队 / 规划路线

### 禁止事项
- 不要 1:1 搬运笔记原文
- 不要推荐没有高德数据且只出现一次的餐厅
- 不要在用户未确认时执行预约/下单

## 降级策略

| 场景 | 处理 |
|------|------|
| xhs 未认证 | 提示 `xhs login` |
| 高德 QPS 超限 | 仅基于小红书数据推荐 |
| 小红书搜不到 | 扩大关键词（去掉区域限定） |
| 高德无 POI | 保留小红书信息，标注"暂无详细数据" |

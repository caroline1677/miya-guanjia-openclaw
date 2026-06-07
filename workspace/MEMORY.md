MEMORY: OpenClaw 商赛项目全局记忆
1. 项目元数据 (Project Context)
项目名称： 基于 OpenClaw 的本地生活管家 Agent（代号：Miya）

参赛目标： 重点展示大模型在复杂任务中的 Agent 编排能力、长时记忆、跨 API 融合以及后台状态监控。

核心边界： 重后端逻辑与机制，轻前端 UI 表现。绝不把时间浪费在画花哨的网页上，而是要打磨底层的数据流转和决策树。

部署环境： 习惯在 Ubuntu 服务器环境下使用 Docker 等容器化技术进行环境隔离与部署调试。

2. 核心场景编排 (Core Scenarios & Workflow)
项目目前聚焦三大核心业务链路，以展示 Agent 的"融会贯通"能力：

场景 A：跨时空状态监控（排队与交通联动）
逻辑链路： 餐厅 API 取号 -> 监控排队进度 -> 监控路况与打车 ETA。

Agent 决策点： 当 剩余桌数耗时 ≈ 打车 ETA + 路况拥堵耗费时间 时，主动触发提醒并拉起打车 Skill。

场景 B：异常状态自愈（天气与行程重定向）
逻辑链路： 监听天气 API -> 发现降雨或极端天气预警 -> 检索原定行程（如户外看展/逛街）。

Agent 决策点： 拦截原计划，平滑推荐室内备选方案（结合 User 偏好），并自动调整出行时间与打车策略。

场景 C：多轮偏好沉淀（无痕记忆）
逻辑链路： 日常交互 -> 提取结构化特征（如吃辣、带猫、极客消费观） -> 写入长时记忆 -> 影响 A、B 场景的决策权重。

3. 沙盒 API 开发规范 (Sandbox API Principles)
运行于 5001 端口的沙盒不能是返回静态 JSON 的"死接口"，必须是具备状态机 (State Machine) 属性的"活系统"，以供 Agent 展示其监控能力：

时间流逝衰减： 餐厅的 剩余等待桌数 必须随时间推移或接口调用次数自然减少。

动态变量注入： 天气和交通 ETA 必须包含随机扰动（如从"通畅"突变为"拥堵"），以测试 Agent 的应急重排能力。

幂等与有状态： 下单、取消打车等写操作必须更新内部的内存字典，确保后续查询能反映最新状态。

4. 待办与当前焦点 (Current Focus / To-Do)
(注：AI 助手需在此处动态更新当前的工作进度，以下为初始占位符)

[x] Phase 1: 完善 5001 沙盒 API 的动态逻辑框架（Node.js 实现，含餐厅/打车/天气模拟）。

[x] Phase 2: 沙盒新增 /sandbox/social/search 路由 + /api/alerts/* 路由验证通过，TOOLS.md 调用链路已打通。

[x] Phase 3: "场景 A"端到端测试通过（scripts/test_scenario_a.js），监控注册→轮询→决策联动全链路 OK。

[x] Phase 4: 跑通"场景 B"（天气异常→行程重定向）完整测试。

[ ] Phase 5: 整理演示脚本，准备答辩材料（三大场景 demo 流程 + 技术亮点总结）。

## 进展记录（2026-06-07 23:15）：
- 完成 outing-planner skill 全链路实战验证：天气→小红书→高德POI→route-planning→route-visualization→restaurant-queue
- 何晴的下周六福田一日游规划完成：莲花山→COCO Park→戏精剧本杀
- 餐厅推荐命中用户偏好：墨西哥菜（LOS PACOS 帕库）+ 羊肉串
- route-visualization 脚本路径确认：route_visualization/（下划线）
- 高德 amap_routes.py 一次只接受单个 JSON 对象，不支持数组
- 飞书图片上传缺少 FEISHU_APP_ID，但可用 filePath 参数直接发 PNG
- smart_memory.js LLM 429 频率较高，fallback 机制正常运作

6. 教训与行为红线 (Lessons Learned)

- **2026-06-07**: 何晴反馈记忆混乱，根因是 profile.json / session_cache.md 从未创建，且每次对话未按 SOUL.md 规则主动读取用户记忆。
  - 红线：每次新对话必须读 profile.json + session_cache.md，不得跳过
  - 红线：所有飞书用户（ou_ 开头）视为同一人，记忆统一存到 ou_USERID
  - 红线：发现记忆文件缺失时必须立即创建，不能"等下次再说"

5. 外部 Skill 路径 (External Skill Paths)
- **QWeather 天气 Skill（优先）**: `/home/ubuntu/.openclaw/workspace/skills/qweather/`（宿主机路径，容器内等价路径相同）
  - 直接调用和风天气 API，不走 mock-server
  - 脚本入口：`scripts/weather_qweather.js`
  - 支持命令：`now` / `forecast` / `warnings` / `all`
  - 支持深圳各区查询
  - **Miya 查天气时优先使用此 skill，失效时才降级到原有机制（mock-server / wttr.in 等）**

---
进展记录（2026-06-06）：
- 修复 sandbox_server.js 接口路径与业务脚本对齐（端口 8001→5001，新增 /restaurant/:name/queue、/taxi/estimate、/weather）
- 统一 IDENTITY.md 为 Miya 🐱（原 Grogu）
- 清理 skills/my-skill/ 空壳
- smart_memory.js 移除硬编码 LONGCAT_KEY，改为 process.env.LONGCAT_KEY
- 合并 3 组重复日志文件
- 删除功能重叠的 poll_haidilao.sh
- 修复 u001/tasks.json 格式（对象→数组）并补全 profile.json
- 整理 2026-06-06.md 日志（失败记录提取到独立文件）
- social_guide.js / poi_checker.js 引入真实搜索 API 降级机制

进展记录（2026-06-06 23:16）：
- 全局替换 mock-server:5001 → 172.17.0.1:5001（6 个文件 6 处）
- 网络连通性自检：172.17.0.1:5001 连接被拒（Connection refused），沙盒服务未运行
- social_guide.js 兜底数据升级：替换过时硬编码，新增 Señor Taco、El Torito
- poi_checker.js 兜底数据升级：随机排队→动态计算 ETA，优化标签
- social_guide.js / poi_checker.js 降级日志精简：移除 Mock 检测相关错误输出
- SOUL.md 更新：搜索行为准则强化（静默降级、禁止提及技术细节、兜底数据说明）
- 宿主机 IP：172.17.0.1（Docker 网桥）

进展记录（2026-06-07 22:50-23:05）：
- 何晴反馈餐厅排队 bug：即刻入座、看不到桌数变化
- 修复 restaurant_sim.py：`_table_snapshot()` 方法新增，`take_number()`/`queue_status()` 返回 `table_status` 字段
- 修复初始化逻辑：所有桌 `dining_remaining` 统一为 `avg_dining_min`（不再随机 half~full）
- 新增屈琦琦打车订单：深圳北→福田口岸，快车约15元，订单号 OB09OTx6dEB3La
- 何晴当前：三出山火锅 A009 已入座，打车 J802rLt9ULcujP 司机已接单
- **新教训**：修改 mock-server 代码后需清除 `__pycache__` 并重启才能生效，否则运行中的进程加载旧代码
- **新教训**：pkill mock-server 进程后容器可能自动重启，导致未保存的修改丢失——修改代码后要确认文件已写入磁盘
- **新教训**：修改 mock-server Python 代码后，必须清除 `__pycache__` 并重启进程才能加载新代码，运行中的进程会使用旧缓存

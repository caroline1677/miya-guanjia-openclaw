
## ⛔ 严重错误：不要把任何东西装在容器文件系统里

容器文件系统（/usr/local/bin、/usr/bin、apt-get 安装的包等）在每次 docker compose up --force-recreate 后全部丢失。

**所有需要持久化的文件必须装在挂载卷里：**
- 挂载卷路径：/root/.openclaw/（对应 host: /home/ubuntu/.openclaw/）
- 可执行脚本放：/root/.openclaw/bin/
- Python 包放：/root/.openclaw/skills/ 下（已在挂载卷）

**PATH 已配置包含 /root/.openclaw/bin**，脚本放这里就能直接调用。

已犯过的错误：
- xhs wrapper 装在 /usr/local/bin/xhs → 重建丢失
- Chrome apt 依赖装在容器系统 → 重建丢失
- Python _common.py 补丁在挂载卷里 → 重建保留 ✅（正确）

# ERRORS.md — 已知错误与禁止行为

**每次对话开始必须读这个文件。遇到新错误必须追加记录。**

---

## xhs / 小红书

### [2026-06-07] IP 被封禁
- **现象**：xhs read 连续调用多篇后触发验证码，之后所有请求返回 verification_required 或 IP at risk
- **根因**：腾讯云服务器 IP 是机房IP，小红书风控严格；连续 read 触发封禁
- **禁止**：触发验证码后继续重试 xhs read
- **正确做法**：
  1. 立刻停止所有 xhs read 调用
  2. xhs search 的摘要结果已够用，直接基于搜索结果给推荐，不需要读全文
  3. 告知用户"小红书读取受限，基于搜索摘要给你结果"
  4. 等待 30-60 分钟后 IP 才可能解封

### [2026-06-07] 频繁循环尝试替代方案
- **现象**：xhs 失败后，反复尝试 agent-browser → Jina → agent-reach → Exa → 再回 xhs，陷入死循环
- **禁止**：同一工具失败后尝试超过 2 个替代方案
- **正确做法**：xhs search 失败 → 试一次 agent-browser → 失败 → 用 web_search 保底 → 给结果，结束

### xhs 调用规范
- search 最多 2 次（不同关键词），read 最多 15 篇（串行，不并行）
- 超过限额立即停止，用已有数据给结论
- read 必须一篇一篇来，每篇之间限速器自动等待，不要手动堆叠
- WARNING "Cookie refresh failed" 是正常现象，忽略，看 ok: true/false

---

## agent-browser / Chrome

### [2026-06-07] 小红书 IP 风控
- **现象**：agent-browser 打开小红书显示 "IP at risk"，无法访问内容
- **根因**：同一服务器 IP，与 xhs API 被封是同一原因
- **正确做法**：IP 被封期间，agent-browser 访问小红书同样无效，不要尝试

---

## 通用规则

### 遇到新错误时
立刻在本文件追加一条记录，格式：
```
### [日期] 错误简述
- **现象**：
- **根因**：
- **禁止**：
- **正确做法**：
```

---

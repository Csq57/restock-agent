# PayPal AI Hackathon 研究（2026-11-06）

来源：<https://paypalaihackathon.devpost.com/> + `/rules` + `/resources`（2026-11-06 抓取）
外部裁决：`gpt-6.1-sol` / effort=high，产出 `C:\Users\Chan\Documents\Hermes\dual-model\runs\20261106-212113-ask-codex.json`

## 1. 一页事实

| 项 | 值 |
|---|---|
| 名称 | PayPal AI Hackathon: Build what's next with PayPal and AI（Devpost challenge 31302） |
| 提交窗口 | 2026-10-01 09:15 PT → **2026-11-12 12:00 PT = 悉尼 2026-11-13 07:00 AEDT** |
| 剩余 | 约 6 天 9 小时（从 2026-11-06 21:19 AEDT 计） |
| 评审 | 12-01 → 12-15；12-21 左右公布 |
| 规模 | Devpost 显示 29,617 名注册者（实际提交数远小于此） |
| 资格 | 全球开放；排除巴西、魁北克、俄、克里米亚、古巴、伊朗、朝鲜及美国制裁地 |
| 赛道 | **无赛道、无命题**。唯一硬要求：项目必须同时"meaningfully"用到 PayPal 与 AI |
| 总奖池 | $67,500 现金 + Render credits |

### 提交物清单（缺一项即失格）

1. 项目本体（用 PayPal developer platform **sandbox**）
2. 文字描述（功能与用法）
3. **可运行 demo**：repo 里完整 setup/run 说明 **或** hosted demo URL。静态 mockup / 设计稿 / 非功能 demo 明确不算
4. 工具说明：用了哪些模型/AI 服务、怎么用的
5. **公开开源 repo**（GitHub / GitLab / Bitbucket），含全部源码与说明，带 license 且 About 区可见
6. **<3 分钟** YouTube 公开视频，须拍到真实运行画面，不得含未授权商标/音乐
7. 材料英文（非英文需提供英文翻译）

### 评分

- **Stage 1**：pass/fail 基线——是否真用了 PayPal + AI、是否贴题。不过线直接淘汰。
- **Stage 2**：五项**等权**——Technological Implementation / Design / Potential Impact / Innovation-Idea / Presentation。
- **平票规则**：按上述顺序逐项比 → Technological Implementation 实际是最高权重项。
- 注意 Design 的定义是"完整连贯的产品体验，不是技术 PoC"；Presentation 明确要求视频端到端跑通。

### 奖金结构

| 类别 | 奖项 | 金额 |
|---|---|---|
| Grand | 1st / 2nd / 3rd | 12k / 8k / 5k |
| Honorable Mention（各 1 名） | Most Creative、Most Impactful、Best Demo Delivery、Best Use of PayPal + AI、**Best Use of Agentic Commerce** | 各 5k |
| Sponsor | AG Grid 1st/2nd/3rd | 5k / 2k / 1k×3 |
| Sponsor | APIMatic、Bryntum | 各 1k×3 |
| Sponsor | Channel3 | 1.5k |
| Sponsor | Render | 1000/750/500 credits |

**叠加规则**：一个项目最多 1 Grand + 1 Sponsor，或 1 Honorable + 1 Sponsor。→ 在主题奖之上再叠一个 sponsor 奖是纯增量，最高可到 $10k。

## 2. 技术底座（已核实）

| 组件 | 实际情况 |
|---|---|
| PayPal sandbox | `api-m.sandbox.paypal.com`，OAuth2 client_credentials 换 token，有效期 3–8h，免费 |
| Orders v2 | create → approve link → capture，纯 REST，Python `requests` 几十行可跑通 |
| 其他能力 | Invoices / Subscriptions / Payouts / Disputes / Webhooks / Catalog / Reporting 全在 sandbox 可用 |
| PayPal MCP server | `https://mcp.sandbox.paypal.com/sse`（SSE），SSE 暴露 Orders & Payments、Invoices、Subscriptions、Disputes、Catalog、Shipment、Reporting 七组工具 |
| PayPal AI Toolkit | `github.com/paypal/AI-Toolkit`（Apache-2.0），给 Claude Code / Codex / Cursor 装 skill + MCP 的插件；*自己写的应用*不需要它，但可用来加速开发时查 API |
| PayPal Agent Toolkit | `github.com/paypal/agent-toolkit`，把 PayPal API 包成 function-calling 工具（`create_order`/`pay_order`/`create_invoice`…）；README 明确写"support for TypeScript"，**Python 侧不可靠** |
| AG Grid | Community 版 MIT，免费可进公开 repo（sponsor 奖要求"use any AG Grid tools"） |

结论：**Python 项目直接打 REST + 自写 3–4 个工具函数，不要依赖 agent-toolkit 的 Python 包**。自写工具层反而在 Technological Implementation 上更好讲故事。

## 3. 外部模型裁决（sol/high，81.95s，窗口第 1/8 次）

原话要点：

- 选 **E「CSV 补货采购 Agent」**，工时盒 30 小时，主攻 **Best Use of Agentic Commerce**，兼争 **AG Grid**。
- 期望值排序：**E > B（只做开票）> C > A（双 agent 谈判）> D（订阅/现金流）**。理由：B 原版接口过多、C 同质化、A 谈判难证明价值、D 缺历史数据。
- 单商户闭环：库存 CSV + 样例目录 → AI 调选货工具、按新预算重规划 → 后端验价与限额 → 买方批准 → sandbox 扣款回写账本。
- 五项判据的对位：可审计闭环=技术分；重规划=创新分；补货减负=影响分；单屏表格=设计分；真实三幕演示=展示分。
- 必砍三件事：① 双 agent 谈判、多商户分账；② Payouts / Disputes / 订阅，只打磨 Orders 闭环；③ sponsor 工具接入限 2 小时。
- 截止换算：悉尼 11-13 07:00 前交齐。

## 4. 落地方案：Restock Agent（单商户闭环）

**一句话**：把"我该补什么货、批不批、付了没"压进一次 AI 驱动的审阅 + 一次真实 sandbox 扣款。

### 三段流程（视频就按这三幕拍）

1. **计划**：上传 `inventory.csv`（SKU、当前库存、日均销量、安全库存）+ `catalog.json`（PayPal Catalog 里的商品与价格）。Agent 调工具算缺口 → 生成采购草案（SKU、数量、单价、总额）。
2. **重规划**：用户改预算（如 $500 → $300）或剔除某 SKU，Agent 必须重新调工具、重算，产出新草案并解释取舍（砍了谁、为什么）。**这一步是"agent 真的在动"的证据**。
3. **执行**：单屏 AG Grid 审阅表（可编辑数量、实时重算）→ 批准 → 后端先验价再限额 → 调 PayPal Orders v2 `create` + `capture` → 写回 `ledger.csv` + 库存扣减。

### 必须跑出来的四个边界（也是视频里的加分镜头）

- 超预算：草案总额 > 预算 → 硬拦截，不允许 capture
- 价格漂移：catalog 价格与草案不一致 → 拒绝并触发重规划
- 重复提交：同一 `idempotency_key` 二次点击 → 不重复扣款
- 取消：批准前取消 → 无订单产生

### 技术栈（按单人 30 小时定）

| 层 | 选型 | 理由 |
|---|---|---|
| 后端 | Python + FastAPI | 熟悉，REST 直连 PayPal |
| 工具层 | 自写 4 个函数：`read_inventory`、`quote_catalog`、`draft_po`、`pay_order` | 不依赖不稳定的 Python agent 包；工具边界清晰好讲 |
| LLM | 任选（Gemini/Groq/GPT 免费档），function calling | 零预算；模型写进"Tools"清单 |
| 前端 | 单页 HTML + AG Grid Community（CDN 引入） | 2 小时上限，不搭框架 |
| 账本 | CSV/SQLite | 可审计、视频里好展示 |

### 判据对位表

| 判据 | 靠什么拿分 |
|---|---|
| Technological Implementation | 真实 Orders v2 create+capture、四条边界、幂等键、账本一致 |
| Design | 单屏"草案 → 审阅 → 支付 → 回执"一条线，不跳页 |
| Potential Impact | 小商户补货：原本手工 Excel 对账 + 手动下单，压到一次批准 |
| Innovation | 预算约束下的**重规划**（不是"AI 建议"，是 AI 重算并重提交） |
| Presentation | 三幕演示 2:40，全程真实点击与真实 sandbox 回执 |

## 5. 时间盒（悉尼日期，共 30h）

| 日期 | 工时 | 目标 | 冻结项 |
|---|---|---|---|
| 11-06 夜 | 4h | sandbox 换 token、跑通 create+capture、LLM 免费档 tool calling | 商户单一、币种单一（USD） |
| 11-07 | 6h | 接 CSV + catalog + 工具层；验证"改预算会改变采购单" | 工具签名定死 |
| 11-08 | 6h | 批准 → 扣款 → 账本回写；四条边界测试 | 支付路径不再动 |
| 11-09 | 5h | AG Grid 单屏审阅；当天冻结功能 | **功能冻结线** |
| 11-10 | 5h | 英文 README + 工具清单 + LICENSE + About 检查；干净环境复现；录 2:40 视频 | 视频素材定稿 |
| 11-11 | 4h | 上传 YouTube、提交 Devpost、逐条核验链接；余量只修阻断问题 | 提交完成（不压线） |

## 6. 风险清单

| 风险 | 处理 |
|---|---|
| AG Grid Community 是否算"AG Grid tools"（sponsor 奖资格） | 未在规则中逐字确认；按"any AG Grid tools"字面成立，但不要把它当主目标，只当增量 |
| Python agent-toolkit 不可靠 | 已核实 README 只承诺 TypeScript → 走 REST |
| 视频超 3 分钟 | 2:40 硬上限，脚本先写后录 |
| sandbox token 3–8h 过期 | 代码里做 token 刷新，演示前重新签发 |
| 规则要求"旧项目须赛期内显著更新" | 本项目从零起，无此风险 |
| 29,617 注册者 → 主题奖竞争激烈 | 靠 Stage 2 五项齐全 + sponsor 叠加，不赌 Grand |

## 7. 需要用户拍板（平台动作，不在我职权内）

1. 是否注册 Devpost 账号并 Join Hackathon（提交动作必须本人）
2. PayPal Developer 账号的 sandbox Client ID / Secret 由本人创建后放入本地 `.env`（不写进 repo、不写进记忆）
3. 是否接受"Agentic Commerce 主题 + AG Grid 增量"这条路线，还是先看别的方向对比

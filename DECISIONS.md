# DECISIONS

## 2026-11-06 · 参赛路线

- **采纳外部裁决**（gpt-6.1-sol / high，runs/20261106-212113-ask-codex.json）：方向定为 **E「CSV 补货采购 Agent」**，主攻 Best Use of Agentic Commerce，AG Grid 作增量 sponsor 奖，工时盒 30h。
- **被推翻的**：我原列的 A（双 agent 谈判）、B（自由职业回款全链路）、C（收据分账）、D（订阅现金流）。理由分别为：A 的价值难以在 3 分钟视频里自证；B 接口面过大、30h 装不下；C 同质化严重；D 需要历史数据而沙箱没有。
- **技术口径**：Python + FastAPI 直连 PayPal REST（Orders v2），工具层自写，不用 agent-toolkit 的 Python 包（README 只承诺 TypeScript，已核实）。
- **未验证假设**：AG Grid Community（MIT）是否满足 sponsor 奖"use any AG Grid tools"——按字面成立，但不作为主目标。

## 待用户拍板

1. 注册 Devpost + Join Hackathon（平台动作）
2. 创建 PayPal sandbox 应用并把 Client ID / Secret 放本地 `.env`
3. 路线确认或改向

## 2026-11-06 · 11-06 时间盒（4h）执行记录

用户已登录 Devpost（0 个项目、6 天倒计时、To-dos 三项）。已交付一个 mock 模式下全通的切片：

- `app/planner.py` 纯函数分配器：gap 公式 + 按 days-of-cover 排序 + 预算硬上限 + 部分填充（按 MOQ 向下取整）+ 丢弃原因
- `app/service.py` 四道守卫：超预算、价格漂移、幂等、非法状态迁移；`app/paypal_client.py` 真实 Orders v2 + token 刷新 + MockPayPal 兜底
- `app/agent.py` 工具调用循环（OpenAI 兼容），无 LLM key 时降级为确定性 planner，演示不会因网络挂掉
- `app/main.py` FastAPI + `static/index.html` 单屏 AG Grid（可编辑数量、实时总额、headroom）
- `tests/test_boundaries.py` 10 个用例全绿（python -m unittest，无需凭据）
- 实测：budget 1200 → 4 行 $1191.10；砍到 600 → $589.40，diff = SKU-1001 dropped / SKU-1008 28→16 / SKU-1002 2→1；qty 改成 9999 → 超预算 $91,207.45 且审批按钮禁用；approve→capture 拿到 CAP-AEF588FF6B
- 文档：英文 README（含 Tools 清单与 2:40 演示脚本）、MIT LICENSE、`.env.example`、`scripts/smoke.py`

下一步（等凭据）：`PAYPAL_CLIENT_ID/SECRET` 进 `.env` → `python -m scripts.smoke --token-check` → 真 sandbox 下单，把 mock 徽章换成 sandbox-live 并重录截图。LLM key 接入后同一循环切到真模型。

## 2026-11-06 · 真 sandbox 接通（凭据到位后）

- 安全修正：用户把凭据填进了 `.env.example`（准备进公开 repo 的模板）。已复制到 `.env`、把模板还原成空值。当前无 git repo，未外泄。
- `--token-check` 通过（真 sandbox OAuth2）。
- 首次真扣款被拒：`422 ORDER_NOT_APPROVED` —— Orders v2 要求付款方先批准。这是规则，不是 bug。
- 决策：加 `PAYPAL_PAYMENT_MODE`，两条路都实现。
  - `card`（默认）：create 时带 `payment_source.card`（sandbox 测试卡），PayPal 在 create 内直接结算，返回 `COMPLETED` + capture id；不要再调 capture，否则 `ORDER_ALREADY_CAPTURED`。
  - `approval`：不带 payment_source，返回 `checkoutnow?token=…` 批准链接，人批完再 `POST /api/capture`。
- 实测：UI 点 Approve 一次即完成真实 sandbox 扣款 —— order `6X147398UT547322A` / capture `1546868974354614C` / USD 1191.10 / `2026-11-06T10:43:17Z`；用 `GET /v2/checkout/orders/{id}` 回查为 `COMPLETED`。截图 `docs/screenshot-live.png`。
- 测试从 10 条扩到 12 条（拆出 card 一次性结算与 approval 两步流），全绿。

## 2026-11-06 · LLM 接入 + 一个必须堵的洞

- Gemini 2.5 Flash（OpenAI 兼容端点）接通，`/api/health` 返回 `llm_mode: llm`。
- **发现真缺陷**：首次真跑模型时，`draft_purchase_order` 的 `budget_usd` 是模型自由参数，模型自己填了 1,000,000，直接生成 $5,684.50 的订单 —— 预算从模型侧泄漏了。
- 修法（三重）：
  1. 从工具 schema 里删掉 `budget_usd`；预算只存在于服务端 session ctx。
  2. 若模型仍然传 `budget_usd`，记 `agent.budget_override_refused` 并忽略。
  3. `assert draft["budget"] == ctx["budget"]` 兜底。
- 同时把 `pay_purchase_order` 从模型可见的 schema 里撤掉，dispatcher 直接 `PermissionError`：agent 只能提方案，不能付钱。
- 降级诚实化：provider 不通时 `engine` 返回 `llm-fallback`（trace 首项 `fallback`），不再假装是模型的输出；实测坏 key → `llm-fallback` 且预算 300/295.75 正确。
- 测试 12 → 14 条（新增"模型不能自己定预算""支付工具不对模型开放"）。
- 第三次真扣款验证：order `8TW31644XB361373W` / capture `0MW30422WD799732V` / USD 589.40。

## 2026-11-06 · 事故与修复记录（编码）

- PowerShell 5.1 的 `Set-Content` 默认编码把 `static/index.html` 的 UTF-8 字符写坏（em-dash 变 U+FFFD），文件流变成非法 UTF-8。
- 相对路径混用（`cd` 对 PowerShell cmdlet 生效，但对 `[System.IO.File]` 用的是进程 CWD）导致一度在项目根写出 0 字节 `index.html`。
- 处理：删除坏文件、用 written-as-UTF8 的新文件替换、`node --check` 校验内嵌 JS（抓到一处多余的 `)` 造成整页白屏），现在零 console 错误。
- 教训：改前端文件只用 write/edit 工具，不用 shell 重定向。





## 2026-11-08 21:05 两项目复查后的修复（按外部模型裁决执行）
### A · restock-agent（PayPal，11/12 截止）
- 公开仓库脱敏：`RESEARCH.md` 移出公开跟踪并加 .gitignore；`DECISIONS.md` 从"参赛流水账"重写为工程决策记录
  （删掉外部模型裁决、奖项布局、工时盒、本地绝对路径；保留 8 个技术决策的 why）
- 修签名洞：`approval_token` 原来只绑 `id:total:line_count`，同一草稿内换 SKU 但单价相同时总额与行数不变 → 旧签名仍有效。
  改为绑定行内容摘要（sku+qty+unit_price 排序后 hash），补测试证明"总额和行数一致时签名必须变化"
- 修刷新丢草稿：UI 从不调用 `/api/state`，`/api/state` 也不返回 token → 评委刷新后草稿消失。
  改为 state 返回 `_reviewable`，UI 启动时 `restoreLastDraft()`
- 测试 26 → **29 条全绿**；干净 venv（仅 requirements.txt）+ 无 .env 下实测：health/index/plan/state/approve/capture 全通
- 教训：我先用 pytest 去跑，误判"缺 pytest 依赖"；实际测试是 `import unittest`，README 写法正确

### B · approval-drift（Codegeist，12/22 截止）
- 修"当前值不持久化"：宏原来只存批准快照，刷新后回落到默认 1250 → 与快照 1600/1850 不符，显示 stale，看着像 bug。
  现改为同一页面属性同时存 `currentRequest`，输入防抖 900ms 写回，`getState` 一并返回
- 实测（CDP）：首次加载 1250 → 输入 1850 → 刷新后仍为 1850 且状态 "Approval still matches"
- 部署 v6.2.0，仍符合 Runs on Atlassian

### 未做（外部模型给了封顶工时）
- Rovo action 运行时实测（2h）：仍只验证到"出现在选择器"
- 第二站点安装验收（1h）：只有一个账号，无法真正验证
- 视频不重录（外部模型明确"不重做配音、UI"）
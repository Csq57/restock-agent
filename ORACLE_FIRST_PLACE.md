# 决策请求：从「拿一个单项奖」改成「争 1st Place」

## 用户目标变更
原目标：拿一个主题奖或 sponsor 奖（期望 $300–800）。**现目标：1st Place（$12,000，唯一名额）**。请按这个目标重新裁决，不要给"稳妥拿奖"的方案。

## 比赛硬事实
- PayPal AI Hackathon，Deadline 悉尼 2026-11-13 07:00，现在 11-06 22:30，约 **6 天 8.5 小时**，可用工时预估 **20–25h**（单人，学生，期间还有课）。
- 注册 29,617 人，估计实际提交 1,000–3,000。
- Stage 1 pass/fail；Stage 2 五项**等权**：Technological Implementation / Design / Potential Impact / Innovation / Presentation。平票按此顺序。
- 提交物：英文文字描述、可运行 demo（repo 说明 **或** hosted URL；静态 mockup 不算）、工具清单、公开 repo + LICENSE 在 About 区、**<3 分钟 YouTube 视频**。
- 规则原文："Judges are not required to test the Project and may choose to judge based solely on the text description, images, and video."（这条很关键：不看代码也能评。）
- 一位项目最多 1 Grand + 1 Sponsor，或 1 Honorable + 1 Sponsor。

## 现状（已上线，可点）
repo：github.com/Csq57/restock-agent（public，MIT）。本地跑在 127.0.0.1:8756，**没有公网 URL**。
- Python/FastAPI + SQLite + 单屏 AG Grid（Community 版）。
- 真 sandbox 扣款成功 4 次（Orders v2，`payment_source.card` 一步结算），最近 capture `0MW30422WD799732V` / $589.40，已用 GET 回查确认 COMPLETED。
- Gemini 2.5 Flash 做 function calling，3 个工具：read_inventory / quote_catalog / draft_purchase_order。预算来自服务端 ctx，模型改不了；支付工具不对模型开放。
- 批准需 HMAC token（绑定 draft_id+total+行数），编辑数量即失效；并发批准有原子抢占；capture 前先回查 PayPal 做崩溃对账。19 条测试全绿。
- `next_unlock`：报价"再加多少钱能多买一个 MOQ"，每个数字都用重算验证过。
- 界面：预算输入 → 规划 → 表格（可改数量）→ 批准 → 真扣款 → 审计流水。截图见 repo docs/。

## 我的自我评估（请质疑）
- Technological Implementation：强（真钱、真边界、真对账）。
- Innovation：中（"AI 补货"容易被说成 Excel 能做的事）。
- Design：弱（像内部工具，不像产品）。
- Potential Impact：中（小商户补货是真问题，但没有用户证据）。
- Presentation：**未做**，是最大空白，也是 20%。

## 请回答（第一行先给结论；≤700 字；动词开头；不要"建议加强文档"这类空话）
1. **要拿 1st，最该补的是哪一项？** 按"补 1 小时能提升多少夺冠概率"排序，给出前 3 个动作，并明确指出**必须放弃**什么（我只有 20–25h，必须砍东西）。
2. **hosted demo 到底做不做？** 考虑规则写明评委不强制运行代码。若做，用 Render 免费层（Python 服务 + 无状态，sandbox 凭据放环境变量，陌生人可点批准真的花 sandbox 钱）——这是加分还是风险？给一个具体判断和替代方案。
3. **2:40 视频怎么排才能赢 1st**：给带时间码的镜头表，说明哪个镜头是"决定名次的那 10 秒"，以及必须拍到但容易被忽略的东西。
4. **有没有一件事，做了就能让评委在 30 秒内认定"这不是常见参赛作品"**？如果有，给出来。

约束：单人、零预算、只用 sandbox、不接真实资金、不能再加架构大改（只剩 20–25h）。

# 裁决请求：这版视频能不能上传（目标 1st Place）

## 目标与约束（不变）
PayPal AI Hackathon，Deadline 悉尼 11-13 07:00，现在 11-07 14:13，**剩 5 天 17 小时**，可用工时约 14–18h。目标仍是 **1st Place**。规则：Presentation 占五项等权之一，评委不强制运行代码，可只看视频。

## 成片事实（已存在 demo.mp4）
- 68.7 秒，1280×980，H.264 + AAC，英文 AI 旁白（en-US-AndrewNeural），标题卡署名 "AI narration - script, build and voice direction by Songquan Chen"。
- 结构（时间 / 画面）：
  - 0:00–0:03 标题卡
  - 0:03–0:11 输入 budget 600 / autopay 700，鼠标移到 Run（旁白：咖啡馆每周补货、错了就断货或压死现金；我只设两个数）
  - 0:17–0:27 **点一次 Run 后结算完成**：底部状态 `PAID AUTOMATICALLY inside your $700.00 limit · order 9TP67806FD5166310 · capture 7N036830614519005 · $589.40`；审计栏 `policy.auto_approve`、`order.captured`、`agent.llm_provider_switch secondary openai/gpt-oss-120b`；三行订单（Caramel 30 / Cold Brew 16 / Oat Milk 1）；KPI 三个（3 SKUs / $589.40 of $600 / $451.15 not covered）
  - 0:27–0:37 点绿色条上的 `Try budget $669.60` → 冷萃 16 变 20，总额 589.40 → 659.00
  - 0:37–0:46 autopay 改成 100 → 琥珀色 `STOPPED: $659.00 is above your $100.00 limit`；审计栏 `guard.policy_refused {"total":659.0,"limit":100.0}`、`agent.llm_retry primary {"status":429}`、`provider_switch secondary`
  - 0:46–0:53 审计栏连续：policy_refused / llm_retry 429 / provider_switch
  - 0:53–1:01 点 `Verify with PayPal` → 状态 `PayPal says: COMPLETED - capture 72E45874N5161023N (matches what this app recorded)`
  - 1:01–1:09 结尾卡：`github.com/Csq57/restock-agent` + "23 boundary tests - real sandbox captures - MIT"
- 两次真实模型等待（各 40 秒左右）已全部跳切，片中没有空转。
- 旁白原文（8 段，共 62.3 秒）覆盖：为什么要做 / 只设两个数 / 一次点击就付款且无人批准 / 加 69.60 多买四箱且是重算验证的 / 越界被服务端拒绝 / 日志里有授权、拒绝、限流切换 / 用 PayPal 回查证明 / 总结。

## 我自己看到的三处弱点
1. **画面上没有出现 "sandbox" 字样**（只有顶栏小徽章 `paypal: sandbox-live`）。评委可能以为动了真钱，也可能反过来以为假的。旁白也没说 sandbox。
2. **第二幕数字与前一幕不连续**：第一幕 $589.40，第三幕变成 $659.00（因为中间点了加预算按钮）。观众可能困惑。
3. **全片 68.7 秒，信息密度高、语速快**；没有一处停顿让评委看清 capture id。

## 请裁决（第一行给结论；≤500 字；只给可执行动作）
1. **现在上传，还是先修？** 若先修，只给最多 3 个改动，每个必须是我在 45 分钟内能做完的（重剪、加字幕层、改旁白重生成音轨都算可行；重录需 30 分钟）。
2. 上面三处弱点哪些是真问题、哪些是我想多了？如果还有我没看到的致命问题，点名。
3. 若加字幕/标注，**具体加哪几句、加在哪一秒**，以及会不会破坏"真实运行"的可信度。
4. 上传后到 11-13 之间，剩下的 14–18 小时该优先投在哪里才对 1st 有帮助（不要建议重做架构或加功能）。

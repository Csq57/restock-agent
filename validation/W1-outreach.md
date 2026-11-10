# W1 用户验证 · 执行包

目标：**5 个真实用户**在两周内试一次，其中 **≥2 人主动再用**。

## 一、找谁（按命中率排序）

1. **已经在付钱给你的人**——Airtasker/自由职业客户里管库存的，命中率最高，因为你已经有信任
2. **悉尼本地小商家**：餐饮（咖啡馆、小餐馆）、零售（烟酒店、杂货）、批发、工作室（打印、花店）
3. **给人做代账/代运营的自由职业者**——他们手上有很多小商家，一个人能带来多个真实场景
4. 学校的创业社团、UNSW 的商科同学家里做生意的

不要找：技术朋友（会给技术意见，不会给业务意见）、大公司员工（用 ERP，不需要这个）。

## 二、怎么开口（英文，可直接复制）

**短版（WhatsApp/微信）**

> Hey — I built a small tool for a hackathon and I'm trying to find out if it's actually useful
> or just clever. It reads a stock spreadsheet, drafts a purchase order inside a budget you set
> once, and pays the supplier through PayPal without you clicking anything — anything over your
> limit stops and asks a human.
>
> Would you spend 10 minutes on it with your own numbers and tell me where it breaks? Nothing is
> charged, it runs offline on your machine. No pitch, I genuinely just want to know if it's wrong.

**如果他不想装东西**

> No problem — send me a stock list (SKU, name, on hand, daily sales, lead time, MOQ, unit cost)
> and I'll run it and send you back the draft it produces.

## 三、跑完问什么（问「上次怎么做的」，不问「你觉得好不好」）

1. 上次补货你是怎么决定买多少的？用了多久？
2. 那次的单子后来改过吗？改了什么、谁发现的？
3. 如果有个东西替你起草，你最怕它做错什么？
4. 你愿意给它多大的自动付款上限？
5. 哪一步让你不想再打开第二次？

## 四、进度表（填满它，别凭感觉）

| # | 谁（关系） | 场景 | 给了反馈? | 说了什么最关键的一句 | 两周内主动再用? |
|---|---|---|---|---|---|
| 1 | Amanda B.（Airtasker 付费客户，Zetland 上门 Excel 修复 ，2026-07-21 完成） | 日常用 Excel，是否有库存/采购未知 | 已问（2026-11-10 16:20 站内消息） | 等回复 | 待观察 |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |

## 五、判定与下一步

- **≥2 人主动复用** → 继续做，进入 W2–3：只修被反复卡住的那一条流程，不加功能
- **<2 人复用** → 停止产品化，把成果整理成可演示案例（求职/接单用），不要加功能试图挽救
- 中途不要因为「新比赛出现」切换目标（这是外部模型给的硬约束）

## 六、已经准备好的东西

- `validation/run-demo.bat` —— 双击即可运行，强制离线（`RESTOCK_OFFLINE=1`），不会扣钱、不会花模型额度
- `validation/README-for-tester.md` —— 给用户看的两页说明，含四条自己动手试的顺序
- 应用本身：29→30 条测试全绿，无凭据也能跑

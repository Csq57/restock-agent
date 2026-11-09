# Try it in two minutes

This is a local demo of a small tool that does your replenishment ordering for you.
Nothing is charged, nothing leaves your computer: it runs on a sample stock sheet with a
stand-in for PayPal.

## Run it

1. Double-click **`run-demo.bat`**.
2. The first run sets up a private Python environment (about a minute). Leave the window open.
3. Your browser opens at `http://127.0.0.1:8756/`.
4. When you are done, close that black window.

If Windows asks whether to allow Python through the firewall, you can say no — it only listens on
your own machine.

## What to try, in this order

1. Leave the budget at the default and press **Plan**. Look at the draft: what it chose to buy, what
   it dropped, and why.
2. Change the budget down to something small and press **Plan** again. Watch what it refuses to buy
   and what it says the next affordable step is.
3. Press **Approve & create PayPal order**. It will say *paid inside your limit* — that is the mock,
   not real money.
4. Try typing a silly quantity (like 9999) into a line and pressing Plan. It should refuse to exceed
   the budget rather than quietly going over.

## What I actually want from you

Not "is it nice". I want to know where it breaks on **your** numbers:

- Does it plan what you would have planned? If not, what did it get wrong?
- What would you never let it decide on its own?
- What budget would you be comfortable setting for automatic payment?
- What would make you not open it a second time?

Tell me in whatever form you like — a voice note is fine.

## If you would rather send me your own sheet

Send a stock CSV with the same columns as `data/inventory.csv`
(`sku, name, on_hand, daily_sales, lead_time_days, moq, unit_cost`). I will run it on your real
numbers and send back the draft it produces, without you installing anything.

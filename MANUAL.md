# Ghost Trader Manual

**Cash-secured puts, covered calls and TQQQ, explained from scratch, plus how Ghost Trader models all of it.**

> **This is an education tool, not financial advice.** Ghost Trader trades paper money only. Nothing here tells you what to buy, sell, or when. Real options trading carries real risk, including losing much of the money you put up. Before trading real options, read the official options risk booklet, *Characteristics and Risks of Standardized Options* (link in [Further reading](#further-reading)).

## Contents

1. [How to use this manual](#how-to-use-this-manual)
2. [Options in plain English](#options-in-plain-english)
3. [Cash-secured puts](#cash-secured-puts)
4. [Covered calls and the wheel](#covered-calls-and-the-wheel)
5. [TQQQ and its risks](#tqqq-and-its-risks)
6. [Indicators](#indicators)
7. [Using Ghost Trader](#using-ghost-trader)
8. [Your first trade, step by step](#your-first-trade-step-by-step)
9. [Glossary](#glossary)
10. [Further reading](#further-reading)

---

## How to use this manual

If you've never traded options, read the first four parts in order. Each one builds on the one before. If you already know options, skip to [TQQQ and its risks](#tqqq-and-its-risks) and [Using Ghost Trader](#using-ghost-trader).

Ghost Trader only allows two kinds of trades that open a position: **selling puts that are fully backed by cash** and **selling calls against shares you own**. These two strategies cap how much you can lose to what you've already set aside, which is why they're the whole focus here. Ghost Trader never lets you sell a call without the shares or a put without the cash.

The numbers in the examples are made up to keep the arithmetic easy. They're not real quotes and not suggestions.

---

## Options in plain English

### Shares versus options

A **share** of TQQQ is a piece of the fund. You buy it, you own it, and its value moves with the price.

An **option** is a contract about shares. It gives one side a *right* and puts the other side under an *obligation*, until a set date. You can buy that right (and pay for it) or sell it (and get paid for it).

One option contract covers **100 shares**. When a price is quoted as $1.80, the contract actually costs or pays **$180** (1.80 × 100).

### Calls and puts

- A **call** gives its buyer the right to **buy** 100 shares at a set price.
- A **put** gives its buyer the right to **sell** 100 shares at a set price.

The person who **sells** the option takes the other side:

- The seller of a call may have to **sell** 100 shares at the set price.
- The seller of a put may have to **buy** 100 shares at the set price.

In Ghost Trader you're the seller.

### The pieces of a contract

| Term | Meaning | Example |
|---|---|---|
| Underlying | The thing the option is about | TQQQ |
| Strike | The set price for buying or selling | $55 |
| Expiration | The last day the contract exists | Fri Dec 18 |
| Premium | The price of the option, paid by the buyer to the seller | $1.80 per share = $180 per contract |
| Type | Call or put | Put |

Ghost Trader writes a contract like this: **TQQQ Fri Dec 18 $55 Put**.

### Who wins when

The buyer pays the premium up front for the chance of a big move. The seller collects the premium up front and takes on the obligation. If the obligation never kicks in, the seller keeps the whole premium. If it does, the seller has to follow through, at a price that's now worse than the market's.

Selling options is a trade of a known, limited income (the premium) for taking on a defined risk.

### In, at, and out of the money

Whether an option is worth exercising depends on where the stock is compared with the strike:

| | Put | Call |
|---|---|---|
| **In the money (ITM)** | Stock is **below** the strike | Stock is **above** the strike |
| **At the money (ATM)** | Stock is about at the strike | Stock is about at the strike |
| **Out of the money (OTM)** | Stock is **above** the strike | Stock is **below** the strike |

An option that's out of the money at expiration is worthless. Nobody would use the right to sell at $55 when the market pays $60. An option that's in the money at expiration gets used.

### Exercise and assignment

When the buyer uses their right, that's **exercise**. The seller on the other end gets **assigned**, meaning they have to complete the trade.

- If you sold a put and you're assigned, you **buy 100 shares per contract at the strike**.
- If you sold a call and you're assigned, you **sell 100 shares per contract at the strike**. People say the shares were **called away**.

At expiration, options that are in the money by $0.01 or more are exercised automatically.

US stock and ETF options are **American-style**. That means the buyer can exercise **any day** before expiration, not just at the end. This early assignment is uncommon for options with time left, but it does happen. It's most likely for in-the-money calls just before an **ex-dividend date**, when the call's owner may want the shares in time to collect the dividend.

### What makes up an option's price

An option's premium has two parts:

- **Intrinsic value** is the amount it's in the money. A $55 put with the stock at $52 has $3.00 of intrinsic value. An out-of-the-money option has none.
- **Time value** is everything else. It's what buyers pay for the chance the stock moves before expiration.

Two things drive time value:

- **Time left.** More time means more chances for a big move, so a higher price. Time value shrinks as expiration approaches, and it shrinks fastest in the last few weeks. This shrinking is called **time decay**. Time decay works for the seller: if nothing else changes, the option you sold gets cheaper to buy back every day.
- **Volatility.** The more the market expects the stock to swing, the more options cost. The market's expectation, worked backwards from option prices, is called **implied volatility (IV)**. High IV means bigger premiums for sellers. It also means the market is pricing in bigger moves, which is exactly the risk the seller is taking on.

### Bid, ask and mid

Every option has two prices at any moment:

- The **bid** is the most anyone is offering to pay. When you sell, you'd get roughly the bid.
- The **ask** is the least anyone is willing to sell for. When you buy, you'd pay roughly the ask.
- The **mid** is halfway between them.

The gap between bid and ask is the **spread**. Real orders often fill somewhere inside the spread, which is why Ghost Trader lets you pick any price from the bid to the ask and suggests the mid when you sell.

### Delta

**Delta** measures how much the option's price moves when the stock moves $1. A put with a delta of −0.25 gains about $0.25 in price when the stock drops $1.

Traders also read delta as a rough guess at the chance the option finishes in the money. A −0.25 delta put is roughly a 1-in-4 chance. It's an approximation from a pricing model, not a promise. Ghost Trader shows delta in the Chain and the ticket.

### Opening and closing

You don't have to hold an option until it expires. There are four kinds of option orders:

| Order | What it does |
|---|---|
| Sell to open | Start a short position. You collect premium and take on the obligation. |
| Buy to close | End a short position by buying the same contract back. Your obligation ends. |
| Buy to open | Start a long position. You pay premium and get the right. |
| Sell to close | End a long position by selling it. |

When you sell an option and later buy it back for less, you keep the difference. If you buy it back for more, you lose the difference.

---

## Cash-secured puts

### What it is

A **cash-secured put** (CSP) means selling a put while keeping enough cash set aside to buy the shares if you're assigned. The amount set aside is the **collateral**:

> **Collateral = strike × 100 × number of contracts**

For one $55 put, that's $5,500. The cash stays yours and stays in the account, but you can't spend it while the put is open.

In exchange, you collect the premium right away.

### A worked example

TQQQ is at **$60**. You sell one **$55 put** expiring in **30 days**. The quote is bid $1.70, ask $1.90, so the mid is **$1.80**.

- You collect **$180** in premium now.
- **$5,500** of your cash becomes collateral.
- While it's set aside, that cash can keep earning interest. At a 4% yearly rate, 30 days on $5,500 is about **$18**.
- Your **breakeven** is the strike minus the premium: $55 − $1.80 = **$53.20**. Above that price at expiration, the trade made money overall.

Return on the cash you put at risk, if the put expires worthless:

> ($180 premium + $18 interest) ÷ $5,500 collateral = **3.6%** in 30 days

Annualized, that's 3.6% × 365 ÷ 30 ≈ **44%**. Annualizing makes trades of different lengths easier to compare. It isn't a prediction. You'd only get that yearly return by repeating the same result every month for a year.

### The three ways it can end

| TQQQ at expiration | What happens | Result |
|---|---|---|
| **$62** (above the strike) | The put expires worthless. Collateral is released. | Keep $180 (+ interest). |
| **$54** (below the strike, above breakeven) | You're assigned. You buy 100 shares at $55 using the $5,500 collateral. The shares are worth $5,400. | −$100 on the shares + $180 premium = **+$80** |
| **$40** (far below) | You're assigned at $55. The shares are worth $4,000. | −$1,500 on the shares + $180 premium = **−$1,320** |

The best case is capped at the premium plus interest. The worst case is that TQQQ goes to zero and you've paid $5,500 for nothing, minus the $180 you collected. The loss is bounded by the collateral. That's what "cash-secured" buys you.

After assignment you **own the shares**. You haven't sold them, so the loss in the table is on paper until you do. What you do next is covered in [Covered calls and the wheel](#covered-calls-and-the-wheel).

### Choosing a strike

Strikes farther below the stock price:

- pay **less** premium,
- have a **lower** delta, so less chance of assignment,
- leave more room for the stock to fall before you're in the money,
- and if you are assigned, you buy at a lower price.

Strikes closer to (or above) the stock price pay more, are more likely to be assigned, and give you less room. There's no free lunch: the extra premium is the market's price for the extra risk.

### Choosing an expiration

Shorter expirations (days to a couple of weeks):

- pay less in total, but more **per day**, because time decay is fastest near the end,
- leave less time for the stock to wander far,
- mean more trades and more decisions.

Longer expirations pay more in total but less per day, and lock up your collateral longer. A big move has more time to happen.

### Managing a put before it expires

You have three choices while a put is open:

- **Hold** it to expiration and let it expire or be assigned.
- **Buy to close.** If the put has gotten cheaper (the stock rose or time passed), buying it back locks in part of the premium and frees the collateral. If the stock fell, buying back costs more than you collected, and you take a loss to end the risk.
- **Roll.** Buy the current put back and sell a new one with a later expiration (and maybe a different strike), usually as two trades. In Ghost Trader a roll is simply a buy to close followed by a new sell to open.

### What can go wrong

- **A big drop.** You still have to buy at the strike, however low the price goes. The premium only cushions the first few dollars.
- **Opportunity cost.** If the stock rockets up, you keep only the premium. Someone who simply bought the shares would have made far more.
- **Cash tied up.** The collateral can't be used for anything else until the put is closed or expires.

---

## Covered calls and the wheel

### What a covered call is

A **covered call** means selling a call while owning 100 shares per contract. The shares are the "cover": if you're assigned, you already have the shares to hand over.

You collect premium now. In exchange, you agree to sell your shares at the strike if the stock is above it at expiration.

### A worked example

You own 100 TQQQ shares bought at **$55**. TQQQ is now **$54**. You sell one **$57 call** expiring in **14 days** for **$0.90** and collect **$90**. Your 100 shares are now locked as cover until the call is closed or expires.

| TQQQ at expiration | What happens | Result |
|---|---|---|
| **$52** (below the strike) | The call expires worthless. Your shares are unlocked. | Keep $90. You still own the shares, now worth less. |
| **$56** (below the strike) | Expires worthless. | Keep $90 and the shares. |
| **$65** (above the strike) | Called away: your 100 shares are sold at $57. | +$200 on the shares ($57 − $55) + $90 = **+$290**. Everything above $57 goes to the buyer. |

### The tradeoffs

- **Capped upside.** Above the strike, gains go to the call buyer. In a fast rally, the shares get called away and you miss the rest of the move.
- **No downside protection beyond the premium.** If the stock falls, you still own the shares. The premium only offsets a little of the drop.
- **Strike versus your cost.** Selling a call with a strike *below* what you paid for the shares means a called-away sale locks in a loss on the shares. Ghost Trader allows it, and the details panel shows exactly what assignment would mean.
- **Early assignment before dividends.** An in-the-money call can be exercised early, especially the day before an ex-dividend date. Ghost Trader warns you about this (see [Alerts](#alerts)).

### The wheel

The **wheel** chains the two strategies into a cycle:

1. **Sell a cash-secured put.** Collect premium.
2. If it **expires worthless**, go back to step 1.
3. If you're **assigned**, you now own 100 shares per contract.
4. **Sell a covered call** on those shares. Collect premium.
5. If it **expires worthless**, go back to step 4.
6. If the shares are **called away**, you're back to cash. Go back to step 1.

Every step collects premium. The risk sits in step 3: you can be assigned on a stock that keeps falling, and then hold shares worth much less than you paid while you wait to sell calls that make sense against your cost. The wheel turns smoothly in a calm or rising market and gets stuck in a falling one.

---

## TQQQ and its risks

### What TQQQ is

**TQQQ** is the ProShares UltraPro QQQ ETF. It aims for **three times the daily return** of the Nasdaq-100, an index of the 100 largest non-financial companies on the Nasdaq. If the Nasdaq-100 rises 1% today, TQQQ aims to rise about 3%. If it falls 2%, TQQQ aims to fall about 6%.

It gets that leverage mostly through **swaps and futures**, not just by owning the stocks. It has traded since February 2010 and pays a small dividend quarterly. Its yearly fee (expense ratio) has been around 0.8–1%, much higher than a plain index fund. Check ProShares' page for the current figure.

### The daily reset

The "3×" applies to **each single day**, not to longer periods. The fund rebalances every day to get back to 3× exposure. Over weeks and months, its return can be very different from 3× the index's return.

Here's what happens when the index goes up 10% one day and down 10% the next:

| | Start | After +10% day | After −10% day | Total |
|---|---|---|---|---|
| Index | $100 | $110 | $99 | **−1%** |
| 3× daily fund | $100 | $130 | $91 | **−9%** |

The index lost 1%. The 3× fund lost 9%, not 3%. This is called **volatility decay**: in a choppy market that goes nowhere, a daily-leveraged fund tends to drift downward. In a steady trend the compounding can work in the fund's favor instead. Either way, holding it for more than a day is not the same as owning 3× the index.

### Drawdowns

Leverage makes the falls enormous. During 2022, the Nasdaq-100 fell about a third over the calendar year, and TQQQ fell roughly 80%. From its November 2021 peak to its December 2022 low, TQQQ lost about 82%. After an 80% loss, a fund needs to rise about 400% just to get back to where it started.

### Overnight gaps

The fund rebalances once a day, but the market can move a lot between one close and the next open. In March 2020 the Nasdaq-100 fell more than 12% in a single day. At 3×, the daily target for that day was a loss of more than a third. No stop or alert in the world helps you inside a single gap.

### What this means for selling options on TQQQ

- **Premiums are large because the risk is large.** TQQQ's implied volatility is usually several times that of a typical large stock. The big yields in the ticket are payment for that.
- **Assignment can come at the worst time.** Put sellers get assigned when TQQQ has fallen, which is often in the middle of a bigger slide. Then you hold a 3× fund in a falling market.
- **Position size matters more than usual.** A single put can tie up most of a small account. Ghost Trader warns when one trade's collateral is above 80% of your account value.
- **Decay hurts long holding.** If you're assigned and wait for TQQQ to recover above your cost, volatility decay works against you while you wait.
- **Dividends are small but real.** They can make early assignment of in-the-money calls more likely right before the ex-dividend date.

---

## Indicators

Ghost Trader's **Indicators** tab shows three common ways traders read the market: the stochastic oscillator on TQQQ, the VIX, and CNN's Fear & Greed index. This part explains what each one measures. None of them predicts prices. They describe where things stand right now compared with the recent past.

### The stochastic oscillator

The stochastic oscillator asks one question: **where did the latest close land within the recent high-to-low range?** It's a number from 0 to 100:

> **%K = 100 × (latest close − lowest low) ÷ (highest high − lowest low)**, over the last *n* trading days

- **100** means TQQQ closed at the very top of its range for that period.
- **0** means it closed at the very bottom.
- **50** means it closed in the middle.

Readings of **80 and above** are traditionally called *overbought*, and **20 and below** *oversold*. Those labels only describe where the price sits in its range. A strong trend can stay overbought or oversold for a long time.

The **lookback** (*n*) sets how much history the range covers. Ghost Trader shows four:

| Setting | What it covers | How it behaves |
|---|---|---|
| 14,3,3 | The last 14 trading days (about 3 weeks) | Moves quickly with short swings |
| 30-day | About 6 weeks | Slower |
| 60-day | About 3 months | Slower still |
| 180-day | About 9 months | Shows where TQQQ sits in its longer-range trend |

The **14,3,3** setting is the classic "slow stochastic." The two 3s add smoothing:

- **%K** is the raw 14-day reading averaged over 3 days, which takes out some day-to-day noise.
- **%D** is a 3-day average of that %K. It lags behind %K, and traders watch where the two lines cross.

The 30, 60 and 180-day settings show the raw %K line only, with no smoothing and no %D.

### The VIX

The **VIX** is the CBOE Volatility Index. It's calculated from S&P 500 option prices and shows how much movement the options market expects over the next 30 days, as a yearly percentage. A VIX of 20 means the market is pricing in moves of roughly 20% a year for the S&P 500.

- **Low VIX** (low teens): the market expects calm.
- **High VIX** (30 and above): the market expects big swings. That usually happens during sell-offs.

The VIX is about the S&P 500, not TQQQ. TQQQ's own option prices usually imply volatility several times higher. The two tend to rise together, though, and when the VIX jumps, TQQQ option premiums generally jump too.

### CNN Fear & Greed

CNN's **Fear & Greed index** combines seven market measures (including stock momentum, the VIX, demand for junk bonds versus safe assets, and put versus call buying) into one score from 0 to 100:

| Score | CNN's label |
|---|---|
| 0–24 | Extreme fear |
| 25–44 | Fear |
| 45–55 | Neutral |
| 56–75 | Greed |
| 76–100 | Extreme greed |

CNN doesn't publish an official data feed. Ghost Trader reads the same data CNN's own web page loads. If CNN changes its site, this can stop working without warning. The tab then says Fear & Greed is unavailable and keeps showing everything else.

### Readings saved with your trades

Every time you place a trade, Ghost Trader saves the current readings with it: all four stochastic values, the VIX, and Fear & Greed. You'll see them:

- under the trade in **History**,
- in the **Market at each trade** table in a position's details,
- and as extra columns in the History and run **CSV** exports.

Double-click a trade's readings in either place to open the Indicators tab on that date, with the day pinned. This lets you look back later at what the market looked like when you made each decision. If the data can't be fetched at that moment, the trade still goes through, just without readings.

---

## Using Ghost Trader

### What Ghost Trader is, and isn't

Ghost Trader is a paper-trading ledger for TQQQ options. It uses real quotes, applies strict rules, and keeps a permanent record of every trade.

It is:

- **Paper money only.** Nothing is ever sent to a broker.
- **Real quotes, delayed.** Option chains and the TQQQ price come from Yahoo Finance and are about 15 minutes behind during market hours.
- **TQQQ only.**
- **Strict.** Every trade is checked against the rules before you can confirm it, and there's no undo.

It is not a perfect simulator. Things it doesn't model:

- **No commissions or fees.**
- **Fills are your choice within the bid–ask.** A real order at the mid might not fill.
- **No early assignment.** Positions are settled only at expiration. Ghost Trader alerts you when early assignment would be likely, but doesn't do it.

### First launch

1. **Alpha Vantage key (optional, free).** Ghost Trader uses it to fetch the 3-month Treasury bill rate, which sets the interest on your cash. Go to Settings → Data & interest → *Get a free key*, then paste the key. Without a key, Ghost Trader falls back to Yahoo's T-bill rate, then to a manual rate you set.
2. **Start a run.** A **run** is one paper account from start to finish. Enter your starting cash. Everything (balances, trades, performance) belongs to the current run.

### What happens every time it opens

Before you can trade, Ghost Trader brings everything up to date. The startup screen shows each step:

| Step | What it does |
|---|---|
| Update | Checks for a newer version of Ghost Trader. |
| Rate | Fetches the latest T-bill rate. |
| Interest | Adds interest for every day since you last opened it, and pays it out if a pay date passed. |
| Settle | Settles any options that expired while the app was closed. |
| Quotes | Refreshes quotes for your open positions. |
| Price | Fetches the TQQQ price. |
| Snapshot | Records the day's account value for the Performance chart. |

If a step fails, it retries once. If it fails again, Ghost Trader tells you what went wrong and lets you fix it, retry, or skip. Skipped steps show as warnings on the Portfolio and in History.

### The header

The top bar always shows:

- **Account value:** hover to see the breakdown.
- **Collateral:** cash currently securing puts.
- **Shares:** how many TQQQ shares you hold and the price.
- **Data as of:** when the data was last refreshed, and whether the market is open.

Double-click any of these to jump to the related screen.

### How the money is counted

Your cash sits in two buckets:

- **Available:** cash you can spend or use as new collateral.
- **Collateral:** cash set aside for open puts.

> **Account value = Available + Collateral + accrued interest + shares × TQQQ price**

Open options aren't counted at their current buy-back price. Premium goes into Available the moment you sell, and the effect of an open option shows up in the P&L column instead. This keeps the account value from jumping around with every quote.

### Portfolio

The main screen. From top to bottom:

- **Alerts** (see below).
- **Cards:** account value and return, Available, Collateral, Shares, premium collected this run, and interest earned (with the next pay date).
- **Open options:** each position with contracts, the price you sold at, the current mark, collateral or shares covering, distance from the strike (and whether it's ITM or OTM), days to expiration (DTE), and P&L. Double-click a contract to open it in the Chain with its details panel. **Close** opens a buy-to-close ticket.
- **Shares:** your lots, average cost, value and P&L, how many shares are covering calls and how many are free. **Buy shares…** opens a share ticket.
- **Calendar** (see below).

### Alerts

| Alert | When it shows |
|---|---|
| Expires this week | An open option expires within the week. |
| Near the money / In the money | TQQQ is within 3% of a short put's strike, or past it. |
| Early assignment risk | A short call is in the money ahead of an ex-dividend date. |
| Startup warnings | A startup step was skipped or failed. |

### Notifications

Ghost Trader can send desktop notifications, even when the app is closed. A small timer checks at 7:45 AM and 3:30 PM Central on trading days.

| Notification | When |
|---|---|
| Expiration day | 7:45 AM on a day your options expire: which ones, and TQQQ versus each strike. |
| End-of-day summary | 3:30 PM: the day's change in account value, premium collected, interest earning per day, and what expires on the next trading day. Turn it on or off in Settings → Notifications. *Send now* shows today's. |
| Indicator alerts | When a reading you chose crosses your level, for example the 14,3,3 stochastic dropping below 20, Fear & Greed going under 25, or the VIX rising above 30. |

Indicator alerts are set up in Settings → Notifications. Each rule picks a reading (any of the four stochastics, the VIX, or Fear & Greed), *below* or *above*, and a level. *Add suggested* fills in four common ones. Each row shows the reading right now, with a dot if it's already past the level.

An alert fires **once per crossing**. If the stochastic drops below 20 and stays there for a week, you hear about it once. It fires again only after the reading goes back above 20 and then drops below it again. Alerts are checked whenever the indicators refresh in the app and at the two timer times, and each one is logged in History.

### Calendar

Below Shares, a month view of weekdays shows:

- TQQQ's closing price and daily change on past days.
- Your open expirations (highlighted) and settled ones (faded).
- Market holidays and early closes.
- Interest pay dates.
- Days you traded (double-click to see that day in History).
- Market events: Fed (FOMC) decisions, CPI inflation reports, the monthly jobs report, and TQQQ ex-dividend dates.
- Earnings dates for the biggest Nasdaq-100 companies: NVIDIA, Apple, Microsoft, Amazon, Alphabet, Meta, Broadcom and Tesla. Their results can move the whole index, and TQQQ three times as much, overnight. Dates come from Yahoo and are checked once a day.

### Chain

The option chain for TQQQ: every strike with a bid, for one expiration at a time.

- **Expiration picker:** grouped by week and month, with days to expiration.
- **Calls / Both / Puts:** show one side or both. In Both, calls are on the left and puts on the right, with strikes down the middle.
- **Shading** marks in-the-money strikes. A line shows where the current TQQQ price falls.
- A **dot** next to a strike means you hold that contract. Double-click it to jump to the position.
- **Vol** (volume) shows how many contracts of that strike traded today. Strikes that trade more usually have tighter bid–ask spreads, which matters for real fills.
- **Click any bid, ask or mid** to open a ticket for that contract.
- **Refresh** fetches the chain again.

### The ticket

The ticket opens on the right. It shows:

- **Contract:** expiration, strike and call/put. You can change any of them in the ticket.
- **Quote:** bid, ask, mid, implied volatility and delta.
- **Contracts and fill price.** The fill price starts at the mid when selling and halfway between the mid and the ask when buying. You can type any price from the bid to the ask.
- **What happens:** premium in, collateral set aside (or shares locked), interest on the collateral to expiration, the return if it expires worthless, and your Available cash before and after.
- **Chances** (when selling to open): three lines, each with a plain percentage. **Chance of expiring worthless** (TQQQ finishes on the keep-the-premium side of the strike), **chance of assignment** (or **of being called away** for a covered call; always 100% minus the first line), and **chance of profit at expiration** (TQQQ finishes on the profitable side of your breakeven, which for a put is the strike minus the premium, so profit can include being assigned). Hover any line for exactly what it means for that contract. These are estimates from the option's implied volatility, the same math that prices the option, not predictions. They assume the market's expected volatility is right and say nothing about direction.
- **Note and tags:** write why you're making the trade and tag it (for example `#earnings-week`). You'll see notes and tags again in History.
- **Compare:** a table of the same trade across other **dates** or other **strikes**, with return and annualized return. The best annualized return gets a star. Click a row to switch to it.
- **Rule check:** a green line if the trade passes every rule, or a red line saying exactly what's wrong.

Click **Review trade** to see a summary, then **Confirm** (or press Enter). **Trades can't be undone.** To reverse one, you'd have to make the opposite trade at the current price.

### The rules

| Rule | What it means |
|---|---|
| Puts must be cash-secured | Available cash must cover strike × 100 × contracts **before** the trade. The premium you're about to collect doesn't count toward it. |
| Calls must be covered | You need 100 **free** shares per contract. Shares already covering another call don't count. |
| Fill within the bid–ask | Any price from the bid to the ask. No exceptions. |
| Fresh quotes | During market hours, quotes older than 15 minutes must be refreshed before you can trade. |
| Sizing warning | If one put's collateral is more than 80% of account value, you're warned. You can still confirm. |
| No buying options to open | Off by default. It can be turned on in Settings → Trading. |
| Shares are sold only if free | Shares covering a call can't be sold until the call is closed or expires. |
| No fees | No commissions are charged. |

### The Indicators tab

Readings for TQQQ, the VIX and Fear & Greed, explained in [Indicators](#indicators).

- **Cards:** TQQQ's latest price, the four stochastic readings (with whether each rose or fell since the day before), the VIX with its 1-year range, and Fear & Greed with its readings from the prior close, 1 week, 1 month and 1 year ago.
- **Range** (top right): 3M, 6M, 1Y, 2Y set how much history every chart and the table cover. The tab opens on 3M. Chart/Table and Refresh sit next to it.
- **TQQQ group:** the price chart, with the stochastic below it in its own tinted panel. Tabs along the top of that panel (14,3,3 · 30-day · 60-day · 180-day) choose which stochastic it draws. Clicking a row in the stochastic card does the same. In the table view the same tabs choose the stochastic column.
- **Market mood group:** the VIX and Fear & Greed charts.
- **Charts:** all on the same dates. Hover anywhere to see every value for that day. **Click** to pin that day's box (Esc or its × unpins), and **double-click** a day to open History for that day.
- **Table:** the same numbers day by day, newest first.
- **Refresh** fetches everything again. Otherwise data is fetched when you open the tab and reused for 15 minutes.

If one source can't be reached, a note says which, and the rest still shows.

### Position details

Click a position (or its dot in the Chain) to open its details:

- what you sold it at and the premium, the current quote, and P&L if closed at the mark,
- collateral or covering shares, and interest on the collateral to expiration,
- how far TQQQ is from the strike and the days left,
- what happens if it expires worthless, and what happens if it's assigned or called away,
- your note and tags.

From here you can open a **Close** ticket.

### Expiration and settlement

Options settle on the expiration date against TQQQ's **official closing price**, at the first launch after **5:00 PM Central** that day (or the next time you open the app).

- **In the money by $0.01 or more:**
  - Short put: **assigned**. Collateral pays for 100 shares per contract at the strike. The shares are added as a new lot at the strike price.
  - Short call: **called away**. 100 shares per contract are sold at the strike. Proceeds go to Available.
- **Otherwise:** the option **expires** worthless. You keep the premium, and the collateral or shares are released.

Shares are used oldest-first (first in, first out) when they're sold or called away.

### Interest

All your cash, Available and Collateral both, earns interest:

- The rate is the 3-month Treasury bill rate, minus an optional **haircut** you can set to mimic a broker that pays less.
- Interest accrues every day, including weekends and holidays.
- It's paid on the **15th** of each month, or the business day before if the 15th is a weekend or holiday. Once paid, it earns interest too.
- Accrued (not yet paid) interest is included in account value.

### Dividends

If you hold shares the day before an ex-dividend date, the dividend is added to Available.

### History

Every event in the run, newest first: trades, share buys and sells, expirations, assignments, interest, dividends and startup warnings.

- **Filters:** All, Trades, Expirations & Assignments, Interest, Errors.
- **Tags:** double-click a tag anywhere to see every trade with that tag. Tags can be renamed, merged or deleted.
- **Double-click a trade** to open the full story of that position: every event, the outcome, what was bought back, the total result, interest earned and days held.
- **Export** the history to CSV.

### Performance

How the run is doing, and how it compares with simpler choices:

- **Cards:** your return, plus two benchmarks: what buying TQQQ shares on day one and holding would have returned, and what leaving all the cash in T-bills would have returned.
- **Account value chart:** one point for each day the app was opened, drawn against the two benchmarks.
- **TQQQ price chart:** with diamond markers on days you got shares. Click a marker to pin its details, and double-click it to open that lot in History.
- **Monthly bars:** premium collected and interest posted each month, with interest not yet paid shown striped.

Each chart can be switched to a table view.

**Readings at entry vs. outcomes** (below the charts) uses the readings saved with your trades. It groups your finished short options by what a reading was when you opened them, for example the 14,3,3 stochastic under 20, between 20 and 80, or over 80. Tabs switch between the four stochastics, the VIX and Fear & Greed. For each group it shows:

- **Trades** in the group, and the **win rate** (a positive result).
- **Average % of premium kept** on the option.
- How many **expired worthless**, and how many were **assigned or called away**.
- **Average result.** Assigned puts count the shares at the closing price on the day they were assigned, so a loss on the shares isn't hidden behind the premium.

With only a few trades in a group, the numbers say very little.

### Settings

- **Trading:** the rules, the fill defaults, and the switch for buying options to open.
- **Data & interest:** the Alpha Vantage key, rate source, manual rate, haircut, **auto-refresh**, and expiration-day alerts.
- **Notifications:** the end-of-day summary switch and your indicator alerts (see [Notifications](#notifications)).

**Auto-refresh** re-fetches TQQQ and the quotes for your open positions every 5, 10 or 15 minutes while the market is open (10 by default), so P&L, alerts and the header stay current without clicking Refresh. It pauses the screen update while a ticket or dialog is open. Quotes are still Yahoo's, about 15 minutes behind.
- **Runs & app:** the current run, past runs, closing a run, the data folder, the last backup, and the version.
- **Appearance:** theme (light, dark, or match system).

**Closing a run** ends it for good. You type the final account value to confirm. Ghost Trader exports the run's full history to CSV, then you can start a new run.

### Navigating

- **Double-click** any underlined item to jump to it.
- **1–7** switch tabs (Portfolio, Chain, Indicators, History, Performance, Settings, Help).
- **Esc** closes a panel or ticket.
- **Enter** confirms.
- All times are **Central**, with Eastern in parentheses in most places.

---

## Your first trade, step by step

This walks through selling one cash-secured put. Read it with Ghost Trader open.

1. **Check your cash.** On Portfolio, look at the **Available** card. One put needs strike × 100 in Available. For a $55 put that's $5,500.
2. **Open the Chain.** Press **2** or click **Chain**. Pick an expiration from the dropdown.
3. **Switch to Puts.** Click **Puts** so only puts show. Strikes shaded as in the money are above the current price.
4. **Pick a strike and click its mid.** The ticket opens on the right with that contract.
5. **Read the ticket.** Check the premium you'd collect, the collateral, your breakeven (strike minus the fill price), and the Available cash after. Use **Compare** to see the same trade at other dates or strikes.
6. **Write a note.** Say why you're making this trade. You'll be glad you did later.
7. **Check the rule line.** Green means the trade is allowed. Red tells you exactly why not, for example not enough Available cash.
8. **Review and confirm.** Click **Review trade**, read the summary, then **Confirm**.
9. **See it on the Portfolio.** The put appears under Open options. The premium is in Available, and the collateral is in its own card.
10. **Watch it.** Distance and P&L update with each quote refresh. Alerts appear as expiration nears or if TQQQ gets close to the strike.
11. **Decide.** Close early with **Close**, or let it run. After expiration, the next launch settles it. History shows the outcome.

---

## Glossary

| Term | Meaning |
|---|---|
| American-style | An option that can be exercised any day up to expiration. |
| Annualized return | A return scaled to a year (return × 365 ÷ days), for comparing trades of different lengths. |
| Ask | The lowest price someone is willing to sell at. |
| Assignment | Being required to complete the trade when the option's buyer exercises. |
| Bid | The highest price someone is willing to pay. |
| Breakeven | The stock price where the trade neither makes nor loses money at expiration. For a short put, strike − premium. |
| Buy to close | Buying back an option you sold, ending the obligation. |
| Call | The right to buy 100 shares at the strike. |
| Called away | Shares sold at the strike because a covered call was assigned. |
| Cash-secured put | A put sold with the full purchase cost set aside as cash. |
| Collateral | Cash set aside to secure a short put. |
| Chance of profit | An estimate, from implied volatility, of the chance a trade finishes beyond its breakeven at expiration. For a short put that includes assignments above the breakeven. |
| Covered call | A call sold against 100 shares you own per contract. |
| Delta | How much an option's price moves per $1 move in the stock. Also used as a rough chance of finishing in the money. |
| %D | In the 14,3,3 stochastic, a 3-day average of %K. |
| %K | The stochastic reading: where the close sits in the recent high-to-low range, 0 to 100. |
| DTE | Days to expiration. |
| Ex-dividend date | The first day a share trades without the right to its next dividend. |
| Exercise | Using an option's right to buy or sell. |
| Expiration | The last day an option exists. |
| Fear & Greed | CNN's 0–100 score of market mood, built from seven measures. |
| Implied volatility (IV) | How much the market expects the stock to move, read from option prices. |
| In the money (ITM) | A put with the stock below the strike, or a call with the stock above it. |
| Intrinsic value | The part of an option's price equal to how far it's in the money. |
| Lookback | How many days of history an indicator covers. |
| Lot | A group of shares bought at one time and price. |
| Mark | The current value Ghost Trader uses for an open option (the mid). |
| Mid | Halfway between the bid and the ask. |
| Out of the money (OTM) | A put with the stock above the strike, or a call with the stock below it. |
| Premium | The price of an option. |
| Put | The right to sell 100 shares at the strike. |
| Roll | Closing one option and opening another with a later date or different strike. |
| Run | One paper account in Ghost Trader, from starting cash to close. |
| Sell to open | Selling an option to start a position. |
| Spread | The gap between the bid and the ask. |
| Stochastic oscillator | A 0–100 reading of where the latest close sits within the high-to-low range of the last *n* days. |
| Strike | The price at which an option's shares are bought or sold. |
| Time decay | The loss of an option's time value as expiration approaches. |
| Time value | The part of an option's price beyond its intrinsic value. |
| VIX | The CBOE Volatility Index: how much movement S&P 500 options are pricing in. |
| Volatility decay | The tendency of a daily-leveraged fund to lose ground in a choppy market. |
| Volume | How many contracts of an option traded today. |
| Wheel | Cycling between cash-secured puts and covered calls. |

---

## Further reading

- [Characteristics and Risks of Standardized Options](https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document): the official options risk booklet from the Options Clearing Corporation. Brokers must give it to you before you can trade options.
- [ProShares UltraPro QQQ (TQQQ)](https://www.proshares.com/our-etfs/leveraged-and-inverse/tqqq): the fund's own page, with its objective, fees and holdings.
- [The Lowdown on Leveraged and Inverse Exchange-Traded Products](https://www.finra.org/investors/insights/lowdown-leveraged-and-inverse-exchange-traded-products): FINRA's explainer on daily-reset funds.
- [CNN Fear & Greed Index](https://www.cnn.com/markets/fear-and-greed): CNN's page for the index, with an explanation of its seven measures.
- [Cboe VIX Index](https://www.cboe.com/tradable_products/vix/): how the VIX is calculated.
- [SEC investor bulletin on leveraged and inverse ETFs](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-alerts/sec-finra): why these funds behave differently over longer periods.

The TQQQ figures in this manual (the daily 3× objective, launch date, fees, and the 2022 drawdown) come from these sources and public price history as of late 2026.

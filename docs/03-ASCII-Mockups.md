# ASCII Mockups — UI Wireframes
### Trading Bot Platform (responsive web)

Legend: `[ ]` button · `( )` radio · `[x]` checkbox · `▼` dropdown · `●` realtime
Mode badge: `🟢PAPER` `🟡TESTNET` `🔴LIVE`

---

## 1. Overall layout (Desktop)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ⚡ BinBot      [Dashboard] [Chart] [Strategies] [Backtest] [Scanner] [Log] │
│                                            ● Feed: LIVE   🟢PAPER   ⚙ ☾    │
├───────────────┬──────────────────────────────────────────────────────────┤
│ WATCHLIST     │                                                            │
│ ───────────── │                  (main page content)                       │
│ ●BTCUSDT      │                                                            │
│   64,210 +1.2%│                                                            │
│ ●ETHUSDT      │                                                            │
│   3,180  -0.4%│                                                            │
│ ●SOLUSDT      │                                                            │
│   142.5 +3.1% │                                                            │
│ [+ add pair]  │                                                            │
└───────────────┴──────────────────────────────────────────────────────────┘
```

---

## 2. Dashboard (home page)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ DASHBOARD                                       🟢PAPER  ● Feed OK         │
├──────────────────────────────────────────────────────────────────────────┤
│ ┌─ Equity ──────────┐ ┌─ PnL today ───┐ ┌─ Open pos. ─┐ ┌─ Winrate ─┐    │
│ │  $10,420  ▲ 4.2%  │ │  +$182  ▲     │ │     3       │ │   58%     │    │
│ └───────────────────┘ └───────────────┘ └─────────────┘ └───────────┘    │
│                                                                            │
│ RUNNING BOTS                                                               │
│ ┌────────────────────────────────────────────────────────────────────┐   │
│ │ Bot          Pair     Mode     Ver   PnL      Status      Action     │   │
│ │ ema_cross    BTCUSDT  🟢PAPER  1.2   +$92    ●Running   [⏸][⚙][✕]   │   │
│ │ rsi_rev      ETHUSDT  🟢PAPER  2.0   -$14    ●Running   [⏸][⚙][✕]   │   │
│ │ macd_v3      SOLUSDT  🟡TEST   3.1   +$104   ⏸Paused    [▶][⚙][✕]   │   │
│ └────────────────────────────────────────────────────────────────────┘   │
│ [+ New bot]                                                                │
│                                                                            │
│ OPEN POSITIONS                                     [Close all]             │
│ ┌────────────────────────────────────────────────────────────────────┐   │
│ │ Pair    Side  Size   Entry    Current   PnL     SL/TP      Action    │   │
│ │ BTCUSDT LONG  0.01   63,900   64,210   +$31   62k/66k  [Close][Edit] │   │
│ │ ETHUSDT LONG  0.10   3,200    3,180    -$20   3.1k/3.4k [Close][Edit]│   │
│ └────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Chart (like a mainstream exchange)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ BTCUSDT ●64,210  +1.2%   [1m][5m][15m][1H][4H][1D]   Indicators▼  🟢PAPER │
├──────────────────────────────────────────────────────────────────────────┤
│ 64500┤                                          ╱╲                         │
│ 64000┤                              ╱╲    ╱╲   ╱   ▲BUY                     │
│ 63500┤                 ╱╲   ╱╲    ╱   ╲╱   ╲ ╱                             │
│ 63000┤      ▲BUY  ╱╲ ╱   ╲ ╱   ╲ ╱                  ┄┄┄┄ TP 66,000         │
│ 62500┤    ╱   ╲╱   ╲╱     ╲╱      EMA9 ─── EMA21 ───                       │
│ 62000┤  ╱                            ┄┄┄┄┄┄┄┄┄┄┄┄┄┄ SL 62,000             │
│      └────────────────────────────────────────────────────────────────    │
│ Vol  ▏▎▍▌▋█▊▆▅▃▂▁▃▅▆█▇▅▃▂▁▂▄▆█▇▆▅▃▂▁▂▃▅▇█▆▄▂                            │
│ RSI  ┄┄┄┄70┄┄┄┄┄╱╲┄┄┄┄┄┄┄╱╲┄┄┄┄┄  56                                     │
│      ──────30─────────────────────────                                     │
├──────────────────────────────────────────────────────────────────────────┤
│ MANUAL ORDER:  ( )Market ( )Limit Price[______] Size[_____]  SL[__] TP[__] │
│                [ BUY / LONG ]   [ SELL / SHORT ]                           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Strategies (list + versions)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ STRATEGIES                                              [+ New strategy]   │
├──────────────────────────────────────────────────────────────────────────┤
│ Name         Version  File             Backtest PnL  In use     Action     │
│ ────────────────────────────────────────────────────────────────────────  │
│ ema_cross    1.0      ema_cross.py     +12.4%        —          [Edit][BT] │
│ ema_cross    1.2 ★    ema_cross.py     +18.1%        2 bots     [Edit][BT] │
│ rsi_rev      2.0      rsi_rev.py       +6.8%         1 bot      [Edit][BT] │
│ macd_v3      3.1      macd_v3.py       +21.0%        1 bot      [Edit][BT] │
│                                                                            │
│ ★ = default active version    [BT]=Backtest                               │
└──────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Editing strategy params (no code edits)

```
┌─────────────────────── ema_cross  v1.2 ────────────────────────┐
│ PARAMS                                                         │
│   fast EMA      [  9 ]                                         │
│   slow EMA      [ 21 ]                                         │
│   size          [ 0.01 ]                                       │
│   timeout (s)   [ 30 ]   (auto-cancel stale limit)            │
│                                                                │
│ ALGORITHM (read-only / open in editor)       [ Open code ✎ ]  │
│ ┌────────────────────────────────────────────────────────┐   │
│ │ def on_candle(self, ctx):                              │   │
│ │     fast = ema(ctx.candles, self.params['fast'])       │   │
│ │     slow = ema(ctx.candles, self.params['slow'])       │   │
│ │     ...                                                │   │
│ └────────────────────────────────────────────────────────┘   │
│                                                                │
│ [ Save as new version ]  [ Overwrite ]   [ Backtest now ]     │
└────────────────────────────────────────────────────────────────┘
```

---

## 5. Backtest

```
┌──────────────────────────────────────────────────────────────────────────┐
│ BACKTEST                                                                   │
├──────────────────────────────────────────────────────────────────────────┤
│ Strategy[ ema_cross v1.2 ▼]  Pair[ BTCUSDT ▼]  TF[ 1H ▼]                  │
│ From[ 2025-01-01 ]  To[ 2025-06-01 ]  Capital[ 10000 ]  Fee[ 0.04% ]     │
│                                                       [ ▶ Run backtest ]   │
├──────────────────────────────────────────────────────────────────────────┤
│ RESULTS                                                                    │
│ ┌─ PnL ─────┐ ┌─ Winrate ─┐ ┌─ Max DD ─┐ ┌─ Sharpe ─┐ ┌─ #Trades ─┐     │
│ │ +18.1%    │ │   61%     │ │  -7.3%   │ │  1.84    │ │   142     │     │
│ └───────────┘ └───────────┘ └──────────┘ └──────────┘ └───────────┘     │
│                                                                            │
│ EQUITY CURVE                                                               │
│  11.8k┤                                       ╱╲___╱╲___╱                  │
│  11.0k┤                          ___╱╲___╱╲__╱                            │
│  10.4k┤             ___╱╲___╱╲__╱                                         │
│  10.0k┤___╱╲___╱╲__╱                                                      │
│       └────────────────────────────────────────────────────────────       │
│                                                                            │
│ TRADE LIST                                                                │
│  #  Time               Side  Entry    Exit     PnL                        │
│  1  01-03 14:00        LONG  42,100   43,050   +2.2%                      │
│  2  01-07 09:00        LONG  43,800   43,200   -1.4%                      │
│  ...                                          [ View on chart ]           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Scanner (research & suggestions)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ SCANNER                          Filter[ Trend + RSI ▼]   [↻ Rescan]       │
├──────────────────────────────────────────────────────────────────────────┤
│ Pair      Score  Signal      Reason                      Action            │
│ ──────────────────────────────────────────────────────────────────────    │
│ SOLUSDT    92    ▲ LONG     EMA cross up + RSI 45 dip   [Chart][→Bot]      │
│ AVAXUSDT   85    ▲ LONG     4H resistance breakout      [Chart][→Bot]      │
│ DOGEUSDT   71    ◦ Watch    Sideways, await confirm     [Chart]            │
│ XRPUSDT    40    ▼ SHORT    Lost support + RSI 68       [Chart][→Bot]      │
│                                                                            │
│ Scanned at 14:32 · 50 pairs · auto every 15 min                           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Audit Log

```
┌──────────────────────────────────────────────────────────────────────────┐
│ AUDIT LOG                Filter:[ All ▼] [ Bot ▼] [ Manual ▼] [Export CSV] │
├──────────────────────────────────────────────────────────────────────────┤
│ Time            Source  Mode    Pair     Action          Details           │
│ ──────────────────────────────────────────────────────────────────────    │
│ 14:31:02        BOT     🟢PAPER BTCUSDT  OPEN LONG       0.01 @63,900     │
│ 14:33:50        MANUAL  🟢PAPER ETHUSDT  EDIT SL/TP      SL 3.1k→3.0k     │
│ 14:35:11        BOT     🟢PAPER SOLUSDT  CANCEL LIMIT    timeout 30s       │
│ 14:40:00        MANUAL  🟢PAPER BTCUSDT  CLOSE           +$31             │
│ 14:41:25        SYS     —       —        FEED RECONNECT  WS reconnected    │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Live Mode — safety guardrails (confirmation modal)

```
        ┌─────────────── ⚠  ENABLE LIVE TRADING ────────────────┐
        │                                                       │
        │   🔴 You are about to switch 'ema_cross v1.2' to LIVE │
        │      → trading with REAL MONEY on Binance.            │
        │                                                       │
        │   Checklist:                                          │
        │   [x] Backtested                                      │
        │   [x] Ran on paper ≥ 24h                              │
        │   [ ] API key withdrawals disabled                    │
        │                                                       │
        │   Type "LIVE" to confirm: [________]                  │
        │                                                       │
        │            [ Cancel ]   [ 🔴 ENABLE LIVE ]            │
        └───────────────────────────────────────────────────────┘
```

---

## 9. Mobile (responsive — narrow screen)

```
┌─────────────────────┐    ┌─────────────────────┐
│ ⚡BinBot   🟢 ● ☰   │    │ BTCUSDT  ●64,210    │
├─────────────────────┤    │ +1.2%   [1H▼]       │
│ Equity  $10,420 ▲   │    ├─────────────────────┤
│ PnL today    +$182  │    │     ╱╲    ▲BUY      │
├─────────────────────┤    │   ╱╲  ╲ ╱           │
│ BOTS                │    │ ╱    ╲╱   EMA──      │
│ ┌─────────────────┐ │    │ ┄┄┄┄┄┄┄ SL/TP      │
│ │ema_cross 🟢     │ │    ├─────────────────────┤
│ │BTC +$92 ●Run ⏸ │ │    │ [Buy]      [Sell]   │
│ ├─────────────────┤ │    ├─────────────────────┤
│ │rsi_rev 🟢       │ │    │ POSITIONS           │
│ │ETH -$14 ●Run ⏸ │ │    │ BTC LONG +$31       │
│ └─────────────────┘ │    │ [Close]   [Edit]    │
├─────────────────────┤    └─────────────────────┘
│ [📊][🤖][🔍][📜]    │     (tab bar at bottom)
└─────────────────────┘
   Dashboard
```

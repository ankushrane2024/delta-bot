# ARES Signal Provider Specification

## Project Context

ARES is the intelligence layer designed to protect an intraday BTC short-strangle strategy. It does not predict price to capture directional profits; it aims to identify structural trend developments early enough to deploy protective delta-hedges against the threatened option leg.

Signal Providers are strictly evidence-gathering modules. They **do not** make hedging decisions. Each provider observes a specific dimension of market behavior and feeds its isolated analysis into the Trend Intelligence Engine, which fuses the data to calculate the overarching probability of trend continuation, whipsaw, or reversal.

---

## 1. Price Action Analyzer

- **Purpose:** To interpret raw candlestick patterns and immediate price velocity.
- **What market behavior it observes:** Candle body size, wick rejections, momentum sequences (e.g., three consecutive large-body candles), and closing prices relative to recent highs/lows.
- **What information it contributes:** Short-term momentum direction and immediate exhaustion signals (e.g., long wicks rejecting a breakout).
- **Why it matters for protecting a short strangle:** Early identification of sudden momentum spikes allows ARES to prepare a hedge before structural damage occurs.
- **Inputs:** Real-time OHLCV (Open, High, Low, Close, Volume) data.
- **Outputs:** Immediate directional bias, momentum strength, and exhaustion probability.
- **Confidence contribution:** High for immediate micro-trend identification; low for macro structural shifts.
- **Strengths:** Zero lag. Reacts instantly to market shock.
- **Weaknesses:** Highly susceptible to noise and algorithmic stop-hunts.
- **Failure cases:** Whipsaw environments where large candles are immediately engulfed by the opposing side, generating rapid false signals.

---

## 2. Market Structure Analyzer

- **Purpose:** To map the overarching framework of the market via support, resistance, and swing points.
- **What market behavior it observes:** The formation of Higher Highs (HH), Higher Lows (HL), Lower Highs (LH), and Lower Lows (LL). It tracks major liquidity pools and historical pivot zones.
- **What information it contributes:** The macro path of least resistance and proximity to critical breakout thresholds.
- **Why it matters for protecting a short strangle:** A structural breakout (e.g., breaking a massive daily resistance level) often precedes a sustained trend that will destroy a short call. ARES uses this to differentiate between normal range oscillations and true breakouts.
- **Inputs:** Rolling historical OHLC data to map swing highs and lows.
- **Outputs:** Market structure state (Bullish, Bearish, Ranging), proximity to key levels, and structural failure alerts.
- **Confidence contribution:** Very high for trend persistence and continuation probability.
- **Strengths:** Excellent at filtering out intraday noise and defining true market regimes.
- **Weaknesses:** inherently lagging; structural shifts are only confirmed after the move has begun.
- **Failure cases:** Fakeouts, where price breaches a structural level to sweep liquidity and immediately mean-reverts back into the range.

---

## 3. Volume Analyzer

- **Purpose:** To measure the financial effort behind price movements.
- **What market behavior it observes:** Trade volume spikes, volume divergence (e.g., price rising but volume falling), and relative volume compared to historical averages.
- **What information it contributes:** The legitimacy and institutional backing of a price move.
- **Why it matters for protecting a short strangle:** A price spike on microscopic volume is likely a fakeout and should *not* trigger a hedge. A price spike on massive volume is a legitimate threat requiring immediate hedging.
- **Inputs:** Real-time trade volume and historical volume profiles.
- **Outputs:** Volume anomaly score, effort-vs-result divergence, and trend legitimacy validation.
- **Confidence contribution:** Acts as a primary multiplier for Trend Confidence. High volume = high confidence.
- **Strengths:** One of the few non-derived, pure market metrics. Cannot be faked.
- **Weaknesses:** Difficult to interpret during extreme low-liquidity periods (e.g., weekends).
- **Failure cases:** Wash trading or extreme retail FOMO that generates high volume without sustained institutional support.

---

## 4. Volatility Analyzer

- **Purpose:** To measure the width and aggression of underlying price swings.
- **What market behavior it observes:** The true range of candles, historical volatility, and the expansion/compression cycles of price movement.
- **What information it contributes:** Whether current price action is abnormally violent or safely within expected statistical bounds.
- **Why it matters for protecting a short strangle:** Short strangles thrive in volatility compression and die in volatility expansion. Identifying a volatility expansion early is critical to locking delta.
- **Inputs:** OHLC data (specifically focusing on range extremes).
- **Outputs:** Volatility state (Compressing, Expanding, Peaked), expected range bands.
- **Confidence contribution:** Modulates the urgency of the signal. High volatility increases the speed at which hedges must be deployed.
- **Strengths:** Excellent at predicting imminent breakouts (compression usually precedes expansion).
- **Weaknesses:** Does not provide directional bias, only magnitude.
- **Failure cases:** "Choppy" high-volatility environments where the range is wide but directionless, potentially triggering unnecessary hedges on both sides.

---

## 5. VWAP Analyzer

- **Purpose:** To track the intraday battle line between buyers and sellers.
- **What market behavior it observes:** The Volume-Weighted Average Price, standard deviation bands, and price interaction with the VWAP anchor.
- **What information it contributes:** Intraday fair value and macroeconomic control (who is dominating the session).
- **Why it matters for protecting a short strangle:** If price is aggressively pushing away from the VWAP and riding the upper standard deviation band, it signals a strong trending day where the short call is in severe danger.
- **Inputs:** Tick-level price and volume data anchored to the daily open.
- **Outputs:** VWAP relation (Above/Below), band proximity, and intraday trend strength.
- **Confidence contribution:** High for intraday trend confirmation.
- **Strengths:** Widely respected by institutional algorithms, making it a self-fulfilling prophecy.
- **Weaknesses:** Loses efficacy during low-volume ranging days where price crosses it repeatedly.
- **Failure cases:** Mean-reversion days where price stretches far from VWAP only to rubber-band back aggressively.

---

## 6. Open Interest Analyzer

- **Purpose:** To track the flow of fresh capital into derivatives.
- **What market behavior it observes:** The total number of outstanding derivative contracts (futures/perpetuals). It observes whether OI is increasing or decreasing alongside price.
- **What information it contributes:** Differentiates between trend initiation (new money entering) and short/long squeezes (old money being forced to close).
- **Why it matters for protecting a short strangle:** A price spike driven by plummeting OI is a short-squeeze. Squeezes are often rapid but temporary, meaning a hedge might get whipsawed. A price spike with rising OI indicates a genuine new trend requiring a persistent hedge.
- **Inputs:** Real-time Open Interest data from the exchange.
- **Outputs:** OI delta, participation health, squeeze probability.
- **Confidence contribution:** Crucial for filtering fakeouts and identifying whipsaw probability.
- **Strengths:** Provides deep insight into market mechanics that price action cannot show.
- **Weaknesses:** Data can be noisy on lower timeframes.
- **Failure cases:** Unrelated macro events causing mass deleveraging that obscures actual directional intent.

---

## 7. IV Analyzer

- **Purpose:** To measure the fear and forward-looking expectations of options traders.
- **What market behavior it observes:** Implied Volatility across various strikes and expiries, focusing on IV skew and overall IV level.
- **What information it contributes:** Determines if the options market is pricing in a severe directional move or crash.
- **Why it matters for protecting a short strangle:** Since the bot sells options, rising IV directly inflates unrealized losses even if price hasn't moved yet. Monitoring IV skew helps detect "tail risk" pricing.
- **Inputs:** Real-time options chain pricing, Greeks, and mark prices.
- **Outputs:** IV trend, IV skew (Call vs Put demand), and options market fear gauge.
- **Confidence contribution:** High for confirming downside panic or upside euphoria.
- **Strengths:** Forward-looking metric; options traders often price in risk before the spot market moves.
- **Weaknesses:** Can remain elevated post-event, causing lingering false positives.
- **Failure cases:** IV crush events (e.g., post-CPI release) where IV plummets rapidly, skewing historical averages.

---

## 8. Funding Rate Analyzer

- **Purpose:** To measure the aggressiveness of perpetual futures traders.
- **What market behavior it observes:** The premium or discount of perpetual futures relative to the spot market.
- **What information it contributes:** Identifies overcrowded trades. High positive funding means longs are aggressively paying shorts, indicating an overcrowded long side (and vice versa).
- **Why it matters for protecting a short strangle:** Overcrowded trades are highly susceptible to cascading liquidations. If funding is extremely positive, the bot should anticipate a potential violent downside flush.
- **Inputs:** Real-time perpetual funding rates and predicted funding rates.
- **Outputs:** Market sentiment skew, liquidation cascade probability.
- **Confidence contribution:** High for predicting reversal probabilities and trend exhaustion.
- **Strengths:** Excellent contrarian indicator at extremes.
- **Weaknesses:** Funding can remain heavily skewed for extended periods during massive bull runs without breaking.
- **Failure cases:** "Riding the trend" phases where high funding correctly indicates massive, unstoppable institutional buying rather than a retail trap.

---

## 9. Order Flow Analyzer

- **Purpose:** To observe the microscopic, real-time battle at the bid/ask spread.
- **What market behavior it observes:** Cumulative Volume Delta (CVD), market buys vs. market sells, limit order book thickness, and absorption.
- **What information it contributes:** Identifies whether aggressive market orders are successfully moving price, or if they are being absorbed by passive limit orders (e.g., Iceberg orders).
- **Why it matters for protecting a short strangle:** If price reaches a major resistance level and Order Flow shows massive market buying being completely absorbed (CVD rising, price flat), it signals exhaustion. The bot should hold off on hedging the call because a reversal is imminent.
- **Inputs:** Real-time Level 2 order book data and trade tick data.
- **Outputs:** CVD divergence, absorption detection, aggressive imbalance.
- **Confidence contribution:** The ultimate micro-filter for timing entries and filtering false breakouts.
- **Strengths:** Provides the highest fidelity view of actual market mechanics and intent.
- **Weaknesses:** Extremely data-heavy and prone to short-term spoofing by algorithms.
- **Failure cases:** "Spoofing", where massive fake limit orders are placed and pulled rapidly to manipulate the analyzer's absorption logic.

---

## Signal Fusion

### How Analyzers Contribute to the TrendResult

The Trend Intelligence Engine does not blindly act on a single analyzer. It performs **Signal Fusion**—a weighted aggregation of all independent signals to form a holistic `TrendResult`.

1. **Conflict Resolution:** If the Price Action Analyzer signals a breakout (LONG), but the Volume and Open Interest Analyzers report low volume and dropping OI, the Engine detects a conflict. It will heavily penalize the `trend_confidence` and spike the `whipsaw_probability`.
2. **Confirmation:** If Market Structure breaks a daily high, VWAP shows strong upward separation, and Order Flow shows aggressive unabsorbed buying, the Engine registers extreme convergence. `trend_strength` and `continuation_probability` are maximized.
3. **Exhaustion Detection:** If a trend has been active for hours, but the Funding Rate reaches extremes, IV skews heavily, and Order Flow shows absorption at the highs, the Engine will drastically increase the `reversal_probability`, warning the Decision Engine to prepare to unwind hedges.

By fusing these distinct market dimensions, ARES gains a nearly comprehensive view of the market, allowing it to protect the short strangle with surgical precision while aggressively filtering out noise.

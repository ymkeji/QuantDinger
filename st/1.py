# signal_form: four_way
# exit_owner: indicator
# flip_mode: R2

my_indicator_name = "Long & Short Trend MA"
my_indicator_description = "Adaptive KAMA trend, structure/ADX/volatility filters, first-pullback entries, and ATR-managed exits."

# @strategy stopLossPct 0
# @strategy takeProfitPct 0
# @strategy entryPct 0.25
# @strategy trailingEnabled false
# @strategy tradeDirection both

# @param trend_len int 21 KAMA efficiency period
# @param trend_fast int 2 KAMA fast smoothing period
# @param trend_slow int 30 KAMA slow smoothing period
# @param trend_smooth int 3 Final TrendMA smoothing period
# @param slope_lookback int 3 TrendMA slope lookback
# @param slope_threshold float 0.06 Minimum ATR-normalized slope
# @param regime_memory int 8 Bars that preserve a confirmed trend through a pullback
# @param structure_period int 12 Price structure lookback
# @param adx_period int 14 ADX period
# @param adx_threshold float 18.0 Minimum ADX for entries
# @param atr_period int 14 ATR period
# @param atr_stop_mult float 2.2 Initial stop distance in ATR
# @param atr_trail_mult float 2.8 Trailing stop distance in ATR
# @param atr_min_ratio float 0.55 Minimum ATR relative to baseline
# @param atr_max_ratio float 2.8 Maximum ATR relative to baseline
# @param volume_period int 20 Volume average period
# @param volume_mult float 1.0 Entry volume expansion multiplier
# @param stand_bars int 2 Bars that must hold beyond TrendMA
# @param pullback_bars int 4 Maximum bars allowed to confirm a pullback
# @param pullback_tolerance_atr float 0.15 Pullback wick tolerance in ATR
# @param cooldown_period int 15 Minimum bars between same-side entries
# @param max_setup_bars int 30 Maximum lifetime of a breakout setup
# @param max_distance_atr float 2.0 Maximum entry distance from TrendMA
# @param cross_limit int 4 Maximum TrendMA crossings in ten bars
# @param bb_period int 20 Bollinger width period
# @param bb_min_width float 0.012 Minimum normalized Bollinger width
# @param breakeven_trigger_atr float 1.2 Profit in ATR before breakeven stop
# @param trail_trigger_atr float 1.8 Profit in ATR before trailing stop
# @param partial_trigger_atr float 2.2 Profit in ATR before partial exit
# @param take_profit_atr float 4.5 Fixed/final profit target in ATR
# @param partial_fraction float 0.5 Position fraction reduced at partial target
# @param profit_mode str trailing Exit mode: fixed, trailing, partial, or hybrid
# @param position_mode str atr Position mode: atr, percent, or fixed
# @param risk_pct float 0.01 Account risk fraction for ATR sizing
# @param percent_position_pct float 0.25 Capital fraction for percent sizing
# @param fixed_position_pct float 0.25 Capital fraction for fixed sizing
# @param max_position_pct float 0.5 Maximum capital fraction per entry


def edge(signal):
    signal = signal.fillna(False).astype(bool)
    return signal & ~signal.shift(1).fillna(False)


trend_len = max(2, int(params.get("trend_len", 21)))
trend_fast = max(1, int(params.get("trend_fast", 2)))
trend_slow = max(trend_fast + 1, int(params.get("trend_slow", 30)))
trend_smooth = max(1, int(params.get("trend_smooth", 3)))
slope_lookback = max(1, int(params.get("slope_lookback", 3)))
slope_threshold = max(0.0, float(params.get("slope_threshold", 0.06)))
regime_memory = max(2, int(params.get("regime_memory", 8)))
structure_period = max(4, int(params.get("structure_period", 12)))
adx_period = max(2, int(params.get("adx_period", 14)))
adx_threshold = max(0.0, float(params.get("adx_threshold", 18.0)))
atr_period = max(2, int(params.get("atr_period", 14)))
atr_stop_mult = max(0.1, float(params.get("atr_stop_mult", 2.2)))
atr_trail_mult = max(0.1, float(params.get("atr_trail_mult", 2.8)))
atr_min_ratio = max(0.0, float(params.get("atr_min_ratio", 0.55)))
atr_max_ratio = max(atr_min_ratio, float(params.get("atr_max_ratio", 2.8)))
volume_period = max(2, int(params.get("volume_period", 20)))
volume_mult = max(0.0, float(params.get("volume_mult", 1.0)))
stand_bars = max(2, int(params.get("stand_bars", 2)))
pullback_bars = max(1, int(params.get("pullback_bars", 4)))
pullback_tolerance_atr = max(0.0, float(params.get("pullback_tolerance_atr", 0.15)))
cooldown_period = max(1, int(params.get("cooldown_period", 15)))
max_setup_bars = max(stand_bars + pullback_bars + 1, int(params.get("max_setup_bars", 30)))
max_distance_atr = max(0.1, float(params.get("max_distance_atr", 2.0)))
cross_limit = max(0, int(params.get("cross_limit", 4)))
bb_period = max(2, int(params.get("bb_period", 20)))
bb_min_width = max(0.0, float(params.get("bb_min_width", 0.012)))
breakeven_trigger_atr = max(0.0, float(params.get("breakeven_trigger_atr", 1.2)))
trail_trigger_atr = max(0.0, float(params.get("trail_trigger_atr", 1.8)))
partial_trigger_atr = max(0.0, float(params.get("partial_trigger_atr", 2.2)))
take_profit_atr = max(partial_trigger_atr, float(params.get("take_profit_atr", 4.5)))
partial_fraction = min(1.0, max(0.01, float(params.get("partial_fraction", 0.5))))
profit_mode = str(params.get("profit_mode", "trailing")).strip().lower()
position_mode = str(params.get("position_mode", "atr")).strip().lower()
risk_pct = min(1.0, max(0.0001, float(params.get("risk_pct", 0.01))))
percent_position_pct = min(1.0, max(0.01, float(params.get("percent_position_pct", 0.25))))
fixed_position_pct = min(1.0, max(0.01, float(params.get("fixed_position_pct", 0.25))))
max_position_pct = min(1.0, max(0.01, float(params.get("max_position_pct", 0.5))))

if profit_mode not in ("fixed", "trailing", "partial", "hybrid"):
    profit_mode = "trailing"
if position_mode not in ("atr", "percent", "fixed"):
    position_mode = "atr"

df = df.copy()
n = len(df)
close = df["close"].astype(float)
high = df["high"].astype(float)
low = df["low"].astype(float)
open_price = df["open"].astype(float)
volume = df.get("volume", pd.Series(0.0, index=df.index)).astype(float)

# Wilder ATR and ADX use only current and earlier completed bars.
previous_close = close.shift(1)
true_range = pd.DataFrame(
    {
        "high_low": high - low,
        "high_close": (high - previous_close).abs(),
        "low_close": (low - previous_close).abs(),
    },
    index=df.index,
).max(axis=1)
atr = true_range.ewm(alpha=1.0 / atr_period, adjust=False, min_periods=atr_period).mean()
atr_fallback = true_range.rolling(atr_period, min_periods=1).mean()
atr = atr.fillna(atr_fallback).replace(0, np.nan)

up_move = high.diff()
down_move = -low.diff()
plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
plus_dm_smoothed = plus_dm.ewm(alpha=1.0 / adx_period, adjust=False, min_periods=adx_period).mean()
minus_dm_smoothed = minus_dm.ewm(alpha=1.0 / adx_period, adjust=False, min_periods=adx_period).mean()
plus_di = (100.0 * plus_dm_smoothed / atr).replace([np.inf, -np.inf], np.nan).fillna(0.0)
minus_di = (100.0 * minus_dm_smoothed / atr).replace([np.inf, -np.inf], np.nan).fillna(0.0)
di_sum = (plus_di + minus_di).replace(0, np.nan)
dx = (100.0 * (plus_di - minus_di).abs() / di_sum).fillna(0.0)
adx = dx.ewm(alpha=1.0 / adx_period, adjust=False, min_periods=adx_period).mean().fillna(0.0)

# Kaufman's adaptive moving average is smooth in noise and accelerates in trends.
price_change = close.diff(trend_len).abs()
path_change = close.diff().abs().rolling(trend_len, min_periods=trend_len).sum()
efficiency_ratio = (price_change / path_change.replace(0, np.nan)).fillna(0.0).clip(0.0, 1.0)
fast_constant = 2.0 / (trend_fast + 1.0)
slow_constant = 2.0 / (trend_slow + 1.0)
smoothing_constant = (efficiency_ratio * (fast_constant - slow_constant) + slow_constant) ** 2
trend_raw = pd.Series(np.nan, index=df.index, dtype=float)
if n > 0:
    trend_raw.iloc[0] = close.iloc[0]
    for i in range(1, n):
        alpha_value = float(smoothing_constant.iloc[i])
        if alpha_value != alpha_value:
            alpha_value = slow_constant ** 2
        trend_raw.iloc[i] = trend_raw.iloc[i - 1] + alpha_value * (close.iloc[i] - trend_raw.iloc[i - 1])
trend_ma = trend_raw.ewm(span=trend_smooth, adjust=False).mean()

atr_safe = atr.replace(0, np.nan)
normalized_slope = ((trend_ma - trend_ma.shift(slope_lookback)) / (atr_safe * slope_lookback)).fillna(0.0)
ma_rising = trend_ma > trend_ma.shift(1)
ma_falling = trend_ma < trend_ma.shift(1)

structure_shift = max(2, structure_period // 2)
range_high = high.rolling(structure_period, min_periods=structure_period).max()
range_low = low.rolling(structure_period, min_periods=structure_period).min()
higher_high = range_high > range_high.shift(structure_shift)
higher_low = range_low > range_low.shift(structure_shift)
lower_high = range_high < range_high.shift(structure_shift)
lower_low = range_low < range_low.shift(structure_shift)
range_mid = (range_high + range_low) / 2.0
bull_structure_score = higher_high.astype(int) + higher_low.astype(int) + (close > range_mid).astype(int)
bear_structure_score = lower_high.astype(int) + lower_low.astype(int) + (close < range_mid).astype(int)
bull_structure = bull_structure_score >= 2
bear_structure = bear_structure_score >= 2

atr_pct = (atr_safe / close.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
atr_baseline = atr_pct.rolling(atr_period * 3, min_periods=atr_period).median()
atr_ratio = (atr_pct / atr_baseline.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(1.0)
atr_normal = (atr_ratio >= atr_min_ratio) & (atr_ratio <= atr_max_ratio)

ma_cross = ((close > trend_ma) & (close.shift(1) <= trend_ma.shift(1))) | (
    (close < trend_ma) & (close.shift(1) >= trend_ma.shift(1))
)
cross_count = ma_cross.astype(int).rolling(10, min_periods=1).sum()
bb_basis = close.rolling(bb_period, min_periods=bb_period).mean()
bb_std = close.rolling(bb_period, min_periods=bb_period).std(ddof=0)
bb_width = (4.0 * bb_std / bb_basis.replace(0, np.nan)).fillna(0.0)
distance_atr = ((close - trend_ma).abs() / atr_safe).replace([np.inf, -np.inf], np.nan).fillna(0.0)
around_ma = (distance_atr.rolling(10, min_periods=3).mean() < 0.45) & (cross_count >= 2)

low_adx = adx < adx_threshold
low_atr = atr_ratio < atr_min_ratio
flat_ma = normalized_slope.abs() < slope_threshold * 0.75
too_many_crosses = cross_count > cross_limit
narrow_band = (bb_width > 0) & (bb_width < bb_min_width)
sideways = low_adx | low_atr | flat_ma | too_many_crosses | narrow_band | around_ma

bull_trend = (
    ma_rising
    & (normalized_slope > slope_threshold)
    & bull_structure
    & (plus_di > minus_di)
    & (adx >= adx_threshold)
    & atr_normal
    & ~sideways
).fillna(False)
bear_trend = (
    ma_falling
    & (normalized_slope < -slope_threshold)
    & bear_structure
    & (minus_di > plus_di)
    & (adx >= adx_threshold)
    & atr_normal
    & ~sideways
).fillna(False)
recent_bull = bull_trend.astype(int).rolling(regime_memory, min_periods=1).max() > 0
recent_bear = bear_trend.astype(int).rolling(regime_memory, min_periods=1).max() > 0
bull_regime = (
    recent_bull
    & ~bear_trend
    & (trend_ma > trend_ma.shift(regime_memory))
    & (close >= trend_ma)
).fillna(False)
bear_regime = (
    recent_bear
    & ~bull_trend
    & (trend_ma < trend_ma.shift(regime_memory))
    & (close <= trend_ma)
).fillna(False)
two_closes_below_ma = ((close < trend_ma) & (close.shift(1) < trend_ma.shift(1))).fillna(False)
two_closes_above_ma = ((close > trend_ma) & (close.shift(1) > trend_ma.shift(1))).fillna(False)
lower_high_confirmed = lower_high.fillna(False)
higher_low_confirmed = higher_low.fillna(False)

long_breakout = ((close > trend_ma) & (previous_close <= trend_ma.shift(1))).fillna(False)
short_breakout = ((close < trend_ma) & (previous_close >= trend_ma.shift(1))).fillna(False)
volume_average = volume.rolling(volume_period, min_periods=volume_period).mean()
volume_expanded = (volume >= volume_average * volume_mult).fillna(False)

# Setup states: 1=breakout stabilization, 2=waiting first pullback, 3=waiting confirmation.
long_candidates = [False] * n
short_candidates = [False] * n
long_stage = 0
short_stage = 0
long_age = 0
short_age = 0
long_stable = 0
short_stable = 0
long_pullback_age = 0
short_pullback_age = 0
long_cycle_used = False
short_cycle_used = False
long_reset_bars = 0
short_reset_bars = 0
last_long_signal = -cooldown_period - 1
last_short_signal = -cooldown_period - 1

for i in range(n):
    current_atr = float(atr.iloc[i])
    if current_atr != current_atr or current_atr <= 0:
        current_atr = max(abs(float(close.iloc[i])) * 0.001, 1e-12)

    long_reset = bool(close.iloc[i] < trend_ma.iloc[i]) or bool(bear_trend.iloc[i])
    short_reset = bool(close.iloc[i] > trend_ma.iloc[i]) or bool(bull_trend.iloc[i])
    long_reset_bars = long_reset_bars + 1 if long_reset else 0
    short_reset_bars = short_reset_bars + 1 if short_reset else 0
    if long_reset_bars >= 2:
        long_cycle_used = False
        long_stage = 0
    if short_reset_bars >= 2:
        short_cycle_used = False
        short_stage = 0

    # A confirmed crossover arms the setup; the full trend filter is enforced at entry.
    # This avoids losing valid setups when ADX/slope confirmation arrives after the breakout bar.
    if bool(long_breakout.iloc[i]) and not long_cycle_used:
        long_stage = 1
        long_age = 0
        long_stable = 0
    elif long_stage > 0:
        long_age += 1
        if (long_age > max_setup_bars and long_stage != 3) or bool(bear_trend.iloc[i]):
            long_stage = 0
        elif long_stage == 1:
            if bool(close.iloc[i] > trend_ma.iloc[i]) and bool(ma_rising.iloc[i]):
                long_stable += 1
                if long_stable >= stand_bars:
                    long_stage = 2
            else:
                long_stage = 0
        elif long_stage == 2:
            wick_floor = trend_ma.iloc[i] - pullback_tolerance_atr * current_atr
            touched = low.iloc[i] <= trend_ma.iloc[i] + pullback_tolerance_atr * current_atr
            held = close.iloc[i] >= trend_ma.iloc[i] and low.iloc[i] >= wick_floor
            if bool(touched and held):
                long_stage = 3
                long_pullback_age = 0
        elif long_stage == 3:
            long_pullback_age += 1
            long_confirm = (
                i > 0
                and close.iloc[i] > open_price.iloc[i]
                and close.iloc[i] > close.iloc[i - 1]
                and bool(bull_regime.iloc[i])
                and bool(volume_expanded.iloc[i])
                and distance_atr.iloc[i] <= max_distance_atr
                and i - last_long_signal >= cooldown_period
            )
            if long_confirm:
                long_candidates[i] = True
                last_long_signal = i
                long_cycle_used = True
                long_stage = 0
                short_stage = 0
            elif long_pullback_age > pullback_bars or close.iloc[i] < trend_ma.iloc[i]:
                long_stage = 0

    if bool(short_breakout.iloc[i]) and not short_cycle_used:
        short_stage = 1
        short_age = 0
        short_stable = 0
    elif short_stage > 0:
        short_age += 1
        if (short_age > max_setup_bars and short_stage != 3) or bool(bull_trend.iloc[i]):
            short_stage = 0
        elif short_stage == 1:
            if bool(close.iloc[i] < trend_ma.iloc[i]) and bool(ma_falling.iloc[i]):
                short_stable += 1
                if short_stable >= stand_bars:
                    short_stage = 2
            else:
                short_stage = 0
        elif short_stage == 2:
            wick_ceiling = trend_ma.iloc[i] + pullback_tolerance_atr * current_atr
            touched = high.iloc[i] >= trend_ma.iloc[i] - pullback_tolerance_atr * current_atr
            held = close.iloc[i] <= trend_ma.iloc[i] and high.iloc[i] <= wick_ceiling
            if bool(touched and held):
                short_stage = 3
                short_pullback_age = 0
        elif short_stage == 3:
            short_pullback_age += 1
            short_confirm = (
                i > 0
                and close.iloc[i] < open_price.iloc[i]
                and close.iloc[i] < close.iloc[i - 1]
                and bool(bear_regime.iloc[i])
                and bool(volume_expanded.iloc[i])
                and distance_atr.iloc[i] <= max_distance_atr
                and i - last_short_signal >= cooldown_period
            )
            if short_confirm:
                short_candidates[i] = True
                last_short_signal = i
                short_cycle_used = True
                short_stage = 0
                long_stage = 0
            elif short_pullback_age > pullback_bars or close.iloc[i] > trend_ma.iloc[i]:
                short_stage = 0

# Position-aware, close-confirmed ATR exits. No future open/high/low is used.
open_long_values = [False] * n
close_long_values = [False] * n
open_short_values = [False] * n
close_short_values = [False] * n
reduce_long_values = [False] * n
reduce_short_values = [False] * n
reduce_size_values = [0.0] * n
position_size_values = [0.0] * n
position = 0
entry_anchor = 0.0
entry_atr = 0.0
best_close = 0.0
partial_taken = False

for i in range(n):
    current_close = float(close.iloc[i])
    current_atr = float(atr.iloc[i])
    if current_atr != current_atr or current_atr <= 0:
        current_atr = max(abs(current_close) * 0.001, 1e-12)

    exited_long = False
    exited_short = False

    if position == 1:
        best_close = max(best_close, current_close)
        initial_stop = entry_anchor - atr_stop_mult * entry_atr
        active_stop = initial_stop
        if best_close >= entry_anchor + breakeven_trigger_atr * entry_atr:
            active_stop = max(active_stop, entry_anchor)
        if best_close >= entry_anchor + trail_trigger_atr * entry_atr:
            active_stop = max(active_stop, best_close - atr_trail_mult * current_atr)

        if profit_mode in ("partial", "hybrid") and not partial_taken:
            if current_close >= entry_anchor + partial_trigger_atr * entry_atr:
                reduce_long_values[i] = True
                reduce_size_values[i] = partial_fraction
                partial_taken = True

        stop_exit = current_close <= active_stop
        fixed_exit = profit_mode in ("fixed", "hybrid") and current_close >= entry_anchor + take_profit_atr * entry_atr
        final_partial_exit = profit_mode == "partial" and current_close >= entry_anchor + take_profit_atr * entry_atr
        trend_exit = (
            bool(bear_trend.iloc[i])
            or bool(two_closes_below_ma.iloc[i])
            or bool(ma_falling.iloc[i] and normalized_slope.iloc[i] <= 0 and close.iloc[i] < trend_ma.iloc[i])
            or bool(lower_high_confirmed.iloc[i] and close.iloc[i] < trend_ma.iloc[i])
        )
        if stop_exit or fixed_exit or final_partial_exit or trend_exit or short_candidates[i]:
            close_long_values[i] = True
            exited_long = True
            position = 0

    elif position == -1:
        best_close = min(best_close, current_close)
        initial_stop = entry_anchor + atr_stop_mult * entry_atr
        active_stop = initial_stop
        if best_close <= entry_anchor - breakeven_trigger_atr * entry_atr:
            active_stop = min(active_stop, entry_anchor)
        if best_close <= entry_anchor - trail_trigger_atr * entry_atr:
            active_stop = min(active_stop, best_close + atr_trail_mult * current_atr)

        if profit_mode in ("partial", "hybrid") and not partial_taken:
            if current_close <= entry_anchor - partial_trigger_atr * entry_atr:
                reduce_short_values[i] = True
                reduce_size_values[i] = partial_fraction
                partial_taken = True

        stop_exit = current_close >= active_stop
        fixed_exit = profit_mode in ("fixed", "hybrid") and current_close <= entry_anchor - take_profit_atr * entry_atr
        final_partial_exit = profit_mode == "partial" and current_close <= entry_anchor - take_profit_atr * entry_atr
        trend_exit = (
            bool(bull_trend.iloc[i])
            or bool(two_closes_above_ma.iloc[i])
            or bool(ma_rising.iloc[i] and normalized_slope.iloc[i] >= 0 and close.iloc[i] > trend_ma.iloc[i])
            or bool(higher_low_confirmed.iloc[i] and close.iloc[i] > trend_ma.iloc[i])
        )
        if stop_exit or fixed_exit or final_partial_exit or trend_exit or long_candidates[i]:
            close_short_values[i] = True
            exited_short = True
            position = 0

    if position == 0:
        open_long_now = long_candidates[i] and not exited_long
        open_short_now = short_candidates[i] and not exited_short
        if open_long_now and not open_short_now:
            open_long_values[i] = True
            position = 1
        elif open_short_now:
            open_short_values[i] = True
            position = -1

        if position != 0:
            entry_anchor = current_close
            entry_atr = current_atr
            best_close = current_close
            partial_taken = False
            stop_fraction = atr_stop_mult * current_atr / max(abs(current_close), 1e-12)
            atr_position_pct = risk_pct / max(stop_fraction, 1e-12)
            atr_position_pct = min(max_position_pct, max(0.01, atr_position_pct))
            if position_mode == "percent":
                selected_position_pct = min(max_position_pct, percent_position_pct)
            elif position_mode == "fixed":
                selected_position_pct = min(max_position_pct, fixed_position_pct)
            else:
                selected_position_pct = atr_position_pct
            position_size_values[i] = selected_position_pct

df["open_long"] = edge(pd.Series(open_long_values, index=df.index))
df["close_long"] = edge(pd.Series(close_long_values, index=df.index))
df["open_short"] = edge(pd.Series(open_short_values, index=df.index))
df["close_short"] = edge(pd.Series(close_short_values, index=df.index))

# Optional position-management columns are consumed by engines that support sizing/scale-out.
false_series = pd.Series(False, index=df.index, dtype=bool)
df["add_long"] = false_series.copy()
df["add_short"] = false_series.copy()
df["reduce_long"] = edge(pd.Series(reduce_long_values, index=df.index))
df["reduce_short"] = edge(pd.Series(reduce_short_values, index=df.index))
df["reduce_size"] = pd.Series(reduce_size_values, index=df.index, dtype=float)
df["position_size"] = pd.Series(position_size_values, index=df.index, dtype=float)

atr_for_marks = atr.fillna(0.0)
buy_marks = [
    float(low.iloc[i] - 0.25 * atr_for_marks.iloc[i]) if bool(df["open_long"].iloc[i]) else None
    for i in range(n)
]
sell_marks = [
    float(high.iloc[i] + 0.25 * atr_for_marks.iloc[i]) if bool(df["open_short"].iloc[i]) else None
    for i in range(n)
]

output = {
    "name": my_indicator_name,
    "plots": [
        {
            "name": "TrendMA",
            "type": "line",
            "data": trend_ma.fillna(close).tolist(),
            "color": "#FACC15",
            "overlay": True,
        },
        {
            "name": "ADX",
            "type": "line",
            "data": adx.fillna(0.0).tolist(),
            "color": "#38BDF8",
            "overlay": False,
        },
    ],
    "signals": [
        {"type": "buy", "text": "多", "data": buy_marks, "color": "#22C55E"},
        {"type": "sell", "text": "空", "data": sell_marks, "color": "#EF4444"},
    ],
    "layers": [],
}

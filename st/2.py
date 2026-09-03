# --- QuantDinger execution contract (v1) ---
# signal_form: four_way
# exit_owner: indicator
# flip_mode: R1

my_indicator_name = "1H/15M 趋势回踩突破策略"
my_indicator_description = "1小时与输入周期EMA同向，MACD/KDJ确认后等待回踩，再以放量突破入场；15分钟输入可精确执行原多周期规则。"

# @strategy stopLossPct 0
# @strategy takeProfitPct 0
# @strategy entryPct 0.5
# @strategy trailingEnabled false
# @strategy tradeDirection both

# @param ema_fast int 20 EMA快线周期
# @param ema_slow int 60 EMA慢线周期
# @param macd_fast int 12 MACD快线周期
# @param macd_slow int 26 MACD慢线周期
# @param macd_signal int 9 MACD信号线周期
# @param kdj_period int 9 KDJ周期
# @param boll_period int 20 布林带周期
# @param boll_std float 2.0 布林带标准差倍数
# @param volume_period int 20 成交量均线周期
# @param volume_multiple float 1.5 放量倍数
# @param breakout_lookback int 20 前高前低回看周期
# @param structure_lookback int 10 止损结构回看周期
# @param atr_period int 14 ATR周期
# @param stop_buffer_atr float 0.2 结构止损ATR缓冲
# @param account_risk_pct float 0.01 单笔账户风险上限
# @param setup_expiry int 12 回踩确认有效K线数
# @param cross_window int 16 交叉确认有效K线数
# @param cooldown_bars int 4 平仓后冷却K线数
# @param ema_separation_pct float 0.001 EMA最小间距比例
# @param min_bandwidth_pct float 0.006 布林带最小宽度比例

# 仓位扩展列 add_*/reduce_* 当前由实盘执行器读取；指标回测仅提取四路主信号。
# 账户风险1%按1倍杠杆约束：50%初始仓位只接受止损距离不超过2%的机会。
# 重大消息过滤需要外部日历数据，OHLCV指标本身不具备该信息，上线时应在执行层暂停。
# 选择1H K线时无法从OHLCV还原真实15分钟结构，脚本以当前1H作为入场周期兼容运行；精确模式请选择15m。


def recent_true(signal, window):
    return signal.fillna(False).astype(int).rolling(window=window, min_periods=1).max().astype(bool)


ema_fast_period = max(2, int(params.get("ema_fast", 20)))
ema_slow_period = max(ema_fast_period + 1, int(params.get("ema_slow", 60)))
macd_fast_period = max(2, int(params.get("macd_fast", 12)))
macd_slow_period = max(macd_fast_period + 1, int(params.get("macd_slow", 26)))
macd_signal_period = max(2, int(params.get("macd_signal", 9)))
kdj_period = max(3, int(params.get("kdj_period", 9)))
boll_period = max(5, int(params.get("boll_period", 20)))
boll_std = max(0.1, float(params.get("boll_std", 2.0)))
volume_period = max(2, int(params.get("volume_period", 20)))
volume_multiple = max(1.0, float(params.get("volume_multiple", 1.5)))
breakout_lookback = max(3, int(params.get("breakout_lookback", 20)))
structure_lookback = max(3, int(params.get("structure_lookback", 10)))
atr_period = max(2, int(params.get("atr_period", 14)))
stop_buffer_atr = max(0.0, float(params.get("stop_buffer_atr", 0.2)))
account_risk_pct = min(0.05, max(0.001, float(params.get("account_risk_pct", 0.01))))
setup_expiry = max(1, int(params.get("setup_expiry", 12)))
cross_window = max(1, int(params.get("cross_window", 16)))
cooldown_bars = max(0, int(params.get("cooldown_bars", 4)))
ema_separation_pct = max(0.0, float(params.get("ema_separation_pct", 0.001)))
min_bandwidth_pct = max(0.0, float(params.get("min_bandwidth_pct", 0.006)))

df = df.copy()

open_price = pd.to_numeric(df["open"], errors="coerce")
high = pd.to_numeric(df["high"], errors="coerce")
low = pd.to_numeric(df["low"], errors="coerce")
close = pd.to_numeric(df["close"], errors="coerce")
volume = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)

# QuantDinger K线时间是开盘时间；低周期输入只在完整小时收盘后更新1H EMA。
time_source = df["time"]
first_time = time_source.iloc[0] if len(df) else 0
if hasattr(first_time, "timestamp"):
    bar_time = pd.to_datetime(time_source, errors="coerce", utc=True)
else:
    first_numeric_time = float(first_time or 0)
    time_unit = "ms" if abs(first_numeric_time) > 100000000000 else "s"
    bar_time = pd.to_datetime(time_source, unit=time_unit, errors="coerce", utc=True)
if len(df) > 1 and not pd.isna(bar_time.iloc[0]) and not pd.isna(bar_time.iloc[1]):
    input_minutes = max(1, int(round((bar_time.iloc[1] - bar_time.iloc[0]).total_seconds() / 60.0)))
else:
    input_minutes = 15

if input_minutes >= 60:
    ema_1h_fast = close.ewm(span=ema_fast_period, adjust=False).mean()
    ema_1h_slow = close.ewm(span=ema_slow_period, adjust=False).mean()
else:
    bar_end_time = bar_time + pd.to_timedelta(input_minutes, unit="m")
    hour_complete = bar_end_time.dt.minute.eq(0)
    hour_close_sparse = close.where(hour_complete).dropna()
    ema_1h_fast_sparse = hour_close_sparse.ewm(span=ema_fast_period, adjust=False).mean()
    ema_1h_slow_sparse = hour_close_sparse.ewm(span=ema_slow_period, adjust=False).mean()
    ema_1h_fast = ema_1h_fast_sparse.reindex(df.index).ffill()
    ema_1h_slow = ema_1h_slow_sparse.reindex(df.index).ffill()

input_timeframe_label = "15M" if input_minutes == 15 else ("1H" if input_minutes == 60 else f"{input_minutes}M")

ema_15m_fast = close.ewm(span=ema_fast_period, adjust=False).mean()
ema_15m_slow = close.ewm(span=ema_slow_period, adjust=False).mean()

macd_fast_line = close.ewm(span=macd_fast_period, adjust=False).mean()
macd_slow_line = close.ewm(span=macd_slow_period, adjust=False).mean()
macd_line = macd_fast_line - macd_slow_line
macd_signal_line = macd_line.ewm(span=macd_signal_period, adjust=False).mean()
macd_hist = macd_line - macd_signal_line
macd_golden = (macd_line > macd_signal_line) & (macd_line.shift(1) <= macd_signal_line.shift(1))
macd_death = (macd_line < macd_signal_line) & (macd_line.shift(1) >= macd_signal_line.shift(1))
macd_recent_golden = recent_true(macd_golden, cross_window) & (macd_line > macd_signal_line)
macd_recent_death = recent_true(macd_death, cross_window) & (macd_line < macd_signal_line)
macd_growing_long = (macd_hist > 0) & (macd_hist > macd_hist.shift(1)) & (macd_hist.shift(1) > macd_hist.shift(2))
macd_growing_short = (macd_hist < 0) & (macd_hist < macd_hist.shift(1)) & (macd_hist.shift(1) < macd_hist.shift(2))

rolling_low = low.rolling(window=kdj_period, min_periods=kdj_period).min()
rolling_high = high.rolling(window=kdj_period, min_periods=kdj_period).max()
price_range = (rolling_high - rolling_low).replace(0, np.nan)
rsv = ((close - rolling_low) / price_range * 100.0).fillna(50.0)
kdj_k = rsv.ewm(alpha=1.0 / 3.0, adjust=False).mean()
kdj_d = kdj_k.ewm(alpha=1.0 / 3.0, adjust=False).mean()
kdj_j = 3.0 * kdj_k - 2.0 * kdj_d
kdj_golden = (kdj_k > kdj_d) & (kdj_k.shift(1) <= kdj_d.shift(1))
kdj_death = (kdj_k < kdj_d) & (kdj_k.shift(1) >= kdj_d.shift(1))
kdj_valid_golden = kdj_golden & (kdj_j <= 80.0)
kdj_valid_death = kdj_death & (kdj_j >= 20.0)
kdj_recent_golden = recent_true(kdj_valid_golden, cross_window) & (kdj_k > kdj_d)
kdj_recent_death = recent_true(kdj_valid_death, cross_window) & (kdj_k < kdj_d)

boll_mid = close.rolling(window=boll_period, min_periods=boll_period).mean()
boll_dev = close.rolling(window=boll_period, min_periods=boll_period).std(ddof=0)
boll_upper = boll_mid + boll_std * boll_dev
boll_lower = boll_mid - boll_std * boll_dev
bandwidth = ((boll_upper - boll_lower) / boll_mid.replace(0, np.nan)).fillna(0.0)

previous_close = close.shift(1)
true_range = pd.concat(
    [
        high - low,
        (high - previous_close).abs(),
        (low - previous_close).abs(),
    ],
    axis=1,
).max(axis=1)
atr = true_range.rolling(window=atr_period, min_periods=atr_period).mean()

previous_high = high.rolling(window=breakout_lookback, min_periods=breakout_lookback).max().shift(1)
previous_low = low.rolling(window=breakout_lookback, min_periods=breakout_lookback).min().shift(1)
support = low.rolling(window=structure_lookback, min_periods=structure_lookback).min().shift(1)
resistance = high.rolling(window=structure_lookback, min_periods=structure_lookback).max().shift(1)
volume_average = volume.rolling(window=volume_period, min_periods=volume_period).mean()

body = (close - open_price).abs()
candle_range = (high - low).replace(0, np.nan)
upper_shadow = high - pd.concat([open_price, close], axis=1).max(axis=1)
lower_shadow = pd.concat([open_price, close], axis=1).min(axis=1) - low
bullish = close > open_price
bearish = close < open_price
bullish_engulfing = bullish & (close.shift(1) < open_price.shift(1)) & (open_price <= close.shift(1)) & (close >= open_price.shift(1))
bearish_engulfing = bearish & (close.shift(1) > open_price.shift(1)) & (open_price >= close.shift(1)) & (close <= open_price.shift(1))
hammer = bullish & (lower_shadow >= body * 2.0) & (upper_shadow <= body * 1.2)
shooting_star = bearish & (upper_shadow >= body * 2.0) & (lower_shadow <= body * 1.2)
two_bullish = bullish & bullish.shift(1).fillna(False)
two_bearish = bearish & bearish.shift(1).fillna(False)
bullish_confirmation = bullish & (bullish_engulfing | hammer | two_bullish | (body / candle_range >= 0.35))
bearish_confirmation = bearish & (bearish_engulfing | shooting_star | two_bearish | (body / candle_range >= 0.35))

trend_1h_long = ema_1h_fast > ema_1h_slow
trend_1h_short = ema_1h_fast < ema_1h_slow
trend_15m_long = ema_15m_fast > ema_15m_slow
trend_15m_short = ema_15m_fast < ema_15m_slow
ema_gap = ((ema_15m_fast - ema_15m_slow).abs() / close.replace(0, np.nan)).fillna(0.0)
ema_tangled = ema_gap < ema_separation_pct
band_contracted = bandwidth < min_bandwidth_pct
kdj_near_middle = kdj_k.between(42.0, 58.0) & kdj_d.between(42.0, 58.0)
kdj_crosses = (kdj_golden | kdj_death).astype(int).rolling(window=8, min_periods=1).sum()
kdj_choppy = kdj_near_middle & (kdj_crosses >= 3)
double_long_wicks = ((upper_shadow > body * 1.2) & (lower_shadow > body * 1.2)).astype(int).rolling(window=2, min_periods=2).sum() >= 2
tradeable = ~(ema_tangled | band_contracted | kdj_choppy | double_long_wicks)

touch_long = ((low <= ema_15m_fast) & (close >= ema_15m_fast)) | ((low <= boll_mid) & (close >= boll_mid))
touch_short = ((high >= ema_15m_fast) & (close <= ema_15m_fast)) | ((high >= boll_mid) & (close <= boll_mid))
pullback_long = trend_1h_long & trend_15m_long & touch_long & bullish_confirmation & tradeable
pullback_short = trend_1h_short & trend_15m_short & touch_short & bearish_confirmation & tradeable

momentum_long = macd_recent_golden & macd_growing_long & kdj_recent_golden
momentum_short = macd_recent_death & macd_growing_short & kdj_recent_death
breakout_long = (close > previous_high) & (volume > volume_average * volume_multiple)
breakout_short = (close < previous_low) & (volume > volume_average * volume_multiple)

n = len(df)
open_long_values = [False] * n
close_long_values = [False] * n
open_short_values = [False] * n
close_short_values = [False] * n
add_long_values = [False] * n
add_short_values = [False] * n
reduce_long_values = [False] * n
reduce_short_values = [False] * n
position_size_values = [0.0] * n
reduce_size_values = [0.0] * n
stop_line_values = [None] * n

position = 0
entry_price = 0.0
stop_price = 0.0
entry_breakout_level = 0.0
entry_bar = -1
first_add_done = False
second_add_done = False
first_target_done = False
long_setup_age = -1
short_setup_age = -1
cooldown = 0
consecutive_losses = 0
current_day = ""
max_stop_distance_pct = account_risk_pct / 0.5

for i in range(n):
    day_value = bar_time.iloc[i].strftime("%Y-%m-%d") if not pd.isna(bar_time.iloc[i]) else ""
    if day_value != current_day:
        current_day = day_value
        consecutive_losses = 0

    if cooldown > 0:
        cooldown -= 1

    if bool(pullback_long.iloc[i]):
        long_setup_age = 0
    elif long_setup_age >= 0:
        long_setup_age += 1
        if long_setup_age > setup_expiry or not bool(trend_15m_long.iloc[i]):
            long_setup_age = -1

    if bool(pullback_short.iloc[i]):
        short_setup_age = 0
    elif short_setup_age >= 0:
        short_setup_age += 1
        if short_setup_age > setup_expiry or not bool(trend_15m_short.iloc[i]):
            short_setup_age = -1

    current_close = float(close.iloc[i]) if not pd.isna(close.iloc[i]) else 0.0
    current_atr = float(atr.iloc[i]) if not pd.isna(atr.iloc[i]) else 0.0

    if position == 1:
        stop_line_values[i] = stop_price
        stop_hit = current_close <= stop_price
        reverse_momentum = bool(macd_death.iloc[i])
        bearish_reversal = bool(bearish_engulfing.iloc[i] | shooting_star.iloc[i])
        trailing_exit = first_target_done and (current_close < float(ema_15m_fast.iloc[i]) or reverse_momentum or bearish_reversal)
        trend_failed = (not bool(trend_15m_long.iloc[i])) and reverse_momentum

        if stop_hit or trailing_exit or trend_failed:
            close_long_values[i] = True
            if current_close < entry_price:
                consecutive_losses += 1
            else:
                consecutive_losses = 0
            position = 0
            cooldown = cooldown_bars
            long_setup_age = -1
            short_setup_age = -1
            continue

        risk_per_unit = entry_price - stop_price
        first_target = entry_price + 2.0 * risk_per_unit
        if (not first_target_done) and risk_per_unit > 0 and current_close >= first_target:
            reduce_long_values[i] = True
            reduce_size_values[i] = 0.5
            first_target_done = True
            continue

        held_bars = i - entry_bar
        stood_above_breakout = current_close > entry_breakout_level and float(previous_close.iloc[i]) > entry_breakout_level
        profitable = current_close > entry_price
        if (not first_add_done) and held_bars >= 2 and stood_above_breakout and profitable and bool(momentum_long.iloc[i]):
            add_long_values[i] = True
            position_size_values[i] = 0.3
            first_add_done = True
            continue
        continuation_level = float(previous_high.iloc[i]) if not pd.isna(previous_high.iloc[i]) else 0.0
        if first_add_done and (not second_add_done) and profitable and current_close > continuation_level and bool(macd_growing_long.iloc[i]):
            add_long_values[i] = True
            position_size_values[i] = 0.2
            second_add_done = True
            continue

    elif position == -1:
        stop_line_values[i] = stop_price
        stop_hit = current_close >= stop_price
        reverse_momentum = bool(macd_golden.iloc[i])
        bullish_reversal = bool(bullish_engulfing.iloc[i] | hammer.iloc[i])
        trailing_exit = first_target_done and (current_close > float(ema_15m_fast.iloc[i]) or reverse_momentum or bullish_reversal)
        trend_failed = (not bool(trend_15m_short.iloc[i])) and reverse_momentum

        if stop_hit or trailing_exit or trend_failed:
            close_short_values[i] = True
            if current_close > entry_price:
                consecutive_losses += 1
            else:
                consecutive_losses = 0
            position = 0
            cooldown = cooldown_bars
            long_setup_age = -1
            short_setup_age = -1
            continue

        risk_per_unit = stop_price - entry_price
        first_target = entry_price - 2.0 * risk_per_unit
        if (not first_target_done) and risk_per_unit > 0 and current_close <= first_target:
            reduce_short_values[i] = True
            reduce_size_values[i] = 0.5
            first_target_done = True
            continue

        held_bars = i - entry_bar
        stood_below_breakout = current_close < entry_breakout_level and float(previous_close.iloc[i]) < entry_breakout_level
        profitable = current_close < entry_price
        if (not first_add_done) and held_bars >= 2 and stood_below_breakout and profitable and bool(momentum_short.iloc[i]):
            add_short_values[i] = True
            position_size_values[i] = 0.3
            first_add_done = True
            continue
        continuation_level = float(previous_low.iloc[i]) if not pd.isna(previous_low.iloc[i]) else 0.0
        if first_add_done and (not second_add_done) and profitable and current_close < continuation_level and bool(macd_growing_short.iloc[i]):
            add_short_values[i] = True
            position_size_values[i] = 0.2
            second_add_done = True
            continue

    if position == 0 and cooldown == 0 and consecutive_losses < 3 and current_close > 0 and current_atr > 0:
        if long_setup_age >= 0 and bool(breakout_long.iloc[i] & momentum_long.iloc[i] & trend_1h_long.iloc[i] & trend_15m_long.iloc[i] & tradeable.iloc[i]):
            candidate_stop = float(support.iloc[i]) - current_atr * stop_buffer_atr
            stop_distance_pct = (current_close - candidate_stop) / current_close
            if candidate_stop > 0 and 0 < stop_distance_pct <= max_stop_distance_pct:
                open_long_values[i] = True
                position_size_values[i] = 0.5
                position = 1
                entry_price = current_close
                stop_price = candidate_stop
                entry_breakout_level = float(previous_high.iloc[i])
                entry_bar = i
                first_add_done = False
                second_add_done = False
                first_target_done = False
                long_setup_age = -1
                short_setup_age = -1
                stop_line_values[i] = stop_price
                continue

        if short_setup_age >= 0 and bool(breakout_short.iloc[i] & momentum_short.iloc[i] & trend_1h_short.iloc[i] & trend_15m_short.iloc[i] & tradeable.iloc[i]):
            candidate_stop = float(resistance.iloc[i]) + current_atr * stop_buffer_atr
            stop_distance_pct = (candidate_stop - current_close) / current_close
            if candidate_stop > current_close and 0 < stop_distance_pct <= max_stop_distance_pct:
                open_short_values[i] = True
                position_size_values[i] = 0.5
                position = -1
                entry_price = current_close
                stop_price = candidate_stop
                entry_breakout_level = float(previous_low.iloc[i])
                entry_bar = i
                first_add_done = False
                second_add_done = False
                first_target_done = False
                long_setup_age = -1
                short_setup_age = -1
                stop_line_values[i] = stop_price

df["open_long"] = pd.Series(open_long_values, index=df.index, dtype=bool)
df["close_long"] = pd.Series(close_long_values, index=df.index, dtype=bool)
df["open_short"] = pd.Series(open_short_values, index=df.index, dtype=bool)
df["close_short"] = pd.Series(close_short_values, index=df.index, dtype=bool)
df["add_long"] = pd.Series(add_long_values, index=df.index, dtype=bool)
df["add_short"] = pd.Series(add_short_values, index=df.index, dtype=bool)
df["reduce_long"] = pd.Series(reduce_long_values, index=df.index, dtype=bool)
df["reduce_short"] = pd.Series(reduce_short_values, index=df.index, dtype=bool)
df["position_size"] = pd.Series(position_size_values, index=df.index, dtype=float)
df["reduce_size"] = pd.Series(reduce_size_values, index=df.index, dtype=float)

open_long_marks = [float(low.iloc[i]) * 0.995 if open_long_values[i] else None for i in range(n)]
open_short_marks = [float(high.iloc[i]) * 1.005 if open_short_values[i] else None for i in range(n)]
add_long_marks = [float(low.iloc[i]) * 0.997 if add_long_values[i] else None for i in range(n)]
add_short_marks = [float(high.iloc[i]) * 1.003 if add_short_values[i] else None for i in range(n)]
reduce_long_marks = [float(high.iloc[i]) * 1.002 if reduce_long_values[i] else None for i in range(n)]
reduce_short_marks = [float(low.iloc[i]) * 0.998 if reduce_short_values[i] else None for i in range(n)]
close_long_marks = [float(high.iloc[i]) * 1.005 if close_long_values[i] else None for i in range(n)]
close_short_marks = [float(low.iloc[i]) * 0.995 if close_short_values[i] else None for i in range(n)]

output = {
    "name": my_indicator_name,
    "plots": [
        {"name": f"{input_timeframe_label} EMA{ema_fast_period}", "data": ema_15m_fast.fillna(0.0).tolist(), "color": "#FF9800", "overlay": True},
        {"name": f"{input_timeframe_label} EMA{ema_slow_period}", "data": ema_15m_slow.fillna(0.0).tolist(), "color": "#1565C0", "overlay": True},
        {"name": f"1H EMA{ema_fast_period}", "data": ema_1h_fast.fillna(0.0).tolist(), "color": "#FDD835", "overlay": True},
        {"name": f"1H EMA{ema_slow_period}", "data": ema_1h_slow.fillna(0.0).tolist(), "color": "#5E35B1", "overlay": True},
        {"name": "BOLL Upper", "data": boll_upper.fillna(0.0).tolist(), "color": "#90A4AE", "overlay": True},
        {"name": "BOLL Mid", "data": boll_mid.fillna(0.0).tolist(), "color": "#546E7A", "overlay": True},
        {"name": "BOLL Lower", "data": boll_lower.fillna(0.0).tolist(), "color": "#90A4AE", "overlay": True},
        {"name": "Structure Stop", "data": stop_line_values, "color": "#D32F2F", "overlay": True},
        {"name": "MACD Histogram", "data": macd_hist.fillna(0.0).tolist(), "color": "#00897B", "overlay": False},
        {"name": "KDJ J", "data": kdj_j.fillna(50.0).tolist(), "color": "#8E24AA", "overlay": False},
    ],
    "signals": [
        {"type": "buy", "text": "L", "data": open_long_marks, "color": "#00C853"},
        {"type": "sell", "text": "S", "data": open_short_marks, "color": "#D50000"},
        {"type": "buy", "text": "+L", "data": add_long_marks, "color": "#64DD17"},
        {"type": "sell", "text": "+S", "data": add_short_marks, "color": "#FF6D00"},
        {"type": "sell", "text": "1/2L", "data": reduce_long_marks, "color": "#FFD600"},
        {"type": "buy", "text": "1/2S", "data": reduce_short_marks, "color": "#FFD600"},
        {"type": "sell", "text": "XL", "data": close_long_marks, "color": "#AA00FF"},
        {"type": "buy", "text": "XS", "data": close_short_marks, "color": "#AA00FF"},
    ],
}

---
name: quantdinger-indicator-strategy
description: Use when writing, generating, repairing, or validating QuantDinger Indicator IDE Python strategy indicators, including requests such as "写策略指标", "生成指标代码", strategy-ide indicator code, four-way signals, or converting a requirements .md file into a runnable .py indicator. Do not use for ScriptStrategy/on_bar, grid bots, or unrelated Python trading systems.
---

# QuantDinger Indicator Strategy

Generate production-ready QuantDinger Indicator IDE strategy code from user requirements, run it through the repository's real sandbox, inspect signal behavior, and repair it before returning the final file.

## Scope

- Use for Indicator IDE Python executed against `df` and producing chart `output` plus DataFrame execution columns.
- Do not silently convert the request to `ScriptStrategy`, `on_bar`, a grid bot, Pine Script, or a standalone backtester.
- If the requested behavior fundamentally requires order callbacks, exchange state, or unsupported partial-order semantics, inspect current engine support and explain the boundary before choosing another strategy type.

## Canonical Sources

Read the current repository implementation before generating code. These files override remembered conventions:

1. `backend_api_python/app/routes/indicator.py`: AI system prompt and generation/repair policy.
2. `backend_api_python/app/services/indicator_validation.py`: executable validation contract.
3. `backend_api_python/app/services/indicator_code_quality.py`: static quality hints.
4. `backend_api_python/app/utils/safe_exec.py`: sandbox restrictions.
5. `docs/SIGNAL_EXECUTION_STANDARD_CN.md`: signal timing, four-way execution, exit ownership, and flip semantics.
6. `backend_api_python/app/services/backtest.py` and `trading_executor.py`: inspect these before using optional sizing, add, reduce, or partial-exit columns.

Do not copy a previous strategy's trading logic unless the user explicitly asks for it. Reuse the platform contract and workflow, not the prior algorithm.

## Input And Output

- Treat the user-provided text or requirements file as the strategy specification.
- If the user identifies `path/N.md` and asks for generated code without naming a target, write `path/N.py`.
- Preserve only final requested artifacts. Remove temporary test harnesses and generated caches.
- Return a complete replacement script, not a fragment or prose embedded in the Python file.

## Generation Workflow

1. Extract hard requirements, prohibited techniques, parameters, chart appearance, signal timing, exits, and position sizing.
2. Resolve contradictions against current platform capabilities. Never pretend an unsupported execution feature works.
3. Select and declare exactly one contract:
   - `# signal_form: four_way`
   - `# exit_owner: engine` or `# exit_owner: indicator`
   - `# flip_mode: R1` or `# flip_mode: R2`
4. Select exit ownership consistently:
   - Use `indicator` for ATR/channel/in-code trailing, breakeven, or touch/close-based risk exits. Set `trailingEnabled false` and disable engine price exits.
   - Use `engine` for engine-managed fixed stop, take profit, or trailing. Do not duplicate narrow TP/SL logic in `close_*`.
5. Implement indicator math vectorized with pandas. Use a single forward state-machine loop only where sequence state is real, such as first pullback, cooldown, position state, trailing stops, or partial exits.
6. Precompute Series used inside loops. Do not call whole-Series operations such as `.shift()`, `.fillna()`, or `.rolling()` on every iteration.
7. Produce chart plots and sparse markers that match the request.
8. Run validation, inspect every hint, add targeted scenarios, repair, and repeat until the code passes.

## Mandatory Code Contract

- Define `my_indicator_name` and `my_indicator_description`.
- Perform `df = df.copy()` before mutating input data.
- Assume `pd`, `np`, `df`, and `params` are injected. Do not import pandas/numpy or perform I/O/network/process operations.
- Read every declared `# @param` through `params.get`; its fallback must exactly equal the declared default before runtime clamping or normalization.
- Assign boolean, index-aligned `df['open_long']`, `df['close_long']`, `df['open_short']`, and `df['close_short']` columns.
- Make execution signals isolated/edge-triggered. Signals are confirmed at bar close and filled by the engine at the next bar open.
- Never use negative shifts, future rows, centered rolling windows, full-sample extrema for historical decisions, or any other lookahead.
- Build `output` with `name`, `plots`, and `signals`. Every plot/signal data list must have exactly `len(df)` items.
- Marker lists must contain explicit `None` or price values; avoid `.where(mask, None).tolist()`.
- Any ndarray converted to Series must use `index=df.index`.
- Audit every `.rolling`, `.fillna`, `.shift`, `.ewm`, `.iloc`, and `.tolist` receiver to ensure it is a pandas object, not an ndarray.

## Strategy Design Standard

- Combine independent evidence rather than renaming one crossover as a professional strategy.
- Separate regime detection, setup, confirmation, execution, and exit logic.
- Entry state machines must have explicit invalidation, expiry, cooldown, and one-signal-per-cycle behavior where requested.
- All decisions must be reproducible from the prefix ending at that bar. A longer DataFrame must not alter earlier signals.
- Parameterize user-requested controls, but avoid decorative parameters that do not affect behavior.
- For ATR risk sizing, derive `position_size` from risk fraction divided by stop distance and cap it to platform-valid bounds. Verify current backtest/live consumers before depending on optional columns.
- If partial exits are requested, verify both backtest and live handling of `reduce_long`, `reduce_short`, and sizing columns. Report any semantic mismatch instead of hiding it.

## Validation And Repair

Run the reusable validator from the repository root:

```bash
python .cursor/skills/quantdinger-indicator-strategy/scripts/validate_indicator.py path/to/strategy.py
```

Use the backend/container Python environment with numpy and pandas installed. If the active interpreter lacks them, select an existing project environment or create an isolated temporary environment; do not modify project dependency manifests just to run this helper.

Useful options:

```bash
python .cursor/skills/quantdinger-indicator-strategy/scripts/validate_indicator.py path/to/strategy.py --stress-bars 5000 --require-entry
```

The validator performs:

- Repository static quality analysis and safety AST validation.
- Execution in the same safe sandbox used by `validate_indicator_code`.
- Output shape and four-way execution-column checks.
- A longer DatetimeIndex stress run.
- Trend/sideways scenario signal counts.
- Prefix-versus-full-history signal equality to detect historical drift.

Then add strategy-specific scenarios derived from the user's requirements. Generic random data is not enough. For example, explicitly construct breakout, valid pullback, invalid pullback, low-ADX chop, high-volatility shock, reversal, stop, trailing, and cooldown cases when those features exist.

## Strategy IDE Real Backtest Acceptance

When the user gives Strategy IDE backtest settings, the exact page-equivalent run is mandatory acceptance, not an optional example. Generic random or synthetic validation cannot replace it.

1. Trace the current frontend implementation before testing:
   - Read `runBacktest`, date-preset handling, default/restored symbol, timeframe values, `strategyConfigFromCode`, and strict-mode state in `vue/src/views/indicator-ide/index.vue`.
   - Use the current editor source as `indicatorCode`; saving the indicator is not required by the endpoint.
   - Treat presets according to code, not labels. For example, verify whether `1M` currently means a fixed 30 days or a calendar month.
   - If the symbol or another material control is not specified and current UI state is inaccessible, state the assumption explicitly. Do not silently claim it matches the user's screen.
2. Reproduce every material request field: symbol, market, date range, timeframe, trade direction, strict mode, initial capital, commission, slippage, leverage, market type, parsed strategy annotations, exit owner, and execution timing.
3. Include the backend-estimated indicator warmup before the requested start. Execute indicators on warmup plus requested data, then slice signals and trading to the requested window exactly as `BacktestService.run` does.
4. Prefer the running authenticated `POST /api/indicator/backtest` endpoint with `persist: false` during iteration. Keep tokens out of commands, logs, diffs, and reports.
5. If the app is not running:
   - Confirm why the UI path is unavailable instead of pretending to click it.
   - Fetch candles from the project's configured data source and venue.
   - Execute code with the repository safe sandbox and the same index reset/parameter merge as `_execute_indicator`.
   - Pass the resulting four-way signals to the repository's actual `BacktestService._simulate_trading`; do not substitute a hand-written simulator for final metrics.
6. Capture both layers of evidence:
   - Raw requested-window counts for `open_long`, `close_long`, `open_short`, and `close_short`.
   - `signalDiagnostics`, all trade events, `totalTrades`, return, win rate, drawdown, actual data range, and execution assumptions when available.
   - Remember that `totalTrades` counts completed profit/loss records and may differ from `len(trades)`. A zero `totalTrades` value alone does not prove no entry order occurred.
7. When a run has zero entries, diagnose the condition funnel before editing:
   - Count regime, structure, ADX/ATR, volatility, breakout, stabilization, pullback, confirmation, volume, cooldown, and distance conditions.
   - Trace state-machine stage occupancy and count intersections on confirmation bars.
   - Determine whether raw signals are zero or whether trade direction, next-bar shifting, position state, warmup slicing, or engine configuration filtered them.
8. Repair the smallest proven over-constraint. Preserve the user's prohibited techniques and risk rules; do not remove filters indiscriminately or hardcode dates/prices to manufacture trades.
9. Re-run the identical real-market request after every candidate fix. Then re-run sandbox, long-history stress, strategy-specific scenarios, and prefix-causality validation before completion.

For the common default Strategy IDE crypto check, verify the implementation rather than assuming these values remain stable: `BTC/USDT`, `1M`, `1H`, strict close confirmation, and next-bar-open fills.

Repair runtime failures, security failures, blocking hints, output mismatches, missing signals in intended regimes, excessive signals in forbidden regimes, historical drift, and avoidable performance problems. Re-run the complete validator after the final edit.

An informational `ZERO_STOP_AND_TAKE_PROFIT` hint is intentional when `exit_owner: indicator` and both engine exits are explicitly disabled. Explain it in the final report; do not enable duplicate engine exits merely to remove the hint.

## Completion Report

State:

- The final output file path.
- Sandbox success/failure and plot/signal counts.
- Stress-run size and runtime.
- Targeted scenario entry/exit counts and sideways behavior where relevant.
- Prefix causality result.
- Remaining non-blocking hints and why they are acceptable.

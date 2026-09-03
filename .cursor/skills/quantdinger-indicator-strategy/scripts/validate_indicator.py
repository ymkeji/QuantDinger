#!/usr/bin/env python3
"""Validate QuantDinger Indicator IDE strategy code with project contracts."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import types
from pathlib import Path
from typing import Any

try:
    import numpy as np
    import pandas as pd
except ModuleNotFoundError as exc:
    print(
        json.dumps(
            {
                "success": False,
                "error": f"Missing validator dependency: {exc.name}",
                "action": "Run with the backend/container Python environment or an isolated environment containing numpy and pandas.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    raise SystemExit(2) from exc


PROJECT_ROOT = Path(__file__).resolve().parents[4]
APP_ROOT = PROJECT_ROOT / "backend_api_python" / "app"
FOUR_WAY_COLUMNS = ("open_long", "close_long", "open_short", "close_short")
BLOCKING_HINT_CODES = {
    "DECLARED_PARAMS_NOT_READ_VIA_PARAMS_GET",
    "FUTURE_DATA_LEAK",
    "HELPER_RETURNS_NDARRAY",
    "MISSING_BUY_SELL_COLUMNS",
    "MISSING_DF_COPY",
    "MISSING_INDICATOR_DESCRIPTION",
    "MISSING_INDICATOR_NAME",
    "MISSING_OUTPUT",
    "NDARRAY_PANDAS_METHOD_MISUSE",
    "PARAM_DEFAULT_MISMATCH",
    "SIGNAL_MARKERS_USE_WHERE_NONE",
    "UNKNOWN_STRATEGY_KEY",
}


def _load_project_validation_modules():
    """Load validation modules without importing the Flask application package."""
    if not APP_ROOT.is_dir():
        raise RuntimeError(f"Backend app directory not found: {APP_ROOT}")

    app_package = types.ModuleType("app")
    app_package.__path__ = [str(APP_ROOT)]
    services_package = types.ModuleType("app.services")
    services_package.__path__ = [str(APP_ROOT / "services")]
    utils_package = types.ModuleType("app.utils")
    utils_package.__path__ = [str(APP_ROOT / "utils")]

    logger_module = types.ModuleType("app.utils.logger")
    logger_module.get_logger = logging.getLogger
    db_module = types.ModuleType("app.utils.db")
    db_module.get_db_connection = lambda: None

    sys.modules.update(
        {
            "app": app_package,
            "app.services": services_package,
            "app.utils": utils_package,
            "app.utils.logger": logger_module,
            "app.utils.db": db_module,
        }
    )

    from app.services import indicator_validation
    from app.utils.safe_exec import build_safe_builtins, safe_exec_with_validation

    return indicator_validation, build_safe_builtins, safe_exec_with_validation


def _ohlcv_frame(close_values: np.ndarray, volume_values: np.ndarray) -> pd.DataFrame:
    close = np.asarray(close_values, dtype=float)
    volume = np.asarray(volume_values, dtype=float)
    prior = np.insert(close[:-1], 0, close[0])
    open_values = prior + 0.2 * (close - prior)
    spread = np.maximum(0.0001, np.abs(close) * 0.0015)
    index = pd.date_range("2025-01-01", periods=len(close), freq="5min", tz="UTC")
    return pd.DataFrame(
        {
            "time": [int(item.timestamp() * 1000) for item in index],
            "open": open_values,
            "high": np.maximum(open_values, close) + spread,
            "low": np.minimum(open_values, close) - spread,
            "close": close,
            "volume": np.maximum(1.0, volume),
        },
        index=index,
    )


def _stress_frame(length: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0, 0.002, length)
    close = 100.0 * np.exp(np.cumsum(returns))
    volume = rng.normal(100_000.0, 25_000.0, length)
    return _ohlcv_frame(close, volume)


def _scenario_frames(seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    flat_start = 100.0 + np.cumsum(rng.normal(0.0, 0.025, 80))
    up_index = np.arange(260)
    up = flat_start[-1] + 0.105 * up_index + 1.25 * np.sin(up_index / 8.0)
    flat_middle = up[-1] + np.cumsum(rng.normal(0.0, 0.03, 60))
    down_index = np.arange(260)
    down = flat_middle[-1] - 0.11 * down_index + 1.3 * np.sin(down_index / 8.5)
    trend_close = np.concatenate([flat_start, up, flat_middle, down])
    trend_volume = rng.normal(1_000.0, 280.0, len(trend_close))

    sideways_close = 100.0 + np.cumsum(rng.normal(0.0, 0.018, 500))
    sideways_volume = rng.normal(1_000.0, 30.0, len(sideways_close))
    return (
        _ohlcv_frame(trend_close, trend_volume),
        _ohlcv_frame(sideways_close, sideways_volume),
    )


def _execute(
    code: str,
    frame: pd.DataFrame,
    indicator_validation,
    build_safe_builtins,
    safe_exec_with_validation,
) -> dict[str, Any]:
    environment: dict[str, Any] = {
        "df": frame.copy(),
        "pd": pd,
        "np": np,
        "params": indicator_validation.merge_indicator_params(code),
        "output": None,
        "__builtins__": build_safe_builtins(),
    }
    execution = safe_exec_with_validation(
        code=code,
        exec_globals=environment,
        exec_locals=environment,
        timeout=20,
    )
    if not execution.get("success"):
        raise RuntimeError(execution.get("error") or "Sandbox execution failed")
    return environment


def _validate_with_frame(code: str, frame: pd.DataFrame, indicator_validation) -> dict[str, Any]:
    original_generator = indicator_validation.generate_mock_df
    indicator_validation.generate_mock_df = lambda length=200: frame.copy()
    try:
        return indicator_validation.validate_indicator_code(code)
    finally:
        indicator_validation.generate_mock_df = original_generator


def _signal_counts(frame: pd.DataFrame) -> dict[str, int]:
    return {
        column: int(frame[column].fillna(False).astype(bool).sum())
        for column in FOUR_WAY_COLUMNS
    }


def _blocking_hints(validation: dict[str, Any], strict_hints: bool) -> list[dict[str, Any]]:
    blocking = []
    for hint in validation.get("hints") or []:
        severity = str(hint.get("severity") or "").lower()
        code = hint.get("code")
        if severity == "error" or code in BLOCKING_HINT_CODES:
            blocking.append(hint)
        elif strict_hints and severity == "warn":
            blocking.append(hint)
    return blocking


def validate(args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    path = args.path.resolve()
    if not path.is_file():
        raise RuntimeError(f"Strategy file not found: {path}")
    code = path.read_text(encoding="utf-8")
    indicator_validation, build_safe_builtins, safe_exec_with_validation = (
        _load_project_validation_modules()
    )

    np.random.seed(args.seed)
    standard = indicator_validation.validate_indicator_code(code)
    blocking_hints = _blocking_hints(standard, args.strict_hints)

    stress_frame = _stress_frame(args.stress_bars, args.seed)
    stress_started = time.perf_counter()
    stress = _validate_with_frame(code, stress_frame, indicator_validation)
    stress_seconds = time.perf_counter() - stress_started

    trend_frame, sideways_frame = _scenario_frames(args.seed)
    trend_environment = _execute(
        code,
        trend_frame,
        indicator_validation,
        build_safe_builtins,
        safe_exec_with_validation,
    )
    sideways_environment = _execute(
        code,
        sideways_frame,
        indicator_validation,
        build_safe_builtins,
        safe_exec_with_validation,
    )

    prefix_length = max(2, int(len(trend_frame) * 0.65))
    prefix_environment = _execute(
        code,
        trend_frame.iloc[:prefix_length],
        indicator_validation,
        build_safe_builtins,
        safe_exec_with_validation,
    )
    trend_result = trend_environment["df"]
    sideways_result = sideways_environment["df"]
    prefix_result = prefix_environment["df"]

    prefix_stable = all(
        trend_result[column].iloc[:prefix_length].equals(prefix_result[column])
        for column in FOUR_WAY_COLUMNS
    )
    execution_columns_bool = all(
        pd.api.types.is_bool_dtype(trend_result[column].dtype)
        and pd.api.types.is_bool_dtype(sideways_result[column].dtype)
        for column in FOUR_WAY_COLUMNS
    )
    trend_counts = _signal_counts(trend_result)
    sideways_counts = _signal_counts(sideways_result)
    trend_entries = trend_counts["open_long"] + trend_counts["open_short"]

    report = {
        "path": str(path),
        "standard": standard,
        "blocking_hints": blocking_hints,
        "stress": {
            "bars": args.stress_bars,
            "seconds": round(stress_seconds, 3),
            "success": bool(stress.get("success")),
            "error_type": stress.get("error_type"),
            "message": stress.get("msg"),
        },
        "scenarios": {
            "trend_bars": len(trend_result),
            "trend_signals": trend_counts,
            "sideways_bars": len(sideways_result),
            "sideways_signals": sideways_counts,
            "prefix_bars": prefix_length,
            "prefix_stable": prefix_stable,
            "execution_columns_bool": execution_columns_bool,
        },
    }
    success = (
        bool(standard.get("success"))
        and not blocking_hints
        and bool(stress.get("success"))
        and prefix_stable
        and execution_columns_bool
        and (not args.require_entry or trend_entries > 0)
    )
    report["success"] = success
    if args.require_entry and trend_entries == 0:
        report["entry_requirement_error"] = "No entries occurred in the generic trend scenario"
    return report, success


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="QuantDinger indicator Python file")
    parser.add_argument("--stress-bars", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260727)
    parser.add_argument(
        "--require-entry",
        action="store_true",
        help="Fail when the generic trend scenario produces no long/short entries",
    )
    parser.add_argument(
        "--strict-hints",
        action="store_true",
        help="Treat all warning-level quality hints as blocking",
    )
    args = parser.parse_args()
    if args.stress_bars < 200:
        parser.error("--stress-bars must be at least 200")
    return args


def main() -> int:
    try:
        report, success = validate(parse_args())
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())

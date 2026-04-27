"""
Sheaf-Style Alpha Pipeline
==========================

Goal:
    Build a minimal but nontrivial alpha research pipeline:

        operator DSL / alpha expression
            -> alpha signal
            -> portfolio weights
            -> backtest
            -> numerical analytics

Sheaf interpretation:
    Field      = section over instruments × time
    Operator   = local morphism on sections
    Expression = composition of local morphisms
    Alpha      = global section / tradable signal

This script uses synthetic OHLCV data by default, so it can run immediately.
Later, replace `make_synthetic_panel()` with real data ingestion.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, Callable


# ============================================================
# 1. Synthetic data panel
# ============================================================


def make_synthetic_panel(
    n_days: int = 252,
    tickers: tuple[str, ...] = ("AAPL", "MSFT", "NVDA", "TSLA"),
    seed: int = 42,
) -> Dict[str, pd.DataFrame]:
    """Create synthetic OHLCV-like panel data.

    Output:
        data[field] is a DataFrame indexed by date, columns=tickers.

    In sheaf language:
        each field is a section over time × asset universe.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=n_days)
    n_assets = len(tickers)

    returns = rng.normal(loc=0.0003, scale=0.02, size=(n_days, n_assets))
    close = 100 * np.exp(np.cumsum(returns, axis=0))

    open_ = close * (1 + rng.normal(0, 0.003, size=close.shape))
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.01, size=close.shape))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.01, size=close.shape))
    volume = rng.lognormal(mean=15, sigma=0.3, size=close.shape)

    data = {
        "open": pd.DataFrame(open_, index=dates, columns=tickers),
        "close": pd.DataFrame(close, index=dates, columns=tickers),
        "high": pd.DataFrame(high, index=dates, columns=tickers),
        "low": pd.DataFrame(low, index=dates, columns=tickers),
        "volume": pd.DataFrame(volume, index=dates, columns=tickers),
    }

    data["returns"] = data["close"].pct_change().fillna(0.0)
    data["vwap"] = (data["high"] + data["low"] + data["close"]) / 3

    return data


# ============================================================
# 2. Local operators on sections
# ============================================================


def cs_rank(x: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional rank at each date."""
    return x.rank(axis=1, pct=True)


def ts_mean(x: pd.DataFrame, window: int) -> pd.DataFrame:
    return x.rolling(window).mean()


def ts_std(x: pd.DataFrame, window: int) -> pd.DataFrame:
    return x.rolling(window).std()


def ts_delta(x: pd.DataFrame, window: int) -> pd.DataFrame:
    return x.diff(window)


def safe_divide(x: pd.DataFrame, y: pd.DataFrame, eps: float = 1e-9) -> pd.DataFrame:
    return x / (y.replace(0, np.nan) + eps)


def zscore(x: pd.DataFrame) -> pd.DataFrame:
    mu = x.mean(axis=1)
    sigma = x.std(axis=1).replace(0, np.nan)
    return x.sub(mu, axis=0).div(sigma, axis=0)


# ============================================================
# 3. Alpha library
# ============================================================


def alpha_momentum(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Momentum alpha: rank of recent return.

    Intuition:
        Assets with higher recent return receive higher signal.
    """
    ret_20 = data["close"].pct_change(20)
    return cs_rank(ret_20)


def alpha_reversal(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Short-term reversal alpha: negative rank of 5-day return."""
    ret_5 = data["close"].pct_change(5)
    return -cs_rank(ret_5)


def alpha_volume_pressure(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Volume-pressure alpha.

    Signal:
        rank( returns * log(volume / ts_mean(volume, 20)) )
    """
    vol_ratio = safe_divide(data["volume"], ts_mean(data["volume"], 20))
    signal = data["returns"] * np.log(vol_ratio.clip(lower=1e-9))
    return cs_rank(signal)


def alpha_price_location(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Close-location alpha.

    Measures where close lies inside the intraday high-low range.
    """
    loc = safe_divide(data["close"] - data["low"], data["high"] - data["low"])
    return cs_rank(loc)


ALPHA_LIBRARY: Dict[str, Callable[[Dict[str, pd.DataFrame]], pd.DataFrame]] = {
    "momentum_20d": alpha_momentum,
    "reversal_5d": alpha_reversal,
    "volume_pressure": alpha_volume_pressure,
    "price_location": alpha_price_location,
}


# ============================================================
# 4. Signal -> portfolio weights
# ============================================================


def signal_to_weights(signal: pd.DataFrame, dollar_neutral: bool = True) -> pd.DataFrame:
    """Convert alpha signal to portfolio weights.

    Steps:
        1. Cross-sectionally demean signal.
        2. Normalize absolute exposure to 1.
        3. Optionally enforce dollar neutrality.
    """
    w = signal.copy()

    if dollar_neutral:
        w = w.sub(w.mean(axis=1), axis=0)

    gross = w.abs().sum(axis=1).replace(0, np.nan)
    w = w.div(gross, axis=0)

    return w.fillna(0.0)


# ============================================================
# 5. Backtest
# ============================================================


@dataclass
class BacktestResult:
    alpha_name: str
    daily_returns: pd.Series
    weights: pd.DataFrame
    signal: pd.DataFrame
    metrics: Dict[str, float]


def compute_metrics(daily_returns: pd.Series) -> Dict[str, float]:
    r = daily_returns.dropna()

    if len(r) == 0:
        return {
            "annual_return": np.nan,
            "annual_vol": np.nan,
            "sharpe": np.nan,
            "max_drawdown": np.nan,
            "win_rate": np.nan,
        }

    annual_return = 252 * r.mean()
    annual_vol = np.sqrt(252) * r.std()
    sharpe = annual_return / annual_vol if annual_vol != 0 else np.nan

    equity = (1 + r).cumprod()
    drawdown = equity / equity.cummax() - 1
    max_drawdown = drawdown.min()
    win_rate = (r > 0).mean()

    return {
        "annual_return": float(annual_return),
        "annual_vol": float(annual_vol),
        "sharpe": float(sharpe),
        "max_drawdown": float(max_drawdown),
        "win_rate": float(win_rate),
    }


def backtest_alpha(
    alpha_name: str,
    alpha_func: Callable[[Dict[str, pd.DataFrame]], pd.DataFrame],
    data: Dict[str, pd.DataFrame],
    execution_lag: int = 1,
) -> BacktestResult:
    """Backtest one alpha.

    Important:
        weights are shifted by execution_lag to avoid lookahead bias.
    """
    signal = alpha_func(data)
    weights = signal_to_weights(signal)

    future_returns = data["returns"]
    pnl = (weights.shift(execution_lag) * future_returns).sum(axis=1)
    pnl = pnl.fillna(0.0)

    metrics = compute_metrics(pnl)

    return BacktestResult(
        alpha_name=alpha_name,
        daily_returns=pnl,
        weights=weights,
        signal=signal,
        metrics=metrics,
    )


# ============================================================
# 6. Run full pipeline
# ============================================================


def run_pipeline() -> pd.DataFrame:
    data = make_synthetic_panel()

    results = []

    for name, func in ALPHA_LIBRARY.items():
        result = backtest_alpha(name, func, data)
        row = {"alpha": name, **result.metrics}
        results.append(row)

        result.signal.to_csv(f"signal_{name}.csv", encoding="utf-8-sig")
        result.weights.to_csv(f"weights_{name}.csv", encoding="utf-8-sig")
        result.daily_returns.to_csv(f"returns_{name}.csv", encoding="utf-8-sig")

    metrics_df = pd.DataFrame(results).sort_values("sharpe", ascending=False)
    metrics_df.to_csv("alpha_metrics.csv", index=False, encoding="utf-8-sig")

    return metrics_df


# ============================================================
# 7. Entry point
# ============================================================


if __name__ == "__main__":
    metrics = run_pipeline()
    print("\nAlpha metrics:")
    print(metrics)
    print("\nSaved:")
    print("  alpha_metrics.csv")
    print("  signal_*.csv")
    print("  weights_*.csv")
    print("  returns_*.csv")

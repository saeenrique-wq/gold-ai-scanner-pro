"""
Cálculo de indicadores técnicos usando pandas/numpy.
No requiere TA-Lib. Funciona con cualquier instalación de Python.
"""
from typing import Tuple
import pandas as pd
import numpy as np

from config import (
    EMA_FAST, EMA_SLOW, RSI_PERIOD, MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    ATR_PERIOD, get_logger,
)

logger = get_logger("indicators")


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Media Móvil Exponencial."""
    return series.ewm(span=period, adjust=False).mean()


def calculate_rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """Índice de Fuerza Relativa (RSI). Rango 0-100."""
    delta     = series.diff()
    gain      = delta.clip(lower=0)
    loss      = (-delta).clip(lower=0)
    avg_gain  = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss  = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs        = avg_gain / avg_loss.replace(0, np.nan)
    rsi       = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def calculate_macd(
    series: pd.Series,
    fast: int   = MACD_FAST,
    slow: int   = MACD_SLOW,
    signal: int = MACD_SIGNAL,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Retorna (macd_line, signal_line, histogram).
    macd_line > 0  → impulso alcista
    macd_line < 0  → impulso bajista
    """
    ema_fast   = calculate_ema(series, fast)
    ema_slow   = calculate_ema(series, slow)
    macd_line  = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    histogram  = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_atr(
    high:   pd.Series,
    low:    pd.Series,
    close:  pd.Series,
    period: int = ATR_PERIOD,
) -> pd.Series:
    """Average True Range — mide la volatilidad actual del mercado."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low  - prev_close).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def calculate_support_resistance(
    df: pd.DataFrame,
    lookback: int = 20,
) -> Tuple[float, float]:
    """
    Soporte y resistencia simples basados en mínimos/máximos del lookback.
    Retorna (soporte, resistencia).
    """
    if len(df) < lookback:
        lookback = len(df)
    window = df.tail(lookback)
    support    = float(window["Low"].min())
    resistance = float(window["High"].max())
    return support, resistance


def calculate_all(df: pd.DataFrame) -> dict:
    """
    Calcula todos los indicadores sobre un DataFrame OHLCV.
    Retorna un dict con los valores de la última vela cerrada.
    Requiere columnas: Open, High, Low, Close, Volume.
    """
    if df is None or len(df) < 30:
        return {"valid": False, "error": "Datos insuficientes para calcular indicadores."}

    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]

    ema50  = calculate_ema(close, EMA_FAST)
    ema200 = calculate_ema(close, EMA_SLOW) if len(df) >= EMA_SLOW else calculate_ema(close, len(df))
    rsi    = calculate_rsi(close)
    atr    = calculate_atr(high, low, close)
    macd_line, signal_line, histogram = calculate_macd(close)
    support, resistance = calculate_support_resistance(df)

    # Usar penúltima vela (última cerrada para evitar señales de vela abierta)
    idx = -2 if len(df) >= 2 else -1

    result = {
        "valid":           True,
        "close":           round(float(close.iloc[idx]),        2),
        "open":            round(float(df["Open"].iloc[idx]),   2),
        "high":            round(float(high.iloc[idx]),         2),
        "low":             round(float(low.iloc[idx]),          2),
        "ema50":           round(float(ema50.iloc[idx]),        2),
        "ema200":          round(float(ema200.iloc[idx]),       2),
        "rsi":             round(float(rsi.iloc[idx]),          2),
        "macd":            round(float(macd_line.iloc[idx]),    4),
        "macd_signal":     round(float(signal_line.iloc[idx]),  4),
        "macd_histogram":  round(float(histogram.iloc[idx]),    4),
        "atr":             round(float(atr.iloc[idx]),          2),
        "support":         round(support,                       2),
        "resistance":      round(resistance,                    2),
        "above_ema50":     float(close.iloc[idx]) > float(ema50.iloc[idx]),
        "above_ema200":    float(close.iloc[idx]) > float(ema200.iloc[idx]),
        "trend_up":        float(ema50.iloc[idx]) > float(ema200.iloc[idx]),
        "macd_bullish":    float(macd_line.iloc[idx]) > float(signal_line.iloc[idx]),
        "candle_count":    len(df),
    }

    # Dirección de la vela actual
    result["candle_bullish"] = result["close"] > result["open"]

    return result

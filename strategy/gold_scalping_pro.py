"""
Estrategia: Gold Scalping Pro
─────────────────────────────
Analiza M5 para confirmación y H1 para tendencia mayor.
Detecta señales BUY o SELL con múltiples confirmaciones.
Solo genera señal si se cumplen al menos MIN_CONFIRMATIONS condiciones.
"""
from typing import Optional, Dict, Any
import pandas as pd

from config import (
    RSI_BUY_MIN, RSI_BUY_MAX, RSI_SELL_MIN, RSI_SELL_MAX,
    MIN_ATR_VALUE, MIN_CONFIRMATIONS, get_logger,
)
from strategy.indicators import calculate_all

logger = get_logger("gold_scalping_pro")


class GoldScalpingPro:
    """
    Estrategia Gold Scalping Pro.

    Proceso:
    1. Calcular indicadores en M5 (confirmación)
    2. Calcular indicadores en H1 (tendencia mayor)
    3. Verificar condiciones de BUY o SELL
    4. Contar cuántas condiciones se cumplen
    5. Si supera el mínimo → emitir señal
    """

    def analyze(
        self,
        df_m5:  pd.DataFrame,
        df_h1:  pd.DataFrame,
        df_m15: Optional[pd.DataFrame] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Analiza el mercado y retorna señal o None.
        Retorna dict con: type, score, entry, reason_list
        """
        # Validar datos
        if df_m5 is None or len(df_m5) < 30:
            logger.debug("Datos M5 insuficientes para analizar.")
            return None
        if df_h1 is None or len(df_h1) < 30:
            logger.debug("Datos H1 insuficientes para analizar.")
            return None

        ind_m5  = calculate_all(df_m5)
        ind_h1  = calculate_all(df_h1)
        ind_m15 = calculate_all(df_m15) if df_m15 is not None and len(df_m15) >= 30 else None

        if not ind_m5.get("valid") or not ind_h1.get("valid"):
            logger.debug("Indicadores no válidos.")
            return None

        # ATR mínimo (volatilidad)
        if ind_m5["atr"] < MIN_ATR_VALUE:
            logger.debug(f"ATR muy bajo ({ind_m5['atr']}). Sin volatilidad suficiente.")
            return None

        entry = ind_m5["close"]

        buy_score,  buy_reasons  = self._check_buy(ind_m5, ind_h1, ind_m15)
        sell_score, sell_reasons = self._check_sell(ind_m5, ind_h1, ind_m15)

        # La dirección con mayor puntuación gana
        if buy_score >= MIN_CONFIRMATIONS and buy_score > sell_score:
            return {
                "type":        "BUY",
                "score":       buy_score,
                "entry":       entry,
                "atr":         ind_m5["atr"],
                "rsi":         ind_m5["rsi"],
                "reasons":     buy_reasons,
                "indicators":  ind_m5,
            }
        elif sell_score >= MIN_CONFIRMATIONS and sell_score > buy_score:
            return {
                "type":        "SELL",
                "score":       sell_score,
                "entry":       entry,
                "atr":         ind_m5["atr"],
                "rsi":         ind_m5["rsi"],
                "reasons":     sell_reasons,
                "indicators":  ind_m5,
            }

        logger.debug(
            f"Sin señal. BUY={buy_score}/{MIN_CONFIRMATIONS}  "
            f"SELL={sell_score}/{MIN_CONFIRMATIONS}"
        )
        return None

    # ─── Condiciones BUY ─────────────────────────────────────────────────────

    def _check_buy(
        self,
        m5:  Dict,
        h1:  Dict,
        m15: Optional[Dict],
    ):
        score   = 0
        reasons = []

        # 1. Tendencia H1 alcista (EMA50 > EMA200)
        if h1["trend_up"]:
            score += 1
            reasons.append("Tendencia H1 alcista (EMA50 > EMA200)")

        # 2. Precio por encima de EMA50 en M5
        if m5["above_ema50"]:
            score += 1
            reasons.append("Precio sobre EMA50 en M5")

        # 3. Precio por encima de EMA200 en M5
        if m5["above_ema200"]:
            score += 1
            reasons.append("Precio sobre EMA200 en M5")

        # 4. RSI en zona de compra (45-70)
        if RSI_BUY_MIN <= m5["rsi"] <= RSI_BUY_MAX:
            score += 1
            reasons.append(f"RSI válido para compra: {m5['rsi']:.1f}")

        # 5. MACD alcista en M5
        if m5["macd_bullish"]:
            score += 1
            reasons.append("MACD alcista en M5")

        # 6. Precio sobre EMA50 en H1
        if h1["above_ema50"]:
            score += 1
            reasons.append("Precio sobre EMA50 en H1")

        # 7. Vela M5 alcista (cierre > apertura)
        if m5["candle_bullish"]:
            score += 1
            reasons.append("Vela M5 alcista")

        # 8. M15 confirma (si disponible)
        if m15 and m15.get("valid"):
            if m15["trend_up"] and m15["above_ema50"]:
                score += 1
                reasons.append("M15 confirma tendencia alcista")

        # 9. RSI H1 por encima de 50
        if h1["rsi"] > 50:
            score += 1
            reasons.append(f"RSI H1 > 50 ({h1['rsi']:.1f})")

        # 10. MACD H1 alcista
        if h1["macd_bullish"]:
            score += 1
            reasons.append("MACD alcista en H1")

        return score, reasons

    # ─── Condiciones SELL ────────────────────────────────────────────────────

    def _check_sell(
        self,
        m5:  Dict,
        h1:  Dict,
        m15: Optional[Dict],
    ):
        score   = 0
        reasons = []

        # 1. Tendencia H1 bajista (EMA50 < EMA200)
        if not h1["trend_up"]:
            score += 1
            reasons.append("Tendencia H1 bajista (EMA50 < EMA200)")

        # 2. Precio por debajo de EMA50 en M5
        if not m5["above_ema50"]:
            score += 1
            reasons.append("Precio bajo EMA50 en M5")

        # 3. Precio por debajo de EMA200 en M5
        if not m5["above_ema200"]:
            score += 1
            reasons.append("Precio bajo EMA200 en M5")

        # 4. RSI en zona de venta (30-55)
        if RSI_SELL_MIN <= m5["rsi"] <= RSI_SELL_MAX:
            score += 1
            reasons.append(f"RSI válido para venta: {m5['rsi']:.1f}")

        # 5. MACD bajista en M5
        if not m5["macd_bullish"]:
            score += 1
            reasons.append("MACD bajista en M5")

        # 6. Precio bajo EMA50 en H1
        if not h1["above_ema50"]:
            score += 1
            reasons.append("Precio bajo EMA50 en H1")

        # 7. Vela M5 bajista
        if not m5["candle_bullish"]:
            score += 1
            reasons.append("Vela M5 bajista")

        # 8. M15 confirma (si disponible)
        if m15 and m15.get("valid"):
            if not m15["trend_up"] and not m15["above_ema50"]:
                score += 1
                reasons.append("M15 confirma tendencia bajista")

        # 9. RSI H1 por debajo de 50
        if h1["rsi"] < 50:
            score += 1
            reasons.append(f"RSI H1 < 50 ({h1['rsi']:.1f})")

        # 10. MACD H1 bajista
        if not h1["macd_bullish"]:
            score += 1
            reasons.append("MACD bajista en H1")

        return score, reasons

    def get_description(self) -> str:
        return (
            f"Gold Scalping Pro — Requiere {MIN_CONFIRMATIONS}/10 confirmaciones. "
            "Usa EMA50, EMA200, RSI, MACD, ATR en M5 y H1."
        )

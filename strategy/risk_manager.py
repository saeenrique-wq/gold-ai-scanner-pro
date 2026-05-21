"""
Risk Manager — Cálculo de lotaje, SL, TP1-TP4 y estadísticas semanales.
Fórmulas basadas en la estructura del plan de GOLD AI SCANNER PRO.
"""
from typing import Optional
from config import MIN_RR_RATIO, CAPITAL_PLANS, get_logger
from models import RiskCalc, WeeklyStats
import database as db

logger = get_logger("risk_manager")


class RiskManager:
    """
    Gestión de riesgo para XAUUSD.

    Cómo funciona el cálculo de distancias para ORO:
    ─────────────────────────────────────────────────
    XAUUSD: 1 lote estándar = 100 onzas.
    Si el precio se mueve $1 USD:
      → 1   lote  gana/pierde $100
      → 0.01 lote gana/pierde $1
      → pip_value = lot_size × 100  (USD por $1 de movimiento)

    Ejemplo con 0.01 lote y riesgo $7:
      pip_value   = 0.01 × 100 = 1 USD / $1 de precio
      sl_distance = 7 / 1      = $7 de precio
      tp1_distance = 7 × 2     = $14 de precio
    """

    def __init__(self, capital: float = 200.0):
        self.capital  = capital
        self._plan    = self._get_plan(capital)

    def _get_plan(self, capital: float) -> dict:
        """Selecciona el plan más cercano al capital ingresado."""
        plans = sorted(CAPITAL_PLANS.keys())
        for threshold in plans:
            if capital <= threshold:
                return CAPITAL_PLANS[threshold]
        return CAPITAL_PLANS[plans[-1]]   # Capital mayor al máximo plan

    def set_capital(self, capital: float) -> None:
        self.capital = capital
        self._plan   = self._get_plan(capital)

    @property
    def lot_size(self) -> float:
        return self._plan["lot"]

    @property
    def risk_usd(self) -> float:
        return self._plan["risk_usd"]

    @property
    def min_profit(self) -> float:
        return self._plan["min_profit"]

    def calculate(
        self,
        entry:       float,
        signal_type: str,
        lot_size:    Optional[float] = None,
        risk_usd:    Optional[float] = None,
    ) -> RiskCalc:
        """
        Calcula SL, TP1-TP4 para una entrada dada.
        Retorna RiskCalc con todos los niveles y validación.
        """
        lot  = lot_size  if lot_size  is not None else self.lot_size
        risk = risk_usd  if risk_usd  is not None else self.risk_usd

        if entry <= 0:
            return RiskCalc(valid=False, error="Precio de entrada inválido.")
        if lot <= 0:
            return RiskCalc(valid=False, error="Lotaje inválido.")
        if risk <= 0:
            return RiskCalc(valid=False, error="Riesgo inválido.")

        # USD ganados/perdidos por $1 de movimiento en precio
        pip_value   = round(lot * 100, 4)
        sl_distance = round(risk / pip_value, 2)

        if sl_distance < 0.01:
            return RiskCalc(valid=False, error="SL demasiado pequeño. Revisa lotaje.")

        tp1_d = round(sl_distance * 2, 2)
        tp2_d = round(sl_distance * 3, 2)
        tp3_d = round(sl_distance * 4, 2)
        tp4_d = round(sl_distance * 5, 2)

        if signal_type == "BUY":
            sl   = round(entry - sl_distance, 2)
            tp1  = round(entry + tp1_d, 2)
            tp2  = round(entry + tp2_d, 2)
            tp3  = round(entry + tp3_d, 2)
            tp4  = round(entry + tp4_d, 2)
        elif signal_type == "SELL":
            sl   = round(entry + sl_distance, 2)
            tp1  = round(entry - tp1_d, 2)
            tp2  = round(entry - tp2_d, 2)
            tp3  = round(entry - tp3_d, 2)
            tp4  = round(entry - tp4_d, 2)
        else:
            return RiskCalc(valid=False, error=f"Tipo de señal inválido: {signal_type}")

        min_profit = round(risk * MIN_RR_RATIO, 2)
        rr_ratio   = MIN_RR_RATIO  # Base siempre 1:2

        # Verificar que SL y TP sean precios válidos
        if sl <= 0 or tp1 <= 0:
            return RiskCalc(valid=False, error="Niveles de precio calculados son negativos.")

        return RiskCalc(
            entry        = entry,
            signal_type  = signal_type,
            lot_size     = lot,
            risk_usd     = risk,
            sl           = sl,
            tp1          = tp1,
            tp2          = tp2,
            tp3          = tp3,
            tp4          = tp4,
            sl_distance  = sl_distance,
            tp1_distance = tp1_d,
            min_profit   = min_profit,
            rr_ratio     = rr_ratio,
            pip_value    = pip_value,
            valid        = True,
        )

    def check_rr_ratio(
        self,
        entry:       float,
        sl:          float,
        tp1:         float,
        signal_type: str,
    ) -> bool:
        """Verifica que el riesgo-beneficio sea al menos 1:2."""
        if signal_type == "BUY":
            risk   = entry - sl
            reward = tp1   - entry
        else:
            risk   = sl    - entry
            reward = entry - tp1

        if risk <= 0:
            return False
        return (reward / risk) >= MIN_RR_RATIO

    def weekly_limit_reached(self) -> bool:
        return db.weekly_limit_reached()

    def get_weekly_stats(self) -> WeeklyStats:
        return db.get_weekly_stats(capital=self.capital)

    def format_summary(self) -> str:
        plan = self._plan
        return (
            f"Capital: ${self.capital:.0f} | "
            f"Lote: {plan['lot']} | "
            f"Riesgo: ${plan['risk_usd']} | "
            f"Ganancia mín.: ${plan['min_profit']}"
        )

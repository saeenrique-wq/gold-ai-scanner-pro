from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class Signal:
    id:               Optional[int]  = None
    created_at:       str            = ""
    broker:           str            = "Yahoo Finance"
    platform:         str            = "Online"
    symbol:           str            = "XAUUSD"
    timeframe:        str            = "M5"
    signal_type:      str            = ""   # BUY / SELL
    entry:            float          = 0.0
    sl:               float          = 0.0
    tp1:              float          = 0.0
    tp2:              float          = 0.0
    tp3:              float          = 0.0
    tp4:              float          = 0.0
    risk_usd:         float          = 0.0
    expected_profit:  float          = 0.0
    rr_ratio:         float          = 0.0
    lot_size:         float          = 0.01
    status:           str            = "BUSCANDO"
    ai_provider:      str            = ""
    ai_decision:      str            = ""
    ai_confidence:    str            = ""
    ai_reason:        str            = ""
    result:           str            = ""
    close_price:      float          = 0.0
    closed_at:        str            = ""
    score:            int            = 0
    signal_style:     str            = "Scalping"


@dataclass
class SignalEvent:
    id:         Optional[int] = None
    signal_id:  int           = 0
    event_time: str           = ""
    event_type: str           = ""
    price:      float         = 0.0
    message:    str           = ""


@dataclass
class AIResponse:
    decision:   str  = "RECHAZAR"   # APROBAR / RECHAZAR / PEDIR_MAS_CONFIRMACION / RIESGO_ALTO
    confianza:  str  = "BAJA"       # BAJA / MEDIA / ALTA
    motivo:     str  = ""
    riesgo:     str  = "ALTO"       # BAJO / MEDIO / ALTO
    raw:        str  = ""
    valid:      bool = False

    def is_approved(self) -> bool:
        return (
            self.valid
            and self.decision == "APROBAR"
            and self.confianza != "BAJA"
            and self.riesgo != "ALTO"
        )


@dataclass
class RiskCalc:
    entry:          float = 0.0
    signal_type:    str   = "BUY"
    lot_size:       float = 0.01
    risk_usd:       float = 7.0
    sl:             float = 0.0
    tp1:            float = 0.0
    tp2:            float = 0.0
    tp3:            float = 0.0
    tp4:            float = 0.0
    sl_distance:    float = 0.0
    tp1_distance:   float = 0.0
    min_profit:     float = 0.0
    rr_ratio:       float = 2.0
    pip_value:      float = 0.0   # USD por $1 de movimiento
    valid:          bool  = False
    error:          str   = ""


@dataclass
class MarketData:
    symbol:         str   = "XAUUSD"
    bid:            float = 0.0
    ask:            float = 0.0
    last:           float = 0.0
    spread:         float = 0.0
    timestamp:      str   = ""
    source:         str   = "yfinance"
    connected:      bool  = False
    error:          str   = ""


@dataclass
class WeeklyStats:
    week_start:    str   = ""
    week_end:      str   = ""
    total_signals: int   = 0
    won_signals:   int   = 0
    lost_signals:  int   = 0
    partial_signals: int = 0
    win_rate:      float = 0.0
    net_profit:    float = 0.0
    capital_start: float = 0.0
    capital_end:   float = 0.0

    @property
    def remaining_signals(self) -> int:
        from config import MAX_WEEKLY_SIGNALS
        return max(0, MAX_WEEKLY_SIGNALS - self.total_signals)

    @property
    def limit_reached(self) -> bool:
        from config import MAX_WEEKLY_SIGNALS
        return self.total_signals >= MAX_WEEKLY_SIGNALS

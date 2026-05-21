"""
Conector opcional para MetaTrader 5.
Solo se usa si el usuario tiene MT5 instalado y activo.
Si no está disponible, el sistema funciona con Yahoo Finance.
"""
from typing import Optional, Dict, Any
import pandas as pd

from config import get_logger, TIMEFRAMES

logger = get_logger("mt5_connector")

try:
    import MetaTrader5 as mt5
    _MT5_LIB_AVAILABLE = True
except ImportError:
    mt5 = None
    _MT5_LIB_AVAILABLE = False


class MT5Connector:
    """Conector opcional a MetaTrader 5 (solo Windows con MT5 instalado)."""

    MT5_TIMEFRAMES = {
        "M1":  21,   # mt5.TIMEFRAME_M1
        "M5":  5,    # mt5.TIMEFRAME_M5
        "M15": 15,   # mt5.TIMEFRAME_M15
        "M30": 30,   # mt5.TIMEFRAME_M30
        "H1":  16385,# mt5.TIMEFRAME_H1
    }

    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol    = symbol
        self._connected = False

    @property
    def is_available(self) -> bool:
        return _MT5_LIB_AVAILABLE

    def connect(self) -> tuple:
        """Intenta conectar con MT5. Retorna (ok, mensaje)."""
        if not _MT5_LIB_AVAILABLE:
            return False, "MetaTrader5 no está instalado."
        try:
            if not mt5.initialize():
                code, desc = mt5.last_error()
                return False, (
                    f"No se pudo inicializar MT5 (error {code}: {desc}). "
                    "Abre MetaTrader 5 e inicia sesión en tu broker primero."
                )
            info = mt5.terminal_info()
            if info is None or not info.connected:
                mt5.shutdown()
                return False, "MT5 abierto pero sin sesión de broker. Inicia sesión en MT5."
            self._connected = True
            return True, f"MT5 conectado — broker: {info.company}"
        except Exception as e:
            return False, f"Error con MT5: {e}"

    def disconnect(self) -> None:
        if _MT5_LIB_AVAILABLE and self._connected:
            mt5.shutdown()
        self._connected = False

    def get_price(self) -> Optional[float]:
        if not self._connected or not _MT5_LIB_AVAILABLE:
            return None
        try:
            tick = mt5.symbol_info_tick(self.symbol)
            return (tick.bid + tick.ask) / 2 if tick else None
        except Exception:
            return None

    def get_candles(self, timeframe: str = "M5", count: int = 210) -> Optional[pd.DataFrame]:
        if not self._connected or not _MT5_LIB_AVAILABLE:
            return None
        try:
            tf_id = self.MT5_TIMEFRAMES.get(timeframe)
            if tf_id is None:
                return None
            rates = mt5.copy_rates_from_pos(self.symbol, tf_id, 0, count)
            if rates is None or len(rates) == 0:
                return None
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df.set_index("time", inplace=True)
            df.rename(columns={
                "open": "Open", "high": "High",
                "low": "Low", "close": "Close",
                "tick_volume": "Volume",
            }, inplace=True)
            return df[["Open", "High", "Low", "Close", "Volume"]]
        except Exception as e:
            logger.error(f"Error obteniendo velas MT5: {e}")
            return None

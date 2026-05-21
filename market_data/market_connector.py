"""
Conector principal de mercado usando Yahoo Finance.
No requiere MetaTrader ni instalación especial.
Obtiene precios en vivo de servidores de Yahoo Finance (datos XAUUSD/ORO).
"""
import time
from datetime import datetime
from typing import Optional, Dict, Any

import pandas as pd

from config import (
    DEFAULT_YAHOO_SYMBOL, TIMEFRAMES, TIMEFRAME_PERIOD,
    CANDLES_NEEDED, get_logger,
)
from models import MarketData

logger = get_logger("market_connector")

# ─── Importar yfinance de forma segura ───────────────────────────────────────
try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    yf = None
    _YF_AVAILABLE = False
    logger.warning("yfinance no instalado. Ejecuta: pip install yfinance")


class MarketConnector:
    """
    Se conecta a Yahoo Finance y entrega precios + velas OHLCV en vivo.
    Servidor: finance.yahoo.com — completamente gratis.
    """

    def __init__(self, symbol: str = DEFAULT_YAHOO_SYMBOL):
        self.symbol   = symbol
        self._ticker  = None
        self._last_price: float = 0.0
        self._connected: bool   = False
        self._last_error: str   = ""
        self._candle_cache: Dict[str, Dict] = {}   # {timeframe: {"df": df, "ts": timestamp}}

    # ─── Conexión ─────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        if not _YF_AVAILABLE:
            self._connected = False
            self._last_error = "yfinance no está instalado. Ejecuta: pip install yfinance"
            return False
        try:
            self._ticker = yf.Ticker(self.symbol)
            # Prueba rápida: descarga 1 día de datos para verificar que el símbolo existe
            test = self._ticker.history(period="1d", interval="5m")
            if test is None or test.empty:
                self._connected = False
                self._last_error = (
                    f"El símbolo '{self.symbol}' no tiene datos. "
                    "Prueba con 'XAUUSD=X' o 'GC=F'."
                )
                return False
            self._connected = True
            self._last_error = ""
            logger.info(f"Conectado a Yahoo Finance — símbolo: {self.symbol}")
            return True
        except Exception as e:
            self._connected = False
            self._last_error = f"Error conectando a Yahoo Finance: {e}"
            logger.error(self._last_error)
            return False

    def disconnect(self) -> None:
        self._ticker    = None
        self._connected = False
        self._candle_cache.clear()
        logger.info("Desconectado del mercado.")

    def reconnect(self) -> bool:
        self.disconnect()
        time.sleep(2)
        return self.connect()

    # ─── Estado ───────────────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_error(self) -> str:
        return self._last_error

    # ─── Precio actual ────────────────────────────────────────────────────────

    def get_market_data(self) -> MarketData:
        if not self._connected or self._ticker is None:
            return MarketData(
                symbol=self.symbol,
                connected=False,
                error=self._last_error or "Sin conexión al mercado.",
            )
        try:
            info = self._ticker.fast_info
            last = float(info.last_price) if info.last_price else 0.0
            if last == 0.0:
                # Fallback: última vela de 1 minuto
                df = self._ticker.history(period="1d", interval="1m")
                if not df.empty:
                    last = float(df["Close"].iloc[-1])

            # Yahoo Finance no diferencia bid/ask directamente; estimamos spread
            bid = round(last - 0.15, 2)   # spread típico ORO ~$0.30
            ask = round(last + 0.15, 2)

            self._last_price = last
            return MarketData(
                symbol    = self.symbol,
                bid       = bid,
                ask       = ask,
                last      = last,
                spread    = 0.30,
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                source    = "Yahoo Finance",
                connected = True,
            )
        except Exception as e:
            err = f"Error obteniendo precio: {e}"
            logger.error(err)
            self._connected = False
            return MarketData(
                symbol=self.symbol, connected=False, error=err
            )

    def get_current_price(self) -> float:
        """Retorna el último precio disponible."""
        if self._last_price > 0:
            return self._last_price
        md = self.get_market_data()
        return md.last

    # ─── Velas OHLCV ─────────────────────────────────────────────────────────

    def get_candles(
        self,
        timeframe: str = "M5",
        count: int = 210,
        force_refresh: bool = False,
    ) -> Optional[pd.DataFrame]:
        """
        Descarga velas OHLCV desde Yahoo Finance.
        Retorna DataFrame con columnas: Open, High, Low, Close, Volume.
        Retorna None si no hay datos.
        """
        if not self._connected or self._ticker is None:
            return None

        tf_info = TIMEFRAMES.get(timeframe)
        if tf_info is None:
            logger.error(f"Temporalidad no reconocida: {timeframe}")
            return None

        yf_interval = tf_info["yf"]
        period      = TIMEFRAME_PERIOD.get(yf_interval, "5d")

        # Cache: no volver a descargar si los datos son recientes
        cache = self._candle_cache.get(timeframe)
        now_ts = time.time()
        cache_ttl = tf_info["minutes"] * 30   # TTL = media vela
        if (
            not force_refresh
            and cache is not None
            and (now_ts - cache["ts"]) < cache_ttl
        ):
            return cache["df"]

        try:
            df = self._ticker.history(period=period, interval=yf_interval)
            if df is None or df.empty:
                logger.warning(f"Sin datos para {timeframe} ({yf_interval})")
                return None

            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.dropna(inplace=True)

            # Guardar cache
            self._candle_cache[timeframe] = {"df": df, "ts": now_ts}
            logger.debug(f"Velas {timeframe}: {len(df)} descargadas.")
            return df

        except Exception as e:
            logger.error(f"Error descargando velas {timeframe}: {e}")
            return None

    # ─── Verificar símbolo ────────────────────────────────────────────────────

    def verify_symbol(self) -> tuple:
        """Retorna (ok: bool, message: str)."""
        if not _YF_AVAILABLE:
            return False, "yfinance no está instalado."
        try:
            ticker = yf.Ticker(self.symbol)
            df = ticker.history(period="1d", interval="5m")
            if df is None or df.empty:
                return False, (
                    f"El símbolo '{self.symbol}' no devuelve datos. "
                    "Prueba con 'XAUUSD=X' o 'GC=F'."
                )
            return True, f"Símbolo '{self.symbol}' verificado OK."
        except Exception as e:
            return False, f"Error verificando símbolo: {e}"

    # ─── Información de disponibilidad ───────────────────────────────────────

    @staticmethod
    def is_library_available() -> bool:
        return _YF_AVAILABLE

    def get_status_dict(self) -> Dict[str, Any]:
        return {
            "connected":    self._connected,
            "symbol":       self.symbol,
            "source":       "Yahoo Finance",
            "library_ok":   _YF_AVAILABLE,
            "last_error":   self._last_error,
            "last_price":   self._last_price,
        }

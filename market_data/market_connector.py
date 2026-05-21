"""
Conector de mercado multi-fuente para XAUUSD/ORO.

Fuentes en orden de prioridad:
  1. Yahoo Finance GC=F  — Gold Futures CME (datos reales, gratis)
  2. Yahoo Finance GLD   — ETF de Oro (fallback)
  3. Yahoo Finance IAU   — ETF de Oro alternativo (fallback)

Símbolo predeterminado: GC=F (confirmado funcionando mayo 2026)
Nota: XAUUSD=X fue descontinuado por Yahoo Finance — NO usar.
"""
import time
from datetime import datetime
from typing import Optional, Dict, Any

import pandas as pd

from config import (
    DEFAULT_YAHOO_SYMBOL, SYMBOL_ALTERNATIVES,
    TIMEFRAMES, TIMEFRAME_PERIOD, get_logger,
)
from models import MarketData

logger = get_logger("market_connector")

try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    yf = None
    _YF_OK = False
    logger.error("yfinance no instalado. Ejecuta: pip install yfinance")

try:
    import requests as _req
    _REQ_OK = True
except ImportError:
    _req = None
    _REQ_OK = False


# Factor de conversión GC=F → precio spot aproximado
# GC=F es el contrato de futuros más cercano, precio muy similar al spot
_GC_TO_SPOT_FACTOR = 1.0   # No se aplica conversión; GC=F ya está en USD/oz


class MarketConnector:
    """
    Obtiene precios y velas de ORO en tiempo real.
    Usa Yahoo Finance GC=F como fuente principal — sin costo, sin API key.
    """

    # Orden de símbolos a intentar
    _SYMBOL_ORDER = ["GC=F", "GLD", "IAU"]

    def __init__(self, symbol: str = DEFAULT_YAHOO_SYMBOL):
        self.symbol          = symbol
        self._active_symbol  = symbol     # Símbolo que realmente funciona
        self._ticker         = None
        self._last_price     = 0.0
        self._connected      = False
        self._last_error     = ""
        self._candle_cache: Dict[str, Dict] = {}
        # GLD y IAU no son spot, pero sus precios se pueden escalar
        self._price_scale    = 1.0        # Para GLD: x10 aprox; para IAU: x49 aprox

    # ─── Conexión ─────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        if not _YF_OK:
            self._connected  = False
            self._last_error = "yfinance no instalado. Ejecuta: pip install yfinance"
            return False

        # Intentar cada símbolo alternativo hasta encontrar uno que devuelva datos
        symbols_to_try = [self.symbol] + [s for s in self._SYMBOL_ORDER if s != self.symbol]

        for sym in symbols_to_try:
            ok, price = self._try_symbol(sym)
            if ok and price > 0:
                self._active_symbol = sym
                self._last_price    = price
                self._connected     = True
                self._last_error    = ""
                self._ticker        = yf.Ticker(sym)
                # Escalar precio si usamos ETF en vez de futuros
                if sym == "GLD":
                    self._price_scale = 10.0   # GLD ≈ 1/10 del precio del oro
                elif sym == "IAU":
                    self._price_scale = 49.0   # IAU ≈ 1/49 del precio del oro
                else:
                    self._price_scale = 1.0
                logger.info(f"Mercado conectado via Yahoo Finance — símbolo activo: {sym} | Precio: ${price:.2f}")
                return True

        self._connected  = False
        self._last_error = (
            "No se pudo obtener datos de Yahoo Finance. "
            "Verifica tu conexión a internet e intenta de nuevo."
        )
        logger.error(self._last_error)
        return False

    def _try_symbol(self, sym: str) -> tuple:
        """Intenta conectar a un símbolo. Retorna (ok, precio)."""
        try:
            t   = yf.Ticker(sym)
            df  = t.history(period="1d", interval="5m")
            if df is None or df.empty:
                return False, 0.0
            price = float(df["Close"].iloc[-1])
            # Escalar ETFs al precio del oro
            if sym == "GLD":
                price *= 10.0
            elif sym == "IAU":
                price *= 49.0
            return True, price
        except Exception as e:
            logger.debug(f"Símbolo {sym} falló: {e}")
            return False, 0.0

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

    @property
    def active_symbol(self) -> str:
        return self._active_symbol

    # ─── Precio actual ────────────────────────────────────────────────────────

    def get_market_data(self) -> MarketData:
        if not self._connected or self._ticker is None:
            return MarketData(
                symbol    = self._active_symbol,
                connected = False,
                error     = self._last_error or "Sin conexión al mercado.",
            )
        try:
            # fast_info es la forma más rápida — sin descargar historial
            info  = self._ticker.fast_info
            last  = float(info.last_price) if info.last_price else 0.0

            if last <= 0:
                # Fallback: última vela de 5 minutos
                df = self._ticker.history(period="1d", interval="5m")
                if not df.empty:
                    last = float(df["Close"].iloc[-1])

            # Aplicar escala si es ETF
            last *= self._price_scale

            if last <= 0:
                return MarketData(
                    symbol=self._active_symbol, connected=False,
                    error="Precio obtenido fue 0. Reconectando...",
                )

            self._last_price = last
            spread = round(last * 0.00015, 2)   # ~0.015% spread típico oro
            bid    = round(last - spread / 2, 2)
            ask    = round(last + spread / 2, 2)

            return MarketData(
                symbol    = self._active_symbol,
                bid       = bid,
                ask       = ask,
                last      = last,
                spread    = spread,
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                source    = f"Yahoo Finance ({self._active_symbol})",
                connected = True,
            )
        except Exception as e:
            err = f"Error obteniendo precio: {e}"
            logger.warning(err)
            # No desconectar por un error puntual — podría ser temporal
            return MarketData(
                symbol=self._active_symbol, connected=False, error=err
            )

    def get_current_price(self) -> float:
        if self._last_price > 0:
            return self._last_price
        md = self.get_market_data()
        return md.last

    # ─── Velas OHLCV ─────────────────────────────────────────────────────────

    def get_candles(
        self,
        timeframe:     str = "M5",
        count:         int = 210,
        force_refresh: bool = False,
    ) -> Optional[pd.DataFrame]:
        """
        Descarga velas OHLCV desde Yahoo Finance.
        Retorna DataFrame con columnas: Open, High, Low, Close, Volume.
        Aplica escala si el símbolo activo es un ETF.
        """
        if not self._connected or self._ticker is None:
            logger.warning("get_candles: no conectado al mercado.")
            return None

        tf_info = TIMEFRAMES.get(timeframe)
        if tf_info is None:
            logger.error(f"Temporalidad no reconocida: {timeframe}")
            return None

        yf_interval = tf_info["yf"]
        period      = TIMEFRAME_PERIOD.get(yf_interval, "5d")

        # Cache para no sobrecargar Yahoo Finance
        cache     = self._candle_cache.get(timeframe)
        now_ts    = time.time()
        cache_ttl = tf_info["minutes"] * 30
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

            # Escalar precio de ETF a precio de oro real
            if self._price_scale != 1.0:
                for col in ["Open", "High", "Low", "Close"]:
                    df[col] = df[col] * self._price_scale

            self._candle_cache[timeframe] = {"df": df, "ts": now_ts}
            logger.debug(f"Velas {timeframe}: {len(df)} descargadas (símbolo {self._active_symbol}).")
            return df

        except Exception as e:
            logger.error(f"Error descargando velas {timeframe}: {e}")
            return None

    # ─── Info y estado ────────────────────────────────────────────────────────

    @staticmethod
    def is_library_available() -> bool:
        return _YF_OK

    def get_status_dict(self) -> Dict[str, Any]:
        return {
            "connected":     self._connected,
            "symbol":        self.symbol,
            "active_symbol": self._active_symbol,
            "source":        "Yahoo Finance",
            "library_ok":    _YF_OK,
            "last_error":    self._last_error,
            "last_price":    self._last_price,
            "price_scale":   self._price_scale,
        }

    def verify_symbol(self) -> tuple:
        if not _YF_OK:
            return False, "yfinance no instalado."
        ok, price = self._try_symbol(self._active_symbol or self.symbol)
        if ok:
            return True, f"Símbolo '{self._active_symbol}' OK — precio ${price:.2f}"
        return False, f"Símbolo '{self.symbol}' sin datos. Intentando alternativas..."

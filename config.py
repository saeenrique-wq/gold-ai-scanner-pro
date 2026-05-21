import os
import logging

# ─── Rutas del proyecto ────────────────────────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "data")
LOGS_DIR  = os.path.join(BASE_DIR, "logs")
DB_PATH   = os.path.join(DATA_DIR, "scanner.db")
LOG_PATH  = os.path.join(LOGS_DIR, "scanner.log")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

# ─── Símbolo y mercado ────────────────────────────────────────────────────────
# GC=F = Gold Futures en CME (funciona, precio real ~$4533/oz en mayo 2026)
# XAUUSD=X fue descontinuado por Yahoo Finance — NO usar
DEFAULT_YAHOO_SYMBOL   = "GC=F"
DEFAULT_DISPLAY_SYMBOL = "XAUUSD"
SYMBOL_ALTERNATIVES    = ["GC=F", "GLD", "IAU"]

# ─── Temporalidades ───────────────────────────────────────────────────────────
# Mapa nombre → intervalo de yfinance → minutos
TIMEFRAMES = {
    "M1":  {"yf": "1m",  "minutes": 1},
    "M5":  {"yf": "5m",  "minutes": 5},
    "M15": {"yf": "15m", "minutes": 15},
    "M30": {"yf": "30m", "minutes": 30},
    "H1":  {"yf": "60m", "minutes": 60},
}

# Periodos de historia compatibles con yfinance por intervalo
TIMEFRAME_PERIOD = {
    "1m":  "1d",
    "5m":  "5d",
    "15m": "60d",
    "30m": "60d",
    "60m": "730d",
}

# ─── Indicadores ─────────────────────────────────────────────────────────────
EMA_FAST      = 50
EMA_SLOW      = 200
RSI_PERIOD    = 14
RSI_BUY_MIN   = 45
RSI_BUY_MAX   = 70
RSI_SELL_MIN  = 30
RSI_SELL_MAX  = 55
MACD_FAST     = 12
MACD_SLOW     = 26
MACD_SIGNAL   = 9
ATR_PERIOD    = 14
MIN_ATR_VALUE = 1.00   # Volatilidad mínima en USD para ORO (ajustado para GC=F ~$4500)

# ─── Estrategia ───────────────────────────────────────────────────────────────
# 6/10 confirmaciones: filtra ruido pero genera suficientes señales buenas
# La IA (Ollama) hace el filtro final para mantener efectividad >80%
MIN_CONFIRMATIONS  = 6   # Subido a 6 para mayor calidad (no cantidad)
MIN_RR_RATIO       = 2.0 # Mínimo riesgo-beneficio 1:2
MAX_WEEKLY_SIGNALS = 50  # Límite real según instrucción del usuario
WEEKLY_TARGET_WIN  = 40  # Objetivo de ganadas (80%)
CANDLES_NEEDED     = 100 # Mínimo para calcular indicadores

# ─── Ollama ───────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL    = "llama3.2:3b"
OLLAMA_TIMEOUT  = 90   # 90s para dar tiempo al modelo (incluye carga en frío)

# ─── Planes de capital ───────────────────────────────────────────────────────
CAPITAL_PLANS = {
    200:  {"lot": 0.01, "risk_usd": 7,  "min_profit": 14},
    500:  {"lot": 0.03, "risk_usd": 15, "min_profit": 30},
    1000: {"lot": 0.05, "risk_usd": 25, "min_profit": 50},
}

# ─── Scanner ─────────────────────────────────────────────────────────────────
SCAN_INTERVAL_SECONDS = 30   # Cada 30s: más frecuente para no perder señales
PRICE_POLL_SECONDS    = 10   # Precio actualizado cada 10s
TRACKER_INTERVAL      = 15   # TP/SL revisados cada 15s

# ─── Colores de la interfaz ──────────────────────────────────────────────────
COLOR_BUY        = "#00ff88"
COLOR_SELL       = "#ff4444"
COLOR_GOLD       = "#ffd700"
COLOR_BLUE_NEON  = "#00bfff"
COLOR_PURPLE     = "#bf5fff"
COLOR_REJECTED   = "#888888"
COLOR_POSSIBLE   = "#ffee44"
COLOR_BG_DARK    = "#0d0d1a"

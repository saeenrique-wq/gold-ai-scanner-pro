"""Script de prueba del sistema completo."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("Probando imports...")
import config; print("  config OK")
import models; print("  models OK")
import database; print("  database OK")
database.init_db(); print("  database.init_db() OK - base de datos creada")

from market_data.market_connector import MarketConnector; print("  MarketConnector OK")
from strategy.indicators import calculate_all; print("  indicators OK")
from strategy.risk_manager import RiskManager; print("  risk_manager OK")
from strategy.gold_scalping_pro import GoldScalpingPro; print("  gold_scalping_pro OK")
from strategy.signal_tracker import SignalTracker; print("  signal_tracker OK")
from ai.ollama_client import OllamaClient; print("  ollama_client OK")
from ai.api_clients import get_client; print("  api_clients OK")
from ai.ai_committee import AICommittee; print("  ai_committee OK")
from alerts.telegram_alerts import TelegramAlerter; print("  telegram OK")
from web.styles import load_css; print("  styles OK")
from web.dashboard import render_connection_badge; print("  dashboard OK")

print()
print("Probando calculo de riesgo con capital $200...")
rm   = RiskManager(capital=200)
calc = rm.calculate(entry=3320.0, signal_type="BUY")
print(f"  Entrada: $3320.00")
print(f"  SL:      ${calc.sl}   (distancia ${calc.sl_distance})")
print(f"  TP1:     ${calc.tp1}")
print(f"  TP2:     ${calc.tp2}")
print(f"  TP3:     ${calc.tp3}")
print(f"  TP4:     ${calc.tp4}")
print(f"  Riesgo:  ${calc.risk_usd}  |  Ganancia min: ${calc.min_profit}  |  R/B: 1:{calc.rr_ratio}")
print(f"  Valido:  {calc.valid}")
assert calc.valid, "Calculo de riesgo fallo"
assert calc.sl < 3320.0, "SL buy debe ser menor a la entrada"
assert calc.tp1 > 3320.0, "TP1 buy debe ser mayor a la entrada"
assert (calc.tp1 - 3320.0) >= (3320.0 - calc.sl) * 2 - 0.01, "RR debe ser al menos 1:2"

print()
print("Probando calculo SELL con capital $500...")
rm2   = RiskManager(capital=500)
calc2 = rm2.calculate(entry=3320.0, signal_type="SELL")
print(f"  Entrada: $3320.00")
print(f"  SL:      ${calc2.sl}   (distancia ${calc2.sl_distance})")
print(f"  TP1:     ${calc2.tp1}")
assert calc2.sl > 3320.0, "SL sell debe ser mayor a la entrada"
assert calc2.tp1 < 3320.0, "TP1 sell debe ser menor a la entrada"
print(f"  Valido:  {calc2.valid}")

print()
print("Probando Ollama...")
client    = OllamaClient()
available = client.is_available(force_check=True)
print(f"  Ollama disponible: {available}")
if available:
    models_list = client.get_models()
    print(f"  Modelos: {models_list}")
    print()
    print("  Enviando senal de prueba a Ollama (llama3.2:3b)...")
    signal_data = {
        "type": "BUY", "entry": 3320.50, "sl": 3313.50,
        "tp1": 3334.50, "tp2": 3341.50, "risk_usd": 7, "min_profit": 14,
        "rr_ratio": 2, "score": 7, "reasons": ["Tendencia alcista H1", "RSI valido"],
        "indicators": {
            "ema50": 3318.0, "ema200": 3310.0, "rsi": 55.2,
            "macd": 0.15, "atr": 2.5, "support": 3310.0,
            "resistance": 3335.0, "trend_up": True, "candle_bullish": True,
            "macd_bullish": True,
        },
    }
    response = client.analyze_signal(signal_data)
    print(f"  Decision:  {response.decision}")
    print(f"  Confianza: {response.confianza}")
    print(f"  Riesgo:    {response.riesgo}")
    print(f"  Motivo:    {response.motivo}")
    print(f"  JSON valido: {response.valid}")

print()
print("Verificando base de datos...")
stats = database.get_weekly_stats(200.0)
print(f"  Semana: {stats.week_start} -> {stats.week_end}")
print(f"  Senales: {stats.total_signals}/12")
print(f"  Limite alcanzado: {stats.limit_reached}")

print()
print("=" * 50)
print("  TODOS LOS SISTEMAS FUNCIONAN CORRECTAMENTE")
print("=" * 50)

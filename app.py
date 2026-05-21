"""
GOLD AI SCANNER PRO — MVP Local
Auto-inicia al abrir. Muestra precio en vivo, estado y señales.
Ejecutar: streamlit run app.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import threading, time, json
from datetime import datetime
from typing import Optional, Dict, Any

import streamlit as st

# ── Base de datos (primero siempre) ──────────────────────────────────────────
import database as db
db.init_db()

from config import (
    DEFAULT_YAHOO_SYMBOL, TIMEFRAMES, CAPITAL_PLANS,
    SCAN_INTERVAL_SECONDS, PRICE_POLL_SECONDS, TRACKER_INTERVAL,
    get_logger,
)
from models import Signal
from market_data.market_connector import MarketConnector
from strategy.indicators    import calculate_all
from strategy.risk_manager  import RiskManager
from strategy.gold_scalping_pro import GoldScalpingPro
from strategy.signal_tracker    import SignalTracker
from ai.ollama_client  import OllamaClient
from ai.ai_committee   import AICommittee
from alerts.telegram_alerts import TelegramAlerter
from web.styles       import load_css
from web.dashboard    import render_signal_card, render_history_table, render_weekly_bar
from web.audio_alerts import play_sounds

logger = get_logger("app")

# ═══════════════════════════════════════════════════════════════════════════════
#  ESTADO GLOBAL — persiste entre reruns de Streamlit en el mismo proceso
# ═══════════════════════════════════════════════════════════════════════════════
_LOCK  = threading.Lock()
_STATE: Dict[str, Any] = {
    "running":          False,
    "thread":           None,
    "stop_event":       threading.Event(),
    # Mercado
    "market_connected": False,
    "current_price":    0.0,
    "bid":              0.0,
    "ask":              0.0,
    "active_symbol":    "",
    # Ollama
    "ollama_connected": False,
    # Señales
    "last_signal":      None,
    # Mensajes
    "status_msg":       "Iniciando...",
    "error_msg":        "",
    "events":           [],
    "scan_count":       0,
    "last_scan_time":   "",
    # Cola de sonidos: ["BUY","SELL","WIN","LOSS"]
    "sound_queue":      [],
}

# Instancias globales del scanner
_connector: Optional[MarketConnector] = None
_ollama:    Optional[OllamaClient]    = None
_strategy:  Optional[GoldScalpingPro] = None
_tracker:   Optional[SignalTracker]   = None
_committee: Optional[AICommittee]     = None
_risk:      Optional[RiskManager]     = None


def _s(key: str, val: Any) -> None:
    with _LOCK:
        _STATE[key] = val

def _g() -> Dict:
    with _LOCK:
        return dict(_STATE)

def _log(msg: str) -> None:
    with _LOCK:
        _STATE["events"].insert(0, f"{datetime.now().strftime('%H:%M:%S')} {msg}")
        _STATE["events"] = _STATE["events"][:30]

def _sound(sound_type: str) -> None:
    """Encola un sonido: BUY, SELL, WIN, LOSS."""
    with _LOCK:
        _STATE["sound_queue"].append(sound_type)


# ═══════════════════════════════════════════════════════════════════════════════
#  HILO DEL SCANNER
# ═══════════════════════════════════════════════════════════════════════════════

def _scanner_loop(symbol, tf_confirm, tf_trend,
                  capital, risk_usd, lot_size,
                  ollama_url, ollama_model,
                  stop_event: threading.Event) -> None:
    global _connector, _ollama, _strategy, _tracker, _committee, _risk

    # ── Crear instancias ─────────────────────────────────────────────────────
    _connector = MarketConnector(symbol=symbol)
    _ollama    = OllamaClient(base_url=ollama_url, model=ollama_model)
    _strategy  = GoldScalpingPro()
    _tracker   = SignalTracker()
    _risk      = RiskManager(capital=capital)
    _committee = AICommittee(_ollama)

    # ── Conectar mercado ─────────────────────────────────────────────────────
    _s("status_msg", "Conectando al mercado en vivo...")
    _s("market_connected", False)

    if not _connector.connect():
        _s("error_msg",    _connector.last_error)
        _s("status_msg",   "Error de conexión al mercado. Reintentando en 30s...")
        _s("market_connected", False)
        # Reintentar cada 30s hasta que funcione o se detenga
        for _ in range(10):
            if stop_event.is_set():
                return
            time.sleep(30)
            if _connector.connect():
                break
        if not _connector.is_connected:
            _s("running", False)
            return

    # Precio inicial inmediato
    md0 = _connector.get_market_data()
    _s("market_connected", True)
    _s("active_symbol",    _connector.active_symbol)
    _s("error_msg",        "")
    if md0.connected and md0.last > 0:
        _s("current_price", md0.last)
        _s("bid",           md0.bid)
        _s("ask",           md0.ask)
    _log(f"Mercado conectado — {_connector.active_symbol} ${md0.last:.2f}")

    # ── Verificar Ollama ─────────────────────────────────────────────────────
    ollama_ok = _ollama.is_available()
    _s("ollama_connected", ollama_ok)
    if ollama_ok:
        _log(f"Ollama listo ({ollama_model})")
        _ollama.warmup_async()
    else:
        _log("Ollama no detectado — señales sin confirmación IA")

    _s("status_msg", "Buscando señales...")

    last_price_poll    = 0.0
    last_scan_time     = 0.0
    last_tracker_time  = 0.0
    last_ollama_check  = 0.0

    # ── Bucle principal ──────────────────────────────────────────────────────
    while not stop_event.is_set():
        now = time.time()

        # Actualizar precio
        if (now - last_price_poll) >= PRICE_POLL_SECONDS:
            try:
                md = _connector.get_market_data()
                if md.connected and md.last > 0:
                    _s("current_price",    md.last)
                    _s("bid",              md.bid)
                    _s("ask",              md.ask)
                    _s("market_connected", True)
                    _s("error_msg",        "")
                else:
                    _s("market_connected", False)
                    _s("error_msg",        md.error)
                    _connector.reconnect()
            except Exception as e:
                logger.error(f"Error precio: {e}")
            last_price_poll = now

        # Verificar Ollama cada 60 segundos (por si el usuario lo inicia después)
        if (now - last_ollama_check) >= 60:
            try:
                ok = _ollama.is_available(force_check=True)
                _s("ollama_connected", ok)
            except Exception:
                pass
            last_ollama_check = now

        # Revisar TP/SL de señales activas
        if (now - last_tracker_time) >= TRACKER_INTERVAL:
            price = _STATE["current_price"]
            if price > 0 and _tracker:
                try:
                    for ev in _tracker.update_all(price):
                        _log(ev)
                        # Sonido según resultado del evento
                        if "SL TOCADO" in ev or "PÉRDIDA" in ev:
                            _sound("LOSS")
                        elif any(x in ev for x in ("TP1","TP2","TP3","TP4","ALCANZADO","🏆","✅")):
                            _sound("WIN")
                except Exception as e:
                    logger.error(f"Tracker error: {e}")
            last_tracker_time = now

        # Escaneo técnico + IA
        if (now - last_scan_time) >= SCAN_INTERVAL_SECONDS:
            if not db.weekly_limit_reached():
                # No escanear si ya hay una señal activa esperando resultado
                activas = db.get_active_signals()
                if activas:
                    _s("status_msg",
                       f"Señal #{activas[0]['id']} activa — esperando resultado...")
                else:
                    try:
                        _run_scan(tf_confirm, tf_trend, risk_usd, lot_size)
                    except Exception as e:
                        logger.error(f"Error scan: {e}", exc_info=True)
                        _log(f"Error scan: {str(e)[:60]}")
            else:
                _s("status_msg", "Límite semanal de señales alcanzado.")
            with _LOCK:
                _STATE["scan_count"]    += 1
                _STATE["last_scan_time"] = datetime.now().strftime("%H:%M:%S")
            last_scan_time = now

        time.sleep(3)

    _s("running", False)
    _s("status_msg", "Scanner detenido.")
    if _connector:
        _connector.disconnect()


_LAST_SIGNAL_KEY: Dict[str, Any] = {"type": "", "entry": 0.0, "ts": 0.0}
SIGNAL_COOLDOWN_SECS = 900   # 15 minutos entre señales del mismo tipo/precio
SIGNAL_PRICE_TOLERANCE = 5.0 # Si la entrada es casi igual, ignorar ($5 de diferencia)


def _is_duplicate(signal_type: str, entry: float) -> bool:
    """Evita publicar la misma señal repetida. Cooldown de 15 minutos."""
    last = _LAST_SIGNAL_KEY
    if (last["type"] == signal_type
            and abs(last["entry"] - entry) < SIGNAL_PRICE_TOLERANCE
            and (time.time() - last["ts"]) < SIGNAL_COOLDOWN_SECS):
        mins_left = int((SIGNAL_COOLDOWN_SECS - (time.time() - last["ts"])) / 60)
        _s("status_msg", f"Buscando señal... (cooldown {mins_left}min)")
        return True
    return False


_SCAN_LOCK = threading.Lock()   # evita que 2 hilos escaneen al mismo tiempo

def _run_scan(tf_confirm: str, tf_trend: str, risk_usd: float, lot_size: float) -> None:
    global _connector, _risk, _strategy, _committee

    # Solo un escaneo a la vez (por si hay 2 hilos accidentales)
    if not _SCAN_LOCK.acquire(blocking=False):
        return
    try:
        _run_scan_inner(tf_confirm, tf_trend, risk_usd, lot_size)
    finally:
        _SCAN_LOCK.release()


def _run_scan_inner(tf_confirm: str, tf_trend: str, risk_usd: float, lot_size: float) -> None:
    global _connector, _risk, _strategy, _committee

    df_m5  = _connector.get_candles(tf_confirm, 210, force_refresh=True)
    df_h1  = _connector.get_candles(tf_trend,   210, force_refresh=True)
    df_m15 = _connector.get_candles("M15",       100, force_refresh=True)

    if df_m5 is None or df_h1 is None:
        _s("status_msg", "Esperando datos del mercado...")
        return

    signal_raw = _strategy.analyze(df_m5, df_h1, df_m15)
    if signal_raw is None:
        _s("status_msg", f"🔍 Analizando mercado... ({datetime.now().strftime('%H:%M')})")
        return

    entry = signal_raw["entry"]

    # Anti-duplicado nivel 1: memoria rápida (15 min cooldown)
    if _is_duplicate(signal_raw["type"], entry):
        return

    # Anti-duplicado nivel 2: base de datos (60 min, $8 tolerancia)
    # Esto sobrevive reinicios de la app y múltiples hilos
    if db.recent_duplicate_exists(signal_raw["type"], entry, minutes=60, tolerance=8.0):
        _s("status_msg", f"🔍 Señal {signal_raw['type']} ya registrada hace menos de 1h — buscando otra...")
        _LAST_SIGNAL_KEY["type"]  = signal_raw["type"]
        _LAST_SIGNAL_KEY["entry"] = entry
        _LAST_SIGNAL_KEY["ts"]    = time.time()
        return

    calc  = _risk.calculate(entry, signal_raw["type"], lot_size, risk_usd)
    if not calc.valid:
        _log(f"Descarté señal {signal_raw['type']}: {calc.error}")
        return
    if not _risk.check_rr_ratio(entry, calc.sl, calc.tp1, signal_raw["type"]):
        _log("Descarté señal: ganancia posible menor al doble del riesgo")
        return

    _s("status_msg", "🤖 Señal detectada — IA revisando...")
    _log(f"Señal {signal_raw['type']} puntaje {signal_raw['score']}/10 — IA analizando")

    ai_data = {
        "type": signal_raw["type"], "entry": entry,
        "sl": calc.sl, "tp1": calc.tp1, "tp2": calc.tp2,
        "risk_usd": calc.risk_usd, "min_profit": calc.min_profit,
        "rr_ratio": calc.rr_ratio, "score": signal_raw["score"],
        "reasons": signal_raw["reasons"], "indicators": signal_raw["indicators"],
    }
    ai = _committee.evaluate(ai_data)

    if not ai.get("approved"):
        _log(f"IA rechazó: {ai.get('motivo','')[:60]}")
        _s("status_msg", f"Buscando señal... (IA rechazó: {ai.get('motivo','')[:40]})")
        return

    # ── Guardar señal aprobada ─────────────────────────────────────────────
    sig = Signal(
        symbol=db.get_setting("display_symbol","XAUUSD"),
        timeframe=tf_confirm, signal_type=signal_raw["type"],
        entry=entry, sl=calc.sl, tp1=calc.tp1, tp2=calc.tp2,
        tp3=calc.tp3, tp4=calc.tp4,
        risk_usd=calc.risk_usd, expected_profit=calc.min_profit,
        rr_ratio=calc.rr_ratio, lot_size=calc.lot_size,
        status="APROBADA",
        ai_provider=ai.get("provider","Ollama"),
        ai_decision=ai.get("decision","APROBAR"),
        ai_confidence=ai.get("confianza","MEDIA"),
        ai_reason=ai.get("motivo",""),
        score=signal_raw["score"],
        signal_style=db.get_setting("signal_style","Scalping"),
    )
    sig_id = db.save_signal(sig)

    # Actualizar tracker anti-duplicado
    _LAST_SIGNAL_KEY["type"]  = sig.signal_type
    _LAST_SIGNAL_KEY["entry"] = entry
    _LAST_SIGNAL_KEY["ts"]    = time.time()

    sig_dict = {
        "id": sig_id, "signal_type": sig.signal_type, "symbol": sig.symbol,
        "timeframe": sig.timeframe, "entry": sig.entry, "sl": sig.sl,
        "tp1": sig.tp1, "tp2": sig.tp2, "tp3": sig.tp3, "tp4": sig.tp4,
        "risk_usd": sig.risk_usd, "expected_profit": sig.expected_profit,
        "rr_ratio": sig.rr_ratio, "lot_size": sig.lot_size,
        "status": sig.status, "ai_decision": sig.ai_decision,
        "ai_confidence": sig.ai_confidence, "ai_reason": sig.ai_reason,
        "score": sig.score, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _s("last_signal", sig_dict)
    emoji = "🟢" if sig.signal_type == "BUY" else "🔴"
    _s("status_msg", f"{emoji} SEÑAL {sig.signal_type} #{sig_id} — ${entry:.2f} | IA: APROBADA")
    _log(f"{emoji} Señal #{sig_id} {sig.signal_type} ${entry:.2f} — TP1 ${calc.tp1:.2f}")
    _sound(sig.signal_type)  # BUY o SELL


# ── Iniciar / Detener ─────────────────────────────────────────────────────────

def start_scanner() -> None:
    if _STATE["running"]:
        return
    symbol       = db.get_setting("symbol",            DEFAULT_YAHOO_SYMBOL)
    capital      = float(db.get_setting("capital",     "200"))
    risk_usd     = float(db.get_setting("risk_usd",    "7"))
    lot_size     = float(db.get_setting("lot_size",    "0.01"))
    tf_confirm   = db.get_setting("timeframe_confirm", "M5")
    tf_trend     = db.get_setting("timeframe_trend",   "H1")
    ollama_url   = db.get_setting("ollama_url",        "http://localhost:11434")
    ollama_model = db.get_setting("ollama_model",      "llama3.2:3b")

    stop_ev = threading.Event()
    with _LOCK:
        _STATE["stop_event"]  = stop_ev
        _STATE["running"]     = True
        _STATE["events"]      = []
        _STATE["scan_count"]  = 0
        _STATE["error_msg"]   = ""
        _STATE["status_msg"]  = "Iniciando..."

    t = threading.Thread(
        target  = _scanner_loop,
        args    = (symbol, tf_confirm, tf_trend, capital, risk_usd,
                   lot_size, ollama_url, ollama_model, stop_ev),
        daemon  = True,
        name    = "scanner",
    )
    with _LOCK:
        _STATE["thread"] = t
    t.start()

def stop_scanner() -> None:
    with _LOCK:
        ev = _STATE.get("stop_event")
        if ev:
            ev.set()
        _STATE["running"] = False


# ═══════════════════════════════════════════════════════════════════════════════
#  AUTO-ARRANQUE — garantiza UN SOLO hilo activo en todo el proceso
# ═══════════════════════════════════════════════════════════════════════════════
_START_LOCK = threading.Lock()   # evita que 2 reruns simultáneos inicien 2 hilos

def _autostart() -> None:
    with _START_LOCK:
        thread   = _STATE.get("thread")
        is_alive = thread is not None and thread.is_alive()
        if not _STATE["running"] and not is_alive:
            start_scanner()

_autostart()

# ═══════════════════════════════════════════════════════════════════════════════
#  INTERFAZ
# ═══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="GOLD AI SCANNER PRO",
    page_icon="⚜️",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(load_css(), unsafe_allow_html=True)

# Leer estado fresco en cada render (no cachear)
def _fresh() -> Dict:
    with _LOCK:
        return dict(_STATE)

state = _fresh()

# ── Sonidos pendientes ────────────────────────────────────────────────────────
_pending_sounds = state.get("sound_queue", [])
if _pending_sounds:
    play_sounds(_pending_sounds)
    with _LOCK:
        _STATE["sound_queue"] = []

# ── Título ────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="main-title">⚜ GOLD AI SCANNER PRO</div>'
    '<div class="subtitle">XAUUSD · IA LOCAL · TIEMPO REAL</div>',
    unsafe_allow_html=True,
)

# ── Fila de estado — leer siempre el valor más fresco ────────────────────────
state   = _fresh()          # refrescar justo aquí para los badges
price   = state["current_price"]
mkt_ok  = state["market_connected"]
ia_ok   = state["ollama_connected"]
running = state["running"]

col_mkt, col_ia, col_price, col_scan = st.columns([2, 2, 2, 2])

with col_mkt:
    if mkt_ok:
        st.markdown(
            '<div style="background:#001a0e;border:1px solid #00ff88;border-radius:10px;'
            'padding:14px;text-align:center;">'
            '<div style="color:#00ff88;font-size:1.5rem;">●</div>'
            '<div style="color:#00ff88;font-weight:700;font-size:1rem;">MERCADO CONECTADO</div>'
            f'<div style="color:#888;font-size:0.8rem;">{state["active_symbol"]} — Yahoo Finance</div>'
            '</div>', unsafe_allow_html=True)
    else:
        err_short = (state.get("error_msg","") or "Sin internet o Yahoo Finance caído")[:50]
        st.markdown(
            '<div style="background:#1a0000;border:1px solid #ff4444;border-radius:10px;'
            'padding:14px;text-align:center;">'
            '<div style="color:#ff4444;font-size:1.5rem;">●</div>'
            '<div style="color:#ff4444;font-weight:700;font-size:1rem;">SIN MERCADO</div>'
            f'<div style="color:#888;font-size:0.75rem;">{err_short}</div>'
            '</div>', unsafe_allow_html=True)
        if st.button("🔄 Reconectar mercado", key="btn_reconect_mkt"):
            stop_scanner()
            time.sleep(1)
            start_scanner()
            st.rerun()

with col_ia:
    if ia_ok:
        st.markdown(
            '<div style="background:#0d0020;border:1px solid #bf5fff;border-radius:10px;'
            'padding:14px;text-align:center;">'
            '<div style="color:#bf5fff;font-size:1.5rem;">●</div>'
            '<div style="color:#bf5fff;font-weight:700;font-size:1rem;">IA ACTIVA</div>'
            f'<div style="color:#888;font-size:0.8rem;">Ollama · {db.get_setting("ollama_model","llama3.2:3b")}</div>'
            '</div>', unsafe_allow_html=True)
    else:
        st.markdown(
            '<div style="background:#1a1400;border:1px solid #ffee44;border-radius:10px;'
            'padding:14px;text-align:center;">'
            '<div style="color:#ffee44;font-size:1.5rem;">●</div>'
            '<div style="color:#ffee44;font-weight:700;font-size:1rem;">IA APAGADA</div>'
            '<div style="color:#888;font-size:0.75rem;">Abre Ollama para activar</div>'
            '</div>', unsafe_allow_html=True)
        if st.button("🔄 Reconectar IA", key="btn_reconect_ia"):
            if _ollama:
                ok = _ollama.is_available(force_check=True)
                _s("ollama_connected", ok)
                st.rerun()

with col_price:
    if price > 0:
        st.markdown(
            '<div style="background:#0d0d1a;border:1px solid #ffd700;border-radius:10px;'
            'padding:14px;text-align:center;">'
            f'<div style="font-family:Orbitron,monospace;color:#ffd700;font-size:1.6rem;'
            f'font-weight:900;">${price:,.2f}</div>'
            '<div style="color:#888;font-size:0.8rem;">XAUUSD · Precio actual</div>'
            '</div>', unsafe_allow_html=True)
    else:
        st.markdown(
            '<div style="background:#0d0d1a;border:1px solid #333;border-radius:10px;'
            'padding:14px;text-align:center;">'
            '<div style="color:#555;font-size:1.4rem;">Obteniendo precio...</div>'
            '</div>', unsafe_allow_html=True)

with col_scan:
    stats = db.get_weekly_stats(float(db.get_setting("capital","200")))
    st.markdown(
        '<div style="background:#0d0d1a;border:1px solid #30363d;border-radius:10px;'
        'padding:14px;text-align:center;">'
        f'<div style="color:#ffd700;font-size:1.4rem;font-weight:700;">'
        f'{stats.total_signals}/50</div>'
        '<div style="color:#888;font-size:0.8rem;">Señales esta semana</div>'
        f'<div style="color:#{"00ff88" if stats.won_signals>0 else "888"};font-size:0.8rem;">'
        f'✓ {stats.won_signals} ganadas &nbsp; ✗ {stats.lost_signals} perdidas</div>'
        '</div>', unsafe_allow_html=True)

# ── Mensaje de estado ─────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
if state["error_msg"]:
    st.error(f"⚠️ {state['error_msg']}")
else:
    color = "#00ff88" if running else "#ffee44"
    icon  = "🟢" if running else "🟡"
    st.markdown(
        f'<div style="background:#0d1117;border-left:3px solid {color};'
        f'padding:10px 16px;border-radius:0 8px 8px 0;color:{color};font-size:0.9rem;">'
        f'{icon} {state["status_msg"]}</div>',
        unsafe_allow_html=True)

st.markdown("---")

# ── Pestañas ─────────────────────────────────────────────────────────────────
tab_señal, tab_hist, tab_cfg, tab_ia = st.tabs([
    "⚡ Señal Activa",
    "📋 Historial",
    "⚙️ Configuración",
    "🤖 IA & APIs",
])

# ════════════════════════════════════════════════════════
# SEÑAL ACTIVA
# ════════════════════════════════════════════════════════
with tab_señal:
    # Mostrar SOLO la señal más reciente activa (nunca duplicados)
    active_all = db.get_active_signals()
    # Deduplicar por ID (ya viene ordenado DESC, primer ID = más reciente)
    seen_ids = set()
    active = []
    for sig in active_all:
        if sig["id"] not in seen_ids:
            seen_ids.add(sig["id"])
            active.append(sig)
    # Solo mostrar la señal activa más reciente
    active = active[:1]

    if active:
        sig  = active[0]
        tipo = sig["signal_type"]
        tipo_label = "🟢 COMPRA" if tipo == "BUY" else "🔴 VENTA"

        # Instrucción clara para el usuario
        st.markdown(
            f'<div style="background:#0d1117;border:2px solid '
            f'{"#00ff88" if tipo=="BUY" else "#ff4444"};border-radius:10px;'
            f'padding:14px;margin-bottom:12px;">'
            f'<div style="font-size:1.1rem;font-weight:700;color:'
            f'{"#00ff88" if tipo=="BUY" else "#ff4444"};">'
            f'⚡ {tipo_label} — Entrar al mercado a ${sig["entry"]:.2f}</div>'
            f'<div style="font-size:0.85rem;color:#8b949e;margin-top:6px;">'
            f'Esta señal se generó a ese precio. Si el mercado está cerca, puedes entrar ahora.</div>'
            f'</div>', unsafe_allow_html=True)

        render_signal_card(sig)

        if price > 0:
            dist_sl  = (price - sig["sl"])  if tipo == "BUY" else (sig["sl"]  - price)
            dist_tp1 = (sig["tp1"] - price) if tipo == "BUY" else (price - sig["tp1"])
            diff_entry = price - sig["entry"]

            c1, c2, c3 = st.columns(3)
            c1.metric("Precio ahora",   f"${price:,.2f}",
                      delta=f"{diff_entry:+.2f} vs entrada")
            c2.metric("Riesgo (SL)",    f"${abs(dist_sl):.2f} al stop",
                      delta="si el precio sube" if tipo=="SELL" else "si el precio baja",
                      delta_color="inverse")
            c3.metric("Meta 1 (TP1)",   f"${abs(dist_tp1):.2f} para ganar",
                      delta="si el precio baja" if tipo=="SELL" else "si el precio sube",
                      delta_color="normal")
    elif state.get("last_signal"):
        st.markdown("#### 🔔 Última señal registrada")
        render_signal_card(state["last_signal"])
    else:
        st.markdown(
            '<div style="background:#0d1117;border:1px solid #30363d;border-radius:12px;'
            'padding:40px;text-align:center;">'
            '<div style="font-size:3rem">📡</div>'
            '<div style="color:#ffd700;font-size:1.1rem;margin-top:10px;">Buscando señal de alta probabilidad...</div>'
            '<div style="color:#888;font-size:0.85rem;margin-top:6px;">'
            'Analizando mercado con EMA, RSI, MACD y ATR cada 30 segundos</div>'
            '</div>', unsafe_allow_html=True)

    # Actividad reciente
    events = state.get("events", [])
    if events:
        st.markdown("##### Registro de actividad")
        for ev in events[:12]:
            st.markdown(
                f'<div style="font-size:0.8rem;color:#8b949e;padding:2px 0;'
                f'border-bottom:1px solid #1c2128;">{ev}</div>',
                unsafe_allow_html=True)

# ════════════════════════════════════════════════════════
# HISTORIAL
# ════════════════════════════════════════════════════════
with tab_hist:
    st.markdown("#### 📋 Historial de señales")
    history_all_raw = db.get_signals_history(200)

    # Deduplicar: si hay señales con mismo tipo+entry+sl en menos de 1 hora, queda solo la primera
    seen_sigs: dict = {}
    history_all = []
    for s in reversed(history_all_raw):  # más antiguo primero para conservar el original
        key = (s["signal_type"], round(s["entry"], 0))
        if key not in seen_sigs:
            seen_sigs[key] = s["created_at"]
            history_all.append(s)
        else:
            # si la diferencia es > 2 horas, es una señal diferente (precio similar, otro día)
            from datetime import datetime as _dt
            try:
                t1 = _dt.strptime(seen_sigs[key][:16], "%Y-%m-%d %H:%M")
                t2 = _dt.strptime(s["created_at"][:16], "%Y-%m-%d %H:%M")
                if abs((t2 - t1).total_seconds()) > 7200:
                    seen_sigs[key] = s["created_at"]
                    history_all.append(s)
            except Exception:
                history_all.append(s)
    history_all = list(reversed(history_all))  # más reciente primero

    # ── Efectividad al tope ───────────────────────────────────────────────────
    won_all   = sum(1 for s in history_all if s.get("result") == "GANADA")
    lost_all  = sum(1 for s in history_all if s.get("result") == "PERDIDA")
    total_all = won_all + lost_all
    efectividad = f"{won_all/total_all*100:.0f}%" if total_all > 0 else "—"

    ea, eb, ec, ed = st.columns(4)
    ea.metric("Total señales",  len(history_all))
    eb.metric("Ganadas ✅",     won_all)
    ec.metric("Perdidas ❌",    lost_all)
    ed.metric("Efectividad",    efectividad,
              delta="objetivo 80%" if total_all > 0 else None,
              delta_color="normal" if won_all/max(total_all,1) >= 0.8 else "inverse")

    st.markdown("")

    if history_all:
        cf1, cf2 = st.columns(2)
        with cf1:
            FILTROS = {
                "Todas":          None,
                "Solo COMPRAS":   ("signal_type", "BUY"),
                "Solo VENTAS":    ("signal_type", "SELL"),
                "Ganadas ✅":     ("result",      "GANADA"),
                "Perdidas ❌":    ("result",      "PERDIDA"),
                "En seguimiento": ("status",      "ACTIVA"),
            }
            ft = st.selectbox("Mostrar:", list(FILTROS.keys()), index=0,
                              key="hist_filter_select")
        with cf2:
            ESTILOS = ["Todos los estilos", "Scalping", "Day Trading", "Swing"]
            estilo_ft = st.selectbox("Tipo de operación:", ESTILOS, index=0,
                                     key="hist_estilo_select")

        campo, valor = FILTROS[ft] if FILTROS[ft] else (None, None)
        history = ([s for s in history_all if s.get(campo) == valor]
                   if campo else list(history_all))
        if estilo_ft != "Todos los estilos":
            history = [s for s in history if s.get("signal_style","").lower() == estilo_ft.lower()]

        if history:
            render_history_table(history)
        else:
            st.info("No hay señales con ese filtro todavía.")
    else:
        st.info("No hay señales registradas todavía. El scanner está en búsqueda.")

# ════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ════════════════════════════════════════════════════════
with tab_cfg:
    st.markdown("#### ⚙️ Configuración")
    st.info("Los cambios se aplican automáticamente en el próximo scan.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**¿Cuánto dinero tienes para operar?**")
        cap_op = st.selectbox(
            "Mi capital es:",
            ["$200 (principiante)", "$500 (intermedio)", "$1000 (avanzado)", "Personalizado"],
            key="cap_op_sel",
        )
        cap_map = {"$200 (principiante)": 200, "$500 (intermedio)": 500, "$1000 (avanzado)": 1000}
        if cap_op == "Personalizado":
            capital = float(st.number_input("Capital exacto ($)", min_value=50.0, value=200.0, key="cap_custom"))
        else:
            capital = float(cap_map[cap_op])
        plan = CAPITAL_PLANS.get(int(capital), CAPITAL_PLANS[200])
        st.markdown(
            f'<div style="background:#0d1117;border:1px solid #ffd700;border-radius:8px;'
            f'padding:10px;font-size:0.85rem;">'
            f'📦 Tamaño de operación: <b>{plan["lot"]}</b> lotes<br>'
            f'⛔ Máximo que puedes perder por trade: <b>${plan["risk_usd"]}</b><br>'
            f'✅ Mínimo que ganarás por trade: <b>${plan["min_profit"]}</b>'
            f'</div>', unsafe_allow_html=True
        )
        r_usd = plan["risk_usd"]
        lot   = plan["lot"]

    with c2:
        st.markdown("**Modo de trading**")
        MODOS = {
            "⚡ Scalping — entradas muy rápidas (M5)":   ("M5",  "H1"),
            "📈 Day Trading — operaciones del día (M15)": ("M15", "H1"),
            "🌊 Swing — varios días (M30)":               ("M30", "H1"),
        }
        modo_sel = st.selectbox(
            "¿Cómo quieres operar?",
            list(MODOS.keys()),
            index=0,
            key="modo_sel",
        )
        tf_c, tf_t = MODOS[modo_sel]
        st.markdown(
            '<div style="background:#0d1117;border:1px solid #30363d;border-radius:8px;'
            'padding:8px;font-size:0.82rem;color:#8b949e;">'
            '⚡ <b>Scalping</b> = 1–5 min en operación<br>'
            '📈 <b>Day Trading</b> = 15–60 min en operación<br>'
            '🌊 <b>Swing</b> = horas o días en operación'
            '</div>', unsafe_allow_html=True
        )
        st.markdown("")
        sym_d = st.text_input(
            "Nombre del par:",
            value=db.get_setting("display_symbol","XAUUSD"),
            key="sym_display_input",
        )
        st.caption("🌐 Datos en vivo de Yahoo Finance · Oro (GC=F)")

    if st.button("💾 Guardar y aplicar", use_container_width=True):
        db.set_setting("capital",           str(capital))
        db.set_setting("risk_usd",          str(r_usd))
        db.set_setting("lot_size",          str(lot))
        db.set_setting("timeframe_confirm", tf_c)
        db.set_setting("timeframe_trend",   tf_t)
        db.set_setting("display_symbol",    sym_d)
        st.success("✅ Guardado. El scanner usa la nueva configuración en el próximo ciclo.")

    st.markdown("---")
    st.markdown("**Plan semanal estimado**")
    st.markdown(f"""
| | Valor |
|--|--|
| Capital | ${capital:.0f} |
| Riesgo/op | ${r_usd:.2f} |
| Ganancia mín/op | ${r_usd*2:.2f} |
| Ops/semana | 50 (máx) |
| Estimado ganadas | 40 |
| Estimado perdidas | 10 |
| Neto esperado | **${r_usd*2*40 - r_usd*10:.2f}** |
| Capital final est. | **${capital + r_usd*2*40 - r_usd*10:.2f}** |
""")
    st.caption("⚠️ Estimaciones basadas en el plan. El trading tiene riesgos reales.")

    st.markdown("---")
    c1, c2 = st.columns(2)
    if c1.button("⏹ Detener scanner"):
        stop_scanner()
        st.warning("Scanner detenido. Recarga la página para reiniciar.")
    if c2.button("🔄 Reiniciar scanner"):
        stop_scanner()
        time.sleep(2)
        start_scanner()
        st.success("Reiniciando...")

    st.markdown("---")
    st.markdown("**🗑 Borrar señales de prueba**")
    st.caption("Usa esto si el historial tiene señales repetidas o de prueba.")
    if st.button("🗑 Borrar TODAS las señales del historial", type="secondary"):
        n = db.delete_all_signals()
        _s("last_signal", None)
        st.success(f"✅ {n} señales borradas. El scanner sigue corriendo.")

# ════════════════════════════════════════════════════════
# IA & APIs
# ════════════════════════════════════════════════════════
with tab_ia:
    st.markdown("#### 🤖 Inteligencia Artificial")
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Ollama (IA local gratuita)**")
        ol_url   = st.text_input("URL", value=db.get_setting("ollama_url","http://localhost:11434"))
        ol_model = st.selectbox("Modelo", ["llama3.2:3b","gemma4:e4b","codellama:latest"],
                                index=0)
        if st.button("🔍 Verificar Ollama"):
            cl = OllamaClient(base_url=ol_url, model=ol_model)
            if cl.is_available(force_check=True):
                models = cl.get_models()
                st.success(f"✅ Ollama activo | Modelos: {', '.join(models[:4])}")
            else:
                st.error("❌ Ollama no responde. Asegúrate de que esté corriendo.")
        if st.button("💾 Guardar Ollama"):
            db.set_setting("ollama_url",   ol_url)
            db.set_setting("ollama_model", ol_model)
            st.success("Guardado.")

    with c2:
        st.markdown("**Telegram (alertas)**")
        tg_tok = st.text_input("Token bot", type="password",
                               value=db.get_setting("telegram_token",""))
        tg_id  = st.text_input("Chat ID",
                               value=db.get_setting("telegram_chat_id",""))
        cc1, cc2 = st.columns(2)
        if cc1.button("💾 Guardar"):
            db.set_setting("telegram_token",   tg_tok)
            db.set_setting("telegram_chat_id", tg_id)
            st.success("Guardado.")
        if cc2.button("🧪 Probar"):
            ok = TelegramAlerter(tg_tok, tg_id).send("🧪 GOLD AI SCANNER PRO — prueba OK")
            st.success("✅ Enviado.") if ok else st.error("❌ Falló. Revisa token y chat_id.")

        st.markdown("---")
        st.markdown("**IAs externas** (próxima fase)")
        for name in ["OpenAI","Gemini","Groq","OpenRouter"]:
            with st.expander(name):
                k = st.text_input(f"API Key {name}", type="password",
                                  key=f"key_{name.lower()}")
                if st.button(f"Guardar {name}", key=f"save_{name.lower()}"):
                    db.set_setting(f"{name.lower()}_key", k)
                    st.success("Guardado.")

# ══════════════════════════════════════════════════════════════════════════════
#  AUTO-REFRESH cada 5 segundos mientras el scanner corre
# ══════════════════════════════════════════════════════════════════════════════
if _STATE["running"]:
    time.sleep(5)
    st.rerun()
elif not _STATE["running"] and _STATE.get("thread") is None:
    # Si el scanner se detuvo inesperadamente, reiniciarlo
    time.sleep(3)
    _autostart()
    st.rerun()

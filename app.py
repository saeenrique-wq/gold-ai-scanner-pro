"""
GOLD AI SCANNER PRO — MVP Local
═══════════════════════════════
Scanner de ORO (XAUUSD) con IA local (Ollama).
Datos en vivo desde Yahoo Finance — sin necesitar MetaTrader.

Ejecutar:
  streamlit run app.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import threading
import time
from datetime import datetime
from typing import Optional, Dict, Any

import streamlit as st

# ─── Inicializar base de datos PRIMERO ───────────────────────────────────────
import database as db
db.init_db()

# ─── Importar módulos del proyecto ───────────────────────────────────────────
from config import (
    DEFAULT_YAHOO_SYMBOL, TIMEFRAMES, CAPITAL_PLANS,
    SCAN_INTERVAL_SECONDS, PRICE_POLL_SECONDS, TRACKER_INTERVAL,
    get_logger,
)
from models import Signal
from market_data.market_connector import MarketConnector
from strategy.indicators import calculate_all
from strategy.risk_manager import RiskManager
from strategy.gold_scalping_pro import GoldScalpingPro
from strategy.signal_tracker import SignalTracker
from ai.ollama_client import OllamaClient
from ai.ai_committee import AICommittee
from alerts.telegram_alerts import TelegramAlerter
from web.styles import load_css
from web.dashboard import (
    render_connection_badge, render_signal_card,
    render_history_table, render_weekly_bar, show_no_data_message,
)

logger = get_logger("app")

# ═══════════════════════════════════════════════════════════════════════════════
# ESTADO GLOBAL DEL SCANNER (persiste entre reruns de Streamlit)
# ═══════════════════════════════════════════════════════════════════════════════
_STATE: Dict[str, Any] = {
    "running":         False,
    "thread":          None,
    "stop_event":      threading.Event(),
    "market_connected": False,
    "ollama_connected": False,
    "current_price":   0.0,
    "bid":             0.0,
    "ask":             0.0,
    "last_signal":     None,          # dict con la última señal generada
    "status_msg":      "Scanner inactivo. Presiona INICIAR para comenzar.",
    "scan_count":      0,
    "last_scan_time":  "",
    "events":          [],            # Lista de eventos recientes
    "error_msg":       "",
}
_LOCK = threading.Lock()

# ─── Instancias reutilizables ────────────────────────────────────────────────
_connector: Optional[MarketConnector]  = None
_ollama:    Optional[OllamaClient]     = None
_strategy:  Optional[GoldScalpingPro]  = None
_tracker:   Optional[SignalTracker]    = None
_committee: Optional[AICommittee]      = None
_risk:      Optional[RiskManager]      = None
_telegram:  Optional[TelegramAlerter]  = None


def _build_components(symbol: str, capital: float, ollama_url: str, ollama_model: str):
    """Crea o recrea todos los componentes del scanner."""
    global _connector, _ollama, _strategy, _tracker, _committee, _risk, _telegram

    _connector = MarketConnector(symbol=symbol)
    _ollama    = OllamaClient(base_url=ollama_url, model=ollama_model)
    _strategy  = GoldScalpingPro()
    _tracker   = SignalTracker()
    _committee = AICommittee(_ollama)
    _risk      = RiskManager(capital=capital)

    tg_token   = db.get_setting("telegram_token")
    tg_chat_id = db.get_setting("telegram_chat_id")
    _telegram  = TelegramAlerter(token=tg_token, chat_id=tg_chat_id)


# ═══════════════════════════════════════════════════════════════════════════════
# HILO DE ESCANEO EN SEGUNDO PLANO
# ═══════════════════════════════════════════════════════════════════════════════

def _scanner_loop(symbol: str, tf_entry: str, tf_confirm: str, tf_trend: str,
                  capital: float, risk_usd: float, lot_size: float,
                  ollama_url: str, ollama_model: str,
                  stop_event: threading.Event) -> None:
    """Bucle principal del scanner. Corre en hilo separado."""
    global _connector, _risk, _strategy, _tracker, _committee, _telegram

    _build_components(symbol, capital, ollama_url, ollama_model)

    logger.info(f"Scanner iniciado — {symbol} | {tf_entry}/{tf_confirm}/{tf_trend}")
    _set_state("status_msg", "Conectando al mercado...")

    # ── Conectar al mercado ──────────────────────────────────────────────────
    if not _connector.connect():
        err = _connector.last_error
        _set_state("market_connected", False)
        _set_state("error_msg", err)
        _set_state("status_msg", f"Error de conexión: {err}")
        _set_state("running", False)
        logger.error(f"No se pudo conectar: {err}")
        return

    _set_state("market_connected", True)
    _set_state("error_msg", "")

    # Precio inicial inmediato
    md0 = _connector.get_market_data()
    if md0.connected and md0.last > 0:
        _set_state("current_price", md0.last)
        _set_state("bid", md0.bid)
        _set_state("ask", md0.ask)

    # Calentar Ollama en paralelo (carga modelo en RAM sin bloquear)
    ollama_ok = _ollama.is_available()
    _set_state("ollama_connected", ollama_ok)
    if ollama_ok:
        _set_state("status_msg", "Mercado conectado. Precalentando IA...")
        _ollama.warmup_async()   # No bloquea — el scanner empieza igual
    else:
        _set_state("status_msg",
                   "Mercado conectado. Ollama no detectado — escaneando sin IA.")
    _add_event(f"Mercado conectado via {_connector.active_symbol} | Precio: ${md0.last:.2f}")

    last_price_poll  = 0.0
    last_scan_time   = 0.0
    last_tracker_time = 0.0

    while not stop_event.is_set():
        now = time.time()

        # ── Actualizar precio cada PRICE_POLL_SECONDS ────────────────────────
        if (now - last_price_poll) >= PRICE_POLL_SECONDS:
            try:
                md = _connector.get_market_data()
                if md.connected:
                    _set_state("current_price", md.last)
                    _set_state("bid",  md.bid)
                    _set_state("ask",  md.ask)
                    _set_state("market_connected", True)
                else:
                    _set_state("market_connected", False)
                    _set_state("error_msg", md.error)
            except Exception as e:
                logger.error(f"Error actualizando precio: {e}")
            last_price_poll = now

        # ── Tracker de señales activas cada TRACKER_INTERVAL ─────────────────
        if (now - last_tracker_time) >= TRACKER_INTERVAL:
            price = _STATE["current_price"]
            if price > 0 and _tracker:
                try:
                    events = _tracker.update_all(price)
                    for ev in events:
                        _add_event(ev)
                        if _telegram and _telegram.is_configured:
                            _telegram.send_system_alert(ev)
                except Exception as e:
                    logger.error(f"Error en tracker: {e}")
            last_tracker_time = now

        # ── Escaneo técnico cada SCAN_INTERVAL_SECONDS ───────────────────────
        if (now - last_scan_time) >= SCAN_INTERVAL_SECONDS:
            _set_state("status_msg", "Analizando mercado...")
            _set_state("ollama_connected", _ollama.is_available())

            try:
                _run_scan(tf_entry, tf_confirm, tf_trend, risk_usd, lot_size)
            except Exception as e:
                logger.error(f"Error en escaneo: {e}", exc_info=True)
                _add_event(f"Error en escaneo: {str(e)[:80]}")

            with _LOCK:
                _STATE["scan_count"]    += 1
                _STATE["last_scan_time"] = datetime.now().strftime("%H:%M:%S")
            last_scan_time = now

        time.sleep(2)   # Pequeña pausa para no saturar CPU

    # ── Fin del bucle ────────────────────────────────────────────────────────
    _set_state("running", False)
    _set_state("status_msg", "Scanner detenido.")
    if _connector:
        _connector.disconnect()
    logger.info("Scanner detenido correctamente.")


def _run_scan(tf_entry: str, tf_confirm: str, tf_trend: str,
              risk_usd: float, lot_size: float) -> None:
    """Un ciclo completo de escaneo técnico + validación IA."""
    global _connector, _risk, _strategy, _committee, _telegram

    # ── Verificar límite semanal ──────────────────────────────────────────────
    if db.weekly_limit_reached():
        _set_state("status_msg", "Límite semanal de 12 señales alcanzado. Reinicia el lunes.")
        return

    # ── Descargar velas ───────────────────────────────────────────────────────
    df_m5  = _connector.get_candles(tf_confirm, count=210)
    df_h1  = _connector.get_candles(tf_trend,   count=210)
    df_m15 = _connector.get_candles("M15",       count=100)

    if df_m5 is None or df_h1 is None:
        _set_state("status_msg", "Esperando datos del mercado... (pocas velas disponibles)")
        return

    # ── Ejecutar estrategia ───────────────────────────────────────────────────
    signal_raw = _strategy.analyze(df_m5, df_h1, df_m15)

    if signal_raw is None:
        reasons = "Sin confirmaciones suficientes."
        _set_state("status_msg", f"Sin señal. {reasons} Siguiente scan en {SCAN_INTERVAL_SECONDS}s")
        return

    _set_state("status_msg", f"Posible señal {signal_raw['type']} detectada. Revisando riesgo...")

    # ── Calcular gestión de riesgo ────────────────────────────────────────────
    entry = signal_raw["entry"]
    calc  = _risk.calculate(
        entry       = entry,
        signal_type = signal_raw["type"],
        lot_size    = lot_size,
        risk_usd    = risk_usd,
    )

    if not calc.valid:
        _set_state("status_msg", f"Señal rechazada por riesgo: {calc.error}")
        return

    # ── Verificar RR mínimo ───────────────────────────────────────────────────
    if not _risk.check_rr_ratio(entry, calc.sl, calc.tp1, signal_raw["type"]):
        _set_state("status_msg", "Señal rechazada: riesgo-beneficio menor a 1:2.")
        return

    # ── Preparar datos para IA ────────────────────────────────────────────────
    _set_state("status_msg", "Enviando señal a IA para confirmación...")
    signal_data_for_ai = {
        "type":       signal_raw["type"],
        "entry":      entry,
        "sl":         calc.sl,
        "tp1":        calc.tp1,
        "tp2":        calc.tp2,
        "risk_usd":   calc.risk_usd,
        "min_profit": calc.min_profit,
        "rr_ratio":   calc.rr_ratio,
        "score":      signal_raw["score"],
        "reasons":    signal_raw["reasons"],
        "indicators": signal_raw["indicators"],
    }

    # ── Consultar comité de IA ────────────────────────────────────────────────
    ai_result = _committee.evaluate(signal_data_for_ai)

    ai_decision    = ai_result.get("decision",  "SIN_CONFIRMACION_IA")
    ai_confidence  = ai_result.get("confianza", "N/A")
    ai_reason      = ai_result.get("motivo",    "")
    ai_approved    = ai_result.get("approved",  False)
    ai_provider    = ai_result.get("provider",  "Ninguna")

    if not ai_approved:
        _set_state("status_msg", f"IA rechazó señal: {ai_reason}")
        db.log_market("INFO", f"Señal {signal_raw['type']} rechazada por IA: {ai_reason}", "scanner")
        return

    # ── Guardar señal aprobada ────────────────────────────────────────────────
    display_symbol = db.get_setting("display_symbol", "XAUUSD")
    new_signal = Signal(
        broker          = "Yahoo Finance",
        platform        = "Online",
        symbol          = display_symbol,
        timeframe       = tf_confirm,
        signal_type     = signal_raw["type"],
        entry           = entry,
        sl              = calc.sl,
        tp1             = calc.tp1,
        tp2             = calc.tp2,
        tp3             = calc.tp3,
        tp4             = calc.tp4,
        risk_usd        = calc.risk_usd,
        expected_profit = calc.min_profit,
        rr_ratio        = calc.rr_ratio,
        lot_size        = calc.lot_size,
        status          = "APROBADA",
        ai_provider     = ai_provider,
        ai_decision     = ai_decision,
        ai_confidence   = ai_confidence,
        ai_reason       = ai_reason,
        score           = signal_raw["score"],
        signal_style    = db.get_setting("signal_style", "Scalping"),
    )

    signal_id = db.save_signal(new_signal)
    new_signal.id = signal_id

    # Guardar en estado global para mostrar en UI
    signal_dict = {
        "id":             signal_id,
        "signal_type":    new_signal.signal_type,
        "symbol":         new_signal.symbol,
        "timeframe":      new_signal.timeframe,
        "entry":          new_signal.entry,
        "sl":             new_signal.sl,
        "tp1":            new_signal.tp1,
        "tp2":            new_signal.tp2,
        "tp3":            new_signal.tp3,
        "tp4":            new_signal.tp4,
        "risk_usd":       new_signal.risk_usd,
        "expected_profit": new_signal.expected_profit,
        "rr_ratio":       new_signal.rr_ratio,
        "lot_size":       new_signal.lot_size,
        "status":         new_signal.status,
        "ai_decision":    ai_decision,
        "ai_confidence":  ai_confidence,
        "ai_reason":      ai_reason,
        "score":          new_signal.score,
        "created_at":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    _set_state("last_signal", signal_dict)
    _set_state("status_msg", f"✅ SEÑAL APROBADA: {signal_raw['type']} en ${entry:.2f}")
    _add_event(
        f"✅ Señal #{signal_id} {signal_raw['type']} aprobada — "
        f"Entrada ${entry:.2f} | IA: {ai_decision} ({ai_confidence})"
    )

    # ── Alertas ───────────────────────────────────────────────────────────────
    if _telegram and _telegram.is_configured:
        _telegram.send_signal(signal_dict)


# ─── Helpers de estado ───────────────────────────────────────────────────────

def _set_state(key: str, value: Any) -> None:
    with _LOCK:
        _STATE[key] = value


def _add_event(msg: str) -> None:
    with _LOCK:
        _STATE["events"].insert(0, f"{datetime.now().strftime('%H:%M:%S')} — {msg}")
        _STATE["events"] = _STATE["events"][:50]   # Máximo 50 eventos


def _get_state() -> Dict:
    with _LOCK:
        return dict(_STATE)


# ═══════════════════════════════════════════════════════════════════════════════
# INICIAR / DETENER SCANNER
# ═══════════════════════════════════════════════════════════════════════════════

def start_scanner() -> None:
    state = _get_state()
    if state["running"]:
        return

    # Leer configuración guardada
    symbol       = db.get_setting("symbol",            DEFAULT_YAHOO_SYMBOL)
    capital      = float(db.get_setting("capital",     "200"))
    risk_usd     = float(db.get_setting("risk_usd",    "7"))
    lot_size     = float(db.get_setting("lot_size",    "0.01"))
    tf_entry     = db.get_setting("timeframe_entry",   "M5")
    tf_confirm   = db.get_setting("timeframe_confirm", "M15")
    tf_trend     = db.get_setting("timeframe_trend",   "H1")
    ollama_url   = db.get_setting("ollama_url",        "http://localhost:11434")
    ollama_model = db.get_setting("ollama_model",      "llama3")

    stop_ev = threading.Event()
    with _LOCK:
        _STATE["stop_event"] = stop_ev
        _STATE["running"]    = True
        _STATE["events"]     = []
        _STATE["scan_count"] = 0
        _STATE["error_msg"]  = ""

    t = threading.Thread(
        target=_scanner_loop,
        args=(symbol, tf_entry, tf_confirm, tf_trend,
              capital, risk_usd, lot_size, ollama_url, ollama_model, stop_ev),
        daemon=True,
        name="scanner_thread",
    )
    with _LOCK:
        _STATE["thread"] = t
    t.start()
    logger.info("Hilo de scanner iniciado.")


def stop_scanner() -> None:
    with _LOCK:
        stop_ev = _STATE.get("stop_event")
        if stop_ev:
            stop_ev.set()
        _STATE["running"] = False
    logger.info("Señal de detención enviada al scanner.")


# ═══════════════════════════════════════════════════════════════════════════════
# INTERFAZ STREAMLIT
# ═══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title = "GOLD AI SCANNER PRO",
    page_icon  = "⚜️",
    layout     = "wide",
    initial_sidebar_state = "expanded",
)

# Inyectar CSS
st.markdown(load_css(), unsafe_allow_html=True)

# ── Título principal ──────────────────────────────────────────────────────────
st.markdown(
    '<div class="main-title">⚜ GOLD AI SCANNER PRO</div>'
    '<div class="subtitle">XAUUSD · IA LOCAL · TIEMPO REAL</div>',
    unsafe_allow_html=True,
)

# ── Leer estado actual ────────────────────────────────────────────────────────
state = _get_state()

# ── Barra lateral — controles principales ────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Control del Scanner")

    if state["running"]:
        st.markdown(
            '<div style="text-align:center">'
            '<span class="scanning-pulse"></span>'
            '<span style="color:#00ff88;font-weight:700">ESCANEANDO...</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button("⏹ DETENER SCANNER", use_container_width=True):
            stop_scanner()
            st.rerun()
    else:
        if st.button("▶ INICIAR SCANNER", use_container_width=True):
            start_scanner()
            st.rerun()

    st.markdown("---")

    # Estado de conexiones
    st.markdown("### 📡 Estado")
    st.markdown(
        render_connection_badge(state["market_connected"], "Mercado"),
        unsafe_allow_html=True,
    )
    st.markdown(
        render_connection_badge(state["ollama_connected"], "Ollama IA"),
        unsafe_allow_html=True,
    )

    if state["current_price"] > 0:
        st.markdown(
            f'<div class="price-panel">${state["current_price"]:.2f}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Stats semanales
    stats = db.get_weekly_stats(float(db.get_setting("capital", "200")))
    st.markdown("### 📊 Esta Semana")
    st.markdown(
        render_weekly_bar(stats.total_signals, 12),
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("Señales", stats.total_signals)
    col2.metric("Ganadas", stats.won_signals)
    col3.metric("Perdidas", stats.lost_signals)

    if stats.total_signals > 0:
        st.metric("Efectividad", f"{stats.win_rate:.1f}%")

    st.markdown("---")
    st.markdown(
        f'<div style="font-size:0.75rem;color:#555;text-align:center;">'
        f'Scans: {state["scan_count"]} | '
        f'Último: {state["last_scan_time"] or "—"}'
        f'</div>',
        unsafe_allow_html=True,
    )

# ═══════════════════════════════════════════════════════════════════════════════
# PESTAÑAS PRINCIPALES
# ═══════════════════════════════════════════════════════════════════════════════
tab_dash, tab_scan, tab_active, tab_history, tab_config, tab_ai, tab_stats = st.tabs([
    "🏠 Dashboard",
    "📡 Scanner",
    "⚡ Señal Activa",
    "📋 Historial",
    "⚙️ Configuración",
    "🤖 IA & APIs",
    "📊 Estadísticas",
])


# ════════════════════════════════════════════════════════
# TAB 1: DASHBOARD
# ════════════════════════════════════════════════════════
with tab_dash:
    # Mensaje de estado
    if state["error_msg"]:
        st.error(f"⚠️ {state['error_msg']}")
    else:
        status_color = "#00ff88" if state["running"] else "#888888"
        st.markdown(
            f'<div style="background:#0d1117;border:1px solid {status_color};'
            f'border-radius:8px;padding:12px 16px;color:{status_color};'
            f'font-size:0.9rem;">{state["status_msg"]}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Métricas principales
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric(
        "Precio ORO",
        f"${state['current_price']:.2f}" if state["current_price"] > 0 else "—",
    )
    col2.metric("Señales Semana", f"{stats.total_signals}/12")
    col3.metric("Ganadas", stats.won_signals)
    col4.metric("Perdidas", stats.lost_signals)
    col5.metric(
        "Efectividad",
        f"{stats.win_rate:.1f}%" if stats.total_signals > 0 else "—",
    )

    st.markdown("---")

    # Última señal
    last_sig = state.get("last_signal")
    if last_sig:
        st.markdown("#### 🔔 Última Señal Generada")
        render_signal_card(last_sig)
    else:
        show_no_data_message("El scanner está buscando señales de alta probabilidad en XAUUSD.")

    # Señales activas
    active = db.get_active_signals()
    if active:
        st.markdown(f"#### ⚡ Señales Activas ({len(active)})")
        for sig in active:
            render_signal_card(sig)

    # Feed de eventos
    events = state.get("events", [])
    if events:
        st.markdown("#### 📝 Actividad Reciente")
        for ev in events[:10]:
            st.markdown(
                f'<div style="font-size:0.8rem;color:#8b949e;padding:3px 0;">{ev}</div>',
                unsafe_allow_html=True,
            )


# ════════════════════════════════════════════════════════
# TAB 2: SCANNER EN VIVO
# ════════════════════════════════════════════════════════
with tab_scan:
    st.markdown("#### 📡 Scanner de Mercado en Vivo")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            render_connection_badge(state["market_connected"], "Yahoo Finance"),
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            render_connection_badge(state["ollama_connected"], "Ollama IA"),
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    if state["current_price"] > 0:
        col1, col2, col3 = st.columns(3)
        col1.metric("Precio", f"${state['current_price']:.2f}")
        col2.metric("BID",    f"${state['bid']:.2f}")
        col3.metric("ASK",    f"${state['ask']:.2f}")

    st.markdown("---")
    st.markdown("##### Estado del Escaneo")
    st.info(state["status_msg"])

    if not state["running"]:
        st.warning(
            "El scanner no está activo. "
            "Presiona **▶ INICIAR SCANNER** en la barra lateral para comenzar."
        )

    # Log de eventos
    events = state.get("events", [])
    if events:
        st.markdown("##### Registro de Actividad")
        log_text = "\n".join(events[:20])
        st.text_area("Log", value=log_text, height=200, disabled=True)

    # Botón manual de refresh
    if st.button("🔄 Actualizar pantalla"):
        st.rerun()


# ════════════════════════════════════════════════════════
# TAB 3: SEÑAL ACTIVA
# ════════════════════════════════════════════════════════
with tab_active:
    st.markdown("#### ⚡ Señal Activa en Seguimiento")
    active = db.get_active_signals()

    if not active:
        show_no_data_message(
            "No hay señales activas en este momento. "
            "El scanner buscará la próxima oportunidad."
        )
    else:
        for sig in active:
            render_signal_card(sig)

            # Precio actual vs niveles
            price = state["current_price"]
            if price > 0:
                st.markdown(f"**Precio actual: ${price:.2f}**")
                entry = sig["entry"]
                sl    = sig["sl"]
                tp1   = sig["tp1"]

                if sig["signal_type"] == "BUY":
                    dist_sl  = price - sl
                    dist_tp1 = tp1   - price
                else:
                    dist_sl  = sl    - price
                    dist_tp1 = price - tp1

                c1, c2 = st.columns(2)
                c1.metric("Distancia al SL",  f"${dist_sl:.2f}")
                c2.metric("Distancia al TP1", f"${dist_tp1:.2f}")


# ════════════════════════════════════════════════════════
# TAB 4: HISTORIAL
# ════════════════════════════════════════════════════════
with tab_history:
    st.markdown("#### 📋 Historial de Señales")
    history = db.get_signals_history(limit=100)

    if history:
        # Filtros
        col1, col2 = st.columns(2)
        filter_type   = col1.selectbox("Filtrar por tipo",   ["Todos", "BUY", "SELL"])
        filter_result = col2.selectbox("Filtrar por resultado", ["Todos", "GANADA", "PERDIDA", "ACTIVA"])

        if filter_type != "Todos":
            history = [s for s in history if s["signal_type"] == filter_type]
        if filter_result != "Todos":
            if filter_result == "ACTIVA":
                history = [s for s in history if s["status"] in ("ACTIVA", "APROBADA")]
            else:
                history = [s for s in history if s.get("result") == filter_result]

        render_history_table(history)
    else:
        show_no_data_message("No hay señales en el historial todavía.")


# ════════════════════════════════════════════════════════
# TAB 5: CONFIGURACIÓN
# ════════════════════════════════════════════════════════
with tab_config:
    st.markdown("#### ⚙️ Configuración del Scanner")
    st.info("Los cambios se aplican al próximo inicio del scanner.")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### Capital y Riesgo")
        capital_opt = st.selectbox(
            "Capital base",
            options=[200, 500, 1000, "Personalizado"],
            index=0,
        )
        if capital_opt == "Personalizado":
            capital = st.number_input("Capital personalizado ($)", min_value=50.0, value=200.0)
        else:
            capital = float(capital_opt)

        plan = CAPITAL_PLANS.get(int(capital) if int(capital) in CAPITAL_PLANS else 200,
                                  CAPITAL_PLANS[200])
        st.markdown(
            f"**Lotaje sugerido:** {plan['lot']} | "
            f"**Riesgo:** ${plan['risk_usd']} | "
            f"**Ganancia mín:** ${plan['min_profit']}"
        )

        risk_usd  = st.number_input("Riesgo por operación ($)", min_value=1.0, value=float(plan["risk_usd"]))
        lot_size  = st.number_input("Lotaje", min_value=0.01, value=float(plan["lot"]), step=0.01, format="%.2f")

    with col2:
        st.markdown("##### Temporalidades")
        tf_entry   = st.selectbox("Temporalidad de entrada",      list(TIMEFRAMES.keys()), index=1)  # M5
        tf_confirm = st.selectbox("Temporalidad de confirmación", list(TIMEFRAMES.keys()), index=2)  # M15
        tf_trend   = st.selectbox("Temporalidad de tendencia",    list(TIMEFRAMES.keys()), index=4)  # H1

        st.markdown("##### Mercado")
        symbol_display = st.text_input("Símbolo (display)", value=db.get_setting("display_symbol", "XAUUSD"))
        symbol_yahoo   = st.selectbox(
            "Símbolo Yahoo Finance",
            ["XAUUSD=X", "GC=F"],
            index=0,
        )

        st.markdown("##### Estilo de señal")
        signal_style = st.selectbox(
            "Estilo",
            ["Scalping", "Intradía", "Swing", "Alta Probabilidad"],
            index=0,
        )

    if st.button("💾 Guardar Configuración", use_container_width=True):
        db.set_setting("capital",           str(capital))
        db.set_setting("risk_usd",          str(risk_usd))
        db.set_setting("lot_size",          str(lot_size))
        db.set_setting("timeframe_entry",   tf_entry)
        db.set_setting("timeframe_confirm", tf_confirm)
        db.set_setting("timeframe_trend",   tf_trend)
        db.set_setting("symbol",            symbol_yahoo)
        db.set_setting("display_symbol",    symbol_display)
        db.set_setting("signal_style",      signal_style)
        st.success("✅ Configuración guardada. Reinicia el scanner para aplicar cambios.")

    st.markdown("---")
    st.markdown("##### Resumen del plan semanal")

    st.markdown(f"""
    | Parámetro | Valor |
    |-----------|-------|
    | Capital | ${capital:.0f} |
    | Lotaje | {lot_size} |
    | Riesgo por op. | ${risk_usd:.2f} |
    | Ganancia mínima | ${risk_usd*2:.2f} |
    | Operaciones/semana | 12 |
    | Estimadas ganadas | 10 |
    | Estimadas perdidas | 2 |
    | Ganancia bruta estim. | ${risk_usd*2*10:.2f} |
    | Pérdida estim. | ${risk_usd*2:.2f} |
    | **Ganancia neta estim.** | **${risk_usd*2*10 - risk_usd*2:.2f}** |
    | Capital final estim. | ${capital + risk_usd*2*10 - risk_usd*2:.2f} |
    """)
    st.caption("⚠️ Estas son estimaciones basadas en el plan. El trading tiene riesgos.")


# ════════════════════════════════════════════════════════
# TAB 6: IA & APIs
# ════════════════════════════════════════════════════════
with tab_ai:
    st.markdown("#### 🤖 Configuración de Inteligencia Artificial")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### Ollama (IA Local — Gratis)")
        ollama_url   = st.text_input("URL de Ollama", value=db.get_setting("ollama_url", "http://localhost:11434"))
        ollama_model = st.text_input("Modelo de Ollama", value=db.get_setting("ollama_model", "llama3"))

        if st.button("🔍 Verificar Ollama"):
            client = OllamaClient(base_url=ollama_url, model=ollama_model)
            if client.is_available(force_check=True):
                models = client.get_models()
                st.success(f"✅ Ollama disponible. Modelos: {', '.join(models[:5]) if models else 'ninguno listado'}")
            else:
                st.error(
                    "❌ Ollama no responde. Para instalarlo:\n"
                    "1. Ve a https://ollama.ai y descárgalo\n"
                    "2. Instálalo en tu PC\n"
                    "3. Abre una terminal y ejecuta: `ollama pull llama3`\n"
                    "4. Deja Ollama corriendo en segundo plano"
                )

        if st.button("💾 Guardar config Ollama"):
            db.set_setting("ollama_url",   ollama_url)
            db.set_setting("ollama_model", ollama_model)
            st.success("✅ Config Ollama guardada.")

    with col2:
        st.markdown("##### IAs Externas (Futuras — requieren API Key)")
        with st.expander("OpenAI (ChatGPT)"):
            key_oa = st.text_input("API Key OpenAI", type="password", key="openai_key")
            if st.button("Guardar OpenAI"):
                db.set_setting("openai_key", key_oa)
                st.success("API Key guardada.")

        with st.expander("Gemini (Google)"):
            key_gm = st.text_input("API Key Gemini", type="password", key="gemini_key")
            if st.button("Guardar Gemini"):
                db.set_setting("gemini_key", key_gm)
                st.success("API Key guardada.")

        with st.expander("Groq (Ultra rápido)"):
            key_gr = st.text_input("API Key Groq", type="password", key="groq_key")
            if st.button("Guardar Groq"):
                db.set_setting("groq_key", key_gr)
                st.success("API Key guardada.")

    st.markdown("---")
    st.markdown("##### Alertas Telegram")
    tg_token   = st.text_input("Token del Bot de Telegram", type="password",
                                value=db.get_setting("telegram_token"))
    tg_chat_id = st.text_input("Chat ID de Telegram",
                                value=db.get_setting("telegram_chat_id"))
    col1, col2 = st.columns(2)
    if col1.button("💾 Guardar Telegram"):
        db.set_setting("telegram_token",   tg_token)
        db.set_setting("telegram_chat_id", tg_chat_id)
        st.success("✅ Telegram configurado.")
    if col2.button("🧪 Probar Telegram"):
        alerter = TelegramAlerter(token=tg_token, chat_id=tg_chat_id)
        ok = alerter.send("🧪 Prueba de GOLD AI SCANNER PRO — ¡funciona!")
        if ok:
            st.success("✅ Mensaje enviado a Telegram.")
        else:
            st.error("❌ No se pudo enviar. Revisa el token y chat_id.")


# ════════════════════════════════════════════════════════
# TAB 7: ESTADÍSTICAS
# ════════════════════════════════════════════════════════
with tab_stats:
    st.markdown("#### 📊 Estadísticas del Sistema")
    capital = float(db.get_setting("capital", "200"))
    stats   = db.get_weekly_stats(capital)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Señales esta semana",  stats.total_signals)
    col2.metric("Ganadas",              stats.won_signals)
    col3.metric("Perdidas",             stats.lost_signals)
    col4.metric("Efectividad",          f"{stats.win_rate:.1f}%" if stats.total_signals > 0 else "—")

    col1, col2, col3 = st.columns(3)
    col1.metric("Semana",         f"{stats.week_start} → {stats.week_end}")
    col2.metric("Neto semanal",   f"${stats.net_profit:.2f}")
    col3.metric("Capital estimado", f"${stats.capital_end:.2f}")

    st.markdown(render_weekly_bar(stats.total_signals, 12), unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("##### Historial completo de señales")
    all_signals = db.get_signals_history(limit=200)
    st.markdown(f"Total de señales registradas: **{len(all_signals)}**")

    won   = sum(1 for s in all_signals if s.get("result") == "GANADA")
    lost  = sum(1 for s in all_signals if s.get("result") == "PERDIDA")
    total = won + lost

    if total > 0:
        eff = won / total * 100
        st.metric("Efectividad histórica real", f"{eff:.1f}%")
        st.caption(
            f"Basado en {total} señales cerradas. "
            "Este es el número REAL — no una promesa."
        )
    else:
        st.info(
            "Sin historial suficiente todavía. La efectividad real solo "
            "se calcula cuando hay señales cerradas (TP o SL tocado)."
        )

    st.markdown("---")
    st.markdown("##### Logs del mercado")
    logs = db.get_market_logs(limit=50)
    if logs:
        for log in logs[:20]:
            lvl   = log["level"]
            color = "#00ff88" if lvl == "INFO" else "#ff4444" if lvl == "ERROR" else "#ffee44"
            st.markdown(
                f'<div style="font-size:0.75rem;color:{color};padding:2px 0;">'
                f'{log["created_at"]} [{lvl}] {log["message"]}</div>',
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# AUTO-REFRESH cuando el scanner está corriendo
# ═══════════════════════════════════════════════════════════════════════════════
if state["running"]:
    time.sleep(8)
    st.rerun()

"""
Componentes visuales reutilizables del dashboard.
"""
import streamlit as st
from typing import List, Dict, Optional
from datetime import datetime


def render_connection_badge(connected: bool, label: str) -> str:
    if connected:
        return f'<span class="status-ok">● {label}: CONECTADO</span>'
    return f'<span class="status-err">● {label}: DESCONECTADO</span>'


def render_signal_badge(signal_type: str) -> str:
    if signal_type == "BUY":
        return '<span class="chip-buy">▲ COMPRA</span>'
    elif signal_type == "SELL":
        return '<span class="chip-sell">▼ VENTA</span>'
    return f'<span class="chip-gold">{signal_type}</span>'


_STATUS_LABELS = {
    "ACTIVA":           ("🟢", "#00ff88", "EN OPERACIÓN"),
    "APROBADA":         ("🟢", "#ffd700", "SEÑAL LISTA"),
    "TP1_ALCANZADO":    ("✅", "#00bfff", "META 1 LOGRADA"),
    "TP2_ALCANZADO":    ("✅", "#00bfff", "META 2 LOGRADA"),
    "TP3_ALCANZADO":    ("✅", "#00bfff", "META 3 LOGRADA"),
    "TP4_ALCANZADO":    ("🏆", "#00ff88", "GANANCIA MÁXIMA"),
    "SL_TOCADO":        ("⛔", "#ff4444", "PÉRDIDA"),
    "RECHAZADA":        ("❌", "#888888", "DESCARTADA"),
    "CANCELADA":        ("❌", "#888888", "CANCELADA"),
    "FINALIZADA":       ("✔️", "#888888", "CERRADA"),
    "EN_REVISION_IA":   ("🤖", "#bf5fff", "IA REVISANDO"),
    "POSIBLE_ENTRADA":  ("👀", "#ffee44", "POSIBLE SEÑAL"),
    "BUSCANDO":         ("🔍", "#888888", "BUSCANDO"),
}

def render_status_badge(status: str) -> str:
    icon, color, label = _STATUS_LABELS.get(status, ("●", "#888888", status))
    return f'<span style="color:{color};font-weight:700">{icon} {label}</span>'


def render_weekly_bar(used: int, limit: int) -> str:
    pct   = min(used / limit * 100, 100)
    color = "#00ff88" if pct < 70 else "#ffee44" if pct < 90 else "#ff4444"
    return f"""
    <div style="background:#1c2128;border-radius:6px;height:12px;width:100%;margin:6px 0;">
      <div style="background:{color};width:{pct:.0f}%;height:100%;border-radius:6px;
                  transition:width 0.4s;box-shadow:0 0 8px {color}66;"></div>
    </div>
    <div style="font-size:0.75rem;color:#888;">{used}/{limit} señales usadas esta semana</div>
    """


_TF_TO_STYLE = {
    "M1": "⚡ Scalping M1", "M5": "⚡ Scalping M5",
    "M15": "📈 Day Trading M15", "M30": "📈 Day Trading M30",
    "H1": "🌊 Swing H1",
}

def render_signal_card(sig: Dict) -> None:
    tipo   = sig.get("signal_type", "?")
    cls    = "signal-buy" if tipo == "BUY" else "signal-sell"
    emoji  = "🟢" if tipo == "BUY" else "🔴"
    tipo_label = "COMPRA" if tipo == "BUY" else "VENTA"
    status = sig.get("status", "")
    entry  = sig.get("entry",  0)
    sl     = sig.get("sl",     0)
    tp1    = sig.get("tp1",    0)
    tp2    = sig.get("tp2",    0)
    tp3    = sig.get("tp3",    0)
    tp4    = sig.get("tp4",    0)
    risk   = sig.get("risk_usd", 0)
    rr     = sig.get("rr_ratio", 2)
    tf     = sig.get("timeframe", "M5")
    style  = _TF_TO_STYLE.get(tf, f"⏱ {tf}")

    # Ganancia esperada por TP (riesgo × multiplicador)
    g1 = round(risk * rr,     2)
    g2 = round(risk * rr * 1.5, 2)
    g3 = round(risk * rr * 2,   2)
    g4 = round(risk * rr * 2.5, 2)

    ai_text = sig.get('ai_reason','')
    ai_decision = sig.get('ai_decision','N/A')
    ai_color = "#00ff88" if ai_decision == "APROBAR" else "#ff4444" if ai_decision == "RECHAZAR" else "#bf5fff"

    st.markdown(f"""
    <div class="{cls}">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
        <div style="font-family:'Orbitron',monospace;font-size:1.1rem;">
          {emoji} {tipo_label} #{sig.get('id','?')} — {sig.get('symbol','XAUUSD')}
        </div>
        <div>{render_status_badge(status)}</div>
      </div>
      <div style="font-size:0.75rem;color:#888;margin-bottom:10px;">{style}</div>
      <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;font-size:0.88rem;margin-bottom:8px;">
        <div style="background:#0d1117;border-radius:6px;padding:8px;">
          <span style="color:#888;font-size:0.75rem;">Precio de entrada</span><br>
          <b style="font-size:1.1rem;">${entry:.2f}</b>
        </div>
        <div style="background:#1a0000;border-radius:6px;padding:8px;">
          <span style="color:#ff4444;font-size:0.75rem;">Stop Loss (pérdida máx)</span><br>
          <b style="color:#ff4444;font-size:1.1rem;">${sl:.2f}</b>
          <span style="color:#888;font-size:0.75rem;"> → pierdes ${risk:.0f}</span>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(2,1fr) repeat(2,1fr);gap:6px;font-size:0.82rem;">
        <div style="background:#001a0e;border-radius:6px;padding:6px;">
          <span style="color:#00ff88;font-size:0.72rem;">Meta 1 (TP1)</span><br>
          <b style="color:#00ff88;">${tp1:.2f}</b><br>
          <span style="color:#888;font-size:0.7rem;">+${g1:.0f}</span>
        </div>
        <div style="background:#001020;border-radius:6px;padding:6px;">
          <span style="color:#00bfff;font-size:0.72rem;">Meta 2 (TP2)</span><br>
          <b style="color:#00bfff;">${tp2:.2f}</b><br>
          <span style="color:#888;font-size:0.7rem;">+${g2:.0f}</span>
        </div>
        <div style="background:#001020;border-radius:6px;padding:6px;">
          <span style="color:#00bfff;font-size:0.72rem;">Meta 3 (TP3)</span><br>
          <b style="color:#00bfff;">${tp3:.2f}</b><br>
          <span style="color:#888;font-size:0.7rem;">+${g3:.0f}</span>
        </div>
        <div style="background:#1a1000;border-radius:6px;padding:6px;">
          <span style="color:#ffd700;font-size:0.72rem;">Meta 4 — Máxima</span><br>
          <b style="color:#ffd700;">${tp4:.2f}</b><br>
          <span style="color:#888;font-size:0.7rem;">+${g4:.0f}</span>
        </div>
      </div>
      <div style="margin-top:8px;font-size:0.78rem;color:#888;display:flex;gap:16px;flex-wrap:wrap;">
        <span>⛔ Riesgo máximo: <b style="color:#ff4444">${risk:.2f}</b></span>
        <span>📊 Relación R/B: <b style="color:#ffd700">1:{rr:.0f}</b></span>
        <span>🤖 IA: <b style="color:{ai_color}">{ai_decision}</b></span>
      </div>
      {f'<div style="margin-top:6px;font-size:0.78rem;color:#bf5fff;border-top:1px solid #30363d;padding-top:6px;">🤖 {ai_text}</div>' if ai_text else ''}
    </div>
    """, unsafe_allow_html=True)


def render_history_table(signals: List[Dict]) -> None:
    if not signals:
        st.info("No hay señales en el historial todavía.")
        return

    header = (
        "| # | Tipo | Entrada | SL | TP1 | Estado | IA | Resultado | Fecha |"
        "\n|---|------|---------|----|----|--------|-----|-----------|-------|"
    )
    rows = []
    for s in signals:
        tipo    = "▲ BUY" if s["signal_type"] == "BUY" else "▼ SELL"
        result  = s.get("result", "—") or "—"
        rows.append(
            f"| {s['id']} | {tipo} | ${s['entry']:.2f} | ${s['sl']:.2f} | "
            f"${s['tp1']:.2f} | {s['status']} | {s.get('ai_decision','—')} | "
            f"{result} | {s['created_at'][:16]} |"
        )

    st.markdown(header + "\n" + "\n".join(rows))


def render_risk_summary(risk_calc) -> None:
    if risk_calc is None or not risk_calc.valid:
        st.error(f"Error en riesgo: {getattr(risk_calc,'error','Desconocido')}")
        return

    tipo  = risk_calc.signal_type
    color = "#00ff88" if tipo == "BUY" else "#ff4444"

    st.markdown(f"""
    <div style="background:#0d1117;border:1px solid {color};border-radius:10px;padding:16px;">
      <div style="font-family:'Orbitron',monospace;color:{color};margin-bottom:10px;">
        {'▲ COMPRA' if tipo=='BUY' else '▼ VENTA'} — Gestión de Riesgo
      </div>
      <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;font-size:0.9rem;">
        <div>Lote: <b>${risk_calc.lot_size}</b></div>
        <div>Riesgo: <b style="color:#ff4444">${risk_calc.risk_usd:.2f}</b></div>
        <div>Ganancia mín: <b style="color:#00ff88">${risk_calc.min_profit:.2f}</b></div>
        <div>R/B: <b style="color:#ffd700">1:{risk_calc.rr_ratio:.0f}</b></div>
        <div>SL Distancia: <b>${risk_calc.sl_distance:.2f}</b></div>
        <div>pip_value: <b>${risk_calc.pip_value:.2f}/dólar</b></div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def show_no_data_message(context: str = "") -> None:
    st.markdown(f"""
    <div style="background:#1c2128;border:1px solid #30363d;border-radius:10px;
                padding:30px;text-align:center;color:#8b949e;">
      <div style="font-size:2rem">📡</div>
      <div style="margin-top:10px;">
        {context or "Esperando datos del mercado..."}
      </div>
    </div>
    """, unsafe_allow_html=True)

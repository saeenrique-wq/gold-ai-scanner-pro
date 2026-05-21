"""
Alertas de sonido para el scanner usando Web Audio API del navegador.
Sonidos distintos para: COMPRA, VENTA, GANANCIA, PÉRDIDA.
"""
import json
import streamlit.components.v1 as components


def play_sounds(events: list) -> None:
    """
    Recibe lista de eventos: ["BUY", "SELL", "WIN", "LOSS"]
    Reproduce el sonido correspondiente en el navegador.
    sessionStorage evita repetir el mismo evento.
    """
    if not events:
        return

    events_json = json.dumps(events)

    html = f"""
<script>
(function() {{
  const events = {events_json};
  if (!events || events.length === 0) return;

  // Clave única para no repetir el mismo evento
  const key = "gold_played_" + JSON.stringify(events);
  if (sessionStorage.getItem(key)) return;
  sessionStorage.setItem(key, "1");

  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return;
  const ctx = new AudioCtx();

  function tone(freq, startT, dur, type, vol) {{
    const osc  = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = type || 'sine';
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(vol || 0.4, ctx.currentTime + startT);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + startT + dur);
    osc.start(ctx.currentTime + startT);
    osc.stop(ctx.currentTime + startT + dur + 0.05);
  }}

  // BUY — 3 notas ascendentes (verde, alegre)
  function playBuy() {{
    [[440,0],[550,0.18],[660,0.36]].forEach(([f,t]) => tone(f, t, 0.22, 'sine', 0.35));
  }}

  // SELL — 3 notas descendentes (rojo, alerta)
  function playSell() {{
    [[660,0],[550,0.18],[440,0.36]].forEach(([f,t]) => tone(f, t, 0.22, 'sine', 0.35));
  }}

  // WIN — fanfarria ascendente (4 notas, brillante)
  function playWin() {{
    [[523,0],[659,0.18],[784,0.36],[1047,0.54]].forEach(([f,t]) => tone(f, t, 0.28, 'sine', 0.4));
  }}

  // LOSS — 3 pulsos graves (alarma)
  function playLoss() {{
    [[220,0],[200,0.3],[180,0.6]].forEach(([f,t]) => tone(f, t, 0.25, 'sawtooth', 0.3));
  }}

  events.forEach(ev => {{
    if      (ev === 'BUY')  playBuy();
    else if (ev === 'SELL') playSell();
    else if (ev === 'WIN')  playWin();
    else if (ev === 'LOSS') playLoss();
  }});
}})();
</script>
"""
    components.html(html, height=0, scrolling=False)

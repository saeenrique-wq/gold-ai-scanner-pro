"""
Alertas de sonido para el scanner usando Web Audio API del navegador.
Maneja la política de autoplay: requiere un clic del usuario para activar.
"""
import json
import streamlit as st
import streamlit.components.v1 as components


def render_sound_button() -> None:
    """
    Muestra botón para activar sonidos (requerido por navegadores modernos).
    Llamar UNA vez al inicio de la página.
    """
    components.html("""
<div id="sound-btn-wrap" style="display:inline-block;">
  <button id="enable-sound-btn"
    onclick="window._goldAudioEnabled=true;
             if(!window._goldAudioCtx){
               window._goldAudioCtx=new(window.AudioContext||window.webkitAudioContext)();
             }
             window._goldAudioCtx.resume();
             this.textContent='🔊 Sonidos ON';
             this.style.background='#00ff8833';
             this.style.borderColor='#00ff88';"
    style="background:#1c2128;border:1px solid #30363d;color:#8b949e;
           padding:6px 14px;border-radius:6px;cursor:pointer;font-size:0.8rem;">
    🔇 Activar sonidos
  </button>
</div>
<script>
  // Si ya estaba activado en esta sesión, restaurar estado
  if(sessionStorage.getItem('goldAudioEnabled')==='1'){
    window._goldAudioEnabled=true;
    var btn=document.getElementById('enable-sound-btn');
    if(btn){btn.textContent='🔊 Sonidos ON';
             btn.style.background='#00ff8833';
             btn.style.borderColor='#00ff88';}
  }
  document.getElementById('enable-sound-btn').addEventListener('click',function(){
    sessionStorage.setItem('goldAudioEnabled','1');
  });
</script>
""", height=45, scrolling=False)


def play_sounds(events: list) -> None:
    """
    Recibe lista de eventos: ["BUY","SELL","WIN","LOSS"]
    Reproduce el sonido correspondiente si el usuario activó el audio.
    """
    if not events:
        return

    events_json = json.dumps(events)
    uid = abs(hash(str(events))) % 1_000_000   # ID único para no repetir

    components.html(f"""
<script>
(function() {{
  var events = {events_json};
  if (!events || events.length === 0) return;

  // Verificar si el usuario activó el audio
  var enabled = sessionStorage.getItem('goldAudioEnabled') === '1'
             || window._goldAudioEnabled === true;
  if (!enabled) return;

  // Evitar repetir el mismo bloque de sonido
  var uid = 'gold_snd_{uid}';
  if (sessionStorage.getItem(uid)) return;
  sessionStorage.setItem(uid, '1');

  // Obtener o crear AudioContext
  var AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return;
  if (!window._goldAudioCtx) {{
    window._goldAudioCtx = new AudioCtx();
  }}
  var ctx = window._goldAudioCtx;
  if (ctx.state === 'suspended') {{ ctx.resume(); }}

  function tone(freq, startT, dur, type, vol) {{
    try {{
      var osc  = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = type || 'sine';
      osc.frequency.value = freq;
      var t0 = ctx.currentTime + startT;
      gain.gain.setValueAtTime(vol || 0.35, t0);
      gain.gain.exponentialRampToValueAtTime(0.001, t0 + dur);
      osc.start(t0);
      osc.stop(t0 + dur + 0.05);
    }} catch(e) {{}}
  }}

  function playBuy()  {{ [[440,0],[550,0.18],[660,0.36]].forEach(function(x){{tone(x[0],x[1],0.22,'sine',0.35)}}); }}
  function playSell() {{ [[660,0],[550,0.18],[440,0.36]].forEach(function(x){{tone(x[0],x[1],0.22,'sine',0.35)}}); }}
  function playWin()  {{ [[523,0],[659,0.18],[784,0.36],[1047,0.54]].forEach(function(x){{tone(x[0],x[1],0.28,'sine',0.4)}}); }}
  function playLoss() {{ [[220,0],[200,0.3],[180,0.6]].forEach(function(x){{tone(x[0],x[1],0.25,'sawtooth',0.3)}}); }}

  events.forEach(function(ev) {{
    if      (ev === 'BUY')  {{ playBuy(); }}
    else if (ev === 'SELL') {{ playSell(); }}
    else if (ev === 'WIN')  {{ playWin(); }}
    else if (ev === 'LOSS') {{ playLoss(); }}
  }});
}})();
</script>
""", height=0, scrolling=False)

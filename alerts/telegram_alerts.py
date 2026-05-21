"""
Alertas por Telegram.
Para activar: obtén un bot token de @BotFather y configura el chat_id.
"""
from typing import Optional
from config import get_logger

logger = get_logger("telegram_alerts")

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    requests = None
    _REQUESTS_OK = False


class TelegramAlerter:
    """
    Envía mensajes al canal de Telegram del usuario.

    Cómo configurar:
    1. Habla con @BotFather en Telegram → /newbot → guarda el token.
    2. Obtén tu chat_id enviando un mensaje al bot y visitando:
       https://api.telegram.org/bot<TOKEN>/getUpdates
    3. Pega token y chat_id en el panel de Configuración del scanner.
    """

    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, token: str = "", chat_id: str = ""):
        self.token   = token
        self.chat_id = chat_id

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, message: str) -> bool:
        """Envía un mensaje de texto. Retorna True si tuvo éxito."""
        if not self.is_configured:
            logger.debug("Telegram no configurado. Omitiendo alerta.")
            return False
        if not _REQUESTS_OK:
            logger.warning("requests no instalado. No se puede enviar por Telegram.")
            return False
        try:
            resp = requests.post(
                self.BASE_URL.format(token=self.token),
                data={
                    "chat_id":    self.chat_id,
                    "text":       message,
                    "parse_mode": "HTML",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("Alerta Telegram enviada.")
                return True
            logger.warning(f"Telegram respondió {resp.status_code}: {resp.text[:100]}")
            return False
        except Exception as e:
            logger.error(f"Error enviando alerta Telegram: {e}")
            return False

    def send_signal(self, signal_data: dict) -> bool:
        """Envía alerta formateada de nueva señal."""
        tipo  = signal_data.get("signal_type", "?")
        emoji = "🟢" if tipo == "BUY" else "🔴"

        msg = (
            f"<b>{emoji} NUEVA SEÑAL XAUUSD — {tipo}</b>\n\n"
            f"📌 Entrada:  <b>${signal_data.get('entry', 0):.2f}</b>\n"
            f"🛑 SL:       <b>${signal_data.get('sl', 0):.2f}</b>\n"
            f"🎯 TP1:      <b>${signal_data.get('tp1', 0):.2f}</b>\n"
            f"🎯 TP2:      <b>${signal_data.get('tp2', 0):.2f}</b>\n"
            f"🎯 TP3:      <b>${signal_data.get('tp3', 0):.2f}</b>\n"
            f"🎯 TP4:      <b>${signal_data.get('tp4', 0):.2f}</b>\n\n"
            f"⏱ Temporal: {signal_data.get('timeframe', 'M5')}\n"
            f"💰 Riesgo:   ${signal_data.get('risk_usd', 0):.2f}\n"
            f"💵 Ganancia mín: ${signal_data.get('min_profit', 0):.2f}\n"
            f"📊 R/B: 1:{signal_data.get('rr_ratio', 2):.0f}\n"
            f"🤖 IA: {signal_data.get('ai_decision', 'N/A')} "
            f"— Confianza: {signal_data.get('ai_confidence', 'N/A')}\n\n"
            f"<i>⚠️ Trading tiene riesgo. Solo usa capital que puedas perder.</i>"
        )
        return self.send(msg)

    def send_tp_update(self, signal_id: int, tp_level: str, price: float) -> bool:
        msg = f"✅ Señal #{signal_id} — <b>{tp_level} ALCANZADO</b> a ${price:.2f}"
        return self.send(msg)

    def send_sl_hit(self, signal_id: int, price: float) -> bool:
        msg = f"⛔ Señal #{signal_id} — <b>SL TOCADO</b> a ${price:.2f}"
        return self.send(msg)

    def send_system_alert(self, message: str) -> bool:
        return self.send(f"⚙️ <b>Sistema:</b> {message}")

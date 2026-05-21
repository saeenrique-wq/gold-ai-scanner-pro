"""
WhatsApp Alerts — Módulo preparado para fase futura.
Requiere API de Twilio o WhatsApp Business.
Por ahora solo registra en logs para no bloquear el sistema.
"""
from config import get_logger

logger = get_logger("whatsapp_alerts")


class WhatsAppAlerter:
    """Placeholder para alertas de WhatsApp. Se implementa en fase 2."""

    def __init__(self):
        logger.info("WhatsApp Alerter inicializado (modo simulación — fase futura).")

    def send_signal(self, signal_data: dict) -> bool:
        logger.info(f"[WhatsApp — pendiente] Señal {signal_data.get('signal_type')} en ${signal_data.get('entry', 0):.2f}")
        return False

    def send_tp_update(self, signal_id: int, tp_level: str, price: float) -> bool:
        logger.info(f"[WhatsApp — pendiente] {tp_level} alcanzado en señal #{signal_id}")
        return False

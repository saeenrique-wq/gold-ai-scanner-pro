"""
Signal Tracker — Monitorea señales activas y actualiza su estado automáticamente.
Compara el precio actual con TP1, TP2, TP3, TP4 y SL.
"""
from datetime import datetime
from typing import List, Dict

import database as db
from models import SignalEvent
from config import get_logger

logger = get_logger("signal_tracker")


class SignalTracker:
    """
    Seguimiento automático de señales activas.
    Se ejecuta cada N segundos en el hilo del scanner.
    """

    def update_all(self, current_price: float) -> List[str]:
        """
        Revisa todas las señales activas y actualiza su estado.
        Retorna lista de mensajes de eventos ocurridos.
        """
        if current_price <= 0:
            return []

        active = db.get_active_signals()
        events = []

        for sig in active:
            msg = self._check_signal(sig, current_price)
            if msg:
                events.append(msg)

        return events

    def _check_signal(self, sig: Dict, price: float) -> str:
        """Evalúa un señal individual contra el precio actual."""
        signal_id   = sig["id"]
        signal_type = sig["signal_type"]
        entry       = sig["entry"]
        sl          = sig["sl"]
        tp1         = sig["tp1"]
        tp2         = sig["tp2"]
        tp3         = sig["tp3"]
        tp4         = sig["tp4"]
        status      = sig["status"]

        result_msg = ""

        if signal_type == "BUY":
            # SL tocado
            if price <= sl:
                db.update_signal_status(signal_id, "SL_TOCADO", price, "PERDIDA")
                self._save_event(signal_id, "SL_TOCADO", price, f"SL tocado a ${price:.2f}")
                result_msg = f"⛔ Señal #{signal_id} BUY — SL TOCADO a ${price:.2f}"
                logger.info(result_msg)

            # TP4 alcanzado (máxima ganancia)
            elif price >= tp4:
                db.update_signal_status(signal_id, "TP4_ALCANZADO", price, "GANADA")
                self._save_event(signal_id, "TP4_ALCANZADO", price, f"TP4 alcanzado a ${price:.2f}")
                result_msg = f"🏆 Señal #{signal_id} BUY — TP4 ALCANZADO a ${price:.2f}"
                logger.info(result_msg)

            # TP3 alcanzado
            elif price >= tp3 and status not in ("TP3_ALCANZADO", "TP4_ALCANZADO"):
                db.update_signal_status(signal_id, "TP3_ALCANZADO")
                self._save_event(signal_id, "TP3_ALCANZADO", price, f"TP3 alcanzado a ${price:.2f}")
                result_msg = f"✅ Señal #{signal_id} BUY — TP3 alcanzado a ${price:.2f}"

            # TP2 alcanzado
            elif price >= tp2 and status not in ("TP2_ALCANZADO", "TP3_ALCANZADO", "TP4_ALCANZADO"):
                db.update_signal_status(signal_id, "TP2_ALCANZADO")
                self._save_event(signal_id, "TP2_ALCANZADO", price, f"TP2 alcanzado a ${price:.2f}")
                result_msg = f"✅ Señal #{signal_id} BUY — TP2 alcanzado a ${price:.2f}"

            # TP1 alcanzado
            elif price >= tp1 and status not in ("TP1_ALCANZADO", "TP2_ALCANZADO", "TP3_ALCANZADO", "TP4_ALCANZADO"):
                db.update_signal_status(signal_id, "TP1_ALCANZADO")
                self._save_event(signal_id, "TP1_ALCANZADO", price, f"TP1 alcanzado a ${price:.2f}")
                result_msg = f"✅ Señal #{signal_id} BUY — TP1 alcanzado a ${price:.2f}"

        elif signal_type == "SELL":
            # SL tocado
            if price >= sl:
                db.update_signal_status(signal_id, "SL_TOCADO", price, "PERDIDA")
                self._save_event(signal_id, "SL_TOCADO", price, f"SL tocado a ${price:.2f}")
                result_msg = f"⛔ Señal #{signal_id} SELL — SL TOCADO a ${price:.2f}"
                logger.info(result_msg)

            # TP4 alcanzado
            elif price <= tp4:
                db.update_signal_status(signal_id, "TP4_ALCANZADO", price, "GANADA")
                self._save_event(signal_id, "TP4_ALCANZADO", price, f"TP4 alcanzado a ${price:.2f}")
                result_msg = f"🏆 Señal #{signal_id} SELL — TP4 ALCANZADO a ${price:.2f}"
                logger.info(result_msg)

            # TP3 alcanzado
            elif price <= tp3 and status not in ("TP3_ALCANZADO", "TP4_ALCANZADO"):
                db.update_signal_status(signal_id, "TP3_ALCANZADO")
                self._save_event(signal_id, "TP3_ALCANZADO", price, f"TP3 alcanzado a ${price:.2f}")
                result_msg = f"✅ Señal #{signal_id} SELL — TP3 alcanzado a ${price:.2f}"

            # TP2 alcanzado
            elif price <= tp2 and status not in ("TP2_ALCANZADO", "TP3_ALCANZADO", "TP4_ALCANZADO"):
                db.update_signal_status(signal_id, "TP2_ALCANZADO")
                self._save_event(signal_id, "TP2_ALCANZADO", price, f"TP2 alcanzado a ${price:.2f}")
                result_msg = f"✅ Señal #{signal_id} SELL — TP2 alcanzado a ${price:.2f}"

            # TP1 alcanzado
            elif price <= tp1 and status not in ("TP1_ALCANZADO", "TP2_ALCANZADO", "TP3_ALCANZADO", "TP4_ALCANZADO"):
                db.update_signal_status(signal_id, "TP1_ALCANZADO")
                self._save_event(signal_id, "TP1_ALCANZADO", price, f"TP1 alcanzado a ${price:.2f}")
                result_msg = f"✅ Señal #{signal_id} SELL — TP1 alcanzado a ${price:.2f}"

        # Marcar como ACTIVA si aún no hay evento (señal esperando)
        if not result_msg and status == "APROBADA":
            db.update_signal_status(signal_id, "ACTIVA")

        return result_msg

    def _save_event(
        self, signal_id: int, event_type: str, price: float, message: str
    ) -> None:
        event = SignalEvent(
            signal_id  = signal_id,
            event_type = event_type,
            price      = price,
            message    = message,
        )
        try:
            db.save_signal_event(event)
        except Exception as e:
            logger.error(f"Error guardando evento de señal: {e}")

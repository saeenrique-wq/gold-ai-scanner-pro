"""
AI Committee — Comité de IAs que votan sobre una señal.
Para MVP usa solo Ollama. En el futuro puede incluir varias IAs.
La señal se aprueba solo si la mayoría vota APROBAR.
"""
from typing import List, Dict, Any
from models import AIResponse
from ai.ollama_client import OllamaClient
from config import get_logger

logger = get_logger("ai_committee")


class AICommittee:
    """
    Gestiona una o varias IAs y consolida su decisión.
    En MVP: Ollama es el único miembro activo.
    """

    def __init__(self, ollama_client: OllamaClient):
        self.ollama   = ollama_client
        self._clients: List[Dict] = []   # Lista para IAs externas futuras

    def evaluate(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Envía la señal a todas las IAs activas.
        Retorna un dict con la decisión consolidada.
        """
        votes: List[AIResponse] = []

        # ── Ollama (IA local) ───────────────────────────────────────────────
        if self.ollama.is_available():
            logger.info(f"Enviando señal a Ollama ({self.ollama.model})...")
            resp = self.ollama.analyze_signal(signal_data)
            votes.append(resp)
            if resp.valid:
                logger.info(
                    f"Ollama respondió: {resp.decision} | "
                    f"Confianza: {resp.confianza} | Riesgo: {resp.riesgo}"
                )
            else:
                logger.warning(f"Ollama: respuesta inválida — {resp.motivo}")
        else:
            logger.warning("Ollama no disponible. Sin confirmación de IA.")
            return {
                "approved":   False,
                "decision":   "SIN_CONFIRMACION_IA",
                "confianza":  "N/A",
                "riesgo":     "N/A",
                "motivo":     "Ollama no está corriendo. Inicia Ollama para obtener confirmación.",
                "provider":   "Ninguna",
                "votes":      [],
                "vote_count": 0,
            }

        # ── IAs externas (cuando el usuario las configure) ──────────────────
        for client_info in self._clients:
            client = client_info.get("client")
            if client and client.is_configured():
                try:
                    ext_resp = client.analyze_signal(signal_data)
                    votes.append(ext_resp)
                except Exception as e:
                    logger.error(f"Error con {client.name}: {e}")

        # ── Consolidar votos ─────────────────────────────────────────────────
        return self._consolidate(votes)

    def _consolidate(self, votes: List[AIResponse]) -> Dict[str, Any]:
        """Consolida votos. Requiere mayoría de APROBAR para pasar."""
        if not votes:
            return {
                "approved":   False,
                "decision":   "SIN_CONFIRMACION_IA",
                "confianza":  "N/A",
                "riesgo":     "ALTO",
                "motivo":     "No hubo IAs disponibles para evaluar.",
                "provider":   "Ninguna",
                "votes":      [],
                "vote_count": 0,
            }

        valid_votes  = [v for v in votes if v.valid]
        approve_count = sum(1 for v in valid_votes if v.decision == "APROBAR")
        reject_count  = sum(1 for v in valid_votes if v.decision == "RECHAZAR")
        high_risk     = any(v.riesgo == "ALTO" for v in valid_votes)
        low_conf      = any(v.confianza == "BAJA" for v in valid_votes)

        # Reglas duras de rechazo
        if high_risk:
            return self._build_result(
                votes, False, "RECHAZAR", "ALTA", "ALTO",
                "IA detectó riesgo ALTO — señal rechazada automáticamente."
            )
        if low_conf:
            return self._build_result(
                votes, False, "RECHAZAR", "BAJA", "MEDIO",
                "IA tiene confianza BAJA — señal rechazada."
            )

        approved = approve_count > 0 and approve_count >= reject_count
        best     = max(valid_votes, key=lambda v: ("ALTA" in v.confianza, "APROBAR" in v.decision))

        return self._build_result(
            votes,
            approved,
            "APROBAR" if approved else "RECHAZAR",
            best.confianza,
            best.riesgo,
            best.motivo,
        )

    def _build_result(
        self, votes, approved, decision, confianza, riesgo, motivo
    ) -> Dict[str, Any]:
        return {
            "approved":   approved,
            "decision":   decision,
            "confianza":  confianza,
            "riesgo":     riesgo,
            "motivo":     motivo,
            "provider":   "Ollama",
            "votes":      [
                {
                    "decision":  v.decision,
                    "confianza": v.confianza,
                    "riesgo":    v.riesgo,
                    "motivo":    v.motivo,
                    "valid":     v.valid,
                }
                for v in votes
            ],
            "vote_count": len(votes),
        }

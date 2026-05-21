"""
Cliente Ollama — IA local que corre en tu PC.
Evalúa señales técnicas y responde APROBAR o RECHAZAR.
No inventa precios. Solo evalúa los datos del scanner.
"""
import json
import time
from typing import Optional, Dict, Any

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    requests = None
    _REQUESTS_AVAILABLE = False

from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT, get_logger
from models import AIResponse

logger = get_logger("ollama_client")

# Prompt base enviado a Ollama — instrucciones estrictas
_SYSTEM_PROMPT = """Eres un analizador de señales de trading de ORO (XAUUSD).
Tu único trabajo: evaluar los datos técnicos que te envíen.

REGLAS:
- NO inventes precios.
- SOLO evalúa los datos recibidos.
- Responde ÚNICAMENTE con el JSON, sin texto extra.
- El campo "motivo" debe tener MÁXIMO 60 caracteres.

Formato EXACTO de respuesta (copia esta estructura):
{"decision":"APROBAR","confianza":"ALTA","motivo":"texto corto","riesgo":"BAJO"}

Valores válidos:
- decision: APROBAR, RECHAZAR, RIESGO_ALTO
- confianza: BAJA, MEDIA, ALTA
- riesgo: BAJO, MEDIO, ALTO"""


class OllamaClient:
    """
    Cliente HTTP para Ollama corriendo localmente.
    URL default: http://localhost:11434
    Modelo default: llama3

    Para instalar Ollama: https://ollama.ai
    Para descargar el modelo: ollama pull llama3
    """

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model:    str = OLLAMA_MODEL,
        timeout:  int = OLLAMA_TIMEOUT,
    ):
        self.base_url  = base_url.rstrip("/")
        self.model     = model
        self.timeout   = timeout
        self._available: Optional[bool] = None

    # ─── Verificar disponibilidad ─────────────────────────────────────────────

    def is_available(self, force_check: bool = False) -> bool:
        """Verifica si Ollama está corriendo y responde."""
        if not _REQUESTS_AVAILABLE:
            return False
        if self._available is not None and not force_check:
            return self._available
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            self._available = resp.status_code == 200
        except Exception:
            self._available = False
        return self._available

    def get_models(self) -> list:
        """Lista los modelos disponibles en Ollama."""
        if not self.is_available():
            return []
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    # ─── Analizar señal ───────────────────────────────────────────────────────

    def analyze_signal(self, signal_data: Dict[str, Any]) -> AIResponse:
        """
        Envía los datos técnicos de la señal a Ollama y retorna la evaluación.
        Si Ollama no responde, retorna AIResponse con valid=False.
        """
        if not _REQUESTS_AVAILABLE:
            return AIResponse(
                decision="RECHAZAR",
                motivo="requests no instalado. pip install requests",
                valid=False,
            )

        if not self.is_available(force_check=True):
            logger.warning("Ollama no disponible. Señal marcada SIN_CONFIRMACION_IA.")
            return AIResponse(
                decision="RECHAZAR",
                motivo="Ollama no está corriendo. Inicia Ollama primero.",
                valid=False,
            )

        prompt = self._build_prompt(signal_data)

        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model":  self.model,
                    "prompt": prompt,
                    "system": _SYSTEM_PROMPT,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,   # Baja temperatura → respuestas más precisas
                        "num_predict": 350,   # Suficiente para el JSON completo
                    },
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            raw_text = resp.json().get("response", "")
            return self._parse_response(raw_text)

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama tardó más de {self.timeout}s. Señal rechazada.")
            return AIResponse(
                decision="RECHAZAR",
                motivo=f"Ollama no respondió en {self.timeout}s.",
                valid=False,
            )
        except Exception as e:
            logger.error(f"Error comunicando con Ollama: {e}")
            return AIResponse(
                decision="RECHAZAR",
                motivo=f"Error de comunicación con Ollama: {str(e)[:80]}",
                valid=False,
            )

    # ─── Construir prompt ────────────────────────────────────────────────────

    def _build_prompt(self, data: Dict[str, Any]) -> str:
        ind = data.get("indicators", {})
        return f"""Analiza esta posible señal de XAUUSD (ORO):

Tipo de señal: {data.get('type', 'N/A')}
Precio de entrada: {data.get('entry', 0):.2f}
SL (Stop Loss): {data.get('sl', 0):.2f}
TP1: {data.get('tp1', 0):.2f}
TP2: {data.get('tp2', 0):.2f}
Riesgo en USD: ${data.get('risk_usd', 0):.2f}
Ganancia mínima: ${data.get('min_profit', 0):.2f}
Relación Riesgo-Beneficio: 1:{data.get('rr_ratio', 2):.1f}

Indicadores técnicos (datos reales del mercado):
- EMA50:  {ind.get('ema50', 0):.2f}
- EMA200: {ind.get('ema200', 0):.2f}
- RSI:    {ind.get('rsi', 0):.1f}
- MACD:   {ind.get('macd', 0):.4f}
- ATR:    {ind.get('atr', 0):.2f}
- Soporte:    {ind.get('support', 0):.2f}
- Resistencia:{ind.get('resistance', 0):.2f}
- Tendencia H1: {'Alcista' if ind.get('trend_up') else 'Bajista'}
- Vela confirmada: {'Alcista' if ind.get('candle_bullish') else 'Bajista'}

Puntuación de confirmaciones: {data.get('score', 0)}/10
Razones que pasaron: {', '.join(data.get('reasons', [])[:5])}

Evalúa si esta señal es válida y responde en JSON."""

    # ─── Parsear respuesta ────────────────────────────────────────────────────

    def _parse_response(self, raw: str) -> AIResponse:
        """
        Extrae el JSON de la respuesta de Ollama.
        Maneja JSON incompleto (sin llaves de cierre) que puede ocurrir
        cuando el modelo genera texto largo y se corta.
        Si el JSON no es válido o falta algún campo → rechaza.
        """
        if not raw or not raw.strip():
            return AIResponse(
                decision="RECHAZAR",
                motivo="Ollama respondió vacío.",
                raw=raw,
                valid=False,
            )

        # Buscar el bloque JSON dentro del texto
        start = raw.find("{")
        if start < 0:
            logger.warning(f"Ollama no devolvió JSON. Respuesta: {raw[:100]}")
            return AIResponse(
                decision="RECHAZAR",
                motivo="La IA no devolvió formato JSON válido.",
                raw=raw,
                valid=False,
            )

        end = raw.rfind("}") + 1
        # Si no hay } final, intentar cerrar el JSON manualmente
        if end <= start:
            json_str = raw[start:].rstrip() + "\n}"
        else:
            json_str = raw[start:end]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # Segundo intento: extraer campos con regex si el JSON está roto
            data = self._extract_fields_fallback(raw)
            if data is None:
                logger.warning(f"JSON inválido de Ollama. Texto: {json_str[:150]}")
                return AIResponse(
                    decision="RECHAZAR",
                    motivo="JSON inválido en respuesta de la IA.",
                    raw=raw,
                    valid=False,
                )

        required = {"decision", "confianza", "motivo", "riesgo"}
        if not required.issubset(data.keys()):
            missing = required - data.keys()
            return AIResponse(
                decision="RECHAZAR",
                motivo=f"Respuesta incompleta. Faltan: {missing}",
                raw=raw,
                valid=False,
            )

        valid_decisions   = {"APROBAR", "RECHAZAR", "PEDIR_MAS_CONFIRMACION", "RIESGO_ALTO"}
        valid_confidences = {"BAJA", "MEDIA", "ALTA"}
        valid_risks       = {"BAJO", "MEDIO", "ALTO"}

        decision  = str(data["decision"]).upper().strip()
        confianza = str(data["confianza"]).upper().strip()
        riesgo    = str(data["riesgo"]).upper().strip()

        if decision not in valid_decisions:
            decision = "RECHAZAR"
        if confianza not in valid_confidences:
            confianza = "BAJA"
        if riesgo not in valid_risks:
            riesgo = "ALTO"

        return AIResponse(
            decision  = decision,
            confianza = confianza,
            motivo    = str(data.get("motivo", ""))[:200],
            riesgo    = riesgo,
            raw       = raw,
            valid     = True,
        )

    def _extract_fields_fallback(self, raw: str) -> Optional[dict]:
        """
        Extrae los 4 campos del JSON usando búsqueda de texto simple,
        por si el JSON está incompleto o mal formado.
        """
        import re
        result = {}
        patterns = {
            "decision":  r'"decision"\s*:\s*"([^"]+)"',
            "confianza": r'"confianza"\s*:\s*"([^"]+)"',
            "motivo":    r'"motivo"\s*:\s*"([^"]+)"',
            "riesgo":    r'"riesgo"\s*:\s*"([^"]+)"',
        }
        for key, pattern in patterns.items():
            m = re.search(pattern, raw, re.IGNORECASE)
            result[key] = m.group(1).strip() if m else ""

        if result.get("decision"):
            return result
        return None

    def get_status_dict(self) -> Dict[str, Any]:
        available = self.is_available(force_check=True)
        models    = self.get_models() if available else []
        return {
            "available": available,
            "url":       self.base_url,
            "model":     self.model,
            "models":    models,
        }

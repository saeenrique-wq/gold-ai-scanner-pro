"""
Cliente Ollama — IA local.
Mejoras v2:
  - format:"json" para forzar JSON válido siempre
  - Warmup automático al conectar (carga modelo en RAM)
  - Timeout 90s, opciones optimizadas para respuesta rápida
  - Parser con fallback regex si JSON llega incompleto
"""
import json
import re
import time
import threading
from typing import Optional, Dict, Any

try:
    import requests
    _REQ_OK = True
except ImportError:
    requests = None
    _REQ_OK = False

from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT, get_logger
from models import AIResponse

logger = get_logger("ollama_client")

_SYSTEM_PROMPT = (
    "Eres un experto en trading de ORO (XAUUSD/GC=F). "
    "Reglas RSI: <30=sobreventa(alcista), 30-45=neutral-bajista, 45-55=neutral, 55-70=neutral-alcista, >70=sobrecompra(bajista). "
    "Reglas MACD: alcista=momentum sube, bajista=momentum baja. "
    "IMPORTANTE: Si score>=6 y MACD confirma dirección, APROBAR. Solo RECHAZAR si hay contradicción clara. "
    "Responde SOLO con JSON sin texto extra. "
    'Formato: {"decision":"APROBAR","confianza":"ALTA","motivo":"razon breve","riesgo":"BAJO"} '
    "decision: APROBAR|RECHAZAR|RIESGO_ALTO | confianza: BAJA|MEDIA|ALTA | riesgo: BAJO|MEDIO|ALTO"
)


class OllamaClient:
    """
    Cliente HTTP para Ollama local (http://localhost:11434).
    Usa format:'json' de Ollama para garantizar JSON válido.
    """

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model:    str = OLLAMA_MODEL,
        timeout:  int = OLLAMA_TIMEOUT,
    ):
        self.base_url   = base_url.rstrip("/")
        self.model      = model
        self.timeout    = timeout
        self._available: Optional[bool] = None
        self._warmed_up = False

    # ─── Estado ───────────────────────────────────────────────────────────────

    def is_available(self, force_check: bool = False) -> bool:
        if not _REQ_OK:
            return False
        if self._available is not None and not force_check:
            return self._available
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            self._available = (r.status_code == 200)
        except Exception:
            self._available = False
        return self._available

    def get_models(self) -> list:
        if not self.is_available():
            return []
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            return []

    # ─── Warmup (carga modelo en RAM) ────────────────────────────────────────

    def warmup(self) -> bool:
        """
        Envía un mensaje corto para cargar el modelo en memoria.
        La primera carga puede tardar 3-8s; las siguientes son rápidas.
        Llamar una sola vez al iniciar el scanner.
        """
        if self._warmed_up or not self.is_available():
            return self._warmed_up
        try:
            logger.info(f"Calentando modelo Ollama ({self.model})...")
            t0 = time.time()
            requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model":   self.model,
                    "prompt":  "Di OK",
                    "stream":  False,
                    "options": {"num_predict": 3, "num_ctx": 64},
                },
                timeout=60,
            )
            elapsed = time.time() - t0
            logger.info(f"Modelo listo en {elapsed:.1f}s.")
            self._warmed_up = True
            return True
        except Exception as e:
            logger.warning(f"Warmup falló (no crítico): {e}")
            return False

    def warmup_async(self) -> None:
        """Lanza el warmup en un hilo para no bloquear el scanner."""
        threading.Thread(target=self.warmup, daemon=True).start()

    # ─── Analizar señal ───────────────────────────────────────────────────────

    def analyze_signal(self, signal_data: Dict[str, Any]) -> AIResponse:
        if not _REQ_OK:
            return AIResponse(decision="RECHAZAR", motivo="requests no instalado.", valid=False)

        if not self.is_available(force_check=True):
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
                    "format": "json",          # ← Ollama fuerza JSON válido
                    "options": {
                        "temperature": 0.05,   # Muy determinista
                        "num_predict": 120,    # Solo los 4 campos del JSON
                        "num_ctx":     512,    # Contexto reducido → más rápido
                        "top_k":       10,
                        "top_p":       0.5,
                    },
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "")
            return self._parse(raw)

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama timeout ({self.timeout}s). Señal rechazada.")
            return AIResponse(
                decision="RECHAZAR",
                motivo=f"Ollama no respondió en {self.timeout}s. Intenta con un modelo más pequeño.",
                valid=False,
            )
        except Exception as e:
            logger.error(f"Error con Ollama: {e}")
            return AIResponse(
                decision="RECHAZAR",
                motivo=f"Error Ollama: {str(e)[:80]}",
                valid=False,
            )

    # ─── Prompt ───────────────────────────────────────────────────────────────

    def _build_prompt(self, data: Dict[str, Any]) -> str:
        ind  = data.get("indicators", {})
        tipo = data.get("type", "?")
        rsi  = ind.get("rsi", 50)
        # Explicar RSI explícitamente para evitar errores del modelo pequeño
        if rsi < 30:
            rsi_desc = f"RSI={rsi:.0f}(SOBREVENTA-alcista)"
        elif rsi > 70:
            rsi_desc = f"RSI={rsi:.0f}(SOBRECOMPRA-bajista)"
        else:
            rsi_desc = f"RSI={rsi:.0f}(neutral)"
        macd_desc = "MACD=alcista(sube)" if ind.get("macd_bullish") else "MACD=bajista(baja)"
        trend_desc = "H1=tendencia-SUBE" if ind.get("trend_up") else "H1=tendencia-BAJA"
        return (
            f"Señal {tipo} ORO. "
            f"Precio:{data.get('entry',0):.0f} SL:{data.get('sl',0):.0f} "
            f"TP1:{data.get('tp1',0):.0f} R/B:1:{data.get('rr_ratio',2):.0f}. "
            f"{rsi_desc} {macd_desc} {trend_desc} "
            f"ATR:{ind.get('atr',0):.1f} Score:{data.get('score',0)}/10. "
            f"EMA50:{ind.get('ema50',0):.0f} EMA200:{ind.get('ema200',0):.0f}. "
            "¿Esta señal es válida? Responde en JSON."
        )

    # ─── Parser ───────────────────────────────────────────────────────────────

    def _parse(self, raw: str) -> AIResponse:
        """Con format:'json' Ollama siempre devuelve JSON válido, pero validamos igual."""
        if not raw or not raw.strip():
            return AIResponse(decision="RECHAZAR", motivo="Respuesta vacía de Ollama.", raw=raw, valid=False)

        # Intentar parsear directamente
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Buscar bloque JSON dentro del texto
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(raw[start:end])
                except Exception:
                    data = None
            else:
                data = None

            # Último recurso: extraer campos con regex
            if data is None:
                data = self._regex_extract(raw)
                if data is None:
                    logger.warning(f"No se pudo parsear respuesta Ollama: {raw[:120]}")
                    return AIResponse(decision="RECHAZAR", motivo="JSON inválido de Ollama.", raw=raw, valid=False)

        # Normalizar valores
        VALID_DECISIONS   = {"APROBAR", "RECHAZAR", "RIESGO_ALTO", "PEDIR_MAS_CONFIRMACION"}
        VALID_CONFIDENCES = {"BAJA", "MEDIA", "ALTA"}
        VALID_RISKS       = {"BAJO", "MEDIO", "ALTO"}

        decision  = str(data.get("decision",  "RECHAZAR")).upper().strip()
        confianza = str(data.get("confianza", "BAJA")).upper().strip()
        riesgo    = str(data.get("riesgo",    "ALTO")).upper().strip()
        motivo    = str(data.get("motivo",    ""))[:200]

        if decision  not in VALID_DECISIONS:   decision  = "RECHAZAR"
        if confianza not in VALID_CONFIDENCES: confianza = "BAJA"
        if riesgo    not in VALID_RISKS:       riesgo    = "ALTO"

        return AIResponse(
            decision  = decision,
            confianza = confianza,
            motivo    = motivo,
            riesgo    = riesgo,
            raw       = raw,
            valid     = True,
        )

    def _regex_extract(self, raw: str) -> Optional[dict]:
        result = {}
        for key, pattern in [
            ("decision",  r'"decision"\s*:\s*"([^"]+)"'),
            ("confianza", r'"confianza"\s*:\s*"([^"]+)"'),
            ("motivo",    r'"motivo"\s*:\s*"([^"]+)"'),
            ("riesgo",    r'"riesgo"\s*:\s*"([^"]+)"'),
        ]:
            m = re.search(pattern, raw, re.IGNORECASE)
            result[key] = m.group(1).strip() if m else ""
        return result if result.get("decision") else None

    # ─── Info ─────────────────────────────────────────────────────────────────

    def get_status_dict(self) -> Dict[str, Any]:
        available = self.is_available(force_check=True)
        return {
            "available":  available,
            "url":        self.base_url,
            "model":      self.model,
            "models":     self.get_models() if available else [],
            "warmed_up":  self._warmed_up,
            "timeout":    self.timeout,
        }

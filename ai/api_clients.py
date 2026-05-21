"""
Clientes para IAs externas — OpenAI, Gemini, Claude, Groq, Mistral, OpenRouter.
Para MVP están preparados pero requieren API Key del usuario.
Se activan desde el panel de Configuración > IA & APIs.
"""
import json
from typing import Dict, Any, Optional
from models import AIResponse
from config import get_logger

logger = get_logger("api_clients")

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    requests = None
    _REQUESTS_OK = False


class BaseAIClient:
    """Base para todos los clientes de IA externa."""
    name = "Base"

    def __init__(self, api_key: str, model: str = ""):
        self.api_key = api_key
        self.model   = model

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def analyze_signal(self, signal_data: Dict[str, Any]) -> AIResponse:
        raise NotImplementedError

    def _build_prompt(self, data: Dict[str, Any]) -> str:
        ind = data.get("indicators", {})
        return (
            f"Analiza esta señal de XAUUSD: Tipo={data.get('type')} "
            f"Entrada={data.get('entry',0):.2f} SL={data.get('sl',0):.2f} "
            f"TP1={data.get('tp1',0):.2f} RSI={ind.get('rsi',0):.1f} "
            f"MACD={'alcista' if ind.get('macd_bullish') else 'bajista'} "
            f"Tendencia H1={'alcista' if ind.get('trend_up') else 'bajista'} "
            f"Score={data.get('score',0)}/10. "
            "Responde SOLO en JSON: "
            '{"decision":"APROBAR"/"RECHAZAR","confianza":"ALTA"/"MEDIA"/"BAJA",'
            '"motivo":"texto","riesgo":"BAJO"/"MEDIO"/"ALTO"}'
        )

    def _parse(self, raw: str) -> AIResponse:
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start < 0 or end <= start:
            return AIResponse(decision="RECHAZAR", motivo="JSON no encontrado.", raw=raw, valid=False)
        try:
            d = json.loads(raw[start:end])
            return AIResponse(
                decision  = str(d.get("decision",  "RECHAZAR")).upper(),
                confianza = str(d.get("confianza", "BAJA")).upper(),
                motivo    = str(d.get("motivo",    ""))[:200],
                riesgo    = str(d.get("riesgo",    "ALTO")).upper(),
                raw       = raw,
                valid     = True,
            )
        except Exception:
            return AIResponse(decision="RECHAZAR", motivo="JSON inválido.", raw=raw, valid=False)


class OpenAIClient(BaseAIClient):
    name = "OpenAI"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        super().__init__(api_key, model)

    def analyze_signal(self, signal_data: Dict[str, Any]) -> AIResponse:
        if not self.is_configured() or not _REQUESTS_OK:
            return AIResponse(decision="RECHAZAR", motivo="OpenAI no configurado.", valid=False)
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "Eres analista de trading de ORO. Responde solo en JSON válido."},
                        {"role": "user",   "content": self._build_prompt(signal_data)},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 200,
                },
                timeout=30,
            )
            content = resp.json()["choices"][0]["message"]["content"]
            return self._parse(content)
        except Exception as e:
            return AIResponse(decision="RECHAZAR", motivo=f"Error OpenAI: {str(e)[:80]}", valid=False)


class GeminiClient(BaseAIClient):
    name = "Gemini"

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        super().__init__(api_key, model)

    def analyze_signal(self, signal_data: Dict[str, Any]) -> AIResponse:
        if not self.is_configured() or not _REQUESTS_OK:
            return AIResponse(decision="RECHAZAR", motivo="Gemini no configurado.", valid=False)
        try:
            url  = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
            body = {"contents": [{"parts": [{"text": self._build_prompt(signal_data)}]}]}
            resp = requests.post(url, json=body, timeout=30)
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return self._parse(text)
        except Exception as e:
            return AIResponse(decision="RECHAZAR", motivo=f"Error Gemini: {str(e)[:80]}", valid=False)


class GroqClient(BaseAIClient):
    name = "Groq"

    def __init__(self, api_key: str, model: str = "llama3-8b-8192"):
        super().__init__(api_key, model)

    def analyze_signal(self, signal_data: Dict[str, Any]) -> AIResponse:
        if not self.is_configured() or not _REQUESTS_OK:
            return AIResponse(decision="RECHAZAR", motivo="Groq no configurado.", valid=False)
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "Analista de ORO. Responde solo en JSON."},
                        {"role": "user",   "content": self._build_prompt(signal_data)},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 200,
                },
                timeout=20,
            )
            content = resp.json()["choices"][0]["message"]["content"]
            return self._parse(content)
        except Exception as e:
            return AIResponse(decision="RECHAZAR", motivo=f"Error Groq: {str(e)[:80]}", valid=False)


class OpenRouterClient(BaseAIClient):
    name = "OpenRouter"

    def __init__(self, api_key: str, model: str = "meta-llama/llama-3-8b-instruct"):
        super().__init__(api_key, model)

    def analyze_signal(self, signal_data: Dict[str, Any]) -> AIResponse:
        if not self.is_configured() or not _REQUESTS_OK:
            return AIResponse(decision="RECHAZAR", motivo="OpenRouter no configurado.", valid=False)
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "Analista de ORO. Responde solo en JSON."},
                        {"role": "user",   "content": self._build_prompt(signal_data)},
                    ],
                    "temperature": 0.1,
                },
                timeout=20,
            )
            content = resp.json()["choices"][0]["message"]["content"]
            return self._parse(content)
        except Exception as e:
            return AIResponse(decision="RECHAZAR", motivo=f"Error OpenRouter: {str(e)[:80]}", valid=False)


def get_client(provider: str, api_key: str, model: str = "") -> Optional[BaseAIClient]:
    """Fábrica de clientes de IA."""
    clients = {
        "openai":      OpenAIClient,
        "gemini":      GeminiClient,
        "groq":        GroqClient,
        "openrouter":  OpenRouterClient,
    }
    cls = clients.get(provider.lower())
    if cls is None:
        logger.warning(f"Proveedor de IA no reconocido: {provider}")
        return None
    return cls(api_key=api_key, model=model)

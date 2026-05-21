# ⚜ GOLD AI SCANNER PRO

Scanner de ORO (XAUUSD) con IA local. Datos en vivo desde internet. Sin MetaTrader requerido.

---

## ¿Qué hace este sistema?

1. Se conecta al mercado en vivo (Yahoo Finance — gratis, sin registro)
2. Analiza el precio del ORO con indicadores técnicos (EMA, RSI, MACD, ATR)
3. Detecta posibles señales de COMPRA o VENTA
4. Le pregunta a tu IA local (Ollama) si la señal es buena
5. Si la IA aprueba → genera la señal con Entrada, SL, TP1, TP2, TP3, TP4
6. Registra todo en una base de datos local
7. Monitorea el precio y te avisa cuando toca TP o SL

---

## INSTALACIÓN PASO A PASO

### Paso 1 — Instalar Python

Si no tienes Python:
1. Ve a https://python.org
2. Descarga Python 3.11 o 3.12
3. Al instalar, **marca la opción "Add Python to PATH"**
4. Completa la instalación

### Paso 2 — Abrir la terminal en la carpeta del proyecto

1. Abre el Explorador de Archivos
2. Navega hasta: `C:\Users\[TuNombre]\gold_ai_scanner_pro\`
3. Haz clic en la barra de direcciones
4. Escribe `cmd` y presiona Enter

### Paso 3 — Instalar las dependencias

En la terminal que se abrió, escribe exactamente esto y presiona Enter:

```
pip install -r requirements.txt
```

Espera a que termine (puede tardar 2-3 minutos la primera vez).

### Paso 4 — Instalar Ollama (IA local)

1. Ve a: **https://ollama.ai**
2. Descarga Ollama para Windows
3. Instálalo normalmente
4. Abre una terminal nueva y escribe:
   ```
   ollama pull llama3
   ```
5. Espera a que descargue el modelo (puede tardar varios minutos)
6. Cuando termine, Ollama queda listo en segundo plano

> Si no quieres usar Ollama ahora, el scanner igual funciona pero las señales quedarán SIN confirmación de IA.

---

## EJECUTAR EL SCANNER

En la terminal dentro de la carpeta del proyecto, escribe:

```
streamlit run app.py
```

Se abrirá automáticamente en tu navegador en: **http://localhost:8501**

---

## CÓMO USARLO

### 1. Configura tu capital
- Ve a la pestaña **⚙️ Configuración**
- Elige tu capital: $200, $500, $1000 o personalizado
- El sistema calcula automáticamente el lotaje y el riesgo

### 2. Elige la temporalidad
- M5 para scalping rápido (recomendado)
- M15 para intradía
- H1 para swing

### 3. Inicia el scanner
- Haz clic en **▶ INICIAR SCANNER** en la barra lateral
- El sistema se conecta al mercado automáticamente

### 4. Espera la señal
- El scanner analiza el mercado cada 60 segundos
- Solo manda señal si hay mínimo 5/10 confirmaciones
- La IA debe aprobar antes de publicar la señal

### 5. Revisa la señal
- Verás en pantalla: Entrada, SL, TP1, TP2, TP3, TP4
- Cada señal tiene su gestión de riesgo calculada
- El sistema monitorea automáticamente si el precio toca TP o SL

---

## REGLAS DEL SISTEMA

- Máximo **12 señales por semana**
- Si se alcanza el límite, el scanner se detiene hasta el lunes
- Riesgo-beneficio mínimo **1:2** — si no hay espacio, no genera señal
- Si la IA rechaza → no se publica la señal

---

## PREGUNTAS FRECUENTES

**¿Necesito MetaTrader?**
No. El sistema usa Yahoo Finance directamente desde internet.

**¿Los datos son en tiempo real?**
Sí, Yahoo Finance provee datos con muy poco retraso (segundos).

**¿Puedo confiar en las señales al 100%?**
No. El trading siempre tiene riesgo. Este scanner ayuda a filtrar oportunidades, pero no garantiza ganancias. La efectividad real solo se sabe cuando haya historial suficiente.

**¿Qué pasa si Ollama no está corriendo?**
El scanner detecta la señal técnica pero la marca como "SIN CONFIRMACIÓN IA". No la publica como aprobada. Inicia Ollama para obtener confirmaciones.

**¿Cómo detengo el scanner?**
Haz clic en **⏹ DETENER SCANNER** en la barra lateral.

**¿Dónde se guarda el historial?**
En `data/scanner.db` — una base de datos local en tu PC.

---

## ADVERTENCIA LEGAL

> Este software es una herramienta de análisis técnico. Las señales generadas son
> para aprendizaje y apoyo a la decisión, NO constituyen asesoramiento financiero.
> El trading de divisas y metales preciosos conlleva un riesgo alto de pérdida de capital.
> Opera solo con dinero que puedas permitirte perder.
> La efectividad anunciada es una proyección teórica, no una garantía real.

---

## ESTRUCTURA DE ARCHIVOS

```
gold_ai_scanner_pro/
├── app.py                    ← Punto de entrada principal
├── config.py                 ← Configuración global
├── database.py               ← Base de datos SQLite
├── models.py                 ← Estructuras de datos
├── requirements.txt          ← Dependencias
├── market_data/
│   ├── market_connector.py   ← Conexión Yahoo Finance (datos en vivo)
│   └── mt5_connector.py      ← MetaTrader 5 (opcional)
├── strategy/
│   ├── indicators.py         ← EMA, RSI, MACD, ATR
│   ├── risk_manager.py       ← Gestión de riesgo, SL, TP
│   ├── gold_scalping_pro.py  ← Estrategia principal
│   └── signal_tracker.py     ← Seguimiento automático TP/SL
├── ai/
│   ├── ollama_client.py      ← IA local Ollama
│   ├── api_clients.py        ← OpenAI, Gemini, Groq (futuros)
│   └── ai_committee.py       ← Comité de IAs
├── alerts/
│   ├── telegram_alerts.py    ← Alertas Telegram
│   └── whatsapp_alerts.py    ← WhatsApp (fase futura)
├── web/
│   ├── styles.py             ← CSS futurista dorado
│   └── dashboard.py          ← Componentes visuales
├── data/
│   └── scanner.db            ← Base de datos (se crea automáticamente)
└── logs/
    └── scanner.log           ← Logs del sistema
```

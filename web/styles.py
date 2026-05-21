"""CSS personalizado para el dashboard — estilo futurista dorado."""


def load_css() -> str:
    """Retorna el bloque de estilos CSS para inyectar en Streamlit."""
    return """
    <style>
    /* Fuente y fondo */
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Rajdhani:wght@400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Rajdhani', sans-serif;
        background-color: #0a0a18;
        color: #e0e0e0;
    }

    /* Título principal */
    .main-title {
        font-family: 'Orbitron', monospace;
        font-size: 2.2rem;
        font-weight: 900;
        background: linear-gradient(90deg, #ffd700, #ff8c00, #ffd700);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        letter-spacing: 3px;
        padding: 10px 0;
        animation: glow 2s ease-in-out infinite alternate;
    }

    @keyframes glow {
        from { filter: drop-shadow(0 0 5px #ffd700); }
        to   { filter: drop-shadow(0 0 15px #ff8c00); }
    }

    /* Subtítulo */
    .subtitle {
        text-align: center;
        color: #888;
        font-size: 0.85rem;
        letter-spacing: 2px;
        margin-bottom: 20px;
    }

    /* Tarjetas de métricas */
    .metric-card {
        background: linear-gradient(135deg, #0d1117, #161b22);
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 16px;
        margin: 6px 0;
        text-align: center;
    }

    .metric-label {
        font-size: 0.7rem;
        color: #8b949e;
        letter-spacing: 1px;
        text-transform: uppercase;
        margin-bottom: 4px;
    }

    .metric-value {
        font-family: 'Orbitron', monospace;
        font-size: 1.4rem;
        font-weight: 700;
        color: #ffd700;
    }

    /* Señal BUY */
    .signal-buy {
        background: linear-gradient(135deg, #001a0e, #002d1a);
        border: 2px solid #00ff88;
        border-radius: 12px;
        padding: 20px;
        margin: 10px 0;
        box-shadow: 0 0 20px rgba(0,255,136,0.2);
    }

    /* Señal SELL */
    .signal-sell {
        background: linear-gradient(135deg, #1a0000, #2d0000);
        border: 2px solid #ff4444;
        border-radius: 12px;
        padding: 20px;
        margin: 10px 0;
        box-shadow: 0 0 20px rgba(255,68,68,0.2);
    }

    /* Estado conectado */
    .status-ok {
        display: inline-block;
        background: #001a0e;
        border: 1px solid #00ff88;
        color: #00ff88;
        border-radius: 20px;
        padding: 4px 14px;
        font-size: 0.8rem;
        font-weight: 700;
        letter-spacing: 1px;
    }

    /* Estado desconectado */
    .status-err {
        display: inline-block;
        background: #1a0000;
        border: 1px solid #ff4444;
        color: #ff4444;
        border-radius: 20px;
        padding: 4px 14px;
        font-size: 0.8rem;
        font-weight: 700;
        letter-spacing: 1px;
    }

    /* Estado pendiente */
    .status-warn {
        display: inline-block;
        background: #1a1400;
        border: 1px solid #ffee44;
        color: #ffee44;
        border-radius: 20px;
        padding: 4px 14px;
        font-size: 0.8rem;
        font-weight: 700;
        letter-spacing: 1px;
    }

    /* Panel de precio */
    .price-panel {
        font-family: 'Orbitron', monospace;
        font-size: 2.5rem;
        font-weight: 900;
        color: #ffd700;
        text-align: center;
        text-shadow: 0 0 20px rgba(255,215,0,0.5);
        padding: 10px;
    }

    /* Tabla de señales */
    .signal-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.85rem;
    }

    .signal-table th {
        background: #161b22;
        color: #ffd700;
        padding: 10px;
        text-align: left;
        border-bottom: 1px solid #30363d;
        font-family: 'Orbitron', monospace;
        font-size: 0.7rem;
        letter-spacing: 1px;
    }

    .signal-table td {
        padding: 10px;
        border-bottom: 1px solid #1c2128;
        color: #c9d1d9;
    }

    .signal-table tr:hover td {
        background: #161b22;
    }

    /* Botones */
    .stButton > button {
        background: linear-gradient(135deg, #ffd700, #ff8c00) !important;
        color: #000 !important;
        font-family: 'Orbitron', monospace !important;
        font-weight: 700 !important;
        border: none !important;
        border-radius: 8px !important;
        letter-spacing: 1px !important;
        padding: 0.6rem 1.5rem !important;
        transition: all 0.2s !important;
    }

    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 15px rgba(255,215,0,0.4) !important;
    }

    /* Selectbox y inputs */
    .stSelectbox > div > div,
    .stNumberInput > div > div > input {
        background: #161b22 !important;
        border-color: #30363d !important;
        color: #e0e0e0 !important;
    }

    /* Sidebar */
    .css-1d391kg, [data-testid="stSidebar"] {
        background: #0d1117 !important;
        border-right: 1px solid #30363d;
    }

    /* Separador */
    .divider {
        border: none;
        border-top: 1px solid #30363d;
        margin: 15px 0;
    }

    /* Chips de estado */
    .chip-buy      { color: #00ff88; font-weight: 700; }
    .chip-sell     { color: #ff4444; font-weight: 700; }
    .chip-gold     { color: #ffd700; font-weight: 700; }
    .chip-rejected { color: #888888; }
    .chip-ai       { color: #bf5fff; font-weight: 700; }

    /* Indicador de escaneo activo */
    .scanning-pulse {
        display: inline-block;
        width: 10px;
        height: 10px;
        background: #00ff88;
        border-radius: 50%;
        animation: pulse 1s ease-in-out infinite;
        margin-right: 8px;
    }

    @keyframes pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50%       { opacity: 0.4; transform: scale(0.8); }
    }

    /* Alerta de señal activa */
    .active-signal-banner {
        background: linear-gradient(90deg, #001a0e, #002d1a, #001a0e);
        border: 2px solid #00ff88;
        border-radius: 10px;
        padding: 12px 20px;
        text-align: center;
        animation: border-glow 1.5s ease-in-out infinite alternate;
    }

    @keyframes border-glow {
        from { box-shadow: 0 0 10px rgba(0,255,136,0.3); }
        to   { box-shadow: 0 0 25px rgba(0,255,136,0.6); }
    }

    /* Ocultar el menú de Streamlit */
    #MainMenu { visibility: hidden; }
    footer     { visibility: hidden; }
    </style>
    """

"""Diagnóstico rápido de todas las conexiones."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 50)
print("GOLD AI SCANNER - DIAGNÓSTICO")
print("=" * 50)

# ── yfinance ──────────────────────────────────────────────────────────────────
try:
    import yfinance as yf
    print("[OK] yfinance instalado")
except ImportError:
    print("[ERROR] yfinance NO instalado. Ejecuta: pip install yfinance")
    sys.exit(1)

# ── requests ──────────────────────────────────────────────────────────────────
try:
    import requests
    print("[OK] requests instalado")
except ImportError:
    print("[ERROR] requests NO instalado. Ejecuta: pip install requests")
    sys.exit(1)

# ── Internet ──────────────────────────────────────────────────────────────────
print("\n--- INTERNET ---")
try:
    r = requests.get("https://www.google.com", timeout=5)
    print(f"[OK] Conexión a internet activa (status {r.status_code})")
except Exception as e:
    print(f"[ERROR] Sin internet: {e}")

# ── Yahoo Finance API directa ─────────────────────────────────────────────────
print("\n--- YAHOO FINANCE ---")
symbols = ["GC=F", "GLD", "IAU"]
for sym in symbols:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=5m"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = r.json()
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        print(f"[OK] {sym} via API directa: ${price:.2f}")
        break
    except Exception as e:
        print(f"[FALLO] {sym} API directa: {e}")

# ── yfinance fast_info ────────────────────────────────────────────────────────
print("\n--- YFINANCE ---")
for sym in ["GC=F", "GLD", "IAU"]:
    try:
        t = yf.Ticker(sym)
        p = t.fast_info.last_price
        if p and p > 0:
            print(f"[OK] {sym} fast_info: ${float(p):.2f}")
            break
        else:
            print(f"[FALLO] {sym} fast_info devolvió: {p}")
    except Exception as e:
        print(f"[FALLO] {sym} fast_info: {e}")

for sym in ["GC=F", "GLD"]:
    try:
        t = yf.Ticker(sym)
        df = t.history(period="1d", interval="5m")
        if not df.empty:
            print(f"[OK] {sym} history: {len(df)} velas, último=${df['Close'].iloc[-1]:.2f}")
            break
        else:
            print(f"[FALLO] {sym} history: vacío")
    except Exception as e:
        print(f"[FALLO] {sym} history: {e}")

# ── Ollama ────────────────────────────────────────────────────────────────────
print("\n--- OLLAMA (IA LOCAL) ---")
try:
    r = requests.get("http://localhost:11434/api/tags", timeout=5)
    if r.status_code == 200:
        models = [m["name"] for m in r.json().get("models", [])]
        print(f"[OK] Ollama activo. Modelos: {models}")
    else:
        print(f"[FALLO] Ollama responde pero con error {r.status_code}")
except Exception as e:
    print(f"[FALLO] Ollama no responde: {e}")
    print("       Solución: abre la app de Ollama y espera que cargue")

print("\n" + "=" * 50)
print("FIN DEL DIAGNÓSTICO")
print("=" * 50)

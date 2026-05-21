"""
GOLD AI SCANNER PRO — Launcher
Ventana de control que abre el scanner en el navegador.
Este archivo se convierte en .exe con: CREAR_EJECUTABLE.bat
"""
import sys
import os
import subprocess
import threading
import webbrowser
import time
import shutil

# ─── Ruta del proyecto ────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    # Corriendo como .exe generado por PyInstaller
    PROJECT_DIR = os.path.dirname(sys.executable)
else:
    # Corriendo como script Python normal
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

APP_PY = os.path.join(PROJECT_DIR, "app.py")
PORT   = 8501
URL    = f"http://localhost:{PORT}"

# ─── Tkinter ─────────────────────────────────────────────────────────────────
try:
    import tkinter as tk
    from tkinter import font as tkfont
    HAS_TK = True
except ImportError:
    HAS_TK = False

_proc: subprocess.Popen = None


# ─── Lanzar / detener Streamlit ──────────────────────────────────────────────

def _find_python() -> str:
    """Busca Python en el sistema."""
    if not getattr(sys, "frozen", False):
        return sys.executable          # Mismo Python que corre este script
    # En modo .exe, buscar python en PATH del sistema
    for candidate in ("python", "python3", "python.exe", "python3.exe"):
        found = shutil.which(candidate)
        if found:
            return found
    return "python"


def _start_streamlit() -> bool:
    """Lanza Streamlit en segundo plano. Retorna True si arrancó bien."""
    global _proc
    if _proc and _proc.poll() is None:
        return True   # Ya está corriendo

    python = _find_python()
    if not os.path.exists(APP_PY):
        return False

    # En Windows: ocultar la ventana de consola del subprocess
    si = None
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags    |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0   # SW_HIDE

    _proc = subprocess.Popen(
        [python, "-m", "streamlit", "run", APP_PY,
         "--server.port",     str(PORT),
         "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        cwd        = PROJECT_DIR,
        startupinfo= si,
        stdout     = subprocess.DEVNULL,
        stderr     = subprocess.DEVNULL,
    )
    return True


def _stop_streamlit() -> None:
    global _proc
    if _proc and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except Exception:
            _proc.kill()
    _proc = None


def _is_running() -> bool:
    return _proc is not None and _proc.poll() is None


# ─── Interfaz gráfica ────────────────────────────────────────────────────────

class LauncherApp:
    BG       = "#0a0a18"
    GOLD     = "#ffd700"
    GREEN    = "#00ff88"
    RED      = "#ff4444"
    GRAY     = "#444466"
    FG       = "#e0e0e0"

    def __init__(self, root: tk.Tk):
        self.root   = root
        self.running = False

        self._setup_window()
        self._build_ui()
        self._update_loop()

    # ── Configurar ventana ────────────────────────────────────────────────────
    def _setup_window(self):
        self.root.title("GOLD AI SCANNER PRO")
        self.root.geometry("420x340")
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG)
        # Centrar en pantalla
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth()  - 420) // 2
        y = (self.root.winfo_screenheight() - 340) // 2
        self.root.geometry(f"420x340+{x}+{y}")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Construir UI ──────────────────────────────────────────────────────────
    def _build_ui(self):
        pad = {"padx": 20, "pady": 6}

        # Título
        tk.Label(
            self.root, text="⚜  GOLD AI SCANNER PRO",
            bg=self.BG, fg=self.GOLD,
            font=("Courier New", 14, "bold"),
        ).pack(pady=(18, 2))

        tk.Label(
            self.root, text="XAUUSD · IA LOCAL · TIEMPO REAL",
            bg=self.BG, fg="#555577",
            font=("Courier New", 8),
        ).pack()

        # Separador
        tk.Frame(self.root, bg=self.GRAY, height=1).pack(fill="x", padx=20, pady=12)

        # Estado del proceso
        self.lbl_status = tk.Label(
            self.root, text="● Inactivo",
            bg=self.BG, fg=self.GRAY,
            font=("Courier New", 10, "bold"),
        )
        self.lbl_status.pack()

        # URL
        self.lbl_url = tk.Label(
            self.root, text=URL,
            bg=self.BG, fg="#334455",
            font=("Courier New", 9),
            cursor="hand2",
        )
        self.lbl_url.pack(pady=2)
        self.lbl_url.bind("<Button-1>", lambda e: webbrowser.open(URL) if self.running else None)

        tk.Frame(self.root, bg=self.GRAY, height=1).pack(fill="x", padx=20, pady=12)

        # Botón principal
        self.btn = tk.Button(
            self.root,
            text="▶   INICIAR SCANNER",
            command=self._toggle,
            bg=self.GOLD, fg="#000000",
            font=("Courier New", 12, "bold"),
            relief="flat",
            activebackground="#ff8c00",
            activeforeground="#000",
            cursor="hand2",
            padx=20, pady=8,
            bd=0,
        )
        self.btn.pack(pady=8, ipadx=10)

        # Botón abrir en navegador
        self.btn_browser = tk.Button(
            self.root,
            text="🌐  Abrir en navegador",
            command=lambda: webbrowser.open(URL),
            bg="#1a1a2e", fg=self.FG,
            font=("Courier New", 9),
            relief="flat",
            cursor="hand2",
            activebackground="#252540",
            activeforeground=self.FG,
            padx=10, pady=4,
            bd=0,
            state="disabled",
        )
        self.btn_browser.pack(pady=2)

        tk.Frame(self.root, bg=self.GRAY, height=1).pack(fill="x", padx=20, pady=10)

        # Nota al pie
        tk.Label(
            self.root,
            text="⚠  El trading tiene riesgo. Usa capital que puedas perder.",
            bg=self.BG, fg="#333355",
            font=("Courier New", 7),
            wraplength=380,
        ).pack()

    # ── Lógica de inicio / parada ─────────────────────────────────────────────
    def _toggle(self):
        if not self.running:
            self._start()
        else:
            self._stop()

    def _start(self):
        self.btn.config(state="disabled", text="Iniciando...")
        self.lbl_status.config(text="● Iniciando...", fg=self.GOLD)
        threading.Thread(target=self._start_bg, daemon=True).start()

    def _start_bg(self):
        ok = _start_streamlit()
        if not ok:
            self.root.after(0, lambda: self._show_error(
                f"No se encontró app.py en:\n{PROJECT_DIR}\n\n"
                "Asegúrate de ejecutar desde la carpeta del proyecto."
            ))
            self.root.after(0, self._reset_btn)
            return
        # Esperar a que Streamlit arranque (~4 segundos) y abrir browser
        time.sleep(4)
        webbrowser.open(URL)
        self.root.after(0, self._mark_running)

    def _mark_running(self):
        self.running = True
        self.lbl_status.config(text="● Corriendo — abierto en tu navegador", fg=self.GREEN)
        self.lbl_url.config(fg="#00bfff")
        self.btn.config(
            state="normal",
            text="⏹   DETENER SCANNER",
            bg=self.RED,
            activebackground="#cc3333",
        )
        self.btn_browser.config(state="normal")

    def _stop(self):
        self.btn.config(state="disabled", text="Deteniendo...")
        threading.Thread(target=self._stop_bg, daemon=True).start()

    def _stop_bg(self):
        _stop_streamlit()
        time.sleep(1)
        self.root.after(0, self._mark_stopped)

    def _mark_stopped(self):
        self.running = False
        self.lbl_status.config(text="● Detenido", fg=self.GRAY)
        self.lbl_url.config(fg="#334455")
        self.btn.config(
            state="normal",
            text="▶   INICIAR SCANNER",
            bg=self.GOLD,
            activebackground="#ff8c00",
        )
        self.btn_browser.config(state="disabled")

    def _reset_btn(self):
        self.btn.config(state="normal", text="▶   INICIAR SCANNER", bg=self.GOLD)
        self.lbl_status.config(text="● Error al iniciar", fg=self.RED)

    def _show_error(self, msg):
        import tkinter.messagebox as mb
        mb.showerror("Error", msg)

    # ── Monitoreo automático ──────────────────────────────────────────────────
    def _update_loop(self):
        """Revisa cada 5 segundos si el proceso sigue corriendo."""
        if self.running and not _is_running():
            self._mark_stopped()
        self.root.after(5000, self._update_loop)

    # ── Cerrar ventana ────────────────────────────────────────────────────────
    def _on_close(self):
        if self.running:
            _stop_streamlit()
        self.root.destroy()


# ─── Punto de entrada ────────────────────────────────────────────────────────

def main():
    if not HAS_TK:
        # Sin tkinter: lanzar directamente sin GUI
        print("Iniciando GOLD AI SCANNER PRO...")
        _start_streamlit()
        time.sleep(4)
        webbrowser.open(URL)
        print(f"Abierto en: {URL}")
        print("Presiona Ctrl+C para detener.")
        try:
            while _is_running():
                time.sleep(2)
        except KeyboardInterrupt:
            _stop_streamlit()
        return

    root = tk.Tk()
    LauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

import sqlite3
import threading
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from config import DB_PATH, get_logger, MAX_WEEKLY_SIGNALS, WEEKLY_TARGET_WIN
from models import Signal, SignalEvent, WeeklyStats

logger = get_logger("database")
_db_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Crea todas las tablas si no existen."""
    with _db_lock:
        conn = _get_conn()
        try:
            c = conn.cursor()

            c.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at       TEXT    NOT NULL,
                broker           TEXT    DEFAULT 'Yahoo Finance',
                platform         TEXT    DEFAULT 'Online',
                symbol           TEXT    DEFAULT 'XAUUSD',
                timeframe        TEXT    DEFAULT 'M5',
                signal_type      TEXT    NOT NULL,
                entry            REAL    NOT NULL,
                sl               REAL    NOT NULL,
                tp1              REAL    NOT NULL,
                tp2              REAL    NOT NULL,
                tp3              REAL    NOT NULL,
                tp4              REAL    NOT NULL,
                risk_usd         REAL    DEFAULT 0,
                expected_profit  REAL    DEFAULT 0,
                rr_ratio         REAL    DEFAULT 2.0,
                lot_size         REAL    DEFAULT 0.01,
                status           TEXT    DEFAULT 'APROBADA',
                ai_provider      TEXT    DEFAULT '',
                ai_decision      TEXT    DEFAULT '',
                ai_confidence    TEXT    DEFAULT '',
                ai_reason        TEXT    DEFAULT '',
                result           TEXT    DEFAULT '',
                close_price      REAL    DEFAULT 0,
                closed_at        TEXT    DEFAULT '',
                score            INTEGER DEFAULT 0,
                signal_style     TEXT    DEFAULT 'Scalping'
            )""")

            c.execute("""
            CREATE TABLE IF NOT EXISTS signal_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id   INTEGER NOT NULL,
                event_time  TEXT    NOT NULL,
                event_type  TEXT    NOT NULL,
                price       REAL    DEFAULT 0,
                message     TEXT    DEFAULT '',
                FOREIGN KEY (signal_id) REFERENCES signals(id)
            )""")

            c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                key   TEXT NOT NULL UNIQUE,
                value TEXT NOT NULL
            )""")

            c.execute("""
            CREATE TABLE IF NOT EXISTS ai_providers (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                provider_type TEXT NOT NULL,
                api_key       TEXT DEFAULT '',
                model         TEXT DEFAULT '',
                enabled       INTEGER DEFAULT 0,
                mode          TEXT DEFAULT 'confirmadora',
                priority      INTEGER DEFAULT 1
            )""")

            c.execute("""
            CREATE TABLE IF NOT EXISTS market_logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                level      TEXT NOT NULL,
                message    TEXT NOT NULL,
                source     TEXT DEFAULT ''
            )""")

            c.execute("""
            CREATE TABLE IF NOT EXISTS weekly_stats (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                week_start      TEXT NOT NULL UNIQUE,
                week_end        TEXT NOT NULL,
                total_signals   INTEGER DEFAULT 0,
                won_signals     INTEGER DEFAULT 0,
                lost_signals    INTEGER DEFAULT 0,
                partial_signals INTEGER DEFAULT 0,
                win_rate        REAL    DEFAULT 0,
                net_profit      REAL    DEFAULT 0,
                capital_start   REAL    DEFAULT 0,
                capital_end     REAL    DEFAULT 0
            )""")

            # Datos iniciales de configuración
            defaults = [
                ("capital",           "200"),
                ("risk_usd",          "7"),
                ("lot_size",          "0.01"),
                ("symbol",            "GC=F"),
                ("display_symbol",    "XAUUSD"),
                ("timeframe_entry",   "M5"),
                ("timeframe_confirm", "M15"),
                ("timeframe_trend",   "H1"),
                ("signal_style",      "Scalping"),
                ("ollama_model",      "llama3.2:3b"),
                ("ollama_url",        "http://localhost:11434"),
                ("telegram_token",    ""),
                ("telegram_chat_id",  ""),
            ]
            for key, val in defaults:
                c.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (key, val),
                )

            conn.commit()
            logger.info("Base de datos inicializada correctamente.")
        except Exception as e:
            logger.error(f"Error inicializando base de datos: {e}")
            raise
        finally:
            conn.close()


# ─── Settings ────────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default
        finally:
            conn.close()


def set_setting(key: str, value: str) -> None:
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()


# ─── Señales ─────────────────────────────────────────────────────────────────

def save_signal(signal: Signal) -> int:
    """Guarda una señal nueva y retorna el ID asignado."""
    with _db_lock:
        conn = _get_conn()
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur = conn.execute("""
                INSERT INTO signals
                (created_at, broker, platform, symbol, timeframe, signal_type,
                 entry, sl, tp1, tp2, tp3, tp4, risk_usd, expected_profit,
                 rr_ratio, lot_size, status, ai_provider, ai_decision,
                 ai_confidence, ai_reason, score, signal_style)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                now, signal.broker, signal.platform, signal.symbol,
                signal.timeframe, signal.signal_type,
                signal.entry, signal.sl, signal.tp1, signal.tp2,
                signal.tp3, signal.tp4, signal.risk_usd, signal.expected_profit,
                signal.rr_ratio, signal.lot_size, signal.status,
                signal.ai_provider, signal.ai_decision, signal.ai_confidence,
                signal.ai_reason, signal.score, signal.signal_style,
            ))
            conn.commit()
            new_id = cur.lastrowid
            logger.info(f"Señal guardada ID={new_id} tipo={signal.signal_type}")
            return new_id
        finally:
            conn.close()


def update_signal_status(signal_id: int, status: str, close_price: float = 0.0,
                         result: str = "") -> None:
    with _db_lock:
        conn = _get_conn()
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if close_price > 0:
                conn.execute("""
                    UPDATE signals SET status=?, result=?, close_price=?, closed_at=?
                    WHERE id=?
                """, (status, result, close_price, now, signal_id))
            else:
                conn.execute(
                    "UPDATE signals SET status=? WHERE id=?",
                    (status, signal_id),
                )
            conn.commit()
        finally:
            conn.close()


def save_signal_event(event: SignalEvent) -> None:
    with _db_lock:
        conn = _get_conn()
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("""
                INSERT INTO signal_events (signal_id, event_time, event_type, price, message)
                VALUES (?,?,?,?,?)
            """, (event.signal_id, now, event.event_type, event.price, event.message))
            conn.commit()
        finally:
            conn.close()


def get_active_signals() -> List[Dict]:
    """Retorna señales en estado ACTIVA."""
    active_states = ("ACTIVA", "APROBADA")
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute("""
                SELECT * FROM signals
                WHERE status IN ({})
                ORDER BY created_at DESC
            """.format(",".join("?" * len(active_states))),
                active_states,
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_signals_history(limit: int = 50) -> List[Dict]:
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def delete_all_signals() -> int:
    """Borra todas las señales y eventos. Retorna cantidad eliminada."""
    with _db_lock:
        conn = _get_conn()
        try:
            n = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
            conn.execute("DELETE FROM signal_events")
            conn.execute("DELETE FROM signals")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='signals'")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='signal_events'")
            conn.commit()
            logger.info(f"Borradas {n} señales y sus eventos.")
            return n
        except Exception as e:
            logger.error(f"Error borrando señales: {e}")
            return 0
        finally:
            conn.close()


def recent_duplicate_exists(signal_type: str, entry: float,
                            minutes: int = 60, tolerance: float = 8.0) -> bool:
    """Devuelve True si ya existe una señal similar en los últimos N minutos."""
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute("""
                SELECT COUNT(*) AS n FROM signals
                WHERE signal_type = ?
                  AND ABS(entry - ?) <= ?
                  AND created_at >= ?
                  AND status NOT IN ('RECHAZADA','CANCELADA')
            """, (signal_type, entry, tolerance, cutoff)).fetchone()
            return (row["n"] or 0) > 0
        finally:
            conn.close()


def get_signal_by_id(signal_id: int) -> Optional[Dict]:
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM signals WHERE id=?", (signal_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


# ─── Estadísticas semanales ──────────────────────────────────────────────────

def _get_week_bounds() -> tuple:
    today = datetime.now().date()
    start = today - timedelta(days=today.weekday())   # lunes
    end   = start + timedelta(days=6)                 # domingo
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def get_weekly_stats(capital: float = 0.0) -> WeeklyStats:
    week_start, week_end = _get_week_bounds()
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute("""
                SELECT
                    COUNT(*)                                          AS total,
                    SUM(CASE WHEN result='GANADA'  THEN 1 ELSE 0 END) AS won,
                    SUM(CASE WHEN result='PERDIDA' THEN 1 ELSE 0 END) AS lost,
                    SUM(CASE WHEN result IN ('TP1','TP2','TP3') THEN 1 ELSE 0 END) AS partial,
                    SUM(CASE WHEN result='GANADA'  THEN expected_profit ELSE 0 END)
                  - SUM(CASE WHEN result='PERDIDA' THEN risk_usd       ELSE 0 END) AS net
                FROM signals
                WHERE DATE(created_at) BETWEEN ? AND ?
                  AND status NOT IN ('RECHAZADA','BUSCANDO','EN_REVISION_IA','POSIBLE_ENTRADA')
            """, (week_start, week_end)).fetchone()

            total   = row["total"]   or 0
            won     = row["won"]     or 0
            lost    = row["lost"]    or 0
            partial = row["partial"] or 0
            net     = row["net"]     or 0.0
            win_rate = (won / total * 100) if total > 0 else 0.0

            return WeeklyStats(
                week_start    = week_start,
                week_end      = week_end,
                total_signals = total,
                won_signals   = won,
                lost_signals  = lost,
                partial_signals = partial,
                win_rate      = round(win_rate, 1),
                net_profit    = round(net, 2),
                capital_start = capital,
                capital_end   = round(capital + net, 2),
            )
        finally:
            conn.close()


def weekly_limit_reached() -> bool:
    week_start, week_end = _get_week_bounds()
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute("""
                SELECT COUNT(*) AS total FROM signals
                WHERE DATE(created_at) BETWEEN ? AND ?
                  AND status NOT IN ('RECHAZADA','BUSCANDO','EN_REVISION_IA','POSIBLE_ENTRADA')
            """, (week_start, week_end)).fetchone()
            return (row["total"] or 0) >= MAX_WEEKLY_SIGNALS
        finally:
            conn.close()


# ─── Log de mercado ──────────────────────────────────────────────────────────

def log_market(level: str, message: str, source: str = "") -> None:
    with _db_lock:
        conn = _get_conn()
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("""
                INSERT INTO market_logs (created_at, level, message, source)
                VALUES (?,?,?,?)
            """, (now, level, message, source))
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()


def get_market_logs(limit: int = 100) -> List[Dict]:
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM market_logs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

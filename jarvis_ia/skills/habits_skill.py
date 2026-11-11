"""
skills/habits_skill.py — JARVIS aprende tus hábitos de uso.

Qué rastrea automáticamente:
  - A qué hora te conectas cada día
  - Qué comandos usas más (y a qué hora del día)
  - Qué música pones y en qué plataforma
  - Qué apps abres con frecuencia
  - Patrones por día de la semana

Comandos que entiende JARVIS:
  "¿cuáles son mis hábitos?"
  "¿qué hago los lunes?"
  "¿qué música suelo poner?"
  "mis comandos más usados"
  "¿a qué hora me conecto?"
  "analiza mis hábitos"

Se activa solo en el saludo si detecta un patrón repetido:
  → "Los lunes por la mañana sueles poner Crunchyroll. ¿Lo hago?"
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path


_DB_PATH = Path("data/jarvis.db")

_DIAS = ["lunes", "martes", "miércoles", "jueves",
         "viernes", "sábado", "domingo"]

_TURNO = [
    (range(5,  12), "mañana"),
    (range(12, 14), "mediodía"),
    (range(14, 19), "tarde"),
    (range(19, 24), "noche"),
    (range(0,   5), "madrugada"),
]

_NOMBRES_INTENT = {
    "tv":           "ver algo en la tele",
    "media":        "reproducir música",
    "web":          "buscar en internet",
    "create_note":  "anotar algo",
    "reminder":     "poner un recordatorio",
    "network":      "revisar la red",
    "phone":        "algo con el celular",
    "file_manager": "manejar archivos",
    "system":       "comandos del sistema",
    "open_app":     "abrir una app",
    "get_time":     "pedir la hora",
    "rag":          "buscar en tu memoria",
    "habits":       "ver tus hábitos",
    "network":      "escanear la red",
}


def _turno(hora: int) -> str:
    for rng, nombre in _TURNO:
        if hora in rng:
            return nombre
    return ""


# ─────────────────────────────────────────────────────────────────────────────
#  HabitTracker — registra eventos en la DB
# ─────────────────────────────────────────────────────────────────────────────

class HabitTracker:

    def __init__(self):
        self._init_table()

    def _conn(self):
        return sqlite3.connect(_DB_PATH)

    def _init_table(self):
        """Crea la tabla habit_log si no existe (no toca las tablas existentes)."""
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS habit_log (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts      TEXT    NOT NULL,
                    intent  TEXT    NOT NULL,
                    command TEXT    NOT NULL,
                    hour    INTEGER NOT NULL,
                    weekday INTEGER NOT NULL,
                    extra   TEXT
                )
            """)
            c.commit()

    def log(self, intent: str, command: str, extra: dict = None):
        """Registra un comando ejecutado."""
        now = datetime.now()
        # No registrar intents que no aportan valor a los hábitos
        if intent in ("confirm_action", "cancel_action", "unknown", "custom_intent"):
            return
        with self._conn() as c:
            c.execute(
                "INSERT INTO habit_log (ts, intent, command, hour, weekday, extra) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    now.isoformat(),
                    intent,
                    command[:200],
                    now.hour,
                    now.weekday(),
                    json.dumps(extra, ensure_ascii=False) if extra else None,
                )
            )
            c.commit()

    def log_session_start(self):
        """Registra el inicio de sesión."""
        now = datetime.now()
        with self._conn() as c:
            c.execute(
                "INSERT INTO habit_log (ts, intent, command, hour, weekday, extra) "
                "VALUES (?, 'session_start', 'inicio de sesión', ?, ?, NULL)",
                (now.isoformat(), now.hour, now.weekday())
            )
            c.commit()


# ─────────────────────────────────────────────────────────────────────────────
#  HabitAnalyzer — analiza los patrones registrados
# ─────────────────────────────────────────────────────────────────────────────

class HabitAnalyzer:

    def _q(self, sql, params=()):
        with sqlite3.connect(_DB_PATH) as c:
            return c.execute(sql, params).fetchall()

    def total(self, days=30) -> int:
        r = self._q(
            "SELECT COUNT(*) FROM habit_log WHERE ts > datetime('now', ?)",
            (f"-{days} days",)
        )
        return r[0][0] if r else 0

    def hora_pico(self, days=30):
        """Hora del día con más actividad. Retorna (hora, turno)."""
        r = self._q(
            """SELECT hour, COUNT(*) FROM habit_log
               WHERE intent != 'session_start' AND ts > datetime('now', ?)
               GROUP BY hour ORDER BY COUNT(*) DESC LIMIT 1""",
            (f"-{days} days",)
        )
        if r:
            return r[0][0], _turno(r[0][0])
        return None, None

    def dia_pico(self, days=30) -> str | None:
        """Día de la semana con más actividad."""
        r = self._q(
            """SELECT weekday, COUNT(*) FROM habit_log
               WHERE ts > datetime('now', ?)
               GROUP BY weekday ORDER BY COUNT(*) DESC LIMIT 1""",
            (f"-{days} days",)
        )
        return _DIAS[r[0][0]] if r else None

    def horarios_conexion(self, days=30, limit=4):
        """Horas más frecuentes de inicio de sesión."""
        return self._q(
            """SELECT hour, COUNT(*) FROM habit_log
               WHERE intent='session_start' AND ts > datetime('now', ?)
               GROUP BY hour ORDER BY COUNT(*) DESC LIMIT ?""",
            (f"-{days} days", limit)
        )

    def intents_frecuentes(self, days=30, limit=10):
        """Top intents más usados."""
        return self._q(
            """SELECT intent, COUNT(*) FROM habit_log
               WHERE intent NOT IN ('session_start', 'unknown', 'habits')
                 AND ts > datetime('now', ?)
               GROUP BY intent ORDER BY COUNT(*) DESC LIMIT ?""",
            (f"-{days} days", limit)
        )

    def musica_frecuente(self, days=30, limit=8):
        """
        Plataformas y canciones más reproducidas.
        Retorna lista de (extra_dict, count).
        """
        rows = self._q(
            """SELECT extra, COUNT(*) FROM habit_log
               WHERE intent IN ('tv', 'media')
                 AND extra IS NOT NULL
                 AND ts > datetime('now', ?)
               GROUP BY extra ORDER BY COUNT(*) DESC LIMIT ?""",
            (f"-{days} days", limit)
        )
        results = []
        seen = set()
        for extra_json, count in rows:
            try:
                extra = json.loads(extra_json)
                # Solo nos interesan entradas con contenido de música
                q   = extra.get("query", "").strip()
                plt = extra.get("plataforma", "").strip()
                if not q and not plt:
                    continue
                key = f"{q}|{plt}"
                if key in seen:
                    continue
                seen.add(key)
                results.append((extra, count))
            except Exception:
                pass
        return results

    def patron_dia(self, weekday: int, days=60, limit=5):
        """Top intents de un día de la semana específico."""
        return self._q(
            """SELECT intent, COUNT(*) FROM habit_log
               WHERE weekday=? AND intent NOT IN ('session_start','unknown','habits')
                 AND ts > datetime('now', ?)
               GROUP BY intent ORDER BY COUNT(*) DESC LIMIT ?""",
            (weekday, f"-{days} days", limit)
        )

    def sugerencia_contextual(self) -> str | None:
        """
        Genera una sugerencia basada en la hora y día actuales.
        Solo sugiere si el patrón tiene al menos 3 repeticiones.
        Retorna None si no hay suficiente historial.
        """
        if self.total(days=14) < 5:
            return None

        now  = datetime.now()
        hora = now.hour
        dia  = now.weekday()

        # Qué se suele hacer a esta hora en este día de la semana
        rows = self._q(
            """SELECT intent, extra, COUNT(*) FROM habit_log
               WHERE weekday = ?
                 AND hour BETWEEN ? AND ?
                 AND intent NOT IN ('session_start','unknown','habits',
                                    'confirm_action','cancel_action')
                 AND ts > datetime('now', '-45 days')
               GROUP BY intent ORDER BY COUNT(*) DESC LIMIT 1""",
            (dia, max(0, hora - 1), min(23, hora + 1))
        )

        if not rows or rows[0][2] < 3:
            return None

        intent, extra_json, _ = rows[0]
        extra = {}
        if extra_json:
            try:
                extra = json.loads(extra_json)
            except Exception:
                pass

        # Construir descripción legible de la acción
        q   = extra.get("query", "").strip()
        plt = extra.get("plataforma", "").strip()

        if q and plt:
            accion = f"poner '{q}' en {plt}"
        elif plt:
            accion = f"abrir {plt}"
        elif q:
            accion = f"buscar '{q}'"
        else:
            accion = _NOMBRES_INTENT.get(intent, intent.replace("_", " "))

        return f"Los {_DIAS[dia]} por la {_turno(hora)} sueles {accion}. ¿Lo hago?"


# ─────────────────────────────────────────────────────────────────────────────
#  HabitsSkill — skill principal
# ─────────────────────────────────────────────────────────────────────────────

class HabitsSkill:

    def __init__(self):
        self.tracker  = HabitTracker()
        self.analyzer = HabitAnalyzer()

    # ── Interfaz pública para assistant.py ───────────────────────────────────

    def log(self, intent: str, command: str, data: dict = None):
        """Llamado desde assistant.py después de cada comando ejecutado."""
        self.tracker.log(intent, command, data)

    def log_session_start(self):
        """Llamado desde assistant.py al arrancar JARVIS."""
        self.tracker.log_session_start()

    def sugerencia_contextual(self) -> str | None:
        """Llamado desde assistant.py al arrancar para saludar con sugerencia."""
        return self.analyzer.sugerencia_contextual()

    # ── Router del skill ─────────────────────────────────────────────────────

    def run(self, data: dict) -> str:
        action = data.get("action", "resumen")
        query  = data.get("query", "").lower()

        if action == "musica":   return self._musica()
        if action == "comandos": return self._comandos()
        if action == "horario":  return self._horario()
        if action == "dia":
            for i, nombre in enumerate(_DIAS):
                if nombre in query or nombre.replace("é","e").replace("á","a") in query:
                    return self._dia(i, nombre)
        return self._resumen()

    # ── Respuestas ────────────────────────────────────────────────────────────

    def _resumen(self) -> str:
        total = self.analyzer.total()
        if total < 3:
            return ("Todavía no tengo suficiente historial para analizar tus hábitos. "
                    "Úsame unos días más y podré darte un resumen completo.")

        lineas = [f"Resumen de tus hábitos (últimos 30 días — {total} acciones registradas):"]

        # Hora pico
        hora, turno = self.analyzer.hora_pico()
        if hora is not None:
            lineas.append(f"\n  Hora de mayor actividad: {hora}:00 ({turno})")

        # Día más activo
        dia = self.analyzer.dia_pico()
        if dia:
            lineas.append(f"  Día más activo: {dia}")

        # Horarios de conexión
        horarios = self.analyzer.horarios_conexion()
        if horarios:
            horas_str = ", ".join(f"{h}:00" for h, _ in horarios[:3])
            lineas.append(f"  Sueles conectarme a las: {horas_str}")

        # Top comandos
        lineas.append("\n  Comandos que más usas:")
        for intent, count in self.analyzer.intents_frecuentes(limit=5):
            nombre = _NOMBRES_INTENT.get(intent, intent.replace("_", " "))
            lineas.append(f"    {nombre}: {count} veces")

        # Música
        musica = self.analyzer.musica_frecuente(limit=3)
        if musica:
            lineas.append("\n  Música/contenido favorito:")
            for extra, count in musica:
                q   = extra.get("query", "")
                plt = extra.get("plataforma", "")
                desc = f"{q} en {plt}" if q and plt else q or plt
                if desc:
                    lineas.append(f"    {desc}: {count} veces")

        lineas.append("\n  Di 'mis comandos más usados', '¿qué hago los lunes?' o '¿qué música suelo poner?' para más detalles.")
        return "\n".join(lineas)

    def _musica(self) -> str:
        musica = self.analyzer.musica_frecuente(limit=10)
        if not musica:
            return ("Sin historial de música todavía. "
                    "Pide canciones o abre plataformas y las aprenderé.")
        lineas = ["Tu música y contenido más frecuente:"]
        for extra, count in musica:
            q   = extra.get("query", "")
            plt = extra.get("plataforma", "")
            desc = f"{q} en {plt}" if q and plt else q or plt or "—"
            lineas.append(f"  {desc} — {count} veces")
        return "\n".join(lineas)

    def _comandos(self) -> str:
        rows = self.analyzer.intents_frecuentes(limit=10)
        if not rows:
            return "Sin historial suficiente todavía."
        lineas = ["Tus comandos más usados (últimos 30 días):"]
        for i, (intent, count) in enumerate(rows, 1):
            nombre = _NOMBRES_INTENT.get(intent, intent.replace("_", " "))
            lineas.append(f"  {i}. {nombre}: {count} veces")
        return "\n".join(lineas)

    def _horario(self) -> str:
        rows = self.analyzer.horarios_conexion()
        if not rows:
            return "Sin historial de conexiones todavía."
        lineas = ["Tus horas de conexión más frecuentes:"]
        for hora, count in rows:
            lineas.append(f"  {hora}:00 ({_turno(hora)}) — {count} sesiones")
        return "\n".join(lineas)

    def _dia(self, dia_idx: int, dia_nombre: str) -> str:
        rows = self.analyzer.patron_dia(dia_idx)
        if not rows:
            return f"Sin suficiente historial para los {dia_nombre}."
        lineas = [f"Lo que más haces los {dia_nombre}:"]
        for intent, count in rows:
            nombre = _NOMBRES_INTENT.get(intent, intent.replace("_", " "))
            lineas.append(f"  {nombre}: {count} veces")
        return "\n".join(lineas)
import sqlite3
from datetime import datetime
from pathlib import Path


# Raíz del proyecto (jarvis_ia/). Antes era Path("data"), relativa al
# directorio desde el que arrancabas: si abrías JARVIS desde otra carpeta se
# creaba una base vacía y se perdían historial, notas y recordatorios.
# Por eso había dos jarvis.db en el proyecto.
_RAIZ = Path(__file__).resolve().parent.parent


class Database:
    def __init__(self, db_path=None):
        self.db_folder = _RAIZ / "data"
        self.db_folder.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path) if db_path else self.db_folder / "jarvis.db"
        self.create_tables()
        self.update_tables()

    def connect(self):
        return sqlite3.connect(self.db_path)

    def create_tables(self):
        connection = self.connect()
        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS command_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command TEXT NOT NULL,
                response TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                remind_at TEXT,
                is_done INTEGER DEFAULT 0
            )
        """)

        connection.commit()
        connection.close()

    def update_tables(self):
        connection = self.connect()
        cursor = connection.cursor()

        cursor.execute("PRAGMA table_info(reminders)")
        columns = [column[1] for column in cursor.fetchall()]

        if "remind_at" not in columns:
            cursor.execute("ALTER TABLE reminders ADD COLUMN remind_at TEXT")

        if "is_done" not in columns:
            cursor.execute("ALTER TABLE reminders ADD COLUMN is_done INTEGER DEFAULT 0")

        connection.commit()
        connection.close()

    def save_note(self, content):
        connection = self.connect()
        cursor = connection.cursor()

        cursor.execute(
            "INSERT INTO notes (content, created_at) VALUES (?, ?)",
            (content, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )

        connection.commit()
        connection.close()

    def get_notes(self):
        connection = self.connect()
        cursor = connection.cursor()

        cursor.execute("SELECT id, content, created_at FROM notes ORDER BY id DESC")
        notes = cursor.fetchall()

        connection.close()
        return notes

    def delete_notes(self):
        connection = self.connect()
        cursor = connection.cursor()

        cursor.execute("DELETE FROM notes")

        connection.commit()
        connection.close()

    def save_command(self, command, response):
        connection = self.connect()
        cursor = connection.cursor()

        cursor.execute(
            "INSERT INTO command_history (command, response, created_at) VALUES (?, ?, ?)",
            (command, response, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )

        connection.commit()
        connection.close()

    def get_history(self):
        connection = self.connect()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT command, response, created_at 
            FROM command_history 
            ORDER BY id DESC 
            LIMIT 10
        """)

        history = cursor.fetchall()

        connection.close()
        return history

    def delete_history(self):
        connection = self.connect()
        cursor = connection.cursor()

        cursor.execute("DELETE FROM command_history")

        connection.commit()
        connection.close()

    def save_reminder(self, content, remind_at=None):
        connection = self.connect()
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO reminders (content, created_at, remind_at, is_done) 
            VALUES (?, ?, ?, ?)
            """,
            (
                content,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                remind_at,
                0
            )
        )

        connection.commit()
        connection.close()

    def get_reminders(self):
        connection = self.connect()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT id, content, created_at, remind_at, is_done 
            FROM reminders 
            ORDER BY id DESC
        """)

        reminders = cursor.fetchall()

        connection.close()
        return reminders

    def delete_reminders(self):
        connection = self.connect()
        cursor = connection.cursor()

        cursor.execute("DELETE FROM reminders")

        connection.commit()
        connection.close()

    def get_due_reminders(self):
        connection = self.connect()
        cursor = connection.cursor()

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            SELECT id, content, remind_at 
            FROM reminders
            WHERE remind_at IS NOT NULL
            AND is_done = 0
            AND remind_at <= ?
        """, (now,))

        reminders = cursor.fetchall()

        connection.close()
        return reminders

    def mark_reminder_done(self, reminder_id):
        connection = self.connect()
        cursor = connection.cursor()

        cursor.execute(
            "UPDATE reminders SET is_done = 1 WHERE id = ?",
            (reminder_id,)
        )

        connection.commit()
        connection.close()
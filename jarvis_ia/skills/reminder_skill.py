import re
from datetime import datetime, timedelta
from database.db import Database


class ReminderSkill:
    def __init__(self):
        self.db = Database()

    def run(self, data):
        action = data.get("action", "create")
        reminder = data.get("reminder", "").strip()

        if action == "create":
            if not reminder:
                return "Dime qué quieres que recuerde."

            content, remind_at = self.extract_time(reminder)

            self.db.save_reminder(content, remind_at)

            if remind_at:
                date_text = datetime.strptime(remind_at, "%Y-%m-%d %H:%M:%S").strftime("%H:%M")
                return f"Listo, te recordaré {content} a las {date_text}."

            return "Listo, guardé el recordatorio."

        if action == "show":
            reminders = self.db.get_reminders()

            if not reminders:
                return "No tienes recordatorios guardados todavía."

            response = "Tus recordatorios son: "

            for reminder_id, content, created_at, remind_at, is_done in reminders[:5]:
                if remind_at:
                    hour = datetime.strptime(remind_at, "%Y-%m-%d %H:%M:%S").strftime("%H:%M")
                    status = "completado" if is_done else "pendiente"
                    response += f"Recordatorio {reminder_id}: {content}, a las {hour}, estado {status}. "
                else:
                    response += f"Recordatorio {reminder_id}: {content}. "

            return response

        if action == "delete":
            self.db.delete_reminders()
            return "Listo, borré todos tus recordatorios."

        return "No entendí la acción de recordatorios."

    def extract_time(self, text):
        pattern = r"(?:a las|alas|a la|para las)\s+(\d{1,2})(?::(\d{2}))?"
        match = re.search(pattern, text)

        if not match:
            return text.strip(), None

        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0

        clean_text = re.sub(pattern, "", text).strip()

        now = datetime.now()
        remind_date = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if remind_date <= now:
            remind_date += timedelta(days=1)

        remind_at = remind_date.strftime("%Y-%m-%d %H:%M:%S")

        return clean_text, remind_at
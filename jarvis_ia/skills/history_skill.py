from database.db import Database


class HistorySkill:
    def __init__(self):
        self.db = Database()

    def run(self, data):
        action = data.get("action", "show")

        if action == "show":
            history = self.db.get_history()

            if not history:
                return "Todavía no hay comandos guardados en el historial."

            response = "Estos son tus últimos comandos: "

            for command, response_text, created_at in history:
                response += f"Comando: {command}. Respuesta: {response_text}. "

            return response

        if action == "delete":
            self.db.delete_history()
            return "Listo, borré el historial de comandos."

        return "No entendí la acción del historial."

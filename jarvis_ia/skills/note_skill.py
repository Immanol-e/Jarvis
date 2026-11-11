from database.db import Database

class NoteSkill:
    def __init__(self):
        self.db = Database()

    def run(self, data):
        action = data.get("action", "create")
        note = data.get("note", "").strip()

        if action == "create":
            if not note:
                return "Dime qué quieres guardar en la nota."

            self.db.save_note(note)
            return "Listo, guardé la nota en mi memoria."

        if action == "show":
            notes = self.db.get_notes()

            if not notes:
                return "No tienes notas guardadas todavía."

            response = "Tus últimas notas son: "

            for note_id, content, created_at in notes[:5]:
                response += f"Nota {note_id}: {content}. "

            return response

        return "No entendí la acción de notas."
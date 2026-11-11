"""
assistant.py

Fix #3: TaskPlanner solo se llama si el comando contiene palabras clave
        de creación/edición. Antes corría para TODOS los comandos (incluso
        "qué hora es"), añadiendo latencia de LLM innecesaria.

Fix #6: ConversationContext enriquece el input antes de clasificarlo.
        Resuelve "siguiente capítulo", "lo mismo en youtube", etc.

Fix #7: respond() no lee respuestas largas completas — recorta al TTS
        a la primera oración o MAX_SPEAK_CHARS caracteres.

Habits: Registra cada comando ejecutado para aprender hábitos de uso.
        Al arrancar, sugiere acciones basadas en patrones detectados.

Fix #12 (nuevo): el intent_data ya clasificado se le pasa al AIRouter.
        Antes el router volvía a clasificar el mismo texto desde cero.

Fix #13 (nuevo): se comparte el mismo IntentClassifier con el AIRouter en
        vez de crear dos instancias idénticas.

Fix #14 (nuevo): las respuestas de plática se van diciendo en voz alta
        conforme el modelo las escribe (streaming), no hasta el final.

Fix #15 (nuevo): el modelo de Ollama se precarga en un hilo al arrancar,
        así el primer comando no es el lento.

Fix #16 (nuevo): start_reminder_checker() se movió a __init__. La interfaz
        gráfica nunca llama a start(), así que en modo GUI los recordatorios
        nunca se revisaban.
"""

import re
import threading
import time

from brain.intent_classifier import IntentClassifier
from brain.conversation_context import ConversationContext
from skills.registry import SkillRegistry
from skills.habits_skill import HabitsSkill
from voice.text_to_speech import TextToSpeech
from voice.speech_to_text import SpeechToText
from database.db import Database
from brain.ai_router import AIRouter
from brain.task_planner import TaskPlanner


# Fix #3: palabras que indican que TaskPlanner puede ser útil.
_TASK_PLANNER_TRIGGERS = {
    "crea", "crear", "haz", "hacer", "genera", "generar",
    "nueva", "nuevo", "modifica", "modificar", "agrega", "agregar",
    "interfaz", "gui", "ventana", "formulario", "proyecto",
    "explica", "explícame", "explicame", "que hace", "qué hace",
    "analiza", "revisa", "edita", "editar",
}

# Fix #7: máximo de caracteres que JARVIS lee en voz alta.
MAX_SPEAK_CHARS = 220


def _necesita_task_planner(text: str) -> bool:
    t = text.lower()
    return any(trigger in t for trigger in _TASK_PLANNER_TRIGGERS)


class JarvisAssistant:
    def __init__(self):
        self.intent_classifier       = IntentClassifier()
        self.skill_registry          = SkillRegistry()
        self.voice                   = TextToSpeech()
        self.ears                    = SpeechToText()
        self.db                      = Database()
        self.reminder_thread_started = False
        self.pending_action          = None
        # Fix #13: el router reusa el mismo clasificador
        self.ai_router               = AIRouter(self.intent_classifier)
        self.task_planner            = TaskPlanner()
        self.response_callback       = None
        self.context                 = ConversationContext()
        self.last_failed_cmd         = None
        self.habits                  = HabitsSkill()

        # Fix #15: precargar el modelo en RAM sin bloquear el arranque.
        # Va en __init__ y no en start() porque la interfaz gráfica nunca
        # llama a start().
        threading.Thread(target=self.ai_router.precargar, daemon=True).start()

        # Fix #16: el revisor de recordatorios también se arranca aquí.
        # Antes solo se llamaba desde start(), y jarvis_ui.py nunca lo llama:
        # en modo gráfico los recordatorios simplemente nunca sonaban.
        self.start_reminder_checker()

    def start(self):
        print("JARVIS iniciado.")

        # ── Registrar inicio de sesión y mostrar sugerencia ──────────────────
        self.habits.log_session_start()
        sugerencia = self.habits.sugerencia_contextual()
        if sugerencia:
            print(f"\nJARVIS: {sugerencia}")
            self.voice.speak(sugerencia)

        print("Modo de uso:")
        print("1. Escribe un comando normal")
        print("2. Escribe voz para activar el modo voz continuo")
        print("3. Escribe una vez para hablar solo una vez")
        print("4. Escribe salir para terminar\n")

        while True:
            user_input = input("Tú: ").strip()

            if user_input.lower() in ["voz", "modo voz", "activar voz"]:
                self.voice_mode(); continue

            if user_input.lower() in ["una vez", "hablar"]:
                self.listen_once(); continue

            if user_input.lower() in ["salir", "exit", "cerrar"]:
                self.respond("Hasta luego, señor."); break

            self.process_command(user_input)

    def listen_once(self):
        self.respond("Te escucho.")
        user_input = self.ears.listen()
        if not user_input:
            self.respond("No entendí lo que dijiste."); return
        self.process_command(user_input)

    def voice_mode(self):
        self.respond("Modo voz activado. Di Jarvis antes de cada comando. Di Jarvis salir para terminar.")
        while True:
            user_input = self.ears.listen()
            if not user_input:
                print("No se detectó audio válido."); continue

            user_input = user_input.lower().strip()
            print(f"Texto recibido en modo voz: {user_input}")

            if "jarvis" not in user_input:
                print("No escuché la palabra Jarvis."); continue

            command = user_input.replace("jarvis", "").strip()
            print(f"Comando detectado: {command}")

            if command in ["salir", "cerrar", "terminar", "cancelar modo voz"]:
                self.respond("Modo voz desactivado."); break

            if not command:
                self.respond("Te escucho, dime qué necesitas."); continue

            self.process_command(command)

    def process_command(self, user_input):
        # ── Fix #6: enriquecer con contexto ─────────────────────────────────
        enriquecido = self.context.enrich(user_input)

        if enriquecido.startswith("__CONTEXT_REPLY__"):
            response = enriquecido.replace("__CONTEXT_REPLY__", "")
            self.db.save_command(user_input, response)
            self.respond(response)
            return

        if enriquecido != user_input:
            print(f"[Contexto] '{user_input}' → '{enriquecido}'")

        user_input = enriquecido
        print(f"Procesando comando: {user_input}")

        # ── Clasificar intent (UNA sola vez en todo el flujo) ────────────────
        intent_data = self.intent_classifier.classify(user_input)
        intent      = intent_data.get("intent")
        data        = intent_data.get("data", {})

        # Variables que iremos actualizando para el registro de hábitos
        _log_intent = intent
        _log_data   = data

        # Fix #14: se pone en True si la respuesta ya se dijo en voz alta
        # mientras el modelo la escribía, para no repetirla al final.
        ya_hablo = False

        # ── Fix #3: TaskPlanner solo si tiene sentido ────────────────────────
        if intent not in ["system_request", "confirm_action", "cancel_action"]:
            if _necesita_task_planner(user_input):
                task_plan = self.task_planner.plan(user_input)
                if task_plan:
                    print(f"Plan de tarea detectado: {task_plan}")
                    response = self.execute_steps(task_plan.get("steps", []))
                    self.db.save_command(user_input, response)
                    self.context.update(intent, data, response)
                    self.respond(response)
                    return

        # ── Acciones del sistema con confirmación ────────────────────────────
        if intent == "system_request":
            self.pending_action = {"intent": "system", "data": data}
            action = data.get("action", "")
            msgs = {
                "shutdown": "Esta acción apagará la computadora. Di confirmar para continuar o cancelar.",
                "restart":  "Esta acción reiniciará la computadora. Di confirmar para continuar o cancelar.",
                "lock":     "Esta acción bloqueará la computadora. Di confirmar para continuar o cancelar.",
            }
            response = msgs.get(action, "Esta acción necesita confirmación. Di confirmar o cancelar.")
            self.db.save_command(user_input, response)
            self.respond(response)
            return

        if intent == "confirm_action":
            if not self.pending_action:
                if self.last_failed_cmd:
                    retry_cmd = self.last_failed_cmd
                    self.last_failed_cmd = None
                    self.respond("Reintentando…")
                    self.process_command(retry_cmd)
                    return
                response = "No hay ninguna acción pendiente para confirmar."
            else:
                response = self.skill_registry.execute(self.pending_action)
                self.pending_action = None
            self.db.save_command(user_input, response)
            self.respond(response)
            return

        if intent == "cancel_action":
            if self.pending_action:
                self.pending_action = None
                response = "Acción cancelada."
            else:
                response = "No hay ninguna acción pendiente para cancelar."
            self.db.save_command(user_input, response)
            self.respond(response)
            return

        # ── Intent desconocido → ai_router ───────────────────────────────────
        if intent == "unknown":
            # Fix #14: lector que va diciendo las oraciones conforme llegan.
            # Se crea hasta el primer pedazo de texto: si la respuesta resulta
            # ser un JSON de acción, nunca se crea y no se habla nada.
            lector = {"obj": None}

            def _al_llegar_texto(trozo):
                if lector["obj"] is None:
                    lector["obj"] = self.voice.lector_streaming()
                lector["obj"].feed(trozo)

            # Fix #12: le pasamos el intent_data ya calculado
            ai_result = self.ai_router.route(
                user_input, intent_data, on_chunk=_al_llegar_texto
            )

            if lector["obj"] is not None:
                lector["obj"].close()
                ya_hablo = True

            print(f"Resultado de AI Router: {ai_result}")

            if ai_result.get("type") == "action":
                ai_intent_data = {
                    "intent": ai_result.get("intent"),
                    "data":   ai_result.get("data", {}),
                }
                response = self.skill_registry.execute(ai_intent_data)
                self.context.update(
                    ai_result.get("intent", "unknown"),
                    ai_result.get("data", {}),
                    response
                )
                _log_intent = ai_result.get("intent", "unknown")
                _log_data   = ai_result.get("data", {})

                ai_intent = ai_result.get("intent", "")
                if ai_intent == "tv" and any(
                    w in response.lower() for w in ["no pude", "error", "no encontré", "no localicé"]
                ):
                    self.last_failed_cmd = user_input
                else:
                    self.last_failed_cmd = None

            elif ai_result.get("type") == "steps":
                responses = []
                last_step_intent = "unknown"
                last_step_data   = {}
                for step in ai_result.get("steps", []):
                    s_intent = step.get("intent")
                    s_data   = step.get("data", {})
                    step_response = self.skill_registry.execute({
                        "intent": s_intent,
                        "data":   s_data,
                    })
                    responses.append(step_response)
                    last_step_intent = s_intent or last_step_intent
                    last_step_data   = s_data
                response = " ".join(responses) if responses else "No pude ejecutar esos pasos."
                self.context.update(last_step_intent, last_step_data, response)
                self.last_failed_cmd = None
                _log_intent = last_step_intent
                _log_data   = last_step_data

            else:
                response = ai_result.get("response", "No pude responder eso.")
                self.last_failed_cmd = None

        else:
            # ── Skill normal ─────────────────────────────────────────────────
            response = self.skill_registry.execute(intent_data)
            self.context.update(intent, data, response)
            if intent == "tv" and any(
                w in response.lower() for w in ["no pude", "error", "no encontré", "no localicé"]
            ):
                self.last_failed_cmd = user_input
            else:
                self.last_failed_cmd = None

        # ── Registrar hábito ─────────────────────────────────────────────────
        self.habits.log(_log_intent, user_input, _log_data)

        self.db.save_command(user_input, response)
        self.respond(response, hablar=not ya_hablo)

    def execute_steps(self, steps):
        responses = []
        for step in steps:
            step_response = self.skill_registry.execute({
                "intent": step.get("intent"),
                "data":   step.get("data", {}),
            })
            if step_response:
                responses.append(step_response)
        return " ".join(responses) if responses else "No pude ejecutar esos pasos."

    def set_response_callback(self, callback):
        self.response_callback = callback

    def respond(self, response, hablar=True):
        print(f"JARVIS: {response}")

        if self.response_callback:
            try:
                self.response_callback(response)
            except Exception as error:
                print(f"Error enviando respuesta a la interfaz: {error}")

        # Fix #14: si ya se dijo mientras el modelo la escribía, no repetir
        if not hablar:
            return

        # Fix #7: no leer respuestas largas completas
        if len(response) <= MAX_SPEAK_CHARS:
            self.voice.speak(response)
        else:
            primera = re.split(r"(?<=[.!?])\s", response)[0].strip()
            if len(primera) > MAX_SPEAK_CHARS:
                primera = response[:MAX_SPEAK_CHARS].rsplit(" ", 1)[0] + "…"
            self.voice.speak(primera)

    def start_reminder_checker(self):
        if self.reminder_thread_started: return
        self.reminder_thread_started = True
        thread = threading.Thread(target=self.check_reminders_loop, daemon=True)
        thread.start()

    def check_reminders_loop(self):
        while True:
            try:
                reminders = self.db.get_due_reminders()
                for reminder_id, content, remind_at in reminders:
                    message = f"Recordatorio: {content}"
                    print(f"\nJARVIS: {message}")
                    self.voice.speak(message)
                    self.db.mark_reminder_done(reminder_id)
            except Exception as error:
                print(f"Error revisando recordatorios: {error}")
            time.sleep(20)
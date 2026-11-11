"""
ai_router.py

Fix #1: Se eliminó el bloque TV roto de quick_route (tenía el extractor
        viejo que dejaba "quizás de toser one en" con basura).

Fix #4: quick_route ahora empieza delegando al IntentClassifier.
        Antes existían DOS lugares con lógica de clasificación;
        ahora hay solo uno. Si classify() ya resolvió el intent,
        quick_route lo devuelve directamente sin duplicar código.

Fix #12 (nuevo): route() y quick_route() reciben el intent_data que el
        assistant YA calculó. Antes se volvía a clasificar el mismo texto
        desde cero — una pasada completa de regex desperdiciada en cada
        comando que terminaba en Ollama, o sea justo en los más lentos.

Fix #13 (nuevo): el IntentClassifier se puede compartir desde afuera para
        no tener dos instancias iguales (assistant + router).

Fix #14 (nuevo): ollama_route() trabaja en streaming. El prompt ahora pide
        JSON SOLO cuando es una acción; si es plática normal el modelo
        contesta en texto plano y ese texto se va mandando al TTS conforme
        llega, con el callback on_chunk.
"""

import re
import json

from brain.ollama_client import OllamaClient
from brain.intent_classifier import IntentClassifier


class AIRouter:

    # Marcas de markdown que a veces mete el modelo aunque le digas que no
    _MARCAS = ("```json", "```")

    def __init__(self, intent_classifier=None):
        self.ollama             = OllamaClient()
        # Fix #13: si el assistant ya tiene uno, lo reusamos
        self.intent_classifier  = intent_classifier or IntentClassifier()

    def route(self, user_input, intent_data=None, on_chunk=None):
        text = user_input.lower().strip()

        quick_action = self.quick_route(text, user_input, intent_data)
        if quick_action:
            return quick_action

        return self.ollama_route(user_input, on_chunk=on_chunk)

    def precargar(self):
        """Carga el modelo de Ollama en RAM. Llamar en un hilo al arrancar."""
        return self.ollama.warmup()

    # ── Helpers de extracción ────────────────────────────────────────

    def extract_folder_name(self, text):
        # Fix: clase NEGADA captura nombre real; antes capturaba comillas/espacios
        _Q_OPEN  = chr(8220) + chr(8221) + chr(34) + chr(8216) + chr(8217) + chr(39)
        _Q_PAT   = "[" + _Q_OPEN + "]([^" + _Q_OPEN + "]+)[" + _Q_OPEN + "]"
        quoted = re.search(_Q_PAT, text)
        if quoted:
            name = quoted.group(1).strip()
            if name:
                return self.clean_folder_name(name)

        patterns = [
            r"(?:que\s+se\s+llame|se\s+llame|que\s+diga|diga|llamada|llamado|nombre\s+de|nombre\s+)\s+(.+)",
            r"carpeta\s+(.+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return self.clean_folder_name(match.group(1).strip())
        return "nueva carpeta"

    def clean_folder_name(self, name):
        name = str(name).strip()
        stop_patterns = [
            r"\s+(?:y|e)\s+(?:la\s+|lo\s+)?(?:abre|abrir|abrirla|abrirlo|ábrela|abrela|abres|ábrelo|abrelo).*$",
            r"\s+para\s+(?:abrir|abrirla|abrirlo|usarla|editarla).*$",
            r"\s+(?:en|con)\s+(?:visual\s+studio\s+code|visual|vscode|vs\s*code|code).*$",
            r"\s+(?:en|dentro\s+de)\s+(?:mis\s+)?(?:documentos|documents|escritorio|desktop|descargas|downloads).*$",
        ]
        for pattern in stop_patterns:
            name = re.sub(pattern, "", name, flags=re.IGNORECASE).strip()
        name = re.sub(
            r"^(?:en|dentro\s+de)\s+(?:mis\s+)?(?:documentos|documents|escritorio|desktop|descargas|downloads)\s+",
            "", name, flags=re.IGNORECASE,
        ).strip()
        name = re.sub(
            r"^(?:que\s+se\s+llame|se\s+llame|que\s+diga|diga|llamada|llamado)\s+",
            "", name, flags=re.IGNORECASE,
        ).strip()
        name = name.strip(' ."\'"')
        name = re.sub(r'[<>:"/\\|?*]', "", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name[:80]

    def extract_folder_location(self, text):
        if "documentos" in text or "mis documentos" in text: return "documents"
        if "escritorio" in text:  return "desktop"
        if "descargas" in text:   return "downloads"
        if "carpeta actual" in text or "proyecto" in text: return "actual"
        return "documents"

    def extract_folder_open_with(self, text):
        if any(w in text for w in ["visual studio code","vscode","visual","vs code"]): return "vscode"
        if any(w in text for w in ["abre","abrir","ábre","abres"]): return "explorer"
        return "none"

    # ── quick_route ──────────────────────────────────────────────────

    def quick_route(self, text, original=None, intent_data=None):
        original = original or text

        # ── Fix #4 + #12: usar la clasificación que ya venía hecha ───
        # Si el assistant ya llamó a classify(), reusamos ese resultado.
        # Solo clasificamos aquí si alguien llama a route() por su cuenta.
        result = intent_data if intent_data is not None \
            else self.intent_classifier.classify(text)

        if result.get("intent") != "unknown":
            return {
                "type":   "action",
                "intent": result["intent"],
                "data":   result.get("data", {}),
            }

        # ── A partir de aquí solo casos que classify() NO maneja ─────

        # Detectar archivos de código mencionados
        file_pattern = r"(?<![\w.-])([A-Za-z0-9_\-]+\.(?:py|java|html|css|js|txt|md|json|ino))(?![\w.-])"
        file_match   = re.search(file_pattern, text, flags=re.IGNORECASE)

        if file_match and any(w in text for w in ["explica","explícame","explicame","que hace","qué hace","revisa","analiza"]):
            return {
                "type":   "action",
                "intent": "explain_file",
                "data":   {"file_name": file_match.group(1)},
            }

        if file_match and any(w in text for w in ["modifica","cambia","actualiza","agrega","añade","edita"]):
            return {
                "type":   "action",
                "intent": "edit_file",
                "data":   {"file_name": file_match.group(1), "instruction": original},
            }

        # Crear carpeta
        if any(w in text for w in ["crea","crear","haz","hacer","nueva","nuevo"]):
            if "carpeta" in text:
                return {
                    "type":   "action",
                    "intent": "create_folder",
                    "data": {
                        "folder_name": self.extract_folder_name(text),
                        "location":    self.extract_folder_location(text),
                        "open_with":   self.extract_folder_open_with(text),
                    },
                }

        # Abrir VS Code directamente
        if any(w in text for w in ["visual studio code","vscode","vs code"]):
            return {
                "type":   "action",
                "intent": "open_app",
                "data":   {"app_name": "visual studio code"},
            }

        return None

    # ── Helpers de streaming ─────────────────────────────────────────

    @staticmethod
    def _limpiar(texto):
        """Quita las marcas ```json / ``` del principio y del final."""
        t = texto.strip()
        t = re.sub(r"^`{3,}(?:json)?\s*", "", t)
        t = re.sub(r"\s*`{3,}$", "", t)
        return t.strip()

    @staticmethod
    def _cabeza(buffer):
        """
        Devuelve el texto útil recibido hasta ahora, o None si todavía no
        alcanza para decidir si viene JSON o texto plano.

        Si el modelo empezó con una marca de markdown esperamos al salto de
        línea que la cierra. Si no, un ```json partido en trozos ("``",
        "`js", "on") se leería como si fuera texto normal.
        """
        t = buffer.lstrip()
        if t.startswith("`"):
            salto = t.find("\n")
            if salto == -1:
                return None
            t = t[salto + 1:].lstrip()
        return t or None

    # ── ollama_route ─────────────────────────────────────────────────

    _PROMPT = """Eres el cerebro de JARVIS, un asistente virtual en español.

Si el mensaje del usuario es una ACCIÓN, responde SOLO con el JSON que
corresponda. Sin markdown, sin explicaciones, sin texto antes o después.

Si el mensaje NO es una acción (plática, pregunta general, duda), contesta
normal en texto plano, máximo dos frases. En ese caso NO uses JSON.

Formato para abrir aplicación:
{
    "type": "action",
    "intent": "open_app",
    "data": {
        "app_name": "nombre"
    }
}

Formato para buscar en Google:
{
    "type": "action",
    "intent": "web",
    "data": {
        "action": "search_google",
        "query": "texto"
    }
}

Formato para reproducir en YouTube:
{
  "type": "action",
  "intent": "web",
  "data": {
    "action": "play_youtube",
    "query": "video o música"
  }
}

Formato para explicar un archivo de código:
{
  "type": "action",
  "intent": "file_editor",
  "data": {
    "action": "explain_file",
    "file_name": "main.py"
  }
}

Formato para modificar un archivo o proyecto existente:
{
  "type": "action",
  "intent": "file_editor",
  "data": {
    "action": "edit_file",
    "file_name": "main.py",
    "instruction": "instrucción completa"
  }
}

Mensaje del usuario: """

    def ollama_route(self, user_input, on_chunk=None):
        """
        Lee la respuesta de Ollama en streaming.

        En cuanto llega el primer carácter útil decidimos:
          - empieza con '{'  → es una acción: juntamos todo y parseamos JSON.
          - cualquier otra   → es plática: cada pedazo se manda a on_chunk
                               para que JARVIS lo vaya diciendo en voz alta.
        """
        prompt = self._PROMPT + user_input

        buffer = ""
        modo   = None   # None = todavía no sabemos, "json" o "texto"

        try:
            for trozo in self.ollama.ask_stream(prompt):
                buffer += trozo

                if modo is None:
                    cabeza = self._cabeza(buffer)
                    if cabeza is None:
                        continue
                    modo = "json" if cabeza.startswith("{") else "texto"
                    if modo == "texto" and on_chunk:
                        on_chunk(cabeza)      # lo acumulado hasta este punto
                    continue

                if modo == "texto" and on_chunk:
                    on_chunk(trozo)

        except Exception as e:
            return {"type": "response", "response": f"Error al consultar Ollama: {e}"}

        limpio = self._limpiar(buffer)

        # Red de seguridad: respuesta cortita que nunca cerró la marca de
        # markdown, o que se acabó antes de que pudiéramos decidir.
        if modo is None:
            if limpio.startswith("{"):
                modo = "json"
            else:
                modo = "texto"
                if on_chunk and limpio:
                    on_chunk(limpio)

        if modo == "texto":
            return {
                "type":     "response",
                "response":  limpio or "No pude responder eso.",
                "hablado":   bool(on_chunk),   # ya se dijo mientras llegaba
            }

        try:
            return json.loads(limpio)
        except json.JSONDecodeError:
            return {"type": "response", "response": limpio or "No pude procesar eso."}
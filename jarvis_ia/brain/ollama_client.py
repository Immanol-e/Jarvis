"""
ollama_client.py

Cambios de esta versión:
  - keep_alive: el modelo se queda cargado en RAM 30 minutos. Sin esto Ollama
    lo descarga solo a los 5 minutos y el siguiente comando tarda 20-30 s
    en vez de 2 s.
  - ask_stream(): generador que va soltando el texto conforme el modelo lo
    escribe. Sirve para empezar a hablar antes de que termine de generar.
  - warmup(): carga el modelo al arrancar JARVIS para que el primer comando
    no sea el lento.

ask() se quedó igual que antes para no romper rag_skill.py.
"""

import json
import requests


class OllamaClient:
    def __init__(self, model="llama3.2", keep_alive="30m"):
        self.model      = model
        self.keep_alive = keep_alive
        self.url        = "http://localhost:11434/api/generate"

    # ── Payload compartido ───────────────────────────────────────────────
    def _payload(self, prompt, stream):
        return {
            "model":      self.model,
            "prompt":     prompt,
            "stream":     stream,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0.1,
                "top_p":       0.8,
                "num_predict": 180
            }
        }

    # ── Modo normal (bloqueante) ─────────────────────────────────────────
    def ask(self, prompt):
        try:
            response = requests.post(
                self.url, json=self._payload(prompt, False), timeout=120
            )
            response.raise_for_status()

            result = response.json()
            return result.get("response", "No pude generar una respuesta.")

        except requests.exceptions.ConnectionError:
            return "No pude conectarme con Ollama. Asegúrate de que Ollama esté abierto."

        except requests.exceptions.Timeout:
            return "Ollama tardó demasiado en responder."

        except Exception as error:
            return f"Ocurrió un error con Ollama: {error}"

    # ── Modo streaming ───────────────────────────────────────────────────
    def ask_stream(self, prompt):
        """
        Generador. Va devolviendo los pedacitos de texto conforme llegan.
        Si algo falla suelta el mensaje de error como un solo pedazo,
        igual que ask().
        """
        try:
            with requests.post(self.url,
                               json=self._payload(prompt, True),
                               stream=True,
                               timeout=120) as response:
                response.raise_for_status()

                for linea in response.iter_lines(decode_unicode=True):
                    if not linea:
                        continue
                    try:
                        dato = json.loads(linea)
                    except json.JSONDecodeError:
                        continue

                    trozo = dato.get("response", "")
                    if trozo:
                        yield trozo
                    if dato.get("done"):
                        break

        except requests.exceptions.ConnectionError:
            yield "No pude conectarme con Ollama. Asegúrate de que Ollama esté abierto."

        except requests.exceptions.Timeout:
            yield "Ollama tardó demasiado en responder."

        except Exception as error:
            yield f"Ocurrió un error con Ollama: {error}"

    # ── Precarga ─────────────────────────────────────────────────────────
    def warmup(self):
        """
        Carga el modelo en RAM sin generar texto (prompt vacío).
        Se llama en un hilo aparte al arrancar JARVIS.
        """
        try:
            requests.post(
                self.url,
                json={
                    "model":      self.model,
                    "prompt":     "",
                    "keep_alive": self.keep_alive,
                },
                timeout=180,
            )
            return True
        except Exception:
            return False
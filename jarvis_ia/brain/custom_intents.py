"""
custom_intents.py — Intents personalizados de JARVIS
======================================================
Permite enseñarle hechos y respuestas fijas sin tocar código ni modelos.
Todo se guarda en custom_intents.json automáticamente.

Comandos de voz:
  "enséñate que cuando diga mi contraseña wifi respondas MiCasa2024"
  "enséñate que cuando diga fecha de examen respondas El 15 de julio"
  "qué intents tienes guardados"
  "olvida el intent cumpleaños"

Formato de custom_intents.json:
{
  "intents": [
    {
      "etiqueta":  "wifi",
      "patrones":  ["contraseña wifi", "clave wifi", "password wifi"],
      "respuesta": "La contraseña del WiFi de casa es MiCasa2024."
    }
  ]
}
"""

import json
from pathlib import Path


class CustomIntents:

    def __init__(self, intents_file: str = None):
        base        = Path(__file__).parent.parent
        self.path   = Path(intents_file or base / "custom_intents.json")
        self.intents: list = []
        self._cargar()

    # ── Persistencia ─────────────────────────────────────────────────────

    def _cargar(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.intents = data.get("intents", [])
            except Exception:
                self.intents = []

    def _guardar(self):
        data = {"intents": self.intents}
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    # ── Matching (se llama desde intent_classifier) ──────────────────────

    def match(self, text: str) -> str | None:
        """
        Busca si el texto coincide con algún intent personalizado.
        Devuelve la respuesta si hay match, None si no hay.
        """
        text_l = text.lower().strip()
        for intent in self.intents:
            for patron in intent.get("patrones", []):
                if patron.lower() in text_l:
                    return intent.get("respuesta", "")
        return None

    # ── Administración ───────────────────────────────────────────────────

    def agregar(self, patrones: list, respuesta: str, etiqueta: str = "") -> str:
        self._cargar()   # refrescar antes de guardar para no perder cambios
        etiq = etiqueta or patrones[0][:30].strip()

        # Actualizar si ya existe la etiqueta
        for intent in self.intents:
            if intent.get("etiqueta", "").lower() == etiq.lower():
                intent["patrones"]  = patrones
                intent["respuesta"] = respuesta
                self._guardar()
                return f"✓ Intent '{etiq}' actualizado."

        self.intents.append({
            "etiqueta":  etiq,
            "patrones":  patrones,
            "respuesta": respuesta,
        })
        self._guardar()
        preview = respuesta[:60] + "…" if len(respuesta) > 60 else respuesta
        return f"✓ Aprendido: '{patrones[0]}' → '{preview}'"

    def eliminar(self, etiqueta: str) -> str:
        antes = len(self.intents)
        self.intents = [
            i for i in self.intents
            if i.get("etiqueta", "").lower() != etiqueta.lower()
        ]
        self._guardar()
        return (
            f"Intent '{etiqueta}' olvidado."
            if len(self.intents) < antes else
            f"No encontré un intent llamado '{etiqueta}'."
        )

    def listar(self) -> str:
        self._cargar()
        if not self.intents:
            return (
                "No tengo intents personalizados todavía.\n"
                "Puedes enseñarme con:\n"
                "  \"enséñate que cuando diga <frase> respondas <respuesta>\""
            )
        lineas = [
            f"  📌 [{i.get('etiqueta','?')}] "
            f"\"{i['patrones'][0]}\" → {i['respuesta'][:50]}"
            + ("…" if len(i['respuesta']) > 50 else "")
            for i in self.intents
        ]
        return f"Intents personalizados ({len(self.intents)}):\n" + "\n".join(lineas)

    # ── Entry point ──────────────────────────────────────────────────────

    def run(self, data: dict) -> str:
        action    = data.get("action", "listar_intents")
        patrones  = data.get("patrones", [])
        respuesta = data.get("respuesta", "")
        etiqueta  = data.get("etiqueta", "")

        if action == "_direct":         return data.get("response", "")
        if action == "agregar_intent":  return self.agregar(patrones, respuesta, etiqueta)
        if action == "eliminar_intent": return self.eliminar(etiqueta)
        if action == "listar_intents":  return self.listar()
        return "Acción de custom intents no reconocida."
"""
finetune_helper.py — Gestor de Fine-Tuning para JARVIS
========================================================
Guarda pares (pregunta, respuesta correcta) para mejorar el modelo base.

Flujo completo de entrenamiento:
  1. JARVIS responde algo bien → di "guarda este ejemplo"
  2. Los ejemplos se acumulan en finetune_dataset.jsonl
  3. Di "genera modelfile" para crear el archivo de configuración
  4. Ejecuta en tu terminal:
       ollama create mi-jarvis -f Modelfile
  5. Cambia model="mi-jarvis" en ollama_client.py y JARVIS usará tu modelo

Para fine-tuning completo con el dataset:
  Usa LLaMA-Factory (gratis, sin GPU mínimo con 4-bit):
    https://github.com/hiyouga/LLaMA-Factory
"""

import json
from pathlib import Path
from datetime import datetime


class FinetuneHelper:

    SYSTEM_PROMPT = (
        "Eres JARVIS, un asistente personal inteligente que habla español de México. "
        "Controlas dispositivos Android vía ADB, televisores Smart TV, "
        "y tienes acceso a una base de conocimiento personal. "
        "Eres conciso, directo y útil."
    )

    def __init__(self, dataset_path: str = None):
        base           = Path(__file__).parent.parent
        self.path      = Path(dataset_path or base / "finetune_dataset.jsonl")
        self.modelfile = base / "Modelfile"

    # ── Dataset ──────────────────────────────────────────────────────────

    def guardar_ejemplo(self, pregunta: str, respuesta: str) -> str:
        """Guarda un ejemplo de conversación ideal en el dataset."""
        if not pregunta or not respuesta:
            return "Necesito la pregunta y la respuesta para guardar el ejemplo."

        ejemplo = {
            "messages": [
                {"role": "system",    "content": self.SYSTEM_PROMPT},
                {"role": "user",      "content": pregunta},
                {"role": "assistant", "content": respuesta},
            ],
            "_meta": {
                "fecha":    datetime.now().strftime("%Y-%m-%d %H:%M"),
                "version":  "1.0",
            }
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ejemplo, ensure_ascii=False) + "\n")

        total = self.total()
        return (
            f"✓ Ejemplo guardado. Dataset: {total} ejemplo(s).\n"
            f"Di 'genera modelfile' cuando tengas suficientes (recomendado: +50)."
        )

    def total(self) -> int:
        if not self.path.exists():
            return 0
        return sum(1 for _ in open(self.path, encoding="utf-8"))

    def stats(self) -> str:
        total = self.total()
        if total == 0:
            return (
                "No hay ejemplos todavía.\n"
                "Después de una buena respuesta di: 'guarda este ejemplo'"
            )
        nivel = (
            "🟢 Listo para entrenar básico"     if total >= 50  else
            "🟡 Acumulando (recomendado: 50+)"  if total >= 20  else
            "🔴 Muy pocos (sigue acumulando)"
        )
        return (
            f"Dataset de fine-tuning:\n"
            f"  • {total} ejemplos guardados\n"
            f"  • {nivel}\n"
            f"  • Archivo: {self.path.name}"
        )

    # ── Modelfile para Ollama ─────────────────────────────────────────────

    def generar_modelfile(self, modelo_base: str = "llama3.2") -> str:
        """
        Genera el Modelfile para personalizar JARVIS en Ollama.
        Esto ajusta el system prompt y los parámetros sin necesitar GPU.
        """
        contenido = f"""FROM {modelo_base}

SYSTEM \"\"\"{self.SYSTEM_PROMPT}\"\"\"

# Temperatura baja = respuestas más precisas y consistentes
PARAMETER temperature 0.4
PARAMETER top_k 40
PARAMETER top_p 0.9
PARAMETER num_predict 350
PARAMETER repeat_penalty 1.1

# Contexto largo para recordar conversaciones
PARAMETER num_ctx 4096
"""
        self.modelfile.write_text(contenido, encoding="utf-8")

        total  = self.total()
        pasos  = [
            f"1. ollama create mi-jarvis -f {self.modelfile}",
            f"2. (Opcional con {total} ejemplos) Usar LLaMA-Factory para fine-tuning real:",
            f"   https://github.com/hiyouga/LLaMA-Factory",
            f"3. Cambiar model='mi-jarvis' en brain/ollama_client.py",
        ]
        return (
            f"✓ Modelfile generado en: {self.modelfile}\n\n"
            f"Pasos para entrenar:\n" +
            "\n".join(f"  {p}" for p in pasos)
        )

    # ── Entry point ──────────────────────────────────────────────────────

    def run(self, data: dict) -> str:
        action    = data.get("action", "stats_finetune")
        pregunta  = data.get("pregunta", "")
        respuesta = data.get("respuesta", "")
        modelo    = data.get("modelo", "llama3.2")

        if action == "guardar_ejemplo":  return self.guardar_ejemplo(pregunta, respuesta)
        if action == "modelfile":        return self.generar_modelfile(modelo)
        if action == "stats_finetune":   return self.stats()
        return "Acción de fine-tuning no reconocida."
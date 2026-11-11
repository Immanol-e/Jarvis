"""
rag_skill.py — Skill RAG de JARVIS
=====================================
Combina búsqueda semántica en knowledge/ con Ollama para dar respuestas
enriquecidas con contexto personal.

Comandos de voz:
  "qué sabes sobre mis horarios"
  "busca en tus notas quién es el profe de bases de datos"
  "agrega a tu memoria: recetas — Caldo de pollo: ..."
  "reconstruye tu memoria"
  "lista tus documentos"
"""

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from brain.knowledge_base import KnowledgeBase
from brain.ollama_client import OllamaClient


_PROMPT = """\
Eres JARVIS, un asistente personal en español de México.
Responde la pregunta usando SOLO el contexto que se te da.
Si el contexto no tiene la respuesta, di claramente que no lo sabes.
Sé conciso y directo.

=== CONTEXTO ===
{contexto}
=== FIN CONTEXTO ===

Pregunta: {pregunta}
Respuesta:"""


class RAGSkill:

    def __init__(self, knowledge_dir: str = None):
        base = knowledge_dir or os.path.join(
            os.path.dirname(__file__), "..", "knowledge"
        )
        self.kb     = KnowledgeBase(base)
        self.ollama = OllamaClient()

    # ── Búsqueda + generación ────────────────────────────────────────────

    def buscar(self, query: str) -> str:
        # Si el índice está vacío, intentar construirlo
        if not self.kb.listo:
            msg = self.kb.rebuild()
            if not self.kb.listo:
                return (
                    "Mi base de conocimiento está vacía. "
                    "Agrega archivos .txt o .md en la carpeta knowledge/ "
                    "y di 'reconstruye tu memoria'.\n\n" + msg
                )

        resultados = self.kb.search(query, top_k=3)

        if not resultados:
            return (
                f"No encontré información sobre '{query}' en mis documentos.\n"
                f"Estado: {self.kb.stats}\n"
                f"Puedes enseñarme con: "
                f"\"agrega a tu memoria: <nombre> — <contenido>\""
            )

        # Construir contexto con fuentes y relevancia
        partes = []
        for r in resultados:
            partes.append(
                f"[📄 {r['source']} | {r['score']:.0%} relevancia]\n{r['text']}"
            )
        contexto = "\n\n---\n".join(partes)

        prompt    = _PROMPT.format(contexto=contexto, pregunta=query)
        respuesta = self.ollama.ask(prompt)

        fuentes = list(dict.fromkeys(r["source"] for r in resultados))
        return f"{respuesta}\n\n📄 Fuentes: {', '.join(fuentes)}"

    # ── Administración ───────────────────────────────────────────────────

    def agregar(self, nombre: str, contenido: str) -> str:
        if not nombre or not contenido:
            return "Necesito un nombre y el contenido. Ej: 'agrega a tu memoria: recetas — Caldo: agua, pollo...'"
        return self.kb.agregar_documento(nombre, contenido)

    def reconstruir(self) -> str:
        return self.kb.rebuild()

    def listar(self) -> str:
        return self.kb.listar()

    # ── Entry point ──────────────────────────────────────────────────────

    def run(self, data: dict) -> str:
        action    = data.get("action", "buscar")
        query     = data.get("query", "")
        nombre    = data.get("nombre", "")
        contenido = data.get("contenido", "")

        if action == "buscar_rag":    return self.buscar(query)
        if action == "agregar_rag":   return self.agregar(nombre, contenido)
        if action == "rebuild_rag":   return self.reconstruir()
        if action == "listar_rag":    return self.listar()
        return "Acción RAG no reconocida."
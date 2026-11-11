"""
knowledge_base.py — Motor RAG de JARVIS
========================================
Indexa documentos de la carpeta knowledge/ usando sentence-transformers
y permite búsqueda semántica en español para enriquecer respuestas de Ollama.

Modelo: paraphrase-multilingual-MiniLM-L12-v2
  ✓ 135 MB  ✓ Español nativo  ✓ Sin GPU  ✓ <1 s por búsqueda

Instalación única:
    pip install sentence-transformers

Uso:
    kb = KnowledgeBase("knowledge/")
    kb.rebuild()
    resultados = kb.search("¿cuál es mi horario del lunes?")
"""

import json
import numpy as np
from pathlib import Path
from datetime import datetime


class KnowledgeBase:

    MODELO          = "paraphrase-multilingual-MiniLM-L12-v2"
    CHUNK_PALABRAS  = 100    # palabras por fragmento (era 250, muy grande para notas personales)
    OVERLAP         = 15     # solapamiento (era 40)
    MIN_SIMILITUD   = 0.25   # umbral mínimo (era 0.38, demasiado estricto para 1 chunk)
    EXTENSIONES     = {".txt", ".md", ".rst"}

    def __init__(self, knowledge_dir: str):
        self.dir         = Path(knowledge_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

        self._idx_json   = self.dir / ".idx_chunks.json"
        self._idx_npy    = self.dir / ".idx_embeddings.npy"

        self._model      = None        # lazy-load al primer uso
        self._chunks     = []          # [{"text":..., "source":..., "fecha":...}]
        self._embeddings = None        # np.ndarray (N, D)

        self._cargar_indice()

    # ── Modelo embedding (carga solo cuando se necesita) ─────────────────

    def _modelo(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.MODELO)
            except ImportError:
                raise ImportError(
                    "Falta sentence-transformers.\n"
                    "Instálalo con:  pip install sentence-transformers"
                )
        return self._model

    # ── Índice en disco ──────────────────────────────────────────────────

    def _cargar_indice(self):
        if self._idx_json.exists() and self._idx_npy.exists():
            with open(self._idx_json, encoding="utf-8") as f:
                self._chunks = json.load(f)
            self._embeddings = np.load(str(self._idx_npy))

    def _guardar_indice(self):
        with open(self._idx_json, "w", encoding="utf-8") as f:
            json.dump(self._chunks, f, ensure_ascii=False, indent=0)
        np.save(str(self._idx_npy), self._embeddings)

    # ── Chunking ─────────────────────────────────────────────────────────

    def _fragmentar(self, texto: str, fuente: str) -> list:
        palabras = texto.split()
        paso     = max(1, self.CHUNK_PALABRAS - self.OVERLAP)
        chunks   = []
        for i in range(0, len(palabras), paso):
            frag = " ".join(palabras[i : i + self.CHUNK_PALABRAS]).strip()
            if len(frag) < 30:
                continue
            chunks.append({
                "text":   frag,
                "source": fuente,
                "fecha":  datetime.now().strftime("%Y-%m-%d"),
            })
        return chunks

    # ── Reconstruir índice completo ──────────────────────────────────────

    def rebuild(self) -> str:
        """
        Lee todos los archivos de knowledge/ y reconstruye el índice.
        Llama esto después de agregar o editar documentos.
        """
        self._chunks = []
        archivos = sorted(
            p for p in self.dir.rglob("*")
            if p.suffix in self.EXTENSIONES and not p.name.startswith(".")
        )

        if not archivos:
            return (
                "La carpeta knowledge/ está vacía.\n"
                "Agrega archivos .txt o .md con tus notas personales."
            )

        for archivo in archivos:
            try:
                texto  = archivo.read_text(encoding="utf-8", errors="ignore")
                nombre = str(archivo.relative_to(self.dir))
                self._chunks.extend(self._fragmentar(texto, nombre))
            except Exception:
                pass

        if not self._chunks:
            return "Los archivos existen pero no se pudo extraer texto."

        textos = [c["text"] for c in self._chunks]
        modelo = self._modelo()
        self._embeddings = modelo.encode(textos, show_progress_bar=False, batch_size=32)
        self._guardar_indice()

        return (
            f"✓ Base de conocimiento lista: {len(archivos)} archivo(s), "
            f"{len(self._chunks)} fragmentos indexados."
        )

    # ── Búsqueda semántica ───────────────────────────────────────────────

    def search(self, query: str, top_k: int = 3) -> list:
        """
        Devuelve los fragmentos más relevantes para la query.
        Lista de dicts: {"text", "source", "score"}
        """
        if not self._chunks or self._embeddings is None:
            return []

        modelo = self._modelo()
        q_emb  = modelo.encode([query])                         # (1, D)

        # Similaridad coseno vectorizada
        normas_db = np.linalg.norm(self._embeddings, axis=1, keepdims=True) + 1e-9
        norma_q   = np.linalg.norm(q_emb) + 1e-9
        sims      = (self._embeddings / normas_db) @ (q_emb / norma_q).T
        sims      = sims.flatten()

        indices = np.argsort(sims)[::-1][:top_k]
        return [
            {
                "text":   self._chunks[i]["text"],
                "source": self._chunks[i]["source"],
                "score":  float(sims[i]),
            }
            for i in indices
            if sims[i] >= self.MIN_SIMILITUD
        ]

    # ── Agregar / listar documentos ──────────────────────────────────────

    def agregar_documento(self, nombre: str, contenido: str) -> str:
        """Guarda un nuevo archivo en knowledge/ y reconstruye el índice."""
        if not any(nombre.endswith(e) for e in self.EXTENSIONES):
            nombre += ".txt"
        ruta = self.dir / nombre
        ruta.write_text(contenido.strip(), encoding="utf-8")
        return self.rebuild()

    def listar(self) -> str:
        archivos = sorted(
            str(p.relative_to(self.dir))
            for p in self.dir.rglob("*")
            if p.suffix in self.EXTENSIONES and not p.name.startswith(".")
        )
        if not archivos:
            return "No hay documentos en la base de conocimiento todavía."
        lineas = "\n".join(f"  📄 {a}" for a in archivos)
        return f"Documentos en mi memoria ({len(archivos)}):\n{lineas}"

    # ── Estado ───────────────────────────────────────────────────────────

    @property
    def listo(self) -> bool:
        return bool(self._chunks) and self._embeddings is not None

    @property
    def stats(self) -> str:
        return (
            f"{len(self._chunks)} fragmentos de "
            f"{len(set(c['source'] for c in self._chunks))} archivo(s)"
            if self._chunks else "Índice vacío"
        )
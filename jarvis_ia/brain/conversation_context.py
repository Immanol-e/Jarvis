"""
Fix #6 — Contexto conversacional entre comandos.

Resuelve referencias implícitas como:
  "siguiente capítulo"   → "reproduce one piece capítulo 26 en crunchyroll en la tv"
  "lo mismo en youtube"  → "reproduce one piece en youtube en la tv"
  "pausa eso"            → "pausa la tv"
  "repítelo"             → "reproduce one piece en crunchyroll en la tv"
"""

import re


class ConversationContext:
    def __init__(self):
        self.last_tv_platform  = None   # "crunchyroll", "youtube", etc.
        self.last_tv_content   = None   # "one piece"
        self.last_tv_capitulo  = None   # "25"  (string)
        self.last_intent       = None   # "tv", "web", "media"…
        self.last_action       = None   # "buscar", "abrir_app"…
        self.history           = []     # últimos 5 comandos + respuestas

    # ── Actualizar después de ejecutar ──────────────────────────────

    def update(self, intent, data, response):
        self.last_intent = intent
        self.last_action = data.get("action", "")

        if intent == "tv":
            action = data.get("action", "")
            if action in ("buscar", "reproducir", "youtube", "crunchyroll"):
                plat = data.get("plataforma") or (action if action not in ("buscar", "reproducir") else None)
                if plat:
                    self.last_tv_platform = plat
                if data.get("query"):
                    self.last_tv_content = data["query"]
                self.last_tv_capitulo = data.get("capitulo")
            elif action == "abrir_app":
                app = data.get("app", "")
                if app:
                    self.last_tv_platform = app

        self.history.append({"intent": intent, "data": data, "response": response})
        if len(self.history) > 5:
            self.history.pop(0)

    # ── Enriquecer el comando entrante ───────────────────────────────

    def enrich(self, text):
        """
        Devuelve el comando enriquecido con contexto si detecta una referencia
        implícita. Si no hace falta, devuelve el texto original sin cambios.
        """
        t = text.lower().strip()

        # "siguiente capítulo" / "siguiente episodio"
        if re.match(
            r"^(?:siguiente|próximo|proximo|next)\s*"
            r"(?:cap[ií]tulo|capitulo|episodio|ep\.?|capítulo)?$", t
        ):
            if self.last_tv_content and self.last_tv_platform:
                if self.last_tv_capitulo:
                    try:
                        siguiente = int(self.last_tv_capitulo) + 1
                    except ValueError:
                        siguiente = "siguiente"
                else:
                    siguiente = "siguiente"
                return (
                    f"reproduce {self.last_tv_content} capítulo {siguiente} "
                    f"en {self.last_tv_platform} en la tv"
                )

        # "capítulo anterior" / "episodio anterior"
        if re.match(
            r"^(?:anterior|prev|atrás|atras)\s*"
            r"(?:cap[ií]tulo|capitulo|episodio|ep\.?)?$", t
        ):
            if self.last_tv_content and self.last_tv_platform and self.last_tv_capitulo:
                try:
                    anterior = max(1, int(self.last_tv_capitulo) - 1)
                except ValueError:
                    anterior = "anterior"
                return (
                    f"reproduce {self.last_tv_content} capítulo {anterior} "
                    f"en {self.last_tv_platform} en la tv"
                )

        # "lo mismo en youtube" / "lo mismo pero en netflix"
        if "lo mismo" in t and self.last_tv_content:
            plat_m = re.search(r"\ben\s+(\w[\w\s]*?)(?:\s+en\s+la\s+tv)?$", t)
            nueva_plat = plat_m.group(1).strip() if plat_m else self.last_tv_platform
            if nueva_plat:
                return f"reproduce {self.last_tv_content} en {nueva_plat} en la tv"

        # "pausa eso" / "pausa esto" → pausa la TV si el último intent fue TV
        if re.match(r"^(?:pausa|pausar|detén|detener)\s+(?:eso|esto|la|lo)?$", t):
            if self.last_intent == "tv":
                return "pausa la tv"

        # "repítelo" / "de nuevo" / "otra vez"
        if t in ("repítelo", "repitelo", "otra vez", "de nuevo", "ponlo de nuevo"):
            if self.last_tv_content and self.last_tv_platform:
                q = self.last_tv_content
                cap_suffix = f" capítulo {self.last_tv_capitulo}" if self.last_tv_capitulo else ""
                return f"reproduce {q}{cap_suffix} en {self.last_tv_platform} en la tv"

        # "qué estoy viendo" / "qué está reproduciendo"
        if re.match(r"^(?:qué|que)\s+(?:estoy\s+viendo|está\s+reproduciendo|puse)", t):
            if self.last_tv_content and self.last_tv_platform:
                cap = f", capítulo {self.last_tv_capitulo}" if self.last_tv_capitulo else ""
                return f"__CONTEXT_REPLY__Estás viendo '{self.last_tv_content}'{cap} en {self.last_tv_platform}."

        return text  # sin cambios

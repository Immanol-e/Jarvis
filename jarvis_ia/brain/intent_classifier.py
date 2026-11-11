from config.tv_config import TV_PLATAFORMAS as _TV_PLATAFORMAS_CFG, TV_PALABRAS as _TV_PALABRAS_CFG
import re

class IntentClassifier:

    def extract_folder_name(self, text):
        # 1) Si el usuario puso el nombre entre comillas, usamos eso primero.
        quoted = re.search(r'["“”\']([^"“”\']+)["“”\']', text)
        if quoted:
            name = quoted.group(1).strip()
            if name:
                return self.clean_folder_name(name)

        patterns = [
            r"(?:que\s+se\s+llame|se\s+llame|que\s+diga|diga|llamada|llamado|nombre\s+de|nombre\s+)\s+(.+)",
            r"carpeta\s+(.+)"
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                name = match.group(1).strip()
                name = self.clean_folder_name(name)
                if name:
                    return name

        return "nueva carpeta"

    def clean_folder_name(self, name):
        name = str(name).strip()

        # Quita partes que son instrucciones, no nombre de carpeta.
        stop_patterns = [
            r"\s+(?:y|e)\s+(?:la\s+|lo\s+)?(?:abre|abrir|abrirla|abrirlo|ábrela|abrela|abres|ábrelo|abrelo).*$",
            r"\s+para\s+(?:abrir|abrirla|abrirlo|usarla|editarla).*$",
            r"\s+(?:en|con)\s+(?:visual\s+studio\s+code|visual|vscode|vs\s*code|code).*$",
            r"\s+(?:en|dentro\s+de)\s+(?:mis\s+)?(?:documentos|documents|escritorio|desktop|descargas|downloads).*$"
        ]

        for pattern in stop_patterns:
            name = re.sub(pattern, "", name, flags=re.IGNORECASE).strip()

        # Si el texto venía como: "en documentos hola", quitamos solo la ubicación del inicio.
        name = re.sub(r"^(?:en|dentro\s+de)\s+(?:mis\s+)?(?:documentos|documents|escritorio|desktop|descargas|downloads)\s+", "", name, flags=re.IGNORECASE).strip()

        # Quita conectores sobrantes del principio.
        name = re.sub(r"^(?:que\s+se\s+llame|se\s+llame|que\s+diga|diga|llamada|llamado)\s+", "", name, flags=re.IGNORECASE).strip()

        # Limpieza para nombres válidos en Windows.
        name = name.strip(" .\"“”'")
        name = re.sub(r'[<>:"/\\|?*]', "", name)
        name = re.sub(r"\s+", " ", name).strip()

        return name[:80]

    def extract_folder_location(self, text):
        if "documentos" in text or "mis documentos" in text:
            return "documents"
        if "escritorio" in text:
            return "desktop"
        if "descargas" in text:
            return "downloads"
        if "carpeta actual" in text or "proyecto" in text:
            return "actual"
        return "documents"

    def extract_folder_open_with(self, text):
        if "visual studio code" in text or "vscode" in text or "visual" in text or "vs code" in text:
            return "vscode"
        if "abre" in text or "abrir" in text or "ábre" in text or "abres" in text:
            return "explorer"
        return "none"


    # Plataformas reconocidas en TV (orden: más largas primero para evitar
    # que "prime" coincida antes que "prime video")
    # Fix #5: importadas desde config/tv_config.py — fuente única de verdad
    _PLATAFORMAS_TV = _TV_PLATAFORMAS_CFG
    _TV_PALABRAS    = _TV_PALABRAS_CFG

    def _extraer_info_tv(self, text):
        """
        Extrae plataforma (la primera mencionada en el texto), query limpio
        y capítulo de un comando natural de TV.

        Maneja múltiples plataformas con conectores "o"/"y":
          "reproduce el chavo en hbo o en vix en la tv"
            → plataforma=hbo, query="el chavo"
          "pon jujutsu kaisen ep 25 en crunchyroll en la tv"
            → plataforma=crunchyroll, query="jujutsu kaisen", capitulo="25"
        """
        t = text.lower().strip()

        # 1) Detectar la plataforma mencionada PRIMERO en el texto (por posición)
        primera_pos = len(t) + 1
        plataforma = None
        for p in self._PLATAFORMAS_TV:
            idx = t.find(p)
            if idx != -1 and idx < primera_pos:
                primera_pos = idx
                plataforma = p

        # 2) Detectar capítulo / episodio
        capitulo = None
        cap_m = re.search(
            r"(?:cap[ií]tulo|capitulo|episodio|ep\.?|cap\.?)\s*[#nº]?\s*(\d+)",
            t, re.IGNORECASE
        )
        if cap_m:
            capitulo = cap_m.group(1)

        # 3) Construir query limpio
        q = t

        # Quitar verbos de acción al inicio.
        # Fix: se amplió la lista para incluir "entrar", "quiero entrar a",
        # "quiero abrir", "quiero poner", "meter" y variantes comunes
        # que antes se colaban en el query (ej: "quiero entrar a crunchyroll").
        q = re.sub(
            r"^(?:quiero\s+(?:ver|entrar?\s*a?|abrir?|poner?|reproducir?)|"
            r"pon(?:me|le)?|reproduce(?:me)?|busca(?:me)?|"
            r"ponme|muéstrame|muestrame|abre|abrir|dale\s+play\s+a|"
            r"entra(?:r)?(?:\s+a)?|mete(?:r)?|"
            r"pon\s+a\s+reproducir)\s*",
            "", q, flags=re.IGNORECASE
        )

        # Quitar capítulo con su contexto
        q = re.sub(
            r"(?:el\s+)?(?:cap[ií]tulo|capitulo|episodio|ep\.?)\s*[#nº]?\s*\d+\s*(?:de\s+)?",
            "", q, flags=re.IGNORECASE
        )

        # Quitar TODAS las plataformas con conectores "o"/"y" antes o después
        for p in self._PLATAFORMAS_TV:
            q = re.sub(rf"\s+(?:o\s+|y\s+|[/,]\s*)?en\s+(?:la\s+|el\s+)?{re.escape(p)}", "", q)
            q = re.sub(rf"\s+(?:o\s+|y\s+|[/,]\s*)?{re.escape(p)}$", "", q)

        # Quitar referencia TV al final
        q = re.sub(
            r"\s+en\s+(?:la\s+|el\s+)?(?:tv|tele|televisión|television|televisor)",
            "", q
        )
        q = re.sub(
            r"\s+(?:la\s+)?(?:tv|tele|televisión|television|televisor)$",
            "", q
        )

        # Limpiar "o"/"y"/"en" sobrantes al final y espacios extra
        q = re.sub(r"\s+(?:o|y)\s*$", "", q)
        q = re.sub(r"\s+en\s*$", "", q)
        q = re.sub(r"\s+", " ", q).strip()

        # Fix: si el query resultante es solo el nombre de la plataforma
        # (ej: "abre crunchyroll" → query="crunchyroll"), vaciarlo para que
        # el clasificador envíe "abrir_app" en vez de buscar dentro de la app.
        if plataforma and q.lower() == plataforma.lower():
            q = ""

        # Quitar artículos/preposiciones sueltos que hayan quedado al inicio o al final
        # (ej: "quiero entrar a" → tras borrar plataforma queda "a")
        q = re.sub(r"^(?:(?:a|al|el|la|los|las|de|del|en)\s+)+", "", q).strip()
        q = re.sub(r"\s+(?:a|al|el|la|los|las|de|del|en)$", "", q).strip()

        return {"plataforma": plataforma, "query": q, "capitulo": capitulo}

    def classify(self, text):
        text = text.lower().strip()

        # ── 0. Custom intents: lo que el usuario le enseñó a JARVIS ─────────
        # Se evalúa PRIMERO para que los hechos personales tengan prioridad
        # sobre cualquier otro intent del sistema.
        try:
            from brain.custom_intents import CustomIntents
            _ci = CustomIntents()
            _respuesta_ci = _ci.match(text)
            if _respuesta_ci is not None:
                return {
                    "intent": "custom_intent",
                    "data":   {"action": "_direct", "response": _respuesta_ci}
                }
        except Exception:
            pass

        # ── 1. RAG — buscar en documentos personales ─────────────────────────
        _rag_buscar = (
            "qué sabes" in text or "busca en tus notas" in text
            or "busca en tu memoria" in text or "en tu memoria" in text
            or "en tus documentos" in text or "qué dice" in text
            or "cuéntame sobre" in text or "cuentame sobre" in text
            or "qué recuerdas de" in text or "que recuerdas de" in text
            or "busca sobre" in text
        )
        if _rag_buscar:
            # Limpiar el comando para quedarnos solo con la consulta real
            _query = text
            for _p in [
                "qué sabes sobre", "que sabes sobre", "busca en tus notas",
                "busca en tu memoria", "en tu memoria sobre", "en tus documentos",
                "qué dice sobre", "que dice sobre", "cuéntame sobre", "cuentame sobre",
                "qué recuerdas de", "que recuerdas de", "busca sobre",
            ]:
                _query = _query.replace(_p, "").strip()
            return {"intent": "rag", "data": {"action": "buscar_rag", "query": _query or text}}

        # ── 2. RAG — agregar documento a la memoria ──────────────────────────
        # "agrega a tu memoria: recetas — Caldo de pollo: agua, pollo, sal"
        if "agrega a tu memoria" in text or "agrega a tus notas" in text \
                or "guarda en tu memoria" in text or "aprende esto" in text:
            # Extraer nombre y contenido separados por " — " o " - "
            import re as _re
            _m = _re.search(r"(?:memoria|notas)[:\s]+(.+?)\s*[—\-–]{1,2}\s*(.+)$", text)
            if _m:
                return {
                    "intent": "rag",
                    "data": {
                        "action":    "agregar_rag",
                        "nombre":    _m.group(1).strip(),
                        "contenido": _m.group(2).strip(),
                    }
                }
            return {"intent": "rag", "data": {"action": "agregar_rag",
                    "nombre": "nuevo", "contenido": text}}

        if "reconstruye tu memoria" in text or "reindexate" in text \
                or "actualiza tu memoria" in text or "recarga tus documentos" in text:
            return {"intent": "rag", "data": {"action": "rebuild_rag"}}

        if "lista tus documentos" in text or "qué documentos tienes" in text \
                or "cuáles son tus archivos" in text:
            return {"intent": "rag", "data": {"action": "listar_rag"}}

        # ── 3. Enseñar intents personalizados ───────────────────────────────
        # "enséñate que cuando diga <frase> respondas <respuesta>"
        if "enséñate que" in text or "enseñate que" in text \
                or "recuerda que cuando" in text or "aprende que cuando" in text:
            import re as _re
            _m = _re.search(
                r"(?:diga|digas|digo|escuches|escuche)\s+[\"']?(.+?)[\"']?"
                r"\s+(?:respondas?|digas?|contestes?)\s+[\"']?(.+?)[\"']?$",
                text
            )
            if _m:
                _patron   = _m.group(1).strip()
                _respuesta = _m.group(2).strip()
                return {
                    "intent": "custom_intent",
                    "data": {
                        "action":    "agregar_intent",
                        "patrones":  [_patron],
                        "respuesta": _respuesta,
                        "etiqueta":  _patron[:25],
                    }
                }

        if "olvida el intent" in text or "elimina el intent" in text \
                or "borra el intent" in text:
            import re as _re
            _m = _re.search(r"intent\s+(.+)$", text)
            _etiq = _m.group(1).strip() if _m else ""
            return {"intent": "custom_intent",
                    "data": {"action": "eliminar_intent", "etiqueta": _etiq}}

        if "qué intents tienes" in text or "que intents tienes" in text \
                or "intents guardados" in text or "lista intents" in text:
            return {"intent": "custom_intent", "data": {"action": "listar_intents"}}

        # ── 4. Fine-tuning ───────────────────────────────────────────────────
        if "guarda este ejemplo" in text or "guarda esa respuesta" in text:
            return {"intent": "finetune", "data": {"action": "guardar_ejemplo",
                    "pregunta": "", "respuesta": ""}}

        if "genera modelfile" in text or "genera el modelfile" in text \
                or "crea el modelfile" in text:
            return {"intent": "finetune", "data": {"action": "modelfile"}}

        if "cuántos ejemplos" in text or "cuantos ejemplos" in text \
                or "estadísticas de entrenamiento" in text \
                or "estado del dataset" in text:
            return {"intent": "finetune", "data": {"action": "stats_finetune"}}

        # ── Crear carpeta ────────────────────────────────────────────
        _crear_verbos = ["crea", "crear", "haz", "hacer", "nueva", "nuevo"]
        if "carpeta" in text and any(w in text for w in _crear_verbos):
            return {
                "intent": "file_manager",
                "data": {
                    "action": "create_folder",
                    "folder_name": self.extract_folder_name(text),
                    "location": self.extract_folder_location(text),
                    "open_with": self.extract_folder_open_with(text)
                }
            }

        # Fix: "hora" solo → pedir la hora. Pero "a las 7 hora..." o "alarma a la hora..."
        # NO deben disparar esto — deben llegar al bloque de celular.
        _pedir_hora = (
            text.strip() in ["hora", "la hora", "qué horas", "que horas", "dime la hora",
                              "qué hora es", "que hora es", "qué hora son", "que hora son"]
            or text.strip().startswith("qué hora")
            or text.strip().startswith("que hora")
        )
        if _pedir_hora:
            return {
                "intent": "get_time",
                "data": {}
            }

        if (
            "muestra mis notas" in text
            or "ver mis notas" in text
            or "enséñame mis notas" in text
            or "enseñame mis notas" in text
            or text == "mis notas"
        ):
            return {
                "intent": "create_note",
                "data": {
                    "action": "show"
                }
            }

        if (
            "borra mis notas" in text
            or "elimina mis notas" in text
            or "limpia mis notas" in text
        ):
            return {
                "intent": "create_note",
                "data": {
                    "action": "delete"
                }
            }

        if "historial" in text or "comandos usados" in text or "qué comandos he usado" in text:
            return {
                "intent": "history",
                "data": {
                    "action": "show"
                }
            }

        if "borra historial" in text or "elimina historial" in text or "limpia historial" in text:
            return {
                "intent": "history",
                "data": {
                    "action": "delete"
                }
            }

        if (
            "muestra mis recordatorios" in text
            or "ver mis recordatorios" in text
            or "enséñame mis recordatorios" in text
            or "enseñame mis recordatorios" in text
            or text == "mis recordatorios"
        ):
            return {
                "intent": "reminder",
                "data": {
                    "action": "show"
                }
            }

        if (
            "borra mis recordatorios" in text
            or "elimina mis recordatorios" in text
            or "limpia mis recordatorios" in text
        ):
            return {
                "intent": "reminder",
                "data": {
                    "action": "delete"
                }
            }

        if (
            "recuérdame" in text
            or "recuerdame" in text
            or "agrega un recordatorio" in text
            or "crea un recordatorio" in text
            or "guarda un recordatorio" in text
        ):
            reminder = (
                text.replace("recuérdame", "")
                .replace("recuerdame", "")
                .replace("agrega un recordatorio", "")
                .replace("crea un recordatorio", "")
                .replace("guarda un recordatorio", "")
                .replace("recordatorio", "")
                .strip()
            )

            return {
                "intent": "reminder",
                "data": {
                    "action": "create",
                    "reminder": reminder
                }
            }

        if (
            "bloquea la computadora" in text
            or "bloquear computadora" in text
            or "bloquea el equipo" in text
            or "bloquear equipo" in text
            or "bloquea la pc" in text
            or "bloquear pc" in text
        ):
            return {
                "intent": "system_request",
                "data": {
                    "action": "lock"
                }
            }

        if (
            "apaga la computadora" in text
            or "apagar computadora" in text
            or "apaga el equipo" in text
            or "apagar equipo" in text
            or "apaga la pc" in text
            or "apagar pc" in text
        ):
            return {
                "intent": "system_request",
                "data": {
                    "action": "shutdown"
                }
            }

        if (
            "reinicia la computadora" in text
            or "reiniciar computadora" in text
            or "reinicia el equipo" in text
            or "reiniciar equipo" in text
            or "reinicia la pc" in text
            or "reiniciar pc" in text
        ):
            return {
                "intent": "system_request",
                "data": {
                    "action": "restart"
                }
            }

        if text in ["confirmar", "confirmo", "sí", "si", "aceptar"]:
            return {
                "intent": "confirm_action",
                "data": {}
            }

        if text in ["cancelar", "cancela", "no", "detener"]:
            return {
                "intent": "cancel_action",
                "data": {}
            }

        # Estos bloques solo aplican a la PC.
        # Si el texto menciona tv/tele, los salta para que los maneje el bloque de TV.
        _es_tv = any(w in text for w in ["tv", "tele", "television", "televisión"])

        if not _es_tv and "reproduce" in text and "youtube" in text:
            query = (
                text.replace("reproduce", "")
                .replace("en youtube", "")
                .replace("youtube", "")
                .strip()
            )

            return {
                "intent": "web",
                "data": {
                    "action": "play_youtube",
                    "query": query
                }
            }

        if not _es_tv and "pon" in text and "youtube" in text:
            query = (
                text.replace("pon", "")
                .replace("en youtube", "")
                .replace("youtube", "")
                .strip()
            )

            return {
                "intent": "web",
                "data": {
                    "action": "play_youtube",
                    "query": query
                }
            }

        if not _es_tv and "youtube" in text and ("abre" in text or "abrir" in text):
            return {
                "intent": "web",
                "data": {
                    "action": "open_youtube"
                }
            }

        if "google" in text and ("abre" in text or "abrir" in text):
            return {
                "intent": "web",
                "data": {
                    "action": "open_google"
                }
            }

        if text == "youtube":
            return {
                "intent": "web",
                "data": {
                    "action": "open_youtube"
                }
            }

        if text == "google":
            return {
                "intent": "web",
                "data": {
                    "action": "open_google"
                }
            }

        if not _es_tv and ("busca en youtube" in text or "buscar en youtube" in text):
            query = (
                text.replace("busca en youtube", "")
                .replace("buscar en youtube", "")
                .strip()
            )

            return {
                "intent": "web",
                "data": {
                    "action": "search_youtube",
                    "query": query
                }
            }

        # WhatsApp/llamada sin mencionar "celular" explícitamente
        if "whatsapp" in text and any(w in text for w in ["manda", "envía", "envia", "escribe", "dile"]):
            num_m = re.search(r"[\d\+][\d\s\-]{6,}", text)
            numero = num_m.group(0).strip() if num_m else ""
            msg_m = re.search(r"(?:mensaje|que diga|diciendo|texto)\s+(.+)$", text)
            mensaje = msg_m.group(1) if msg_m else ""
            return {"intent": "phone", "data": {"action": "whatsapp", "numero": numero, "mensaje": mensaje}}

        # "buscar package X" → TV, siempre antes que búsqueda web
        if "package" in text and any(w in text for w in ["buscar", "busca", "package de"]):
            q = re.sub(r"buscar?\s+(?:el\s+)?package\s+(?:de\s+)?|package\s+de\s+", "", text).strip()
            return {"intent": "tv", "data": {"action": "buscar_package", "query": q}}

        if not _es_tv and ("busca" in text or "buscar" in text):
            query = (
                text.replace("busca en google", "")
                .replace("buscar en google", "")
                .replace("busca", "")
                .replace("buscar", "")
                .strip()
            )

            return {
                "intent": "web",
                "data": {
                    "action": "search_google",
                    "query": query
                }
            }

        # Comandos de media solo para la PC (no TV)
        if not _es_tv and ("pausa" in text or "pausar" in text):
            return {
                "intent": "media",
                "data": {
                    "action": "pause"
                }
            }

        if not _es_tv and ("continua" in text or "continúa" in text or "reanuda" in text):
            return {
                "intent": "media",
                "data": {
                    "action": "play"
                }
            }

        _es_cel_check = any(w in text for w in ["celular","teléfono","telefono","móvil","movil","cel"])
        if not _es_tv and not _es_cel_check and (
            "sube volumen" in text
            or "sube el volumen" in text
            or "subir volumen" in text
            or "subir el volumen" in text
            or "aumenta volumen" in text
            or "aumenta el volumen" in text
        ):
            return {
                "intent": "media",
                "data": {
                    "action": "volume_up"
                }
            }

        if not _es_tv and not _es_cel_check and (
            "baja volumen" in text
            or "baja el volumen" in text
            or "bajar volumen" in text
            or "bajar el volumen" in text
            or "disminuye volumen" in text
            or "disminuye el volumen" in text
        ):
            return {
                "intent": "media",
                "data": {
                    "action": "volume_down"
                }
            }

        if not _es_tv and not _es_cel_check and ("silencia" in text or "silenciar" in text or "mute" in text):
            return {
                "intent": "media",
                "data": {
                    "action": "mute"
                }
            }

        if "pantalla completa" in text:
            return {
                "intent": "media",
                "data": {
                    "action": "fullscreen"
                }
            }

        if not _es_tv and not _es_cel_check and "siguiente" in text:
            return {
                "intent": "media",
                "data": {
                    "action": "next"
                }
            }

        if not _es_tv and ("adelanta" in text or "adelantar" in text):
            return {
                "intent": "media",
                "data": {
                    "action": "forward"
                }
            }

        if not _es_tv and ("retrocede" in text or "retroceder" in text):
            return {
                "intent": "media",
                "data": {
                    "action": "back"
                }
            }

        if "nota" in text or "apunta" in text:
            note = (
                text.replace("crea una nota", "")
                .replace("crear nota", "")
                .replace("guarda una nota", "")
                .replace("guarda nota", "")
                .replace("nota", "")
                .replace("apunta", "")
                .strip()
            )

            return {
                "intent": "create_note",
                "data": {
                    "action": "create",
                    "note": note
                }
            }
        if (
            "lee archivo" in text
            or "leer archivo" in text
            or "lee un archivo" in text
            or "leer un archivo" in text
            or "lee mi pdf" in text
            or "leer mi pdf" in text
            or "lee pdf" in text
            or "leer pdf" in text
        ):
            return {
                "intent": "file_reader",
                "data": {
                    "action": "read"
                }
            }

        if (
            "resume archivo" in text
            or "resumir archivo" in text
            or "resume un archivo" in text
            or "resumir un archivo" in text
            or "resume mi pdf" in text
            or "resumir mi pdf" in text
            or "resume pdf" in text
            or "resumir pdf" in text
        ):
            return {
                "intent": "file_reader",
                "data": {
                    "action": "summary"
                }
            }


        # ── CELULAR / PHONE ──────────────────────────────────────────────────────
        _cel_palabras = ["celular", "teléfono", "telefono", "móvil", "movil", "cel", "phone"]
        _es_cel = any(w in text for w in _cel_palabras)

        if _es_cel:

            # Conexión / Emparejamiento
            ip_m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", text)
            if "conectar" in text or "conecta" in text:
                ip = ip_m.group(1) if ip_m else ""
                texto_sin_ip = text.replace(ip, "") if ip else text

                # Fix: si hay un número de 6 dígitos es el código de emparejamiento,
                # aunque el usuario haya dicho "conectar" en vez de "vincular/emparejar".
                # Ejemplo: "conectar celular 192.168.3.4 44917 178759"
                #           → emparejar(ip, puerto=44917, codigo=178759)
                codigo_m = re.search(r"\b(\d{6})\b", texto_sin_ip)
                if codigo_m:
                    codigo = codigo_m.group(1)
                    puerto_m = re.search(r"\b(\d{4,5})\b", texto_sin_ip)
                    puerto = puerto_m.group(1) if puerto_m else ""
                    return {"intent": "phone", "data": {"action": "emparejar", "ip": ip, "puerto": puerto, "codigo": codigo}}

                # Sin código de 6 dígitos → conexión directa (IP + puerto)
                puerto_m = re.search(r"\b(\d{4,5})\b", texto_sin_ip)
                puerto = puerto_m.group(1) if puerto_m else ""
                return {"intent": "phone", "data": {"action": "conectar", "ip": ip, "puerto": puerto}}

            if "desconectar" in text or "desconecta" in text:
                return {"intent": "phone", "data": {"action": "desconectar"}}

            if "emparejar" in text or "vincular" in text or "pair" in text:
                partes = text.split()
                ip = ip_m.group(1) if ip_m else ""
                numeros = re.findall(r"\d+", text.replace(ip, ""))
                puerto = numeros[0] if numeros else ""
                codigo = numeros[1] if len(numeros) > 1 else ""
                return {"intent": "phone", "data": {"action": "emparejar", "ip": ip, "puerto": puerto, "codigo": codigo}}

            if "usb" in text and ("preparar" in text or "activar" in text or "configurar" in text):
                return {"intent": "phone", "data": {"action": "preparar_usb"}}

            if "estado" in text or "conectado" in text:
                return {"intent": "phone", "data": {"action": "estado"}}

            if "info" in text or "información" in text or "informacion" in text or "batería" in text or "bateria" in text:
                return {"intent": "phone", "data": {"action": "info"}}

            # Pantalla
            if ("enciende" in text or "encender" in text or "prende" in text) and "pantalla" in text:
                return {"intent": "phone", "data": {"action": "encender_pantalla"}}

            if ("apaga" in text or "apagar" in text) and "pantalla" in text:
                return {"intent": "phone", "data": {"action": "apagar_pantalla"}}

            # Screenshot
            if "screenshot" in text or "captura" in text or "pantallaz" in text:
                return {"intent": "phone", "data": {"action": "screenshot"}}

            # Volumen
            if ("sube" in text or "subir" in text or "aumenta" in text) and "volumen" in text:
                veces = 3
                m = re.search(r"(\d+)\s*(?:veces|niveles?)?", text)
                if m: veces = int(m.group(1))
                return {"intent": "phone", "data": {"action": "volumen_up", "veces": veces}}

            if ("baja" in text or "bajar" in text or "disminuye" in text) and "volumen" in text:
                veces = 3
                m = re.search(r"(\d+)\s*(?:veces|niveles?)?", text)
                if m: veces = int(m.group(1))
                return {"intent": "phone", "data": {"action": "volumen_down", "veces": veces}}

            if "silencia" in text or "mute" in text or "silenciar" in text:
                return {"intent": "phone", "data": {"action": "silenciar"}}

            if "vibra" in text or "vibración" in text or "vibracion" in text or "modo vibración" in text:
                return {"intent": "phone", "data": {"action": "vibrar"}}

            if ("quita" in text or "quitar" in text or "activa" in text or "normal" in text) and "silencio" in text:
                return {"intent": "phone", "data": {"action": "sonido_normal"}}

            # ── Conectividad ──────────────────────────────────────────
            if "wifi" in text or "wi-fi" in text:
                apagar = any(w in text for w in ["apaga","desactiva","desactivar","quita","off","deshabilita"])
                return {"intent": "phone", "data": {"action": "wifi_off" if apagar else "wifi_on"}}

            if "bluetooth" in text or "bt" in text:
                apagar = any(w in text for w in ["apaga","desactiva","desactivar","quita","off"])
                return {"intent": "phone", "data": {"action": "bt_off" if apagar else "bt_on"}}

            if ("datos" in text and ("móvil" in text or "movil" in text or "celular" in text)) or "datos móviles" in text:
                apagar = any(w in text for w in ["apaga","desactiva","quita","off"])
                return {"intent": "phone", "data": {"action": "datos_off" if apagar else "datos_on"}}

            if "modo avión" in text or "modo avion" in text or ("avion" in text and "modo" in text):
                apagar = any(w in text for w in ["apaga","desactiva","quita","off","desactivar"])
                return {"intent": "phone", "data": {"action": "avion_off" if apagar else "avion_on"}}

            # ── Pantalla / apariencia ─────────────────────────────────
            if "brillo" in text:
                # Buscar porcentaje: "pon el brillo al 70%"
                pct_m = re.search(r"(\d+)\s*%", text)
                if pct_m:
                    return {"intent": "phone", "data": {"action": "brillo", "nivel": int(pct_m.group(1))}}
                if any(w in text for w in ["auto","automático","automatico"]):
                    apagar = any(w in text for w in ["apaga","desactiva","quita","off"])
                    return {"intent": "phone", "data": {"action": "brillo_auto_off" if apagar else "brillo_auto_on"}}
                # Sube/baja brillo sin valor → 80% / 20% por defecto
                if any(w in text for w in ["sube","subir","más","mas","aumenta"]):
                    return {"intent": "phone", "data": {"action": "brillo", "nivel": 80}}
                if any(w in text for w in ["baja","bajar","menos","reduce"]):
                    return {"intent": "phone", "data": {"action": "brillo", "nivel": 20}}
                # Fix: fallback — sin modificador específico, consultar/mostrar brillo actual
                # antes el bloque caía fuera de _es_cel y terminaba como open_app("brillo")
                return {"intent": "phone", "data": {"action": "info"}}

            if "modo oscuro" in text or "dark mode" in text or "modo noche" in text:
                apagar = any(w in text for w in ["apaga","desactiva","quita","off","desactivar"])
                return {"intent": "phone", "data": {"action": "dark_off" if apagar else "dark_on"}}

            if "rotación" in text or "rotacion" in text:
                desbloquear = any(w in text for w in ["desbloquea","desbloquear","activa","habilita"])
                return {"intent": "phone", "data": {"action": "rotacion_off" if desbloquear else "rotacion_on"}}

            # ── No Molestar ───────────────────────────────────────────
            if "no molestar" in text or "dnd" in text or "no disturb" in text:
                apagar = any(w in text for w in ["apaga","desactiva","quita","off"])
                return {"intent": "phone", "data": {"action": "dnd_off" if apagar else "dnd_on"}}

            # ── Alarma ────────────────────────────────────────────────
            if "alarma" in text or "despertador" in text:
                # Extraer hora: "pon alarma a las 7:30", "a las 8", "7 30"
                hora_m = re.search(r"(\d{1,2})[:\s](\d{2})", text)
                if not hora_m:
                    hora_m = re.search(r"(?:las?\s+)?(\d{1,2})\s*(?:en\s+punto)?(?:\s*y\s*media)?", text)
                hora    = int(hora_m.group(1)) if hora_m else 7
                minutos = int(hora_m.group(2)) if hora_m and hora_m.lastindex >= 2 else 0
                etiq_m  = re.search(r"(?:llamada?|etiqueta|nombre|que diga)\s+(.+)$", text)
                etiq    = etiq_m.group(1) if etiq_m else "Alarma JARVIS"
                return {"intent": "phone", "data": {"action": "alarma", "hora": hora, "minutos": minutos, "etiqueta": etiq}}

            # ── Ahorro de energía ─────────────────────────────────────
            if "ahorro" in text or "batería saver" in text or "battery saver" in text:
                apagar = any(w in text for w in ["apaga","desactiva","quita","off"])
                return {"intent": "phone", "data": {"action": "bateria_saver_off" if apagar else "bateria_saver_on"}}

            # ── Reiniciar ─────────────────────────────────────────────
            if ("reinicia" in text or "reiniciar" in text or "reboot" in text or "restart" in text):
                return {"intent": "phone", "data": {"action": "reiniciar_cel"}}

            # Llamadas
            if "llama" in text or "llamar" in text or "llamada" in text:
                num_m = re.search(r"[\d\+][\d\s\-]{6,}", text)
                numero = num_m.group(0).strip() if num_m else re.sub(r"llama(?:r)?(?:\s+a)?\s*", "", text, flags=re.IGNORECASE).strip()
                return {"intent": "phone", "data": {"action": "llamar", "numero": numero}}

            if "marca" in text or "marcar" in text:
                num_m = re.search(r"[\d\+][\d\s\-]{6,}", text)
                numero = num_m.group(0).strip() if num_m else ""
                return {"intent": "phone", "data": {"action": "marcar", "numero": numero}}

            if "cuelga" in text or "colgar" in text or "termina la llamada" in text:
                return {"intent": "phone", "data": {"action": "colgar"}}

            # WhatsApp: solo si hay un número → acción de mensaje; si no → abrir app
            if "whatsapp" in text:
                num_m = re.search(r"[\d\+][\d\s\-]{6,}", text)
                if num_m:
                    numero = num_m.group(0).strip()
                    msg_m = re.search(r"(?:mensaje|que diga|diciendo|texto)\s+(.+)$", text)
                    mensaje = msg_m.group(1) if msg_m else ""
                    return {"intent": "phone", "data": {"action": "whatsapp", "numero": numero, "mensaje": mensaje}}
                # Sin número → solo abrir la app
                return {"intent": "phone", "data": {"action": "abrir_app", "app": "whatsapp"}}

            # SMS
            if "sms" in text or "mensaje de texto" in text or "manda un mensaje" in text:
                num_m = re.search(r"[\d\+][\d\s\-]{6,}", text)
                numero = num_m.group(0).strip() if num_m else ""
                msg_m = re.search(r"(?:que diga|diciendo|mensaje)\s+(.+)$", text)
                mensaje = msg_m.group(1) if msg_m else ""
                return {"intent": "phone", "data": {"action": "sms", "numero": numero, "mensaje": mensaje}}

            # Linterna
            if "linterna" in text or "flash" in text or "lámpara" in text or "lampara" in text:
                apagar = any(w in text for w in ["apaga", "apagar", "quita", "quitar", "off"])
                return {"intent": "phone", "data": {"action": "linterna_off" if apagar else "linterna_on"}}

            # Notificaciones
            if "notificaciones" in text or "notificación" in text or "avisos" in text:
                return {"intent": "phone", "data": {"action": "notificaciones"}}

            # Reproducción
            if "pausa" in text or "play" in text or "reanuda" in text:
                return {"intent": "phone", "data": {"action": "play_pause"}}

            if "siguiente" in text or "next" in text:
                return {"intent": "phone", "data": {"action": "siguiente"}}

            # Fix: "anterior" → pista previa de audio
            # "atrás/atras/back" → botón de retroceso de navegación
            # Antes estaban mezclados: "atrás" siempre caía en "anterior"
            # y el check de navegación más abajo era código muerto.
            if "anterior" in text:
                return {"intent": "phone", "data": {"action": "anterior"}}

            # Navegación
            if "inicio" in text or "home" in text:
                return {"intent": "phone", "data": {"action": "home"}}

            if "apps recientes" in text or "recientes" in text:
                return {"intent": "phone", "data": {"action": "recientes"}}

            if "atrás" in text or "atras" in text or "back" in text:
                return {"intent": "phone", "data": {"action": "atras"}}

            # Abrir app
            if "abre" in text or "abrir" in text or "abrí" in text or "pon" in text:
                app = re.sub(
                    r"(?:abre|abrir|pon(?:me)?|en el )\s*(?:celular|teléfono|telefono|móvil|movil|cel)?\s*",
                    "", text, flags=re.IGNORECASE
                ).strip()
                return {"intent": "phone", "data": {"action": "abrir_app", "app": app}}

        # ── TV / Android TV ──────────────────────────────────────────────

        # ── HÁBITOS / Análisis de uso ─────────────────────────────────────────
        _habitos_trigger = (
            any(w in text for w in [
                "hábito", "habito", "hábitos", "habitos",
                "mis comandos", "uso más", "uso mas", "más uso", "mas uso",
                "suelo hacer", "suelo poner", "qué hago", "que hago",
                "qué música", "que musica", "música suelo", "musica suelo",
                "a qué hora", "a que hora", "hora me conecto",
                "analiza mis", "analizar mis", "muéstrame mis", "muestrame mis",
                "estadísticas", "estadisticas", "mis hábitos", "mis habitos",
            ])
        )
        if _habitos_trigger:
            action = "resumen"
            query  = text
            if any(w in text for w in ["música", "musica", "canción", "cancion", "song"]):
                action = "musica"
            elif any(w in text for w in ["comandos", "uso", "más uso", "mas uso"]):
                action = "comandos"
            elif any(w in text for w in ["hora", "conecto", "horario"]):
                action = "horario"
            elif any(d in text for d in ["lunes","martes","miércoles","miercoles",
                                          "jueves","viernes","sábado","sabado","domingo"]):
                action = "dia"
            return {"intent": "habits", "data": {"action": action, "query": text}}

        # Listar/buscar apps instaladas en la TV
        if any(p in text for p in ["listar apps", "qué apps", "que apps", "apps instaladas", "apps en la tv", "ver apps", "todas las apps"]):
            if any(w in text for w in ["tv", "tele", "televisión", "television"]):
                return {"intent": "tv", "data": {"action": "listar_apps"}}

        if "buscar package" in text or "busca el package" in text or "package de" in text:
            q = re.sub(r"buscar?\s+(?:el\s+)?package\s+(?:de\s+)?|package\s+de\s+", "", text).strip()
            return {"intent": "tv", "data": {"action": "buscar_package", "query": q}}

        if ("conectar tv" in text or "conectar la tv" in text or "conectar tele" in text):
            ip_match = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", text)
            ip = ip_match.group(1) if ip_match else ""
            return {"intent": "tv", "data": {"action": "conectar", "extra": ip}}

        if ("desconectar tv" in text or "desconectar la tv" in text):
            return {"intent": "tv", "data": {"action": "desconectar"}}

        if ("estado tv" in text or "estado de la tv" in text or "tv conectada" in text):
            return {"intent": "tv", "data": {"action": "estado"}}

        # ── Detectar si el comando es para TV ────────────────────────────────
        _tv_palabras  = ["tv", "tele", "televisión", "television", "televisor"]
        _plataformas  = self._PLATAFORMAS_TV
        _tiene_tv     = any(w in text for w in _tv_palabras)
        _tiene_plat   = any(p in text for p in _plataformas)

        # Comandos que implican TV si mencionan tv/tele O una plataforma de streaming
        # junto con un verbo de reproducción o la palabra "ver"
        # Verbos de solo-búsqueda (mostrar resultados, usuario elige)
        _verbos_buscar = ["busca", "buscar", "busco", "muéstrame", "muestrame", "muestra"]
        # Verbos de reproducción (buscar Y auto-seleccionar para reproducir)
        _verbos_rep    = ["reproduce", "pon", "quiero ver", "ver", "play"]
        _tiene_verbo_buscar = any(v in text for v in _verbos_buscar)
        _tiene_verbo_rep    = any(v in text for v in _verbos_rep)
        _tiene_verbo        = _tiene_verbo_buscar or _tiene_verbo_rep
        _es_cmd_tv    = _tiene_tv or (_tiene_plat and _tiene_verbo)

        if _es_cmd_tv:

            # ── Temporizador PRIMERO ── (contiene "apaga" + tiempo,
            #    debe evaluarse antes del toggle general de encender/apagar)
            if ("apaga" in text or "apagar" in text) and ("minut" in text or "hora" in text):
                min_m = re.search(r"(\d+)\s*(?:minut|hora)", text)
                minutos = int(min_m.group(1)) if min_m else 30
                if "hora" in text and min_m:
                    minutos *= 60
                return {"intent": "tv", "data": {"action": "temporizador", "minutos": minutos}}

            if ("apaga" in text or "apagar" in text or "enciende" in text
                    or "encender" in text or "prende" in text):
                return {"intent": "tv", "data": {"action": "encender"}}

            if ("sube" in text or "subir" in text or "aumenta" in text) and "volumen" in text:
                veces = 3
                m = re.search(r"(\d+)\s*(?:veces|niveles?|pasos?)?", text)
                if m:
                    veces = int(m.group(1))
                return {"intent": "tv", "data": {"action": "volumen_up", "veces": veces}}

            if ("baja" in text or "bajar" in text or "disminuye" in text) and "volumen" in text:
                veces = 3
                m = re.search(r"(\d+)\s*(?:veces|niveles?|pasos?)?", text)
                if m:
                    veces = int(m.group(1))
                return {"intent": "tv", "data": {"action": "volumen_down", "veces": veces}}

            if "silencia" in text or "mute" in text or "sin sonido" in text:
                return {"intent": "tv", "data": {"action": "mute"}}

            # Subtítulos
            if "subtítulo" in text or "subtitulo" in text or "caption" in text:
                return {"intent": "tv", "data": {"action": "subtitulos"}}

            # Adelantar / retroceder
            if "adelanta" in text or "adelantar" in text or "fast forward" in text:
                return {"intent": "tv", "data": {"action": "adelantar"}}

            if "retrocede" in text or "retroceder" in text or "rewind" in text or "regresa" in text:
                return {"intent": "tv", "data": {"action": "retroceder"}}

            # Info de lo que se reproduce
            if ("qué" in text or "que" in text or "info" in text) and ("viendo" in text or "reproduce" in text):
                return {"intent": "tv", "data": {"action": "info_tv"}}

            # Canal arriba / abajo
            if "canal" in text:
                if any(w in text for w in ["arriba", "sigue", "siguiente", "subir", "next"]):
                    return {"intent": "tv", "data": {"action": "canal_arriba"}}
                if any(w in text for w in ["abajo", "anterior", "bajar", "back"]):
                    return {"intent": "tv", "data": {"action": "canal_abajo"}}

            if ("pausa" in text or "pausar" in text or "detener" in text) and not _tiene_verbo:
                return {"intent": "tv", "data": {"action": "play_pause"}}

            if "siguiente" in text or "next" in text:
                return {"intent": "tv", "data": {"action": "siguiente"}}

            if "anterior" in text or ("atrás" in text or "atras" in text):
                return {"intent": "tv", "data": {"action": "anterior"}}

            if ("inicio" in text or "home" in text) and not _tiene_verbo:
                return {"intent": "tv", "data": {"action": "home"}}

            if any(w in text for w in ["enter", "ok", "seleccionar", "selecciona", "confirma", "acepta"]):
                return {"intent": "tv", "data": {"action": "ok"}}

            if any(w in text for w in ["arriba", "sube", "subir"]) and "volumen" not in text and "canal" not in text:
                return {"intent": "tv", "data": {"action": "navegar", "extra": "arriba"}}
            if any(w in text for w in ["abajo", "baja", "bajar"]) and "volumen" not in text and "canal" not in text:
                return {"intent": "tv", "data": {"action": "navegar", "extra": "abajo"}}
            if any(w in text for w in ["izquierda"]):
                return {"intent": "tv", "data": {"action": "navegar", "extra": "izquierda"}}
            if "derecha" in text:
                return {"intent": "tv", "data": {"action": "navegar", "extra": "derecha"}}
            if any(w in text for w in ["back", "regresa", "volver", "vuelve"]) and "retrocede" not in text:
                return {"intent": "tv", "data": {"action": "atras"}}

            # Comandos con contenido: busca X / reproduce X en plataforma en la tv
            if _tiene_verbo or _tiene_plat:
                info = self._extraer_info_tv(text)
                query     = info["query"]
                plat      = info["plataforma"]
                capitulo  = info["capitulo"]

                # Si solo quiere abrir una app sin contenido específico
                if not query and plat:
                    return {"intent": "tv", "data": {"action": "abrir_app", "app": plat}}

                # "busca X" → mostrar resultados, el usuario elige
                # "reproduce/pon X" → buscar Y auto-seleccionar para reproducir
                accion_tv = "buscar" if _tiene_verbo_buscar and not _tiene_verbo_rep else "reproducir"

                return {
                    "intent": "tv",
                    "data": {
                        "action":     accion_tv,
                        "plataforma": plat or "",
                        "query":      query,
                        "capitulo":   capitulo,
                    }
                }

            # Abrir app genérica en TV: "abre netflix en la tv"
            if "abre" in text or "abrir" in text or "pon" in text:
                info = self._extraer_info_tv(text)
                app  = info["plataforma"] or info["query"]
                return {"intent": "tv", "data": {"action": "abrir_app", "app": app}}

        # ── Abrir app en PC (al final para no chocar con TV) ─────────────

        if "abre" in text or "abrir" in text:
            app_name = text.replace("abre", "").replace("abrir", "").strip()

            return {
                "intent": "open_app",
                "data": {
                    "app_name": app_name
                }
            }

        return {
            "intent": "unknown",
            "data": {
                "original_text": text
            }
        }
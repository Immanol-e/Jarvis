import re
import unicodedata


class TaskPlanner:
    """
    Convierte órdenes naturales en varios pasos ejecutables.

    Nivel actual:
    - Crear carpetas y archivos.
    - Crear proyectos completos.
    - Buscar, leer, explicar y modificar archivos existentes.
    - Crear interfaces gráficas en proyectos Python, Java y Web.
    - Agregar mejoras simples a proyectos existentes.
    """

    CREATE_WORDS = ["crea", "crear", "haz", "hacer", "genera", "generar", "nueva", "nuevo"]
    COMPOUND_WORDS = [" y ", ",", " luego ", " después ", " despues ", " adentro ", " dentro ", " tambien ", " también "]

    FILE_EXTENSIONS = (
        "py", "java", "txt", "html", "css", "js", "md", "json", "xml", "csv",
        "cpp", "c", "cs", "kt", "php", "sql", "bat", "sh", "ino", "yml", "yaml"
    )

    def plan(self, user_input):
        original = user_input.strip()
        text = self.normalize(original)

        if not original:
            return None

        # Primero revisamos si el usuario quiere una interfaz gráfica.
        gui_plan = self.plan_gui_task(original, text)
        if gui_plan:
            return gui_plan

        # Luego revisamos acciones sobre archivos/proyectos ya existentes.
        editor_plan = self.plan_editor_task(original, text)
        if editor_plan:
            return editor_plan

        if not self.looks_like_file_task(text):
            return None

        folder_requested = "carpeta" in text or "proyecto" in text or "pagina web" in text or "página web" in text
        file_requested = "archivo" in text or "archivos" in text or bool(self.extract_file_names(original))
        location = self.extract_location(text)
        open_with = self.extract_open_with(text)
        file_names = self.extract_file_names(original)

        # Proyectos completos:
        # "crea un proyecto de python para calculadora"
        # "crea una pagina web de login y abrela en visual"
        template = self.detect_template(text)
        if self.looks_like_project_task(text):
            project_name = self.extract_project_name(original, template)

            return {
                "type": "steps",
                "steps": [
                    {
                        "intent": "project",
                        "data": {
                            "action": "create_project",
                            "project_type": template or "general",
                            "project_name": project_name,
                            "location": location,
                            "description": original,
                            "open_with": open_with if open_with != "none" else "vscode",
                            "files": file_names
                        }
                    }
                ],
                "description": "creación de proyecto completo"
            }

        # Si es una orden simple de una sola acción, dejamos que el clasificador normal la maneje.
        if not self.looks_compound(text) and not file_requested:
            return None

        folder_name = self.extract_folder_name(original)

        # Plantillas automáticas cuando el usuario habla de proyectos.
        if template and not file_names:
            file_names = self.default_files_for_template(template)

        steps = []

        if folder_requested:
            if not folder_name:
                folder_name = self.default_folder_name(template)

            steps.append({
                "intent": "file_manager",
                "data": {
                    "action": "create_folder",
                    "folder_name": folder_name,
                    "location": location,
                    "open_with": "none"
                }
            })

        if file_requested or file_names:
            if not file_names:
                file_names = self.default_files_for_template(template) or ["nuevo_archivo.txt"]

            for file_name in file_names:
                steps.append({
                    "intent": "file_manager",
                    "data": {
                        "action": "create_file",
                        "file_name": file_name,
                        "folder_name": folder_name if folder_requested else "",
                        "location": location,
                        "template": bool(template),
                        "project_type": template or ""
                    }
                })

        if open_with in ["vscode", "explorer"] and folder_requested:
            steps.append({
                "intent": "file_manager",
                "data": {
                    "action": "open_folder",
                    "folder_name": folder_name,
                    "location": location,
                    "open_with": open_with
                }
            })

        if not steps:
            return None

        return {
            "type": "steps",
            "steps": steps,
            "description": "tarea compuesta de archivos"
        }

    # ------------------------------------------------------------------
    # Nuevo: creador de interfaces gráficas
    # ------------------------------------------------------------------
    def plan_gui_task(self, original, text):
        gui_words = [
            "interfaz", "interfaz grafica", "interfaz gráfica", "ventana",
            "jframe", "swing", "tkinter", "pantalla", "panel visual",
            "menu visual", "menú visual", "botones", "formulario visual",
            "dashboard"
        ]
        action_words = [
            "crea", "crear", "haz", "hacer", "genera", "generar",
            "agrega", "añade", "anade", "pon", "ponle", "mete", "modifica"
        ]

        wants_gui = any(word in text for word in gui_words)
        has_action = any(word in text for word in action_words)

        # Caso especial: "el menú lo quiero en una interfaz"
        if "menu" in text and any(word in text for word in ["interfaz", "ventana", "visual", "grafica", "gráfica"]):
            wants_gui = True
            has_action = True

        if not (wants_gui and has_action):
            return None

        project_name = self.extract_existing_project_name(original)

        # Si no detecta proyecto existente, intentamos tomar un nombre natural.
        if not project_name:
            project_name = self.extract_gui_project_name(original)

        gui_type = self.detect_gui_type(text)
        location = self.extract_location(text)
        open_with = self.extract_open_with(text)
        if open_with == "none":
            open_with = "vscode"

        return {
            "type": "steps",
            "steps": [
                {
                    "intent": "gui_builder",
                    "data": {
                        "action": "create_gui",
                        "project_name": project_name,
                        "gui_type": gui_type,
                        "location": location,
                        "instruction": original,
                        "open_with": open_with
                    }
                }
            ],
            "description": "crear interfaz gráfica"
        }

    def detect_gui_type(self, text):
        if any(word in text for word in ["java", "swing", "jframe"]):
            return "java_swing"
        if any(word in text for word in ["web", "html", "css", "javascript", "pagina", "página"]):
            return "web"
        if any(word in text for word in ["python", "tkinter"]):
            return "python_tkinter"
        return "auto"

    def extract_gui_project_name(self, original_text):
        text = self.normalize(original_text)

        quoted = re.search(r'["“”\']([^"“”\']+)["“”\']', original_text)
        if quoted:
            return self.clean_name(quoted.group(1))

        patterns = [
            r"para\s+(?:el\s+)?proyecto\s+(.+?)(?=\s+y\s+|\s+con\s+|\s+que\s+|,|$)",
            r"en\s+(?:el\s+)?proyecto\s+(.+?)(?=\s+(?:crea|crear|haz|hacer|genera|agrega|añade|anade|pon|ponle|modifica)\s+|\s+y\s+|\s+con\s+|,|$)",
            r"interfaz\s+(?:para|de)\s+(.+?)(?=\s+y\s+|\s+con\s+|,|$)",
            r"ventana\s+(?:para|de)\s+(.+?)(?=\s+y\s+|\s+con\s+|,|$)",
            r"proyecto\s+(?:llamado|llamada|de)?\s+(.+?)(?=\s+(?:crea|crear|haz|hacer|genera|agrega|añade|anade|pon|ponle|modifica)\s+|\s+y\s+|\s+con\s+|\s+para\s+|,|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                name = self.clean_name(match.group(1))
                if name and name not in ["java", "python", "web", "swing", "tkinter", "grafica", "gráfica"]:
                    return name

        if "calculadora" in text:
            return "calculadora"
        if "login" in text or "inicio de sesion" in text:
            return "login"
        if "restaurante" in text:
            return "restaurante"
        if "riego" in text or "humedad" in text:
            return "riego smart"

        return "interfaz jarvis"

    # ------------------------------------------------------------------
    # Nuevo: editor de archivos inteligentes
    # ------------------------------------------------------------------
    def plan_editor_task(self, original, text):
        file_names = self.extract_file_names(original)
        location = self.extract_location(text)
        open_with = self.extract_open_with(text)
        project_name = self.extract_existing_project_name(original)
        class_name = self.extract_class_name(original)

        mentions_file = "archivo" in text or bool(file_names)
        mentions_project = "proyecto" in text or project_name != ""
        mentions_code = any(word in text for word in ["codigo", "código", "clase", "html", "css", "javascript", "java", "python", "arduino"])

        # Evita chocar con creación de proyectos nuevos.
        # Excepción: "crea una clase en el proyecto X" sí es edición de proyecto existente.
        if self.looks_like_project_task(text) and "clase" not in text:
            return None

        if not (mentions_file or mentions_project or mentions_code):
            return None

        steps = []

        # Buscar archivo/proyecto.
        if any(word in text for word in ["busca", "buscar", "encuentra", "encontrar", "localiza", "ubica"]):
            if mentions_project and not file_names:
                return self.single_editor_step(
                    "search_file",
                    {
                        "action": "search_project",
                        "project_name": project_name or self.extract_query_after_search(original),
                        "location": location,
                        "kind": "folder"
                    },
                    "búsqueda de proyecto"
                )

            return self.single_editor_step(
                "search_file",
                {
                    "action": "search_file",
                    "file_name": file_names[0] if file_names else self.extract_query_after_search(original),
                    "location": location,
                    "kind": "file"
                },
                "búsqueda de archivo"
            )

        # Abrir proyecto/archivo existente.
        if any(word in text for word in ["abre", "abrir", "abrelo", "abrela", "ábrelo", "ábrela"]):
            if mentions_project and not file_names and not any(word in text for word in ["agrega", "añade", "anade", "modifica", "edita", "cambia", "ponle"]):
                return self.single_editor_step(
                    "file_editor",
                    {
                        "action": "open_project",
                        "project_name": project_name or self.extract_query_after_open(original),
                        "location": location,
                        "open_with": open_with if open_with != "none" else "vscode"
                    },
                    "abrir proyecto"
                )

            if file_names and not any(word in text for word in ["agrega", "añade", "anade", "modifica", "edita", "cambia", "ponle"]):
                return self.single_editor_step(
                    "file_editor",
                    {
                        "action": "open_file",
                        "file_name": file_names[0],
                        "project_name": project_name,
                        "location": location,
                        "open_with": open_with if open_with != "none" else "vscode"
                    },
                    "abrir archivo"
                )

        # Leer o explicar archivo.
        if any(word in text for word in ["explica", "explicame", "explícame", "que hace", "qué hace", "revisa", "analiza"]):
            return self.single_editor_step(
                "file_editor",
                {
                    "action": "explain_file",
                    "file_name": file_names[0] if file_names else "",
                    "project_name": project_name,
                    "location": location
                },
                "explicar archivo"
            )

        if any(word in text for word in ["lee", "leer", "muestra", "ver"]):
            return self.single_editor_step(
                "file_editor",
                {
                    "action": "read_file",
                    "file_name": file_names[0] if file_names else "",
                    "project_name": project_name,
                    "location": location
                },
                "leer archivo"
            )

        # Crear una clase dentro de un proyecto.
        if class_name:
            return self.single_editor_step(
                "file_editor",
                {
                    "action": "create_class",
                    "class_name": class_name,
                    "project_name": project_name,
                    "location": location,
                    "instruction": original,
                    "open_with": open_with
                },
                "crear clase"
            )

        # Escribir/agregar texto a un archivo específico.
        if any(word in text for word in ["escribe", "agrega", "añade", "anade", "pon"]):
            content = self.extract_content_to_write(original)
            if content and file_names:
                return self.single_editor_step(
                    "file_editor",
                    {
                        "action": "append_to_file",
                        "file_name": file_names[0],
                        "project_name": project_name,
                        "location": location,
                        "content": content
                    },
                    "agregar texto al archivo"
                )

        # Modificar proyecto o archivo existente.
        if any(word in text for word in ["modifica", "modificar", "edita", "editar", "agrega", "añade", "anade", "ponle", "pon", "cambia", "cambiar", "corrige", "arregla", "mejora"]):
            return self.single_editor_step(
                "file_editor",
                {
                    "action": "add_feature",
                    "file_name": file_names[0] if file_names else "",
                    "project_name": project_name,
                    "location": location,
                    "instruction": original,
                    "open_with": open_with
                },
                "modificar archivo o proyecto"
            )

        return None

    def single_editor_step(self, intent, data, description):
        return {
            "type": "steps",
            "steps": [
                {
                    "intent": intent,
                    "data": data
                }
            ],
            "description": description
        }

    # ------------------------------------------------------------------
    # Detectores generales
    # ------------------------------------------------------------------
    def looks_like_file_task(self, text):
        has_create = any(word in text for word in self.CREATE_WORDS)
        has_file_word = any(word in text for word in ["carpeta", "archivo", "archivos", "proyecto", "pagina web", "página web"])
        return has_create and has_file_word

    def looks_like_project_task(self, text):
        has_create = any(word in text for word in self.CREATE_WORDS)
        asks_project = "proyecto" in text or "pagina web" in text or "página web" in text

        # Si solo dijo "carpeta llamada proyecto", no lo tomamos como proyecto completo.
        if "carpeta" in text and "proyecto" in text and not any(word in text for word in ["python", "java", "arduino", "web", "html", "login", "calculadora", "sensor", "restaurante"]):
            return False

        return has_create and asks_project

    def looks_compound(self, text):
        return any(word in text for word in self.COMPOUND_WORDS)

    def normalize(self, text):
        text = text.lower().strip()
        text = "".join(
            char for char in unicodedata.normalize("NFD", text)
            if unicodedata.category(char) != "Mn"
        )
        text = re.sub(r"\s+", " ", text)
        return text

    def extract_location(self, text):
        if "descargas" in text or "downloads" in text:
            return "downloads"
        if "escritorio" in text or "desktop" in text:
            return "desktop"
        if "documentos" in text or "documents" in text or "mis documentos" in text:
            return "documents"
        if "carpeta actual" in text or "directorio actual" in text:
            return "actual"
        return "documents"

    def extract_open_with(self, text):
        if any(word in text for word in ["visual studio code", "vscode", "vs code", "visual", "code"]):
            return "vscode"
        if any(word in text for word in ["abre", "abrir", "abrela", "abrelo", "abrirla", "abrirlo"]):
            return "explorer"
        return "none"

    # ------------------------------------------------------------------
    # Extracción de nombres
    # ------------------------------------------------------------------
    def extract_project_name(self, original_text, template=""):
        text = original_text.strip()
        normalized = self.normalize(text)

        quoted = re.search(
            r'(?:proyecto|pagina\s+web|página\s+web)\s+(?:de\s+)?(?:python|java|arduino|web|html)?\s*(?:llamado|llamada|que\s+se\s+llame|que\s+diga|con\s+nombre\s+de)?\s*["“”\']([^"“”\']+)["“”\']',
            text,
            re.IGNORECASE
        )
        if quoted:
            return self.clean_name(quoted.group(1))

        first_quoted = re.search(r'["“”\']([^"“”\']+)["“”\']', text)
        if first_quoted:
            return self.clean_name(first_quoted.group(1))

        patterns = [
            r"(?:proyecto|pagina\s+web|página\s+web)\s+(?:de\s+)?(?:python|java|arduino|web|html)?\s*(?:llamado|llamada|que\s+se\s+llame|que\s+diga|con\s+nombre\s+de)\s+(.+?)(?=\s+y\s+|,|\s+con\s+(?:archivo|archivos|[a-z0-9_-]+\.)|$)",
            r"(?:proyecto|pagina\s+web|página\s+web)\s+(?:de\s+)?(?:python|java|arduino|web|html)?\s+para\s+(.+?)(?=\s+y\s+|,|\s+con\s+(?:archivo|archivos|[a-z0-9_-]+\.)|$)",
            r"(?:pagina\s+web|página\s+web)\s+de\s+(.+?)(?=\s+y\s+|,|\s+con\s+(?:archivo|archivos|[a-z0-9_-]+\.)|$)",
            r"proyecto\s+de\s+(?:python|java|arduino|web|html)\s+(.+?)(?=\s+y\s+|,|\s+con\s+(?:archivo|archivos|[a-z0-9_-]+\.)|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                name = self.clean_name(match.group(1))
                if name:
                    return name

        if "calculadora" in normalized:
            return "calculadora"
        if "login" in normalized or "inicio de sesion" in normalized:
            return "login"
        if "restaurante" in normalized:
            return "restaurante"
        if "humedad" in normalized or "riego" in normalized:
            return "riego smart"

        return self.default_folder_name(template)

    def extract_existing_project_name(self, original_text):
        text = self.normalize(original_text)

        quoted = re.search(r'proyecto\s+(?:llamado|llamada|de)?\s*["“”\']([^"“”\']+)["“”\']', original_text, re.IGNORECASE)
        if quoted:
            return self.clean_name(quoted.group(1))

        patterns = [
            r"proyecto\s+(?:llamado|llamada|que\s+se\s+llame|de)?\s+(.+?)(?=\s+(?:crea|crear|haz|hacer|genera|agrega|añade|anade|pon|ponle|modifica)\s+|\s+y\s+|\s+para\s+|\s+con\s+|,|$)",
            r"abre\s+(?:el\s+)?proyecto\s+(.+?)(?=\s+(?:crea|crear|haz|hacer|genera|agrega|añade|anade|pon|ponle|modifica)\s+|\s+y\s+|\s+para\s+|,|$)",
            r"en\s+(?:el\s+)?proyecto\s+(.+?)(?=\s+(?:crea|crear|haz|hacer|genera|agrega|añade|anade|pon|ponle|modifica)\s+|\s+y\s+|\s+para\s+|,|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = self.clean_name(match.group(1))
                if name and name not in ["java", "python", "arduino", "web"]:
                    return name

        return ""

    def extract_folder_name(self, original_text):
        text = original_text.strip()
        normalized = self.normalize(text)

        quoted = re.search(r'(?:carpeta|proyecto)\s+(?:llamada|llamado|que se llame|que diga)?\s*["“”\']([^"“”\']+)["“”\']', text, re.IGNORECASE)
        if quoted:
            return self.clean_name(quoted.group(1))

        first_quoted = re.search(r'["“”\']([^"“”\']+)["“”\']', text)
        if first_quoted and ("carpeta" in normalized or "proyecto" in normalized):
            return self.clean_name(first_quoted.group(1))

        patterns = [
            r"carpeta\s+(?:llamada|llamado|que\s+se\s+llame|que\s+diga|con\s+nombre\s+de|nombre\s+de)\s+(.+?)(?=\s+y\s+(?:(?:la|lo)\s+)?(?:dentro|adentro|crea|crear|abre|abrir|abrela|abrirla|abres)|,|\s+dentro\s|\s+adentro\s|\s+con\s+(?:un\s+archivo|los\s+archivos|archivos|[a-z0-9_-]+\.)|$)",
            r"carpeta\s+para\s+(?:mi\s+)?proyecto\s+de\s+(.+?)(?=\s+y\s+|,|\s+con\s+|$)",
            r"proyecto\s+de\s+[a-z0-9_ -]+\s+(?:llamado|llamada|que\s+se\s+llame|que\s+diga)\s+(.+?)(?=\s+y\s+|,|\s+con\s+|$)",
            r"proyecto\s+(?:llamado|llamada|que\s+se\s+llame|que\s+diga)\s+(.+?)(?=\s+y\s+|,|\s+con\s+|$)",
            r"proyecto\s+de\s+(.+?)(?=\s+y\s+|,|\s+con\s+|$)",
            r"pagina\s+web\s+(?:llamada|llamado|que\s+se\s+llame|que\s+diga)?\s*(.+?)(?=\s+y\s+|,|\s+con\s+|$)",
            r"página\s+web\s+(?:llamada|llamado|que\s+se\s+llame|que\s+diga)?\s*(.+?)(?=\s+y\s+|,|\s+con\s+|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                name = self.clean_name(match.group(1))
                if name:
                    if pattern.startswith("carpeta\\s+para") or pattern.startswith("proyecto\\s+de\\s+(.+?)"):
                        return f"proyecto {name}".strip()
                    return name

        if "pagina web" in normalized or "página web" in normalized:
            return "pagina web"

        if "proyecto" in normalized:
            template = self.detect_template(normalized)
            return self.default_folder_name(template)

        return "nueva carpeta"

    def extract_file_names(self, original_text):
        text = original_text.strip()

        ext = "|".join(self.FILE_EXTENSIONS)
        pattern = rf"(?<![\w.-])([A-Za-z0-9_\-]+\.({ext}))(?![\w.-])"
        matches = re.findall(pattern, text, flags=re.IGNORECASE)

        files = []
        for full_match, _ in matches:
            cleaned = self.clean_file_name(full_match)
            if cleaned and cleaned not in files:
                files.append(cleaned)

        quoted_items = re.findall(r"[\"“”']([^\"“”']+)[\"“”']", text)
        for item in quoted_items:
            if re.search(rf"\.({ext})$", item.strip(), flags=re.IGNORECASE):
                cleaned = self.clean_file_name(item)
                if cleaned and cleaned not in files:
                    files.append(cleaned)

        if not files:
            named_file = re.search(
                r"archivo\s+(?:llamado|llamada|que\s+se\s+llame|que\s+diga|con\s+nombre\s+de)\s+(.+?)(?=\s+y\s+|,|\s+en\s+visual|$)",
                self.normalize(text),
                flags=re.IGNORECASE
            )
            if named_file:
                file_name = self.clean_file_name(named_file.group(1))
                if file_name and "." not in file_name:
                    file_name += ".txt"
                files.append(file_name)

        return files

    def extract_class_name(self, original_text):
        patterns = [
            r"clase\s+(?:llamada|llamado|que\s+se\s+llame|con\s+nombre\s+de)\s+([A-Za-z_][A-Za-z0-9_]*)",
            r"clase\s+([A-Za-z_][A-Za-z0-9_]*)"
        ]
        for pattern in patterns:
            match = re.search(pattern, original_text, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return ""

    def extract_content_to_write(self, original_text):
        text = original_text.strip()
        patterns = [
            r"(?:escribe|agrega|añade|anade|pon)\s+(.+?)\s+(?:en|al|a)\s+(?:el\s+)?archivo\s+[A-Za-z0-9_\-]+\.[A-Za-z0-9]+",
            r"(?:escribe|agrega|añade|anade|pon)\s+[\"“”']([^\"“”']+)[\"“”']"
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def extract_query_after_search(self, original_text):
        text = self.normalize(original_text)
        text = re.sub(r"^(busca|buscar|encuentra|encontrar|localiza|ubica)\s+", "", text).strip()
        text = re.sub(r"^(el|la|un|una|archivo|proyecto)\s+", "", text).strip()
        return self.clean_name(text)

    def extract_query_after_open(self, original_text):
        text = self.normalize(original_text)
        text = re.sub(r"^(abre|abrir|abrelo|abrela)\s+", "", text).strip()
        text = re.sub(r"^(el|la|un|una|archivo|proyecto)\s+", "", text).strip()
        return self.clean_name(text)

    # ------------------------------------------------------------------
    # Limpieza y plantillas
    # ------------------------------------------------------------------
    def clean_name(self, name):
        name = str(name).strip()

        stop_patterns = [
            r"\s+y\s+(?:(?:la|lo)\s+)?(?:dentro|adentro|crea|crear|abre|abrir|abrela|abrirla|abrelo|abrirlo|abres|agrega|añade|anade|modifica|edita).*$",
            r"\s+con\s+(?:un\s+archivo|los\s+archivos|archivos|[a-z0-9_-]+\.).*$",
            r"\s+dentro\s+.*$",
            r"\s+adentro\s+.*$",
            r"\s+en\s+(?:visual\s+studio\s+code|visual|vscode|vs\s*code|code).*$",
            r"\s+en\s+(?:documentos|mis\s+documentos|escritorio|descargas).*$",
        ]

        for pattern in stop_patterns:
            name = re.sub(pattern, "", name, flags=re.IGNORECASE).strip()

        name = re.sub(r"^(?:una|un|el|la|mi|mis|proyecto|archivo|carpeta)\s+", "", name, flags=re.IGNORECASE).strip()
        name = name.strip(" .\"“”'")
        name = re.sub(r'[<>:"/\\|?*]', "", name)
        name = re.sub(r"\s+", " ", name)
        return name[:80]

    def clean_file_name(self, file_name):
        file_name = str(file_name).strip()
        file_name = re.sub(r"^(?:archivo|archivos|llamado|llamada|y|e|con)\s+", "", file_name, flags=re.IGNORECASE).strip()
        file_name = file_name.strip(" .\"“”'")
        file_name = re.sub(r'[<>:"/\\|?*]', "", file_name)
        file_name = re.sub(r"\s+", "_", file_name)
        return file_name[:100]

    def detect_template(self, text):
        if "pagina web" in text or "página web" in text or "html" in text:
            return "web"
        if "python" in text or "main.py" in text:
            return "python"
        if "java" in text or "main.java" in text:
            return "java"
        if "arduino" in text or ".ino" in text:
            return "arduino"
        return ""

    def default_folder_name(self, template):
        defaults = {
            "python": "proyecto python",
            "java": "proyecto java",
            "web": "pagina web",
            "arduino": "proyecto arduino"
        }
        return defaults.get(template, "nuevo proyecto")

    def default_files_for_template(self, template):
        defaults = {
            "python": ["main.py", "README.md"],
            "java": ["Main.java", "README.md"],
            "web": ["index.html", "style.css", "script.js"],
            "arduino": ["main.ino", "README.md"]
        }
        return defaults.get(template, [])

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from skills.launcher import abrir_en_vscode


class CodeEditorSkill:
    """
    Habilidad para buscar, leer, explicar y modificar archivos de código.

    Acciones principales:
    - search_file: buscar un archivo o proyecto
    - read_file: leer archivo
    - explain_file: explicar de forma simple qué contiene un archivo
    - append_to_file / overwrite_file / replace_text: editar texto
    - add_feature / modify_project: agregar mejoras básicas a proyectos existentes
    - create_class: crear una clase Java/Python en un proyecto
    - open_file / open_project: abrir en VS Code o explorador
    """

    TEXT_EXTENSIONS = {
        ".py", ".java", ".html", ".css", ".js", ".txt", ".md", ".json",
        ".xml", ".csv", ".cpp", ".c", ".cs", ".kt", ".php", ".sql",
        ".bat", ".sh", ".ino", ".yml", ".yaml"
    }

    MAX_READ_BYTES = 1_000_000

    def __init__(self):
        self.last_file_path = None
        self.last_project_path = None

    def run(self, data):
        action = str(data.get("action", "search_file")).lower().strip()

        if action in ["search_file", "find_file", "buscar_archivo", "search_project", "find_project"]:
            return self.search_file(data)

        if action in ["read_file", "leer_archivo"]:
            return self.read_file(data)

        if action in ["explain_file", "explain_code", "explicar_archivo", "que_hace"]:
            return self.explain_file(data)

        if action in ["append_to_file", "append", "agregar_texto"]:
            return self.write_file(data, mode="append")

        if action in ["overwrite_file", "overwrite", "sobrescribir_archivo"]:
            return self.write_file(data, mode="overwrite")

        if action in ["replace_text", "replace", "reemplazar_texto"]:
            return self.replace_text(data)

        if action in ["add_feature", "modify_file", "modify_project", "edit_file", "edit_project"]:
            return self.add_feature(data)

        if action in ["create_class", "crear_clase"]:
            return self.create_class(data)

        if action in ["open_file", "abrir_archivo"]:
            return self.open_file(data)

        if action in ["open_project", "abrir_proyecto"]:
            return self.open_project(data)

        return "No entendí qué quieres hacer con el editor de archivos."

    # ------------------------------------------------------------------
    # Búsqueda y resolución de rutas
    # ------------------------------------------------------------------
    def search_file(self, data):
        name = self.clean_name(
            data.get("file_name")
            or data.get("project_name")
            or data.get("name")
            or data.get("query")
            or ""
        )
        location = data.get("location", "")
        kind = data.get("kind", "file")

        if not name:
            return "Dime qué archivo o proyecto quieres buscar."

        matches = self.find_matches(name, location=location, kind=kind, limit=8)

        if not matches:
            return f"No encontré nada llamado {name} en Documentos, Escritorio o Descargas."

        first = matches[0]
        if first.is_dir():
            self.last_project_path = first
        else:
            self.last_file_path = first
            self.last_project_path = first.parent

        lines = []
        for index, path in enumerate(matches, start=1):
            lines.append(f"{index}. {path}")

        return "Encontré esto:\n" + "\n".join(lines)

    def resolve_file_path(self, data, must_exist=True):
        if data.get("path"):
            path = Path(str(data.get("path"))).expanduser()
            if path.is_dir() and data.get("file_name"):
                path = path / self.clean_file_name(data.get("file_name"))
            return path

        if data.get("use_last_file") and self.last_file_path:
            return self.last_file_path

        file_name = self.clean_file_name(data.get("file_name") or data.get("name") or "")
        project_name = self.clean_name(data.get("project_name") or data.get("folder_name") or data.get("folder") or "")
        location = data.get("location", "")

        if project_name:
            project_path = self.resolve_project_path({"project_name": project_name, "location": location}, must_exist=False)
            if file_name:
                return project_path / file_name

        if file_name:
            matches = self.find_matches(file_name, location=location, kind="file", limit=1)
            if matches:
                self.last_file_path = matches[0]
                self.last_project_path = matches[0].parent
                return matches[0]

            # Si no existe, lo creamos en la carpeta del último proyecto o Documentos.
            if not must_exist:
                if self.last_project_path:
                    return self.last_project_path / file_name
                return self.resolve_location(location or "documents") / file_name

        if self.last_file_path:
            return self.last_file_path

        return None

    def resolve_project_path(self, data, must_exist=True):
        if data.get("project_path") or data.get("path"):
            path = Path(str(data.get("project_path") or data.get("path"))).expanduser()
            return path

        if data.get("use_last_project") and self.last_project_path:
            return self.last_project_path

        project_name = self.clean_name(data.get("project_name") or data.get("folder_name") or data.get("name") or "")
        location = data.get("location", "")

        if project_name:
            matches = self.find_matches(project_name, location=location, kind="folder", limit=1)
            if matches:
                self.last_project_path = matches[0]
                return matches[0]

            if not must_exist:
                return self.resolve_location(location or "documents") / project_name

        if self.last_project_path:
            return self.last_project_path

        return None

    def find_matches(self, name, location="", kind="file", limit=8):
        target = self.normalize_for_search(name)
        if not target:
            return []

        search_roots = self.search_roots(location)
        matches = []

        for root in search_roots:
            if not root.exists():
                continue

            try:
                for path in root.rglob("*"):
                    if len(matches) >= limit:
                        return matches

                    if self.should_skip_path(path):
                        continue

                    if kind == "file" and not path.is_file():
                        continue
                    if kind in ["folder", "project"] and not path.is_dir():
                        continue

                    path_name = self.normalize_for_search(path.name)
                    stem_name = self.normalize_for_search(path.stem)

                    if target == path_name or target == stem_name or target in path_name:
                        matches.append(path)
            except PermissionError:
                continue
            except OSError:
                continue

        return matches

    def search_roots(self, location=""):
        if location:
            return [self.resolve_location(location)]

        home = Path.home()
        roots = [
            home / "Documents",
            home / "Desktop",
            home / "Downloads",
            Path.cwd()
        ]

        # Soporte para equipos con OneDrive.
        for one_drive_name in ["OneDrive", "OneDrive - Personal"]:
            one_drive = home / one_drive_name
            roots.extend([
                one_drive / "Documents",
                one_drive / "Desktop",
                one_drive / "Downloads"
            ])

        unique_roots = []
        for root in roots:
            if root not in unique_roots and root.exists():
                unique_roots.append(root)

        return unique_roots or [home]

    def should_skip_path(self, path):
        skip_names = {
            ".git", "node_modules", "venv", ".venv", "__pycache__", ".idea",
            ".vscode", "dist", "build", "target", ".gradle"
        }
        return any(part in skip_names for part in path.parts)

    # ------------------------------------------------------------------
    # Lectura y explicación
    # ------------------------------------------------------------------
    def read_file(self, data):
        file_path = self.resolve_file_path(data, must_exist=True)

        if not file_path or not file_path.exists():
            return "No encontré el archivo que quieres leer."

        if not self.is_text_file(file_path):
            return f"El archivo {file_path.name} no parece ser de texto o código."

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as error:
            return f"No pude leer {file_path.name}. Error: {error}"

        self.last_file_path = file_path
        self.last_project_path = file_path.parent

        preview = content[:1800]
        if len(content) > 1800:
            preview += "\n..."

        if not preview.strip():
            preview = "El archivo está vacío."

        return f"Contenido de {file_path.name}:\n{preview}"

    def explain_file(self, data):
        file_path = self.resolve_file_path(data, must_exist=True)

        if not file_path or not file_path.exists():
            return "No encontré el archivo que quieres que explique."

        if not self.is_text_file(file_path):
            return f"El archivo {file_path.name} no parece ser de texto o código."

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as error:
            return f"No pude leer {file_path.name}. Error: {error}"

        self.last_file_path = file_path
        self.last_project_path = file_path.parent

        return self.simple_explanation(file_path, content)

    def simple_explanation(self, file_path, content):
        ext = file_path.suffix.lower()
        lines = content.splitlines()
        non_empty = [line for line in lines if line.strip()]

        if not non_empty:
            return f"{file_path.name} está vacío."

        if ext == ".py":
            functions = re.findall(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", content, re.MULTILINE)
            classes = re.findall(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)", content, re.MULTILINE)
            parts = [f"{file_path.name} es un archivo de Python con {len(lines)} líneas."]
            if classes:
                parts.append("Clases: " + ", ".join(classes[:8]) + ".")
            if functions:
                parts.append("Funciones: " + ", ".join(functions[:10]) + ".")
            if "if __name__" in content:
                parts.append("También tiene un punto de entrada principal para ejecutarse directamente.")
            return " ".join(parts)

        if ext == ".java":
            classes = re.findall(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", content)
            methods = re.findall(r"\b(?:public|private|protected)?\s*(?:static\s+)?[A-Za-z0-9_<>,\[\]]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", content)
            parts = [f"{file_path.name} es un archivo Java con {len(lines)} líneas."]
            if classes:
                parts.append("Clases: " + ", ".join(classes[:8]) + ".")
            if methods:
                parts.append("Métodos detectados: " + ", ".join(methods[:10]) + ".")
            if "public static void main" in content:
                parts.append("Contiene un método main, así que puede ejecutarse como programa principal.")
            return " ".join(parts)

        if ext == ".html":
            title = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
            forms = len(re.findall(r"<form\b", content, re.IGNORECASE))
            scripts = re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", content, re.IGNORECASE)
            css = re.findall(r"<link[^>]+href=[\"']([^\"']+)[\"']", content, re.IGNORECASE)
            parts = [f"{file_path.name} es una página HTML con {len(lines)} líneas."]
            if title:
                parts.append(f"Título: {title.group(1).strip()}.")
            if css:
                parts.append("Carga CSS: " + ", ".join(css[:5]) + ".")
            if scripts:
                parts.append("Carga JavaScript: " + ", ".join(scripts[:5]) + ".")
            if forms:
                parts.append(f"Tiene {forms} formulario(s).")
            return " ".join(parts)

        if ext == ".css":
            selectors = re.findall(r"(^|\n)\s*([^{}\n]+)\s*\{", content)
            selector_names = [item[1].strip() for item in selectors][:10]
            parts = [f"{file_path.name} es una hoja de estilos CSS con {len(lines)} líneas."]
            if selector_names:
                parts.append("Selectores principales: " + ", ".join(selector_names) + ".")
            return " ".join(parts)

        if ext == ".js":
            functions = re.findall(r"function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", content)
            listeners = len(re.findall(r"addEventListener", content))
            parts = [f"{file_path.name} es un archivo JavaScript con {len(lines)} líneas."]
            if functions:
                parts.append("Funciones: " + ", ".join(functions[:10]) + ".")
            if listeners:
                parts.append(f"Tiene {listeners} listener(s) de eventos.")
            return " ".join(parts)

        return f"{file_path.name} es un archivo de texto/código con {len(lines)} líneas. Las primeras líneas indican que trata sobre: {self.first_meaningful_line(content)}"

    # ------------------------------------------------------------------
    # Escritura y modificación
    # ------------------------------------------------------------------
    def write_file(self, data, mode="append"):
        file_path = self.resolve_file_path(data, must_exist=False)
        content = data.get("content") or data.get("text") or ""

        if not file_path:
            return "Dime en qué archivo quieres escribir."

        if not content.strip():
            return "Dime qué texto quieres escribir en el archivo."

        if not self.is_text_file(file_path):
            return f"No voy a modificar {file_path.name} porque no parece ser archivo de texto o código."

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if file_path.exists():
                self.backup_file(file_path)

            if mode == "overwrite":
                file_path.write_text(content, encoding="utf-8")
            else:
                with file_path.open("a", encoding="utf-8") as file:
                    if file_path.exists() and file_path.stat().st_size > 0:
                        file.write("\n")
                    file.write(content)
                    if not content.endswith("\n"):
                        file.write("\n")

            self.last_file_path = file_path
            self.last_project_path = file_path.parent
            return f"Listo, escribí en {file_path.name}. Dejé copia de seguridad si el archivo ya existía."

        except Exception as error:
            return f"No pude escribir en {file_path.name}. Error: {error}"

    def replace_text(self, data):
        file_path = self.resolve_file_path(data, must_exist=True)
        find_text = data.get("find") or data.get("old_text") or ""
        replace_with = data.get("replace") or data.get("new_text") or ""

        if not file_path or not file_path.exists():
            return "No encontré el archivo que quieres modificar."

        if not find_text:
            return "Dime qué texto quieres reemplazar."

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            if find_text not in content:
                return f"No encontré ese texto dentro de {file_path.name}."

            self.backup_file(file_path)
            file_path.write_text(content.replace(find_text, replace_with), encoding="utf-8")
            self.last_file_path = file_path
            self.last_project_path = file_path.parent
            return f"Listo, reemplacé el texto en {file_path.name} e hice una copia de seguridad."
        except Exception as error:
            return f"No pude reemplazar el texto. Error: {error}"

    def add_feature(self, data):
        instruction = data.get("instruction") or data.get("description") or data.get("original_text") or ""
        normalized = self.normalize(instruction)
        file_path = self.resolve_file_path(data, must_exist=True)
        project_path = self.resolve_project_path(data, must_exist=True)

        # Si el usuario pidió una clase, la creamos aunque no haya archivo específico.
        class_name = data.get("class_name") or self.extract_class_name(instruction)
        if class_name:
            data = dict(data)
            data["class_name"] = class_name
            return self.create_class(data)

        # Si no se especificó archivo, inferimos el mejor archivo del proyecto.
        if not file_path and project_path:
            file_path = self.infer_target_file(project_path, normalized)

        if not file_path or not file_path.exists():
            return "No encontré el archivo o proyecto que quieres modificar. Primero dime el nombre exacto o búscalo con Jarvis."

        if not self.is_text_file(file_path):
            return f"No voy a modificar {file_path.name} porque no parece ser archivo de texto o código."

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            new_content, message = self.apply_feature(file_path, content, normalized, instruction)

            if new_content == content:
                return message

            self.backup_file(file_path)
            file_path.write_text(new_content, encoding="utf-8")
            self.last_file_path = file_path
            self.last_project_path = file_path.parent

            open_message = ""
            open_with = data.get("open_with", "")
            if open_with in ["vscode", "visual", "visual studio code", "code"]:
                open_message = " " + self.open_path_in_vscode(file_path)
            elif open_with in ["explorer", "explorador", "file_explorer"]:
                open_message = " " + self.open_in_explorer(file_path.parent)

            return f"Listo, modifiqué {file_path.name}: {message} Hice una copia de seguridad.{open_message}"

        except Exception as error:
            return f"No pude modificar {file_path.name}. Error: {error}"

    def apply_feature(self, file_path, content, normalized_instruction, original_instruction):
        ext = file_path.suffix.lower()

        if ext == ".py":
            if "menu" in normalized_instruction or "menú" in original_instruction.lower():
                return self.python_menu_template(), "agregué un menú básico en Python."

            snippet = (
                "\n\n# --- Código agregado por Jarvis ---\n"
                f"# Instrucción: {original_instruction}\n"
                "def nueva_funcion():\n"
                "    pass\n"
            )
            return content.rstrip() + snippet + "\n", "agregué una sección nueva para que la completes."

        if ext == ".java":
            if "menu" in normalized_instruction or "menú" in original_instruction.lower():
                return self.java_menu_template(), "agregué un menú básico en Java."

            snippet = (
                "\n\n// --- Código agregado por Jarvis ---\n"
                f"// Instrucción: {original_instruction}\n"
            )
            return content.rstrip() + snippet + "\n", "agregué una sección comentada para continuar la mejora."

        if ext == ".html":
            if "login" in normalized_instruction or "formulario" in normalized_instruction or "inicio de sesion" in normalized_instruction:
                return self.add_login_to_html(content), "agregué un formulario de login al HTML."

            snippet = (
                "\n    <section class=\"jarvis-section\">\n"
                "        <h2>Sección agregada por Jarvis</h2>\n"
                f"        <p>{self.escape_html(original_instruction)}</p>\n"
                "    </section>\n"
            )
            if "</body>" in content.lower():
                return re.sub(r"</body>", snippet + "</body>", content, flags=re.IGNORECASE), "agregué una sección nueva al HTML."
            return content.rstrip() + snippet + "\n", "agregué una sección nueva al HTML."

        if ext == ".css":
            if "color" in normalized_instruction or "colores" in normalized_instruction or "tema" in normalized_instruction:
                return content.rstrip() + "\n\n" + self.css_color_theme(), "agregué un tema de colores al CSS."
            return content.rstrip() + "\n\n" + self.css_basic_section(), "agregué estilos básicos nuevos."

        if ext == ".js":
            if "login" in normalized_instruction or "formulario" in normalized_instruction:
                return content.rstrip() + "\n\n" + self.js_login_validation(), "agregué validación básica de login en JavaScript."
            return content.rstrip() + "\n\nconsole.log('Mejora agregada por Jarvis');\n", "agregué una línea de prueba en JavaScript."

        if ext == ".ino":
            snippet = (
                "\n\n// --- Código agregado por Jarvis ---\n"
                f"// Instrucción: {original_instruction}\n"
            )
            return content.rstrip() + snippet + "\n", "agregué una sección comentada al archivo Arduino."

        return content.rstrip() + f"\n\nAgregado por Jarvis: {original_instruction}\n", "agregué el texto solicitado."

    def create_class(self, data):
        instruction = data.get("instruction") or data.get("description") or data.get("original_text") or ""
        class_name = self.clean_class_name(data.get("class_name") or self.extract_class_name(instruction) or "Usuario")
        project_path = self.resolve_project_path(data, must_exist=True)

        if not project_path:
            # Como respaldo, usamos la carpeta del último archivo.
            if self.last_project_path:
                project_path = self.last_project_path
            else:
                return "No encontré el proyecto donde quieres crear la clase."

        language = self.detect_project_language(project_path, instruction)
        extension = ".java" if language == "java" else ".py"
        file_path = project_path / f"{class_name}{extension}"

        try:
            if file_path.exists():
                return f"La clase {class_name} ya existe en {file_path}."

            if language == "java":
                content = self.java_class_template(class_name)
            else:
                content = self.python_class_template(class_name)

            file_path.write_text(content, encoding="utf-8")
            self.last_file_path = file_path
            self.last_project_path = project_path

            open_with = data.get("open_with", "")
            open_message = ""
            if open_with in ["vscode", "visual", "visual studio code", "code"]:
                open_message = " " + self.open_path_in_vscode(project_path)

            return f"Listo, creé la clase {class_name} en {file_path}.{open_message}"

        except Exception as error:
            return f"No pude crear la clase {class_name}. Error: {error}"

    # ------------------------------------------------------------------
    # Apertura
    # ------------------------------------------------------------------
    def open_file(self, data):
        file_path = self.resolve_file_path(data, must_exist=True)
        if not file_path or not file_path.exists():
            return "No encontré el archivo que quieres abrir."

        self.last_file_path = file_path
        self.last_project_path = file_path.parent
        open_with = data.get("open_with", "vscode")

        if open_with in ["vscode", "visual", "visual studio code", "code"]:
            return self.open_path_in_vscode(file_path)

        return self.open_in_explorer(file_path)

    def open_project(self, data):
        project_path = self.resolve_project_path(data, must_exist=True)
        if not project_path or not project_path.exists():
            return "No encontré el proyecto que quieres abrir."

        self.last_project_path = project_path
        open_with = data.get("open_with", "vscode")

        if open_with in ["vscode", "visual", "visual studio code", "code"]:
            return self.open_path_in_vscode(project_path)

        return self.open_in_explorer(project_path)

    def open_path_in_vscode(self, path):
        if abrir_en_vscode(path):
            return "Lo abrí en Visual Studio Code."
        return self.open_in_explorer(path)

    def open_in_explorer(self, path):
        try:
            if os.name == "nt":
                os.startfile(str(path))
            else:
                subprocess.Popen(["xdg-open", str(path)])
            return "Lo abrí en el explorador."
        except Exception as error:
            return f"No pude abrirlo. Error: {error}"

    # ------------------------------------------------------------------
    # Plantillas
    # ------------------------------------------------------------------
    def python_menu_template(self):
        return (
            "def mostrar_menu():\n"
            "    print('\\n--- MENÚ ---')\n"
            "    print('1. Opción 1')\n"
            "    print('2. Opción 2')\n"
            "    print('3. Salir')\n\n"
            "def main():\n"
            "    while True:\n"
            "        mostrar_menu()\n"
            "        opcion = input('Elige una opción: ')\n\n"
            "        if opcion == '1':\n"
            "            print('Elegiste la opción 1')\n"
            "        elif opcion == '2':\n"
            "            print('Elegiste la opción 2')\n"
            "        elif opcion == '3':\n"
            "            print('Saliendo...')\n"
            "            break\n"
            "        else:\n"
            "            print('Opción no válida')\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        )

    def java_menu_template(self):
        return (
            "import java.util.Scanner;\n\n"
            "public class Main {\n"
            "    public static void main(String[] args) {\n"
            "        Scanner sc = new Scanner(System.in);\n"
            "        int opcion;\n\n"
            "        do {\n"
            "            System.out.println(\"\\n--- MENÚ ---\");\n"
            "            System.out.println(\"1. Opción 1\");\n"
            "            System.out.println(\"2. Opción 2\");\n"
            "            System.out.println(\"3. Salir\");\n"
            "            System.out.print(\"Elige una opción: \" );\n"
            "            opcion = sc.nextInt();\n\n"
            "            switch (opcion) {\n"
            "                case 1:\n"
            "                    System.out.println(\"Elegiste la opción 1\");\n"
            "                    break;\n"
            "                case 2:\n"
            "                    System.out.println(\"Elegiste la opción 2\");\n"
            "                    break;\n"
            "                case 3:\n"
            "                    System.out.println(\"Saliendo...\");\n"
            "                    break;\n"
            "                default:\n"
            "                    System.out.println(\"Opción no válida\");\n"
            "            }\n"
            "        } while (opcion != 3);\n\n"
            "        sc.close();\n"
            "    }\n"
            "}\n"
        )

    def java_class_template(self, class_name):
        return (
            f"public class {class_name} {{\n"
            "    private String nombre;\n\n"
            f"    public {class_name}() {{\n"
            "    }\n\n"
            f"    public {class_name}(String nombre) {{\n"
            "        this.nombre = nombre;\n"
            "    }\n\n"
            "    public String getNombre() {\n"
            "        return nombre;\n"
            "    }\n\n"
            "    public void setNombre(String nombre) {\n"
            "        this.nombre = nombre;\n"
            "    }\n"
            "}\n"
        )

    def python_class_template(self, class_name):
        return (
            f"class {class_name}:\n"
            "    def __init__(self, nombre=''):\n"
            "        self.nombre = nombre\n\n"
            "    def __str__(self):\n"
            f"        return f'{class_name}: {{self.nombre}}'\n"
        )

    def add_login_to_html(self, content):
        login_html = (
            "\n    <main class=\"login-card\">\n"
            "        <h1>Inicio de sesión</h1>\n"
            "        <form id=\"loginForm\">\n"
            "            <label for=\"usuario\">Usuario</label>\n"
            "            <input type=\"text\" id=\"usuario\" placeholder=\"Escribe tu usuario\" required>\n"
            "            <label for=\"password\">Contraseña</label>\n"
            "            <input type=\"password\" id=\"password\" placeholder=\"Escribe tu contraseña\" required>\n"
            "            <button type=\"submit\">Entrar</button>\n"
            "        </form>\n"
            "        <p id=\"mensaje\"></p>\n"
            "    </main>\n"
        )

        if "loginForm" in content:
            return content

        if "</body>" in content.lower():
            return re.sub(r"</body>", login_html + "</body>", content, flags=re.IGNORECASE)

        return content.rstrip() + login_html + "\n"

    def css_color_theme(self):
        return (
            "/* --- Tema agregado por Jarvis --- */\n"
            ":root {\n"
            "    --color-principal: #1f6feb;\n"
            "    --color-secundario: #0d1117;\n"
            "    --color-fondo: #f5f7fb;\n"
            "}\n\n"
            "body {\n"
            "    background: var(--color-fondo);\n"
            "    color: var(--color-secundario);\n"
            "}\n\n"
            "button {\n"
            "    background: var(--color-principal);\n"
            "    color: white;\n"
            "    border: none;\n"
            "    border-radius: 8px;\n"
            "}\n"
        )

    def css_basic_section(self):
        return (
            "/* --- Estilos agregados por Jarvis --- */\n"
            ".jarvis-section {\n"
            "    max-width: 800px;\n"
            "    margin: 40px auto;\n"
            "    padding: 24px;\n"
            "    border-radius: 12px;\n"
            "    background: white;\n"
            "    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.12);\n"
            "}\n"
        )

    def js_login_validation(self):
        return (
            "// --- Validación agregada por Jarvis ---\n"
            "const loginForm = document.getElementById('loginForm');\n"
            "const mensaje = document.getElementById('mensaje');\n\n"
            "if (loginForm) {\n"
            "    loginForm.addEventListener('submit', function(event) {\n"
            "        event.preventDefault();\n"
            "        const usuario = document.getElementById('usuario').value.trim();\n"
            "        const password = document.getElementById('password').value.trim();\n\n"
            "        if (!usuario || !password) {\n"
            "            mensaje.textContent = 'Completa todos los campos.';\n"
            "            return;\n"
            "        }\n\n"
            "        mensaje.textContent = `Bienvenido, ${usuario}`;\n"
            "    });\n"
            "}\n"
        )

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def infer_target_file(self, project_path, normalized_instruction):
        candidates = []

        if "html" in normalized_instruction or "login" in normalized_instruction or "formulario" in normalized_instruction:
            candidates = ["index.html"]
        elif "css" in normalized_instruction or "color" in normalized_instruction or "colores" in normalized_instruction:
            candidates = ["style.css"]
        elif "javascript" in normalized_instruction or "js" in normalized_instruction:
            candidates = ["script.js"]
        elif "java" in normalized_instruction or "menu" in normalized_instruction:
            candidates = ["Main.java", "main.py", "index.html"]
        elif "python" in normalized_instruction or "py" in normalized_instruction:
            candidates = ["main.py"]
        else:
            candidates = ["main.py", "Main.java", "index.html", "README.md"]

        for candidate in candidates:
            path = project_path / candidate
            if path.exists():
                return path

        for path in project_path.rglob("*"):
            if path.is_file() and path.suffix.lower() in self.TEXT_EXTENSIONS:
                return path

        return None

    def detect_project_language(self, project_path, instruction=""):
        text = self.normalize(instruction)
        if "java" in text:
            return "java"
        if "python" in text:
            return "python"

        if (project_path / "Main.java").exists() or list(project_path.glob("*.java")):
            return "java"
        if (project_path / "main.py").exists() or list(project_path.glob("*.py")):
            return "python"

        return "java"

    def extract_class_name(self, text):
        patterns = [
            r"clase\s+(?:llamada|llamado|que\s+se\s+llame|con\s+nombre\s+de)\s+([A-Za-z_][A-Za-z0-9_]*)",
            r"clase\s+([A-Za-z_][A-Za-z0-9_]*)"
        ]
        for pattern in patterns:
            match = re.search(pattern, text or "", re.IGNORECASE)
            if match:
                return match.group(1)
        return ""

    def clean_class_name(self, name):
        name = re.sub(r"[^A-Za-z0-9_]", "", str(name).strip())
        if not name:
            return "Usuario"
        return name[0].upper() + name[1:]

    def clean_name(self, name):
        name = str(name).strip().strip(" .\"“”'")
        name = re.sub(r"^(?:el|la|mi|mis|proyecto|archivo|carpeta)\s+", "", name, flags=re.IGNORECASE).strip()
        name = re.sub(r'[<>:"/\\|?*]', "", name)
        name = re.sub(r"\s+", " ", name)
        return name[:100]

    def clean_file_name(self, file_name):
        file_name = str(file_name).strip().strip(" .\"“”'")
        file_name = re.sub(r"^(?:archivo|llamado|llamada|que\s+se\s+llame)\s+", "", file_name, flags=re.IGNORECASE).strip()
        file_name = re.sub(r'[<>:"/\\|?*]', "", file_name)
        return file_name[:120]

    def normalize(self, text):
        text = str(text).lower().strip()
        text = text.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
        text = re.sub(r"\s+", " ", text)
        return text

    def normalize_for_search(self, text):
        text = self.normalize(text)
        text = re.sub(r"[^a-z0-9_. -]", "", text)
        return text.strip()

    def resolve_location(self, location):
        text = self.normalize(location or "documents")
        home = Path.home()
        locations = {
            "documentos": home / "Documents",
            "documents": home / "Documents",
            "mis documentos": home / "Documents",
            "escritorio": home / "Desktop",
            "desktop": home / "Desktop",
            "descargas": home / "Downloads",
            "downloads": home / "Downloads",
            "actual": Path.cwd(),
            "carpeta actual": Path.cwd(),
            "proyecto": Path.cwd()
        }
        return locations.get(text, home / "Documents")

    def is_text_file(self, file_path):
        if file_path.suffix.lower() not in self.TEXT_EXTENSIONS:
            return False
        try:
            if file_path.exists() and file_path.stat().st_size > self.MAX_READ_BYTES:
                return False
        except OSError:
            return False
        return True

    def backup_file(self, file_path):
        if not file_path.exists():
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = file_path.with_name(f"{file_path.name}.jarvis_backup_{timestamp}")
        backup_path.write_text(file_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        return backup_path

    def first_meaningful_line(self, content):
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "//", "/*", "*")):
                return line[:140]
        return "no hay suficiente contenido para resumirlo."

    def escape_html(self, text):
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
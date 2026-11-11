import os
import re
import subprocess
from pathlib import Path

from skills.launcher import abrir_en_vscode


class FileManagerSkill:
    def __init__(self):
        self.last_folder_path = None

    def run(self, data):
        action = data.get("action", "create_folder")

        if action in ["create_folder", "create_folder_and_open", "create_folder_and_open_vscode"]:
            return self.create_folder(data)

        if action in ["create_file", "new_file"]:
            return self.create_file(data)

        if action in ["write_file", "edit_file"]:
            return self.write_file(data)

        if action in ["open_folder", "open_folder_vscode", "open_with_vscode"]:
            return self.open_folder(data)

        return "No entendí qué quieres hacer con archivos o carpetas."

    def create_folder(self, data):
        folder_name = self.clean_name(data.get("folder_name") or data.get("name") or "")
        location = data.get("location", "documents")
        open_with = data.get("open_with", "none")
        action = data.get("action", "")

        if action == "create_folder_and_open_vscode":
            open_with = "vscode"

        if not folder_name:
            return "Dime qué nombre quieres para la carpeta."

        base_path = self.resolve_location(location)
        folder_path = base_path / folder_name

        try:
            folder_path.mkdir(parents=True, exist_ok=True)
            self.last_folder_path = folder_path
        except Exception as error:
            return f"No pude crear la carpeta {folder_name}. Error: {error}"

        open_message = ""

        if open_with in ["explorer", "file_explorer", "explorador"]:
            open_message = self.open_in_explorer(folder_path)

        elif open_with in ["vscode", "visual", "visual studio code", "code"]:
            open_message = self.open_in_vscode(folder_path)

        if open_message:
            return f"Carpeta {folder_name} creada en {base_path}. {open_message}"

        return f"Carpeta {folder_name} creada en {base_path}."

    def create_file(self, data):
        file_name = self.clean_file_name(data.get("file_name") or data.get("name") or "")
        content = data.get("content")
        template = bool(data.get("template", False))
        project_type = data.get("project_type", "")

        if not file_name:
            return "Dime qué nombre quieres para el archivo."

        folder_path = self.resolve_target_folder(data)

        try:
            folder_path.mkdir(parents=True, exist_ok=True)
            file_path = folder_path / file_name

            if content is None:
                content = self.get_default_content(file_name, folder_path.name, template, project_type)

            # No borra contenido si el archivo ya existe y no se pidió sobrescribir.
            if file_path.exists() and not data.get("overwrite", False):
                return f"El archivo {file_name} ya existe en {folder_path}."

            file_path.write_text(content, encoding="utf-8")
            return f"Archivo {file_name} creado en {folder_path}."

        except Exception as error:
            return f"No pude crear el archivo {file_name}. Error: {error}"

    def write_file(self, data):
        file_name = self.clean_file_name(data.get("file_name") or data.get("name") or "")
        content = data.get("content", "")
        mode = data.get("mode", "append")

        if not file_name:
            return "Dime en qué archivo quieres escribir."

        folder_path = self.resolve_target_folder(data)
        file_path = folder_path / file_name

        try:
            folder_path.mkdir(parents=True, exist_ok=True)

            if mode == "overwrite":
                file_path.write_text(content, encoding="utf-8")
            else:
                with file_path.open("a", encoding="utf-8") as file:
                    if file_path.exists() and file_path.stat().st_size > 0:
                        file.write("\n")
                    file.write(content)

            return f"Escribí en {file_name}."

        except Exception as error:
            return f"No pude escribir en {file_name}. Error: {error}"

    def open_folder(self, data):
        location = data.get("location", "documents")
        open_with = data.get("open_with", "explorer")
        action = data.get("action", "")

        if action in ["open_folder_vscode", "open_with_vscode"]:
            open_with = "vscode"

        folder_path = self.resolve_target_folder(data, allow_last=True)

        if not folder_path.exists():
            return f"No encontré la carpeta {folder_path}."

        self.last_folder_path = folder_path

        if open_with in ["vscode", "visual", "visual studio code", "code"]:
            return self.open_in_vscode(folder_path)

        return self.open_in_explorer(folder_path)

    def resolve_target_folder(self, data, allow_last=False):
        if data.get("path"):
            return Path(data.get("path")).expanduser()

        if data.get("use_last_folder") and self.last_folder_path:
            return self.last_folder_path

        folder_name = self.clean_name(data.get("folder_name") or data.get("folder") or "")
        location = data.get("location", "documents")
        base_path = self.resolve_location(location)

        if folder_name:
            return base_path / folder_name

        if allow_last and self.last_folder_path:
            return self.last_folder_path

        return base_path

    def resolve_location(self, location):
        text = str(location).lower().strip()
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

    def clean_name(self, name):
        name = str(name).strip()

        quoted = re.search(r'["“”\']([^"“”\']+)["“”\']', name)
        if quoted:
            name = quoted.group(1).strip()

        stop_patterns = [
            r"\s+(?:y|e)\s+(?:la\s+|lo\s+)?(?:abre|abrir|abrirla|abrirlo|ábrela|abrela|abres|ábrelo|abrelo).*$",
            r"\s+para\s+(?:abrir|abrirla|abrirlo|usarla|editarla).*$",
            r"\s+(?:en|con)\s+(?:visual\s+studio\s+code|visual|vscode|vs\s*code|code).*$",
            r"\s+(?:en|dentro\s+de)\s+(?:mis\s+)?(?:documentos|documents|escritorio|desktop|descargas|downloads).*$"
        ]

        for pattern in stop_patterns:
            name = re.sub(pattern, "", name, flags=re.IGNORECASE).strip()

        name = re.sub(r"^(?:en|dentro\s+de)\s+(?:mis\s+)?(?:documentos|documents|escritorio|desktop|descargas|downloads)\s+", "", name, flags=re.IGNORECASE).strip()
        name = str(name).strip().strip(" .\"“”'")
        name = re.sub(r'[<>:"/\\|?*]', "", name)
        name = re.sub(r"\s+", " ", name)
        return name[:80]

    def clean_file_name(self, file_name):
        file_name = str(file_name).strip().strip(" .\"“”'")
        file_name = re.sub(r"^(?:archivo|archivos|llamado|llamada|y|e|con)\s+", "", file_name, flags=re.IGNORECASE).strip()
        file_name = re.sub(r'[<>:"/\\|?*]', "", file_name)
        file_name = re.sub(r"\s+", "_", file_name)
        return file_name[:100]

    def get_default_content(self, file_name, project_name, template, project_type):
        if not template:
            return ""

        lower = file_name.lower()

        if lower == "main.py":
            return (
                "def main():\n"
                "    print(\"Hola, proyecto creado por Jarvis\")\n\n"
                "if __name__ == \"__main__\":\n"
                "    main()\n"
            )

        if lower == "main.java":
            return (
                "public class Main {\n"
                "    public static void main(String[] args) {\n"
                "        System.out.println(\"Hola, proyecto creado por Jarvis\");\n"
                "    }\n"
                "}\n"
            )

        if lower == "index.html":
            return (
                "<!DOCTYPE html>\n"
                "<html lang=\"es\">\n"
                "<head>\n"
                "    <meta charset=\"UTF-8\">\n"
                "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
                f"    <title>{project_name}</title>\n"
                "    <link rel=\"stylesheet\" href=\"style.css\">\n"
                "</head>\n"
                "<body>\n"
                f"    <h1>{project_name}</h1>\n"
                "    <script src=\"script.js\"></script>\n"
                "</body>\n"
                "</html>\n"
            )

        if lower == "style.css":
            return "body {\n    font-family: Arial, sans-serif;\n}\n"

        if lower == "script.js":
            return "console.log('Proyecto creado por Jarvis');\n"

        if lower == "readme.md":
            return f"# {project_name}\n\nProyecto creado por Jarvis.\n"

        if lower.endswith(".ino"):
            return "void setup() {\n\n}\n\nvoid loop() {\n\n}\n"

        return ""

    def open_in_explorer(self, folder_path):
        try:
            if os.name == "nt":
                os.startfile(str(folder_path))
            else:
                subprocess.Popen(["xdg-open", str(folder_path)])
            return "La abrí en el explorador."
        except Exception as error:
            return f"No pude abrir la carpeta. Error: {error}"

    def open_in_vscode(self, folder_path):
        if abrir_en_vscode(folder_path):
            return "La abrí en Visual Studio Code."
        try:
            self.open_in_explorer(folder_path)
            return "No pude abrir Visual Studio Code. La abrí en el explorador."
        except Exception as error:
            return f"No pude abrir Visual Studio Code. Error: {error}"
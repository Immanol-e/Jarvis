import os
import re
import subprocess
import unicodedata
from pathlib import Path

from skills.launcher import abrir_en_vscode


class ProjectSkill:
    """
    Crea proyectos completos con estructura y archivos base.

    Soporta:
    - Python
    - Java
    - Web HTML/CSS/JS
    - Arduino
    """

    FILE_EXTENSIONS = (
        "py", "java", "txt", "html", "css", "js", "md", "json", "xml", "csv",
        "cpp", "c", "cs", "kt", "php", "sql", "bat", "sh", "ino"
    )

    def run(self, data):
        action = data.get("action", "create_project")

        if action not in ["create_project", "new_project", "crear_proyecto"]:
            return "No entendí qué proyecto quieres crear."

        return self.create_project(data)

    def create_project(self, data):
        description = data.get("description") or data.get("original_text") or ""
        project_type = self.detect_project_type(data.get("project_type", ""), description)
        project_name = self.clean_project_name(
            data.get("project_name")
            or data.get("folder_name")
            or data.get("name")
            or self.default_project_name(project_type, description)
        )
        location = data.get("location", "documents")
        open_with = data.get("open_with", "none")
        extra_files = data.get("files", []) or []
        overwrite = bool(data.get("overwrite", False))

        if not project_name:
            project_name = self.default_project_name(project_type, description)

        base_path = self.resolve_location(location)
        project_path = base_path / project_name

        try:
            project_path.mkdir(parents=True, exist_ok=True)
        except Exception as error:
            return f"No pude crear la carpeta del proyecto {project_name}. Error: {error}"

        files = self.build_project_files(project_type, project_name, description)

        for extra_file in extra_files:
            clean_extra = self.clean_file_name(extra_file)
            if clean_extra and clean_extra not in files:
                files[clean_extra] = self.default_file_content(clean_extra, project_name, project_type, description)

        created_files = []
        skipped_files = []

        for relative_path, content in files.items():
            file_path = project_path / relative_path

            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)

                if file_path.exists() and not overwrite:
                    skipped_files.append(relative_path)
                    continue

                file_path.write_text(content, encoding="utf-8")
                created_files.append(relative_path)

            except Exception as error:
                return f"Creé la carpeta del proyecto, pero no pude crear {relative_path}. Error: {error}"

        open_message = ""
        if open_with in ["vscode", "visual", "visual studio code", "code"]:
            open_message = self.open_in_vscode(project_path)
        elif open_with in ["explorer", "explorador", "file_explorer"]:
            open_message = self.open_in_explorer(project_path)

        project_label = self.project_label(project_type)
        files_text = ", ".join(created_files) if created_files else "sin archivos nuevos porque ya existían"
        response = f"Proyecto {project_label} {project_name} creado en {project_path}. Archivos: {files_text}."

        if skipped_files:
            response += f" No sobrescribí estos archivos porque ya existían: {', '.join(skipped_files)}."

        if open_message:
            response += f" {open_message}"

        return response

    def build_project_files(self, project_type, project_name, description):
        if project_type == "python":
            return self.python_project(project_name, description)

        if project_type == "java":
            return self.java_project(project_name, description)

        if project_type == "web":
            return self.web_project(project_name, description)

        if project_type == "arduino":
            return self.arduino_project(project_name, description)

        return self.generic_project(project_name, description)

    def python_project(self, project_name, description):
        text = self.normalize(description)

        if "calculadora" in text or "calculator" in text:
            main_py = (
                "def sumar(a, b):\n"
                "    return a + b\n\n"
                "def restar(a, b):\n"
                "    return a - b\n\n"
                "def multiplicar(a, b):\n"
                "    return a * b\n\n"
                "def dividir(a, b):\n"
                "    if b == 0:\n"
                "        return 'No se puede dividir entre cero'\n"
                "    return a / b\n\n"
                "def pedir_numero(mensaje):\n"
                "    while True:\n"
                "        try:\n"
                "            return float(input(mensaje))\n"
                "        except ValueError:\n"
                "            print('Escribe un número válido.')\n\n"
                "def main():\n"
                "    print('Calculadora creada por Jarvis')\n"
                "    a = pedir_numero('Primer número: ')\n"
                "    b = pedir_numero('Segundo número: ')\n\n"
                "    print(f'Suma: {sumar(a, b)}')\n"
                "    print(f'Resta: {restar(a, b)}')\n"
                "    print(f'Multiplicación: {multiplicar(a, b)}')\n"
                "    print(f'División: {dividir(a, b)}')\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        else:
            main_py = (
                "def main():\n"
                f"    print('Hola, este es el proyecto {project_name} creado por Jarvis')\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )

        return {
            "main.py": main_py,
            "README.md": self.readme(project_name, "Python", description),
            "requirements.txt": "",
            ".gitignore": "__pycache__/\n*.pyc\n.venv/\nvenv/\n.env\n"
        }

    def java_project(self, project_name, description):
        text = self.normalize(description)

        if "calculadora" in text or "calculator" in text:
            main_java = (
                "import java.util.Scanner;\n\n"
                "public class Main {\n"
                "    public static void main(String[] args) {\n"
                "        Scanner sc = new Scanner(System.in);\n\n"
                "        System.out.println(\"Calculadora creada por Jarvis\");\n"
                "        System.out.print(\"Primer número: \" );\n"
                "        double a = sc.nextDouble();\n"
                "        System.out.print(\"Segundo número: \" );\n"
                "        double b = sc.nextDouble();\n\n"
                "        System.out.println(\"Suma: \" + (a + b));\n"
                "        System.out.println(\"Resta: \" + (a - b));\n"
                "        System.out.println(\"Multiplicación: \" + (a * b));\n\n"
                "        if (b == 0) {\n"
                "            System.out.println(\"No se puede dividir entre cero\");\n"
                "        } else {\n"
                "            System.out.println(\"División: \" + (a / b));\n"
                "        }\n\n"
                "        sc.close();\n"
                "    }\n"
                "}\n"
            )
        else:
            main_java = (
                "public class Main {\n"
                "    public static void main(String[] args) {\n"
                f"        System.out.println(\"Proyecto {project_name} creado por Jarvis\");\n"
                "    }\n"
                "}\n"
            )

        return {
            "Main.java": main_java,
            "README.md": self.readme(project_name, "Java", description),
            ".gitignore": "*.class\nout/\nbuild/\n.vscode/\n"
        }

    def web_project(self, project_name, description):
        text = self.normalize(description)

        if "login" in text or "inicio de sesion" in text or "iniciar sesion" in text:
            body = (
                "    <main class=\"login-card\">\n"
                f"        <h1>{project_name}</h1>\n"
                "        <p>Inicio de sesión</p>\n"
                "        <form id=\"loginForm\">\n"
                "            <label for=\"usuario\">Usuario</label>\n"
                "            <input type=\"text\" id=\"usuario\" placeholder=\"Escribe tu usuario\" required>\n\n"
                "            <label for=\"password\">Contraseña</label>\n"
                "            <input type=\"password\" id=\"password\" placeholder=\"Escribe tu contraseña\" required>\n\n"
                "            <button type=\"submit\">Entrar</button>\n"
                "        </form>\n"
                "        <p id=\"mensaje\"></p>\n"
                "    </main>\n"
            )
            css_extra = (
                ".login-card {\n"
                "    width: 360px;\n"
                "    margin: 80px auto;\n"
                "    padding: 24px;\n"
                "    border-radius: 16px;\n"
                "    box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);\n"
                "    background: white;\n"
                "}\n\n"
                "input, button {\n"
                "    width: 100%;\n"
                "    padding: 12px;\n"
                "    margin: 8px 0 16px;\n"
                "    box-sizing: border-box;\n"
                "}\n\n"
                "button {\n"
                "    cursor: pointer;\n"
                "}\n"
            )
            js = (
                "const form = document.getElementById('loginForm');\n"
                "const mensaje = document.getElementById('mensaje');\n\n"
                "form.addEventListener('submit', function(event) {\n"
                "    event.preventDefault();\n\n"
                "    const usuario = document.getElementById('usuario').value.trim();\n"
                "    const password = document.getElementById('password').value.trim();\n\n"
                "    if (usuario === '' || password === '') {\n"
                "        mensaje.textContent = 'Completa todos los campos.';\n"
                "        return;\n"
                "    }\n\n"
                "    mensaje.textContent = `Bienvenido, ${usuario}`;\n"
                "});\n"
            )
        elif "restaurante" in text or "menu" in text or "menú" in text:
            body = (
                "    <header>\n"
                f"        <h1>{project_name}</h1>\n"
                "        <p>Menú principal</p>\n"
                "    </header>\n"
                "    <section class=\"menu\">\n"
                "        <article>\n"
                "            <h2>Platillo 1</h2>\n"
                "            <p>Descripción del platillo.</p>\n"
                "        </article>\n"
                "        <article>\n"
                "            <h2>Platillo 2</h2>\n"
                "            <p>Descripción del platillo.</p>\n"
                "        </article>\n"
                "    </section>\n"
            )
            css_extra = (
                "header {\n"
                "    text-align: center;\n"
                "    padding: 32px;\n"
                "}\n\n"
                ".menu {\n"
                "    max-width: 900px;\n"
                "    margin: auto;\n"
                "    display: grid;\n"
                "    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));\n"
                "    gap: 16px;\n"
                "}\n\n"
                "article {\n"
                "    padding: 20px;\n"
                "    border-radius: 12px;\n"
                "    background: white;\n"
                "    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.12);\n"
                "}\n"
            )
            js = "console.log('Página de restaurante creada por Jarvis');\n"
        else:
            body = (
                "    <main>\n"
                f"        <h1>{project_name}</h1>\n"
                "        <p>Proyecto web creado por Jarvis.</p>\n"
                "        <button id=\"boton\">Haz clic</button>\n"
                "    </main>\n"
            )
            css_extra = (
                "main {\n"
                "    max-width: 800px;\n"
                "    margin: 80px auto;\n"
                "    padding: 24px;\n"
                "    text-align: center;\n"
                "}\n"
            )
            js = (
                "const boton = document.getElementById('boton');\n\n"
                "boton.addEventListener('click', function() {\n"
                "    alert('Proyecto creado por Jarvis');\n"
                "});\n"
            )

        index_html = (
            "<!DOCTYPE html>\n"
            "<html lang=\"es\">\n"
            "<head>\n"
            "    <meta charset=\"UTF-8\">\n"
            "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
            f"    <title>{project_name}</title>\n"
            "    <link rel=\"stylesheet\" href=\"style.css\">\n"
            "</head>\n"
            "<body>\n"
            f"{body}"
            "    <script src=\"script.js\"></script>\n"
            "</body>\n"
            "</html>\n"
        )

        style_css = (
            "* {\n"
            "    box-sizing: border-box;\n"
            "}\n\n"
            "body {\n"
            "    margin: 0;\n"
            "    font-family: Arial, sans-serif;\n"
            "    background: #f4f4f4;\n"
            "    color: #222;\n"
            "}\n\n"
            f"{css_extra}"
        )

        return {
            "index.html": index_html,
            "style.css": style_css,
            "script.js": js,
            "README.md": self.readme(project_name, "Web", description)
        }

    def arduino_project(self, project_name, description):
        text = self.normalize(description)
        ino_name = self.clean_arduino_file_name(project_name)

        if "humedad" in text or "riego" in text or "sensor" in text:
            ino = (
                "const int sensorHumedad = A0;\n"
                "const int releBomba = 7;\n"
                "const int umbralSeco = 500;\n\n"
                "void setup() {\n"
                "  Serial.begin(9600);\n"
                "  pinMode(releBomba, OUTPUT);\n"
                "  digitalWrite(releBomba, LOW);\n"
                "}\n\n"
                "void loop() {\n"
                "  int lectura = analogRead(sensorHumedad);\n"
                "  Serial.print(\"Humedad: \" );\n"
                "  Serial.println(lectura);\n\n"
                "  if (lectura > umbralSeco) {\n"
                "    digitalWrite(releBomba, HIGH);\n"
                "  } else {\n"
                "    digitalWrite(releBomba, LOW);\n"
                "  }\n\n"
                "  delay(1000);\n"
                "}\n"
            )
        else:
            ino = (
                "const int led = 13;\n\n"
                "void setup() {\n"
                "  pinMode(led, OUTPUT);\n"
                "}\n\n"
                "void loop() {\n"
                "  digitalWrite(led, HIGH);\n"
                "  delay(1000);\n"
                "  digitalWrite(led, LOW);\n"
                "  delay(1000);\n"
                "}\n"
            )

        return {
            f"{ino_name}.ino": ino,
            "README.md": self.readme(project_name, "Arduino", description)
        }

    def generic_project(self, project_name, description):
        return {
            "README.md": self.readme(project_name, "General", description),
            "notas.txt": "Proyecto creado por Jarvis.\n"
        }

    def default_file_content(self, file_name, project_name, project_type, description):
        lower = file_name.lower()

        if lower.endswith(".py"):
            return self.python_project(project_name, description).get("main.py", "")

        if lower.endswith(".java"):
            return self.java_project(project_name, description).get("Main.java", "")

        if lower == "index.html":
            return self.web_project(project_name, description).get("index.html", "")

        if lower == "style.css":
            return self.web_project(project_name, description).get("style.css", "")

        if lower == "script.js":
            return self.web_project(project_name, description).get("script.js", "")

        if lower.endswith(".ino"):
            return next(iter(self.arduino_project(project_name, description).values()))

        if lower.endswith(".md"):
            return self.readme(project_name, project_type or "General", description)

        return ""

    def readme(self, project_name, project_type, description):
        description = description.strip() or "Proyecto generado automáticamente."
        return (
            f"# {project_name}\n\n"
            f"Tipo de proyecto: {project_type}\n\n"
            f"Descripción: {description}\n\n"
            "Creado por Jarvis.\n"
        )

    def detect_project_type(self, project_type, description):
        text = self.normalize(f"{project_type} {description}")

        if "pagina web" in text or "página web" in text or "html" in text or "css" in text or "javascript" in text or "web" in text:
            return "web"
        if "python" in text or "main.py" in text:
            return "python"
        if "java" in text or "main.java" in text:
            return "java"
        if "arduino" in text or ".ino" in text or "sensor" in text:
            return "arduino"
        return "general"

    def default_project_name(self, project_type, description):
        text = self.normalize(description)

        if "calculadora" in text:
            return "calculadora"
        if "login" in text or "inicio de sesion" in text:
            return "login"
        if "restaurante" in text:
            return "restaurante"
        if "humedad" in text or "riego" in text:
            return "riego smart"

        defaults = {
            "python": "proyecto python",
            "java": "proyecto java",
            "web": "pagina web",
            "arduino": "proyecto arduino"
        }
        return defaults.get(project_type, "nuevo proyecto")

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

    def open_in_explorer(self, folder_path):
        try:
            if os.name == "nt":
                os.startfile(str(folder_path))
            else:
                subprocess.Popen(["xdg-open", str(folder_path)])
            return "Lo abrí en el explorador."
        except Exception as error:
            return f"No pude abrir el proyecto en el explorador. Error: {error}"

    def open_in_vscode(self, folder_path):
        if abrir_en_vscode(folder_path):
            return "Lo abrí en Visual Studio Code."
        try:
            self.open_in_explorer(folder_path)
            return "No pude abrir Visual Studio Code. Lo abrí en el explorador."
        except Exception as error:
            return f"No pude abrir Visual Studio Code. Error: {error}"

    def clean_project_name(self, name):
        name = str(name).strip()
        name = re.sub(r"^(?:proyecto|pagina\s+web|página\s+web)\s+(?:de\s+)?", "", name, flags=re.IGNORECASE).strip()
        name = re.sub(r"^(?:llamado|llamada|que\s+se\s+llame|que\s+diga|para)\s+", "", name, flags=re.IGNORECASE).strip()
        name = re.sub(r"\s+y\s+(?:abre|abrir|abrelo|abrela|ábrelo|ábrela|abrirlo|abrirla).*$", "", name, flags=re.IGNORECASE).strip()
        name = re.sub(r"\s+en\s+(?:visual\s+studio\s+code|visual|vscode|vs\s*code|documentos|escritorio|descargas).*$", "", name, flags=re.IGNORECASE).strip()
        name = name.strip(" .\"“”'")
        name = re.sub(r'[<>:"/\\|?*]', "", name)
        name = re.sub(r"\s+", " ", name)
        return name[:80]

    def clean_file_name(self, file_name):
        file_name = str(file_name).strip().strip(" .\"“”'")
        file_name = re.sub(r"^(?:archivo|archivos|llamado|llamada|y|e|con)\s+", "", file_name, flags=re.IGNORECASE).strip()
        file_name = re.sub(r'[<>:"/\\|?*]', "", file_name)
        file_name = re.sub(r"\s+", "_", file_name)
        return file_name[:100]

    def clean_arduino_file_name(self, project_name):
        name = self.normalize(project_name)
        name = re.sub(r"[^a-z0-9_]+", "_", name)
        name = re.sub(r"_+", "_", name).strip("_")
        return name or "main"

    def normalize(self, text):
        text = str(text).lower().strip()
        text = "".join(
            char for char in unicodedata.normalize("NFD", text)
            if unicodedata.category(char) != "Mn"
        )
        text = re.sub(r"\s+", " ", text)
        return text

    def project_label(self, project_type):
        labels = {
            "python": "de Python",
            "java": "de Java",
            "web": "web",
            "arduino": "de Arduino",
            "general": ""
        }
        return labels.get(project_type, "").strip()
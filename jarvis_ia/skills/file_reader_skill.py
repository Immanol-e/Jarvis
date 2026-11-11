from tkinter import Tk, filedialog
from pathlib import Path

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None


class FileReaderSkill:
    def run(self, data):
        action = data.get("action", "read")

        file_path = self.select_file()

        if not file_path:
            return "No seleccionaste ningún archivo."

        file_path = Path(file_path)

        if not file_path.exists():
            return "El archivo no existe."

        if file_path.suffix.lower() == ".txt":
            content = self.read_txt(file_path)

        elif file_path.suffix.lower() == ".pdf":
            content = self.read_pdf(file_path)

        else:
            return "Por ahora solo puedo leer archivos TXT y PDF."

        if not content:
            return "No pude leer el contenido del archivo."

        if action == "summary":
            return self.summarize(content)

        return self.prepare_read_response(content)

    def select_file(self):
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        file_path = filedialog.askopenfilename(
            title="Selecciona un archivo",
            filetypes=[
                ("Archivos PDF y TXT", "*.pdf *.txt"),
                ("Archivos PDF", "*.pdf"),
                ("Archivos TXT", "*.txt"),
                ("Todos los archivos", "*.*")
            ]
        )

        root.destroy()
        return file_path

    def read_txt(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                return file.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="latin-1") as file:
                return file.read()
        except Exception:
            return ""

    def read_pdf(self, file_path):
        if PyPDF2 is None:
            return "Falta instalar PyPDF2. Ejecuta: python -m pip install PyPDF2"

        try:
            text = ""

            with open(file_path, "rb") as file:
                reader = PyPDF2.PdfReader(file)

                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"

            return text.strip()

        except Exception:
            return ""

    def prepare_read_response(self, content):
        content = content.strip()

        if len(content) > 800:
            content = content[:800] + "..."

        return f"Leí el archivo. Esto encontré: {content}"

    def summarize(self, content):
        content = content.strip()

        if len(content) <= 500:
            return f"El archivo dice principalmente esto: {content}"

        paragraphs = content.split("\n")
        useful_parts = []

        for paragraph in paragraphs:
            paragraph = paragraph.strip()

            if len(paragraph) > 40:
                useful_parts.append(paragraph)

            if len(useful_parts) == 3:
                break

        if not useful_parts:
            summary = content[:600]
        else:
            summary = " ".join(useful_parts)

        if len(summary) > 700:
            summary = summary[:700] + "..."

        return f"Resumen del archivo: {summary}"
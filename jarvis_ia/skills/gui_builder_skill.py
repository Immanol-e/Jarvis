import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from skills.launcher import abrir_en_vscode


class GuiBuilderSkill:
    """
    Crea interfaces gráficas para proyectos existentes o nuevos.

    Soporta:
    - Java Swing: Main.java con JFrame, JMenuBar, botones y área de salida.
    - Python Tkinter: main.py con ventana, menú, botones y panel principal.
    - Web: index.html, style.css y script.js con interfaz moderna.
    """

    def run(self, data):
        action = str(data.get("action", "create_gui")).lower().strip()

        if action in ["create_gui", "create_interface", "add_gui", "create_menu_interface", "crear_interfaz"]:
            return self.create_gui(data)

        return "No entendí qué interfaz quieres crear."

    def create_gui(self, data):
        instruction = data.get("instruction") or data.get("description") or ""
        project_name = self.clean_name(
            data.get("project_name")
            or data.get("folder_name")
            or data.get("name")
            or self.extract_project_name(instruction)
            or "interfaz jarvis"
        )
        location = data.get("location", "documents")
        open_with = data.get("open_with", "vscode")

        project_path = self.resolve_project_path(project_name, location)
        project_path.mkdir(parents=True, exist_ok=True)

        gui_type = self.detect_gui_type(data, project_path, instruction)

        try:
            if gui_type == "java_swing":
                self.create_java_swing_interface(project_path, instruction)
                message = f"Listo, creé una interfaz Java Swing en {project_path}."
            elif gui_type == "web":
                self.create_web_interface(project_path, instruction)
                message = f"Listo, creé una interfaz web moderna en {project_path}."
            else:
                self.create_python_tkinter_interface(project_path, instruction)
                message = f"Listo, creé una interfaz Python con Tkinter en {project_path}."

            if open_with in ["vscode", "visual", "visual studio code", "code"]:
                message += " " + self.open_path_in_vscode(project_path)
            elif open_with in ["explorer", "explorador"]:
                message += " " + self.open_in_explorer(project_path)

            return message

        except Exception as error:
            return f"No pude crear la interfaz. Error: {error}"

    # ------------------------------------------------------------------
    # Detección
    # ------------------------------------------------------------------
    def detect_gui_type(self, data, project_path, instruction):
        explicit = self.normalize(
            data.get("gui_type")
            or data.get("project_type")
            or data.get("language")
            or data.get("type")
            or ""
        )
        text = self.normalize(instruction)

        combined = f"{explicit} {text}"

        if any(word in combined for word in ["swing", "jframe", "java"]):
            return "java_swing"
        if any(word in combined for word in ["web", "html", "css", "javascript", "pagina"]):
            return "web"
        if any(word in combined for word in ["python", "tkinter", "ventana py"]):
            return "python_tkinter"

        if (project_path / "Main.java").exists() or list(project_path.glob("*.java")):
            return "java_swing"
        if (project_path / "index.html").exists() or list(project_path.glob("*.html")):
            return "web"
        if (project_path / "main.py").exists() or list(project_path.glob("*.py")):
            return "python_tkinter"

        return "python_tkinter"

    def extract_project_name(self, instruction):
        text = instruction or ""
        normalized = self.normalize(text)

        quoted = re.search(r'["“”\']([^"“”\']+)["“”\']', text)
        if quoted:
            return self.clean_name(quoted.group(1))

        patterns = [
            r"proyecto\s+(?:llamado|llamada|de)?\s+(.+?)(?=\s+y\s+|\s+con\s+|\s+para\s+|,|$)",
            r"en\s+(?:el\s+)?proyecto\s+(.+?)(?=\s+y\s+|\s+con\s+|\s+para\s+|,|$)",
            r"interfaz\s+(?:para|de)\s+(.+?)(?=\s+y\s+|\s+con\s+|,|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if match:
                name = self.clean_name(match.group(1))
                if name and name not in ["java", "python", "web", "swing", "tkinter"]:
                    return name

        if "calculadora" in normalized:
            return "calculadora"
        if "login" in normalized or "inicio de sesion" in normalized:
            return "login"
        if "restaurante" in normalized:
            return "restaurante"
        if "riego" in normalized or "humedad" in normalized:
            return "riego smart"

        return "interfaz jarvis"

    # ------------------------------------------------------------------
    # Plantillas de interfaces
    # ------------------------------------------------------------------
    def create_python_tkinter_interface(self, project_path, instruction):
        main_py = project_path / "main.py"
        if main_py.exists():
            self.backup_file(main_py)
        main_py.write_text(self.python_tkinter_template(instruction), encoding="utf-8")

        readme = project_path / "README.md"
        if not readme.exists():
            readme.write_text(
                "# Proyecto con interfaz Tkinter\n\nEjecuta el proyecto con:\n\n```bash\npython main.py\n```\n",
                encoding="utf-8"
            )

    def create_java_swing_interface(self, project_path, instruction):
        main_java = project_path / "Main.java"
        if main_java.exists():
            self.backup_file(main_java)
        main_java.write_text(self.java_swing_template(instruction), encoding="utf-8")

        readme = project_path / "README.md"
        if not readme.exists():
            readme.write_text(
                "# Proyecto con interfaz Java Swing\n\nCompila y ejecuta con:\n\n```bash\njavac Main.java\njava Main\n```\n",
                encoding="utf-8"
            )

    def create_web_interface(self, project_path, instruction):
        files = {
            "index.html": self.web_html_template(instruction),
            "style.css": self.web_css_template(),
            "script.js": self.web_js_template(),
        }

        for file_name, content in files.items():
            path = project_path / file_name
            if path.exists():
                self.backup_file(path)
            path.write_text(content, encoding="utf-8")

        readme = project_path / "README.md"
        if not readme.exists():
            readme.write_text(
                "# Proyecto web con interfaz\n\nAbre `index.html` en el navegador o en Visual Studio Code con Live Server.\n",
                encoding="utf-8"
            )

    def python_tkinter_template(self, instruction):
        title = self.safe_title(instruction, default="Panel Inteligente")
        return f'''import tkinter as tk
from tkinter import ttk, messagebox


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("{title}")
        self.geometry("900x560")
        self.minsize(760, 480)
        self.configure(bg="#0f172a")
        self.create_styles()
        self.create_menu()
        self.create_layout()

    def create_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Main.TFrame", background="#0f172a")
        style.configure("Card.TFrame", background="#111827", relief="flat")
        style.configure("Title.TLabel", background="#0f172a", foreground="#e5e7eb", font=("Segoe UI", 22, "bold"))
        style.configure("Sub.TLabel", background="#0f172a", foreground="#94a3b8", font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", background="#111827", foreground="#e5e7eb", font=("Segoe UI", 14, "bold"))
        style.configure("CardText.TLabel", background="#111827", foreground="#cbd5e1", font=("Segoe UI", 10))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=10)

    def create_menu(self):
        menu_bar = tk.Menu(self)
        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="Nuevo", command=lambda: self.set_status("Nuevo elemento"))
        file_menu.add_command(label="Guardar", command=lambda: self.set_status("Guardado"))
        file_menu.add_separator()
        file_menu.add_command(label="Salir", command=self.destroy)
        menu_bar.add_cascade(label="Archivo", menu=file_menu)

        options_menu = tk.Menu(menu_bar, tearoff=0)
        options_menu.add_command(label="Configuración", command=lambda: self.set_status("Configuración abierta"))
        options_menu.add_command(label="Ayuda", command=self.show_help)
        menu_bar.add_cascade(label="Opciones", menu=options_menu)

        self.config(menu=menu_bar)

    def create_layout(self):
        main = ttk.Frame(self, style="Main.TFrame", padding=24)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="{title}", style="Title.TLabel").pack(anchor="w")
        ttk.Label(main, text="Interfaz generada por Jarvis", style="Sub.TLabel").pack(anchor="w", pady=(4, 20))

        content = ttk.Frame(main, style="Main.TFrame")
        content.pack(fill="both", expand=True)

        left = ttk.Frame(content, style="Card.TFrame", padding=20)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))

        right = ttk.Frame(content, style="Card.TFrame", padding=20)
        right.pack(side="right", fill="y")

        ttk.Label(left, text="Menú principal", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(left, text="Selecciona una opción para continuar.", style="CardText.TLabel").pack(anchor="w", pady=(4, 18))

        buttons = [
            ("Iniciar", lambda: self.set_status("Iniciando proceso...")),
            ("Consultar", lambda: self.set_status("Consultando información...")),
            ("Procesar", lambda: self.set_status("Procesando datos...")),
            ("Limpiar", self.clear_output),
        ]

        for text, command in buttons:
            ttk.Button(left, text=text, style="Accent.TButton", command=command).pack(fill="x", pady=6)

        self.output = tk.Text(left, height=8, bg="#020617", fg="#e5e7eb", insertbackground="#e5e7eb", relief="flat", font=("Consolas", 10))
        self.output.pack(fill="both", expand=True, pady=(16, 0))
        self.output.insert("end", "Listo para trabajar.\n")

        ttk.Label(right, text="Estado", style="CardTitle.TLabel").pack(anchor="w")
        self.status_var = tk.StringVar(value="Sistema listo")
        ttk.Label(right, textvariable=self.status_var, style="CardText.TLabel", wraplength=220).pack(anchor="w", pady=(8, 20))
        ttk.Button(right, text="Acerca de", command=self.show_help).pack(fill="x", pady=6)
        ttk.Button(right, text="Salir", command=self.destroy).pack(fill="x", pady=6)

    def set_status(self, message):
        self.status_var.set(message)
        self.output.insert("end", message + "\n")
        self.output.see("end")

    def clear_output(self):
        self.output.delete("1.0", "end")
        self.set_status("Panel limpio")

    def show_help(self):
        messagebox.showinfo("Ayuda", "Esta interfaz fue generada por Jarvis. Puedes modificar botones, colores y funciones en main.py.")


if __name__ == "__main__":
    app = App()
    app.mainloop()
'''

    def java_swing_template(self, instruction):
        title = self.safe_title(instruction, default="Panel Inteligente")
        return f'''import javax.swing.*;
import java.awt.*;

public class Main extends JFrame {{
    private JTextArea salida;
    private JLabel estado;

    public Main() {{
        setTitle("{title}");
        setSize(900, 560);
        setMinimumSize(new Dimension(760, 480));
        setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        setLocationRelativeTo(null);
        setLayout(new BorderLayout());

        crearMenu();
        crearInterfaz();
    }}

    private void crearMenu() {{
        JMenuBar barra = new JMenuBar();

        JMenu archivo = new JMenu("Archivo");
        JMenuItem nuevo = new JMenuItem("Nuevo");
        JMenuItem guardar = new JMenuItem("Guardar");
        JMenuItem salir = new JMenuItem("Salir");

        nuevo.addActionListener(e -> escribir("Nuevo elemento creado"));
        guardar.addActionListener(e -> escribir("Información guardada"));
        salir.addActionListener(e -> dispose());

        archivo.add(nuevo);
        archivo.add(guardar);
        archivo.addSeparator();
        archivo.add(salir);

        JMenu opciones = new JMenu("Opciones");
        JMenuItem configuracion = new JMenuItem("Configuración");
        JMenuItem ayuda = new JMenuItem("Ayuda");

        configuracion.addActionListener(e -> escribir("Configuración abierta"));
        ayuda.addActionListener(e -> JOptionPane.showMessageDialog(this, "Interfaz generada por Jarvis"));

        opciones.add(configuracion);
        opciones.add(ayuda);

        barra.add(archivo);
        barra.add(opciones);
        setJMenuBar(barra);
    }}

    private void crearInterfaz() {{
        JPanel principal = new JPanel(new BorderLayout(16, 16));
        principal.setBackground(new Color(15, 23, 42));
        principal.setBorder(BorderFactory.createEmptyBorder(24, 24, 24, 24));

        JLabel titulo = new JLabel("{title}");
        titulo.setForeground(new Color(229, 231, 235));
        titulo.setFont(new Font("Segoe UI", Font.BOLD, 26));
        principal.add(titulo, BorderLayout.NORTH);

        JPanel centro = new JPanel(new GridLayout(1, 2, 16, 16));
        centro.setOpaque(false);

        JPanel panelMenu = crearTarjeta();
        panelMenu.setLayout(new GridLayout(0, 1, 8, 8));

        JLabel menuTitulo = new JLabel("Menú principal");
        menuTitulo.setForeground(Color.WHITE);
        menuTitulo.setFont(new Font("Segoe UI", Font.BOLD, 18));
        panelMenu.add(menuTitulo);

        JButton iniciar = crearBoton("Iniciar");
        JButton consultar = crearBoton("Consultar");
        JButton procesar = crearBoton("Procesar");
        JButton limpiar = crearBoton("Limpiar");

        iniciar.addActionListener(e -> escribir("Iniciando proceso..."));
        consultar.addActionListener(e -> escribir("Consultando información..."));
        procesar.addActionListener(e -> escribir("Procesando datos..."));
        limpiar.addActionListener(e -> salida.setText(""));

        panelMenu.add(iniciar);
        panelMenu.add(consultar);
        panelMenu.add(procesar);
        panelMenu.add(limpiar);

        JPanel panelSalida = crearTarjeta();
        panelSalida.setLayout(new BorderLayout(8, 8));
        JLabel salidaTitulo = new JLabel("Salida");
        salidaTitulo.setForeground(Color.WHITE);
        salidaTitulo.setFont(new Font("Segoe UI", Font.BOLD, 18));
        panelSalida.add(salidaTitulo, BorderLayout.NORTH);

        salida = new JTextArea("Listo para trabajar.\n");
        salida.setBackground(new Color(2, 6, 23));
        salida.setForeground(new Color(229, 231, 235));
        salida.setFont(new Font("Consolas", Font.PLAIN, 14));
        salida.setBorder(BorderFactory.createEmptyBorder(12, 12, 12, 12));
        panelSalida.add(new JScrollPane(salida), BorderLayout.CENTER);

        estado = new JLabel("Estado: sistema listo");
        estado.setForeground(new Color(148, 163, 184));
        panelSalida.add(estado, BorderLayout.SOUTH);

        centro.add(panelMenu);
        centro.add(panelSalida);
        principal.add(centro, BorderLayout.CENTER);

        add(principal);
    }}

    private JPanel crearTarjeta() {{
        JPanel panel = new JPanel();
        panel.setBackground(new Color(17, 24, 39));
        panel.setBorder(BorderFactory.createEmptyBorder(18, 18, 18, 18));
        return panel;
    }}

    private JButton crearBoton(String texto) {{
        JButton boton = new JButton(texto);
        boton.setFont(new Font("Segoe UI", Font.BOLD, 14));
        boton.setFocusPainted(false);
        return boton;
    }}

    private void escribir(String texto) {{
        salida.append(texto + "\n");
        estado.setText("Estado: " + texto);
    }}

    public static void main(String[] args) {{
        SwingUtilities.invokeLater(() -> new Main().setVisible(true));
    }}
}}
'''

    def web_html_template(self, instruction):
        title = self.safe_title(instruction, default="Panel Inteligente")
        return f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <aside class="sidebar">
        <div class="brand">JARVIS UI</div>
        <button class="nav-btn active">Inicio</button>
        <button class="nav-btn">Panel</button>
        <button class="nav-btn">Reportes</button>
        <button class="nav-btn">Ajustes</button>
    </aside>

    <main class="dashboard">
        <header class="hero">
            <p class="eyebrow">Interfaz generada por Jarvis</p>
            <h1>{title}</h1>
            <p>Panel moderno con menú, tarjetas, botones y área de resultados.</p>
        </header>

        <section class="cards">
            <article class="card">
                <h2>Acción principal</h2>
                <p>Usa este botón para iniciar el flujo principal.</p>
                <button id="startBtn">Iniciar</button>
            </article>

            <article class="card">
                <h2>Estado</h2>
                <p id="statusText">Sistema listo.</p>
            </article>

            <article class="card wide">
                <h2>Registro</h2>
                <pre id="logBox">Listo para trabajar.</pre>
            </article>
        </section>
    </main>

    <script src="script.js"></script>
</body>
</html>
'''

    def web_css_template(self):
        return '''* {
    box-sizing: border-box;
}

body {
    margin: 0;
    min-height: 100vh;
    font-family: "Segoe UI", Arial, sans-serif;
    background: radial-gradient(circle at top left, #1d4ed8 0, transparent 28%), #020617;
    color: #e5e7eb;
    display: flex;
}

.sidebar {
    width: 230px;
    padding: 24px;
    background: rgba(15, 23, 42, 0.88);
    border-right: 1px solid rgba(148, 163, 184, 0.18);
    backdrop-filter: blur(18px);
}

.brand {
    font-weight: 800;
    letter-spacing: 2px;
    margin-bottom: 32px;
    color: #38bdf8;
}

.nav-btn {
    width: 100%;
    display: block;
    margin-bottom: 10px;
    padding: 12px 14px;
    border: 0;
    border-radius: 14px;
    background: transparent;
    color: #cbd5e1;
    text-align: left;
    cursor: pointer;
}

.nav-btn.active,
.nav-btn:hover {
    background: rgba(56, 189, 248, 0.14);
    color: #fff;
}

.dashboard {
    flex: 1;
    padding: 34px;
}

.hero {
    max-width: 900px;
    padding: 28px;
    border-radius: 26px;
    background: linear-gradient(135deg, rgba(14, 165, 233, 0.22), rgba(30, 41, 59, 0.75));
    border: 1px solid rgba(148, 163, 184, 0.18);
}

.eyebrow {
    color: #38bdf8;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.8px;
}

.hero h1 {
    margin: 8px 0;
    font-size: 42px;
}

.cards {
    display: grid;
    grid-template-columns: repeat(2, minmax(240px, 1fr));
    gap: 18px;
    margin-top: 20px;
}

.card {
    padding: 24px;
    border-radius: 22px;
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(148, 163, 184, 0.16);
    box-shadow: 0 20px 55px rgba(0, 0, 0, 0.25);
}

.card.wide {
    grid-column: 1 / -1;
}

button {
    border: 0;
    padding: 12px 18px;
    border-radius: 14px;
    background: linear-gradient(135deg, #38bdf8, #2563eb);
    color: white;
    font-weight: 700;
    cursor: pointer;
}

pre {
    white-space: pre-wrap;
    padding: 16px;
    border-radius: 14px;
    background: #020617;
    color: #bae6fd;
}
'''

    def web_js_template(self):
        return '''const startBtn = document.getElementById("startBtn");
const statusText = document.getElementById("statusText");
const logBox = document.getElementById("logBox");

function log(message) {
    statusText.textContent = message;
    logBox.textContent += "\n" + message;
}

startBtn.addEventListener("click", () => {
    log("Proceso iniciado desde la interfaz.");
});

document.querySelectorAll(".nav-btn").forEach((button) => {
    button.addEventListener("click", () => {
        document.querySelectorAll(".nav-btn").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        log(`Se abrió la sección: ${button.textContent}`);
    });
});
'''

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def resolve_project_path(self, project_name, location="documents"):
        existing = self.find_project(project_name, location)
        if existing:
            return existing
        return self.resolve_location(location) / self.clean_name(project_name)

    def find_project(self, project_name, location=""):
        target = self.normalize_for_search(project_name)
        if not target:
            return None

        for root in self.search_roots(location):
            if not root.exists():
                continue
            try:
                for path in root.rglob("*"):
                    if not path.is_dir() or self.should_skip_path(path):
                        continue
                    name = self.normalize_for_search(path.name)
                    if target == name or target in name:
                        return path
            except (PermissionError, OSError):
                continue
        return None

    def search_roots(self, location=""):
        if location:
            return [self.resolve_location(location)]

        home = Path.home()
        roots = [home / "Documents", home / "Desktop", home / "Downloads", Path.cwd()]
        for one_drive_name in ["OneDrive", "OneDrive - Personal"]:
            one_drive = home / one_drive_name
            roots.extend([one_drive / "Documents", one_drive / "Desktop", one_drive / "Downloads"])

        unique = []
        for root in roots:
            if root not in unique and root.exists():
                unique.append(root)
        return unique or [home]

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
        }
        return locations.get(text, home / "Documents")

    def should_skip_path(self, path):
        skip = {".git", "node_modules", "venv", ".venv", "__pycache__", ".idea", ".vscode", "dist", "build", "target"}
        return any(part in skip for part in path.parts)

    def backup_file(self, file_path):
        if not file_path.exists():
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = file_path.with_name(f"{file_path.name}.jarvis_backup_{timestamp}")
        backup_path.write_text(file_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        return backup_path

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

    def safe_title(self, instruction, default="Panel Inteligente"):
        text = self.clean_name(instruction or "")
        for word in ["interfaz", "ventana", "menu", "menú", "grafica", "gráfica", "crea", "crear", "haz", "hacer", "proyecto"]:
            text = re.sub(rf"\b{word}\b", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s+", " ", text).strip()
        if not text or len(text) < 3:
            return default
        return text[:45].title()

    def clean_name(self, name):
        name = str(name).strip().strip(" .\"“”'")
        name = re.sub(r"^(?:el|la|mi|mis|proyecto|archivo|carpeta|interfaz)\s+", "", name, flags=re.IGNORECASE).strip()
        name = re.sub(r'[<>:"/\\|?*]', "", name)
        name = re.sub(r"\s+", " ", name)
        return name[:100] or "interfaz jarvis"

    def normalize(self, text):
        text = str(text).lower().strip()
        text = text.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
        text = re.sub(r"\s+", " ", text)
        return text

    def normalize_for_search(self, text):
        text = self.normalize(text)
        text = re.sub(r"[^a-z0-9_. -]", "", text)
        return text.strip()
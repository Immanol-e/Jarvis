"""
app/jarvis_ui.py — Interfaz JARVIS con HUD animado estilo Iron Man / Tony Stark

Cambios respecto al original:
  - create_orb()   → instancia HUDOrb (clase completa con animación propia)
  - animate_orb()  → eliminado (HUDOrb se anima sola)
  - 4 estados visuales: idle, listening, processing, speaking
  - Barra de estado inferior estilo HUD
  - Colores del chat diferenciados por hablante
  - Todos los cambios de estado van por message_queue (thread-safe)
"""

import math
import queue
import random
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

from app.assistant import JarvisAssistant


# ── Paleta global ─────────────────────────────────────────────────────────
_BG  = "#050816"
_BG2 = "#0b1020"
_BG3 = "#111827"

# Propiedades visuales de cada estado del orb
_STATE = {
    "idle": {
        "primary":   "#0ea5e9",
        "secondary": "#075985",
        "accent":    "#38bdf8",
        "glow":      "#041828",
        "text_col":  "#7dd3fc",
        "label":     "EN ESPERA",
        "speed":     1.0,
    },
    "listening": {
        "primary":   "#22d3ee",
        "secondary": "#0891b2",
        "accent":    "#67e8f9",
        "glow":      "#042830",
        "text_col":  "#a5f3fc",
        "label":     "ESCUCHANDO",
        "speed":     2.5,
    },
    "processing": {
        "primary":   "#fbbf24",
        "secondary": "#b45309",
        "accent":    "#fde68a",
        "glow":      "#120a00",
        "text_col":  "#fef3c7",
        "label":     "PROCESANDO",
        "speed":     4.5,
    },
    "speaking": {
        "primary":   "#4ade80",
        "secondary": "#15803d",
        "accent":    "#86efac",
        "glow":      "#021a07",
        "text_col":  "#dcfce7",
        "label":     "HABLANDO",
        "speed":     1.8,
    },
}


# ═══════════════════════════════════════════════════════════════════════════
#  HUDOrb — animación Iron Man
# ═══════════════════════════════════════════════════════════════════════════

class HUDOrb(tk.Canvas):
    """
    Canvas con animación HUD estilo Iron Man.
    Uso: orb.set_state("idle" | "listening" | "processing" | "speaking")
    Se anima sola con after() — no requiere llamada externa.
    """

    SIZE = 220
    CX   = 110
    CY   = 110

    def __init__(self, parent, **kw):
        super().__init__(
            parent,
            width=self.SIZE, height=self.SIZE,
            bg=_BG2, highlightthickness=0,
            **kw,
        )
        self._state     = "idle"
        self._angle     = 0.0
        self._pulse     = 0.0
        self._pulse_dir = 1
        self._ripples   = []          # ondas expansivas en modo listening
        self._data      = self._new_data()
        self._frame     = 0
        self._alive     = True
        self._tick()

    # ── API pública ──────────────────────────────────────────────────────────
    def set_state(self, name: str):
        if name not in _STATE:
            return
        if name == "listening" and self._state != "listening":
            self._ripples.clear()
        self._state = name

    # ── Helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _new_data():
        return [
            f"PWR  {random.randint(94,100)}%",
            f"NET  {random.randint(1,9)}.{random.randint(0,9)}Gb",
            f"CPU  {random.randint(4,38)}%",
            f"SYS  OK",
            f"LAT  {random.randint(1,15)}ms",
            f"REV  4.{random.randint(0,9)}",
        ]

    @staticmethod
    def _blend(color: str, alpha: float) -> str:
        """Interpola color hacia negro según alpha (0=negro, 1=color puro)."""
        r = int(int(color[1:3], 16) * alpha)
        g = int(int(color[3:5], 16) * alpha)
        b = int(int(color[5:7], 16) * alpha)
        return f"#{r:02x}{g:02x}{b:02x}"

    # ── Bucle de animación ────────────────────────────────────────────────────
    def _tick(self):
        if not self._alive:
            return

        st    = _STATE[self._state]
        speed = st["speed"]

        self._angle = (self._angle + speed * 2.0) % 360

        self._pulse += 0.045 * speed * self._pulse_dir
        if   self._pulse >= 1.0: self._pulse = 1.0; self._pulse_dir = -1
        elif self._pulse <= 0.0: self._pulse = 0.0; self._pulse_dir =  1

        if self._state == "listening" and self._frame % 18 == 0:
            self._ripples.append([38, 1.0])
        self._ripples = [
            [r + 2.8 * speed, max(0.0, a - 0.035)]
            for r, a in self._ripples if a > 0
        ]

        if self._frame % 38 == 0:
            self._data = self._new_data()

        self._draw(st, speed)
        self._frame += 1
        self.after(50, self._tick)

    # ── Renderizado ───────────────────────────────────────────────────────────
    def _draw(self, st, speed):
        self.delete("all")
        blend = self._blend
        cx, cy = self.CX, self.CY
        angle  = self._angle
        pulse  = self._pulse
        p, s, ac, gl = st["primary"], st["secondary"], st["accent"], st["glow"]

        # 1. Fondo oscuro del orb
        self.create_oval(8, 8, 212, 212, fill="#010d1f", outline="")

        # 2. Ondas de escucha
        for radius, alpha in self._ripples:
            if alpha <= 0: continue
            r = int(radius)
            self.create_oval(cx-r, cy-r, cx+r, cy+r,
                             outline=blend(ac, alpha * 0.55), width=1)

        # 3. Anillo exterior segmentado (16 segmentos, giro lento)
        seg_extent = 360 / 16 - 8
        for i in range(16):
            start     = angle * 0.25 + i * (360 / 16)
            intensity = 0.35 + 0.65 * (i % 4 == 0)
            self.create_arc(
                cx-97, cy-97, cx+97, cy+97,
                start=start, extent=seg_extent,
                style=tk.ARC, outline=blend(p, intensity), width=2,
            )

        # 4. Arco primario giratorio (195°)
        self.create_arc(
            cx-83, cy-83, cx+83, cy+83,
            start=angle * 1.6, extent=195,
            style=tk.ARC, outline=p, width=3,
        )

        # 5. Arco de acento contra-rotatorio (85°)
        self.create_arc(
            cx-76, cy-76, cx+76, cy+76,
            start=-angle * 2.4, extent=85,
            style=tk.ARC, outline=ac, width=2,
        )

        # 6. Arco secundario (40°, giro lento inverso)
        self.create_arc(
            cx-70, cy-70, cx+70, cy+70,
            start=angle * 0.9 + 180, extent=40,
            style=tk.ARC, outline=s, width=2,
        )

        # 7. Ticks radiales (24 marcas)
        for i in range(24):
            a      = math.radians(i * 15)
            major  = i % 6 == 0
            r_out  = 92
            r_in   = 82 if major else 87
            x1 = cx + r_in  * math.cos(a);  y1 = cy - r_in  * math.sin(a)
            x2 = cx + r_out * math.cos(a);  y2 = cy - r_out * math.sin(a)
            self.create_line(x1, y1, x2, y2,
                             fill=ac if major else blend(s, 0.55),
                             width=2 if major else 1)

        # 8. Barrido tipo radar con cola
        for i in range(6):
            sweep_a = math.radians(angle * 2.0 - i * 14)
            alpha   = max(0.0, 0.7 - i * 0.12)
            sx = cx + 87 * math.cos(sweep_a)
            sy = cy - 87 * math.sin(sweep_a)
            self.create_line(cx, cy, sx, sy,
                             fill=blend(p, alpha), width=1)

        # 9. Indicadores de cuadrante (4 arcos pequeños)
        for deg in (45, 135, 225, 315):
            a_start = deg - angle * 0.45
            self.create_arc(
                cx-62, cy-62, cx+62, cy+62,
                start=a_start, extent=22,
                style=tk.ARC, outline=blend(ac, 0.65), width=2,
            )

        # 10. Círculo interior pulsante
        ir = int(50 + pulse * 7)
        self.create_oval(cx-ir, cy-ir, cx+ir, cy+ir,
                         fill=gl,
                         outline=blend(ac, 0.45 + pulse * 0.55),
                         width=2)

        # 11. Destello de núcleo
        gr = int(38 + pulse * 5)
        self.create_oval(cx-gr, cy-gr, cx+gr, cy+gr,
                         fill="", outline=blend(p, 0.25 + pulse * 0.55),
                         width=1)

        # 12. Letra J central
        self.create_text(cx, cy - 7,
                         text="J",
                         fill=ac,
                         font=("Segoe UI", 30, "bold"))

        # 13. Etiqueta de estado
        self.create_text(cx, cy + 18,
                         text=st["label"],
                         fill=blend(st["text_col"], 0.7),
                         font=("Consolas", 6, "bold"))

        # 14. Datos técnicos alrededor del orb
        positions = [
            (cx - 108, cy - 20), (cx - 108, cy + 2),
            (cx + 108, cy - 20), (cx + 108, cy + 2),
            (cx - 24,  cy - 108), (cx + 24, cy + 108),
        ]
        for (dx, dy), label in zip(positions, self._data):
            self.create_text(dx, dy,
                             text=label,
                             fill=blend(s, 0.6),
                             font=("Consolas", 7))

        # 15. Líneas horizontales de referencia
        ref = blend(s, 0.28)
        self.create_line(cx-90, cy, cx-56, cy, fill=ref, width=1)
        self.create_line(cx+56, cy, cx+90, cy, fill=ref, width=1)

    def destroy(self):
        self._alive = False
        super().destroy()


# ═══════════════════════════════════════════════════════════════════════════
#  JarvisUI — ventana principal
# ═══════════════════════════════════════════════════════════════════════════

class JarvisUI(tk.Tk):
    """Interfaz visual para JARVIS con HUD animado Iron Man."""

    def __init__(self):
        super().__init__()
        self.title("JARVIS IA")
        self.geometry("1060x700")
        self.minsize(860, 580)
        self.configure(bg=_BG)

        self.message_queue = queue.Queue()
        self.orb: HUDOrb | None = None

        self.jarvis = JarvisAssistant()
        self.jarvis.set_response_callback(self._on_jarvis_response)
        self.jarvis.start_reminder_checker()

        self._create_styles()
        self._create_layout()
        self.after(100, self._process_queue)

    # ── Estilos ───────────────────────────────────────────────────────────────
    def _create_styles(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure("Root.TFrame",  background=_BG)
        st.configure("Panel.TFrame", background=_BG2)
        st.configure("Card.TFrame",  background=_BG3)

        st.configure("Title.TLabel",
                     background=_BG, foreground="#e5e7eb",
                     font=("Segoe UI", 24, "bold"))
        st.configure("Sub.TLabel",
                     background=_BG, foreground="#7dd3fc",
                     font=("Segoe UI", 10, "bold"))
        st.configure("Small.TLabel",
                     background=_BG2, foreground="#94a3b8",
                     font=("Consolas", 9))
        st.configure("Status.TLabel",
                     background=_BG3, foreground="#bae6fd",
                     font=("Segoe UI", 10, "bold"))
        st.configure("HUD.TLabel",
                     background=_BG, foreground="#0ea5e9",
                     font=("Consolas", 8))
        st.configure("Accent.TButton",
                     font=("Segoe UI", 10, "bold"), padding=(14, 10))
        st.configure("Ghost.TButton",
                     font=("Segoe UI", 10), padding=(12, 9))

    # ── Layout principal ──────────────────────────────────────────────────────
    def _create_layout(self):
        root = ttk.Frame(self, style="Root.TFrame", padding=20)
        root.pack(fill="both", expand=True)

        # ── Header ────────────────────────────────────────────────────────────
        header = ttk.Frame(root, style="Root.TFrame")
        header.pack(fill="x")

        title_box = ttk.Frame(header, style="Root.TFrame")
        title_box.pack(side="left", fill="x", expand=True)
        ttk.Label(title_box, text="JARVIS  IA", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="Asistente local · Ollama · Windows",
                  style="Sub.TLabel").pack(anchor="w", pady=(0, 12))

        self.status_var = tk.StringVar(value="Sistema listo")
        status_card = ttk.Frame(header, style="Card.TFrame", padding=14)
        status_card.pack(side="right", padx=(12, 0))
        ttk.Label(status_card, text="ESTADO DEL SISTEMA",
                  style="Status.TLabel").pack(anchor="w")
        ttk.Label(status_card, textvariable=self.status_var,
                  style="Status.TLabel", wraplength=230).pack(anchor="w", pady=(6, 0))

        # ── Cuerpo ────────────────────────────────────────────────────────────
        body = ttk.Frame(root, style="Root.TFrame")
        body.pack(fill="both", expand=True, pady=(10, 0))

        # Sidebar izquierdo
        sidebar = ttk.Frame(body, style="Panel.TFrame", padding=18)
        sidebar.pack(side="left", fill="y", padx=(0, 14))

        self._create_orb(sidebar)

        ttk.Label(sidebar, text="▸ ACCESOS RÁPIDOS",
                  style="Small.TLabel").pack(anchor="w", pady=(18, 8))

        accesos = [
            ("Abrir VS Code",           "abre visual studio code"),
            ("Crear proyecto Python",   "crea un proyecto de python para calculadora y abrelo en visual"),
            ("Crear interfaz tkinter",  "crea una interfaz en python con menu y botones"),
            ("Buscar en Google",        "busca inteligencia artificial en google"),
            ("Escanear red",            "escanea la red"),
            ("Mis hábitos",             "cuáles son mis hábitos"),
            ("Estado del sistema",      "stats del sistema"),
            ("Voz (una vez)",           None),
        ]
        for label, cmd in accesos:
            if cmd is None:
                ttk.Button(sidebar, text=label, style="Ghost.TButton",
                           command=self.listen_once).pack(fill="x", pady=4)
            else:
                ttk.Button(sidebar, text=label, style="Ghost.TButton",
                           command=lambda c=cmd: self._fill_and_send(c)
                           ).pack(fill="x", pady=4)

        ttk.Separator(sidebar, orient="horizontal").pack(fill="x", pady=14)
        ttk.Button(sidebar, text="Salir", style="Ghost.TButton",
                   command=self.destroy).pack(fill="x")

        # Panel de chat
        chat_panel = ttk.Frame(body, style="Panel.TFrame", padding=16)
        chat_panel.pack(side="right", fill="both", expand=True)

        self.chat = scrolledtext.ScrolledText(
            chat_panel,
            wrap="word",
            bg="#010d1f",
            fg="#e5e7eb",
            insertbackground="#e5e7eb",
            relief="flat",
            font=("Segoe UI", 11),
            padx=16, pady=16,
        )
        self.chat.pack(fill="both", expand=True)
        self.chat.configure(state="disabled")
        self._configure_chat_tags()

        # Barra de entrada
        input_bar = ttk.Frame(chat_panel, style="Panel.TFrame")
        input_bar.pack(fill="x", pady=(14, 0))

        self.command_var = tk.StringVar()
        self.entry = tk.Entry(
            input_bar,
            textvariable=self.command_var,
            bg="#0f172a", fg="#e5e7eb",
            insertbackground="#38bdf8",
            relief="flat",
            font=("Segoe UI", 12),
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=11, padx=(0, 10))
        self.entry.bind("<Return>", lambda e: self.send_command())

        ttk.Button(input_bar, text="Enviar",
                   style="Accent.TButton", command=self.send_command).pack(side="left")
        ttk.Button(input_bar, text="Hablar",
                   style="Accent.TButton", command=self.listen_once).pack(side="left", padx=(8, 0))

        # Barra de estado HUD (inferior)
        self._create_hud_statusbar(root)

        self._add_chat("JARVIS", "Sistema iniciado. Escribe un comando o presiona Hablar.")

    # ── Orb ───────────────────────────────────────────────────────────────────
    def _create_orb(self, parent):
        self.orb = HUDOrb(parent)
        self.orb.pack(pady=(4, 6))

    # ── Barra inferior HUD ────────────────────────────────────────────────────
    def _create_hud_statusbar(self, parent):
        bar = ttk.Frame(parent, style="Root.TFrame")
        bar.pack(fill="x", pady=(10, 0))

        items = [
            "JARVIS v4.0",
            "OLLAMA ● ONLINE",
            "ADB ● READY",
            "ENC ● OFF",
            "MODO ● TEXTO",
        ]
        for item in items:
            ttk.Label(bar, text=f"  {item}  ",
                      style="HUD.TLabel").pack(side="left")

        self.hud_clock = tk.StringVar()
        ttk.Label(bar, textvariable=self.hud_clock,
                  style="HUD.TLabel").pack(side="right")
        self._update_clock()

    def _update_clock(self):
        import datetime
        now = datetime.datetime.now().strftime("%H:%M:%S   %d/%m/%Y")
        self.hud_clock.set(now)
        self.after(1000, self._update_clock)

    # ── Tags del chat ─────────────────────────────────────────────────────────
    def _configure_chat_tags(self):
        self.chat.tag_config("sender_jarvis",
                             foreground="#38bdf8",
                             font=("Segoe UI", 11, "bold"))
        self.chat.tag_config("sender_user",
                             foreground="#a78bfa",
                             font=("Segoe UI", 11, "bold"))
        self.chat.tag_config("sender_system",
                             foreground="#94a3b8",
                             font=("Segoe UI", 11, "bold"))
        self.chat.tag_config("msg_jarvis",
                             foreground="#e2e8f0",
                             font=("Segoe UI", 11))
        self.chat.tag_config("msg_user",
                             foreground="#c4b5fd",
                             font=("Segoe UI", 11))
        self.chat.tag_config("msg_system",
                             foreground="#64748b",
                             font=("Segoe UI", 10, "italic"))

    # ── Acciones ─────────────────────────────────────────────────────────────
    def _fill_and_send(self, cmd: str):
        self.command_var.set(cmd)
        self.send_command()

    def send_command(self):
        cmd = self.command_var.get().strip()
        if not cmd:
            return
        self.command_var.set("")
        self._add_chat("Tú", cmd)
        self.status_var.set("Procesando...")
        if self.orb:
            self.orb.set_state("processing")
        threading.Thread(
            target=self.jarvis.process_command,
            args=(cmd,), daemon=True
        ).start()

    def listen_once(self):
        self.status_var.set("Escuchando...")
        self._add_chat("Sistema", "Te escucho...")
        if self.orb:
            self.orb.set_state("listening")

        def worker():
            try:
                text = self.jarvis.ears.listen()
                if not text:
                    self.message_queue.put(("Sistema", "No entendí lo que dijiste."))
                    self.message_queue.put(("status",  "Sistema listo"))
                    self.message_queue.put(("orb",     "idle"))
                    return
                self.message_queue.put(("Tú", text))
                self.message_queue.put(("orb", "processing"))
                self.jarvis.process_command(text)
            except Exception as err:
                self.message_queue.put(("Sistema", f"Error con el micrófono: {err}"))
                self.message_queue.put(("status",  "Error"))
                self.message_queue.put(("orb",     "idle"))

        threading.Thread(target=worker, daemon=True).start()

    # ── Callback de respuesta (hilo de JARVIS) ────────────────────────────────
    def _on_jarvis_response(self, response: str):
        self.message_queue.put(("JARVIS",  response))
        self.message_queue.put(("status",  "Sistema listo"))
        self.message_queue.put(("orb",     "speaking"))

    # ── Procesador de la cola (hilo principal) ────────────────────────────────
    def _process_queue(self):
        try:
            while not self.message_queue.empty():
                tag, value = self.message_queue.get_nowait()
                if tag == "status":
                    self.status_var.set(value)
                elif tag == "orb":
                    if self.orb:
                        self.orb.set_state(value)
                        if value == "speaking":
                            # Volver a idle después de 3.5 segundos
                            self.after(3500, self._back_to_idle)
                else:
                    self._add_chat(tag, value)
        except Exception:
            pass
        self.after(100, self._process_queue)

    def _back_to_idle(self):
        if self.orb:
            self.orb.set_state("idle")

    # ── Chat ──────────────────────────────────────────────────────────────────
    def _add_chat(self, sender: str, message: str):
        self.chat.configure(state="normal")

        if sender == "JARVIS":
            stag, mtag = "sender_jarvis", "msg_jarvis"
            prefix     = "▸ JARVIS"
        elif sender == "Tú":
            stag, mtag = "sender_user",   "msg_user"
            prefix     = "▸ TÚ"
        else:
            stag, mtag = "sender_system", "msg_system"
            prefix     = f"▸ {sender.upper()}"

        self.chat.insert("end", f"{prefix}:\n", (stag,))
        self.chat.insert("end", f"{message}\n\n", (mtag,))
        self.chat.see("end")
        self.chat.configure(state="disabled")

    # ── Compatibilidad con el código que llama add_chat_message ──────────────
    def add_chat_message(self, sender: str, message: str):
        self._add_chat(sender, message)


def main():
    app = JarvisUI()
    app.mainloop()


if __name__ == "__main__":
    main()
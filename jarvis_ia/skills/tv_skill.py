"""
tv_skill.py — Control de Android TV via ADB over WiFi.

Fixes aplicados:
  #2  Sleeps adaptativos: _esperar_ui_estable() espera que la pantalla
      deje de cambiar en vez de usar time.sleep() fijos.
  #5  Importa TV_APPS y TV_PLATAFORMAS desde config.tv_config
      (fuente única de verdad).
  #8  Auto-reconexión: _require_connection() intenta reconectar si la TV
      se durmió o perdió la conexión ADB.
  #9  _escribir() ya NO usa urllib.parse.quote() — Android TV acepta
      UTF-8 directamente; el encoding anterior mandaba "canci%C3%B3n"
      en lugar de "canción".
  #10 Selector de resultados Crunchyroll por XML + foco real de Android TV.
"""


import subprocess
import time
import re
import html

from config.tv_config import TV_APPS, TV_PLATAFORMAS   # Fix #5


KEYCODES = {
    "home":         3,
    "back":         4,
    "menu":         82,
    "play_pause":   85,
    "play":         126,
    "pause":        127,
    "stop":         86,
    "siguiente":    87,
    "anterior":     88,
    "retroceder":   89,    # KEYCODE_MEDIA_REWIND
    "adelantar":    90,    # KEYCODE_MEDIA_FAST_FORWARD
    "volumen_up":   24,
    "volumen_down": 25,
    "mute":         164,
    "subtitulos":   175,   # KEYCODE_CAPTIONS
    "info":         165,   # KEYCODE_INFO
    "canal_arriba": 166,   # KEYCODE_CHANNEL_UP
    "canal_abajo":  167,   # KEYCODE_CHANNEL_DOWN
    "arriba":       19,
    "abajo":        20,
    "izquierda":    21,
    "derecha":      22,
    "ok":           23,
    "encender":     26,
    "power":        26,
    "search":       84,
    "enter":        66,
    "espacio":      62,
}


class TVSkill:
    def __init__(self):
        self.tv_ip     = None
        self.connected = False

    # ── Estado de Crunchyroll / Android TV ───────────────────────────
    def _paquete_en_primer_plano(self):
        """Devuelve el package que Android TV tiene realmente en primer plano."""
        consultas = [
            ("shell", "dumpsys", "window", "windows"),
            ("shell", "dumpsys", "activity", "activities"),
        ]
        for args in consultas:
            out, _, code = self._adb(*args, timeout=5)
            if code != 0 or not out:
                continue
            patrones = [
                r"mCurrentFocus=Window\{[^}]*\s([A-Za-z0-9._]+)/",
                r"mFocusedApp=ActivityRecord\{[^}]*\s([A-Za-z0-9._]+)/",
                r"ResumedActivity: ActivityRecord\{[^}]*\s([A-Za-z0-9._]+)/",
            ]
            for patron in patrones:
                m = re.search(patron, out)
                if m:
                    return m.group(1)
        return ""

    def _cr_xml_state(self, xml):
        """Clasifica de forma aproximada la pantalla actual de Crunchyroll."""
        x = (xml or "").lower()
        if not x:
            return "desconocido"

        perfil = self._CRUNCHYROLL_PERFIL.lower()
        if perfil and perfil in x and any(
            a in x for a in ['focused="true"', 'selected="true"']
        ):
            # No basta con que el nombre exista: intentamos detectar selector.
            if any(t in x for t in ["selecciona tu perfil", "elige tu perfil", "quién está viendo",
                                     "who's watching", "select profile", "perfiles"]):
                return "perfiles"

        if "android.widget.edittext" in x:
            return "busqueda"

        if any(t in x for t in [
            'content-desc="buscar"', 'content-desc="search"',
            'text="buscar"', 'text="search"', 'búsqueda'
        ]):
            # Puede ser home o la pantalla de búsqueda.
            if any(t in x for t in ["resultados", "results", "buscar en crunchyroll"]):
                return "busqueda"
            return "home"

        if any(t in x for t in ["inicio", "home", "navegación", "navigation"]):
            return "home"

        return "desconocido"

    def _normalizar_query_tv(self, query, capitulo=None, plataforma=""):
        """Evita que una frase completa de voz llegue al campo de búsqueda."""
        q = str(query or "").strip()
        if not q:
            return ""

        q = re.sub(
            r"^(?:oye\s+)?(?:jarvis[,:]?\s*)?(?:por favor\s*)?"
            r"(?:reproduce(?:me)?|reproducir|reproduceme|pon(?:me)?|"
            r"quiero\s+(?:ver|reproducir)|dale\s+play\s+a|"
            r"busca(?:me)?|muestrame|muéstrame)\s+",
            "", q, flags=re.IGNORECASE
        )
        if capitulo is not None:
            q = re.sub(
                r"\s+(?:el\s+)?(?:cap[ií]tulo|capitulo|episodio|ep\.?|cap\.?)"
                r"\s*[#nº]?\s*\d+\b", "", q, flags=re.IGNORECASE
            )
        if plataforma:
            q = re.sub(
                rf"\s+(?:en\s+(?:la\s+|el\s+)?)?{re.escape(str(plataforma))}\b",
                "", q, flags=re.IGNORECASE
            )
        q = re.sub(r"\s+(?:en\s+(?:la\s+|el\s+)?(?:tv|tele|television|televisión|televisor))\b",
                   "", q, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", q).strip(" ,.-")

    def _es_crunchyroll_activo(self, package):
        actual = self._paquete_en_primer_plano()
        return bool(actual and actual == package)

    # ── ADB base ────────────────────────────────────────────────────

    def _adb(self, *args, timeout=10):
        base = ["adb", "-s", f"{self.tv_ip}:5555"] if self.tv_ip else ["adb"]
        try:
            r = subprocess.run(
                base + list(args),
                capture_output=True,
                text=True,
                encoding="utf-8",   # Fix: Windows usa cp1252 por defecto, que no puede
                errors="replace",   # decodificar bytes UTF-8 de uiautomator dump (kanji, tildes…)
                timeout=timeout,
            )
            return r.stdout.strip(), r.stderr.strip(), r.returncode
        except FileNotFoundError:
            return "", "ADB no encontrado", 1
        except subprocess.TimeoutExpired:
            return "", "Timeout", 1
        except Exception as e:
            return "", str(e), 1

    def _keyevent(self, keycode):
        self._adb("shell", "input", "keyevent", str(keycode))

    def _check_adb(self):
        _, _, code = self._adb("version", timeout=4)
        return code == 0

    # ── Fix #9: escribir texto SIN urllib.parse.quote ────────────────
    # Android TV acepta UTF-8 en "input text". El quote anterior enviaba
    # "canci%C3%B3n" literalmente en pantalla.

    def _escribir(self, texto):
        """
        Escribe texto en el campo activo de la TV.
        Divide por palabras y usa KEYCODE_SPACE para los espacios,
        enviando cada palabra directamente en UTF-8 sin codificar.
        """
        palabras = texto.split()
        for i, palabra in enumerate(palabras):
            # Sin URL encoding — Fix #9
            self._adb("shell", "input", "text", palabra)
            time.sleep(0.15)
            if i < len(palabras) - 1:
                self._keyevent(KEYCODES["espacio"])
                time.sleep(0.1)

    # ── Fix #8: auto-reconexión ──────────────────────────────────────

    def _auto_reconnect(self):
        """
        Verifica si la TV sigue conectada y reconecta automáticamente si no.
        Devuelve True si hay conexión activa, False si falló todo.
        """
        out, _, _ = self._adb("devices")
        # Fix: "device" in out siempre es True por el header "List of devices attached".
        # Verificar que la LÍNEA del dispositivo termine con "\tdevice".
        target = f"{self.tv_ip}:5555"
        if any(target in line and line.strip().endswith("device")
               for line in out.splitlines()):
            return True   # ya conectada

        # Intentar reconectar
        out2, _, code = self._adb("connect", f"{self.tv_ip}:5555", timeout=8)
        if code == 0 and ("connected" in out2 or "already" in out2):
            return True

        return False

    def _require_connection(self):
        if not self.tv_ip:
            return False
        return self._auto_reconnect()   # Fix #8

    def _no_connection_msg(self):
        return "Primero conecta la TV. Di: conectar tv <IP de la TV>"

    # ── Fix #2: espera adaptativa basada en uiautomator ─────────────

    def _dump_ui(self):
        """Lee el árbol de UI de la pantalla actual como XML."""
        self._adb("shell", "uiautomator", "dump", "/sdcard/ui_dump.xml")
        time.sleep(0.4)
        out, _, code = self._adb("shell", "cat", "/sdcard/ui_dump.xml")
        return out if (code == 0 and "<hierarchy" in out) else None

    def _esperar_ui_estable(self, timeout=12, pausa=1.0):
        """
        Fix #2 — espera hasta que el UI deje de cambiar durante 2 ciclos
        consecutivos, lo que indica que la pantalla ya cargó.
        Mucho mejor que un sleep fijo: funciona igual en TVs lentas y rápidas.
        """
        ui_prev    = ""
        estable    = 0
        inicio     = time.time()

        while time.time() - inicio < timeout:
            time.sleep(pausa)
            ui_actual = self._dump_ui() or ""

            if ui_actual and ui_actual == ui_prev:
                estable += 1
                if estable >= 2:
                    return True
            else:
                estable = 0

            ui_prev = ui_actual

        return False   # timeout, continuar de todas formas

    # ── uiautomator: buscar elemento en pantalla ─────────────────────

    def _buscar_elemento_ui(self, xml_str, texto_buscar):
        """
        Busca un elemento en el XML de uiautomator por texto parcial.
        Fix: revisa text= Y content-desc= porque íconos de búsqueda,
        perfiles y botones de nav-bar usan content-desc, no text.
        """
        if not xml_str:
            return None
        texto_lower = texto_buscar.lower()
        for attr in ("text", "content-desc"):
            patron = re.compile(
                rf'{attr}="([^"]*)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                re.IGNORECASE
            )
            for m in patron.finditer(xml_str):
                if texto_lower in m.group(1).lower():
                    x1, y1 = int(m.group(2)), int(m.group(3))
                    x2, y2 = int(m.group(4)), int(m.group(5))
                    return (x1 + x2) // 2, (y1 + y2) // 2
        return None

    def _tocar(self, cx, cy):
        self._adb("shell", "input", "tap", str(cx), str(cy))

    def _encontrar_capitulo(self, numero, intentos=14):
        """Busca y reproduce el episodio solicitado usando el foco real."""
        num = str(numero).strip()
        patron_numero = re.compile(
            rf"(?<!\d){re.escape(num)}(?!\d)", re.IGNORECASE
        )

        for _ in range(intentos):
            time.sleep(0.45)
            xml = self._dump_ui() or ""
            if not xml:
                self._keyevent(KEYCODES["abajo"])
                continue

            texto_focused = self._texto_elemento_focused(xml).strip()
            if texto_focused and patron_numero.search(texto_focused):
                # Evita que "5" haga match con títulos que casualmente
                # contienen el número; preferimos etiquetas de episodio.
                low = texto_focused.lower()
                es_episodio = any(k in low for k in [
                    "episode", "episodio", "ep.", "ep ", "capítulo", "capitulo", "cap "
                ]) or low == num
                if es_episodio:
                    self._keyevent(KEYCODES["ok"])
                    self._esperar_ui_estable(timeout=8, pausa=0.5)
                    return True

            self._keyevent(KEYCODES["abajo"])

        return False

    # ── Lanzar app ───────────────────────────────────────────────────

    def _obtener_package_real(self, nombre_app):
        """
        Resuelve el package real de una app en 2 pasos:
          1. Busca en TV_APPS y verifica que esté instalada en la TV.
          2. Si no, busca entre todos los paquetes instalados por nombre parcial.
        Esto soluciona que Vix/HBO tengan packages distintos según la región o versión.
        """
        nombre = nombre_app.lower().strip()

        # Paso 1: diccionario conocido + verificación real
        candidato = TV_APPS.get(nombre)
        if candidato:
            out, _, code = self._adb("shell", "pm", "list", "packages", candidato)
            if code == 0 and candidato in out:
                return candidato   # está instalado con ese package

        # Paso 2: buscar por nombre parcial entre todos los paquetes instalados
        out, _, code = self._adb("shell", "pm", "list", "packages")
        if code != 0:
            return candidato   # no se pudo listar, usar el del diccionario de todas formas

        terminos = nombre.replace(" ", "").replace("+", "")  # "hbomax" → "hbomax"
        primera = nombre.split()[0]                          # "hbo max" → "hbo"

        for linea in out.splitlines():
            pkg = linea.replace("package:", "").strip().lower()
            if terminos in pkg or primera in pkg:
                return linea.replace("package:", "").strip()

        return candidato   # fallback al diccionario aunque no esté instalado

    def listar_apps(self):
        """
        Lista TODAS las apps de terceros instaladas en la TV.
        Usa -3 para mostrar solo apps del usuario, no del sistema.
        """
        if not self._require_connection():
            return self._no_connection_msg()

        # -3 = solo apps instaladas por el usuario (no del sistema)
        out, _, code = self._adb("shell", "pm", "list", "packages", "-3")
        if code != 0 or not out:
            # fallback sin -3
            out, _, code = self._adb("shell", "pm", "list", "packages")
            if code != 0:
                return "No pude obtener la lista de apps de la TV."

        paquetes = sorted([
            l.replace("package:", "").strip()
            for l in out.splitlines() if l.strip()
        ])

        if not paquetes:
            return "No encontré apps instaladas."

        return "Apps instaladas en la TV:\n" + "\n".join(f"  • {p}" for p in paquetes)

    def buscar_package(self, termino):
        """
        Busca en TODOS los packages (incluyendo sistema) los que contengan el término.
        Si no encuentra nada, muestra los packages "sospechosos" (no son Android/Google/Sony base)
        para que el usuario identifique la app manualmente.
        """
        if not self._require_connection():
            return self._no_connection_msg()

        # Buscar en TODOS los packages (sin -3, incluye sistema)
        out, _, code = self._adb("shell", "pm", "list", "packages")
        if code != 0:
            return "No pude consultar los packages de la TV."

        todos = [l.replace("package:", "").strip() for l in out.splitlines() if l.strip()]

        if termino and termino.lower() not in ["todos", "all", "lista"]:
            termino_lower = termino.lower().strip()
            encontrados = [p for p in todos if termino_lower in p.lower()]

            if encontrados:
                return (
                    f"Packages con '{termino}':\n" +
                    "\n".join(f"  • {p}" for p in encontrados)
                )

            # No encontró nada con ese término → mostrar apps de terceros
            # filtrando los packages claramente del sistema
            sistema = {
                "com.android", "com.google", "android.",
                "com.sony", "jp.co.sony", "com.bravia",
                "com.qualcomm", "com.mediatek", "com.sec",
                "com.samsung", "org.chromium",
            }
            terceros = [
                p for p in todos
                if not any(p.startswith(s) for s in sistema)
            ]
            if not terceros:
                terceros = todos  # fallback: mostrar todo

            return (
                f"No encontré packages con '{termino}'.\n"
                f"Apps de terceros instaladas ({len(terceros)}):\n" +
                "\n".join(f"  • {p}" for p in sorted(terceros))
            )

        # Sin término → mostrar todo sin sistema
        sistema = {
            "com.android", "com.google", "android.",
            "com.sony", "jp.co.sony", "com.bravia",
            "com.qualcomm", "com.mediatek",
        }
        terceros = [p for p in todos if not any(p.startswith(s) for s in sistema)]
        return (
            f"Todos los packages de terceros ({len(terceros)}):\n" +
            "\n".join(f"  • {p}" for p in sorted(terceros))
        )

    def _monkey_launch(self, package):
        """
        Lanza una app con 3 estrategias en orden de confiabilidad.

        Fix: antes monkey iba PRIMERO y podía reportar 'Events injected: 1'
        sin que la app abriera realmente. Ahora va al final como respaldo.

        Estrategia 1 — am start -n (más confiable)
          pm resolve-activity obtiene el componente exacto (package/Activity)
          y am start lo lanza directamente. No hay ambigüedad.

        Estrategia 2 — monkey (respaldo)
          Útil si pm resolve-activity no devuelve nada.

        Estrategia 3 — am start sin categoría (Vix y apps atípicas)
          Para apps que no registran LEANBACK_LAUNCHER ni LAUNCHER estándar
          pero sí responden a un intent MAIN genérico.
        """
        categorias = [
            "android.intent.category.LEANBACK_LAUNCHER",  # Android TV
            "android.intent.category.LAUNCHER",            # Apps estándar
        ]

        # ── Estrategia 1: pm resolve-activity → am start -n ─────────────
        for cat in categorias:
            out, _, code = self._adb(
                "shell", "pm", "resolve-activity", "--brief",
                "-a", "android.intent.action.MAIN", "-c", cat, package
            )
            if code == 0:
                for linea in reversed(out.splitlines()):
                    linea = linea.strip()
                    if "/" in linea and package in linea:
                        out2, _, code2 = self._adb("shell", "am", "start", "-n", linea)
                        if code2 == 0 and "Error" not in out2 and "Exception" not in out2:
                            return True
                        break

        # ── Estrategia 2: monkey con categoría ──────────────────────────
        for cat in categorias:
            out, _, code = self._adb(
                "shell", "monkey", "-p", package, "-c", cat, "1"
            )
            if code == 0 and "Events injected: 1" in out:
                return True

        # ── Estrategia 3: am start sin categoría (Vix, apps atípicas) ───
        out, _, code = self._adb(
            "shell", "am", "start", "-p", package,
            "-a", "android.intent.action.MAIN"
        )
        if code == 0 and "Error" not in out and "Exception" not in out:
            return True

        return False

    # ── Patrón: buscar → reproducir con espera adaptativa ────────────

    def _buscar_y_reproducir(self, package, query, navegaciones_down=1):
        """
        Busca y reproduce contenido dentro de una app de Android TV.

        Fix crítico: KEYCODE_SEARCH (84) en Android TV abre el buscador del
        SISTEMA (Google Assistant), NO el de la app. Por eso Crunchyroll
        abría pero la búsqueda iba a Google y no encontraba nada.

        Nuevo flujo:
          1. Intent android.intent.action.SEARCH directo al package (sin UI de teclado)
          2. Si falla: abrir app + KEYCODE_SEARCH como antes (algunas apps sí lo manejan)
        """
        # ── Intento 1: intent SEARCH directo al package ──────────────────
        # Esto envía la búsqueda directamente a la app sin pasar por el
        # buscador del sistema. Funciona en apps que declaran SearchActivity.
        out, _, code = self._adb(
            "shell", "am", "start",
            "-a", "android.intent.action.SEARCH",
            "--es", "query", query,
            "-p", package
        )
        if code == 0 and "Error" not in out and "Exception" not in out:
            self._esperar_ui_estable(timeout=8)
            # Seleccionar primer resultado
            for _ in range(navegaciones_down):
                self._keyevent(KEYCODES["abajo"])
                time.sleep(0.3)
            self._keyevent(KEYCODES["ok"])
            return True, "ok"

        # ── Intento 2: abrir app + KEYCODE_SEARCH + escribir ────────────
        # Para apps que manejan el search key internamente (YouTube, etc.)
        ok = self._monkey_launch(package)
        if not ok:
            return False, f"No pude abrir {package}. ¿Está instalada en la TV?"

        self._esperar_ui_estable(timeout=10)
        self._keyevent(KEYCODES["search"])
        time.sleep(1.0)
        self._escribir(query)
        time.sleep(0.4)
        self._keyevent(KEYCODES["enter"])
        self._esperar_ui_estable(timeout=12)

        for _ in range(navegaciones_down):
            self._keyevent(KEYCODES["abajo"])
            time.sleep(0.3)
        self._keyevent(KEYCODES["ok"])

        return True, "ok"

    # ── Conexión ────────────────────────────────────────────────────

    def conectar(self, ip):
        if not ip:
            return "Dime la IP de la TV. Ejemplo: conectar tv 192.168.1.100"
        if not self._check_adb():
            return "No encontré ADB. Instálalo con: winget install Google.PlatformTools"
        self.tv_ip = ip
        out, _, code = self._adb("connect", f"{ip}:5555", timeout=10)
        if code == 0 and ("connected" in out or "already" in out):
            self.connected = True
            return f"Conectado a la TV en {ip}."
        self.tv_ip = None
        return (
            f"No pude conectarme a {ip}. "
            "Activa ADB por red: Ajustes → Preferencias del dispositivo "
            "→ Acerca de → Compilación (7 veces) → Depuración por red."
        )

    def desconectar(self):
        if not self.tv_ip: return "No hay TV conectada."
        self._adb("disconnect", f"{self.tv_ip}:5555")
        self.tv_ip = None
        self.connected = False
        return "TV desconectada."

    def estado(self):
        if not self.tv_ip: return "No hay TV conectada."
        return f"TV conectada en {self.tv_ip}." if self._auto_reconnect() else "TV desconectada."

    # ── Control básico ───────────────────────────────────────────────

    def encender_apagar(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["power"]); return "Comando encender/apagar enviado."

    def volumen(self, accion, veces=3):
        if not self._require_connection(): return self._no_connection_msg()
        kc = KEYCODES["volumen_up"] if accion == "up" else KEYCODES["volumen_down"]
        for _ in range(veces):
            self._keyevent(kc); time.sleep(0.15)
        return f"Volumen {'subido' if accion == 'up' else 'bajado'}."

    def mute(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["mute"]); return "Silenciado/dessilenciado."

    def play_pause(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["play_pause"]); return "Play/Pausa enviado."

    def siguiente(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["siguiente"]); return "Siguiente enviado."

    def anterior(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["anterior"]); return "Anterior enviado."

    def home(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["home"]); return "Enviado al inicio."

    def atras(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["back"]); return "Atrás enviado."

    # ── Controles de reproducción extendidos ─────────────────────────

    def adelantar(self):
        """Adelanta la reproducción (KEYCODE_MEDIA_FAST_FORWARD)."""
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["adelantar"])
        return "Adelantando reproducción."

    def retroceder(self):
        """Retrocede la reproducción (KEYCODE_MEDIA_REWIND)."""
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["retroceder"])
        return "Retrocediendo reproducción."

    def subtitulos(self):
        """Activa/desactiva subtítulos (KEYCODE_CAPTIONS = 175)."""
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["subtitulos"])
        return "Subtítulos alternados."

    def info_tv(self):
        """Muestra la pantalla de info de lo que se reproduce (KEYCODE_INFO = 165)."""
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["info"])
        return "Mostrando información."

    def canal_arriba(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["canal_arriba"])
        return "Canal siguiente."

    def canal_abajo(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["canal_abajo"])
        return "Canal anterior."

    def temporizador_apagado(self, minutos):
        """Apaga la TV después de N minutos en hilo daemon (no bloquea JARVIS)."""
        if not self._require_connection(): return self._no_connection_msg()
        import threading
        def _apagar():
            time.sleep(minutos * 60)
            self._keyevent(KEYCODES["power"])
        threading.Thread(target=_apagar, daemon=True).start()
        return f"La TV se apagará en {minutos} minuto{'s' if minutos != 1 else ''}."

    def abrir_app(self, nombre_app):
        if not self._require_connection(): return self._no_connection_msg()
        nombre = nombre_app.lower().strip()

        if "." in nombre:
            # Ya es un package directo
            package = nombre
        else:
            # Resolver el package real consultando la TV
            package = self._obtener_package_real(nombre)
            if not package:
                return (
                    f"No encontré '{nombre_app}' en la TV. "
                    f"Di 'listar apps tv' para ver qué tienes instalado."
                )

        ok = self._monkey_launch(package)
        if ok:
            return f"Abriendo {nombre_app}."

        # Fallback 1: am start con MAIN + LAUNCHER sin monkey
        out, _, code = self._adb(
            "shell", "am", "start",
            "-a", "android.intent.action.MAIN",
            "-c", "android.intent.category.LAUNCHER",
            "-p", package
        )
        if code == 0 and "Error" not in out and "Exception" not in out:
            return f"Abriendo {nombre_app}."

        # Fallback 2: URL scheme propio de la app (funciona para Crunchyroll y otras
        # apps que registran su propio scheme como crunchyroll://, youtube://, etc.)
        schemes = {
            "crunchyroll": "crunchyroll://browse",
            "youtube":     "youtube://",
            "netflix":     "netflix://",
            "spotify":     "spotify://",
            "twitch":      "twitch://",
        }
        scheme = schemes.get(nombre)
        if scheme:
            out2, _, code2 = self._adb(
                "shell", "am", "start",
                "-a", "android.intent.action.VIEW",
                "-d", scheme
            )
            if code2 == 0 and "Error" not in out2:
                return f"Abriendo {nombre_app}."

        return (
            f"No pude abrir {nombre_app} ({package}).\n"
            f"Di 'listar apps tv' para verificar si está instalada "
            f"o di '{nombre_app} com.paquete.real' con el package exacto."
        )

    # ── YouTube ─────────────────────────────────────────────────────

    def reproducir_youtube(self, query):
        if not self._require_connection(): return self._no_connection_msg()
        if not query: return self.abrir_app("youtube")
        ok, msg = self._buscar_y_reproducir(TV_APPS["youtube"], query)
        return f"Reproduciendo '{query}' en YouTube." if ok else msg

    # ── Crunchyroll ──────────────────────────────────────────────────

    # Perfil por defecto — cámbialo si el nombre en Crunchyroll es distinto
    _CRUNCHYROLL_PERFIL = "Imanolespinoza"

    def _seleccionar_perfil_crunchyroll(self, perfil=None):
        """
        Selecciona el perfil solo cuando realmente estamos en el selector.
        Si el perfil ya está activo, no mueve el D-pad ni vuelve a pulsar OK.
        """
        perfil = perfil or self._CRUNCHYROLL_PERFIL
        limite = time.time() + 10

        while time.time() < limite:
            xml = self._dump_ui() or ""
            estado = self._cr_xml_state(xml)

            if estado != "perfiles":
                # Si el selector ya desapareció, no tocar nada: el perfil
                # puede haber quedado activo o Crunchyroll ya avanzó al home.
                return True

            patron = re.compile(
                rf'(?:{re.escape(perfil)}.{{0,500}}(?:focused|selected)="true"'
                rf'|(?:focused|selected)="true".{{0,500}}{re.escape(perfil)})',
                re.IGNORECASE
            )
            if patron.search(xml):
                self._keyevent(KEYCODES["ok"])
                self._esperar_ui_estable(timeout=8, pausa=0.6)
                return True

            self._keyevent(KEYCODES["derecha"])
            time.sleep(0.35)

        return False

    def _texto_elemento_activo(self, xml):
        """Devuelve texto del elemento con focused o selected en True."""
        for attr in ['focused="true"', 'selected="true"']:
            for nodo in re.findall(
                rf'<node\s[^/]*?{re.escape(attr)}[^/]*/>',
                xml, re.IGNORECASE | re.DOTALL
            ):
                m = re.search(r'(?:text|content-desc)="([^"]+)"', nodo, re.IGNORECASE)
                if m and m.group(1).strip():
                    return m.group(1).strip()
        return ""

    def _texto_elemento_focused(self, xml):
        return self._texto_elemento_activo(xml)

    def _hay_campo_texto_activo(self):
        xml = self._dump_ui() or ""
        return "android.widget.EditText" in xml

    def _normalizar_texto_ui(self, texto):
        """Normaliza texto de uiautomator para comparar títulos sin ruido."""
        texto = html.unescape(str(texto or "")).lower()
        texto = re.sub(r"[\u2018\u2019\u201c\u201d]", "'", texto)
        texto = re.sub(r"[^a-záéíóúüñ0-9]+", " ", texto)
        return re.sub(r"\s+", " ", texto).strip()

    def _nodos_texto_ui(self, xml):
        """Extrae nodos text/content-desc con bounds y propiedades de foco."""
        if not xml:
            return []

        patron = re.compile(
            r"<node\b(?P<attrs>[^>]*?)\/?>",
            re.IGNORECASE | re.DOTALL
        )
        salida = []
        for m in patron.finditer(xml):
            attrs = m.group("attrs")

            tm = re.search(r'\btext="([^"]*)"', attrs, re.IGNORECASE)
            dm = re.search(r'\bcontent-desc="([^"]*)"', attrs, re.IGNORECASE)
            texto = (tm.group(1) if tm else "") or (dm.group(1) if dm else "")
            if not texto:
                continue

            bm = re.search(
                r'\bbounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                attrs, re.IGNORECASE
            )
            if not bm:
                continue

            x1, y1, x2, y2 = map(int, bm.groups())
            salida.append({
                "text": html.unescape(texto).strip(),
                "norm": self._normalizar_texto_ui(texto),
                "x": (x1 + x2) // 2,
                "y": (y1 + y2) // 2,
                "top": y1,
                "bottom": y2,
                "clickable": 'clickable="true"' in attrs.lower(),
                "focusable": 'focusable="true"' in attrs.lower(),
                "focused": 'focused="true"' in attrs.lower(),
                "selected": 'selected="true"' in attrs.lower(),
                "raw": attrs,
            })
        return salida

    def _resultados_busqueda_aparecieron(self, query):
        """
        Comprueba que la pantalla ya reaccionó a la búsqueda.
        Crunchyroll cambia su árbol de UI entre versiones, por lo que no
        exigimos que el título esté necesariamente en un nodo concreto.
        """
        xml = self._dump_ui() or ""
        if not xml:
            return False

        objetivo = self._normalizar_texto_ui(query)
        palabras = [p for p in objetivo.split() if len(p) >= 2]
        if not palabras:
            return False

        nodos = self._nodos_texto_ui(xml)

        # 1) Coincidencia del título en cualquier nodo visible.
        for nodo in nodos:
            texto = nodo["norm"]
            if all(p in texto for p in palabras):
                return True

        # 2) Crunchyroll puede renderizar la tarjeta como contenedor y
        # dejar el texto separado en varios nodos. Si cada palabra aparece
        # en la misma zona de resultados, también lo consideramos válido.
        zonas = []
        for nodo in nodos:
            if nodo["top"] < 120:
                continue
            for p in palabras:
                if p in nodo["norm"]:
                    zonas.append(nodo)
                    break
        if zonas:
            return True

        # 3) Si estamos claramente en la pantalla de resultados/búsqueda,
        # dejamos continuar al selector. El selector hará la comprobación
        # definitiva antes de pulsar OK.
        x = xml.lower()
        indicadores = (
            "resultados", "results", "search", "buscar",
            "android.widget.recyclerview", "lazycolumn"
        )
        return any(i in x for i in indicadores)

    def _coords_primer_resultado(self, xml, query):
        """
        Localiza el resultado real de Crunchyroll mediante text/content-desc.
        Se prioriza coincidencia exacta del título y después coincidencia por
        palabras. Nunca se toma la barra superior como resultado.
        """
        objetivo = self._normalizar_texto_ui(query)
        palabras = [p for p in objetivo.split() if len(p) >= 2]
        if not objetivo or not palabras:
            return None

        candidatos = []
        for nodo in self._nodos_texto_ui(xml):
            if nodo["bottom"] <= 180:
                continue

            texto = nodo["norm"]
            if not texto:
                continue

            coincidencias = sum(1 for p in palabras if p in texto)
            if coincidencias == 0:
                continue

            score = coincidencias * 10

            # Coincidencia exacta del título: máxima prioridad.
            if texto == objetivo:
                score += 100

            # Preferir tarjetas/elementos interactivos.
            if nodo["clickable"]:
                score += 15
            if nodo["focusable"]:
                score += 8
            if nodo["selected"] or nodo["focused"]:
                score += 5

            # Resultados normalmente están debajo de la barra de búsqueda.
            score += min(nodo["top"] // 100, 8)

            candidatos.append((score, nodo["top"], nodo["x"], nodo["y"], nodo["text"]))

        if not candidatos:
            return None

        candidatos.sort(key=lambda x: (-x[0], x[1]))
        return candidatos[0][2], candidatos[0][3]

    def _seleccionar_resultado_crunchyroll(self, query):
        """
        Selecciona el resultado de Crunchyroll.

        Crunchyroll puede usar RecyclerView, Compose o nodos sin clickable=true.
        Por eso no dependemos de una sola representación del XML.
        """
        objetivo = self._normalizar_texto_ui(query)
        palabras = [p for p in objetivo.split() if len(p) >= 2]
        if not objetivo:
            return False

        # A) Buscar directamente el texto completo o sus palabras.
        for intento in range(8):
            xml = self._dump_ui() or ""
            nodos = self._nodos_texto_ui(xml)

            candidatos = []
            for nodo in nodos:
                texto = nodo["norm"]
                if not texto:
                    continue

                coincidencias = sum(1 for p in palabras if p in texto)
                if coincidencias == 0:
                    continue

                # Ignorar controles superiores (barra de búsqueda).
                if nodo["bottom"] <= 100:
                    continue

                score = coincidencias * 100

                if texto == objetivo:
                    score += 1000
                elif all(p in texto for p in palabras):
                    score += 500

                if nodo["clickable"]:
                    score += 50
                if nodo["focusable"]:
                    score += 20
                if nodo["focused"]:
                    score += 30
                if nodo["selected"]:
                    score += 20

                # Los resultados suelen estar debajo de la barra.
                score += min(nodo["top"] // 80, 10)

                candidatos.append((score, nodo))

            if candidatos:
                candidatos.sort(key=lambda x: x[0], reverse=True)
                nodo = candidatos[0][1]
                self._tocar(nodo["x"], nodo["y"])
                time.sleep(0.8)
                self._keyevent(KEYCODES["ok"])
                self._esperar_ui_estable(timeout=8, pausa=0.5)
                return True

            # B) Si el XML tiene foco, recorrer con D-pad y comprobarlo.
            foco = self._texto_elemento_focused(xml)
            foco_norm = self._normalizar_texto_ui(foco)
            if foco_norm and (
                foco_norm == objetivo or all(p in foco_norm for p in palabras)
            ):
                self._keyevent(KEYCODES["ok"])
                self._esperar_ui_estable(timeout=8, pausa=0.5)
                return True

            # En Android TV, los resultados pueden quedar en la primera
            # fila. Probamos derecha y luego abajo sin volver al perfil.
            if intento < 3:
                self._keyevent(KEYCODES["derecha"])
            else:
                self._keyevent(KEYCODES["abajo"])
            time.sleep(0.45)

        # C) Último recurso: volver al principio de la zona de resultados
        # y avanzar por el foco. No asumimos que el primer elemento del XML
        # sea el resultado.
        for _ in range(12):
            xml = self._dump_ui() or ""
            foco = self._normalizar_texto_ui(self._texto_elemento_focused(xml))
            if foco and all(p in foco for p in palabras):
                self._keyevent(KEYCODES["ok"])
                self._esperar_ui_estable(timeout=8, pausa=0.5)
                return True
            self._keyevent(KEYCODES["derecha"])
            time.sleep(0.25)

        # Guardamos el XML final para diagnosticar cambios de UI de Crunchyroll.
        try:
            xml_final = self._dump_ui() or ""
            if xml_final:
                with open("jarvis_cr_debug.xml", "w", encoding="utf-8") as f:
                    f.write(xml_final)
        except Exception:
            pass
        return False

    def _navegar_busqueda_crunchyroll(self, query):
        """
        Abre el buscador de Crunchyroll y escribe SOLO el título.
        Evita borrar 50 veces sobre una pantalla no enfocada, que puede
        provocar navegación accidental por el menú de la TV.
        """
        query = self._normalizar_query_tv(query, plataforma="crunchyroll")
        if not query:
            return False

        def _escribir_en_busqueda():
            # La barra custom de Crunchyroll no siempre aparece como EditText.
            # Primero damos una oportunidad corta a la UI para enfocarse.
            xml = self._dump_ui() or ""
            if "android.widget.EditText" in xml:
                self._adb("shell", "input", "keyevent", "KEYCODE_MOVE_END")
            # Borrado acotado: solo después de haber confirmado que estamos
            # en una pantalla de búsqueda.
            for _ in range(40):
                self._keyevent(67)
            time.sleep(0.15)
            self._escribir(query)
            time.sleep(0.35)
            self._keyevent(KEYCODES["enter"])

        # Primero intentamos el deep link, pero no lo damos por bueno solo
        # porque Android acepte el intent: comprobamos que la UI cambió.
        q_enc = query.replace(" ", "+").replace("&", "%26")
        for link in [
            f"https://www.crunchyroll.com/search?q={q_enc}",
            f"crunchyroll://search?q={q_enc}",
        ]:
            self._adb(
                "shell", "am", "start",
                "-a", "android.intent.action.VIEW",
                "-d", link,
            )
            if self._esperar_ui_estable(timeout=6, pausa=0.6):
                xml = self._dump_ui() or ""
                if self._resultados_busqueda_aparecieron(query):
                    return True
                if self._cr_xml_state(xml) == "busqueda":
                    _escribir_en_busqueda()
                    if self._esperar_ui_estable(timeout=8, pausa=0.6):
                        return self._resultados_busqueda_aparecieron(query)

        # Fallback: localizar el botón Buscar y tocarlo UNA sola vez.
        xml = self._dump_ui() or ""
        coords_buscar = None
        for t in ["Buscar", "Search", "buscar", "búsqueda", "Búsqueda"]:
            coords_buscar = self._buscar_elemento_ui(xml, t)
            if coords_buscar:
                break

        if not coords_buscar:
            m = re.search(
                r'resource-id="[^"]*(?:search|buscar)[^"]*"'
                r'[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                xml, re.IGNORECASE
            )
            if m:
                coords_buscar = (
                    (int(m.group(1)) + int(m.group(3))) // 2,
                    (int(m.group(2)) + int(m.group(4))) // 2
                )

        if coords_buscar:
            self._tocar(*coords_buscar)
            time.sleep(1.2)
            _escribir_en_busqueda()
            self._esperar_ui_estable(timeout=8, pausa=0.6)
            return True

        # Último recurso: D-pad, pero solo una secuencia corta.
        for _ in range(3):
            self._keyevent(KEYCODES["abajo"])
            time.sleep(0.2)
        self._keyevent(KEYCODES["arriba"])
        time.sleep(0.3)
        self._keyevent(KEYCODES["derecha"])
        time.sleep(0.4)
        self._keyevent(KEYCODES["ok"])
        time.sleep(1.0)
        _escribir_en_busqueda()
        self._esperar_ui_estable(timeout=8, pausa=0.6)
        return True

    def reproducir_crunchyroll(self, query, capitulo=None, auto_play=False):
        """
        Flujo robusto de Crunchyroll:
        1) Conserva el contexto actual si ya estamos dentro de la app.
        2) Solo selecciona perfil cuando Android realmente muestra el selector.
        3) Normaliza el título antes de escribirlo.
        4) Verifica resultados antes de intentar seleccionar el anime.
        """
        if not self._require_connection():
            return self._no_connection_msg()

        package = self._obtener_package_real("crunchyroll")
        if not package:
            return "No encontré Crunchyroll en la TV. Di 'listar apps tv' para ver las apps instaladas."

        query = self._normalizar_query_tv(query, capitulo=capitulo, plataforma="crunchyroll")
        if not query:
            return "No entendí qué título quieres reproducir en Crunchyroll."

        # ── Detectar dónde estamos ANTES de lanzar nada ───────────────
        ya_en_cr = self._es_crunchyroll_activo(package)
        xml_actual = self._dump_ui() if ya_en_cr else ""
        estado = self._cr_xml_state(xml_actual)

        if not ya_en_cr:
            if not self._monkey_launch(package):
                return "No pude abrir Crunchyroll. Verifica que esté instalada en la TV."
            self._esperar_ui_estable(timeout=10, pausa=0.6)
            xml_actual = self._dump_ui() or ""
            estado = self._cr_xml_state(xml_actual)

        # Si aparece selector de perfiles, y SOLO entonces, elegir perfil.
        if estado == "perfiles":
            if not self._seleccionar_perfil_crunchyroll():
                return "Abrí Crunchyroll, pero no pude seleccionar el perfil."
            self._esperar_ui_estable(timeout=8, pausa=0.6)
            xml_actual = self._dump_ui() or ""
            estado = self._cr_xml_state(xml_actual)

        # Si ya está en resultados/búsqueda, no regresamos al perfil ni al home.
        # Intentamos comprobar si ya existe el título.
        if estado in ("busqueda", "desconocido"):
            if self._resultados_busqueda_aparecieron(query):
                resultados_listos = True
            else:
                resultados_listos = self._navegar_busqueda_crunchyroll(query)
        else:
            resultados_listos = self._navegar_busqueda_crunchyroll(query)

        if not resultados_listos:
            return f"Abrí Crunchyroll, pero no pude encontrar resultados para '{query}'."

        self._esperar_ui_estable(timeout=8, pausa=0.6)

        if not capitulo and not auto_play:
            return f"Buscando '{query}' en Crunchyroll."

        # ── Seleccionar el resultado del anime ────────────────────────
        if not self._seleccionar_resultado_crunchyroll(query):
            return (
                f"Encontré resultados para '{query}', pero no pude "
                f"seleccionar el anime automáticamente."
            )

        self._esperar_ui_estable(timeout=10, pausa=0.6)

        if not capitulo:
            # En la página del título, intentamos encontrar el botón de
            # reproducir antes de usar navegación genérica.
            xml = self._dump_ui() or ""
            coords_play = None
            for label in ["Reproducir", "Play", "Ver ahora", "Watch now"]:
                coords_play = self._buscar_elemento_ui(xml, label)
                if coords_play:
                    break
            if coords_play:
                self._tocar(*coords_play)
            else:
                for _ in range(3):
                    self._keyevent(KEYCODES["abajo"])
                    time.sleep(0.3)
                self._keyevent(KEYCODES["ok"])
            return f"Reproduciendo '{query}' en Crunchyroll."

        # ── Capítulo específico ─────────────────────────────────────
        # Damos como máximo 3 bajadas para entrar a episodios y luego
        # dejamos que _encontrar_capitulo decida por el foco real.
        for _ in range(3):
            self._keyevent(KEYCODES["abajo"])
            time.sleep(0.3)

        if self._encontrar_capitulo(capitulo, intentos=14):
            return f"Reproduciendo '{query}' capítulo {capitulo} en Crunchyroll."

        return (
            f"Abrí '{query}' en Crunchyroll, pero no localicé "
            f"el capítulo {capitulo} automáticamente."
        )

    # ── Búsqueda unificada (cualquier plataforma) ────────────────────

    def buscar_en_plataforma(self, plataforma, query, capitulo=None):
        if not self._require_connection(): return self._no_connection_msg()
        if not query and not plataforma: return "No entendí qué quieres ver ni dónde."

        if not plataforma or plataforma == "youtube":
            q = query + (f" capítulo {capitulo}" if capitulo else "")
            return self.reproducir_youtube(q)

        if plataforma == "crunchyroll":
            return self.reproducir_crunchyroll(query, capitulo)

        package = self._obtener_package_real(plataforma)
        if not package: return f"No encontré '{plataforma}' en la TV."
        if not query:   return self.abrir_app(plataforma)

        q = query + (f" episodio {capitulo}" if capitulo else "")
        ok, msg = self._buscar_y_reproducir(package, q)
        return f"Buscando '{q}' en {plataforma}." if ok else msg

    # ── Texto y navegación ───────────────────────────────────────────

    def navegar(self, direccion):
        if not self._require_connection(): return self._no_connection_msg()
        kc = KEYCODES.get(direccion)
        if not kc: return f"Dirección '{direccion}' no reconocida."
        self._keyevent(kc); return f"Movido {direccion}."

    def texto(self, texto):
        if not self._require_connection(): return self._no_connection_msg()
        self._escribir(texto); return f"Texto '{texto}' enviado."

    def reproducir_en_plataforma(self, plataforma, query, capitulo=None):
        """
        Busca el contenido Y auto-reproduce el primer resultado.
        Se llama cuando el usuario dice 'reproduce X en plataforma'.
        A diferencia de buscar_en_plataforma, después de mostrar resultados
        navega automáticamente al primer resultado y presiona OK.
        """
        if not self._require_connection(): return self._no_connection_msg()
        if not query: return "No entendí qué quieres reproducir."

        if not plataforma or plataforma == "youtube":
            q = query + (f" capítulo {capitulo}" if capitulo else "")
            return self.reproducir_youtube(q)

        if plataforma == "crunchyroll":
            return self.reproducir_crunchyroll(query, capitulo, auto_play=True)

        package = self._obtener_package_real(plataforma)
        if not package: return f"No encontré '{plataforma}' en la TV."
        q = query + (f" episodio {capitulo}" if capitulo else "")
        ok, msg = self._buscar_y_reproducir(package, q)
        return f"Reproduciendo '{q}' en {plataforma}." if ok else msg

    # ── Entry point ─────────────────────────────────────────────────

    def run(self, data):
        action     = data.get("action", "")
        extra      = data.get("extra", "")
        query      = data.get("query", "")
        app        = data.get("app", "")
        plataforma = data.get("plataforma", "")
        capitulo   = data.get("capitulo")
        veces      = int(data.get("veces", 3))

        if action == "conectar":      return self.conectar(extra)
        if action == "desconectar":   return self.desconectar()
        if action == "estado":        return self.estado()
        if action == "encender":      return self.encender_apagar()
        if action == "volumen_up":    return self.volumen("up", veces)
        if action == "volumen_down":  return self.volumen("down", veces)
        if action == "mute":          return self.mute()
        if action == "play_pause":    return self.play_pause()
        if action == "siguiente":     return self.siguiente()
        if action == "anterior":      return self.anterior()
        if action == "home":          return self.home()
        if action == "listar_apps":   return self.listar_apps()
        if action == "buscar_package": return self.buscar_package(query or extra)
        if action == "atras":         return self.atras()
        if action == "abrir_app":     return self.abrir_app(app or extra)
        if action == "youtube":       return self.reproducir_youtube(query)
        if action == "crunchyroll":   return self.reproducir_crunchyroll(query, capitulo)
        if action == "buscar":        return self.buscar_en_plataforma(plataforma, query, capitulo)
        if action == "reproducir":    return self.reproducir_en_plataforma(plataforma, query, capitulo)
        if action == "adelantar":    return self.adelantar()
        if action == "retroceder":   return self.retroceder()
        if action == "subtitulos":   return self.subtitulos()
        if action == "info_tv":      return self.info_tv()
        if action == "canal_arriba": return self.canal_arriba()
        if action == "canal_abajo":  return self.canal_abajo()
        if action == "temporizador": return self.temporizador_apagado(int(data.get("minutos", 30)))
        if action == "navegar":       return self.navegar(extra)
        if action == "texto":         return self.texto(query or extra)

        return "No reconocí ese comando para la TV."
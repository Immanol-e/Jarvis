"""
phone_skill.py — Control de celular Android via ADB over WiFi.

Diferencias clave respecto a tv_skill:
  - Android 11+: requiere emparejamiento con código (adb pair)
  - Android 10-: conectar vía USB una vez, luego adb tcpip 5555
  - Apps del celular tienen packages distintos a la TV
  - Capacidades extra: llamadas, SMS, notificaciones, screenshot, linterna
"""

import subprocess
import time
import re
import os


PHONE_APPS = {
    "whatsapp":    "com.whatsapp",
    "telegram":    "org.telegram.messenger",
    "instagram":   "com.instagram.android",
    "facebook":    "com.facebook.katana",
    "tiktok":      "com.zhiliaoapp.musically",
    "youtube":     "com.google.android.youtube",
    "spotify":     "com.spotify.music",
    "maps":        "com.google.android.apps.maps",
    "google maps": "com.google.android.apps.maps",
    "chrome":      "com.android.chrome",
    "camera":      "com.android.camera2",
    "camara":      "com.android.camera2",
    "galeria":     "com.google.android.apps.photos",
    "fotos":       "com.google.android.apps.photos",
    "ajustes":     "com.android.settings",
    "configuracion": "com.android.settings",
    "calculadora": "com.google.android.calculator",
    "gmail":       "com.google.android.gm",
    "netflix":     "com.netflix.mediaclient",
    "twitter":     "com.twitter.android",
    "x":           "com.twitter.android",
    "snapchat":    "com.snapchat.android",
    "discord":     "com.discord",
    "clock":       "com.google.android.deskclock",
    "reloj":       "com.google.android.deskclock",
}

KEYCODES = {
    "home":         3,
    "back":         4,
    "menu":         82,
    "power":        26,
    "volumen_up":   24,
    "volumen_down": 25,
    "mute":         164,
    "play_pause":   85,
    "siguiente":    87,
    "anterior":     88,
    "enter":        66,
    "camara":       27,
    "linterna":     None,
    "notif":        83,
    "recientes":    187,
}


class PhoneSkill:
    def __init__(self):
        # ── Cargar IP fija desde config ──────────────────────────────────────
        # Ya no necesitas decir "conectar celular <IP>" cada vez.
        # JARVIS intenta conectarse solo al arrancar usando la IP del router.
        try:
            from config.tv_config import PHONE_IP, PHONE_PORT
            self.phone_ip   = PHONE_IP
            self.phone_port = PHONE_PORT
        except (ImportError, AttributeError):
            self.phone_ip   = None
            self.phone_port = None

        self.connected           = False
        self._linterna_encendida = False

        # Intentar conectar al arrancar JARVIS
        if self.phone_ip and self.phone_port:
            ok = self._auto_reconnect()
            if ok:
                print(f"[PhoneSkill] Celular conectado en {self.phone_ip}:{self.phone_port}")
            else:
                print(f"[PhoneSkill] Celular no disponible en {self.phone_ip} — "
                      f"se conectará automáticamente cuando esté en la red.")

    # ── ADB base ─────────────────────────────────────────────────────────────
    def _adb(self, *args, timeout=10):
        if self.phone_ip and self.phone_port:
            base = ["adb", "-s", f"{self.phone_ip}:{self.phone_port}"]
        else:
            base = ["adb"]

        try:
            r = subprocess.run(
                base + list(args),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout
            )
            return r.stdout.strip(), r.stderr.strip(), r.returncode
        except FileNotFoundError:
            return "", "ADB no encontrado.", 1
        except subprocess.TimeoutExpired:
            return "", "Timeout: el dispositivo no respondió.", 1

    def _keyevent(self, keycode):
        self._adb("shell", "input", "keyevent", str(keycode))

    def _check_adb(self):
        _, _, code = self._adb("version", timeout=4)
        return code == 0

    def _auto_reconnect(self):
        if not self.phone_ip or not self.phone_port:
            return False

        out, _, _ = self._adb("devices")

        target = f"{self.phone_ip}:{self.phone_port}"
        if any(target in line and line.strip().endswith("device")
               for line in out.splitlines()):
            return True

        out2, _, code = self._adb(
            "connect",
            f"{self.phone_ip}:{self.phone_port}",
            timeout=8
        )

        return code == 0 and (
            "connected" in out2 or
            "already connected" in out2
        )

    def _require_connection(self):
        return self.phone_ip is not None and self._auto_reconnect()

    def _no_connection_msg(self):
        return "Primero conecta el celular. Di: conectar celular <IP>"

    # ── Conexión ──────────────────────────────────────────────────────────────
    def conectar(self, ip, puerto=None):
        if not ip:
            return "Dime la IP del celular."

        if not self._check_adb():
            return "No encontré ADB."

        if puerto is None:
            puerto = self.phone_port

        if not puerto:
            return (
                "Necesito también el puerto de ADB.\n"
                "Ve a Depuración inalámbrica y dime la 'Dirección IP y puerto'.\n"
                "Ejemplo: conectar celular 192.168.1.50 45497"
            )

        out, err, code = self._adb(
            "connect",
            f"{ip}:{puerto}",
            timeout=10
        )

        if code == 0 and ("connected" in out or "already connected" in out):
            self.phone_ip   = ip
            self.phone_port = puerto
            self.connected  = True
            return f"Celular conectado en {ip}:{puerto}"

        return f"No pude conectar.\n{err or out}"

    def emparejar(self, ip, puerto, codigo):
        if not self._check_adb():
            return "No encontré ADB en tu PC."

        out, err, code = self._adb(
            "pair",
            f"{ip}:{puerto}",
            codigo,
            timeout=20
        )

        if code != 0 or "Successfully paired" not in out:
            return f"No pude emparejar el celular.\nError: {err or out}"

        time.sleep(2)

        puerto_conexion = None
        for _ in range(5):
            out, _, _ = self._adb("devices")
            for linea in out.splitlines():
                m = re.match(rf"({re.escape(ip)}):(\d+)\s+device", linea.strip())
                if m:
                    puerto_conexion = m.group(2)
                    break
            if puerto_conexion:
                break
            time.sleep(1)

        if puerto_conexion is None:
            self._adb("connect", ip, timeout=5)
            time.sleep(1)
            out, _, _ = self._adb("devices")
            for linea in out.splitlines():
                m = re.match(rf"({re.escape(ip)}):(\d+)\s+device", linea.strip())
                if m:
                    puerto_conexion = m.group(2)
                    break

        if puerto_conexion is None:
            self.phone_ip = ip
            return (
                "Celular emparejado correctamente.\n\n"
                "No pude detectar el puerto de conexión automáticamente.\n"
                "En el teléfono abre 'Depuración inalámbrica' y dime el valor "
                "de 'Dirección IP y puerto' (ej: 192.168.1.50 45497).\n"
                "Luego di: conectar celular <IP> <PUERTO>"
            )

        self.phone_ip   = ip
        self.phone_port = puerto_conexion
        self.connected  = True
        return f"Celular emparejado y conectado en {ip}:{puerto_conexion}"

    def preparar_usb(self):
        out, err, code = self._adb("tcpip", "5555", timeout=8)
        if code == 0:
            return (
                "ADB por red activado en el celular. "
                "Ahora desconecta el cable USB y di: conectar celular <IP del celular>"
            )
        return f"No pude activar ADB por red. ¿Está conectado el cable USB? Error: {err}"

    def desconectar(self):
        if not self.phone_ip:
            return "No hay celular conectado."
        puerto = self.phone_port or "5555"
        self._adb("disconnect", f"{self.phone_ip}:{puerto}")
        self.phone_ip   = None
        self.phone_port = None
        self.connected  = False
        return "Celular desconectado."

    def estado(self):
        if not self.phone_ip:
            return "No hay celular conectado. Di: conectar celular <IP>"
        return (f"Celular conectado en {self.phone_ip}."
                if self._auto_reconnect()
                else "Celular desconectado.")

    # ── Información del dispositivo ───────────────────────────────────────────
    def info(self):
        if not self._require_connection():
            return self._no_connection_msg()

        modelo, _, _      = self._adb("shell", "getprop", "ro.product.model")
        android, _, _     = self._adb("shell", "getprop", "ro.build.version.release")
        bateria_raw, _, _ = self._adb("shell", "dumpsys", "battery")

        nivel = "?"
        for linea in bateria_raw.splitlines():
            if "level:" in linea:
                nivel = linea.split(":")[1].strip()
                break

        return (
            f"Celular: {modelo or 'desconocido'}\n"
            f"Android: {android or '?'}\n"
            f"Batería: {nivel}%"
        )

    # ── Pantalla ──────────────────────────────────────────────────────────────
    def encender_pantalla(self):
        if not self._require_connection(): return self._no_connection_msg()
        out, _, _ = self._adb("shell", "dumpsys", "power")
        if "mWakefulness=Asleep" in out or "mWakefulness=Dozing" in out:
            self._keyevent(KEYCODES["power"])
            time.sleep(0.5)
            self._adb("shell", "input", "swipe", "500", "1500", "500", "500", "300")
        return "Pantalla encendida."

    def apagar_pantalla(self):
        if not self._require_connection(): return self._no_connection_msg()
        out, _, _ = self._adb("shell", "dumpsys", "power")
        if "mWakefulness=Awake" in out:
            self._keyevent(KEYCODES["power"])
        return "Pantalla apagada."

    def screenshot(self):
        if not self._require_connection(): return self._no_connection_msg()
        ts       = int(time.time())
        ruta_cel = f"/sdcard/jarvis_screenshot_{ts}.png"
        ruta_pc  = os.path.expanduser(f"~/Desktop/screenshot_{ts}.png")

        self._adb("shell", "screencap", "-p", ruta_cel)
        time.sleep(0.5)
        out, err, code = self._adb("pull", ruta_cel, ruta_pc, timeout=15)
        self._adb("shell", "rm", ruta_cel)

        if code == 0:
            return f"Screenshot guardado en el escritorio como screenshot_{ts}.png"
        return f"No pude tomar el screenshot. Error: {err}"

    # ── Volumen ───────────────────────────────────────────────────────────────
    def volumen(self, accion, veces=3):
        if not self._require_connection(): return self._no_connection_msg()
        kc  = KEYCODES["volumen_up"] if accion == "up" else KEYCODES["volumen_down"]
        adj = "raise" if accion == "up" else "lower"
        for _ in range(veces):
            self._keyevent(kc)
            time.sleep(0.12)
        for _ in range(veces):
            self._adb("shell", "media", "volume", "--stream", "3", "--adj", adj)
        return f"Volumen {'subido' if accion == 'up' else 'bajado'} en el celular."

    def silenciar(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["mute"])
        self._adb("shell", "media", "volume", "--stream", "2", "--set", "0")
        return "Celular silenciado."

    def vibrar(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._adb("shell", "media", "volume", "--stream", "2", "--set", "0")
        self._adb("shell", "settings", "put", "system", "vibrate_when_ringing", "1")
        return "Modo vibración activado."

    def sonido_normal(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._adb("shell", "media", "volume", "--stream", "2", "--set", "7")
        return "Sonido normal restaurado."

    # ── Llamadas ──────────────────────────────────────────────────────────────
    def llamar(self, numero):
        if not self._require_connection(): return self._no_connection_msg()
        numero_limpio = re.sub(r"[^\d+]", "", numero)
        if not numero_limpio:
            return f"Número inválido: '{numero}'"
        out, err, code = self._adb(
            "shell", "am", "start",
            "-a", "android.intent.action.CALL",
            "-d", f"tel:{numero_limpio}"
        )
        return f"Llamando al {numero_limpio}." if code == 0 else f"No pude iniciar la llamada. Error: {err}"

    def marcar(self, numero):
        if not self._require_connection(): return self._no_connection_msg()
        numero_limpio = re.sub(r"[^\d+]", "", numero)
        out, err, code = self._adb(
            "shell", "am", "start",
            "-a", "android.intent.action.DIAL",
            "-d", f"tel:{numero_limpio}"
        )
        return f"Marcador abierto con {numero_limpio}." if code == 0 else f"Error: {err}"

    def colgar(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._adb("shell", "input", "keyevent", "6")
        return "Llamada colgada."

    # ── SMS ───────────────────────────────────────────────────────────────────
    def enviar_sms(self, numero, mensaje):
        if not self._require_connection(): return self._no_connection_msg()
        numero_limpio = re.sub(r"[^\d+]", "", numero)
        if not numero_limpio:
            return "Necesito un número de teléfono válido."
        out, err, code = self._adb(
            "shell", "am", "start",
            "-a", "android.intent.action.SENDTO",
            "-d", f"smsto:{numero_limpio}",
            "--es", "sms_body", mensaje,
            "--ez", "exit_on_sent", "true"
        )
        return (f"Mensaje a {numero_limpio} listo para enviar: '{mensaje}'"
                if code == 0 else f"Error abriendo mensajes: {err}")

    # ── Apps ──────────────────────────────────────────────────────────────────
    def abrir_app(self, nombre_app):
        if not self._require_connection(): return self._no_connection_msg()
        nombre  = nombre_app.lower().strip()
        package = PHONE_APPS.get(nombre)

        if not package:
            if "." in nombre:
                package = nombre
            else:
                package = self._buscar_package_instalado(nombre)
                if not package:
                    return (f"No conozco la app '{nombre_app}'. "
                            f"Puedes decirme el package directo, ej: com.whatsapp")

        out, err, code = self._adb(
            "shell", "monkey", "-p", package,
            "-c", "android.intent.category.LAUNCHER", "1"
        )
        if code == 0 and "Events injected: 1" in out:
            return f"Abriendo {nombre_app} en el celular."

        out2, err2, code2 = self._adb(
            "shell", "am", "start",
            "-a", "android.intent.action.MAIN",
            "-c", "android.intent.category.LAUNCHER",
            package
        )
        return (f"Abriendo {nombre_app} en el celular."
                if code2 == 0
                else f"No pude abrir {nombre_app}. ¿Está instalada?")

    def _buscar_package_instalado(self, termino):
        out, _, code = self._adb("shell", "pm", "list", "packages")
        if code != 0:
            return None
        for linea in out.splitlines():
            pkg = linea.replace("package:", "").strip()
            if termino.lower() in pkg.lower():
                return pkg
        return None

    # ── WhatsApp ──────────────────────────────────────────────────────────────
    def whatsapp_mensaje(self, numero, mensaje):
        if not self._require_connection(): return self._no_connection_msg()
        import urllib.parse
        numero_limpio = re.sub(r"[^\d]", "", numero)
        if not numero_limpio:
            return "Necesito un número de teléfono para enviar el mensaje."
        mensaje_enc = urllib.parse.quote(mensaje, safe="")
        out, err, code = self._adb(
            "shell", "am", "start",
            "-a", "android.intent.action.VIEW",
            "-d", f"https://api.whatsapp.com/send?phone={numero_limpio}&text={mensaje_enc}"
        )
        if code != 0:
            return f"No pude abrir WhatsApp: {err}"
        time.sleep(3.5)
        self._keyevent(KEYCODES["enter"])
        return f"Mensaje enviado a +{numero_limpio}: '{mensaje}'"

    # ── Notificaciones ────────────────────────────────────────────────────────
    def ver_notificaciones(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["notif"])
        return "Panel de notificaciones abierto."

    # ── Linterna ──────────────────────────────────────────────────────────────
    def linterna(self, encender=True):
        if not self._require_connection(): return self._no_connection_msg()

        if self._linterna_encendida == encender:
            return f"La linterna ya estaba {'encendida' if encender else 'apagada'}."

        modo = "true" if encender else "false"
        out, err, code = self._adb("shell", "cmd", "camera", "set-torch-mode", "0", modo)
        if code == 0 and "error" not in out.lower() and "error" not in err.lower():
            self._linterna_encendida = encender
            return f"Linterna {'encendida' if encender else 'apagada'}."

        tiles = [
            "com.android.systemui.qs.tiles.FlashlightTile",
            "com.android.systemui.qs.tiles.Torch",
            "com.samsung.systemui.qs.tiles.FlashlightTile",
        ]
        for tile in tiles:
            out, err, code = self._adb("shell", "cmd", "statusbar", "tile-click", tile)
            if code == 0 and "error" not in err.lower():
                self._linterna_encendida = encender
                return f"Linterna {'encendida' if encender else 'apagada'}."

        estado = "1" if encender else "0"
        for ruta in ["/sys/class/leds/flashlight/brightness",
                     "/sys/class/leds/torch-light/brightness",
                     "/sys/class/leds/led:flash_torch/brightness"]:
            out, err, code = self._adb("shell", f"echo {estado} > {ruta} 2>/dev/null && echo ok")
            if code == 0 and "ok" in out:
                self._linterna_encendida = encender
                return f"Linterna {'encendida' if encender else 'apagada'}."

        return (f"No pude {'encender' if encender else 'apagar'} la linterna.\n"
                f"Actívala manualmente desde el panel de notificaciones.")

    # ── Reproducción ──────────────────────────────────────────────────────────
    def play_pause(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["play_pause"])
        return "Play/Pausa enviado al celular."

    def siguiente(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["siguiente"])
        return "Siguiente canción."

    def anterior(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["anterior"])
        return "Canción anterior."

    # ── Navegación ────────────────────────────────────────────────────────────
    def home(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["home"])
        return "Inicio del celular."

    def atras(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["back"])
        return "Atrás en el celular."

    def recientes(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._keyevent(KEYCODES["recientes"])
        return "Apps recientes abiertas."

    def texto(self, texto):
        if not self._require_connection(): return self._no_connection_msg()
        palabras = texto.split()
        for i, p in enumerate(palabras):
            self._adb("shell", "input", "text", p)
            time.sleep(0.1)
            if i < len(palabras) - 1:
                self._keyevent(62)
        return f"Texto '{texto}' enviado al celular."

    # ── Buscar package ────────────────────────────────────────────────────────
    def buscar_package(self, termino):
        if not self._require_connection(): return self._no_connection_msg()
        out, _, code = self._adb("shell", "pm", "list", "packages")
        if code != 0:
            return "No pude listar los packages del celular."
        encontrados = [
            l.replace("package:", "").strip()
            for l in out.splitlines()
            if termino.lower() in l.lower()
        ]
        if not encontrados:
            return f"No encontré packages con '{termino}' en el celular."
        return f"Packages con '{termino}':\n" + "\n".join(f"  {p}" for p in encontrados)

    # ── Conectividad ──────────────────────────────────────────────────────────
    def wifi(self, activar=True):
        if not self._require_connection(): return self._no_connection_msg()
        self._adb("shell", "svc", "wifi", "enable" if activar else "disable")
        return f"WiFi {'activado' if activar else 'desactivado'}."

    def bluetooth(self, activar=True):
        if not self._require_connection(): return self._no_connection_msg()
        self._adb("shell", "svc", "bluetooth", "enable" if activar else "disable")
        return f"Bluetooth {'activado' if activar else 'desactivado'}."

    def datos_moviles(self, activar=True):
        if not self._require_connection(): return self._no_connection_msg()
        self._adb("shell", "svc", "data", "enable" if activar else "disable")
        return f"Datos móviles {'activados' if activar else 'desactivados'}."

    def modo_avion(self, activar=True):
        if not self._require_connection(): return self._no_connection_msg()
        val   = "1" if activar else "0"
        state = "true" if activar else "false"
        self._adb("shell", "settings", "put", "global", "airplane_mode_on", val)
        self._adb("shell", "am", "broadcast",
                  "-a", "android.intent.action.AIRPLANE_MODE",
                  "--ez", "state", state)
        return f"Modo avión {'activado' if activar else 'desactivado'}."

    # ── Pantalla y apariencia ─────────────────────────────────────────────────
    def brillo(self, nivel):
        if not self._require_connection(): return self._no_connection_msg()
        val = max(0, min(255, int(nivel * 255 / 100)))
        self._adb("shell", "settings", "put", "system", "screen_brightness_mode", "0")
        self._adb("shell", "settings", "put", "system", "screen_brightness", str(val))
        return f"Brillo ajustado al {nivel}%."

    def brillo_auto(self, activar=True):
        if not self._require_connection(): return self._no_connection_msg()
        self._adb("shell", "settings", "put", "system",
                  "screen_brightness_mode", "1" if activar else "0")
        return f"Brillo automático {'activado' if activar else 'desactivado'}."

    def modo_oscuro(self, activar=True):
        if not self._require_connection(): return self._no_connection_msg()
        self._adb("shell", "cmd", "uimode", "night", "yes" if activar else "no")
        return f"Modo oscuro {'activado' if activar else 'desactivado'}."

    def rotacion(self, bloquear=True):
        if not self._require_connection(): return self._no_connection_msg()
        self._adb("shell", "settings", "put", "system",
                  "accelerometer_rotation", "0" if bloquear else "1")
        return f"Rotación {'bloqueada' if bloquear else 'desbloqueada'}."

    # ── No Molestar ───────────────────────────────────────────────────────────
    def dnd(self, activar=True):
        if not self._require_connection(): return self._no_connection_msg()
        self._adb("shell", "cmd", "notification",
                  "set_dnd", "on" if activar else "off")
        return f"No Molestar {'activado' if activar else 'desactivado'}."

    # ── Alarma ────────────────────────────────────────────────────────────────
    def alarma(self, hora, minutos=0, etiqueta="Alarma"):
        if not self._require_connection(): return self._no_connection_msg()

        args_base = [
            "--ei", "android.intent.extra.alarm.HOUR",    str(hora),
            "--ei", "android.intent.extra.alarm.MINUTES", str(minutos),
            "--es", "android.intent.extra.alarm.MESSAGE", etiqueta,
        ]

        out, err, code = self._adb(
            "shell", "am", "start", "-p", "com.miui.clock",
            "-a", "android.intent.action.SET_ALARM",
            *args_base,
            "--ez", "android.intent.extra.alarm.SKIP_UI", "true",
        )
        if code == 0 and "Error" not in out and "Exception" not in out:
            return f"Alarma configurada para las {hora:02d}:{minutos:02d} — '{etiqueta}'."

        out, err, code = self._adb(
            "shell", "am", "start",
            "-a", "android.intent.action.SET_ALARM",
            *args_base,
            "--ez", "android.intent.extra.alarm.SKIP_UI", "true",
        )
        if code == 0 and "Error" not in out and "Exception" not in out:
            return f"Alarma configurada para las {hora:02d}:{minutos:02d} — '{etiqueta}'."

        self._adb("shell", "am", "start",
                  "-a", "android.intent.action.SET_ALARM", *args_base)
        return (f"Se abrió el reloj para las {hora:02d}:{minutos:02d}. "
                f"Confirma la alarma en pantalla.")

    # ── Batería ───────────────────────────────────────────────────────────────
    def bateria_saver(self, activar=True):
        if not self._require_connection(): return self._no_connection_msg()
        self._adb("shell", "settings", "put", "global",
                  "low_power", "1" if activar else "0")
        return f"Ahorro de batería {'activado' if activar else 'desactivado'}."

    def reiniciar_cel(self):
        if not self._require_connection(): return self._no_connection_msg()
        self._adb("shell", "reboot")
        self.phone_ip   = None
        self.phone_port = None
        self.connected  = False
        return "Reiniciando celular... Vuelve a conectarlo en unos segundos."

    # ── Router principal ──────────────────────────────────────────────────────
    def run(self, data):
        action  = data.get("action", "")
        extra   = data.get("extra", "")
        query   = data.get("query", "")
        numero  = data.get("numero", "")
        mensaje = data.get("mensaje", "")
        app     = data.get("app", "")
        veces   = int(data.get("veces", 3))
        ip      = data.get("ip", "")
        puerto  = data.get("puerto", "")
        codigo  = data.get("codigo", "")

        if action == "conectar":          return self.conectar(ip or extra, puerto or None)
        if action == "emparejar":         return self.emparejar(ip, puerto, codigo)
        if action == "preparar_usb":      return self.preparar_usb()
        if action == "desconectar":       return self.desconectar()
        if action == "estado":            return self.estado()
        if action == "info":              return self.info()
        if action == "encender_pantalla": return self.encender_pantalla()
        if action == "apagar_pantalla":   return self.apagar_pantalla()
        if action == "screenshot":        return self.screenshot()
        if action == "volumen_up":        return self.volumen("up", veces)
        if action == "volumen_down":      return self.volumen("down", veces)
        if action == "silenciar":         return self.silenciar()
        if action == "vibrar":            return self.vibrar()
        if action == "sonido_normal":     return self.sonido_normal()
        if action == "llamar":            return self.llamar(numero or extra)
        if action == "marcar":            return self.marcar(numero or extra)
        if action == "colgar":            return self.colgar()
        if action == "sms":               return self.enviar_sms(numero, mensaje)
        if action == "whatsapp":          return self.whatsapp_mensaje(numero, mensaje)
        if action == "abrir_app":         return self.abrir_app(app or extra)
        if action == "notificaciones":    return self.ver_notificaciones()
        if action == "linterna_on":       return self.linterna(True)
        if action == "linterna_off":      return self.linterna(False)
        if action == "play_pause":        return self.play_pause()
        if action == "siguiente":         return self.siguiente()
        if action == "anterior":          return self.anterior()
        if action == "home":              return self.home()
        if action == "atras":             return self.atras()
        if action == "recientes":         return self.recientes()
        if action == "texto":             return self.texto(query or extra)
        if action == "buscar_package":    return self.buscar_package(query or extra)
        if action == "wifi_on":           return self.wifi(True)
        if action == "wifi_off":          return self.wifi(False)
        if action == "bt_on":             return self.bluetooth(True)
        if action == "bt_off":            return self.bluetooth(False)
        if action == "datos_on":          return self.datos_moviles(True)
        if action == "datos_off":         return self.datos_moviles(False)
        if action == "avion_on":          return self.modo_avion(True)
        if action == "avion_off":         return self.modo_avion(False)
        if action == "brillo":            return self.brillo(int(data.get("nivel", 50)))
        if action == "brillo_auto_on":    return self.brillo_auto(True)
        if action == "brillo_auto_off":   return self.brillo_auto(False)
        if action == "dark_on":           return self.modo_oscuro(True)
        if action == "dark_off":          return self.modo_oscuro(False)
        if action == "rotacion_on":       return self.rotacion(True)
        if action == "rotacion_off":      return self.rotacion(False)
        if action == "dnd_on":            return self.dnd(True)
        if action == "dnd_off":           return self.dnd(False)
        if action == "alarma":            return self.alarma(
                                              int(data.get("hora", 7)),
                                              int(data.get("minutos", 0)),
                                              data.get("etiqueta", "Alarma"))
        if action == "bateria_saver_on":  return self.bateria_saver(True)
        if action == "bateria_saver_off": return self.bateria_saver(False)
        if action == "reiniciar_cel":     return self.reiniciar_cel()

        return "No reconocí ese comando para el celular."
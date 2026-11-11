"""
skills/network_skill.py — Escaneo de dispositivos en la red local
No requiere ningún pip install — solo librería estándar de Python.
Funciona en Windows, Linux y macOS.

Comandos que entiende JARVIS:
  "escanea la red"
  "¿quién está conectado a mi red?"
  "¿cuántos dispositivos hay en mi wifi?"
  "¿quién está en mi wifi?"
"""

import socket
import subprocess
import re
import platform
from concurrent.futures import ThreadPoolExecutor, as_completed


# ── OUI: prefijos MAC conocidos para identificar fabricantes ──────────────
# Solo los más comunes en redes domésticas
_OUI = {
    "D8:07:B6": "Xiaomi",      "F4:F5:DB": "Xiaomi",
    "28:6C:07": "Xiaomi",      "9C:99:A0": "Xiaomi",
    "AC:C1:EE": "Xiaomi",      "78:11:DC": "Xiaomi",
    "50:64:2B": "Samsung",     "8C:77:12": "Samsung",
    "FC:00:12": "Samsung",     "CC:07:AB": "Apple",
    "3C:22:FB": "Apple",       "A4:C3:F0": "Apple",
    "18:65:90": "Apple",       "60:03:08": "Apple",
    "DC:2B:2A": "Google",      "F4:F5:E8": "Google",
    "48:D6:D5": "Google",      "54:60:09": "Amazon",
    "44:65:0D": "Amazon",      "F0:D2:F1": "Amazon",
    "B8:27:EB": "Raspberry Pi","DC:A6:32": "Raspberry Pi",
    "E4:5F:01": "Raspberry Pi",
}


class NetworkSkill:

    def __init__(self):
        self._ultimo_scan: list = []

    # ── Detectar IP local ─────────────────────────────────────────────────
    def _ip_local(self) -> str | None:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return None

    # ── Ping a una IP ─────────────────────────────────────────────────────
    def _ping(self, ip: str) -> bool:
        sistema = platform.system()
        try:
            if sistema == "Windows":
                cmd = ["ping", "-n", "1", "-w", "500", ip]
            else:
                cmd = ["ping", "-c", "1", "-W", "1", ip]
            r = subprocess.run(cmd, capture_output=True, timeout=2)
            return r.returncode == 0
        except Exception:
            return False

    # ── Leer tabla ARP ────────────────────────────────────────────────────
    def _arp_tabla(self) -> dict:
        """Retorna {ip: mac} de todos los dispositivos en la tabla ARP."""
        try:
            out = subprocess.check_output(
                "arp -a", shell=True,
                encoding="utf-8", errors="replace"
            )
        except Exception:
            return {}

        dispositivos = {}
        for linea in out.splitlines():
            # Windows:  "  192.168.1.5    aa-bb-cc-dd-ee-ff    dinámico"
            # Linux:    "192.168.1.5 ether aa:bb:cc:dd:ee:ff C eth0"
            m = re.search(
                r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
                r".*?"
                r"([0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-]"
                r"[0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-]"
                r"[0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2})",
                linea
            )
            if m:
                ip  = m.group(1)
                mac = m.group(2).replace("-", ":").upper()
                # Ignorar broadcast y multicast
                if not ip.endswith(".255") and mac not in ("FF:FF:FF:FF:FF:FF", "00:00:00:00:00:00"):
                    dispositivos[ip] = mac
        return dispositivos

    # ── Resolver hostname ─────────────────────────────────────────────────
    def _hostname(self, ip: str) -> str:
        try:
            return socket.gethostbyaddr(ip)[0].split(".")[0]
        except Exception:
            return ""

    # ── Identificar tipo de dispositivo ──────────────────────────────────
    def _identificar(self, ip: str, mac: str, hostname: str, ip_local: str) -> str:
        """Intenta dar un nombre descriptivo al dispositivo."""
        # La propia PC
        if ip == ip_local:
            return "Esta PC"

        # Router: suele ser la .1 o .254 de la subred
        partes = ip.rsplit(".", 1)
        ultimo = int(partes[1]) if partes[1].isdigit() else -1
        if ultimo in (1, 254):
            return "Router"

        # Por OUI (primeros 3 bytes de la MAC)
        oui = mac[:8].upper()
        fabricante = _OUI.get(oui, "")

        # Por hostname
        h = hostname.lower()
        if any(x in h for x in ["iphone", "ipad"]):
            return "iPhone/iPad"
        if any(x in h for x in ["android", "samsung", "xiaomi",
                                  "huawei", "pixel", "oneplus", "oppo", "motorola"]):
            return "Android"
        if any(x in h for x in ["laptop", "notebook", "pc", "desktop",
                                  "imac", "macbook", "windows"]):
            return "PC/Laptop"
        if any(x in h for x in ["echo", "alexa", "dot"]):
            return "Amazon Echo"
        if any(x in h for x in ["chromecast", "google-home", "nest"]):
            return "Google Chromecast/Home"
        if any(x in h for x in ["firetv", "fire-tv", "amazon-fire"]):
            return "Amazon Fire TV"
        if any(x in h for x in ["appletv", "apple-tv"]):
            return "Apple TV"
        if "printer" in h or "impresora" in h or "hp" in h and "print" in h:
            return "Impresora"

        # Por fabricante OUI
        if fabricante:
            if "Apple" in fabricante:   return "Dispositivo Apple"
            if "Samsung" in fabricante: return "Samsung"
            if "Xiaomi" in fabricante:  return "Xiaomi"
            if "Google" in fabricante:  return "Google"
            if "Amazon" in fabricante:  return "Amazon"
            if "Raspberry" in fabricante: return "Raspberry Pi"

        return "Dispositivo desconocido"

    # ── Escaneo principal ─────────────────────────────────────────────────
    def escanear(self) -> tuple:
        """
        Escanea la red local.
        Retorna (lista_dispositivos, ip_local) o ([], None) en error.
        """
        ip_local = self._ip_local()
        if not ip_local:
            return [], None

        # Generar todas las IPs de la subred /24
        base = ip_local.rsplit(".", 1)[0]
        ips  = [f"{base}.{i}" for i in range(1, 255)]

        print(f"[RED] Escaneando {base}.0/24 — espera un momento...")

        # Ping en paralelo para poblar la tabla ARP (50 hilos simultáneos)
        with ThreadPoolExecutor(max_workers=50) as ex:
            list(as_completed({ex.submit(self._ping, ip): ip for ip in ips}))

        # Leer tabla ARP
        arp = self._arp_tabla()

        # Construir lista de dispositivos
        dispositivos = []
        for ip, mac in arp.items():
            if not ip.startswith(base):
                continue  # ignorar IPs fuera de la subred
            hostname = self._hostname(ip)
            tipo     = self._identificar(ip, mac, hostname, ip_local)
            dispositivos.append({
                "ip":       ip,
                "mac":      mac,
                "hostname": hostname or "desconocido",
                "tipo":     tipo,
            })

        # Ordenar por último octeto de IP
        dispositivos.sort(key=lambda d: int(d["ip"].rsplit(".", 1)[-1]))
        self._ultimo_scan = dispositivos
        return dispositivos, ip_local

    # ── Respuestas para JARVIS ─────────────────────────────────────────────
    def _respuesta_scan(self) -> str:
        dispositivos, ip_local = self.escanear()

        if ip_local is None:
            return "No pude obtener tu IP local. ¿Estás conectado a la red?"

        n    = len(dispositivos)
        base = ip_local.rsplit(".", 1)[0]

        if n == 0:
            return "No encontré dispositivos en la red. Intenta de nuevo en un momento."

        # Respuesta corta para voz
        lineas = [f"Hay {n} dispositivo{'s' if n != 1 else ''} conectado{'s' if n != 1 else ''} en tu red ({base}.0):"]
        for d in dispositivos:
            nombre = d["hostname"] if d["hostname"] != "desconocido" else d["ip"]
            lineas.append(f"  {d['tipo']}: {nombre}  —  {d['ip']}")

        return "\n".join(lineas)

    def _respuesta_ultimo(self) -> str:
        if not self._ultimo_scan:
            return "Aún no he escaneado la red. Di: escanea la red."
        n = len(self._ultimo_scan)
        lineas = [f"Último escaneo: {n} dispositivo{'s' if n != 1 else ''}"]
        for d in self._ultimo_scan:
            nombre = d["hostname"] if d["hostname"] != "desconocido" else d["ip"]
            lineas.append(f"  {d['tipo']}: {nombre}  —  {d['ip']}")
        return "\n".join(lineas)

    # ── Router principal ───────────────────────────────────────────────────
    def run(self, data: dict) -> str:
        action = data.get("action", "scan")

        if action in ("scan", "quienes", "cuantos"):
            return self._respuesta_scan()
        if action == "ultimo":
            return self._respuesta_ultimo()

        return "No reconocí ese comando de red."
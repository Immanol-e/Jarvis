"""
skills/system_skill.py — v2 con SysMonitor C++
Agrega: monitoreo real de CPU, RAM, disco y temperatura.
Mantiene: lock, shutdown, restart (sin cambios).

Nuevas acciones reconocidas en intents:
  "cpu"   → porcentaje de CPU
  "ram"   → uso de memoria
  "disco" → espacio en disco
  "temp"  → temperatura del CPU
  "stats" → resumen de todo
"""

import os
import sys
import platform
import subprocess
from pathlib import Path

# ── Cargar SysMonitor C++ ────────────────────────────────────────────────────
_NATIVE_PATH = Path(__file__).parent.parent / "native"
sys.path.insert(0, str(_NATIVE_PATH))

try:
    from bindings import SysMonitor
    _mon = SysMonitor()
    _USE_SYSMON = True
except (FileNotFoundError, OSError):
    _USE_SYSMON = False
    _mon = None
    print("[SystemSkill] SysMonitor C++ no disponible — compila native/sysmon.so")


class SystemSkill:

    def run(self, data: dict) -> str:
        action = data.get("action", "").lower()

        # ── Monitoreo (nuevo) ────────────────────────────────────────────────
        if action == "cpu":     return self._cpu()
        if action == "ram":     return self._ram()
        if action == "disco":   return self._disco()
        if action == "temp":    return self._temp()
        if action == "stats":   return self._stats()

        # ── Control del sistema (sin cambios) ────────────────────────────────
        if action == "lock":     return self.lock_computer()
        if action == "shutdown": return self.shutdown_computer()
        if action == "restart":  return self.restart_computer()

        return "No reconocí la acción del sistema."

    # ── Monitoreo ────────────────────────────────────────────────────────────

    def _cpu(self) -> str:
        if not _USE_SYSMON:
            return self._no_sysmon()
        # Dos llamadas con pausa para medir delta en Linux
        import time
        _mon.cpu_percent()
        time.sleep(0.15)
        pct = _mon.cpu_percent()
        nivel = "alta" if pct > 80 else ("media" if pct > 40 else "baja")
        return f"La CPU está al {pct}% — carga {nivel}."

    def _ram(self) -> str:
        if not _USE_SYSMON:
            return self._no_sysmon()
        r = _mon.ram()
        return (f"RAM: {r['used_gb']} GB usados de {r['total_gb']} GB "
                f"({r['percent']}% ocupado).")

    def _disco(self) -> str:
        if not _USE_SYSMON:
            return self._no_sysmon()
        ruta = "C:\\" if platform.system() == "Windows" else "/"
        d = _mon.disk(ruta)
        libre = d["free_gb"]
        total = d["total_gb"]
        alerta = " ¡Poco espacio!" if libre < 5 else ""
        return (f"Disco: {libre} GB libres de {total} GB "
                f"({d['percent']}% ocupado).{alerta}")

    def _temp(self) -> str:
        if not _USE_SYSMON:
            return self._no_sysmon()
        t = _mon.cpu_temp()
        if t < 0:
            return "No pude leer la temperatura — puede que este hardware no la exponga."
        nivel = "alta" if t > 80 else ("media" if t > 60 else "normal")
        return f"Temperatura del CPU: {t}°C ({nivel})."

    def _stats(self) -> str:
        if not _USE_SYSMON:
            return self._no_sysmon()
        import time
        _mon.cpu_percent()
        time.sleep(0.15)
        s = _mon.stats()

        temp_str = f" | Temp {s['cpu_temp']:.0f}°C" if s["cpu_temp"] >= 0 else ""
        return (
            f"CPU: {s['cpu_percent']}%{temp_str} | "
            f"RAM: {s['ram_percent']}% ({s['ram_used_gb']}/{s['ram_total_gb']} GB) | "
            f"Disco: {s['disk_percent']}% ({s['disk_free_gb']} GB libres)"
        )

    @staticmethod
    def _no_sysmon() -> str:
        return ("El módulo de monitoreo C++ no está compilado. "
                "Ejecuta: cd native && make sysmon.so")

    # ── Control del sistema ─────────────────────────────────────────────────

    def lock_computer(self) -> str:
        sys_name = platform.system()
        if sys_name == "Windows":
            subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True)
        elif sys_name == "Linux":
            # Intenta varios métodos según el entorno de escritorio
            for cmd in ["loginctl lock-session",
                        "gnome-screensaver-command --lock",
                        "xdg-screensaver lock"]:
                if subprocess.run(cmd, shell=True,
                                  capture_output=True).returncode == 0:
                    break
        elif sys_name == "Darwin":
            subprocess.run(
                '/System/Library/CoreServices/Menu\\ Extras/User.menu/'
                'Contents/Resources/CGSession -suspend',
                shell=True)
        return "Computadora bloqueada."

    def shutdown_computer(self) -> str:
        sys_name = platform.system()
        if sys_name == "Windows":   os.system("shutdown /s /t 5")
        elif sys_name == "Linux":   os.system("shutdown now")
        elif sys_name == "Darwin":  os.system("sudo shutdown -h now")
        return "Apagando computadora en 5 segundos."

    def restart_computer(self) -> str:
        sys_name = platform.system()
        if sys_name == "Windows":   os.system("shutdown /r /t 5")
        elif sys_name == "Linux":   os.system("reboot")
        elif sys_name == "Darwin":  os.system("sudo shutdown -r now")
        return "Reiniciando computadora en 5 segundos."

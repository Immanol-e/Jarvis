"""
skills/launcher.py — abre rutas en Visual Studio Code.

Antes cada skill hacía lo mismo, y estaba mal:

    subprocess.Popen(["code", str(path)], shell=True)

Mezclar una LISTA de argumentos con shell=True falla en los dos sistemas:

  - En Linux/macOS, Python le pasa al shell solo el primer elemento y TIRA
    el resto. O sea que la ruta nunca llegaba: se abría VS Code vacío.
  - En Windows jalaba de chiripa porque "code" es un .cmd y lo resuelve el
    shell, pero de paso parpadeaba una ventana de consola.

Aquí se busca la ruta real del ejecutable con shutil.which() (que en Windows
ya respeta PATHEXT y encuentra code.cmd) y se llama sin shell. Los .cmd y
.bat sí necesitan cmd.exe porque CreateProcess no los ejecuta por su cuenta.
"""

import platform
import shutil
import subprocess
from pathlib import Path

_ES_WINDOWS = platform.system() == "Windows"

# Se guarda la ruta ya encontrada para no buscar en el PATH cada vez
_cache_exe = None
_ya_busque = False


def buscar_vscode():
    """Devuelve la ruta del ejecutable de VS Code, o None si no está."""
    global _cache_exe, _ya_busque

    if _ya_busque:
        return _cache_exe
    _ya_busque = True

    for nombre in ("code", "code-insiders", "codium"):
        ruta = shutil.which(nombre)
        if ruta:
            _cache_exe = ruta
            return _cache_exe

    # Instalaciones de Windows que no agregaron VS Code al PATH
    if _ES_WINDOWS:
        candidatos = [
            Path.home() / "AppData" / "Local" / "Programs" / "Microsoft VS Code" / "bin" / "code.cmd",
            Path("C:/Program Files/Microsoft VS Code/bin/code.cmd"),
            Path("C:/Program Files (x86)/Microsoft VS Code/bin/code.cmd"),
        ]
        for candidato in candidatos:
            if candidato.exists():
                _cache_exe = str(candidato)
                return _cache_exe

    return None


def abrir_en_vscode(ruta) -> bool:
    """
    Abre la ruta en VS Code. Devuelve True si se lanzó, False si no se pudo
    (no está instalado o falló al arrancar). Quien llama decide el fallback.
    """
    exe = buscar_vscode()
    if not exe:
        return False

    try:
        if _ES_WINDOWS and exe.lower().endswith((".cmd", ".bat")):
            subprocess.Popen(
                ["cmd", "/c", exe, str(ruta)],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            subprocess.Popen([exe, str(ruta)])
        return True
    except Exception:
        return False
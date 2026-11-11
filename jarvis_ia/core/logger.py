"""
core/logger.py — logging central de JARVIS.

Por qué esto:
El proyecto tenía como 88 bloques try/except y muchos se tragaban el error
sin dejar rastro. Cuando algo fallaba de noche no había forma de saber qué
pasó, y si JARVIS se caía arrancado desde el .bat la ventana se cerraba y
el traceback se perdía.

Qué deja:
  data/logs/jarvis.log     → todo lo que pasa (rota cada 1 MB, guarda 5)
  data/logs/comandos.log   → un renglón por comando, en TSV, para analizarlo

El de comandos es el que va a servir para el bloque 5: de ahí salen las
frases reales para armar las pruebas del clasificador, y se ve cuáles
cayeron en unknown y cuánto tardó cada una.

Uso normal:

    from core.logger import get_logger
    log = get_logger("tv_skill")

    log.debug("detalle que solo va al archivo")
    log.info("algo que pasó")
    log.warning("algo raro pero no fatal")
    log.exception("falló X")     # dentro de un except: mete el traceback

Por defecto la consola solo muestra WARNING para arriba, así la terminal
de JARVIS no se llena. El archivo sí se queda con todo.
"""

import logging
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Raíz del proyecto (jarvis_ia/), no el directorio desde donde arrancaste
_RAIZ    = Path(__file__).resolve().parent.parent
_CARPETA = _RAIZ / "data" / "logs"

_FORMATO_ARCHIVO = "%(asctime)s | %(levelname)-8s | %(name)-26s | %(message)s"
_FORMATO_CONSOLA = "[%(levelname)s] %(name)s: %(message)s"
_FECHA           = "%Y-%m-%d %H:%M:%S"

_configurado = False


def configurar(nivel_consola=logging.WARNING, nivel_archivo=logging.DEBUG):
    """
    Prepara los handlers. Se puede llamar las veces que sea, solo hace
    trabajo la primera vez.
    """
    global _configurado
    if _configurado:
        return

    _CARPETA.mkdir(parents=True, exist_ok=True)

    # En Windows la consola suele venir en cp1252 y los acentos truenan
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    # ── Log general ──────────────────────────────────────────────────────
    raiz = logging.getLogger("jarvis")
    raiz.setLevel(logging.DEBUG)
    raiz.propagate = False
    raiz.handlers.clear()

    archivo = RotatingFileHandler(
        _CARPETA / "jarvis.log",
        maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    archivo.setLevel(nivel_archivo)
    archivo.setFormatter(logging.Formatter(_FORMATO_ARCHIVO, _FECHA))
    raiz.addHandler(archivo)

    consola = logging.StreamHandler(sys.stdout)
    consola.setLevel(nivel_consola)
    consola.setFormatter(logging.Formatter(_FORMATO_CONSOLA))
    raiz.addHandler(consola)

    # ── Log de comandos (TSV, para analizar después) ─────────────────────
    comandos = logging.getLogger("jarvis_comandos")
    comandos.setLevel(logging.INFO)
    comandos.propagate = False
    comandos.handlers.clear()

    h_cmd = RotatingFileHandler(
        _CARPETA / "comandos.log",
        maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    h_cmd.setFormatter(logging.Formatter("%(asctime)s\t%(message)s", _FECHA))
    comandos.addHandler(h_cmd)

    _configurado = True


def get_logger(nombre):
    """Logger para un módulo. El nombre sale en cada renglón del archivo."""
    configurar()
    return logging.getLogger(f"jarvis.{nombre}")


def log_comando(entrada, intent, origen, ms, respuesta=""):
    """
    Un renglón por comando en comandos.log:

        fecha  entrada  intent  origen  ms  respuesta

    origen dice quién resolvió el comando:
        regex    → lo agarró el IntentClassifier al instante
        router   → lo agarró quick_route del AIRouter
        ollama   → tuvo que preguntarle al modelo
        contexto → lo resolvió el ConversationContext
        plan     → lo armó el TaskPlanner
    """
    configurar()
    limpiar = lambda t: " ".join(str(t).split())
    logging.getLogger("jarvis_comandos").info(
        "%s\t%s\t%s\t%d\t%s",
        limpiar(entrada)[:120],
        intent or "unknown",
        origen,
        int(ms),
        limpiar(respuesta)[:150],
    )


def instalar_excepthook():
    """
    Manda al log cualquier crash, del hilo principal o de los hilos daemon.

    Sin esto, si JARVIS truena arrancado desde run_jarvis.bat la ventana se
    cierra y nunca ves el traceback. Y si truena el hilo de la voz o el de
    los recordatorios, hoy no te enteras nunca.
    """
    configurar()
    log = get_logger("crash")

    anterior = sys.excepthook

    def _hook(tipo, valor, tb):
        log.critical(
            "JARVIS se cayó:\n%s",
            "".join(traceback.format_exception(tipo, valor, tb))
        )
        anterior(tipo, valor, tb)

    sys.excepthook = _hook

    def _hook_hilo(args):
        log.critical(
            "El hilo '%s' se cayó:\n%s",
            args.thread.name if args.thread else "?",
            "".join(traceback.format_exception(
                args.exc_type, args.exc_value, args.exc_traceback
            ))
        )

    threading.excepthook = _hook_hilo


def ruta_logs():
    """Carpeta donde quedan los logs, por si la quieres abrir."""
    configurar()
    return _CARPETA
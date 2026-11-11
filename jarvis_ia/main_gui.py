from core.logger import configurar, get_logger, instalar_excepthook
from app.jarvis_ui import main as abrir_interfaz


def main():
    configurar()
    instalar_excepthook()

    log = get_logger("main_gui")
    log.info("=== JARVIS arrancando (modo gráfico) ===")

    try:
        abrir_interfaz()
    finally:
        log.info("=== JARVIS cerrado ===")


if __name__ == "__main__":
    main()
    
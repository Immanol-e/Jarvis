from core.logger import configurar, get_logger, instalar_excepthook
from app.assistant import JarvisAssistant


def main():
    configurar()
    instalar_excepthook()

    log = get_logger("main")
    log.info("=== JARVIS arrancando (modo terminal) ===")

    try:
        jarvis = JarvisAssistant()
        jarvis.start()
    except KeyboardInterrupt:
        log.info("Cerrado con Ctrl+C")
        print("\nHasta luego, señor.")
    finally:
        log.info("=== JARVIS cerrado ===")


if __name__ == "__main__":
    main()
"""
voice/text_to_speech.py — voz JARVIS de Tony Stark

Cambios de esta versión:
  - Caché: cada frase se guarda como data/audio/cache/<hash>.mp3 y ya no se
    borra. Frases repetidas ("Te escucho.", "Hasta luego, señor.") se generan
    una sola vez en la vida; las siguientes veces se reproducen al instante.
  - La carpeta de audio ya no depende del directorio desde el que arrancas
    (antes era Path("data/audio"), relativa al cwd; si arrancabas desde otra
    carpeta se creaba una caché nueva vacía).
  - Dos hilos: uno sintetiza y el otro reproduce. Mientras suena la frase 1
    ya se está generando la frase 2 — es lo que hace que el streaming suene
    seguido y no a pedazos.
  - decir() encola sin bloquear. speak() sigue funcionando igual que antes
    (encola y espera), así que el resto del proyecto no cambia.
  - lector_streaming(): recibe los pedacitos del LLM y va soltando oraciones
    completas al TTS conforme se van cerrando.

La voz y el filtro de ffmpeg quedaron igual.
"""

import asyncio
import hashlib
import queue
import re
import subprocess
import threading
from pathlib import Path

import edge_tts
from playsound import playsound


# Raíz del proyecto (jarvis_ia/), no el directorio desde donde arrancaste
_RAIZ = Path(__file__).resolve().parent.parent


# ── Configuración de voz ────────────────────────────────────────────────────
# es-ES-AlvaroNeural: acento español peninsular — más formal y autoritario que
# el mexicano, el más parecido a JARVIS hablando español.
# Alternativas:
#   "en-GB-RyanNeural"   → inglés británico, JARVIS auténtico de las películas
#   "es-MX-JorgeNeural"  → voz original del proyecto
JARVIS_VOICE  = "es-ES-AlvaroNeural"
JARVIS_RATE   = "+10%"    # JARVIS habla más rápido que la media
JARVIS_PITCH  = "-8Hz"    # ligeramente más grave — más serio

# ── Efecto de audio JARVIS (requiere ffmpeg en PATH) ───────────────────────
# Puedes instalar ffmpeg en Windows desde: https://ffmpeg.org/download.html
# Si no lo tienes, JARVIS habla igual pero sin el efecto metálico.
_JARVIS_FILTER = ",".join([
    "equalizer=f=180:width_type=o:width=2:g=3",   # cuerpo y gravedad
    "equalizer=f=2800:width_type=o:width=2:g=2",  # presencia y claridad
    "equalizer=f=6500:width_type=o:width=2:g=-4", # reduce agudos chiflantes
    "aecho=0.85:0.88:35:0.2",                      # eco sutil — sensación de sala
    "atempo=1.0",                                   # velocidad ya controlada por rate
])

# Corte de oración para el modo streaming
_FIN_ORACION = re.compile(r"[.!?…\n]+[\"')\]]?\s")


class TextToSpeech:
    def __init__(self):
        self.voice        = JARVIS_VOICE
        self.audio_folder = _RAIZ / "data" / "audio" / "cache"
        self.audio_folder.mkdir(parents=True, exist_ok=True)
        self._pyttsx_engine = None
        self._ffmpeg_ok     = self._check_ffmpeg()

        # Cola de texto → hilo sintetizador → cola de audio → hilo reproductor
        self._cola_texto  = queue.Queue()
        self._cola_audio  = queue.Queue()
        self._hilos_ok    = False
        self._lock_hilos  = threading.Lock()

        if self._ffmpeg_ok:
            print("[VOZ] ffmpeg detectado — efecto JARVIS activado.")
        else:
            print("[VOZ] ffmpeg no encontrado — voz sin efecto (funciona igual).")

    def _check_ffmpeg(self) -> bool:
        """Verifica si ffmpeg está instalado en el sistema."""
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True, timeout=3
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    # ── Hilos de trabajo ────────────────────────────────────────────────────
    def _arrancar_hilos(self):
        with self._lock_hilos:
            if self._hilos_ok:
                return
            threading.Thread(target=self._loop_sintetizar, daemon=True).start()
            threading.Thread(target=self._loop_reproducir, daemon=True).start()
            self._hilos_ok = True

    def _loop_sintetizar(self):
        while True:
            texto = self._cola_texto.get()
            try:
                ruta = self._sintetizar(texto)
            except Exception as error:
                print(f"[VOZ] Edge TTS falló ({type(error).__name__}) — usando voz local...")
                ruta = None
            self._cola_audio.put((texto, ruta))
            self._cola_texto.task_done()

    def _loop_reproducir(self):
        while True:
            texto, ruta = self._cola_audio.get()
            try:
                if ruta:
                    playsound(ruta)
                else:
                    self._speak_fallback(texto)
            except Exception as error:
                print(f"[VOZ] No pude reproducir ({type(error).__name__}) — voz local...")
                self._speak_fallback(texto)
            self._cola_audio.task_done()

    # ── Caché + generación ──────────────────────────────────────────────────
    def _clave(self, texto: str) -> str:
        """Hash de la frase + la configuración de voz. Si cambias la voz,
        cambia la clave y se regenera el audio solo."""
        firma = f"{self.voice}|{JARVIS_RATE}|{JARVIS_PITCH}|{int(self._ffmpeg_ok)}|{texto}"
        return hashlib.sha1(firma.encode("utf-8")).hexdigest()

    def _sintetizar(self, texto: str) -> str:
        """
        Devuelve la ruta del mp3 listo para reproducir.
        Si ya está en caché no vuelve a generarlo.
        """
        clave = self._clave(texto)
        final = self.audio_folder / f"{clave}.mp3"

        # El chequeo de tamaño es a propósito: edge-tts a veces deja mp3 de
        # 0 bytes cuando se cae la red, y esos hay que regenerarlos.
        if final.exists() and final.stat().st_size > 0:
            return str(final)

        crudo = self.audio_folder / f"tmp_{clave}.mp3"
        asyncio.run(self._generate_audio(texto, str(crudo)))

        if crudo.stat().st_size == 0:
            crudo.unlink(missing_ok=True)
            raise RuntimeError("edge-tts devolvió un audio vacío")

        if self._ffmpeg_ok and self._apply_jarvis_effect(str(crudo), str(final)):
            crudo.unlink(missing_ok=True)
        else:
            crudo.replace(final)

        return str(final)

    async def _generate_audio(self, text: str, file_path: str):
        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=JARVIS_RATE,
            pitch=JARVIS_PITCH,
        )
        await communicate.save(file_path)

    def _apply_jarvis_effect(self, input_path: str, output_path: str) -> bool:
        """
        Aplica el filtro de audio JARVIS con ffmpeg.
        Retorna True si tuvo éxito, False si falló.
        """
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", input_path,
                    "-af", _JARVIS_FILTER,
                    "-q:a", "2",    # calidad MP3 alta
                    output_path
                ],
                capture_output=True,
                timeout=15
            )
            return result.returncode == 0
        except Exception:
            return False

    # ── Fallback: pyttsx3 ────────────────────────────────────────────────────
    def _speak_fallback(self, text: str):
        try:
            import pyttsx3
            if self._pyttsx_engine is None:
                self._pyttsx_engine = pyttsx3.init()
                voices = self._pyttsx_engine.getProperty("voices")
                # Buscar voz en español
                for v in voices:
                    if ("es" in (v.languages or []) or
                            "spanish" in v.name.lower() or
                            "español" in v.name.lower()):
                        self._pyttsx_engine.setProperty("voice", v.id)
                        break
                self._pyttsx_engine.setProperty("rate", 175)
                self._pyttsx_engine.setProperty("volume", 1.0)
            self._pyttsx_engine.say(text)
            self._pyttsx_engine.runAndWait()
        except Exception as err:
            print(f"[VOZ-FALLBACK] pyttsx3 falló: {err}")

    # ── Puntos de entrada públicos ──────────────────────────────────────────
    def decir(self, text: str):
        """Encola la frase y regresa de inmediato (no bloquea)."""
        if not text or not text.strip():
            return
        print(f"[JARVIS] {text}")
        self._arrancar_hilos()
        self._cola_texto.put(text.strip())

    def esperar(self):
        """Se queda esperando a que termine todo lo encolado."""
        self._cola_texto.join()
        self._cola_audio.join()

    def speak(self, text: str):
        """Igual que siempre: dice la frase y no regresa hasta terminar."""
        if not text:
            return
        self.decir(text)
        self.esperar()

    def lector_streaming(self):
        """Devuelve un lector para ir alimentando texto del LLM."""
        return LectorEnStreaming(self)

    # ── Mantenimiento de la caché ───────────────────────────────────────────
    def limpiar_cache(self):
        """Borra los mp3 guardados. Útil si cambiaste la voz o el filtro."""
        borrados = 0
        for archivo in self.audio_folder.glob("*.mp3"):
            try:
                archivo.unlink()
                borrados += 1
            except Exception:
                pass
        return f"Caché de voz limpia. Borré {borrados} archivos."


class LectorEnStreaming:
    """
    Recibe los pedacitos de texto que va soltando el LLM y manda al TTS
    cada oración en cuanto se cierra, sin esperar a que termine todo.
    """

    def __init__(self, tts: TextToSpeech):
        self.tts    = tts
        self.buffer = ""
        self.dicho  = ""

    def feed(self, trozo: str):
        if not trozo:
            return
        self.buffer += trozo

        while True:
            corte = _FIN_ORACION.search(self.buffer)
            if not corte:
                break
            oracion     = self.buffer[:corte.end()].strip()
            self.buffer = self.buffer[corte.end():]
            if oracion:
                self.dicho += oracion + " "
                self.tts.decir(oracion)

    def close(self):
        """Manda lo que haya quedado sin punto final."""
        resto = self.buffer.strip()
        self.buffer = ""
        if resto:
            self.dicho += resto
            self.tts.decir(resto)
        return self.dicho.strip()
"""
voice/speech_to_text.py — v2 con VAD y AudioCapture C++
Fix: el try/except ahora cubre la instanciación de los módulos C++,
     no solo el import. Así funciona aunque los .dll/.so no estén compilados.
"""

import sys
import array
import time
from pathlib import Path

import speech_recognition as sr

# Importar el módulo de bindings (solo el .py — esto siempre funciona)
_NATIVE_PATH = Path(__file__).parent.parent / "native"
sys.path.insert(0, str(_NATIVE_PATH))

try:
    from bindings import VAD, WakeDetector, AudioCapture
    _BINDINGS_OK = True
except ImportError:
    _BINDINGS_OK = False


class SpeechToText:
    SAMPLE_RATE      = 16000
    CHUNK_SIZE       = 512
    MAX_RECORD_SEC   = 10
    WAKE_SENSITIVITY = 0.65

    def __init__(self):
        self.recognizer  = sr.Recognizer()

        # Inicializar siempre en None — evita el AttributeError en __del__
        self._vad        = None
        self._wake       = None
        self._cap        = None
        self._mic        = None
        self._use_native = False

        # Intentar cargar los módulos C++ (falla si los .dll/.so no están compilados)
        if _BINDINGS_OK:
            try:
                self._vad  = VAD(rms_threshold=0.015,
                                 zcr_threshold=0.15,
                                 min_silence_frames=15,
                                 ema_alpha=0.3)
                self._wake = WakeDetector(sensitivity=self.WAKE_SENSITIVITY,
                                          sample_rate=self.SAMPLE_RATE,
                                          frames_per_buffer=self.CHUNK_SIZE)
                self._cap  = AudioCapture(sample_rate=self.SAMPLE_RATE,
                                          channels=1,
                                          frames_per_buffer=self.CHUNK_SIZE)
                self._use_native = True
                print("[STT] Módulos C++ cargados correctamente.")
            except (FileNotFoundError, OSError):
                self._use_native = False
                print("[STT] .dll/.so no encontrados — usando SpeechRecognition normal.")
                print(f"      Para compilar: cd {_NATIVE_PATH} && make all")

        if not self._use_native:
            self._mic = sr.Microphone(sample_rate=self.SAMPLE_RATE)

    # ── Punto de entrada público ─────────────────────────────────────────────
    def listen(self) -> str:
        return self._listen_native() if self._use_native else self._listen_fallback()

    # ── Modo nativo ──────────────────────────────────────────────────────────
    def _listen_native(self) -> str:
        self._cap.flush()
        self._wake.reset()
        self._vad.reset()

        print("[JARVIS] En espera... (di 'hey jarvis')")
        while True:
            chunk = self._cap.read(self.CHUNK_SIZE)
            if not chunk:
                time.sleep(0.005)
                continue
            if self._wake.process(chunk):
                if self._quick_confirm():
                    break

        print("[JARVIS] Escuchando comando...")
        self._cap.flush()
        self._vad.reset()

        audio_samples = []
        max_samples   = self.SAMPLE_RATE * self.MAX_RECORD_SEC

        while len(audio_samples) < max_samples:
            chunk = self._cap.read(self.CHUNK_SIZE)
            if not chunk:
                time.sleep(0.005)
                continue
            audio_samples.extend(chunk)
            if self._vad.process(chunk) == -1:
                break

        return self._samples_to_text(audio_samples) if audio_samples else ""

    def _quick_confirm(self) -> bool:
        self._cap.flush()
        samples = []
        target  = int(self.SAMPLE_RATE * 0.6)
        while len(samples) < target:
            chunk = self._cap.read(self.CHUNK_SIZE)
            if chunk:
                samples.extend(chunk)
            else:
                time.sleep(0.005)
        texto = self._samples_to_text(samples)
        return "jarvis" in texto.lower() if texto else False

    # ── Modo fallback ────────────────────────────────────────────────────────
    def _listen_fallback(self) -> str:
        try:
            with self._mic as source:
                print("Escuchando...")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(source, timeout=6, phrase_time_limit=7)
            return self._recognize(audio)
        except sr.WaitTimeoutError:
            return ""
        except Exception as e:
            print(f"[STT] Error: {e}")
            return ""

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _samples_to_text(self, samples: list) -> str:
        int16      = array.array("h", [max(-32768, min(32767, int(s * 32767)))
                                        for s in samples])
        audio_data = sr.AudioData(int16.tobytes(), self.SAMPLE_RATE, 2)
        return self._recognize(audio_data)

    def _recognize(self, audio) -> str:
        try:
            texto = self.recognizer.recognize_google(audio, language="es-MX")
            print(f"Tú dijiste: {texto}")
            return texto
        except sr.UnknownValueError:
            print("No entendí el audio.")
            return ""
        except sr.RequestError:
            print("Error con Google STT.")
            return ""

    def __del__(self):
        if self._cap:
            self._cap.close()
"""
native/bindings.py — Puente Python <-> C++ para JARVIS
Carga las librerías compiladas vía ctypes y expone clases Python limpias.
No requiere pybind11 ni extensiones de compilación — solo ctypes estándar.
"""

import ctypes
import platform
import json
from pathlib import Path

_DIR = Path(__file__).parent
_EXT = ".dll" if platform.system() == "Windows" else ".so"


def _load(name: str) -> ctypes.CDLL:
    """Carga nombre.so / nombre.dll desde el directorio native/."""
    path = _DIR / f"{name}{_EXT}"
    if not path.exists():
        raise FileNotFoundError(
            f"No se encontró {path}.\n"
            f"Compila con:  cd native && make {name}{_EXT}"
        )
    return ctypes.CDLL(str(path))


# ════════════════════════════════════════════════════════════════════════════
#  VAD — Voice Activity Detection
# ════════════════════════════════════════════════════════════════════════════

class VAD:
    """
    Detecta voz vs silencio en bloques de audio float32.

    Uso:
        vad = VAD()
        estado = vad.process(lista_de_floats)
        # 0 = silencio, 1 = hablando, -1 = fin de habla
    """

    def __init__(self,
                 rms_threshold: float = 0.015,
                 zcr_threshold: float = 0.15,
                 min_silence_frames: int = 15,
                 ema_alpha: float = 0.3):
        lib = _load("vad")

        lib.vad_create.restype  = ctypes.c_void_p
        lib.vad_create.argtypes = [ctypes.c_float, ctypes.c_float,
                                    ctypes.c_int, ctypes.c_float]
        lib.vad_destroy.argtypes  = [ctypes.c_void_p]
        lib.vad_process.restype   = ctypes.c_int
        lib.vad_process.argtypes  = [ctypes.c_void_p,
                                      ctypes.POINTER(ctypes.c_float), ctypes.c_int]
        lib.vad_is_speech.restype  = ctypes.c_int
        lib.vad_is_speech.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.c_int,
                                       ctypes.c_float, ctypes.c_float]
        lib.vad_rms.restype       = ctypes.c_float
        lib.vad_rms.argtypes      = [ctypes.POINTER(ctypes.c_float), ctypes.c_int]
        lib.vad_reset.argtypes    = [ctypes.c_void_p]

        self._lib    = lib
        self._handle = lib.vad_create(rms_threshold, zcr_threshold,
                                       min_silence_frames, ema_alpha)

    def process(self, samples: list) -> int:
        """
        Procesa un bloque de muestras float32.
        Retorna: 0=silencio, 1=hablando, -1=fin de habla.
        """
        arr = (ctypes.c_float * len(samples))(*samples)
        return self._lib.vad_process(self._handle, arr, len(samples))

    def is_speech(self, samples: list,
                  rms_threshold: float = 0.015,
                  zcr_threshold: float = 0.15) -> bool:
        """Consulta instantánea sin estado interno."""
        arr = (ctypes.c_float * len(samples))(*samples)
        return bool(self._lib.vad_is_speech(arr, len(samples),
                                             rms_threshold, zcr_threshold))

    def rms(self, samples: list) -> float:
        """Energía RMS del bloque (útil para calibrar umbrales)."""
        arr = (ctypes.c_float * len(samples))(*samples)
        return self._lib.vad_rms(arr, len(samples))

    def reset(self):
        self._lib.vad_reset(self._handle)

    def __del__(self):
        if hasattr(self, "_handle") and self._handle:
            self._lib.vad_destroy(self._handle)


# ════════════════════════════════════════════════════════════════════════════
#  WakeDetector — Activación por nombre
# ════════════════════════════════════════════════════════════════════════════

class WakeDetector:
    """
    Detecta cuando el usuario dice la wake word ('hey jarvis').
    Basado en energía + duración. Devuelve True cuando detecta un candidato.
    El caller confirma con STT antes de procesar.

    Uso:
        wake = WakeDetector(sensitivity=0.7)
        if wake.process(chunk):
            print("Posible wake word — confirmar con STT")
    """

    def __init__(self, sensitivity: float = 0.7,
                 sample_rate: int = 16000,
                 frames_per_buffer: int = 512):
        lib = _load("wake_word")

        lib.wake_create.restype   = ctypes.c_void_p
        lib.wake_create.argtypes  = [ctypes.c_float, ctypes.c_int, ctypes.c_int]
        lib.wake_destroy.argtypes = [ctypes.c_void_p]
        lib.wake_process.restype  = ctypes.c_int
        lib.wake_process.argtypes = [ctypes.c_void_p,
                                      ctypes.POINTER(ctypes.c_float), ctypes.c_int]
        lib.wake_recent_rms.restype  = ctypes.c_float
        lib.wake_recent_rms.argtypes = [ctypes.c_void_p]
        lib.wake_reset.argtypes      = [ctypes.c_void_p]

        self._lib    = lib
        self._handle = lib.wake_create(sensitivity, sample_rate, frames_per_buffer)

    def process(self, samples: list) -> bool:
        arr = (ctypes.c_float * len(samples))(*samples)
        return bool(self._lib.wake_process(self._handle, arr, len(samples)))

    def recent_rms(self) -> float:
        """RMS promedio reciente — útil para calibrar sensitivity."""
        return self._lib.wake_recent_rms(self._handle)

    def reset(self):
        self._lib.wake_reset(self._handle)

    def __del__(self):
        if hasattr(self, "_handle") and self._handle:
            self._lib.wake_destroy(self._handle)


# ════════════════════════════════════════════════════════════════════════════
#  AudioCapture — Captura de micrófono
# ════════════════════════════════════════════════════════════════════════════

class AudioCapture:
    """
    Captura de micrófono con PortAudio — reemplaza PyAudio en STT.
    Soporta context manager (with AudioCapture() as cap: ...).

    Uso:
        with AudioCapture() as cap:
            while True:
                chunk = cap.read(512)
                if chunk:
                    # procesar chunk (lista de floats)
    """

    def __init__(self, sample_rate: int = 16000,
                 channels: int = 1,
                 frames_per_buffer: int = 512):
        lib = _load("audiocap")

        lib.audiocap_open.restype         = ctypes.c_void_p
        lib.audiocap_open.argtypes        = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
        lib.audiocap_close.argtypes       = [ctypes.c_void_p]
        lib.audiocap_read.restype         = ctypes.c_int
        lib.audiocap_read.argtypes        = [ctypes.c_void_p,
                                              ctypes.POINTER(ctypes.c_float), ctypes.c_int]
        lib.audiocap_available.restype    = ctypes.c_int
        lib.audiocap_available.argtypes   = [ctypes.c_void_p]
        lib.audiocap_flush.argtypes       = [ctypes.c_void_p]
        lib.audiocap_overflow_count.restype  = ctypes.c_int
        lib.audiocap_overflow_count.argtypes = [ctypes.c_void_p]
        lib.audiocap_sample_rate.restype     = ctypes.c_int
        lib.audiocap_sample_rate.argtypes    = [ctypes.c_void_p]

        self._lib  = lib
        self._ch   = channels
        self._fpb  = frames_per_buffer
        handle = lib.audiocap_open(sample_rate, channels, frames_per_buffer)
        if not handle:
            raise RuntimeError(
                "No se pudo abrir el micrófono.\n"
                "Verifica que PortAudio esté instalado y que haya un micrófono disponible."
            )
        self._handle = handle

    def read(self, frames: int) -> list:
        """Lee hasta `frames` frames. Retorna lista de floats en [-1, 1]."""
        buf = (ctypes.c_float * (frames * self._ch))()
        n   = self._lib.audiocap_read(self._handle, buf, frames)
        return list(buf[: n * self._ch])

    def available(self) -> int:
        """Frames disponibles en el buffer interno."""
        return self._lib.audiocap_available(self._handle)

    def flush(self):
        """Descarta todo el audio acumulado (útil antes de empezar a escuchar)."""
        self._lib.audiocap_flush(self._handle)

    def overflow_count(self) -> int:
        """Cuántas veces se desbordó el buffer (debería ser 0 siempre)."""
        return self._lib.audiocap_overflow_count(self._handle)

    def close(self):
        if self._handle:
            self._lib.audiocap_close(self._handle)
            self._handle = None

    def __del__(self):   self.close()
    def __enter__(self): return self
    def __exit__(self, *_): self.close()


# ════════════════════════════════════════════════════════════════════════════
#  SysMonitor — CPU, RAM, disco, temperatura
# ════════════════════════════════════════════════════════════════════════════

class SysMonitor:
    """
    Monitoreo de sistema vía APIs nativas — sin psutil.

    Uso:
        mon = SysMonitor()
        print(mon.cpu_percent())   # 34.2
        print(mon.ram())           # {'total_gb': 16.0, 'used_gb': 8.1, 'percent': 50.6}
        print(mon.stats())         # dict con todo
    """

    def __init__(self):
        lib = _load("sysmon")

        lib.sysmon_cpu_percent.restype  = ctypes.c_float
        lib.sysmon_cpu_temp.restype     = ctypes.c_float
        lib.sysmon_stats_json.restype   = ctypes.c_char_p
        lib.sysmon_ram.argtypes  = [ctypes.POINTER(ctypes.c_longlong),
                                     ctypes.POINTER(ctypes.c_longlong),
                                     ctypes.POINTER(ctypes.c_float)]
        lib.sysmon_disk.argtypes = [ctypes.c_char_p,
                                     ctypes.POINTER(ctypes.c_longlong),
                                     ctypes.POINTER(ctypes.c_longlong),
                                     ctypes.POINTER(ctypes.c_float)]
        self._lib = lib

    def cpu_percent(self) -> float:
        """% de uso de CPU (0-100). Llama dos veces con ~100ms de diferencia para mayor precisión."""
        return round(self._lib.sysmon_cpu_percent(), 1)

    def cpu_temp(self) -> float:
        """Temperatura del CPU en °C. Retorna -1.0 si no está disponible."""
        return round(self._lib.sysmon_cpu_temp(), 1)

    def ram(self) -> dict:
        total = ctypes.c_longlong()
        used  = ctypes.c_longlong()
        pct   = ctypes.c_float()
        self._lib.sysmon_ram(ctypes.byref(total), ctypes.byref(used), ctypes.byref(pct))
        return {
            "total_gb": round(total.value / 1e9, 2),
            "used_gb":  round(used.value  / 1e9, 2),
            "percent":  round(pct.value, 1),
        }

    def disk(self, path: str = "/") -> dict:
        total = ctypes.c_longlong()
        free  = ctypes.c_longlong()
        pct   = ctypes.c_float()
        self._lib.sysmon_disk(path.encode(), ctypes.byref(total),
                               ctypes.byref(free), ctypes.byref(pct))
        return {
            "total_gb": round(total.value / 1e9, 2),
            "free_gb":  round(free.value  / 1e9, 2),
            "percent":  round(pct.value, 1),
        }

    def stats(self) -> dict:
        """Retorna un dict con todos los valores de una sola llamada."""
        raw = self._lib.sysmon_stats_json()
        return json.loads(raw.decode())


# ════════════════════════════════════════════════════════════════════════════
#  FileSearch — Búsqueda recursiva de archivos
# ════════════════════════════════════════════════════════════════════════════

class FileSearch:
    """
    Búsqueda recursiva de archivos vía std::filesystem — mucho más rápida que os.walk().

    Uso:
        fs = FileSearch()
        resultados = fs.find("/home/user", pattern="jarvis", ext=".py")
        for ruta in resultados:
            print(ruta)
    """

    def __init__(self):
        lib = _load("filesearch")

        lib.filesearch_find.restype     = ctypes.c_int
        lib.filesearch_find.argtypes    = [ctypes.c_char_p, ctypes.c_char_p,
                                            ctypes.c_char_p, ctypes.c_int]
        lib.filesearch_count.restype    = ctypes.c_int
        lib.filesearch_get.restype      = ctypes.c_char_p
        lib.filesearch_get.argtypes     = [ctypes.c_int]
        lib.filesearch_parent.restype   = ctypes.c_char_p
        lib.filesearch_parent.argtypes  = [ctypes.c_int]
        lib.filesearch_name.restype     = ctypes.c_char_p
        lib.filesearch_name.argtypes    = [ctypes.c_int]
        lib.filesearch_size.restype     = ctypes.c_longlong
        lib.filesearch_size.argtypes    = [ctypes.c_int]
        lib.filesearch_by_ext.restype   = ctypes.c_int
        lib.filesearch_by_ext.argtypes  = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        lib.filesearch_list_dir.restype  = ctypes.c_int
        lib.filesearch_list_dir.argtypes = [ctypes.c_char_p, ctypes.c_int]

        self._lib = lib

    def find(self, root: str, pattern: str = "",
             ext: str = "", max_results: int = 500) -> list:
        """Búsqueda recursiva. pattern y ext son opcionales."""
        n = self._lib.filesearch_find(root.encode(), pattern.encode(),
                                       ext.encode(), max_results)
        return [self._lib.filesearch_get(i).decode() for i in range(n)]

    def find_by_ext(self, root: str, ext: str, max_results: int = 500) -> list:
        """Busca todos los archivos con una extensión dada."""
        n = self._lib.filesearch_by_ext(root.encode(), ext.encode(), max_results)
        return [self._lib.filesearch_get(i).decode() for i in range(n)]

    def list_dir(self, path: str, max_results: int = 200) -> list:
        """Lista archivos en un directorio (no recursivo)."""
        n = self._lib.filesearch_list_dir(path.encode(), max_results)
        return [self._lib.filesearch_get(i).decode() for i in range(n)]

    def find_with_meta(self, root: str, pattern: str = "",
                       ext: str = "", max_results: int = 500) -> list:
        """
        Como find() pero retorna dicts con ruta, nombre, directorio y tamaño.
        """
        n = self._lib.filesearch_find(root.encode(), pattern.encode(),
                                       ext.encode(), max_results)
        results = []
        for i in range(n):
            size = self._lib.filesearch_size(i)
            results.append({
                "path":   self._lib.filesearch_get(i).decode(),
                "name":   self._lib.filesearch_name(i).decode(),
                "parent": self._lib.filesearch_parent(i).decode(),
                "size_kb": round(size / 1024, 1) if size >= 0 else -1,
            })
        return results

// vad.cpp — Voice Activity Detection para JARVIS
// Reemplaza el timeout fijo en speech_to_text.py
// Usa RMS + Zero Crossing Rate + EMA para detectar voz/silencio
// Compila: g++ -O2 -fPIC -shared -std=c++17 -o vad.so vad.cpp

#include <cmath>
#include <cstring>

// ─── Estructura de estado (fuera de extern "C") ───────────────────────────
struct VadState {
    float rms_threshold;       // energía mínima para considerar habla (~0.015)
    float zcr_threshold;       // ZCR máximo para filtrar ruido agudo (~0.15)
    int   silence_frames;      // frames consecutivos de silencio actual
    int   min_silence_frames;  // frames de silencio para declarar fin de habla
    int   speaking;            // 1 si estamos en medio de habla
    float smoothed_rms;        // RMS suavizado con EMA
    float ema_alpha;           // factor EMA (0.1=lento, 0.5=rápido)
};

// ─── Helpers internos ────────────────────────────────────────────────────
static float calc_rms(const float* s, int n) {
    float sum = 0.0f;
    for (int i = 0; i < n; i++) sum += s[i] * s[i];
    return (n > 0) ? sqrtf(sum / n) : 0.0f;
}

static float calc_zcr(const float* s, int n) {
    int crossings = 0;
    for (int i = 1; i < n; i++)
        if ((s[i] >= 0.0f) != (s[i-1] >= 0.0f)) crossings++;
    return (n > 1) ? (float)crossings / (n - 1) : 0.0f;
}

// ─── API pública ─────────────────────────────────────────────────────────
extern "C" {

// Crea un detector VAD.
// rms_threshold      : ~0.015 para mic típico (bajar si corta mucho)
// zcr_threshold      : ~0.15 (sube si detecta ruido como voz)
// min_silence_frames : cuántos frames de silencio para "fin de habla" (~15 = 500ms a 16kHz/512)
// ema_alpha          : suavizado de energía (0.3 es buen punto medio)
void* vad_create(float rms_threshold, float zcr_threshold,
                 int min_silence_frames, float ema_alpha) {
    VadState* s       = new VadState();
    s->rms_threshold      = rms_threshold;
    s->zcr_threshold      = zcr_threshold;
    s->min_silence_frames = min_silence_frames;
    s->silence_frames     = 0;
    s->speaking           = 0;
    s->smoothed_rms       = 0.0f;
    s->ema_alpha          = ema_alpha;
    return s;
}

void vad_destroy(void* handle) {
    delete static_cast<VadState*>(handle);
}

// Procesa un bloque de muestras float32 en rango [-1, 1].
// Retorna:
//   0  → silencio puro
//   1  → hablando
//  -1  → fin de habla (justo terminó)
int vad_process(void* handle, const float* samples, int count) {
    VadState* s = static_cast<VadState*>(handle);

    float rms = calc_rms(samples, count);
    float zcr = calc_zcr(samples, count);

    // EMA suaviza picos de ruido transitorio
    s->smoothed_rms = s->ema_alpha * rms + (1.0f - s->ema_alpha) * s->smoothed_rms;

    // Habla: energía suficiente Y no es solo ruido de alta frecuencia (zcr alto)
    int is_speech = (s->smoothed_rms > s->rms_threshold &&
                     zcr < s->zcr_threshold) ? 1 : 0;

    if (is_speech) {
        s->speaking       = 1;
        s->silence_frames = 0;
        return 1;
    }

    if (s->speaking) {
        s->silence_frames++;
        if (s->silence_frames >= s->min_silence_frames) {
            s->speaking       = 0;
            s->silence_frames = 0;
            return -1;  // fin de habla
        }
        return 1;  // silencio corto dentro de habla — seguimos contando como habla
    }

    return 0;  // silencio puro
}

// Consulta instantánea sin estado: ¿hay voz en este bloque?
int vad_is_speech(const float* samples, int count,
                  float rms_threshold, float zcr_threshold) {
    float rms = calc_rms(samples, count);
    float zcr = calc_zcr(samples, count);
    return (rms > rms_threshold && zcr < zcr_threshold) ? 1 : 0;
}

// Energía RMS del bloque (útil para calibrar umbrales desde Python)
float vad_rms(const float* samples, int count) {
    return calc_rms(samples, count);
}

void vad_reset(void* handle) {
    VadState* s       = static_cast<VadState*>(handle);
    s->silence_frames = 0;
    s->speaking       = 0;
    s->smoothed_rms   = 0.0f;
}

}  // extern "C"

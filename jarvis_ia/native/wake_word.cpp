// wake_word.cpp — Detector de palabra de activación para JARVIS
// NUEVO módulo — no tenía equivalente en el proyecto original
// Detecta energía con la duración correcta de "hey jarvis" (~400ms)
// El lado Python confirma con Whisper/Google STT para evitar falsos positivos
// Compila: g++ -O2 -fPIC -shared -std=c++17 -o wake_word.so wake_word.cpp

#include <cmath>
#include <deque>

// ─── Estado interno ────────────────────────────────────────────────────────
struct WakeState {
    float rms_threshold;         // energía mínima para considerar "hay voz"
    int   target_min;            // duración mínima del burst en frames
    int   target_max;            // duración máxima del burst en frames
    int   consecutive_speech;    // frames de voz consecutivos en el burst actual
    int   consecutive_silence;   // frames de silencio tras el burst
    int   cooldown;              // frames de espera para evitar doble disparo
    int   frames_per_buffer;
    int   sample_rate;
    std::deque<float>* history;  // historial de RMS (para debug/calibración)
};

extern "C" {

// sensitivity : 0.0 a 1.0 (mayor = más sensible, más falsos positivos)
// sample_rate : típicamente 16000
// frames_per_buffer : típicamente 512
void* wake_create(float sensitivity, int sample_rate, int frames_per_buffer) {
    WakeState* s          = new WakeState();
    s->sample_rate        = sample_rate;
    s->frames_per_buffer  = frames_per_buffer;

    // Umbral de energía inversamente proporcional a la sensibilidad
    s->rms_threshold = 0.018f * (1.0f - sensitivity * 0.75f);

    // "hey jarvis" dura ~400ms → ventana de 250ms a 600ms
    float fps = (float)sample_rate / frames_per_buffer;
    s->target_min = (int)(0.25f * fps);
    s->target_max = (int)(0.60f * fps);

    s->consecutive_speech  = 0;
    s->consecutive_silence = 0;
    s->cooldown            = 0;
    s->history             = new std::deque<float>();
    return s;
}

void wake_destroy(void* handle) {
    WakeState* s = static_cast<WakeState*>(handle);
    delete s->history;
    delete s;
}

// Procesa un bloque de muestras.
// Retorna 1 si detectó posible wake word, 0 si no.
// Después de recibir 1, el caller debe confirmar con STT.
int wake_process(void* handle, const float* samples, int count) {
    WakeState* s = static_cast<WakeState*>(handle);

    if (s->cooldown > 0) {
        s->cooldown--;
        return 0;
    }

    // RMS del bloque
    float sum = 0.0f;
    for (int i = 0; i < count; i++) sum += samples[i] * samples[i];
    float rms = (count > 0) ? sqrtf(sum / count) : 0.0f;

    // Historial para calibración (máx 3 segundos)
    int max_history = (int)(3.0f * s->sample_rate / s->frames_per_buffer);
    s->history->push_back(rms);
    if ((int)s->history->size() > max_history)
        s->history->pop_front();

    if (rms > s->rms_threshold) {
        // Hay energía: incrementar contador de habla
        s->consecutive_speech++;
        s->consecutive_silence = 0;
    } else {
        s->consecutive_silence++;

        // Acaba de terminar un burst de habla
        if (s->consecutive_speech > 0) {
            int burst = s->consecutive_speech;
            s->consecutive_speech = 0;

            // ¿El burst tiene la duración típica de la wake word?
            if (burst >= s->target_min && burst <= s->target_max) {
                // Cooldown para evitar doble disparo (~1 segundo)
                s->cooldown = (int)((float)s->sample_rate / s->frames_per_buffer);
                return 1;
            }
        }
    }

    return 0;
}

// Energía RMS promedio del historial reciente (útil para calibrar threshold)
float wake_recent_rms(void* handle) {
    WakeState* s = static_cast<WakeState*>(handle);
    if (s->history->empty()) return 0.0f;
    float sum = 0.0f;
    for (float v : *s->history) sum += v;
    return sum / s->history->size();
}

void wake_reset(void* handle) {
    WakeState* s           = static_cast<WakeState*>(handle);
    s->consecutive_speech  = 0;
    s->consecutive_silence = 0;
    s->cooldown            = 0;
    s->history->clear();
}

}  // extern "C"

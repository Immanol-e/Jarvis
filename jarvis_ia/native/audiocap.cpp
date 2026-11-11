// audiocap.cpp — Captura de micrófono con PortAudio para JARVIS
// Reemplaza PyAudio + SpeechRecognition para la captura de audio
// Ventajas: menor latencia, buffer propio, sin GIL de Python en el hilo de audio
// Requiere: libportaudio2-dev (Linux) / portaudio (brew macOS)
// Compila: g++ -O2 -fPIC -shared -std=c++17 -o audiocap.so audiocap.cpp -lportaudio -lpthread

#include <portaudio.h>
#include <cstring>
#include <cstdlib>
#include <queue>
#include <mutex>

// ─── Estado de la captura ─────────────────────────────────────────────────
struct AudioCapState {
    PaStream*          stream;
    std::queue<float>* ring;           // ring buffer de muestras float32
    std::mutex*        mtx;
    int                sample_rate;
    int                channels;
    int                frames_per_buffer;
    int                overflow_count;
    int                max_samples;    // capacidad máxima del ring (10 segundos)
};

// Callback de PortAudio — se ejecuta en el hilo de audio, NO en Python
static int pa_callback(const void* input, void*,
                       unsigned long frame_count,
                       const PaStreamCallbackTimeInfo*,
                       PaStreamCallbackFlags,
                       void* user_data) {
    AudioCapState* s  = static_cast<AudioCapState*>(user_data);
    const float*   in = static_cast<const float*>(input);
    int total = (int)frame_count * s->channels;

    std::lock_guard<std::mutex> lock(*s->mtx);

    // Si el ring está lleno, descarta las muestras más antiguas
    int overflow = (int)s->ring->size() + total - s->max_samples;
    if (overflow > 0) {
        s->overflow_count++;
        for (int i = 0; i < overflow && !s->ring->empty(); i++)
            s->ring->pop();
    }

    for (int i = 0; i < total; i++)
        s->ring->push(in[i]);

    return paContinue;
}

extern "C" {

// Abre el micrófono por defecto del sistema.
// sample_rate       : 16000 Hz es lo estándar para STT
// channels          : 1 (mono) es suficiente para voz
// frames_per_buffer : 512 da ~32ms de latencia a 16kHz
// Retorna NULL en caso de error.
void* audiocap_open(int sample_rate, int channels, int frames_per_buffer) {
    if (Pa_Initialize() != paNoError) return nullptr;

    PaDeviceIndex dev = Pa_GetDefaultInputDevice();
    if (dev == paNoDevice) { Pa_Terminate(); return nullptr; }

    PaStreamParameters params;
    params.device                    = dev;
    params.channelCount              = channels;
    params.sampleFormat              = paFloat32;
    params.suggestedLatency          = Pa_GetDeviceInfo(dev)->defaultLowInputLatency;
    params.hostApiSpecificStreamInfo = nullptr;

    AudioCapState* s      = new AudioCapState();
    s->sample_rate        = sample_rate;
    s->channels           = channels;
    s->frames_per_buffer  = frames_per_buffer;
    s->ring               = new std::queue<float>();
    s->mtx                = new std::mutex();
    s->overflow_count     = 0;
    s->max_samples        = sample_rate * channels * 10;  // 10 segundos

    PaError err = Pa_OpenStream(&s->stream, &params, nullptr,
                                sample_rate, frames_per_buffer,
                                paClipOff, pa_callback, s);
    if (err != paNoError) {
        delete s->ring;
        delete s->mtx;
        delete s;
        Pa_Terminate();
        return nullptr;
    }

    Pa_StartStream(s->stream);
    return s;
}

void audiocap_close(void* handle) {
    if (!handle) return;
    AudioCapState* s = static_cast<AudioCapState*>(handle);
    Pa_StopStream(s->stream);
    Pa_CloseStream(s->stream);
    Pa_Terminate();
    delete s->ring;
    delete s->mtx;
    delete s;
}

// Lee hasta `frames` frames en `buffer` (float32 entrelazado si channels>1).
// Retorna el número de frames realmente leídos (puede ser menor si el buffer no tiene suficiente).
int audiocap_read(void* handle, float* buffer, int frames) {
    AudioCapState* s = static_cast<AudioCapState*>(handle);
    std::lock_guard<std::mutex> lock(*s->mtx);

    int wanted = frames * s->channels;
    int avail  = (int)s->ring->size();
    int n      = (wanted < avail) ? wanted : avail;

    for (int i = 0; i < n; i++) {
        buffer[i] = s->ring->front();
        s->ring->pop();
    }
    return n / s->channels;
}

// Frames disponibles en el buffer interno
int audiocap_available(void* handle) {
    AudioCapState* s = static_cast<AudioCapState*>(handle);
    std::lock_guard<std::mutex> lock(*s->mtx);
    return (int)s->ring->size() / s->channels;
}

// Descarta todo el audio acumulado en el buffer
void audiocap_flush(void* handle) {
    AudioCapState* s = static_cast<AudioCapState*>(handle);
    std::lock_guard<std::mutex> lock(*s->mtx);
    while (!s->ring->empty()) s->ring->pop();
}

// Cuántas veces se desbordó el buffer (útil para detectar frames_per_buffer muy pequeño)
int audiocap_overflow_count(void* handle) {
    AudioCapState* s = static_cast<AudioCapState*>(handle);
    return s->overflow_count;
}

// Sample rate con el que se abrió
int audiocap_sample_rate(void* handle) {
    return static_cast<AudioCapState*>(handle)->sample_rate;
}

}  // extern "C"

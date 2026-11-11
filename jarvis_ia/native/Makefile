# Makefile — Módulos C++ nativos de JARVIS
# Uso: make all
#
# Dependencias:
#   Linux  : sudo apt install g++ portaudio19-dev pkg-config
#   macOS  : brew install portaudio
#   Windows: instalar portaudio + MinGW o MSVC

CXX      := g++
CXXFLAGS := -O2 -fPIC -std=c++17 -Wall -Wextra
LDFLAGS  := -shared

# Extensión de la librería según el OS
ifeq ($(OS), Windows_NT)
  EXT := .dll
  LDFLAGS += -static-libgcc -static-libstdc++
else
  UNAME := $(shell uname -s)
  ifeq ($(UNAME), Darwin)
    EXT := .dylib
    LDFLAGS += -undefined dynamic_lookup
  else
    EXT := .so
  endif
endif

# PortAudio para audiocap
PA_CFLAGS := $(shell pkg-config --cflags portaudio-2.0 2>/dev/null || echo "")
PA_LIBS   := $(shell pkg-config --libs   portaudio-2.0 2>/dev/null || echo "-lportaudio")

TARGETS := vad$(EXT) wake_word$(EXT) audiocap$(EXT) sysmon$(EXT) filesearch$(EXT)

.PHONY: all clean help

all: $(TARGETS)
	@echo ""
	@echo "Compilación completa. Módulos generados:"
	@ls -lh *$(EXT)

# ── Módulos individuales ──────────────────────────────────────────────────────

vad$(EXT): vad.cpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $<
	@echo "  [OK] vad$(EXT)"

wake_word$(EXT): wake_word.cpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $<
	@echo "  [OK] wake_word$(EXT)"

audiocap$(EXT): audiocap.cpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $< $(PA_CFLAGS) $(PA_LIBS) -lpthread
	@echo "  [OK] audiocap$(EXT)"

sysmon$(EXT): sysmon.cpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $<
	@echo "  [OK] sysmon$(EXT)"

filesearch$(EXT): filesearch.cpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $<
	@echo "  [OK] filesearch$(EXT)"

# ── Utilidades ────────────────────────────────────────────────────────────────

clean:
	rm -f *.so *.dll *.dylib
	@echo "Librerías eliminadas."

help:
	@echo "Targets disponibles:"
	@echo "  make all          — compila todos los módulos"
	@echo "  make vad$(EXT)        — solo VAD"
	@echo "  make wake_word$(EXT)  — solo wake word"
	@echo "  make audiocap$(EXT)   — solo captura de audio (requiere portaudio)"
	@echo "  make sysmon$(EXT)     — solo monitor de sistema"
	@echo "  make filesearch$(EXT) — solo búsqueda de archivos"
	@echo "  make clean        — elimina las librerías compiladas"

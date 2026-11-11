// filesearch.cpp — Búsqueda recursiva de archivos para JARVIS
// Reemplaza os.walk() en file_manager_skill.py y code_editor_skill.py
// Usa std::filesystem (C++17) que llama directamente a las APIs del OS
// En carpetas grandes es 3-10x más rápido que os.walk() en Python
// Compila: g++ -O2 -fPIC -shared -std=c++17 -o filesearch.so filesearch.cpp

#include <filesystem>
#include <string>
#include <vector>
#include <algorithm>
#include <cctype>
#include <cstring>

namespace fs = std::filesystem;

// ─── Helpers ──────────────────────────────────────────────────────────────
static std::string to_lower(const std::string& s) {
    std::string out = s;
    std::transform(out.begin(), out.end(), out.begin(),
                   [](unsigned char c) { return std::tolower(c); });
    return out;
}

static bool str_contains(const std::string& haystack, const std::string& needle_lower) {
    if (needle_lower.empty()) return true;
    return to_lower(haystack).find(needle_lower) != std::string::npos;
}

// ─── Resultados globales del último find() ────────────────────────────────
// (thread-unsafe por diseño — JARVIS es single-threaded para skills)
static std::vector<std::string> g_results;

extern "C" {

// Búsqueda principal.
//
// root        : directorio raíz donde buscar (ej. "/home/user" o "C:\\Users\\")
// pattern     : subcadena en el nombre del archivo, case-insensitive ("" = cualquiera)
// ext         : extensión requerida (ej. ".py", ".txt", "" = cualquiera)
// max_results : límite de resultados (0 = sin límite)
//
// Retorna el número de archivos encontrados.
// Usa filesearch_get(i) para obtener cada ruta.
int filesearch_find(const char* root, const char* pattern,
                    const char* ext, int max_results) {
    g_results.clear();

    std::string pat_low = to_lower(std::string(pattern ? pattern : ""));
    std::string ext_low = to_lower(std::string(ext     ? ext     : ""));

    try {
        auto opts = fs::directory_options::skip_permission_denied;
        for (const auto& entry : fs::recursive_directory_iterator(root, opts)) {
            if (!entry.is_regular_file()) continue;

            const fs::path& p    = entry.path();
            std::string     name = p.filename().string();

            // Filtro por extensión
            if (!ext_low.empty()) {
                std::string file_ext = to_lower(p.extension().string());
                if (file_ext != ext_low) continue;
            }

            // Filtro por nombre
            if (!pat_low.empty() && !str_contains(name, pat_low)) continue;

            g_results.push_back(p.string());

            if (max_results > 0 && (int)g_results.size() >= max_results) break;
        }
    } catch (...) {
        // Ignora errores de permisos o rutas inválidas
    }

    return (int)g_results.size();
}

// Número de resultados del último find
int filesearch_count() {
    return (int)g_results.size();
}

// Ruta completa del resultado i (válido hasta el próximo find)
const char* filesearch_get(int i) {
    if (i < 0 || i >= (int)g_results.size()) return nullptr;
    return g_results[i].c_str();
}

// Directorio padre del resultado i
const char* filesearch_parent(int i) {
    if (i < 0 || i >= (int)g_results.size()) return nullptr;
    static std::string buf;
    buf = fs::path(g_results[i]).parent_path().string();
    return buf.c_str();
}

// Solo nombre de archivo (sin ruta) del resultado i
const char* filesearch_name(int i) {
    if (i < 0 || i >= (int)g_results.size()) return nullptr;
    static std::string buf;
    buf = fs::path(g_results[i]).filename().string();
    return buf.c_str();
}

// Tamaño en bytes del resultado i (-1 si no se puede leer)
long long filesearch_size(int i) {
    if (i < 0 || i >= (int)g_results.size()) return -1;
    std::error_code ec;
    auto sz = fs::file_size(g_results[i], ec);
    return ec ? -1LL : (long long)sz;
}

// Shortcut: busca solo por extensión en todo el árbol
int filesearch_by_ext(const char* root, const char* ext, int max_results) {
    return filesearch_find(root, "", ext, max_results);
}

// Shortcut: lista todos los archivos en un directorio (no recursivo)
int filesearch_list_dir(const char* path, int max_results) {
    g_results.clear();
    try {
        for (const auto& entry : fs::directory_iterator(path)) {
            if (!entry.is_regular_file()) continue;
            g_results.push_back(entry.path().string());
            if (max_results > 0 && (int)g_results.size() >= max_results) break;
        }
    } catch (...) {}
    return (int)g_results.size();
}

}  // extern "C"

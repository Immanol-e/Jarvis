// sysmon.cpp — Monitoreo de sistema vía APIs nativas del OS para JARVIS
// Reemplaza psutil en system_skill.py (sin dependencia de Python externa)
// Compatible: Linux, Windows, macOS
// Compila Linux : g++ -O2 -fPIC -shared -std=c++17 -o sysmon.so sysmon.cpp
// Compila macOS : g++ -O2 -fPIC -shared -std=c++17 -o sysmon.so sysmon.cpp -framework CoreFoundation
// Compila Win   : g++ -O2 -shared -std=c++17 -o sysmon.dll sysmon.cpp -lpdh -lpsapi

#include <cstdio>
#include <cstring>
#include <cstdlib>

// ─── Plataforma ─────────────────────────────────────────────────────────────
#if defined(_WIN32)
  #define WIN32_LEAN_AND_MEAN
  #include <windows.h>
  #include <psapi.h>
  #include <pdh.h>
  #pragma comment(lib, "pdh.lib")
  #pragma comment(lib, "psapi.lib")
  #define SYSMON_WIN

#elif defined(__APPLE__)
  #include <sys/sysctl.h>
  #include <sys/types.h>
  #include <sys/statvfs.h>
  #include <mach/mach.h>
  #include <mach/host_info.h>
  #include <unistd.h>
  #define SYSMON_MAC

#else
  // Linux
  #include <sys/sysinfo.h>
  #include <sys/statvfs.h>
  #include <unistd.h>
  #include <fstream>
  #include <string>
  #define SYSMON_LINUX
#endif

// ─── CPU ─────────────────────────────────────────────────────────────────────
#ifdef SYSMON_LINUX
static long long g_prev_idle = 0, g_prev_total = 0;
#endif

#ifdef SYSMON_WIN
static PDH_HQUERY   g_cpu_query   = nullptr;
static PDH_HCOUNTER g_cpu_counter = nullptr;
#endif

#ifdef SYSMON_MAC
static host_cpu_load_info_data_t g_prev_cpu = {};
#endif

extern "C" {

// Porcentaje de uso de CPU (0-100).
// En Linux: requiere dos llamadas con ~100ms de diferencia para ser preciso.
float sysmon_cpu_percent() {
#ifdef SYSMON_LINUX
    std::ifstream f("/proc/stat");
    if (!f.is_open()) return -1.0f;
    std::string tag;
    long long u, n, s, idle, iw, irq, sirq;
    f >> tag >> u >> n >> s >> idle >> iw >> irq >> sirq;
    long long total = u + n + s + idle + iw + irq + sirq;
    long long dt = total - g_prev_total;
    long long di = idle  - g_prev_idle;
    g_prev_total = total;
    g_prev_idle  = idle;
    if (dt == 0) return 0.0f;
    return (float)(dt - di) / dt * 100.0f;

#elif defined(SYSMON_WIN)
    if (!g_cpu_query) {
        PdhOpenQuery(nullptr, 0, &g_cpu_query);
        PdhAddCounterW(g_cpu_query,
                       L"\\Processor(_Total)\\% Processor Time",
                       0, &g_cpu_counter);
        PdhCollectQueryData(g_cpu_query);
        Sleep(100);
    }
    PdhCollectQueryData(g_cpu_query);
    PDH_FMT_COUNTERVALUE val;
    PdhGetFormattedCounterValue(g_cpu_counter, PDH_FMT_DOUBLE, nullptr, &val);
    return (float)val.doubleValue;

#elif defined(SYSMON_MAC)
    mach_msg_type_number_t count = HOST_CPU_LOAD_INFO_COUNT;
    host_cpu_load_info_data_t info;
    host_statistics(mach_host_self(), HOST_CPU_LOAD_INFO,
                    (host_info_t)&info, &count);
    long long u = info.cpu_ticks[CPU_STATE_USER]   - g_prev_cpu.cpu_ticks[CPU_STATE_USER];
    long long s = info.cpu_ticks[CPU_STATE_SYSTEM] - g_prev_cpu.cpu_ticks[CPU_STATE_SYSTEM];
    long long i = info.cpu_ticks[CPU_STATE_IDLE]   - g_prev_cpu.cpu_ticks[CPU_STATE_IDLE];
    long long n = info.cpu_ticks[CPU_STATE_NICE]   - g_prev_cpu.cpu_ticks[CPU_STATE_NICE];
    g_prev_cpu = info;
    long long total = u + s + i + n;
    if (total == 0) return 0.0f;
    return (float)(u + s + n) / total * 100.0f;
#endif
}

// ─── RAM ─────────────────────────────────────────────────────────────────────
void sysmon_ram(long long* total_bytes, long long* used_bytes, float* percent) {
#ifdef SYSMON_LINUX
    std::ifstream f("/proc/meminfo");
    if (!f.is_open()) { *total_bytes = *used_bytes = 0; *percent = 0; return; }
    long long total_kb = 0, free_kb = 0, buffers_kb = 0, cached_kb = 0, sreclaimable_kb = 0;
    std::string key, unit;
    long long val;
    while (f >> key >> val >> unit) {
        if (key == "MemTotal:")       total_kb       = val;
        if (key == "MemFree:")        free_kb        = val;
        if (key == "Buffers:")        buffers_kb     = val;
        if (key == "Cached:")         cached_kb      = val;
        if (key == "SReclaimable:")   sreclaimable_kb = val;
    }
    long long avail_kb = free_kb + buffers_kb + cached_kb + sreclaimable_kb;
    *total_bytes = total_kb * 1024LL;
    *used_bytes  = (total_kb - avail_kb) * 1024LL;
    if (*used_bytes < 0) *used_bytes = 0;
    *percent = (*total_bytes > 0)
               ? (float)*used_bytes / *total_bytes * 100.0f : 0.0f;

#elif defined(SYSMON_WIN)
    MEMORYSTATUSEX ms;
    ms.dwLength = sizeof(ms);
    GlobalMemoryStatusEx(&ms);
    *total_bytes = (long long)ms.ullTotalPhys;
    *used_bytes  = (long long)(ms.ullTotalPhys - ms.ullAvailPhys);
    *percent     = (float)ms.dwMemoryLoad;

#elif defined(SYSMON_MAC)
    int64_t total = 0;
    size_t  len   = sizeof(total);
    sysctlbyname("hw.memsize", &total, &len, nullptr, 0);
    *total_bytes = (long long)total;

    vm_statistics64_data_t vm;
    mach_msg_type_number_t cnt = HOST_VM_INFO64_COUNT;
    host_statistics64(mach_host_self(), HOST_VM_INFO64,
                      (host_info64_t)&vm, &cnt);
    int64_t page = getpagesize();
    int64_t free = (vm.free_count + vm.inactive_count) * page;
    *used_bytes  = total - free;
    *percent     = (total > 0) ? (float)*used_bytes / total * 100.0f : 0.0f;
#endif
}

// ─── DISCO ─────────────────────────────────────────────────────────────────
void sysmon_disk(const char* path,
                 long long* total_bytes, long long* free_bytes, float* percent) {
#ifdef SYSMON_WIN
    wchar_t wpath[512];
    mbstowcs(wpath, path, 512);
    ULARGE_INTEGER tot, fr, caller;
    GetDiskFreeSpaceExW(wpath, &caller, &tot, &fr);
    *total_bytes = (long long)tot.QuadPart;
    *free_bytes  = (long long)fr.QuadPart;
#else
    struct statvfs st;
    if (statvfs(path, &st) != 0) {
        *total_bytes = *free_bytes = 0; *percent = 0; return;
    }
    *total_bytes = (long long)st.f_frsize * (long long)st.f_blocks;
    *free_bytes  = (long long)st.f_frsize * (long long)st.f_bfree;
#endif
    long long used = *total_bytes - *free_bytes;
    *percent = (*total_bytes > 0) ? (float)used / *total_bytes * 100.0f : 0.0f;
}

// ─── TEMPERATURA CPU ────────────────────────────────────────────────────────
// Retorna °C. Retorna -1.0 si no está disponible en este OS/hardware.
float sysmon_cpu_temp() {
#ifdef SYSMON_LINUX
    // Buscar thermal_zone0 (AMD/Intel en la mayoría de distros)
    const char* paths[] = {
        "/sys/class/thermal/thermal_zone0/temp",
        "/sys/class/thermal/thermal_zone1/temp",
        nullptr
    };
    for (int i = 0; paths[i]; i++) {
        FILE* f = fopen(paths[i], "r");
        if (!f) continue;
        int millic = 0;
        if (fscanf(f, "%d", &millic) == 1) {
            fclose(f);
            return millic / 1000.0f;
        }
        fclose(f);
    }
    return -1.0f;
#else
    return -1.0f;  // No implementado en Windows/Mac en esta versión
#endif
}

// ─── JSON de todo (útil para respuestas de JARVIS) ─────────────────────────
static char g_json[512];

const char* sysmon_stats_json() {
    long long ram_total, ram_used, disk_total, disk_free;
    float     ram_pct, disk_pct;
    float     cpu_pct  = sysmon_cpu_percent();
    float     cpu_temp = sysmon_cpu_temp();

    sysmon_ram(&ram_total, &ram_used, &ram_pct);
#ifdef SYSMON_WIN
    sysmon_disk("C:\\", &disk_total, &disk_free, &disk_pct);
#else
    sysmon_disk("/", &disk_total, &disk_free, &disk_pct);
#endif

    snprintf(g_json, sizeof(g_json),
        "{"
        "\"cpu_percent\":%.1f,"
        "\"cpu_temp\":%.1f,"
        "\"ram_total_gb\":%.2f,"
        "\"ram_used_gb\":%.2f,"
        "\"ram_percent\":%.1f,"
        "\"disk_total_gb\":%.2f,"
        "\"disk_free_gb\":%.2f,"
        "\"disk_percent\":%.1f"
        "}",
        cpu_pct, cpu_temp,
        ram_total / 1e9, ram_used / 1e9, ram_pct,
        disk_total / 1e9, disk_free / 1e9, disk_pct);

    return g_json;
}

}  // extern "C"

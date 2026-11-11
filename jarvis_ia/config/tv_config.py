"""
Fuente única de verdad para todo lo relacionado con TV/Android TV.
Importar desde aquí en tv_skill.py e intent_classifier.py
para evitar que ambos tengan listas distintas.
"""

# Paquetes de apps en Android TV
TV_APPS = {
    "youtube":      "com.google.android.youtube.tv",
    "netflix":      "com.netflix.ninja",
    "prime video":  "com.amazon.amazonvideo.livingroom",
    "amazon prime": "com.amazon.amazonvideo.livingroom",
    "disney":       "com.disney.disneyplus",
    "disney plus":  "com.disney.disneyplus",
    "hbo":          "com.hbo.hbonow",
    "max":          "com.hbo.hbonow",
    "spotify":      "com.spotify.tv.android",
    "twitch":       "tv.twitch.android.app",
    "plex":         "com.plexapp.android",
    "kodi":         "org.xbmc.kodi",
    "vix":          "com.vix.vixapp",
    "pluto":        "tv.pluto.android",
    "crunchyroll":  "com.crunchyroll.crunchyroid",
    "configuracion":"com.android.settings",
    "ajustes":      "com.android.settings",
}

TV_PLATAFORMAS = [
    "prime video", "amazon prime", "disney plus",
    "crunchyroll", "youtube", "netflix", "disney",
    "hbo", "max", "spotify", "twitch", "plex",
    "vix", "pluto", "kodi",
]

TV_PALABRAS = ["tv", "tele", "televisión", "television", "televisor"]

# ── Celular ────────────────────────────────────────────────────────────────
# Pon aquí la IP que reservaste en el router para tu celular.
# Cómo encontrarla: Ajustes → Wi-Fi → tu red → "Dirección IP"
# Después la fijas en el router (busca "DHCP reservation" o "IP fija por MAC").
PHONE_IP   = "192.168.1.100"   # ← CAMBIA ESTO por tu IP real
PHONE_PORT = 5555               # puerto ADB estándar — no cambiar
import webbrowser
from urllib.parse import quote

try:
    import pywhatkit
except ImportError:
    pywhatkit = None


class WebSkill:
    def run(self, data):
        action = data.get("action", "")
        query = data.get("query", "").strip()

        if action == "open_youtube":
            webbrowser.open("https://www.youtube.com")
            return "Abriendo YouTube."

        if action == "open_google":
            webbrowser.open("https://www.google.com")
            return "Abriendo Google."

        if action == "search_google":
            if not query:
                return "Dime qué quieres buscar en Google."

            url = "https://www.google.com/search?q=" + quote(query)
            webbrowser.open(url)
            return f"Buscando {query} en Google."

        if action == "search_youtube":
            if not query:
                return "Dime qué quieres buscar en YouTube."

            url = "https://www.youtube.com/results?search_query=" + quote(query)
            webbrowser.open(url)
            return f"Buscando {query} en YouTube."

        if action == "play_youtube":
            if not query:
                return "Dime qué video quieres reproducir en YouTube."

            if pywhatkit:
                pywhatkit.playonyt(query)
                return f"Reproduciendo {query} en YouTube."

            url = "https://www.youtube.com/results?search_query=" + quote(query)
            webbrowser.open(url)
            return f"Buscando {query} en YouTube."

        return "No entendí la acción web."

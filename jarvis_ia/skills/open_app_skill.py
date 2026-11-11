import subprocess
import platform
import webbrowser


class OpenAppSkill:
    def run(self, data):
        app_name = data.get("app_name", "").strip().lower()

        if not app_name:
            return "Dime qué aplicación quieres abrir."

        system = platform.system()

        try:
            if system == "Windows":
                return self.open_windows_app(app_name)

            if system == "Linux":
                return self.open_linux_app(app_name)

            if system == "Darwin":
                return self.open_macos_app(app_name)

            return "No reconozco este sistema operativo."

        except Exception as error:
            return f"No pude abrir {app_name}. Error: {error}"

    def open_windows_app(self, app_name):
        apps = {
            "chrome": "chrome",
            "google chrome": "chrome",
            "bloc de notas": "notepad",
            "notepad": "notepad",
            "calculadora": "calc",
            "vscode": "code",
            "visual studio code": "code",
            "paint": "mspaint",
            "cmd": "cmd",
            "terminal": "wt",
            "spotify": "spotify",
            "whatsapp": "whatsapp",
            "discord": "discord",
            "brave": "brave",
            "edge": "msedge",
            "crunchyroll": "explorer shell:AppsFolder\\15EF7777.Crunchyroll_mgdgtskya6f22!App"
        }

        websites = {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "netflix": "https://www.netflix.com",
            "facebook": "https://www.facebook.com",
            "instagram": "https://www.instagram.com",
            "tiktok": "https://www.tiktok.com",
            "gmail": "https://mail.google.com",
            "chatgpt": "https://chatgpt.com",
            "github": "https://github.com",
            "crunchyroll web": "https://www.crunchyroll.com"
        }

        if app_name in apps:
            command = apps[app_name]
            subprocess.Popen(command, shell=True)
            return f"Abriendo {app_name}."

        if app_name in websites:
            webbrowser.open(websites[app_name])
            return f"Abriendo {app_name} en la web."

        return self.open_web_fallback(app_name)

    def open_linux_app(self, app_name):
        apps = {
            "chrome": "google-chrome",
            "google chrome": "google-chrome",
            "brave": "brave",
            "firefox": "firefox",
            "vscode": "code",
            "visual studio code": "code",
            "terminal": "konsole",
            "spotify": "spotify",
            "discord": "discord"
        }

        websites = {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "crunchyroll": "https://www.crunchyroll.com",
            "netflix": "https://www.netflix.com",
            "gmail": "https://mail.google.com",
            "chatgpt": "https://chatgpt.com",
            "github": "https://github.com"
        }

        if app_name in apps:
            command = apps[app_name]
            subprocess.Popen(command, shell=True)
            return f"Abriendo {app_name}."

        if app_name in websites:
            webbrowser.open(websites[app_name])
            return f"Abriendo {app_name} en la web."

        return self.open_web_fallback(app_name)

    def open_macos_app(self, app_name):
        websites = {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "crunchyroll": "https://www.crunchyroll.com",
            "netflix": "https://www.netflix.com",
            "gmail": "https://mail.google.com",
            "chatgpt": "https://chatgpt.com",
            "github": "https://github.com"
        }

        if app_name in websites:
            webbrowser.open(websites[app_name])
            return f"Abriendo {app_name} en la web."

        subprocess.Popen(["open", "-a", app_name])
        return f"Abriendo {app_name}."

    def open_web_fallback(self, app_name):
        query = app_name.replace(" ", "+")
        webbrowser.open(f"https://www.google.com/search?q={query}")
        return f"No encontré {app_name} como aplicación. Lo busqué en Google."
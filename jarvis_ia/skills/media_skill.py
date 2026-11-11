try:
    import pyautogui
except Exception:
    pyautogui = None


class MediaSkill:
    def run(self, data):
        if pyautogui is None:
            return "Falta instalar o configurar pyautogui. Ejecuta: python -m pip install pyautogui"

        action = data.get("action", "")

        if action == "pause":
            pyautogui.press("space")
            return "Video pausado."

        if action == "play":
            pyautogui.press("space")
            return "Continuando reproducción."

        if action == "volume_up":
            pyautogui.press("volumeup")
            return "Subiendo volumen."

        if action == "volume_down":
            pyautogui.press("volumedown")
            return "Bajando volumen."

        if action == "mute":
            pyautogui.press("volumemute")
            return "Volumen silenciado."

        if action == "fullscreen":
            pyautogui.press("f")
            return "Activando pantalla completa."

        if action == "next":
            pyautogui.hotkey("shift", "n")
            return "Pasando al siguiente video."

        if action == "back":
            pyautogui.press("j")
            return "Retrocediendo el video."

        if action == "forward":
            pyautogui.press("l")
            return "Adelantando el video."

        return "No entendí la acción multimedia."

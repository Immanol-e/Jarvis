from datetime import datetime

class TimeSkill:
    def run(self, data):
        current_time = datetime.now().strftime("%H:%M")
        return f"Son las {current_time}."

from skills.tv_skill          import TVSkill
from skills.phone_skill       import PhoneSkill
from skills.time_skill        import TimeSkill
from skills.open_app_skill    import OpenAppSkill
from skills.note_skill        import NoteSkill
from skills.web_skill         import WebSkill
from skills.media_skill       import MediaSkill
from skills.history_skill     import HistorySkill
from skills.reminder_skill    import ReminderSkill
from skills.system_skill      import SystemSkill
from skills.file_reader_skill import FileReaderSkill
from skills.file_manager_skill import FileManagerSkill
from skills.project_skill     import ProjectSkill
from skills.code_editor_skill import CodeEditorSkill
from skills.gui_builder_skill import GuiBuilderSkill
from skills.rag_skill         import RAGSkill
from brain.custom_intents     import CustomIntents
from brain.finetune_helper    import FinetuneHelper
from skills.habits_skill      import HabitsSkill


class SkillRegistry:
    def __init__(self):
        file_manager   = FileManagerSkill()
        project_skill  = ProjectSkill()
        code_editor    = CodeEditorSkill()
        gui_builder    = GuiBuilderSkill()
        tv_skill       = TVSkill()
        phone_skill    = PhoneSkill()
        rag_skill      = RAGSkill()
        custom_intents = CustomIntents()
        finetune       = FinetuneHelper()
        habits_skill   = HabitsSkill()

        self.skills = {
            "get_time":         TimeSkill(),
            "system":           SystemSkill(),
            "media":            MediaSkill(),
            "history":          HistorySkill(),
            "reminder":         ReminderSkill(),
            "open_app":         OpenAppSkill(),
            "create_note":      NoteSkill(),
            "web":              WebSkill(),
            "file_reader":      FileReaderSkill(),
            "file_manager":     file_manager,
            "create_folder":    file_manager,
            "create_file":      file_manager,
            "open_folder":      file_manager,
            "project":          project_skill,
            "create_project":   project_skill,
            "code_editor":      code_editor,
            "file_editor":      code_editor,
            "edit_file":        code_editor,
            "edit_project":     code_editor,
            "search_file":      code_editor,
            "explain_file":     code_editor,
            "gui_builder":      gui_builder,
            "create_gui":       gui_builder,
            "create_interface": gui_builder,
            "interface":        gui_builder,
            "tv":               tv_skill,
            "phone":            phone_skill,
            "rag":              rag_skill,
            "custom_intent":    custom_intents,
            "finetune":         finetune,
            "habits":           habits_skill,
            "mis_habitos":      habits_skill,
            "analizar_habitos": habits_skill,
        }

    def execute(self, intent_data):
        intent = intent_data.get("intent")
        data   = intent_data.get("data", {})
        skill  = self.skills.get(intent)
        if skill:
            return skill.run(data)
        return "No entendí ese comando todavía."
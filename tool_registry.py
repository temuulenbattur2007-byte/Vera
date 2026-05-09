"""
tool_registry.py — Maps JSON command names to Python functions.
"""
from tools.volume      import volume_up, volume_down, volume_mute, volume_set
from tools.media       import media_play_pause, media_next, media_prev, media_stop, play_music
from tools.apps        import open_app, open_url, open_folder, search_web
from tools.system      import system_shutdown, system_restart, system_sleep, system_lock, system_cancel_shutdown
from tools.reminder    import set_reminder, list_reminders
from tools.web_search  import web_search as tavily_web_search
from tools.file_creator import (
    create_word, create_pdf, create_excel, create_powerpoint, open_output_folder
)
from tools.screenshot import take_screenshot, analyze_screenshot

TOOL_REGISTRY = {
    # ── Volume ────────────────────────────────────────────────────────────────
    "volume_up":              volume_up,
    "volume_down":            volume_down,
    "volume_mute":            volume_mute,
    "volume_set":             volume_set,

    # ── Media ─────────────────────────────────────────────────────────────────
    "media_play_pause":       media_play_pause,
    "media_next":             media_next,
    "media_prev":             media_prev,
    "media_stop":             media_stop,
    "play_music":             play_music,

    # ── Apps & System ─────────────────────────────────────────────────────────
    "open_app":               open_app,
    "open_url":               open_url,
    "open_folder":            open_folder,
    "search_web":             search_web,
    "system_shutdown":        system_shutdown,
    "system_restart":         system_restart,
    "system_sleep":           system_sleep,
    "system_lock":            system_lock,
    "system_cancel_shutdown": system_cancel_shutdown,

    # ── Reminders ─────────────────────────────────────────────────────────────
    "set_reminder":           set_reminder,
    "list_reminders":         list_reminders,

    # ── Web Search ────────────────────────────────────────────────────────────
    "web_search":             tavily_web_search,

    # ── File Creation ─────────────────────────────────────────────────────────
    "create_word":            create_word,
    "create_pdf":             create_pdf,
    "create_excel":           create_excel,
    "create_powerpoint":      create_powerpoint,
    "open_output_folder":     open_output_folder,

    # ── Vision ────────────────────────────────────────────────────────────────
    "take_screenshot":        take_screenshot,
    "analyze_screenshot":     analyze_screenshot,
}

DANGEROUS = {"system_shutdown", "system_restart"}

def execute(command, args):
    if not command or command.lower() == "null":
        return None
    if command not in TOOL_REGISTRY:
        return f"Unknown command: '{command}'"
    try:
        fn = TOOL_REGISTRY[command]
        return fn(**args) if args else fn()
    except TypeError as e:
        return f"Wrong args for '{command}': {e}"
    except Exception as e:
        return f"Error: {e}"

def list_tools():
    return list(TOOL_REGISTRY.keys())
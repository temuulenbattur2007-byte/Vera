"""
hotkey.py — Global hotkey listener for Vera.
Ctrl+Alt+Space toggles Vera's window from anywhere on your desktop.

This runs as a background thread inside gui.py — no separate process needed.
"""
import threading
import sys


def start_hotkey_listener(on_trigger, hotkey: str = "ctrl+alt+space"):
    """
    Start a background thread that listens for the global hotkey.

    Args:
        on_trigger: Callback function called when hotkey is pressed.
        hotkey: Key combo string (default: ctrl+alt+space).
    """
    def listen():
        try:
            import keyboard
            keyboard.add_hotkey(hotkey, on_trigger, suppress=False)
            keyboard.wait()  # Block this thread forever, listening for keys
        except ImportError:
            print("[Hotkey] 'keyboard' library not found.")
            print("[Hotkey] Install it with: pip install keyboard")
        except Exception as e:
            print(f"[Hotkey] Error: {e}")
            print("[Hotkey] Try running Vera as Administrator for global hotkeys.")

    t = threading.Thread(target=listen, daemon=True)
    t.start()
    return t


def stop_hotkey_listener():
    """Remove all hotkeys."""
    try:
        import keyboard
        keyboard.unhook_all_hotkeys()
    except Exception:
        pass
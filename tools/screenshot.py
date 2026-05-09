"""
tools/screenshot.py — Screenshot capture for Vera.

Two modes:
- take_screenshot(save=True)  → saves permanently, no analysis
- take_screenshot(save=False) → temp file, analyzed then deleted by gui.py
- analyze_screenshot()        → finds last saved screenshot, returns path for analysis then deletes it
"""

import os
import tempfile
from datetime import datetime
from pathlib import Path

SCREENSHOT_DIR = Path(os.path.expanduser("~")) / "Documents" / "Vera" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# Track the last saved screenshot path in memory
_last_saved: str = None


def take_screenshot(save: bool = True, **kwargs) -> str:
    """
    Take a screenshot.
    save=True  — save permanently, return path
    save=False — save to temp file for analysis, return path (gui.py deletes after)
    """
    global _last_saved
    try:
        import pyautogui
        screenshot = pyautogui.screenshot()
        if save:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = SCREENSHOT_DIR / f"screenshot_{timestamp}.png"
            screenshot.save(str(path))
            _last_saved = str(path)
            return str(path)
        else:
            tmp = tempfile.NamedTemporaryFile(
                suffix=".png", delete=False, dir=str(SCREENSHOT_DIR)
            )
            screenshot.save(tmp.name)
            tmp.close()
            return tmp.name
    except ImportError:
        return "error: Missing library. Run: pip install pyautogui pillow"
    except Exception as e:
        return f"error: {e}"


def analyze_screenshot(**kwargs) -> str:
    """
    Return the last saved screenshot path for vision analysis.
    Marks it for deletion after analysis (gui.py handles the delete).
    """
    global _last_saved
    if _last_saved and Path(_last_saved).exists():
        path = _last_saved
        _last_saved = None
        return path
    # Fallback — find the most recent screenshot in the folder
    screenshots = sorted(SCREENSHOT_DIR.glob("screenshot_*.png"))
    if screenshots:
        return str(screenshots[-1])
    return "error: No saved screenshot found. Say \'take screenshot\' first."


def get_last_saved():
    return _last_saved
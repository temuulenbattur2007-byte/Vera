"""
tools/reminder.py — Reminder system with background checking.
Reminders persist in a JSON file and fire as Windows toast notifications.
"""
import json
import os
import threading
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

REMINDERS_FILE = Path(__file__).parent.parent / "reminders.json"

def _load():
    if REMINDERS_FILE.exists():
        try:
            return json.loads(REMINDERS_FILE.read_text())
        except:
            pass
    return []

def _save(reminders):
    REMINDERS_FILE.write_text(json.dumps(reminders, indent=2))

def _parse_time(remind_at: str) -> str:
    """Convert relative time strings to ISO datetime."""
    remind_at = remind_at.strip().lower()
    now = datetime.now()

    mappings = {
        "minute": timedelta(minutes=1),
        "minutes": timedelta(minutes=1),
        "hour": timedelta(hours=1),
        "hours": timedelta(hours=1),
        "day": timedelta(days=1),
        "days": timedelta(days=1),
        "week": timedelta(weeks=1),
        "weeks": timedelta(weeks=1),
    }

    # Parse "X days/hours/minutes"
    parts = remind_at.split()
    for i, part in enumerate(parts):
        for key, delta in mappings.items():
            if part.startswith(key):
                try:
                    n = int(parts[i-1]) if i > 0 else 1
                    return (now + delta * n).isoformat()
                except:
                    pass

    # Try parsing as direct datetime
    try:
        return datetime.fromisoformat(remind_at).isoformat()
    except:
        # Default: 1 hour from now
        return (now + timedelta(hours=1)).isoformat()


def set_reminder(title: str = None, message: str = None, remind_at: str = None, **kwargs) -> str:
    """Set a reminder that fires at a specific time."""
    title     = title or kwargs.get("name", "Reminder")
    message   = message or kwargs.get("text", title)
    remind_at = remind_at or kwargs.get("time", "1 hour")

    fire_at = _parse_time(remind_at)
    reminders = _load()
    reminders.append({
        "id": len(reminders) + 1,
        "title": title,
        "message": message,
        "fire_at": fire_at,
        "fired": False,
    })
    _save(reminders)

    fire_dt = datetime.fromisoformat(fire_at)
    return f"Reminder set: '{title}' at {fire_dt.strftime('%B %d, %Y %I:%M %p')}"


def list_reminders() -> str:
    """List all pending reminders."""
    reminders = [r for r in _load() if not r["fired"]]
    if not reminders:
        return "No pending reminders."
    lines = []
    for r in reminders:
        dt = datetime.fromisoformat(r["fire_at"])
        lines.append(f"• {r['title']} — {dt.strftime('%b %d %I:%M %p')}")
    return "\n".join(lines)


def _toast(title, message):
    """Show a Windows toast notification."""
    try:
        script = f'''
Add-Type -AssemblyName System.Windows.Forms
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.Visible = $true
$notify.ShowBalloonTip(8000, "{title}", "{message}", [System.Windows.Forms.ToolTipIcon]::None)
Start-Sleep -Seconds 9
$notify.Dispose()
'''
        subprocess.Popen(['powershell', '-WindowStyle', 'Hidden', '-Command', script])
    except Exception as e:
        print(f"[Vera] Toast error: {e}")


def check_reminders(on_fire=None):
    """
    Check for due reminders. Call this in a background loop.
    on_fire: callback(title, message) when a reminder fires.
    """
    reminders = _load()
    changed = False
    now = datetime.now()

    for r in reminders:
        if r["fired"]:
            continue
        try:
            fire_at = datetime.fromisoformat(r["fire_at"])
            if now >= fire_at:
                r["fired"] = True
                changed = True
                _toast(r["title"], r["message"])
                if on_fire:
                    on_fire(r["title"], r["message"])
        except:
            pass

    if changed:
        _save(reminders)


def start_reminder_loop(on_fire=None, interval=30):
    """Start background thread that checks reminders every N seconds."""
    def loop():
        while True:
            try:
                check_reminders(on_fire)
            except:
                pass
            threading.Event().wait(interval)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t

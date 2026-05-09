"""
tools/system.py — Windows system controls: shutdown, restart, sleep, lock.
"""

import os
import subprocess


def system_shutdown(delay_seconds: int = 5) -> str:
    """Shutdown the computer after a delay."""
    os.system(f"shutdown /s /t {delay_seconds}")
    return f"Shutting down in {delay_seconds} seconds. You can cancel with: shutdown /a"


def system_restart(delay_seconds: int = 5) -> str:
    """Restart the computer after a delay."""
    os.system(f"shutdown /r /t {delay_seconds}")
    return f"Restarting in {delay_seconds} seconds. You can cancel with: shutdown /a"


def system_sleep() -> str:
    """Put the computer to sleep."""
    os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
    return "Going to sleep..."


def system_lock() -> str:
    """Lock the workstation."""
    os.system("rundll32.exe user32.dll,LockWorkStation")
    return "Locked the screen."


def system_cancel_shutdown() -> str:
    """Cancel a pending shutdown or restart."""
    os.system("shutdown /a")
    return "Shutdown cancelled."

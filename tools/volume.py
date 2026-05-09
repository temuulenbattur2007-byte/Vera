"""
tools/volume.py — Windows volume control via pycaw with flexible args.
"""
from __future__ import annotations

def _get_vol():
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return interface.QueryInterface(IAudioEndpointVolume)
    except:
        return None

def volume_up(steps: int = 1, amount: int = None, by: int = None, percent: int = None, value: int = None, **kwargs) -> str:
    n = steps or amount or by or percent or value or 1
    try: n = int(n)
    except: n = 1
    vol = _get_vol()
    if vol:
        current = vol.GetMasterVolumeLevelScalar()
        new_vol = min(1.0, current + n * 0.10)
        vol.SetMasterVolumeLevelScalar(new_vol, None)
        return f"Volume: {int(new_vol * 100)}%"
    else:
        import pyautogui
        for _ in range(n): pyautogui.press("volumeup")
        return f"Volume increased by {n} step(s)"

def volume_down(steps: int = 1, amount: int = None, by: int = None, percent: int = None, value: int = None, **kwargs) -> str:
    n = steps or amount or by or percent or value or 1
    try: n = int(n)
    except: n = 1
    vol = _get_vol()
    if vol:
        current = vol.GetMasterVolumeLevelScalar()
        new_vol = max(0.0, current - n * 0.10)
        vol.SetMasterVolumeLevelScalar(new_vol, None)
        return f"Volume: {int(new_vol * 100)}%"
    else:
        import pyautogui
        for _ in range(n): pyautogui.press("volumedown")
        return f"Volume decreased by {n} step(s)"

def volume_mute(**kwargs) -> str:
    vol = _get_vol()
    if vol:
        current_mute = vol.GetMute()
        vol.SetMute(not current_mute, None)
        return "Muted" if not current_mute else "Unmuted"
    else:
        import pyautogui
        pyautogui.press("volumemute")
        return "Toggled mute"

def volume_set(percent: int = 50, level: int = None, value: int = None, amount: int = None, **kwargs) -> str:
    p = percent or level or value or amount or 50
    try: p = int(p)
    except: p = 50
    p = max(0, min(100, p))
    vol = _get_vol()
    if vol:
        vol.SetMasterVolumeLevelScalar(p / 100.0, None)
        return f"Volume set to {p}%"
    return "pycaw not available"
"""
tools/media.py — Media control using Windows media keys and VLC/Spotify.
"""
import os
import random
import subprocess
import pyautogui
from pathlib import Path


def media_play_pause(**kwargs) -> str:
    pyautogui.press("playpause")
    return "Toggled play/pause"

def media_next(**kwargs) -> str:
    pyautogui.press("nexttrack")
    return "Next track"

def media_prev(**kwargs) -> str:
    pyautogui.press("prevtrack")
    return "Previous track"

def media_stop(**kwargs) -> str:
    pyautogui.press("stop")
    return "Stopped"

def play_music(folder: str = None, path: str = None, song: str = None,
               file: str = None, query: str = None, **kwargs) -> str:
    """Play music — uses VLC if available, otherwise opens with default player."""
    target = folder or path or song or file or query

    music_dirs = [
        Path.home() / "Music",
        Path(f"C:/Users/{os.environ.get('USERNAME', 'TEK')}/Music"),
        Path.home() / "Downloads" / "Music",
        Path.home() / "Desktop" / "Music",
    ]

    extensions = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma"}

    # Search for specific song
    if target and target.lower() not in ["music", "songs", "playlist", "something", "any", ""]:
        for music_dir in music_dirs:
            if not music_dir.exists():
                continue
            for ext in extensions:
                matches = list(music_dir.rglob(f"*{target}*{ext}"))
                if matches:
                    return _play_file(str(matches[0]))

    # Pick random song from music folder
    all_songs = []
    for music_dir in music_dirs:
        if music_dir.exists():
            for ext in extensions:
                all_songs.extend(music_dir.rglob(f"*{ext}"))

    if all_songs:
        song_to_play = random.choice(all_songs)
        return _play_file(str(song_to_play))

    # Fallback — try Spotify then YouTube Music
    try:
        import AppOpener
        AppOpener.open("spotify", match_closest=False, output=False)
        return "Opened Spotify"
    except:
        import webbrowser
        webbrowser.open("https://music.youtube.com")
        return "Opened YouTube Music"


def _play_file(file_path: str) -> str:
    """Play a file using VLC if available, otherwise default player."""
    name = Path(file_path).name

    # Try VLC first — it supports media keys properly
    vlc_paths = [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ]
    for vlc in vlc_paths:
        if Path(vlc).exists():
            subprocess.Popen([vlc, file_path])
            return f"Playing: {name}"

    # Try Windows Media Player
    wmp = r"C:\Program Files\Windows Media Player\wmplayer.exe"
    if Path(wmp).exists():
        subprocess.Popen([wmp, file_path])
        return f"Playing: {name}"

    # Default file association
    os.startfile(file_path)
    return f"Playing: {name}"
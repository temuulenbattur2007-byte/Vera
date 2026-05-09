"""
tools/apps.py — Open applications, URLs, and folders.
"""
import os
import json
import webbrowser
import subprocess
from pathlib import Path


def open_app(name: str = None, app: str = None, application: str = None, **kwargs) -> str:
    name = name or app or application or next(iter(kwargs.values()), None)
    if not name:
        return "No app name provided"

    # Method 1: Windows Start Menu search (most accurate)
    try:
        result = subprocess.run(
            ['powershell', '-Command',
             f'Get-StartApps | Where-Object {{$_.Name -like "*{name}*"}} | Select-Object -First 1 | ConvertTo-Json'],
            capture_output=True, text=True, timeout=8
        )
        output = result.stdout.strip()
        if output:
            app_data = json.loads(output)
            app_id = app_data.get("AppID", "")
            if "://" in app_id:
                # URL-based app like Google Play Games
                subprocess.Popen(['start', '', app_id], shell=True)
            else:
                subprocess.Popen(['explorer', f'shell:appsFolder\\{app_id}'])
            return f"Opened {name}"
    except Exception:
        pass

    # Method 2: Search Desktop\Programs and Start Menu shortcuts
    try:
        start_dirs = [
            Path.home() / "Desktop/Programs",
            Path.home() / "Desktop",
            Path(os.environ.get("APPDATA","")) / "Microsoft/Windows/Start Menu/Programs",
            Path("C:/ProgramData/Microsoft/Windows/Start Menu/Programs"),
        ]
        name_lower = name.lower()
        for base in start_dirs:
            if not base.exists():
                continue
            for lnk in base.rglob("*.lnk"):
                if name_lower in lnk.stem.lower():
                    os.startfile(str(lnk))
                    return f"Opened {lnk.stem}"
            for url_file in base.rglob("*.url"):
                if name_lower in url_file.stem.lower():
                    os.startfile(str(url_file))
                    return f"Opened {url_file.stem}"
    except Exception:
        pass

    # Method 3: Search Program Files for .exe
    try:
        prog_dirs = [
            Path(os.environ.get("PROGRAMFILES","C:/Program Files")),
            Path(os.environ.get("PROGRAMFILES(X86)","C:/Program Files (x86)")),
            Path(os.environ.get("LOCALAPPDATA","")) / "Programs",
        ]
        name_lower = name.lower()
        for base in prog_dirs:
            if not base.exists():
                continue
            for exe in base.rglob("*.exe"):
                if name_lower in exe.stem.lower() and "uninstall" not in exe.stem.lower():
                    subprocess.Popen([str(exe)])
                    return f"Opened {exe.name}"
    except Exception:
        pass

    # Method 4: direct shell launch
    try:
        subprocess.Popen(name, shell=True)
        return f"Tried to launch {name}"
    except Exception:
        return f"Couldn't find {name} — is it installed?"


def open_url(url: str = None, link: str = None, website: str = None, **kwargs) -> str:
    url = url or link or website or next(iter(kwargs.values()), None)
    if not url:
        return "No URL provided"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url}"


def search_web(query: str = None, search: str = None, term: str = None, **kwargs) -> str:
    query = query or search or term or next(iter(kwargs.values()), None)
    if not query:
        return "No search query"
    import urllib.parse
    webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}")
    return f"Searching: {query}"


def open_folder(path: str = None, folder: str = None, directory: str = None, **kwargs) -> str:
    path = path or folder or directory or next(iter(kwargs.values()), None)
    if not path:
        return "No folder provided"
    user = os.environ.get("USERNAME", "TEK")
    shortcuts = {
        "downloads": f"C:\\Users\\{user}\\Downloads",
        "documents": f"C:\\Users\\{user}\\Documents",
        "desktop":   f"C:\\Users\\{user}\\Desktop",
        "pictures":  f"C:\\Users\\{user}\\Pictures",
        "music":     f"C:\\Users\\{user}\\Music",
        "videos":    f"C:\\Users\\{user}\\Videos",
        "home":      f"C:\\Users\\{user}",
}
    resolved = shortcuts.get(path.lower().strip(), path)
    if not os.path.exists(resolved):
        return f"Folder not found: {resolved}"
    os.startfile(resolved)
    return f"Opened: {resolved}"
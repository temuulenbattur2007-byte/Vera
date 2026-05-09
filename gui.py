"""
gui.py — Vera AI Companion — Full GUI
Features: Voice, Web Search, System Tray, Reminders, Editable input
Run: python gui.py
"""
import sys, os, json, threading, math, time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from tkinter import font as tkfont

from persona import SYSTEM_PROMPT, DAILY_SUMMARY_PROMPT
from config import VERA_NAME, USER_NAME
import model_loader
from tool_registry import execute, DANGEROUS
from memory.short_term import ShortTermMemory
from memory.daily_log import append_messages, save_summary, format_summaries_for_prompt, list_logged_days, load_date
from memory.startup import build_startup_context, get_opening_line
from memory.vector_store import format_memories_for_prompt, store_facts_from_summary, memory_count, store_memory
from tools.reminder import start_reminder_loop, list_reminders
from hotkey import start_hotkey_listener, stop_hotkey_listener
from tools.tts import speak, set_enabled as tts_set_enabled, is_enabled as tts_is_enabled
from tools.voice_pipeline import start_pipeline, stop_pipeline, is_running as voice_is_running
from memory.rag import index_directory, search_documents, format_for_context, list_indexed_files, document_count, index_file, DOCS_DIR

# ── Colors ────────────────────────────────────────────────────────────────────
BG         = "#0c0a0e"
BG_PANEL   = "#110f14"
BG_INPUT   = "#1a1520"
BG_USER    = "#1e1830"
GARNET     = "#8b1a2e"
GARNET_LT  = "#c42847"
GARNET_DIM = "#5a0f1d"
ROSE       = "#e8607a"
ROSE_LT    = "#f0909f"
WHITE      = "#f0eaf4"
MUTED      = "#6b5f75"
DIM        = "#3d3545"
GREEN      = "#6bcfa0"
RED        = "#ff5566"
AMBER      = "#f0a060"
BORDER     = "#221a2c"
BLUE       = "#6090e0"

short_term = ShortTermMemory(max_messages=40)

_startup_context = None


# ── Windows Startup Registration ──────────────────────────────────────────────
def _get_startup_folder() -> str:
    """Returns the Windows user startup folder path."""
    return os.path.join(
        os.environ.get("APPDATA", ""),
        r"Microsoft\Windows\Start Menu\Programs\Startup"
    )

def _get_shortcut_path() -> str:
    return os.path.join(_get_startup_folder(), f"{VERA_NAME}.bat")

def register_startup():
    """
    Register Vera as a Windows Task Scheduler task.
    Runs at login with highest privileges — no UAC popup ever.
    Safe to call multiple times.
    """
    try:
        vera_dir = os.path.dirname(os.path.abspath(__file__))
        pythonw  = os.path.join(vera_dir, "venv", "Scripts", "pythonw.exe")
        script   = os.path.join(vera_dir, "gui.py")

        if not os.path.exists(pythonw):
            print("[Startup] pythonw.exe not found in venv.")
            return

        # Use schtasks to create a task that runs at login, highest privileges, no popup
        cmd = (
            f'schtasks /Create /F /TN "Vera AI" ' +
            f'/TR "\"{pythonw}\" \"{script}\"" ' +
            f'/SC ONLOGON /RL HIGHEST /DELAY 0000:10'
        )
        result = os.system(cmd)
        if result == 0:
            print("[Startup] Vera registered via Task Scheduler — no UAC popup on boot.")
            # Clean up old startup folder .bat if it exists
            old_shortcut = _get_shortcut_path()
            if os.path.exists(old_shortcut):
                os.remove(old_shortcut)
            # Clean up old vbs if it exists
            old_vbs = os.path.join(vera_dir, "vera_launcher.vbs")
            if os.path.exists(old_vbs):
                os.remove(old_vbs)
        else:
            print("[Startup] Task Scheduler registration failed.")
    except Exception as e:
        print(f"[Startup] Could not register startup: {e}")


def unregister_startup():
    """Remove Vera from Task Scheduler."""
    try:
        result = os.system('schtasks /Delete /F /TN "Vera AI"')
        if result == 0:
            print("[Startup] Vera removed from Task Scheduler.")
        else:
            print("[Startup] Vera was not in Task Scheduler.")
        # Also clean up leftover files
        shortcut = _get_shortcut_path()
        if os.path.exists(shortcut):
            os.remove(shortcut)
        vera_dir = os.path.dirname(os.path.abspath(__file__))
        old_vbs  = os.path.join(vera_dir, "vera_launcher.vbs")
        if os.path.exists(old_vbs):
            os.remove(old_vbs)
    except Exception as e:
        print(f"[Startup] Error removing startup: {e}")


def is_startup_registered() -> bool:
    """Check if Vera task exists in Task Scheduler."""
    result = os.system('schtasks /Query /TN "Vera AI" >nul 2>&1')
    return result == 0

def get_startup_context():
    global _startup_context
    if _startup_context is None:
        _startup_context = build_startup_context()
    return _startup_context

def build_system_prompt(query=""):
    base = SYSTEM_PROMPT
    past = format_summaries_for_prompt(days=7)
    lt   = format_memories_for_prompt(query, n_results=4) if query else ""
    extras = "\n\n".join(filter(None, [past, lt]))
    return base + (f"\n\n---\n{extras}" if extras else "")

def parse_response(raw):
    if not isinstance(raw, str):
        return {"speech": str(raw), "command": None, "args": {}}
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result
    except:
        pass
    import re
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if m:
        try:
            result = json.loads(m.group())
            if isinstance(result, dict):
                return result
        except:
            pass
    return {"speech": raw, "command": None, "args": {}}

def _normalize_response(obj: dict) -> dict:
    """Normalize args — convert list content to string."""
    args = obj.get("args", {}) or {}
    if "content" in args and isinstance(args["content"], list):
        args["content"] = "\n".join(str(x) for x in args["content"])
    obj["args"] = args
    obj.setdefault("command", None)
    obj.setdefault("speech", "")
    return obj


def extract_file_command(raw: str):
    """
    Fallback: scan raw model output for a create_* command and its args.
    Used when the model splits JSON across multiple objects.
    Returns {"command": ..., "args": ...} or None.
    """
    import re

    cmd_match = re.search(r'"command"\s*:\s*"(create_\w+)"', raw)
    if not cmd_match:
        return None
    command = cmd_match.group(1)

    args_match = re.search(r'"args"\s*:\s*(\{.*?\})', raw, re.DOTALL)
    if not args_match:
        return None

    try:
        args_str = args_match.group(1)

        # Convert list content to joined string
        def fix_list(m):
            items = re.findall(r'"([^"]+)"', m.group(1))
            return '"content": "' + "\\n".join(items) + '"'

        args_str = re.sub(r'"content"\s*:\s*\[(.*?)\]', fix_list, args_str, flags=re.DOTALL)
        args = json.loads(args_str)
        return {"command": command, "args": args}
    except:
        return None


def end_session(on_done=None):
    msgs = [{"role": m.role, "content": m.content, "timestamp": m.timestamp}
            for m in short_term.get_raw() if m.role != "system"]
    if msgs: append_messages(msgs)
    try:
        r = model_loader.chat([
            {"role":"system","content":"Output only JSON."},
            {"role":"user","content":f"{json.dumps(msgs)}\n\n{DAILY_SUMMARY_PROMPT}"}
        ], max_tokens=300, temperature=0.3)
        r = r.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        s = json.loads(r)
        save_summary(s)
        store_facts_from_summary(s, datetime.now().strftime("%Y-%m-%d"))
    except: pass
    if on_done: on_done()


class Avatar(tk.Canvas):
    def __init__(self, parent, size=130):
        super().__init__(parent, width=size, height=size,
                        bg=BG_PANEL, highlightthickness=0)
        self.size = size
        self.cx = self.cy = size // 2
        self.mode = "offline"
        self._t = 0
        self._loop()

    def set_mode(self, m): self.mode = m

    def _loop(self):
        self._t += 1
        self.delete("all")
        t, cx, cy, s = self._t, self.cx, self.cy, self.size
        if self.mode == "offline":
            self.create_oval(cx-30,cy-30,cx+30,cy+30,fill=DIM,outline=MUTED,width=1)
            self.create_text(cx,cy,text="V",fill=MUTED,font=("Segoe UI",16,"bold"))
        else:
            spd = {"idle":0.04,"thinking":0.18,"speaking":0.10,"listening":0.08}.get(self.mode,0.04)
            amp = {"idle":0.05,"thinking":0.12,"speaking":0.08,"listening":0.06}.get(self.mode,0.05)
            pulse = math.sin(t*spd)*amp + 1.0
            color = BLUE if self.mode == "listening" else GARNET_LT
            for r_frac in [0.46,0.40,0.34]:
                r = s*r_frac*pulse
                self.create_oval(cx-r,cy-r,cx+r,cy+r,outline=color,width=1)
            rc = s*0.27*pulse
            fill_color = "#1a2a4a" if self.mode == "listening" else GARNET_DIM
            self.create_oval(cx-rc,cy-rc,cx+rc,cy+rc,fill=fill_color,outline=color,width=2)
            ri = rc*0.42*(math.sin(t*0.07+1.2)*0.3+0.7)
            ox,oy = cx-rc*0.18, cy-rc*0.18
            dot_color = BLUE if self.mode == "listening" else ROSE
            self.create_oval(ox-ri,oy-ri,ox+ri,oy+ri,fill=dot_color,outline="")
            if self.mode == "thinking":
                for i,col in enumerate([ROSE_LT,GARNET_LT]):
                    a = t*0.12+i*math.pi
                    px,py = cx+math.cos(a)*rc*0.85, cy+math.sin(a)*rc*0.85
                    r2=4-i
                    self.create_oval(px-r2,py-r2,px+r2,py+r2,fill=col,outline="")
            if self.mode == "speaking":
                for i in range(5):
                    h=(math.sin(t*0.15+i*0.8)*0.5+0.5)*16+5
                    x=cx-18+i*9; y=cy+rc+8
                    self.create_rectangle(x,y,x+4,y+h,fill=ROSE,outline="")
            if self.mode == "listening":
                for i in range(3):
                    h=(math.sin(t*0.20+i*1.2)*0.5+0.5)*12+4
                    x=cx-8+i*8; y=cy+rc+8
                    self.create_rectangle(x,y,x+4,y+h,fill=BLUE,outline="")
        self.after(40, self._loop)


class VeraApp:
    def __init__(self, root):
        self.root = root
        self.root.title(VERA_NAME)
        self.root.geometry("960x700")
        self.root.configure(bg=BG)
        self.root.minsize(700,500)
        self.ready = False
        self.busy  = False
        self.listening = False
        self.tray_icon = None
        self.pending_image = None
        self._msg_count = 0
        self._voice_active = False
        self._voice_pipeline_started = False
        self._is_hidden = False  # Track visibility manually — more reliable than winfo_viewable
        self._text_model_on = False   # Text model state
        self._vl_model_on   = False   # Vision model state
        self._text_loading  = False
        self._vl_loading    = False

        f = lambda **kw: tkfont.Font(**kw)
        self.F = {
            "chat":  f(family="Segoe UI", size=11),
            "bold":  f(family="Segoe UI", size=11, weight="bold"),
            "small": f(family="Segoe UI", size=9),
            "title": f(family="Segoe UI", size=15, weight="bold"),
            "mono":  f(family="Consolas",  size=10),
            "tiny":  f(family="Segoe UI", size=8),
        }

        self._build()
        short_term.add("system", build_system_prompt())
        # Few-shot examples — Vera's actual voice
        short_term.add("user", "hi")
        short_term.add("assistant", '{"speech": "Yeah yeah, I\'m here. What\'s going on?", "command": null, "args": {}}')
        short_term.add("user", "what is your name")
        short_term.add("assistant", '{"speech": "Vera. You already know that.", "command": null, "args": {}}')
        short_term.add("user", "how are you")
        short_term.add("assistant", '{"speech": "Fine. You look like you have something on your mind though.", "command": null, "args": {}}')
        short_term.add("user", "I got silver in the competition")
        short_term.add("assistant", '{"speech": "Silver? ...okay fine, that\'s not bad. But you could\'ve gone for gold, right?", "command": null, "args": {}}')
        short_term.add("user", "I\'m stressed")
        short_term.add("assistant", '{"speech": "Hey. You good? And don\'t say fine.", "command": null, "args": {}}')
        self._load_model()
        start_reminder_loop(on_fire=self._on_reminder)
        self._setup_tray()
        self._preload_vl()
        self.root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        start_hotkey_listener(self._toggle_window, hotkey="ctrl+alt+space")
        register_startup()  # Register to start on boot (runs silently)

    # ── UI Builder ────────────────────────────────────────────────────────────
    def _build(self):
        # Header
        hdr = tk.Frame(self.root, bg=BG_PANEL, height=48)
        hdr.pack(fill=tk.X, side=tk.TOP)
        hdr.pack_propagate(False)
        tk.Label(hdr, text=VERA_NAME, font=self.F["title"], bg=BG_PANEL, fg=ROSE).pack(side=tk.LEFT, padx=16)
        self.dot = tk.Canvas(hdr, width=10, height=10, bg=BG_PANEL, highlightthickness=0)
        self.dot.pack(side=tk.LEFT)
        self.dot.create_oval(1,1,9,9,fill=MUTED,outline="")
        self.st_lbl = tk.Label(hdr, text="Loading...", font=self.F["small"], bg=BG_PANEL, fg=MUTED)
        self.st_lbl.pack(side=tk.LEFT, padx=6)
        self.mem_lbl = tk.Label(hdr, text="", font=self.F["small"], bg=BG_PANEL, fg=MUTED)
        self.mem_lbl.pack(side=tk.RIGHT, padx=16)
        self.always_listen_btn = tk.Button(hdr, text="👂 OFF", font=self.F["small"],
            bg=BG_USER, fg=MUTED, activebackground=GARNET_DIM, activeforeground=ROSE,
            relief=tk.FLAT, padx=8, cursor="hand2", command=self._toggle_always_listen)
        self.always_listen_btn.pack(side=tk.RIGHT, padx=4)
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X, side=tk.TOP)

        # Input bottom
        bot = tk.Frame(self.root, bg=BG_INPUT)
        bot.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Frame(bot, bg=BORDER, height=1).pack(fill=tk.X)
        tk.Label(bot, text="Enter → send   Shift+Enter → new line   /help → commands",
                font=self.F["tiny"], bg=BG_INPUT, fg=MUTED).pack(pady=(5,2))
        row = tk.Frame(bot, bg=BG_INPUT)
        row.pack(fill=tk.X, padx=12, pady=(0,10))

        self.img_btn = tk.Button(row, text="🖼", font=self.F["bold"],
                                   bg=BG_USER, fg=MUTED, activebackground=GARNET_DIM,
                                   activeforeground=ROSE, relief=tk.FLAT, width=3,
                                   cursor="hand2", command=self._pick_image)
        self.img_btn.pack(side=tk.LEFT, padx=(0,4), fill=tk.Y)

        self.voice_btn = tk.Button(row, text="🎤", font=self.F["bold"],
                                   bg=BG_USER, fg=MUTED, activebackground=GARNET_DIM,
                                   activeforeground=ROSE, relief=tk.FLAT, width=3,
                                   cursor="hand2", command=self._toggle_voice)
        self.voice_btn.pack(side=tk.LEFT, padx=(0,6), fill=tk.Y)

        self.inp = tk.Text(row, height=3, bg=BG_USER, fg=WHITE,
                          font=self.F["chat"], relief=tk.FLAT, wrap=tk.WORD,
                          insertbackground=ROSE, selectbackground=GARNET_DIM,
                          padx=12, pady=8, undo=True)
        self.inp.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.inp.bind("<Return>", self._enter)
        self.inp.bind("<Control-z>", lambda e: self.inp.edit_undo())
        self.inp.bind("<Control-y>", lambda e: self.inp.edit_redo())
        self.inp.focus_set()

        self.tts_btn = tk.Button(row, text="🔊", font=self.F["bold"],
                                  bg=GARNET_DIM, fg=ROSE, activebackground=GARNET,
                                  activeforeground=WHITE, relief=tk.FLAT, width=3,
                                  cursor="hand2", command=self._toggle_tts)
        self.tts_btn.pack(side=tk.RIGHT, padx=(4,0), fill=tk.Y)

        self.send_btn = tk.Button(row, text="↑",
                                 font=tkfont.Font(family="Segoe UI",size=16,weight="bold"),
                                 bg=GARNET, fg=WHITE, activebackground=GARNET_LT,
                                 activeforeground=WHITE, relief=tk.FLAT,
                                 width=3, cursor="hand2", command=self._send)
        self.send_btn.pack(side=tk.RIGHT, padx=(6,0), fill=tk.Y)

        # Middle
        mid = tk.Frame(self.root, bg=BG)
        mid.pack(fill=tk.BOTH, expand=True)

        # Right panel
        rp = tk.Frame(mid, bg=BG_PANEL, width=220)
        rp.pack(side=tk.RIGHT, fill=tk.Y)
        rp.pack_propagate(False)
        tk.Frame(mid, bg=BORDER, width=1).pack(side=tk.RIGHT, fill=tk.Y)

        # Chat
        cf = tk.Frame(mid, bg=BG)
        cf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.chat = tk.Text(cf, bg=BG, fg=WHITE, font=self.F["chat"], wrap=tk.WORD,
                           state=tk.DISABLED, relief=tk.FLAT, padx=20, pady=16,
                           spacing1=2, spacing3=6, cursor="arrow",
                           selectbackground=GARNET_DIM)
        sb = tk.Scrollbar(cf, command=self.chat.yview, bg=BG_PANEL,
                         troughcolor=BG, activebackground=GARNET_DIM, width=5, relief=tk.FLAT)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.chat.configure(yscrollcommand=sb.set)

        self.chat.tag_config("vn",    foreground=ROSE,      font=self.F["small"])
        self.chat.tag_config("vm",    foreground="#e8daf0",  font=self.F["chat"])
        self.chat.tag_config("un",    foreground=MUTED,      font=self.F["small"])
        self.chat.tag_config("um",    foreground=WHITE,      font=self.F["chat"])
        self.chat.tag_config("cmd",   foreground=GREEN,      font=self.F["mono"])
        self.chat.tag_config("sys",   foreground=MUTED,      font=self.F["small"])
        self.chat.tag_config("err",   foreground=RED,        font=self.F["small"])
        self.chat.tag_config("thk",   foreground=GARNET_LT,  font=self.F["small"])
        self.chat.tag_config("notif", foreground=AMBER,      font=self.F["small"])
        self.chat.tag_config("wsrch", foreground=BLUE,       font=self.F["small"])

        self._build_right(rp)

    def _build_right(self, p):
        tk.Frame(p, bg=BG_PANEL, height=16).pack()
        self.avatar = Avatar(p, size=130)
        self.avatar.pack(anchor="center")
        tk.Label(p, text=VERA_NAME, font=self.F["title"], bg=BG_PANEL, fg=ROSE).pack(pady=(8,2))
        self.av_st = tk.Label(p, text="Offline", font=self.F["small"], bg=BG_PANEL, fg=MUTED)
        self.av_st.pack()
        tk.Frame(p, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=10)

        sf = tk.Frame(p, bg=BG_PANEL); sf.pack(fill=tk.X, padx=16)
        self.sm   = self._srow(sf, "Memories",   "—")
        self.sd   = self._srow(sf, "Days logged", "—")
        self.sr   = self._srow(sf, "Reminders",  "0")
        self.sdoc = self._srow(sf, "Documents",  "0")
        self._srow(sf, "Device", "RTX 3070")

        tk.Frame(p, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=10)

        # ── Model Switches ────────────────────────────────────────────────────
        mf = tk.Frame(p, bg=BG_PANEL); mf.pack(fill=tk.X, padx=16, pady=4)
        tk.Label(mf, text="Models", font=self.F["small"], bg=BG_PANEL, fg=MUTED).pack(anchor="w")

        # Text model row
        tr = tk.Frame(mf, bg=BG_PANEL); tr.pack(fill=tk.X, pady=3)
        tk.Label(tr, text="🧠 Text", font=self.F["small"], bg=BG_PANEL, fg=WHITE).pack(side=tk.LEFT)
        self.text_status = tk.Label(tr, text="OFF", font=self.F["tiny"], bg=BG_PANEL, fg=MUTED)
        self.text_status.pack(side=tk.RIGHT, padx=4)
        self.text_switch = tk.Button(tr, text="○", font=self.F["bold"],
            bg=BG_USER, fg=MUTED, activebackground=GARNET_DIM, activeforeground=ROSE,
            relief=tk.FLAT, width=3, cursor="hand2",
            command=self._toggle_text_model)
        self.text_switch.pack(side=tk.RIGHT)

        # VL model row
        vr = tk.Frame(mf, bg=BG_PANEL); vr.pack(fill=tk.X, pady=3)
        tk.Label(vr, text="👁 Vision", font=self.F["small"], bg=BG_PANEL, fg=WHITE).pack(side=tk.LEFT)
        self.vl_status = tk.Label(vr, text="OFF", font=self.F["tiny"], bg=BG_PANEL, fg=MUTED)
        self.vl_status.pack(side=tk.RIGHT, padx=4)
        self.vl_switch = tk.Button(vr, text="○", font=self.F["bold"],
            bg=BG_USER, fg=MUTED, activebackground=GARNET_DIM, activeforeground=ROSE,
            relief=tk.FLAT, width=3, cursor="hand2",
            command=self._toggle_vl_model)
        self.vl_switch.pack(side=tk.RIGHT)

        tk.Frame(p, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=10)

        af = tk.Frame(p, bg=BG_PANEL); af.pack(fill=tk.X, padx=12)
        buttons = [
            ("💾 Memory",    "/memory"),
            ("📅 Days",      "/days"),
            ("⏰ Reminders", "/reminders"),
            ("🔍 Web search", "/websearch"),
            ("❓ Help",      "/help"),
        ]
        for lbl, cmd in buttons:
            tk.Button(af, text=lbl, font=self.F["small"], bg="#1e1428", fg=MUTED,
                     activebackground=GARNET_DIM, activeforeground=ROSE,
                     relief=tk.FLAT, cursor="hand2", pady=5,
                     command=lambda c=cmd: self._cmd(c)).pack(fill=tk.X, pady=2)

    def _srow(self, p, label, val):
        r = tk.Frame(p, bg=BG_PANEL); r.pack(fill=tk.X, pady=3)
        tk.Label(r, text=label, font=self.F["small"], bg=BG_PANEL, fg=MUTED).pack(side=tk.LEFT)
        v = tk.Label(r, text=val, font=self.F["small"], bg=BG_PANEL, fg=WHITE)
        v.pack(side=tk.RIGHT)
        return v

    # ── Model ─────────────────────────────────────────────────────────────────
    # ── Model Toggle Methods ──────────────────────────────────────────────────
    def _toggle_text_model(self):
        if self._text_loading:
            return
        if self._text_model_on:
            # Turn OFF — unload model
            self._text_model_on = False
            self.ready = False
            try:
                import model_loader
                model_loader._model = None
                import gc, torch
                gc.collect()
                torch.cuda.empty_cache()
            except:
                pass
            self.text_switch.configure(text="○", bg=BG_USER, fg=MUTED)
            self.text_status.configure(text="OFF", fg=MUTED)
            self.avatar.set_mode("offline")
            self.av_st.configure(text="Text model OFF", fg=MUTED)
            self.dot.delete("all"); self.dot.create_oval(1,1,9,9,fill=MUTED,outline="")
            self.st_lbl.configure(text="Offline", fg=MUTED)
            self._log("sys", "Text model unloaded. Vera can't chat until you turn it back on.")
        else:
            # Turn ON — load model
            self._text_loading = True
            self.text_switch.configure(text="...", bg=GARNET_DIM, fg=AMBER)
            self.text_status.configure(text="Loading...", fg=AMBER)
            self._log("sys", "Loading text model...")
            def load():
                try:
                    import model_loader
                    model_loader.get_model()
                    self._text_model_on = True
                    self.ready = True
                    self.root.after(0, self._on_text_ready)
                except Exception as e:
                    self.root.after(0, lambda: self._log("err", f"Text model failed: {e}"))
                    self.root.after(0, lambda: self.text_switch.configure(text="○", bg=BG_USER, fg=MUTED))
                    self.root.after(0, lambda: self.text_status.configure(text="ERROR", fg=RED))
                finally:
                    self._text_loading = False
            threading.Thread(target=load, daemon=True).start()

    def _on_text_ready(self):
        self.text_switch.configure(text="●", bg=GARNET, fg=WHITE)
        self.text_status.configure(text="ON", fg=GREEN)
        self.avatar.set_mode("idle")
        self.av_st.configure(text="Online", fg=GREEN)
        self.dot.delete("all"); self.dot.create_oval(1,1,9,9,fill=GREEN,outline="")
        self.st_lbl.configure(text="Online  ·  GPU", fg=GREEN)
        self._log("sys", "Text model ready.")

    def _toggle_vl_model(self):
        if self._vl_loading:
            return
        if self._vl_model_on:
            # Turn OFF — unload vision model
            self._vl_model_on = False
            try:
                import model_loader_vl
                model_loader_vl._model     = None
                model_loader_vl._processor = None
                import gc, torch
                gc.collect()
                torch.cuda.empty_cache()
            except:
                pass
            self.vl_switch.configure(text="○", bg=BG_USER, fg=MUTED)
            self.vl_status.configure(text="OFF", fg=MUTED)
            if self._text_model_on:
                self.av_st.configure(text="Online (no vision)", fg=GREEN)
            self._log("sys", "Vision model unloaded. VRAM freed.")
        else:
            # Turn ON — load vision model
            self._vl_loading = True
            self.vl_switch.configure(text="...", bg=GARNET_DIM, fg=AMBER)
            self.vl_status.configure(text="Loading...", fg=AMBER)
            self._log("sys", "Loading vision model... (this takes a minute)")
            def load():
                try:
                    import model_loader_vl as vl
                    vl.get_model()
                    self._vl_model_on = True
                    self.root.after(0, self._on_vl_ready)
                except Exception as e:
                    self.root.after(0, lambda: self._log("err", f"Vision model failed: {e}"))
                    self.root.after(0, lambda: self.vl_switch.configure(text="○", bg=BG_USER, fg=MUTED))
                    self.root.after(0, lambda: self.vl_status.configure(text="ERROR", fg=RED))
                finally:
                    self._vl_loading = False
            threading.Thread(target=load, daemon=True).start()

    def _on_vl_ready(self):
        self.vl_switch.configure(text="●", bg=GARNET, fg=WHITE)
        self.vl_status.configure(text="ON", fg=GREEN)
        self.av_st.configure(text="Online + Vision ✓", fg=GREEN)
        self._log("sys", "Vision model ready.")

    def _autosave(self):
        """Save current session messages to daily log automatically."""
        try:
            raw_messages = short_term.get_raw()
            loggable = [
                {"role": m.role, "content": m.content, "timestamp": m.timestamp}
                for m in raw_messages
                if m.role != "system"
            ]
            if loggable:
                append_messages(loggable)
        except Exception as e:
            print(f"[Autosave] Error: {e}")

    def _index_docs(self):
        """Index documents folder in background on startup."""
        try:
            results = index_directory()
            count = document_count()
            self.root.after(0, lambda: self.sdoc.configure(text=str(count)))
            if results["indexed"]:
                msg = "Indexed: " + ", ".join(results["indexed"])
                self.root.after(0, lambda: self._log("sys", msg))
        except Exception as e:
            print(f"[RAG] Startup index error: {e}")

    def _preload_vl(self):
        """Warm up TTS only — vision model is controlled by the switch in UI."""
        def load():
            try:
                from tools.tts import _get_voice
                voice = _get_voice()
                if voice:
                    list(voice.synthesize_stream_raw("ready"))
            except Exception:
                pass
        threading.Thread(target=load, daemon=True).start()

    def _load_model(self):
        self._text_loading = True
        self.text_switch.configure(text="...", bg=GARNET_DIM, fg=AMBER)
        self.text_status.configure(text="Loading...", fg=AMBER)
        def go():
            try:
                model_loader.get_model()
                self._text_model_on = True
                self.ready = True
                self.root.after(0, self._on_ready)
            except Exception as e:
                self.root.after(0, lambda: self._log("err", str(e)))
            finally:
                self._text_loading = False
        threading.Thread(target=go, daemon=True).start()

    def _on_ready(self):
        self.avatar.set_mode("idle")
        self.av_st.configure(text="Online", fg=GREEN)
        self.dot.delete("all"); self.dot.create_oval(1,1,9,9,fill=GREEN,outline="")
        self.st_lbl.configure(text="Online  ·  GPU", fg=GREEN)
        c=memory_count(); d=len(list_logged_days())
        self.sm.configure(text=str(c)); self.sd.configure(text=str(d))
        self.mem_lbl.configure(text=str(c) + " memories  ·  " + str(d) + " days")

        threading.Thread(target=self._index_docs, daemon=True).start()

        startup_ctx = get_startup_context()
        if startup_ctx:
            memory_rule = "\n\n## Memory Rules\n- You have memory of past conversations. Use it ONLY when directly relevant to what TEK just said.\n- NEVER randomly bring up past events, achievements, or emotions unprompted.\n- If TEK mentions something related to a memory, you can reference it naturally. Otherwise, stay in the present conversation.\n- Do not mention the silver medal, competitions, stress, or anything from past logs unless TEK brings it up first."
            system_with_memory = SYSTEM_PROMPT + startup_ctx + memory_rule
            short_term._history[0].content = system_with_memory

        opening = get_opening_line(USER_NAME)
        self._vera(opening)
        self.inp.focus_set()

    # ── System Tray ───────────────────────────────────────────────────────────
    def _setup_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (64, 64), color="#0c0a0e")
            draw = ImageDraw.Draw(img)
            draw.ellipse([8, 8, 56, 56], fill="#8b1a2e", outline="#c42847")
            draw.text((22, 18), "V", fill="white")
            def toggle_startup():
                if is_startup_registered():
                    unregister_startup()
                else:
                    register_startup()

            menu = pystray.Menu(
                pystray.MenuItem("Open Vera",           self._show_window, default=True),
                pystray.MenuItem(
                    lambda item: "✓ Start on Boot" if is_startup_registered() else "✗ Start on Boot",
                    toggle_startup
                ),
                pystray.MenuItem("Quit", self._quit),
            )
            self.tray_icon = pystray.Icon(VERA_NAME, img, VERA_NAME, menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except ImportError:
            pass

    def _hide_to_tray(self):
        """Hide window to tray instead of closing."""
        self.root.withdraw()

    def _show_window(self):
        self._is_hidden = False
        self.root.after(0, self.root.deiconify)
        self.root.after(0, self.root.lift)
        self.root.after(0, self.root.focus_force)

    def _toggle_window(self):
        """Toggle Vera's window — called by Ctrl+Alt+Space hotkey."""
        def do_toggle():
            if self._is_hidden:
                self._is_hidden = False
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
                self.inp.focus_set()
            else:
                self._is_hidden = True
                self.root.withdraw()
        self.root.after(0, do_toggle)

    def _quit(self):
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.after(0, self._close)

    # ── Voice ─────────────────────────────────────────────────────────────────
    def _add_document(self):
        from pathlib import Path
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select a document for Vera",
            filetypes=[
                ("Documents", "*.pdf *.docx *.doc *.txt *.md *.py *.js *.json *.csv"),
                ("All files", "*.*")
            ]
        )
        if path:
            self._log("sys", "Indexing: " + Path(path).name + "...")
            def do_index():
                try:
                    n = index_file(path)
                    count = document_count()
                    self.root.after(0, lambda: self.sdoc.configure(text=str(count)))
                    self.root.after(0, lambda: self._log("sys", "Done! " + str(n) + " chunks indexed from " + Path(path).name))
                except Exception as e:
                    self.root.after(0, lambda: self._log("err", "Index error: " + str(e)))
            threading.Thread(target=do_index, daemon=True).start()

    def _toggle_always_listen(self):
        if not self._voice_pipeline_started:
            self._voice_pipeline_started = True
            start_pipeline(
                on_wake=self._on_wake_word,
                on_transcript=self._on_voice_transcript,
                on_error=lambda e: self.root.after(0, lambda: self._log("err", "Voice: " + e))
            )
            self._voice_active = True
            self.always_listen_btn.configure(bg=GARNET_DIM, fg=ROSE, text="👂 ON")
            self._log("sys", "Always-on voice started. Say 'Hey Vera' to wake her.")
        elif self._voice_active:
            stop_pipeline()
            self._voice_active = False
            self.always_listen_btn.configure(bg=BG_USER, fg=MUTED, text="👂 OFF")
            self._log("sys", "Voice paused.")
        else:
            start_pipeline(
                on_wake=self._on_wake_word,
                on_transcript=self._on_voice_transcript,
                on_error=lambda e: self.root.after(0, lambda: self._log("err", "Voice: " + e))
            )
            self._voice_active = True
            self.always_listen_btn.configure(bg=GARNET_DIM, fg=ROSE, text="👂 ON")
            self._log("sys", "Voice resumed.")

    def _on_wake_word(self):
        self.root.after(0, lambda: self.avatar.set_mode("listening"))
        self.root.after(0, lambda: self.av_st.configure(text="Listening...", fg=BLUE))
        self.root.after(0, lambda: self._log("sys", "Wake word detected..."))

    def _on_voice_transcript(self, text: str):
        self.root.after(0, lambda: self._process_voice_input(text))

    def _process_voice_input(self, text: str):
        if not self.ready or self.busy:
            return
        self._user(text)
        self._thinking(True)
        self.busy = True
        self.send_btn.configure(state=tk.DISABLED, bg=GARNET_DIM)
        threading.Thread(target=self._respond, args=(text,), daemon=True).start()

    def _toggle_tts(self):
        enabled = not tts_is_enabled()
        tts_set_enabled(enabled)
        if enabled:
            self.tts_btn.configure(bg=GARNET_DIM, fg=ROSE)
            self._log("sys", "Voice ON")
            speak("Voice enabled.")
        else:
            self.tts_btn.configure(bg=BG_USER, fg=MUTED)
            self._log("sys", "Voice OFF")

    def _pick_image(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select an image for Vera",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("All files", "*.*")]
        )
        if path:
            self.pending_image = path
            name = path.split("/")[-1].split("\\")[-1]
            self.img_btn.configure(bg=GARNET_DIM, fg=ROSE)
            self._log("sys", "Image ready: " + name + " — now type your question and send")

    def _toggle_voice(self):
        if self.listening:
            self.listening = False
            self.voice_btn.configure(bg=BG_USER, fg=MUTED)
            self.avatar.set_mode("idle")
            self.av_st.configure(text="Online", fg=GREEN)
        else:
            threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        try:
            import speech_recognition as sr
            self.listening = True
            self.root.after(0, lambda: self.voice_btn.configure(bg=GARNET_DIM, fg=ROSE))
            self.root.after(0, lambda: self.avatar.set_mode("listening"))
            self.root.after(0, lambda: self.av_st.configure(text="Listening...", fg=BLUE))
            r = sr.Recognizer()
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source, duration=0.5)
                audio = r.listen(source, timeout=8, phrase_time_limit=15)
            text = r.recognize_google(audio)
            self.listening = False
            self.root.after(0, lambda: self.voice_btn.configure(bg=BG_USER, fg=MUTED))
            self.root.after(0, lambda: self.inp.delete("1.0", tk.END))
            self.root.after(0, lambda: self.inp.insert("1.0", text))
            self.root.after(100, self._send)
        except ImportError:
            self.listening = False
            self.root.after(0, lambda: self._log("err", "Voice needs: pip install SpeechRecognition pyaudio"))
            self.root.after(0, lambda: self.voice_btn.configure(bg=BG_USER, fg=MUTED))
        except Exception as e:
            self.listening = False
            self.root.after(0, lambda: self._log("err", f"Voice error: {e}"))
            self.root.after(0, lambda: self.voice_btn.configure(bg=BG_USER, fg=MUTED))
            self.root.after(0, lambda: self.avatar.set_mode("idle"))

    # ── Web Search ────────────────────────────────────────────────────────────
    def _web_search_ai(self, query):
        self._log("wsrch", f"🔍 Searching: {query}")
        def go():
            try:
                import urllib.request, urllib.parse
                encoded = urllib.parse.quote_plus(query)
                url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
                req = urllib.request.urlopen(url, timeout=5)
                data = json.loads(req.read().decode())
                abstract = data.get("AbstractText", "") or data.get("Answer", "")
                if abstract:
                    context = f"Web search result for '{query}': {abstract[:500]}"
                else:
                    context = f"No instant answer found for '{query}'. Answer from your knowledge."
                msgs = list(short_term.get_messages())
                msgs.append({"role": "user", "content":
                    f"[Web Search Context]: {context}\n\nUser asked: {query}"})
                raw = model_loader.chat(msgs, max_tokens=200)
                p = parse_response(raw)
                speech = p.get("speech", abstract or "Couldn't find a good result.")
                self.root.after(0, lambda: self._vera(speech))
                self.root.after(0, self._reset)
            except Exception as e:
                self.root.after(0, lambda: self._log("err", f"Search error: {e}"))
                self.root.after(0, self._reset)
        threading.Thread(target=go, daemon=True).start()

    # ── Reminder callback ─────────────────────────────────────────────────────
    def _on_reminder(self, title, message):
        self.root.after(0, lambda: self._log("notif", f"⏰ REMINDER: {title} — {message}"))
        self.root.after(0, self._show_window)

    # ── Chat display ──────────────────────────────────────────────────────────
    def _log(self, tag, text):
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, text+"\n", tag)
        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

    def _vera(self, speech, cmd=None):
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, f"\n{VERA_NAME}\n", "vn")
        self.chat.insert(tk.END, speech+"\n", "vm")
        if cmd: self.chat.insert(tk.END, "  → " + str(cmd) + "\n", "cmd")
        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)
        speak(speech)

    def _vera_no_speak(self, speech, cmd=None):
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, f"\n{VERA_NAME}\n", "vn")
        self.chat.insert(tk.END, speech+"\n", "vm")
        if cmd: self.chat.insert(tk.END, "  → " + str(cmd) + "\n", "cmd")
        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

    def _user(self, text):
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, f"\n{USER_NAME}\n", "un")
        self.chat.insert(tk.END, text+"\n", "um")
        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

    def _thinking(self, on):
        self.chat.configure(state=tk.NORMAL)
        if on:
            self.chat.insert(tk.END, "\nthinking...\n", "thk")
            self.avatar.set_mode("thinking")
            self.av_st.configure(text="Thinking...", fg=ROSE)
        else:
            c = self.chat.get("1.0", tk.END)
            i = c.rfind("\nthinking...\n")
            if i >= 0:
                ln = c[:i].count("\n")+1
                self.chat.delete(f"{ln}.0", f"{ln+2}.0")
            self.avatar.set_mode("idle")
            self.av_st.configure(text="Online", fg=GREEN)
        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

    # ── Input ─────────────────────────────────────────────────────────────────
    def _enter(self, e):
        if e.state & 0x1: return
        self._send()
        return "break"

    def _send(self):
        if not self._text_model_on:
            self._log("sys", "Text model is OFF. Turn it on with the 🧠 switch.")
            return
        if not self.ready or self.busy: return
        text = self.inp.get("1.0", tk.END).strip()
        if not text: return
        self.inp.delete("1.0", tk.END)
        if text.startswith("/"): self._cmd(text); return
        self._user(text)
        self._thinking(True)
        self.busy = True
        self.send_btn.configure(state=tk.DISABLED, bg=GARNET_DIM)
        threading.Thread(target=self._respond, args=(text,), daemon=True).start()

    def _respond(self, user_input):
        try:
            short_term.add("user", user_input)
            img = self.pending_image
            self.pending_image = None
            self.root.after(0, lambda: self.img_btn.configure(bg=BG_USER, fg=MUTED))
            if img:
                import model_loader_vl as vl_loader
                raw = vl_loader.chat_with_image(short_term.get_messages(), image_path=img, max_tokens=300)
            else:
                self._msg_count += 1
                msgs = list(short_term.get_messages())

                doc_chunks = search_documents(user_input, n_results=3)
                if doc_chunks:
                    doc_context = format_for_context(doc_chunks)
                    msgs.append({"role": "system", "content": "Relevant document context:" + chr(10) + doc_context})


                raw = model_loader.chat(msgs, max_tokens=200)

            p = parse_response(raw)
            speech  = p.get("speech", "...")
            command = p.get("command") or None
            args    = p.get("args") or {}
            res = None

            # Fallback: if no command found but raw contains a create_* command, extract it
            if not command:
                fallback = extract_file_command(raw)
                if fallback:
                    command = fallback["command"]
                    args    = fallback["args"]

            # Clean speech — if it looks like raw JSON leaked into speech, replace it
            if speech.strip().startswith("{") or "\"command\"" in speech:
                import re
                # Extract just the speech value if possible
                sm = re.search(r'"speech"\s*:\s*"([^"]+)"', speech)
                speech = sm.group(1) if sm else "On it."

            if command == "confirm_action":
                action  = args.get("action")
                p_args  = args.get("args", {})
                if action and action not in DANGEROUS:
                    res_holder2 = [None]
                    ev2 = threading.Event()
                    def run_confirmed():
                        res_holder2[0] = execute(action, p_args)
                        ev2.set()
                    self.root.after(0, run_confirmed)
                    ev2.wait(timeout=10)
                    res = res_holder2[0]
                    short_term.add("assistant", raw)
                    self.root.after(0, lambda: self._show(speech, res))
                    return
                elif action in DANGEROUS:
                    short_term.add("assistant", raw)
                    self.root.after(0, lambda: self._show_with_confirm(speech, args))
                    return

            if command == "web_search":
                query = args.get("query", user_input)
                from datetime import datetime as _dt
                year = str(_dt.now().year)
                if year not in query and any(w in query.lower() for w in ["news","current","today","now","latest","recent","weather"]):
                    query = query + " " + year
                self.root.after(0, lambda: self._log("wsrch", "Searching: " + query))
                from tools.web_search import tavily_search, format_for_context
                results = tavily_search(query)
                context = format_for_context(results)
                augmented_msgs = list(short_term.get_messages())
                search_msg = "Web search results: " + chr(10) + context + chr(10) + chr(10) + "Based on these results, answer in JSON format: {speech: your answer as Vera, command: null, args: {}}"
                augmented_msgs.append({"role": "user", "content": search_msg})
                raw2 = model_loader.chat(augmented_msgs, max_tokens=250)
                p2 = parse_response(raw2)
                speech = p2.get("speech", speech)
                short_term.add("assistant", raw2)
                self.root.after(0, lambda: self._show(speech, None))
                return

            elif command == "take_screenshot":
                if not self._vl_model_on and not args.get("save", True):
                    self.root.after(0, lambda: self._show("Vision model is OFF. Turn it on with the 👁 switch first.", None))
                    return
                save = args.get("save", True)
                from tools.screenshot import take_screenshot
                screenshot_path = take_screenshot(save=save)
                if screenshot_path.startswith("error"):
                    self.root.after(0, lambda: self._show("Couldn't take screenshot: " + screenshot_path, None))
                    return
                if save:
                    # Just saved — no analysis, tell user where it is
                    short_term.add("assistant", raw)
                    self.root.after(0, lambda: self._show(speech, f"Saved to: {screenshot_path}"))
                    return
                else:
                    # Temp screenshot — analyze immediately then delete
                    self.root.after(0, lambda: self._log("sys", "Analyzing screen..."))
                    self._analyze_image_path(screenshot_path, raw, speech, delete_after=True)
                return

            elif command == "analyze_screenshot":
                # Analyze the last saved screenshot then delete it
                from tools.screenshot import analyze_screenshot
                path = analyze_screenshot()
                if path.startswith("error"):
                    self.root.after(0, lambda: self._show(path, None))
                    return
                self.root.after(0, lambda: self._log("sys", f"Analyzing saved screenshot..."))
                self._analyze_image_path(path, raw, speech, delete_after=True)
                return

            elif command and command not in DANGEROUS:
                res_holder = [None]
                ev = threading.Event()
                def run_cmd():
                    res_holder[0] = execute(command, args)
                    ev.set()
                self.root.after(0, run_cmd)
                ev.wait(timeout=10)
                res = res_holder[0]
            elif command in DANGEROUS:
                self.root.after(0, lambda: self._confirm(command, args, speech, raw))
                return

            short_term.add("assistant", raw)
            if self._msg_count % 5 == 0:
                threading.Thread(target=self._autosave, daemon=True).start()
            self.root.after(0, lambda: self._show(speech, res))
        except Exception as e:
            self.root.after(0, lambda: self._log("err", "Error: " + str(e)))
            self.root.after(0, self._reset)

    def _show_with_confirm(self, speech, pending):
        self._thinking(False)
        self._vera(speech)
        self.chat.configure(state=tk.NORMAL)
        btn_frame = tk.Frame(self.chat, bg=BG)

        def yes():
            btn_frame.destroy()
            action  = pending.get("action")
            p_args  = pending.get("args", {})
            self._log("sys", "Confirmed.")
            if action and action not in DANGEROUS:
                res_holder = [None]
                ev = threading.Event()
                def run():
                    res_holder[0] = execute(action, p_args)
                    ev.set()
                self.root.after(0, run)
                ev.wait(timeout=10)
                self._vera("Done.", res_holder[0])
            self._reset()

        def no():
            btn_frame.destroy()
            self._vera(f"My bad {USER_NAME}. What did you actually want?")
            self._reset()

        tk.Button(btn_frame, text="Yes", bg=GREEN, fg=BG,
                 font=self.F["small"], relief=tk.FLAT, padx=12, pady=4,
                 cursor="hand2", command=yes).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="No", bg=RED, fg=WHITE,
                 font=self.F["small"], relief=tk.FLAT, padx=12, pady=4,
                 cursor="hand2", command=no).pack(side=tk.LEFT, padx=4)

        self.chat.window_create(tk.END, window=btn_frame)
        self.chat.insert(tk.END, chr(10))
        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

    def _analyze_image_path(self, image_path: str, raw: str, speech: str, delete_after: bool = False):
        """Feed an image path to the vision model and show the result."""
        def go():
            try:
                import model_loader_vl as vl_loader
                vision_msgs = list(short_term.get_messages())
                raw_vision = vl_loader.chat_with_image(
                    vision_msgs,
                    image_path=image_path,
                    max_tokens=400
                )
                p2 = parse_response(raw_vision)
                vision_speech = p2.get("speech", raw_vision)
                short_term.add("assistant", raw_vision)
                if delete_after:
                    try:
                        import os as _os
                        _os.unlink(image_path)
                    except:
                        pass
                self.root.after(0, lambda: self._show(vision_speech, None))
            except Exception as e:
                self.root.after(0, lambda: self._show(f"Vision error: {e}", None))
        threading.Thread(target=go, daemon=True).start()

    def _show(self, speech, res):
        self._thinking(False)
        self._vera_no_speak(speech, res)
        if tts_is_enabled():
            def speak_then_reset():
                from tools.tts import _speak_blocking
                _speak_blocking(speech)
                self.root.after(0, self._reset)
            threading.Thread(target=speak_then_reset, daemon=True).start()
        else:
            self._reset()

    def _reset(self):
        self.busy = False
        self.send_btn.configure(state=tk.NORMAL, bg=GARNET)
        self.inp.focus_set()

    def _confirm(self, command, args, speech, raw):
        w = tk.Toplevel(self.root)
        w.title("Confirm"); w.geometry("320x150")
        w.configure(bg=BG_PANEL); w.resizable(False,False); w.grab_set()
        tk.Label(w, text=f"⚠  {command}", font=self.F["bold"], bg=BG_PANEL, fg=RED).pack(pady=(18,6))
        tk.Label(w, text="Vera wants to run this. Sure?", font=self.F["chat"], bg=BG_PANEL, fg=WHITE).pack()
        bf = tk.Frame(w, bg=BG_PANEL); bf.pack(pady=16)
        def yes():
            w.destroy()
            res=execute(command,args); short_term.add("assistant",raw)
            self.root.after(0, lambda: self._show(speech, res))
        def no():
            w.destroy(); short_term.add("assistant",raw)
            self.root.after(0, lambda: self._show(speech+f" — Fine, {USER_NAME}. Chickened out.", None))
        tk.Button(bf,text="Do it",bg=RED,fg=WHITE,font=self.F["chat"],
                 relief=tk.FLAT,padx=14,pady=4,cursor="hand2",command=yes).pack(side=tk.LEFT,padx=8)
        tk.Button(bf,text="Cancel",bg=BG_INPUT,fg=WHITE,font=self.F["chat"],
                 relief=tk.FLAT,padx=14,pady=4,cursor="hand2",command=no).pack(side=tk.LEFT,padx=8)

    # ── Commands ──────────────────────────────────────────────────────────────
    def _cmd(self, text):
        c = text.strip().lower()
        if c in ("/quit","/exit","/bye"):
            self._close()
        elif c == "/help":
            self._log("sys",
                "Commands:\n"
                "  /quit — exit\n"
                "  /memory — memory stats\n"
                "  /days — list logged days\n"
                "  /day YYYY-MM-DD — view a day\n"
                "  /reminders — list reminders\n"
                "  /save <fact> — save a memory\n"
                "  /websearch <query> — search the web\n"
                "  /help — this list"
            )
        elif c == "/memory":
            mc=memory_count(); d=len(list_logged_days())
            self._log("sys",f"Memories: {mc}  ·  Days: {d}")
            self.sm.configure(text=str(mc)); self.sd.configure(text=str(d))
        elif c == "/days":
            days=list_logged_days()
            self._log("sys","Days: "+( ", ".join(days[-10:]) if days else "none"))
        elif c.startswith("/day "):
            date_str = text[5:].strip()
            log = load_date(date_str)
            if not log:
                self._log("err", f"No log for {date_str}")
            else:
                s = log.get("summary")
                if s:
                    self._log("sys", f"{date_str}: {s.get('mood','?')} mood | Topics: {', '.join(s.get('topics',[]))}")
                else:
                    self._log("sys", f"{date_str}: no summary yet")
        elif c == "/reminders":
            self._log("sys", list_reminders())
        elif c.startswith("/save "):
            fact=text[6:].strip()
            if fact:
                store_memory(fact,metadata={"type":"manual","date":datetime.now().strftime("%Y-%m-%d")})
                self._log("sys",f"Saved: {fact}")
        elif c == "/websearch":
            self._log("sys", "Usage: /websearch your query here")
        elif c.startswith("/websearch "):
            query = text[11:].strip()
            if query:
                self.busy = True
                self.send_btn.configure(state=tk.DISABLED, bg=GARNET_DIM)
                self._web_search_ai(query)
        else:
            self._log("err",f"Unknown: {text}")

    # ── Close ─────────────────────────────────────────────────────────────────
    def _close(self):
        self._log("sys","Saving session...")
        self.avatar.set_mode("thinking")
        if self.tray_icon:
            try: self.tray_icon.stop()
            except: pass
        threading.Thread(
            target=lambda: end_session(lambda: self.root.after(0, self.root.destroy)),
            daemon=True).start()


if __name__ == "__main__":
    root = tk.Tk()
    app = VeraApp(root)

    # Always start dormant — hidden in tray.
    # Press Ctrl+Alt+Space to show the window.
    # Pass --show flag to start with window visible (e.g. first time setup).
    if "--show" not in sys.argv:
        app._is_hidden = True
        root.withdraw()

    root.mainloop()
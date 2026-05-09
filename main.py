"""
main.py — Vera AI Companion — Main conversation loop (terminal version).

Run with:
    python main.py
"""

import json
import sys
import os
from datetime import datetime

# ── Dependency check ──────────────────────────────────────────────────────────
def check_dependencies():
    missing = []
    required = {
        "llama_cpp":  "llama-cpp-python",
        "chromadb":   "chromadb",
        "pyautogui":  "pyautogui",
        "rich":       "rich",
    }
    for module, package in required.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    return missing

missing = check_dependencies()
if missing:
    print("\n[Vera] Missing dependencies. Install them first:\n")
    print(f"  pip install {' '.join(missing)}\n")
    print("Optional (for precise volume control on Windows):")
    print("  pip install pycaw comtypes AppOpener\n")
    sys.exit(1)

# ── Rich terminal styling ─────────────────────────────────────────────────────
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule

console = Console()

# ── Core modules ──────────────────────────────────────────────────────────────
from persona import SYSTEM_PROMPT, DANGEROUS_COMMANDS, DAILY_SUMMARY_PROMPT, USER_NICKNAME
from config import VERA_NAME, USER_NAME
import model_loader
from tool_registry import execute, DANGEROUS
from memory.short_term import ShortTermMemory
from memory.daily_log import (
    append_messages, save_summary, format_summaries_for_prompt,
    list_logged_days, load_date
)
from memory.vector_store import (
    format_memories_for_prompt, store_facts_from_summary,
    memory_count, store_memory
)

# ── Session state ─────────────────────────────────────────────────────────────
short_term = ShortTermMemory(max_messages=40)


def build_system_prompt(user_query: str = "") -> str:
    """Build the full system prompt with memory context injected."""
    base = SYSTEM_PROMPT
    past_summaries = format_summaries_for_prompt(days=7)
    long_term = format_memories_for_prompt(user_query, n_results=4) if user_query else ""
    extras = "\n\n".join(filter(None, [past_summaries, long_term]))
    if extras:
        base += f"\n\n---\n{extras}"
    return base


def parse_vera_response(raw: str) -> dict:
    """Parse Vera's JSON response. Handles messy output gracefully."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
    return {"speech": raw, "command": None, "args": {}}


def confirm_dangerous(command: str) -> bool:
    """Ask for confirmation before executing dangerous commands."""
    console.print(f"\n[bold yellow]⚠  Vera wants to run: {command}[/bold yellow]")
    answer = input("  Type 'yes' to confirm, anything else to cancel: ").strip().lower()
    return answer == "yes"


def display_vera(speech: str, command_result: str | None = None):
    """Render Vera's response in the terminal with styling."""
    panel_content = Text(speech, style="bold magenta")
    if command_result:
        panel_content.append(f"\n\n→ {command_result}", style="dim green")
    console.print(Panel(
        panel_content,
        title=f"[bold magenta]{VERA_NAME}[/bold magenta]",
        border_style="magenta",
        padding=(0, 2),
    ))


def display_help():
    """Show available commands."""
    console.print(Panel(
        "[bold]Special commands:[/bold]\n"
        "  [cyan]/quit[/cyan]       — End session (saves memory)\n"
        "  [cyan]/memory[/cyan]     — Show memory stats\n"
        "  [cyan]/days[/cyan]       — List all logged days\n"
        "  [cyan]/day YYYY-MM-DD[/cyan] — Show a specific day's summary\n"
        "  [cyan]/save <fact>[/cyan] — Manually save a memory\n"
        "  [cyan]/help[/cyan]       — Show this message",
        title="[bold cyan]Commands[/bold cyan]",
        border_style="cyan"
    ))


def handle_special_command(user_input: str) -> bool:
    """Handle /commands. Returns True if handled."""
    cmd = user_input.strip().lower()

    if cmd == "/help":
        display_help()
        return True

    if cmd == "/memory":
        count = memory_count()
        days = list_logged_days()
        console.print(f"[dim]Long-term memories: {count} | Logged days: {len(days)}[/dim]")
        return True

    if cmd == "/days":
        days = list_logged_days()
        if days:
            console.print("[dim]Logged days: " + ", ".join(days) + "[/dim]")
        else:
            console.print("[dim]No logs yet.[/dim]")
        return True

    if cmd.startswith("/day "):
        date_str = cmd[5:].strip()
        log = load_date(date_str)
        if not log:
            console.print(f"[dim]No log found for {date_str}[/dim]")
        else:
            summary = log.get("summary")
            if summary:
                console.print(Panel(
                    json.dumps(summary, indent=2),
                    title=f"[bold]{date_str}[/bold]",
                    border_style="dim"
                ))
            else:
                console.print(f"[dim]{date_str} has messages but no summary yet.[/dim]")
        return True

    if cmd.startswith("/save "):
        fact = user_input[6:].strip()
        if fact:
            store_memory(fact, metadata={"type": "manual", "date": datetime.now().strftime("%Y-%m-%d")})
            console.print(f"[dim green]Memory saved: {fact}[/dim green]")
        return True

    return False


def end_session():
    """Save session to daily log and generate summary."""
    console.print(Rule("[dim]Ending session...[/dim]"))

    raw_messages = short_term.get_raw()
    loggable = [
        {"role": m.role, "content": m.content, "timestamp": m.timestamp}
        for m in raw_messages
        if m.role != "system"
    ]
    if loggable:
        append_messages(loggable)

    try:
        console.print("[dim]Generating session summary...[/dim]")
        summary_messages = [
            {"role": "system", "content": "You are a helpful AI. Output only JSON."},
            {"role": "user", "content": (
                f"Here is a conversation log:\n\n"
                f"{json.dumps(loggable, indent=2)}\n\n"
                f"{DAILY_SUMMARY_PROMPT}"
            )}
        ]
        raw_summary = model_loader.chat(summary_messages, max_tokens=300, temperature=0.3)
        raw_summary = raw_summary.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        summary = json.loads(raw_summary)
        save_summary(summary)

        today = datetime.now().strftime("%Y-%m-%d")
        store_facts_from_summary(summary, today)

        console.print(f"[dim green]Session saved. Mood: {summary.get('mood', '?')} | Topics: {', '.join(summary.get('topics', []))}[/dim green]")
    except Exception as e:
        console.print(f"[dim yellow]Summary generation failed: {e}[/dim yellow]")

    console.print(f"\n[bold magenta]{VERA_NAME}[/bold magenta]: [magenta]Fine. Goodbye, {USER_NAME}. Don't do anything stupid while I'm gone.[/magenta]\n")


# ── Main Loop ─────────────────────────────────────────────────────────────────
def main():
    console.print(Rule(f"[bold magenta]{VERA_NAME} — AI Companion[/bold magenta]"))
    console.print("[dim]Type /help for commands. Type /quit to exit.[/dim]\n")

    try:
        model_loader.get_model()
    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/bold red]")
        sys.exit(1)

    initial_system = build_system_prompt()
    short_term.add("system", initial_system)

    import random
    nickname = random.choice([USER_NICKNAME, USER_NAME, "genius", "dummy"])
    display_vera(f"You're back. Took you long enough. What do you need, {nickname}?")

    while True:
        try:
            user_input = input("\n[You] ").strip()
        except (KeyboardInterrupt, EOFError):
            end_session()
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            if user_input.lower() in ("/quit", "/exit", "/bye"):
                end_session()
                break
            handle_special_command(user_input)
            continue

        short_term.add("user", user_input)

        try:
            raw = model_loader.chat(short_term.get_messages(), max_tokens=200)
        except Exception as e:
            console.print(f"[bold red]Model error: {e}[/bold red]")
            continue

        parsed = parse_vera_response(raw)
        speech  = parsed.get("speech", "...")
        command = parsed.get("command") or None
        args    = parsed.get("args") or {}

        command_result = None
        if command:
            if command in DANGEROUS:
                if confirm_dangerous(command):
                    command_result = execute(command, args)
                else:
                    speech += " — Fine, I won't do it."
                    command = None
            else:
                command_result = execute(command, args)

        short_term.add("assistant", raw)
        display_vera(speech, command_result)


if __name__ == "__main__":
    main()
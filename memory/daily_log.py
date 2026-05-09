"""
memory/daily_log.py — Daily conversation logs saved as JSON files.
Each day: logs/YYYY-MM-DD.json
"""
from __future__ import annotations
import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional

LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

def _today_path() -> Path:
    return LOGS_DIR / f"{date.today().isoformat()}.json"

def _load_log(path: Path) -> dict:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"date": path.stem, "messages": [], "summary": None, "session_count": 0}

def _save_log(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def _dedup_messages(messages: list) -> list:
    """Remove duplicate messages keeping order."""
    seen = set()
    result = []
    for m in messages:
        key = (m.get("role"), m.get("content", "")[:100])
        if key not in seen:
            seen.add(key)
            result.append(m)
    return result

def append_messages(messages: list[dict]) -> None:
    """Append messages to today's log, avoiding duplicates."""
    path = _today_path()
    data = _load_log(path)
    existing = data.get("messages", [])
    # Only add messages not already saved
    existing_keys = {(m.get("role"), m.get("content", "")[:100]) for m in existing}
    new_msgs = [m for m in messages
                if (m.get("role"), m.get("content", "")[:100]) not in existing_keys
                and m.get("role") != "system"]
    if new_msgs:
        data["messages"] = existing + new_msgs
        _save_log(path, data)

def save_summary(summary: dict) -> None:
    path = _today_path()
    data = _load_log(path)
    data["summary"] = summary
    data["session_count"] = data.get("session_count", 0) + 1
    _save_log(path, data)

def load_today() -> dict:
    return _load_log(_today_path())

def load_date(target_date: str) -> Optional[dict]:
    path = LOGS_DIR / f"{target_date}.json"
    if not path.exists():
        return None
    return _load_log(path)

def list_logged_days() -> list[str]:
    files = sorted(LOGS_DIR.glob("*.json"))
    return [f.stem for f in files]

def get_recent_summaries(days: int = 7) -> list[dict]:
    all_days = sorted(list_logged_days(), reverse=True)[:days]
    summaries = []
    for day in all_days:
        log = load_date(day)
        if log:
            # Include days with or without summary
            entry = {"date": day}
            if log.get("summary"):
                entry.update(log["summary"])
            else:
                # Extract topics from messages if no summary
                msgs = log.get("messages", [])
                user_msgs = [m["content"][:100] for m in msgs if m.get("role") == "user"]
                if user_msgs:
                    entry["topics"] = user_msgs[:3]
                    entry["mood"] = "unknown"
                    entry["key_facts"] = []
                    entry["notable_moments"] = f"Had {len(msgs)} messages"
            summaries.append(entry)
    return summaries

def format_summaries_for_prompt(days: int = 7) -> str:
    summaries = get_recent_summaries(days)
    if not summaries:
        return ""
    lines = ["## Recent conversation history:"]
    for s in summaries:
        lines.append(f"\n**{s['date']}**")
        topics = s.get("topics", [])
        if topics:
            lines.append(f"  Topics: {', '.join(topics)}")
        facts = s.get("key_facts", [])
        if facts:
            lines.append(f"  Key facts: {', '.join(facts)}")
        notable = s.get("notable_moments", "")
        if notable:
            lines.append(f"  Notable: {notable}")
    return "\n".join(lines)
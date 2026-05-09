"""
memory/startup.py — Loads past conversation context into Vera on startup.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

from memory.daily_log import load_date, list_logged_days, get_recent_summaries
from memory.vector_store import retrieve_memories


def build_startup_context() -> str:
    lines = []

    # ── Recent summaries (last 7 days) ───────────────────────────────────────
    summaries = get_recent_summaries(days=7)
    if summaries:
        lines.append("## Our recent conversations:")
        for s in summaries:
            date = s.get("date", "unknown")
            topics = s.get("topics", [])
            facts = s.get("key_facts", [])
            notable = s.get("notable_moments", "")
            line = f"\n**{date}**"
            if topics:
                line += f" — Topics: {', '.join(topics[:5])}"
            if facts:
                line += f"\n  Facts: {', '.join(facts[:3])}"
            if notable and notable != f"Had 0 messages":
                line += f"\n  Notable: {notable}"
            lines.append(line)

    # ── Last session actual messages (last 20) ────────────────────────────────
    days = list_logged_days()
    if days:
        # Load yesterday or most recent day
        for day in reversed(days[-3:]):
            last_day = load_date(day)
            if last_day:
                messages = last_day.get("messages", [])
                recent = [m for m in messages
                         if m.get("role") in ("user", "assistant")][-20:]
                if recent:
                    lines.append(f"\n## Last conversation ({day}):")
                    for m in recent:
                        role = "TEK" if m["role"] == "user" else "Vera"
                        content = m["content"][:200]
                        if len(m["content"]) > 200:
                            content += "..."
                        lines.append(f"  {role}: {content}")
                    break

    # ── Long-term memories ────────────────────────────────────────────────────
    memories = retrieve_memories("TEK preferences habits", n_results=5)
    if memories:
        lines.append("\n## Things I remember about TEK:")
        for m in memories:
            lines.append(f"  - [{m['date']}] {m['text']}")

    if not lines:
        return ""

    return "\n".join([
        "\n---",
        "# Memory loaded on startup — use naturally, don't announce it",
        *lines,
        "---",
    ])


def get_opening_line(user_name: str = "TEK") -> str:
    days = list_logged_days()
    if not days:
        return f"First time we've talked, {user_name}. Don't make it weird."

    last_date = days[-1]
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    if last_date == today:
        return f"Back already, {user_name}? Miss me?"
    elif last_date == yesterday:
        summaries = get_recent_summaries(days=1)
        if summaries and summaries[0].get("topics"):
            topic = summaries[0]["topics"][0]
            return f"Yesterday we were on about {topic}. Continuing or something new?"
        return f"Back again {user_name}."
    else:
        days_ago = (datetime.now() - datetime.strptime(last_date, "%Y-%m-%d")).days
        return f"It's been {days_ago} days, {user_name}. Welcome back."
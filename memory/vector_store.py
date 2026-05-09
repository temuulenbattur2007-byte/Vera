"""
memory/vector_store.py — Long-term semantic memory using ChromaDB.
Stores important facts/moments as embeddings. Retrieves by meaning, not keywords.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings

CHROMA_DIR = str(Path(__file__).parent.parent / "chroma_db")

_client: Optional[chromadb.Client] = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection

    _client = chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(anonymized_telemetry=False)
    )
    _collection = _client.get_or_create_collection(
        name="vera_memory",
        metadata={"description": "Vera long-term memory store"}
    )
    return _collection


def store_memory(text: str, metadata: Optional[dict] = None) -> str:
    """
    Store a memory string with optional metadata.
    Returns the memory's unique ID.
    """
    collection = _get_collection()
    memory_id = str(uuid.uuid4())
    meta = {
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        **(metadata or {})
    }
    collection.add(
        documents=[text],
        metadatas=[meta],
        ids=[memory_id]
    )
    return memory_id


def retrieve_memories(query: str, n_results: int = 4) -> list[dict]:
    """
    Retrieve the most semantically relevant memories for a given query.
    Returns list of {"text": ..., "date": ..., "metadata": ...}
    """
    collection = _get_collection()
    count = collection.count()
    if count == 0:
        return []

    n = min(n_results, count)
    results = collection.query(
        query_texts=[query],
        n_results=n,
        include=["documents", "metadatas", "distances"]
    )

    memories = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0]
    ):
        if dist < 1.5:
            memories.append({
                "text": doc,
                "date": meta.get("date", "unknown"),
                "metadata": meta,
                "relevance_score": round(1 - dist / 2, 3)
            })

    return memories


def format_memories_for_prompt(query: str, n_results: int = 4) -> str:
    """Format retrieved memories into a block for injection into the system prompt."""
    memories = retrieve_memories(query, n_results)
    if not memories:
        return ""

    lines = ["## Relevant Memories:"]
    for m in memories:
        lines.append(f"- [{m['date']}] {m['text']}")

    return "\n".join(lines)


def store_facts_from_summary(summary: dict, date_str: str) -> None:
    """Auto-extract and store key facts from a daily summary into long-term memory."""
    facts = summary.get("key_facts", [])
    notable = summary.get("notable_moments", "")

    for fact in facts:
        store_memory(fact, metadata={"type": "key_fact", "date": date_str})

    if notable:
        store_memory(notable, metadata={"type": "notable_moment", "date": date_str})


def memory_count() -> int:
    """Return total number of memories stored."""
    return _get_collection().count()
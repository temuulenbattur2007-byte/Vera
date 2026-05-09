"""
memory/rag.py — Document RAG system.
Indexes PDFs, text files, and Word docs into ChromaDB.
Vera searches them before answering relevant questions.
"""
import os
import json
import hashlib
from pathlib import Path
from typing import Optional

DOCS_DIR     = Path(__file__).parent.parent / "documents"
INDEX_FILE   = Path(__file__).parent.parent / "chroma_db" / "doc_index.json"
CHUNK_SIZE   = 500    # characters per chunk
CHUNK_OVERLAP = 50    # overlap between chunks

DOCS_DIR.mkdir(exist_ok=True)

# ── ChromaDB collection ───────────────────────────────────────────────────────
_collection = None

def _get_collection():
    global _collection
    if _collection is not None:
        return _collection
    import chromadb
    from chromadb.config import Settings
    client = chromadb.PersistentClient(
        path=str(Path(__file__).parent.parent / "chroma_db"),
        settings=Settings(anonymized_telemetry=False)
    )
    _collection = client.get_or_create_collection(
        name="vera_documents",
        metadata={"description": "Vera document RAG store"}
    )
    return _collection


# ── File readers ──────────────────────────────────────────────────────────────
def _read_pdf(path: str) -> str:
    import fitz  # pymupdf
    doc = fitz.open(path)
    text = ""
    for page in doc:
        text += page.get_text() + "\n"
    doc.close()
    return text


def _read_docx(path: str) -> str:
    from docx import Document
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _read_txt(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def _read_file(path: str) -> Optional[str]:
    ext = Path(path).suffix.lower()
    try:
        if ext == ".pdf":
            return _read_pdf(path)
        elif ext in (".docx", ".doc"):
            return _read_docx(path)
        elif ext in (".txt", ".md", ".py", ".js", ".ts", ".json", ".csv"):
            return _read_txt(path)
        else:
            return None
    except Exception as e:
        print(f"[RAG] Error reading {path}: {e}")
        return None


# ── Chunking ──────────────────────────────────────────────────────────────────
def _chunk_text(text: str, filename: str) -> list[dict]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    chunk_idx = 0

    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]

        if chunk.strip():
            chunk_id = hashlib.md5(f"{filename}_{chunk_idx}".encode()).hexdigest()
            chunks.append({
                "id":       chunk_id,
                "text":     chunk,
                "filename": filename,
                "chunk":    chunk_idx,
            })
            chunk_idx += 1

        start = end - CHUNK_OVERLAP

    return chunks


# ── Index management ──────────────────────────────────────────────────────────
def _load_index() -> dict:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text())
        except:
            pass
    return {}


def _save_index(index: dict):
    INDEX_FILE.parent.mkdir(exist_ok=True)
    INDEX_FILE.write_text(json.dumps(index, indent=2))


def _file_hash(path: str) -> str:
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


# ── Public API ────────────────────────────────────────────────────────────────
def index_file(path: str) -> int:
    """
    Index a single file into ChromaDB.
    Returns number of chunks indexed, or 0 if already up to date.
    """
    collection = _get_collection()
    index = _load_index()
    path = str(Path(path).resolve())
    filename = Path(path).name
    current_hash = _file_hash(path)

    # Skip if already indexed and unchanged
    if index.get(path) == current_hash:
        return 0

    # Read file
    text = _read_file(path)
    if not text or not text.strip():
        return 0

    # Remove old chunks for this file
    try:
        results = collection.get(where={"filename": filename})
        if results["ids"]:
            collection.delete(ids=results["ids"])
    except:
        pass

    # Index new chunks
    chunks = _chunk_text(text, filename)
    if not chunks:
        return 0

    collection.add(
        documents=[c["text"] for c in chunks],
        metadatas=[{"filename": c["filename"], "chunk": c["chunk"]} for c in chunks],
        ids=[c["id"] for c in chunks],
    )

    # Update index
    index[path] = current_hash
    _save_index(index)

    print(f"[RAG] Indexed {filename} — {len(chunks)} chunks")
    return len(chunks)


def index_directory(directory: str = None) -> dict:
    """
    Index all supported files in a directory.
    Returns summary of what was indexed.
    """
    dir_path = Path(directory) if directory else DOCS_DIR
    supported = {".pdf", ".docx", ".doc", ".txt", ".md", ".py", ".js", ".json", ".csv"}

    results = {"indexed": [], "skipped": [], "errors": []}

    for file in dir_path.rglob("*"):
        if file.suffix.lower() in supported:
            try:
                n = index_file(str(file))
                if n > 0:
                    results["indexed"].append(file.name)
                else:
                    results["skipped"].append(file.name)
            except Exception as e:
                results["errors"].append(f"{file.name}: {e}")

    return results


def search_documents(query: str, n_results: int = 4) -> list[dict]:
    """
    Search indexed documents for relevant chunks.
    Returns list of {text, filename, relevance} dicts.
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

    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0]
    ):
        if dist < 1.8:  # relevance threshold
            chunks.append({
                "text":      doc,
                "filename":  meta.get("filename", "unknown"),
                "relevance": round(1 - dist / 2, 3),
            })

    return chunks


def format_for_context(chunks: list[dict]) -> str:
    """Format search results for injection into Vera's context."""
    if not chunks:
        return ""

    lines = ["[Document Search Results]"]
    for c in chunks:
        lines.append(f"\nFrom: {c['filename']}")
        lines.append(c["text"])

    return "\n".join(lines)


def list_indexed_files() -> list[str]:
    """Return list of all indexed filenames."""
    index = _load_index()
    return [Path(p).name for p in index.keys()]


def document_count() -> int:
    """Return total number of indexed chunks."""
    return _get_collection().count()
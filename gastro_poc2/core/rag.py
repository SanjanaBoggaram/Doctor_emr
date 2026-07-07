"""
RAG (Retrieval-Augmented Generation) for the symptom-intake agent.

Drop clinical reference material (gastroenterology questioning guides, red-flag
criteria, symptom checklists, etc.) into `rag_data/` as .txt / .md / .pdf, then:

    python manage.py build_rag

This chunks + embeds the documents into a persistent Chroma store (`rag_store/`).
At chat time, `retrieve()` pulls the most relevant snippets so the agent can ask
better, guideline-grounded follow-up questions.

Design notes
------------
* Vector store: Chroma (persistent, metadata-aware, embeddings built in).
* Embeddings: local ONNX `all-MiniLM-L6-v2` by default — offline, free, no API
  key (good for medical data). Set RAG_EMBED_PROVIDER=gemini to use Gemini
  embeddings instead (needs GEMINI_API_KEY).
* Everything is lazy-imported and guarded, so the app runs fine even if chromadb
  isn't installed or the index hasn't been built — RAG just stays inactive.
"""

from __future__ import annotations

import os
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
RAG_DATA_DIR = Path(os.getenv("RAG_DATA_DIR", _BASE / "rag_data"))
RAG_STORE_DIR = Path(os.getenv("RAG_STORE_DIR", _BASE / "rag_store"))
COLLECTION = "clinical_kb"

SUPPORTED_EXTS = {".txt", ".md", ".pdf"}


def rag_enabled() -> bool:
    return os.getenv("RAG_ENABLED", "false").lower() in ("1", "true", "yes", "on")


def _top_k() -> int:
    try:
        return int(os.getenv("RAG_TOP_K", "4"))
    except ValueError:
        return 4


def _debug_enabled() -> bool:
    return os.getenv("RAG_DEBUG", "false").lower() in ("1", "true", "yes", "on")


# ── Embeddings ───────────────────────────────────────────────────────────────

def _embedding_fn():
    """Return a Chroma embedding function based on RAG_EMBED_PROVIDER."""
    from chromadb.utils import embedding_functions

    provider = os.getenv("RAG_EMBED_PROVIDER", "local").lower()
    if provider == "gemini":
        return embedding_functions.GoogleGenerativeAiEmbeddingFunction(
            api_key=os.getenv("GEMINI_API_KEY"),
            model_name=os.getenv("RAG_EMBED_MODEL", "models/text-embedding-004"),
        )
    # Local, offline, no API key (all-MiniLM-L6-v2 via ONNX).
    return embedding_functions.DefaultEmbeddingFunction()


def _client():
    import chromadb

    RAG_STORE_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(RAG_STORE_DIR))


# ── Document loading + chunking ──────────────────────────────────────────────

def _read_file(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def _chunk(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    """Paragraph-aware char chunking with overlap."""
    text = text.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) + 2 <= size:
            buf = f"{buf}\n\n{para}" if buf else para
        else:
            if buf:
                chunks.append(buf)
            # Carry a little overlap from the previous chunk for context.
            tail = buf[-overlap:] if buf else ""
            buf = f"{tail}\n\n{para}".strip() if tail else para
            # A single huge paragraph: hard-split it.
            while len(buf) > size:
                chunks.append(buf[:size])
                buf = buf[size - overlap:]
    if buf:
        chunks.append(buf)
    return chunks


def iter_source_files() -> list[Path]:
    if not RAG_DATA_DIR.exists():
        return []
    return sorted(
        p for p in RAG_DATA_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )


# ── Build + query ────────────────────────────────────────────────────────────

def build_index(verbose: bool = False) -> dict:
    """(Re)build the Chroma collection from everything in rag_data/.
    Returns a small stats dict."""
    files = iter_source_files()
    client = _client()

    # Fresh rebuild: drop and recreate the collection.
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    col = client.create_collection(COLLECTION, embedding_function=_embedding_fn())

    ids, docs, metas = [], [], []
    for f in files:
        rel = f.relative_to(RAG_DATA_DIR).as_posix()
        chunks = _chunk(_read_file(f))
        if verbose:
            print(f"  {rel}: {len(chunks)} chunks")
        for i, chunk in enumerate(chunks):
            ids.append(f"{rel}::{i}")
            docs.append(chunk)
            metas.append({"source": rel, "chunk": i})

    if docs:
        # Add in batches to keep memory/embedding calls reasonable.
        B = 100
        for s in range(0, len(docs), B):
            col.add(ids=ids[s:s + B], documents=docs[s:s + B], metadatas=metas[s:s + B])

    return {"files": len(files), "chunks": len(docs)}


def retrieve(query: str, k: int | None = None) -> list[dict]:
    """Return up to k relevant chunks as [{'text','source'}]. Never raises —
    returns [] if RAG is off, unbuilt, or anything goes wrong."""
    if not rag_enabled() or not query or not query.strip():
        return []
    try:
        client = _client()
        col = client.get_collection(COLLECTION, embedding_function=_embedding_fn())
        if col.count() == 0:
            return []
        res = col.query(query_texts=[query], n_results=k or _top_k())
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        snippets = [
            {"text": d, "source": (m or {}).get("source", "?")}
            for d, m in zip(docs, metas)
        ]
        if _debug_enabled() and snippets:
            print(f"[RAG] query: {query}")
            for idx, snippet in enumerate(snippets, start=1):
                preview = snippet["text"].strip().replace("\n", " ")
                if len(preview) > 500:
                    preview = preview[:500] + "..."
                print(f"[RAG] chunk {idx} | source={snippet['source']} | {preview}")
        return snippets
    except Exception:
        return []


def format_context(snippets: list[dict]) -> str:
    """Render retrieved snippets as a prompt-ready reference block."""
    blocks = []
    for s in snippets:
        blocks.append(f"[Source: {s['source']}]\n{s['text'].strip()}")
    return "\n\n---\n\n".join(blocks)

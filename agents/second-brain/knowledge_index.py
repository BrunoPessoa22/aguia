#!/usr/bin/env python3
"""
ÁGUIA Knowledge Indexer
Embeds all wiki articles + agent memory files into ChromaDB for semantic retrieval.
Run after Second Brain compiles new articles.
"""

import os
import sys
from pathlib import Path
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

WIKI_COMPILED = Path("$AGUIA_HOME/agents/second-brain/wiki/compiled")
MEMORY_DIRS = [
    Path("$AGUIA_HOME/agents/health-coach/memory"),
    Path("$AGUIA_HOME/agents/second-brain/memory"),
    Path("$AGUIA_HOME/agents/arara/memory"),
    Path("$AGUIA_HOME/agents/falcao/memory"),
    Path("$AGUIA_HOME/agents/fti-intern/memory"),
    Path("$AGUIA_HOME/agents/jaguar/memory"),
    Path("$AGUIA_HOME/agents/harpia/memory"),
    Path("$AGUIA_HOME/agents/canario/memory"),
    Path("$AGUIA_HOME/agents/coruja/memory"),
    Path("$AGUIA_HOME/agents/clawfix/memory"),
    Path("$WIKI_ROOT/raw/claude-code-memory"),
]
CHROMA_PATH = Path("$AGUIA_HOME/data/chroma")
MODEL_NAME = "all-MiniLM-L6-v2"


def load_documents():
    docs = []

    # Wiki compiled articles
    for md_file in sorted(WIKI_COMPILED.rglob("*.md")):
        content = md_file.read_text(encoding="utf-8", errors="ignore").strip()
        if len(content) < 50:
            continue
        rel = str(md_file.relative_to(WIKI_COMPILED))
        category = str(md_file.parent.relative_to(WIKI_COMPILED))
        lines = content.split("\n")
        title = lines[0].lstrip("# ").strip() if lines else md_file.stem
        docs.append({
            "id": f"wiki::{rel}",
            "text": content[:4000],
            "metadata": {
                "source": "wiki",
                "category": category,
                "title": title,
                "path": str(md_file),
                "rel_path": rel,
            }
        })

    # Agent memory files (last 7 days only — keep it fresh)
    import datetime
    cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
    for mem_dir in MEMORY_DIRS:
        if not mem_dir.exists():
            continue
        for md_file in sorted(mem_dir.glob("*.md")):
            try:
                mtime = datetime.datetime.fromtimestamp(md_file.stat().st_mtime)
                if mtime < cutoff:
                    continue
            except Exception:
                continue
            content = md_file.read_text(encoding="utf-8", errors="ignore").strip()
            if len(content) < 50:
                continue
            agent = mem_dir.parent.name
            docs.append({
                "id": f"memory::{agent}::{md_file.name}",
                "text": content[:4000],
                "metadata": {
                    "source": "memory",
                    "agent": agent,
                    "file": md_file.name,
                    "path": str(md_file),
                }
            })

    return docs


def main():
    print(f"Loading model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)

    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    # Use get_or_create so we can upsert incrementally
    collection = client.get_or_create_collection(
        name="aguia_knowledge",
        metadata={"hnsw:space": "cosine"}
    )

    docs = load_documents()
    print(f"Loaded {len(docs)} documents")

    if not docs:
        print("No documents found. Check paths.")
        sys.exit(1)

    texts = [d["text"] for d in docs]
    ids = [d["id"] for d in docs]
    metadatas = [d["metadata"] for d in docs]

    print("Embedding documents...")
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=32)

    print("Upserting to ChromaDB...")
    # Upsert in batches
    batch_size = 50
    for i in range(0, len(docs), batch_size):
        batch_ids = ids[i:i+batch_size]
        batch_embeddings = embeddings[i:i+batch_size].tolist()
        batch_texts = texts[i:i+batch_size]
        batch_meta = metadatas[i:i+batch_size]
        collection.upsert(
            ids=batch_ids,
            embeddings=batch_embeddings,
            documents=batch_texts,
            metadatas=batch_meta,
        )

    total = collection.count()
    print(f"Done. Collection has {total} documents indexed.")
    return total


if __name__ == "__main__":
    main()

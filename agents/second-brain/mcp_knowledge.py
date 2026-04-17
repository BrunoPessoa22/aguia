#!/usr/bin/env python3
"""
ÁGUIA Knowledge MCP Server
Exposes semantic search over wiki articles and agent memory files.
Compatible with Claude Code MCP protocol (stdio).
"""

import sys
import json
from pathlib import Path

CHROMA_PATH = Path("$AGUIA_HOME/data/chroma")

# Lazy-loaded
_model = None
_collection = None

def get_resources():
    global _model, _collection
    if _model is None:
        import chromadb
        from sentence_transformers import SentenceTransformer
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        _collection = client.get_collection("aguia_knowledge")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model, _collection


def semantic_search(query: str, n: int = 5, source: str = "all") -> dict:
    model, collection = get_resources()
    vec = model.encode([query])[0].tolist()
    where = None
    if source in ("wiki", "memory"):
        where = {"source": source}
    kwargs = {
        "query_embeddings": [vec],
        "n_results": min(n, 20),
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where
    res = collection.query(**kwargs)
    hits = []
    for i, doc_id in enumerate(res["ids"][0]):
        hits.append({
            "id": doc_id,
            "score": round(1 - res["distances"][0][i], 3),
            "source": res["metadatas"][0][i].get("source"),
            "title": res["metadatas"][0][i].get("title") or res["metadatas"][0][i].get("file", doc_id),
            "path": res["metadatas"][0][i].get("path", ""),
            "excerpt": res["documents"][0][i][:600],
        })
    return {
        "query": query,
        "total_indexed": collection.count(),
        "results": hits,
    }


TOOLS = [
    {
        "name": "knowledge_search",
        "description": (
            "Semantic search over ÁGUIA's knowledge base: 68+ wiki articles and recent agent memory files. "
            "Use this to find relevant context before answering questions or making decisions. "
            "Returns the most semantically similar documents with excerpts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query — describe what you're looking for",
                },
                "n": {
                    "type": "integer",
                    "description": "Number of results to return (default 5, max 20)",
                    "default": 5,
                },
                "source": {
                    "type": "string",
                    "enum": ["all", "wiki", "memory"],
                    "description": "Filter by source: 'wiki' for compiled articles, 'memory' for agent logs, 'all' for both",
                    "default": "all",
                },
            },
            "required": ["query"],
        },
    }
]


def handle_request(req: dict) -> dict:
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "aguia-knowledge", "version": "1.0.0"},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        tool_name = req.get("params", {}).get("name")
        args = req.get("params", {}).get("arguments", {})

        if tool_name == "knowledge_search":
            try:
                result = semantic_search(
                    query=args["query"],
                    n=args.get("n", 5),
                    source=args.get("source", "all"),
                )
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
                    },
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32000, "message": str(e)},
                }

    if method == "notifications/initialized":
        return None  # no response needed

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_request(req)
            if resp is not None:
                print(json.dumps(resp), flush=True)
        except Exception as e:
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"},
            }), flush=True)


if __name__ == "__main__":
    main()

"""Lightweight Wiki API server for EC2."""
import os
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

app = FastAPI(title="Wiki API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

WIKI_ROOT = Path(os.getenv("WIKI_ROOT", os.path.dirname(__file__)))

@app.get("/")
async def serve_root():
    return FileResponse(WIKI_ROOT / "index.html")

@app.get("/wiki")
async def serve_spa():
    return FileResponse(WIKI_ROOT / "index.html")

@app.get("/wiki/index")
async def get_index():
    compiled = WIKI_ROOT / "compiled"
    articles = []
    for md_file in sorted(compiled.rglob("*.md")):
        rel = md_file.relative_to(compiled)
        cat = str(rel.parent) if str(rel.parent) != "." else "uncategorized"
        content = md_file.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        title = lines[0].lstrip("# ").strip() if lines else md_file.stem
        articles.append({"path": str(rel), "category": cat, "title": title, "word_count": len(content.split()), "size_bytes": md_file.stat().st_size})
    categories = {}
    for a in articles:
        categories.setdefault(a["category"], []).append(a)
    return {"total_articles": len(articles), "total_words": sum(a["word_count"] for a in articles), "categories": categories, "articles": articles}

@app.get("/wiki/article/{path:path}")
async def get_article(path: str):
    article_path = WIKI_ROOT / "compiled" / path
    if not article_path.exists():
        raise HTTPException(404, "Article not found")
    content = article_path.read_text(encoding="utf-8")
    return {"path": path, "content": content, "word_count": len(content.split())}

@app.get("/wiki/search")
async def search_wiki(q: str):
    compiled = WIKI_ROOT / "compiled"
    results = []
    for md_file in compiled.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        if q.lower() in content.lower():
            rel = str(md_file.relative_to(compiled))
            lines = content.strip().split("\n")
            title = lines[0].lstrip("# ").strip() if lines else md_file.stem
            matches = sum(1 for l in lines if q.lower() in l.lower())
            results.append({"path": rel, "title": title, "matches": matches})
    return {"query": q, "results": sorted(results, key=lambda r: -r["matches"])}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3200)

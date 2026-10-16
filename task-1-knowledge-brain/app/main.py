import os
import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from app.models import (
    SearchRequest, SearchResult, AskRequest, AskResponse,
    ExpertTask, ExpertTaskResolve, SyncReport
)
from app.database import Database
from app.rag_engine import HybridRAGEngine
from app.crawler import PoliteCrawler
from app.vision import VisionAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("knowledge_brain")

app = FastAPI(
    title="AI Tech Consultant - Knowledge Brain API",
    version="1.0.0",
    description="Task 1: Self-evolving product memory, polite crawler, multimodal vision, and RAG service."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.getenv("KNOWLEDGE_DB_PATH", "knowledge_brain.db")
db = Database(db_path=DB_PATH)
vision = VisionAnalyzer()
crawler = PoliteCrawler(db=db, vision_analyzer=vision)
rag_engine = HybridRAGEngine(db=db)

@app.get("/")
def root():
    return {
        "service": "Knowledge Brain API",
        "status": "online",
        "version": "1.0.0",
        "active_articles_count": len(db.get_all_active_urls()),
        "chunks_count": len(db.get_all_chunks()),
        "docs_url": "/docs"
    }

@app.post("/api/v1/search", response_model=List[SearchResult])
def search_knowledge(req: SearchRequest):
    return rag_engine.search(query=req.query, top_k=req.top_k, category=req.category)

@app.post("/api/v1/ask", response_model=AskResponse)
async def ask_question(req: AskRequest, model: str = Query("claude-3-5-haiku-20241022")):
    return await rag_engine.ask(request=req, model=model)

@app.post("/api/v1/sync", response_model=SyncReport)
async def trigger_sync(background_tasks: BackgroundTasks, max_pages: Optional[int] = Query(None)):
    report = await crawler.sync_daily(max_pages=max_pages)
    return report

@app.get("/api/v1/articles", response_model=List[str])
def list_active_articles():
    return db.get_all_active_urls()

@app.delete("/api/v1/articles")
def remove_article(url: str = Query(..., description="Article URL to remove")):
    db.mark_article_removed(url)
    return {"status": "success", "message": f"Article {url} removed and purged from active chunks"}

@app.get("/api/v1/expert-tasks", response_model=List[ExpertTask])
def get_expert_tasks(status: Optional[str] = Query(None)):
    return db.get_expert_tasks(status=status)

@app.post("/api/v1/expert-tasks/{task_id}/resolve", response_model=ExpertTask)
def resolve_expert_task(task_id: str, body: ExpertTaskResolve):
    resolved = db.resolve_expert_task(task_id=task_id, expert_answer=body.expert_answer)
    if not resolved:
        raise HTTPException(status_code=404, detail="Expert task not found")
    return resolved

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

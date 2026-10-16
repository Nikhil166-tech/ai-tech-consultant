import os
import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from app.models import (
    SearchRequest, SearchResult, AskRequest, AskResponse,
    ExpertTask, ExpertTaskResolve, SyncReport, SyncStatus
)
from app.database import Database
from app.rag_engine import HybridRAGEngine
from app.crawler import PoliteCrawler
from app.vision import VisionAnalyzer
from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("knowledge_brain")

app = FastAPI(
    title="AI Tech Consultant - Knowledge Brain API",
    version="2.0.0",
    description="Task 1: Self-evolving product memory, polite crawler, multimodal vision, and hybrid RAG service."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = Database(db_path=settings.knowledge_db_path)
vision = VisionAnalyzer()
crawler = PoliteCrawler(db=db, vision_analyzer=vision)
rag_engine = HybridRAGEngine(db=db)

@app.get("/health")
def health_check():
    """Operational health check verifying database connectivity and active index size."""
    try:
        active_articles = len(db.get_all_active_urls())
        chunks_count = len(db.get_all_chunks())
        return {
            "status": "healthy",
            "database": "connected",
            "active_articles_count": active_articles,
            "chunks_count": chunks_count,
            "environment": "production" if os.getenv("ANTHROPIC_API_KEY") else "local_test"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unhealthy: {str(e)}")

@app.get("/")
def root():
    return {
        "service": "Knowledge Brain API",
        "status": "online",
        "version": "2.0.0",
        "health_check": "/health",
        "docs_url": "/docs"
    }

@app.post("/api/v1/search", response_model=List[SearchResult])
def search_knowledge(req: SearchRequest):
    return rag_engine.search(query=req.query, top_k=req.top_k, category=req.category)

@app.post("/api/v1/ask", response_model=AskResponse)
async def ask_question(
    req: AskRequest,
    model: Optional[str] = Query(None, description="Claude model identifier (defaults to configured text model)")
):
    return await rag_engine.ask(request=req, model=model)

@app.post("/api/v1/sync", response_model=SyncReport)
async def trigger_sync(max_pages: Optional[int] = Query(None, description="Limit crawl slice for test runs")):
    """
    Checks complete sitemap against local DB: indexes added/updated articles,
    purges deleted articles from active memory.
    """
    report = await crawler.sync_daily(max_pages=max_pages)
    return report

@app.get("/api/v1/sync/status", response_model=SyncStatus)
def get_sync_status():
    """Returns the latest crawler sync job status, step progress, and last execution report."""
    return db.get_sync_status()

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
    resolved = db.resolve_expert_task(
        task_id=task_id,
        expert_answer=body.expert_answer,
        expert_id=body.expert_id or "expert_reviewer",
        version=body.version or "1.0",
        provenance_notes=body.provenance_notes or "Manual product specialist review"
    )
    if not resolved:
        raise HTTPException(status_code=404, detail="Expert task not found")
    return resolved

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

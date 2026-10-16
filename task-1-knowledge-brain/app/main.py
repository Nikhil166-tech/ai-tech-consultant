import os
import asyncio
import logging
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
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

db = Database(db_path=settings.knowledge_db_path)
vision = VisionAnalyzer()
crawler = PoliteCrawler(db=db, vision_analyzer=vision)
rag_engine = HybridRAGEngine(db=db)

# Lightweight background sync loop (no heavy message queues or Redis)
_daily_sync_task: Optional[asyncio.Task] = None

async def _daily_sync_loop():
    interval_seconds = settings.sync_interval_hours * 3600.0
    logger.info(f"Daily sync worker started. Scheduled every {settings.sync_interval_hours}h ({interval_seconds}s).")
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            logger.info("Executing scheduled daily sitemap sync...")
            await crawler.sync_daily()
        except asyncio.CancelledError:
            logger.info("Daily sync worker received cancellation.")
            break
        except Exception as e:
            logger.error(f"Error during scheduled daily sync: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _daily_sync_task
    if settings.enable_background_sync:
        _daily_sync_task = asyncio.create_task(_daily_sync_loop())
        logger.info("Background daily sitemap sync worker scheduled.")
    else:
        logger.info("Background daily sitemap sync is disabled by configuration (test/local mode).")
    try:
        yield
    finally:
        if _daily_sync_task and not _daily_sync_task.done():
            _daily_sync_task.cancel()
            try:
                await _daily_sync_task
            except asyncio.CancelledError:
                pass

app = FastAPI(
    title="AI Tech Consultant - Knowledge Brain API",
    version="2.1.0",
    description="Task 1: Self-evolving product memory, polite crawler, multimodal vision, and hybrid RAG service.",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    """
    Operational health check verifying DB connectivity, active index size,
    embedding provider status, daily sync configuration, and active models.
    """
    try:
        active_articles = len(db.get_all_active_urls())
        chunks_count = len(db.get_all_chunks())
        
        emb_status = rag_engine.retriever.embedder.get_status()
        
        overall_status = "healthy"
        if emb_status.get("status") in ["error", "degraded"]:
            overall_status = "degraded"

        return {
            "status": overall_status,
            "database": "connected",
            "active_articles_count": active_articles,
            "chunks_count": chunks_count,
            "embedding": emb_status,
            "daily_sync_enabled": settings.enable_background_sync,
            "sync_interval_hours": settings.sync_interval_hours,
            "models": {
                "text": settings.anthropic_model_text,
                "vision": settings.anthropic_model_vision
            },
            "environment": "production" if os.getenv("ANTHROPIC_API_KEY") else "local_test"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")

@app.get("/")
def root():
    return {
        "service": "Knowledge Brain API",
        "status": "online",
        "version": "2.1.0",
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
async def trigger_sync(
    max_pages: Optional[int] = Query(None, description="Limit crawl slice for test runs"),
    force: bool = Query(False, description="Force re-processing and re-embedding of articles even if content hash is unchanged")
):
    """
    Checks complete sitemap against local DB: indexes added/updated articles,
    purges deleted articles from active memory. Supports force=True for complete re-indexing.
    """
    report = await crawler.sync_daily(max_pages=max_pages, force=force)
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

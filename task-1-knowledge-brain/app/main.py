import os
import asyncio
import logging
import hashlib
import secrets
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Response, Request, Cookie, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from app.models import (
    SearchRequest, SearchResult, AskRequest, AskResponse,
    ExpertTask, ExpertTaskResolve, SyncReport, SyncStatus,
    SitemapCreate, SitemapItem, SitemapPreview, RefreshRunSummary,
    RefreshRunDetail, QuarantineRecord, QuarantineReason,
    URLHealthStatus, UserSettings
)
from app.database import Database
from app.rag_engine import HybridRAGEngine
from app.crawler import PoliteCrawler, validate_url_ssrf_safe
from app.vision import VisionAnalyzer
from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("knowledge_brain")

db = Database(db_path=settings.knowledge_db_path)
vision = VisionAnalyzer()
crawler = PoliteCrawler(db=db, vision_analyzer=vision)
rag_engine = HybridRAGEngine(db=db)

# -------------------------------------------------------------
# Security & Auth Helpers
# -------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000)
    return f"{salt}${key.hex()}"

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, key_hex = stored_hash.split("$")
        check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000)
        return secrets.compare_digest(check.hex(), key_hex)
    except Exception:
        return False

class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str

class PreviewRequest(BaseModel):
    url: str

class QuarantineRestoreRequest(BaseModel):
    url: str

def get_current_user(request: Request) -> Dict[str, Any]:
    session_id = request.cookies.get("session_id")
    if session_id:
        user = db.get_session_user(session_id)
        if user:
            return user
    # Fallback to default demo user for frictionless local development
    return {"id": "default_user", "email": "demo@consultant.ai", "display_name": "Demo Admin", "role": "admin"}

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
    version="2.2.0",
    description="Self-evolving product memory, polite crawler, multi-sitemap management, URL health & quarantine, and hybrid RAG service.",
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
        active_articles = db.count_active_articles()
        chunks_count = db.count_active_chunks()
        
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
        "version": "2.2.0",
        "health_check": "/health",
        "docs_url": "/docs"
    }

# -------------------------------------------------------------
# Phase 6: Authentication Endpoints
# -------------------------------------------------------------
@app.post("/api/v1/auth/register")
def register_user(req: RegisterRequest, response: Response):
    existing = db.get_user_by_email(req.email)
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists")
    
    hashed = hash_password(req.password)
    user = db.create_user(email=req.email, password_hash=hashed, display_name=req.display_name or "")
    session_id = db.create_session(user["id"])
    response.set_cookie(key="session_id", value=session_id, httponly=True, samesite="lax", max_age=86400 * 7)
    return {"status": "success", "user": user}

@app.post("/api/v1/auth/login")
def login_user(req: LoginRequest, response: Response):
    user = db.get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    session_id = db.create_session(user["id"])
    response.set_cookie(key="session_id", value=session_id, httponly=True, samesite="lax", max_age=86400 * 7)
    user_data = {"id": user["id"], "email": user["email"], "display_name": user["display_name"], "role": user["role"]}
    return {"status": "success", "user": user_data}

@app.post("/api/v1/auth/logout")
def logout_user(request: Request, response: Response):
    session_id = request.cookies.get("session_id")
    if session_id:
        db.delete_session(session_id)
    response.delete_cookie(key="session_id")
    return {"status": "success", "message": "Logged out successfully"}

@app.get("/api/v1/auth/me")
def get_me(user: Dict[str, Any] = Depends(get_current_user)):
    return {"user": user}

# -------------------------------------------------------------
# User Settings Endpoints
# -------------------------------------------------------------
@app.get("/api/v1/settings", response_model=UserSettings)
def get_settings(user: Dict[str, Any] = Depends(get_current_user)):
    return db.get_user_settings(user_id=user["id"])

@app.post("/api/v1/settings", response_model=UserSettings)
def update_settings(req: UserSettings, user: Dict[str, Any] = Depends(get_current_user)):
    req.user_id = user["id"]
    db.save_user_settings(req)
    return req

# -------------------------------------------------------------
# Phase 2: Custom Sitemap Management Endpoints
# -------------------------------------------------------------
@app.post("/api/v1/sitemaps/preview", response_model=SitemapPreview)
async def preview_sitemap(req: PreviewRequest):
    """
    Validates and previews a submitted sitemap URL before indexing:
    - Recursively resolves nested sitemaps
    - Extracts unique URLs and exact sitemap lastmod timestamps
    - Checks SSRF and destination constraints
    """
    return await crawler.preview_sitemap(req.url)

@app.post("/api/v1/sitemaps", response_model=SitemapItem)
def create_sitemap(req: SitemapCreate, user: Dict[str, Any] = Depends(get_current_user)):
    validate_url_ssrf_safe(req.url)
    days = req.refresh_interval_days or 1
    if req.refresh_interval:
        mapping = {"daily": 1, "weekly": 7, "biweekly": 15, "monthly": 30}
        days = mapping.get(str(req.refresh_interval).lower(), days)
    return db.create_sitemap(
        root_url=req.url,
        name=req.name or req.url,
        user_id=user["id"],
        refresh_interval_days=days
    )

@app.get("/api/v1/sitemaps", response_model=List[SitemapItem])
def list_sitemaps(user: Dict[str, Any] = Depends(get_current_user)):
    return db.get_sitemaps(user_id=user["id"])

@app.get("/api/v1/sitemaps/estimate")
def get_sitemap_indexing_estimate():
    estimate = crawler.throughput_tracker.get_estimate(total_remaining=0)
    data = estimate.model_dump()
    data["observed_pages_per_5min"] = estimate.pages_processed_5min
    data["estimated_pages_per_hour"] = int(estimate.observed_throughput_pages_per_min * 60)
    data["formatted_estimate"] = estimate.estimated_completion_time_human
    data["is_estimate_only"] = True
    data["notes"] = estimate.disclaimer
    return data

@app.get("/api/v1/sitemaps/{sitemap_id}", response_model=SitemapItem)
def get_sitemap_detail(sitemap_id: str):
    sm = db.get_sitemap(sitemap_id)
    if not sm:
        raise HTTPException(status_code=404, detail="Sitemap not found")
    return sm

@app.post("/api/v1/sitemaps/{sitemap_id}/confirm")
def confirm_sitemap_for_indexing(sitemap_id: str):
    confirmed = db.confirm_sitemap(sitemap_id)
    if not confirmed:
        raise HTTPException(status_code=404, detail="Sitemap not found")
    return {"status": "confirmed", "message": f"Sitemap {sitemap_id} confirmed for scheduled indexing"}

@app.post("/api/v1/sitemaps/{sitemap_id}/confirm-index", response_model=RefreshRunSummary)
async def confirm_and_begin_indexing(
    sitemap_id: str,
    max_pages: Optional[int] = Query(None, description="Limit crawl slice for testing"),
    sync: bool = Query(False, description="Wait synchronously until crawl completes"),
    user: Dict[str, Any] = Depends(get_current_user)
):
    sm = db.get_sitemap(sitemap_id)
    if not sm:
        raise HTTPException(status_code=404, detail="Sitemap not found")
    db.confirm_sitemap(sitemap_id)

    summary = db.create_refresh_run(sitemap_id=sitemap_id, user_id=user["id"])
    task = asyncio.create_task(crawler.execute_refresh_run(
        sitemap_id=sitemap_id,
        user_id=user["id"],
        max_pages=max_pages,
        force=False,
        existing_summary=summary
    ))

    if sync:
        return await task
    return summary

@app.get("/api/v1/sitemaps/{sitemap_id}/relationships")
def get_sitemap_relationships(sitemap_id: str):
    return db.get_sitemap_relationships(sitemap_id)

# -------------------------------------------------------------
# Phase 3: Refresh Runs & History Endpoints
# -------------------------------------------------------------
@app.post("/api/v1/sitemaps/{sitemap_id}/refresh", response_model=RefreshRunSummary)
@app.post("/api/v1/sitemaps/{sitemap_id}/trigger-refresh", response_model=RefreshRunSummary)
async def trigger_sitemap_refresh(
    sitemap_id: str,
    max_pages: Optional[int] = Query(None, description="Limit crawl slice for testing"),
    force: bool = Query(False, description="Force re-chunking and re-embedding"),
    sync: bool = Query(False, description="Wait synchronously until crawl completes"),
    user: Dict[str, Any] = Depends(get_current_user)
):
    sm = db.get_sitemap(sitemap_id)
    if not sm:
        raise HTTPException(status_code=404, detail="Sitemap not found")

    summary = db.create_refresh_run(sitemap_id=sitemap_id, user_id=user["id"])
    task = asyncio.create_task(crawler.execute_refresh_run(
        sitemap_id=sitemap_id,
        user_id=user["id"],
        max_pages=max_pages,
        force=force,
        existing_summary=summary
    ))

    if sync:
        return await task
    return summary

@app.get("/api/v1/refresh-runs", response_model=List[RefreshRunSummary])
def list_refresh_runs(sitemap_id: Optional[str] = Query(None), limit: int = Query(20, le=100)):
    return db.get_refresh_runs(sitemap_id=sitemap_id, limit=limit)

@app.get("/api/v1/refresh-runs/{run_id}", response_model=RefreshRunDetail)
def get_refresh_run_detail(
    run_id: str,
    search: Optional[str] = Query(None, description="Filter URLs by search substring"),
    status: Optional[str] = Query(None, description="Filter URLs by status"),
    limit: int = Query(200, le=1000),
    offset: int = Query(0, ge=0)
):
    detail = db.get_refresh_run_detail(run_id=run_id, search=search, status_filter=status, limit=limit, offset=offset)
    if not detail:
        raise HTTPException(status_code=404, detail="Refresh run not found")
    return detail

# -------------------------------------------------------------
# Phase 4: URL Health & Quarantine Endpoints
# -------------------------------------------------------------
@app.get("/api/v1/health-observations", response_model=List[URLHealthStatus])
def list_url_health_statuses(sitemap_id: Optional[str] = Query(None)):
    return db.get_url_health_statuses(sitemap_id=sitemap_id)

@app.get("/api/v1/quarantine", response_model=List[QuarantineRecord])
def list_quarantined_articles():
    return db.get_quarantined_articles()

@app.post("/api/v1/quarantine/restore")
def restore_quarantined_article(req: QuarantineRestoreRequest):
    restored = db.restore_quarantined_article(req.url)
    if not restored:
        raise HTTPException(status_code=404, detail="Quarantined record not found or could not be restored")
    return {"status": "success", "message": f"Successfully restored {req.url} to active knowledge"}

# -------------------------------------------------------------
# Core Knowledge RAG Endpoints (Preserved & Enhanced)
# -------------------------------------------------------------
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
    Backwards-compatible endpoint for triggering polite sitemap sync.
    """
    return await crawler.sync_daily(max_pages=max_pages, force=force)

@app.get("/api/v1/sync/status", response_model=SyncStatus)
def get_sync_status():
    """Returns the latest crawler sync job status, step progress, and last execution report."""
    return db.get_sync_status()

@app.get("/api/v1/articles")
def list_active_articles(limit: int = Query(100, le=500)):
    return db.get_active_articles(limit=limit)

@app.get("/api/v1/articles/urls", response_model=List[str])
def list_active_article_urls():
    return db.get_all_active_urls()

@app.delete("/api/v1/articles")
def remove_article(url: str = Query(..., description="Article URL to remove")):
    db.mark_article_removed(url)
    return {"status": "success", "message": f"Article {url} removed from active memory"}

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


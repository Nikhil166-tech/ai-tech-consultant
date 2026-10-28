import os
import time
import uuid
import asyncio
import logging
import secrets
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Response, Request, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

from app.models import (
    SearchRequest, SearchResult, AskRequest, AskResponse,
    ExpertTask, ExpertTaskResolve, SyncReport, SyncStatus,
    SitemapCreate, SitemapItem, SitemapPreview, RefreshRunSummary,
    RefreshRunDetail, QuarantineRecord, QuarantineReason,
    URLHealthStatus, UserSettings, ScheduleUpdateRequest,
    SchedulerStatusResponse, ArchivedArticleItem, ArchivedArticleDetail,
    ArchiveRetentionUpdateRequest, ArticleRedirectItem, ArticleHistoryItem,
    ModelRoleStatusItem, AIModelStatusResponse
)
from app.database import Database
from app.rag_engine import HybridRAGEngine
from app.crawler import PoliteCrawler, validate_url_ssrf_safe
from app.scheduler import SitemapScheduler
from app.vision import VisionAnalyzer
from app.config import settings
from app.auth import (
    hash_password, verify_password, verify_and_check_rehash, needs_rehash, validate_email, validate_password_strength
)

# Production-safe logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("knowledge_brain")

db = Database(db_path=settings.knowledge_db_path)
vision = VisionAnalyzer()
crawler = PoliteCrawler(db=db, vision_analyzer=vision)
scheduler = SitemapScheduler(db=db, crawler=crawler)
rag_engine = HybridRAGEngine(db=db)

# -------------------------------------------------------------
# Request Models
# -------------------------------------------------------------
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
    url: Optional[str] = None
    id: Optional[str] = None

# In-memory IP rate limiter for failed login attempts
_failed_login_ips: Dict[str, List[float]] = {}

def check_ip_rate_limit(ip: str, limit: int = 15, window_seconds: float = 900.0) -> bool:
    now = datetime.now(timezone.utc).timestamp()
    attempts = [t for t in _failed_login_ips.get(ip, []) if now - t < window_seconds]
    _failed_login_ips[ip] = attempts
    return len(attempts) < limit

def record_ip_failure(ip: str):
    now = datetime.now(timezone.utc).timestamp()
    if ip not in _failed_login_ips:
        _failed_login_ips[ip] = []
    _failed_login_ips[ip].append(now)

# -------------------------------------------------------------
# Authentication & CSRF Dependencies
# -------------------------------------------------------------
def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Enforces authentication for protected customer-facing routes.
    Accepts:
    1. Internal service key header (X-Internal-Service-Key)
    2. Secure HttpOnly session cookie (session_id)
    3. Authorization Bearer header (session_id)
    Returns authenticated user dict.
    STRICT SECURITY: Returns HTTP 401 if unauthenticated. NO DEFAULT ADMIN FALLBACK.
    """
    # 1. Check for authenticated internal service communication (Task 2 & 3 -> Task 1)
    internal_key = request.headers.get("x-internal-service-key")
    if internal_key:
        if settings.internal_service_key and secrets.compare_digest(internal_key, settings.internal_service_key):
            return {
                "id": "service_internal",
                "email": "internal@system.local",
                "display_name": "Internal Service",
                "role": "service"
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal service key."
        )

    # 2. Check session cookie or Authorization Bearer header
    session_id = request.cookies.get("session_id")
    if not session_id:
        auth_hdr = request.headers.get("authorization", "")
        if auth_hdr.startswith("Bearer "):
            session_id = auth_hdr[7:].strip()

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in."
        )

    user = db.get_session_user(session_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or is invalid. Please sign in again."
        )

    return user

def get_current_user_or_internal(request: Request) -> Optional[Dict[str, Any]]:
    """
    User dependency for shared knowledge endpoints (e.g. search, ask).
    Allows internal service calls, authenticated user sessions, or anonymous read-only access.
    Explicitly rejects invalid service keys or expired sessions.
    """
    internal_key = request.headers.get("x-internal-service-key")
    if internal_key:
        if settings.internal_service_key and secrets.compare_digest(internal_key, settings.internal_service_key):
            return {
                "id": "service_internal",
                "email": "internal@system.local",
                "display_name": "Internal Service",
                "role": "service"
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal service key."
        )

    session_id = request.cookies.get("session_id")
    if not session_id:
        auth_hdr = request.headers.get("authorization", "")
        if auth_hdr.startswith("Bearer "):
            session_id = auth_hdr[7:].strip()

    if session_id:
        user = db.get_session_user(session_id)
        if user:
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or is invalid. Please sign in again."
        )

    if settings.is_production():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in."
        )

    return {
        "id": "anonymous_reader",
        "email": "anon@local.test",
        "display_name": "Anonymous Dev Reader",
        "role": "user"
    }

def require_user_account(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Dependency that guarantees the caller is an authenticated human user account,
    not an internal service key. Used for user-owned resources (settings, profile, sitemaps, etc.).
    """
    if user.get("role") == "service" or user.get("id") == "service_internal":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Internal service keys are not authorized to access user account data."
        )
    return user

def verify_csrf(request: Request, user: Dict[str, Any] = Depends(get_current_user)):
    """
    CSRF verification for state-changing browser operations authenticated via session cookie.
    Validates X-CSRF-Token header against user session CSRF token or csrf_token cookie.
    Bypassed for internal service calls or Authorization Bearer header auth.
    """
    # Internal service calls do not use browser cookies; CSRF not applicable
    if user.get("role") == "service" or user.get("id") == "service_internal":
        return

    # If authenticated via Authorization Bearer header rather than cookie, CSRF is not applicable
    if not request.cookies.get("session_id") and request.headers.get("authorization"):
        return

    csrf_header = request.headers.get("x-csrf-token")
    expected_csrf = user.get("csrf_token") or request.cookies.get("csrf_token")

    if not csrf_header or not expected_csrf or not secrets.compare_digest(csrf_header, expected_csrf):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token validation failed. Please refresh the page and try again."
        )

# -------------------------------------------------------------
# Background Daily Sync Loop
# -------------------------------------------------------------
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
    # Log database migration status on startup
    logger.info(f"Knowledge Brain started. Database initialized at {settings.knowledge_db_path}.")
    if settings.enable_background_sync:
        scheduler.start()
        logger.info("Background SitemapScheduler started.")
    else:
        logger.info("Background sitemap scheduler is disabled by configuration (test/local mode).")
    try:
        yield
    finally:
        await scheduler.stop()
        if _daily_sync_task and not _daily_sync_task.done():
            _daily_sync_task.cancel()
            try:
                await _daily_sync_task
            except asyncio.CancelledError:
                pass

app = FastAPI(
    title="AI Tech Consultant - Knowledge Brain API",
    version="2.3.0",
    description="Production-hardened self-evolving product memory, authentication, and hybrid RAG service.",
    lifespan=lifespan
)

# Structured Request ID & Logging Middleware
@app.middleware("http")
async def request_id_and_logging_middleware(request: Request, call_next):
    req_id = request.headers.get("x-request-id") or str(uuid.uuid4())[:8]
    request.state.request_id = req_id
    start_time = time.time()
    
    # Process request
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000.0
    
    # Safe request logging without exposing secrets
    response.headers["X-Request-ID"] = req_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"

    # Only log paths, methods, and status codes (never request bodies with passwords)
    logger.info(f"[{req_id}] {request.method} {request.url.path} -> {response.status_code} ({duration_ms:.1f}ms)")
    return response

# Explicit CORS configuration (No wildcard with credentials)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-CSRF-Token", "Set-Cookie"],
)

# -------------------------------------------------------------
# Health and Diagnostics Endpoints (Public)
# -------------------------------------------------------------
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
            "environment": settings.environment
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")

@app.get("/")
def root():
    return {
        "service": "Knowledge Brain API",
        "status": "online",
        "version": "2.3.0",
        "health_check": "/health",
        "docs_url": "/docs"
    }

# -------------------------------------------------------------
# Authentication Endpoints
# -------------------------------------------------------------
@app.post("/api/v1/auth/register")
def register_user(req: RegisterRequest, response: Response):
    # 1. Validation
    try:
        clean_email = validate_email(req.email)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    is_strong, reason = validate_password_strength(req.password)
    if not is_strong:
        raise HTTPException(status_code=400, detail=reason or "Password does not meet security requirements.")

    # 2. Check existing user
    existing = db.get_user_by_email(clean_email)
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    # 3. Secure Argon2id password hashing
    hashed = hash_password(req.password)
    user = db.create_user(
        email=clean_email,
        password_hash=hashed,
        display_name=req.display_name or clean_email.split("@")[0]
    )

    # 4. Create session and CSRF token
    session_id, csrf = db.create_session(user["id"], expires_in_seconds=86400 * settings.session_expiry_days)
    
    # 5. Set secure HTTP-only cookie
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=settings.is_production(),
        max_age=86400 * settings.session_expiry_days,
        path="/"
    )
    # Set accessible CSRF cookie for client-side inclusion in headers
    response.set_cookie(
        key="csrf_token",
        value=csrf,
        httponly=False,
        samesite="lax",
        secure=settings.is_production(),
        max_age=86400 * settings.session_expiry_days,
        path="/"
    )

    logger.info(f"Audit: New user registered: {user['id']}")
    safe_user = {"id": user["id"], "email": user["email"], "display_name": user["display_name"], "role": user["role"]}
    return {"status": "success", "user": safe_user, "csrf_token": csrf}

@app.post("/api/v1/auth/login")
def login_user(req: LoginRequest, request: Request, response: Response):
    client_ip = request.client.host if request.client else "unknown"

    # 1. Rate limiting checks
    if not check_ip_rate_limit(client_ip):
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts from this network. Please wait 15 minutes before trying again."
        )

    is_locked, locked_until = db.is_account_locked(req.email)
    if is_locked:
        logger.warning(f"Login attempted on locked account: {req.email[:3]}***")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account is temporarily locked due to repeated failed login attempts. Please try again later."
        )

    # 2. Authenticate
    user = db.get_user_by_email(req.email)
    is_valid = False
    needs_rehash = False

    if user and "password_hash" in user:
        is_valid, needs_rehash = verify_and_check_rehash(req.password, user["password_hash"])

    if not is_valid or not user:
        record_ip_failure(client_ip)
        lock_status = db.record_failed_login(
            req.email,
            limit=settings.failed_login_limit,
            lockout_minutes=settings.lockout_duration_minutes
        )
        logger.warning(f"Audit: Failed login attempt for user: {req.email[:3]}*** from IP {client_ip}")
        if lock_status.get("locked"):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Account locked due to {settings.failed_login_limit} consecutive failed attempts. Please wait {settings.lockout_duration_minutes} minutes."
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    # 3. Successful login - rehash legacy password to Argon2id if needed
    if needs_rehash:
        try:
            new_hash = hash_password(req.password)
            db.update_password_hash(user["id"], new_hash)
            logger.info(f"Audit: Upgraded password hash to Argon2id for user: {user['id']}")
        except Exception as e:
            logger.warning(f"Failed to auto-upgrade hash for user {user['id']}: {e}")

    # 4. Reset failed attempts
    db.reset_failed_logins(user["id"])

    # 5. Create session
    session_id, csrf = db.create_session(user["id"], expires_in_seconds=86400 * settings.session_expiry_days)

    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=settings.is_production(),
        max_age=86400 * settings.session_expiry_days,
        path="/"
    )
    response.set_cookie(
        key="csrf_token",
        value=csrf,
        httponly=False,
        samesite="lax",
        secure=settings.is_production(),
        max_age=86400 * settings.session_expiry_days,
        path="/"
    )

    logger.info(f"Audit: User logged in: {user['id']}")
    user_data = {
        "id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"],
        "role": user["role"]
    }
    return {"status": "success", "user": user_data, "csrf_token": csrf}

@app.post("/api/v1/auth/demo-login")
def demo_login(response: Response):
    """
    Separate development and demo login capability.
    Disabled in production mode.
    """
    if not settings.demo_auth_enabled or settings.is_production():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo authentication is disabled in production mode."
        )

    demo_email = settings.demo_user_email
    user = db.get_user_by_email(demo_email)
    if not user:
        hashed = hash_password(settings.demo_user_password)
        user = db.create_user(
            email=demo_email,
            password_hash=hashed,
            display_name="Demo Consultant",
            role="user"
        )

    session_id, csrf = db.create_session(user["id"], expires_in_seconds=86400 * settings.session_expiry_days)
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=settings.is_production(),
        max_age=86400 * settings.session_expiry_days,
        path="/"
    )
    response.set_cookie(
        key="csrf_token",
        value=csrf,
        httponly=False,
        samesite="lax",
        secure=settings.is_production(),
        max_age=86400 * settings.session_expiry_days,
        path="/"
    )

    logger.info(f"Audit: Demo user authenticated: {user['id']}")
    user_data = {
        "id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"],
        "role": user["role"]
    }
    return {"status": "success", "user": user_data, "csrf_token": csrf}

@app.post("/api/v1/auth/logout")
def logout_user(request: Request, response: Response):
    session_id = request.cookies.get("session_id")
    if session_id:
        db.delete_session(session_id)
    response.delete_cookie(key="session_id", path="/")
    response.delete_cookie(key="csrf_token", path="/")
    return {"status": "success", "message": "Logged out successfully"}

@app.get("/api/v1/auth/me")
def get_me(user: Dict[str, Any] = Depends(require_user_account)):
    safe_user = {
        "id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"],
        "role": user["role"]
    }
    return {"user": safe_user, "csrf_token": user.get("csrf_token", "")}

# -------------------------------------------------------------
# User Settings Endpoints (Aligned: supports GET, POST, and PUT)
# -------------------------------------------------------------
@app.get("/api/v1/settings", response_model=UserSettings)
def get_settings(user: Dict[str, Any] = Depends(require_user_account)):
    return db.get_user_settings(user_id=user["id"])

@app.post("/api/v1/settings", response_model=UserSettings)
def update_settings_post(
    req: UserSettings,
    user: Dict[str, Any] = Depends(require_user_account),
    _csrf: None = Depends(verify_csrf)
):
    req.user_id = user["id"]
    db.save_user_settings(req)
    return req

@app.put("/api/v1/settings", response_model=UserSettings)
def update_settings_put(
    req: UserSettings,
    user: Dict[str, Any] = Depends(require_user_account),
    _csrf: None = Depends(verify_csrf)
):
    """Frontend compatibility endpoint (resolves PUT /api/v1/settings mismatch)."""
    req.user_id = user["id"]
    db.save_user_settings(req)
    return req

# -------------------------------------------------------------
# Sitemap Management Endpoints (Strictly user-isolated)
# -------------------------------------------------------------
@app.post("/api/v1/sitemaps/preview", response_model=SitemapPreview)
async def preview_sitemap(
    req: PreviewRequest,
    user: Dict[str, Any] = Depends(require_user_account),
    _csrf: None = Depends(verify_csrf)
):
    validate_url_ssrf_safe(req.url)
    return await crawler.preview_sitemap(req.url)

@app.post("/api/v1/sitemaps", response_model=SitemapItem)
def create_sitemap(
    req: SitemapCreate,
    user: Dict[str, Any] = Depends(require_user_account),
    _csrf: None = Depends(verify_csrf)
):
    validate_url_ssrf_safe(req.url)
    days = req.refresh_interval_days or 1
    if req.refresh_interval:
        mapping = {"daily": 1, "weekly": 7, "biweekly": 15, "monthly": 30}
        days = mapping.get(str(req.refresh_interval).lower(), days)
    try:
        return db.create_sitemap(
            root_url=req.url,
            name=req.name or req.url,
            user_id=user["id"],
            refresh_interval_days=days
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(ve)
        )

@app.get("/api/v1/sitemaps/duplicates")
def get_duplicate_sitemaps(user: Dict[str, Any] = Depends(require_user_account)):
    """Returns detected duplicate sitemap registrations for the authenticated user or all (if admin)."""
    return db.get_duplicate_sitemaps(user_id=user["id"])

@app.get("/api/v1/sitemaps/reconciliation-plan")
def get_sitemap_reconciliation_plan(user: Dict[str, Any] = Depends(require_user_account)):
    """Returns non-destructive dry-run reconciliation plan for historical duplicates."""
    return db.get_dry_run_reconciliation_plan()

@app.get("/api/v1/sitemaps", response_model=List[SitemapItem])
def list_sitemaps(user: Dict[str, Any] = Depends(require_user_account)):
    return db.get_sitemaps(user_id=user["id"])

@app.get("/api/v1/sitemaps/estimate")
def get_sitemap_indexing_estimate(user: Dict[str, Any] = Depends(require_user_account)):
    estimate = crawler.throughput_tracker.get_estimate(total_remaining=0)
    data = estimate.model_dump()
    data["observed_pages_per_5min"] = estimate.pages_processed_5min
    data["estimated_pages_per_hour"] = int(estimate.observed_throughput_pages_per_min * 60)
    data["formatted_estimate"] = estimate.estimated_completion_time_human
    data["is_estimate_only"] = True
    data["notes"] = estimate.disclaimer
    return data

@app.get("/api/v1/sitemaps/{sitemap_id}", response_model=SitemapItem)
def get_sitemap_detail(sitemap_id: str, user: Dict[str, Any] = Depends(require_user_account)):
    sm = db.get_sitemap(sitemap_id, user_id=user["id"])
    if not sm:
        raise HTTPException(status_code=404, detail="Sitemap not found")
    return sm

@app.delete("/api/v1/sitemaps/{sitemap_id}")
def delete_sitemap(
    sitemap_id: str,
    user: Dict[str, Any] = Depends(require_user_account),
    _csrf: None = Depends(verify_csrf)
):
    """User-isolated sitemap removal endpoint."""
    deleted = db.delete_sitemap(sitemap_id, user_id=user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Sitemap not found or access denied")
    return {"status": "success", "message": f"Sitemap {sitemap_id} deleted"}

@app.post("/api/v1/sitemaps/{sitemap_id}/confirm")
def confirm_sitemap_for_indexing(
    sitemap_id: str,
    user: Dict[str, Any] = Depends(require_user_account),
    _csrf: None = Depends(verify_csrf)
):
    confirmed = db.confirm_sitemap(sitemap_id, user_id=user["id"])
    if not confirmed:
        raise HTTPException(status_code=404, detail="Sitemap not found")
    return {"status": "confirmed", "message": f"Sitemap {sitemap_id} confirmed for scheduled indexing"}

@app.post("/api/v1/sitemaps/{sitemap_id}/confirm-index", response_model=RefreshRunSummary)
async def confirm_and_begin_indexing(
    sitemap_id: str,
    max_pages: Optional[int] = Query(None, description="Limit crawl slice for testing"),
    sync: bool = Query(False, description="Wait synchronously until crawl completes"),
    user: Dict[str, Any] = Depends(require_user_account),
    _csrf: None = Depends(verify_csrf)
):
    sm = db.get_sitemap(sitemap_id, user_id=user["id"])
    if not sm:
        raise HTTPException(status_code=404, detail="Sitemap not found")
    db.confirm_sitemap(sitemap_id, user_id=user["id"])

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
def get_sitemap_relationships(sitemap_id: str, user: Dict[str, Any] = Depends(require_user_account)):
    sm = db.get_sitemap(sitemap_id, user_id=user["id"])
    if not sm:
        raise HTTPException(status_code=404, detail="Sitemap not found")
    return db.get_sitemap_relationships(sitemap_id)

# -------------------------------------------------------------
# Refresh Runs & History Endpoints (Strictly user-isolated)
# -------------------------------------------------------------
@app.post("/api/v1/sitemaps/{sitemap_id}/refresh", response_model=RefreshRunSummary)
@app.post("/api/v1/sitemaps/{sitemap_id}/trigger-refresh", response_model=RefreshRunSummary)
async def trigger_sitemap_refresh(
    sitemap_id: str,
    max_pages: Optional[int] = Query(None, description="Limit crawl slice for testing"),
    force: bool = Query(False, description="Force re-chunking and re-embedding"),
    sync: bool = Query(False, description="Wait synchronously until crawl completes"),
    user: Dict[str, Any] = Depends(require_user_account),
    _csrf: None = Depends(verify_csrf)
):
    sm = db.get_sitemap(sitemap_id, user_id=user["id"])
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

@app.put("/api/v1/sitemaps/{sitemap_id}/schedule", response_model=SitemapItem)
def update_sitemap_schedule(
    sitemap_id: str,
    req: ScheduleUpdateRequest,
    user: Dict[str, Any] = Depends(require_user_account),
    _csrf: None = Depends(verify_csrf)
):
    if req.refresh_interval_days is not None and req.refresh_interval_days not in (1, 7, 15, 30):
        raise HTTPException(status_code=400, detail="Invalid refresh interval. Supported intervals: 1, 7, 15, 30 days.")
    if req.schedule_status is not None and req.schedule_status not in ("active", "paused", "disabled"):
        raise HTTPException(status_code=400, detail="Invalid schedule status. Supported: active, paused, disabled.")
    
    updated = db.update_sitemap_schedule(
        sitemap_id=sitemap_id,
        refresh_interval_days=req.refresh_interval_days,
        schedule_status=req.schedule_status,
        next_refresh_at=req.next_refresh_at,
        user_id=user["id"]
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Sitemap not found or access denied.")
    return updated

@app.get("/api/v1/scheduler/status", response_model=SchedulerStatusResponse)
def get_scheduler_status(user: Dict[str, Any] = Depends(require_user_account)):
    return scheduler.get_status()

@app.post("/api/v1/sitemaps/{sitemap_id}/refresh-now", response_model=RefreshRunSummary)
async def manual_refresh_now(
    sitemap_id: str,
    force: bool = Query(False),
    user: Dict[str, Any] = Depends(require_user_account),
    _csrf: None = Depends(verify_csrf)
):
    sm = db.get_sitemap(sitemap_id, user_id=user["id"])
    if not sm:
        raise HTTPException(status_code=404, detail="Sitemap not found or access denied.")
    return await scheduler.trigger_refresh_now(sitemap_id=sitemap_id, user_id=user["id"], force=force)

@app.get("/api/v1/refresh-runs", response_model=List[RefreshRunSummary])
def list_refresh_runs(
    sitemap_id: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    user: Dict[str, Any] = Depends(require_user_account)
):
    return db.get_refresh_runs(user_id=user["id"], sitemap_id=sitemap_id, limit=limit)

@app.get("/api/v1/refresh-runs/{run_id}", response_model=RefreshRunDetail)
def get_refresh_run_detail(
    run_id: str,
    search: Optional[str] = Query(None, description="Filter URLs by search substring"),
    status: Optional[str] = Query(None, description="Filter URLs by status"),
    limit: int = Query(200, le=1000),
    offset: int = Query(0, ge=0),
    user: Dict[str, Any] = Depends(require_user_account)
):
    detail = db.get_refresh_run_detail(
        run_id=run_id,
        user_id=user["id"],
        search=search,
        status_filter=status,
        limit=limit,
        offset=offset
    )
    if not detail:
        raise HTTPException(status_code=404, detail="Refresh run not found")
    return detail

# -------------------------------------------------------------
# URL Health & Quarantine Endpoints (Strictly user-isolated)
# -------------------------------------------------------------
@app.get("/api/v1/health-observations", response_model=List[URLHealthStatus])
def list_url_health_statuses(
    sitemap_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="healthy, unhealthy, pending, 404, 301"),
    search: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    user: Dict[str, Any] = Depends(require_user_account)
):
    items, total = db.get_url_health_statuses(
        user_id=user["id"],
        sitemap_id=sitemap_id,
        status_filter=status,
        search=search,
        limit=limit,
        offset=offset
    )
    return items

@app.post("/api/v1/health-observations/cancel-pending")
def cancel_pending_action_body(
    req: Dict[str, str],
    user: Dict[str, Any] = Depends(require_user_account),
    _csrf: None = Depends(verify_csrf)
):
    url = req.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required.")
    success = db.cancel_pending_url_action(url, user_id=user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="URL health record not found or access denied.")
    return {"status": "success", "message": f"Cancelled pending action for {url}"}

@app.post("/api/v1/health-observations/{url:path}/cancel-pending")
def cancel_pending_action_path(
    url: str,
    user: Dict[str, Any] = Depends(require_user_account),
    _csrf: None = Depends(verify_csrf)
):
    success = db.cancel_pending_url_action(url, user_id=user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="URL health record not found or access denied.")
    return {"status": "success", "message": f"Cancelled pending action for {url}"}

@app.post("/api/v1/health-observations/{url:path}/reverify")
async def reverify_url_endpoint(
    url: str,
    user: Dict[str, Any] = Depends(require_user_account),
    _csrf: None = Depends(verify_csrf)
):
    import httpx
    async with httpx.AsyncClient(timeout=10.0) as client:
        red_res = await crawler.resolve_redirect_lifecycle(client, url, max_hops=5)
        st = red_res.get("initial_status") or 500
        is_ok = red_res.get("success") and st == 200
        health = db.update_url_health(
            url=url,
            http_status=st,
            is_in_sitemap=True,
            content_valid=is_ok,
            user_id=user["id"],
            error_reason=red_res.get("reason")
        )
        return health

@app.get("/api/v1/quarantine", response_model=List[QuarantineRecord])
def list_quarantined_articles(user: Dict[str, Any] = Depends(require_user_account)):
    return db.get_quarantined_articles(user_id=user["id"])

@app.post("/api/v1/quarantine/restore")
def restore_quarantined_article_body(
    req: QuarantineRestoreRequest,
    user: Dict[str, Any] = Depends(require_user_account),
    _csrf: None = Depends(verify_csrf)
):
    """Restores a quarantined article by body URL or ID."""
    target = req.url or req.id
    if not target:
        raise HTTPException(status_code=400, detail="Either 'url' or 'id' is required in request body.")
    restored = db.restore_quarantined_article(target, user_id=user["id"])
    if not restored:
        raise HTTPException(status_code=404, detail="Quarantined record not found or access denied.")
    return {"status": "success", "message": f"Successfully restored {target} to active knowledge"}

@app.post("/api/v1/quarantine/{item_id}/restore")
def restore_quarantined_article_path(
    item_id: str,
    user: Dict[str, Any] = Depends(require_user_account),
    _csrf: None = Depends(verify_csrf)
):
    """Frontend-compatible restore endpoint (resolves POST /api/v1/quarantine/{id}/restore mismatch)."""
    restored = db.restore_quarantined_article(item_id, user_id=user["id"])
    if not restored:
        raise HTTPException(status_code=404, detail="Quarantined record not found or access denied.")
    return {"status": "success", "success": True, "article_id": item_id, "message": f"Successfully restored {item_id}"}

# -------------------------------------------------------------
# Phase F & G: Archived Knowledge Base Endpoints
# -------------------------------------------------------------
@app.get("/api/v1/archive", response_model=List[ArchivedArticleItem])
def list_archived_articles(
    sitemap_id: Optional[str] = Query(None),
    reason: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    user: Dict[str, Any] = Depends(require_user_account)
):
    items, total = db.get_archived_articles(
        user_id=user["id"],
        sitemap_id=sitemap_id,
        reason=reason,
        search=search,
        limit=limit,
        offset=offset
    )
    return items

@app.get("/api/v1/archive/{item_id}", response_model=ArchivedArticleDetail)
def get_archived_article_detail(
    item_id: str,
    user: Dict[str, Any] = Depends(require_user_account)
):
    detail = db.get_archived_article_detail(id_or_url=item_id, user_id=user["id"])
    if not detail:
        raise HTTPException(status_code=404, detail="Archived article not found or access denied.")
    return detail

@app.post("/api/v1/archive/{item_id}/restore")
def restore_archived_article(
    item_id: str,
    user: Dict[str, Any] = Depends(require_user_account),
    _csrf: None = Depends(verify_csrf)
):
    restored = db.restore_archived_article(id_or_url=item_id, user_id=user["id"])
    if not restored:
        raise HTTPException(status_code=404, detail="Archived article not found or access denied.")
    return {"status": "success", "message": f"Successfully restored {item_id} to active knowledge base."}

@app.put("/api/v1/archive/{item_id}/retention")
def update_archive_retention(
    item_id: str,
    req: ArchiveRetentionUpdateRequest,
    user: Dict[str, Any] = Depends(require_user_account),
    _csrf: None = Depends(verify_csrf)
):
    if req.retention_preset not in ("2d", "15d", "30d", "custom"):
        raise HTTPException(status_code=400, detail="Invalid retention preset. Supported: 2d, 15d, 30d, custom.")
    days = req.retention_days or (2 if req.retention_preset == "2d" else 15 if req.retention_preset == "15d" else 30)
    updated = db.update_archive_retention(
        id_or_url=item_id,
        retention_preset=req.retention_preset,
        retention_days=days,
        user_id=user["id"]
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Archived article not found or access denied.")
    return {"status": "success", "retention_preset": req.retention_preset, "retention_days": days}

# -------------------------------------------------------------
# Phase E: Redirect Relationships Endpoints
# -------------------------------------------------------------
@app.get("/api/v1/redirects", response_model=List[ArticleRedirectItem])
def list_article_redirects(
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    user: Dict[str, Any] = Depends(require_user_account)
):
    return db.get_article_redirects(user_id=user["id"], limit=limit, offset=offset)

# -------------------------------------------------------------
# Phase H: Article Version History Endpoints
# -------------------------------------------------------------
@app.get("/api/v1/article-history/diff")
def get_article_history_diff(
    v1: str = Query(..., description="First version ID"),
    v2: str = Query(..., description="Second version ID"),
    user: Dict[str, Any] = Depends(require_user_account)
):
    diff = db.get_article_version_diff(version_id_1=v1, version_id_2=v2)
    if "error" in diff:
        raise HTTPException(status_code=404, detail=diff["error"])
    return diff

@app.get("/api/v1/articles/{url:path}/history", response_model=List[ArticleHistoryItem])
def get_article_version_history(
    url: str,
    user: Dict[str, Any] = Depends(require_user_account)
):
    return db.get_article_versions(url=url, user_id=user["id"])

# -------------------------------------------------------------
# Core Knowledge RAG Endpoints (Secure internal/user service)
# -------------------------------------------------------------
@app.post("/api/v1/search", response_model=List[SearchResult])
def search_knowledge(
    req: SearchRequest,
    caller: Optional[Dict[str, Any]] = Depends(get_current_user_or_internal)
):
    return rag_engine.search(query=req.query, top_k=req.top_k, category=req.category)

@app.post("/api/v1/ask", response_model=AskResponse)
async def ask_question(
    req: AskRequest,
    model: Optional[str] = Query(None, description="Claude model identifier"),
    caller: Optional[Dict[str, Any]] = Depends(get_current_user_or_internal)
):
    """
    Executes hybrid RAG retrieval and answer synthesis.
    Preserves full compatibility for internal Task 2 and Task 3 service requests.
    """
    return await rag_engine.ask(request=req, model=model)

@app.post("/api/v1/sync", response_model=SyncReport)
async def trigger_sync(
    max_pages: Optional[int] = Query(None, description="Limit crawl slice for test runs"),
    force: bool = Query(False, description="Force re-processing and re-embedding of articles even if content hash is unchanged"),
    user: Dict[str, Any] = Depends(get_current_user),
    _csrf: None = Depends(verify_csrf)
):
    return await crawler.sync_daily(max_pages=max_pages, force=force)

@app.get("/api/v1/sync/status", response_model=SyncStatus)
def get_sync_status(caller: Optional[Dict[str, Any]] = Depends(get_current_user_or_internal)):
    return db.get_sync_status()

@app.get("/api/v1/articles")
def list_active_articles(
    limit: int = Query(100, le=500),
    caller: Optional[Dict[str, Any]] = Depends(get_current_user_or_internal)
):
    return db.get_active_articles(limit=limit)

@app.get("/api/v1/articles/urls", response_model=List[str])
def list_active_article_urls(
    caller: Optional[Dict[str, Any]] = Depends(get_current_user_or_internal)
):
    return db.get_all_active_urls()

@app.delete("/api/v1/articles")
def remove_article(
    url: str = Query(..., description="Article URL to remove"),
    user: Dict[str, Any] = Depends(get_current_user),
    _csrf: None = Depends(verify_csrf)
):
    db.mark_article_removed(url)
    return {"status": "success", "message": f"Article {url} removed from active memory"}

@app.get("/api/v1/expert-tasks", response_model=List[ExpertTask])
def get_expert_tasks(
    status: Optional[str] = Query(None),
    caller: Optional[Dict[str, Any]] = Depends(get_current_user_or_internal)
):
    return db.get_expert_tasks(status=status)

@app.post("/api/v1/expert-tasks/{task_id}/resolve", response_model=ExpertTask)
def resolve_expert_task(
    task_id: str,
    body: ExpertTaskResolve,
    user: Dict[str, Any] = Depends(get_current_user),
    _csrf: None = Depends(verify_csrf)
):
    resolved = db.resolve_expert_task(
        task_id=task_id,
        expert_answer=body.expert_answer,
        expert_id=body.expert_id or user.get("display_name") or "expert_reviewer",
        version=body.version or "1.0",
        provenance_notes=body.provenance_notes or "Manual product specialist review"
    )
    if not resolved:
        raise HTTPException(status_code=404, detail="Expert task not found")
    return resolved

@app.get("/api/v1/ai/models/status", response_model=AIModelStatusResponse)
def get_ai_models_status(
    caller: Optional[Dict[str, Any]] = Depends(get_current_user_or_internal)
):
    from app.fallback_engine import ModelFallbackEngine, ESTIMATED_COST_PER_1K_TOKENS
    roles_def = [
        ("KNOWLEDGE_ANSWER", "gemini-3.5-flash", 0.2),
        ("EMAIL_CLASSIFICATION", "gemini-3.5-flash", 0.0),
        ("EMAIL_DRAFTING", "gemini-3.5-flash", 0.3),
        ("REQUIREMENTS_EXTRACTION", "claude-haiku-5-5", 0.1),
        ("CAPABILITY_CHECKING", "gemini-3.5-flash", 0.0),
    ]
    items = []
    for role_name, default_model, temp in roles_def:
        engine = ModelFallbackEngine(role=role_name)
        candidates = engine.get_model_candidates()
        primary = candidates[0][1] if candidates else default_model
        provider = candidates[0][0] if candidates else "google"
        fallbacks = [c[1] for c in candidates[1:]]
        cost = ESTIMATED_COST_PER_1K_TOKENS.get(primary, 0.0001)

        has_key = bool(engine.gemini_api_key if provider == "google" else engine.anthropic_api_key)
        status_val = "CONFIGURED" if has_key else "DEGRADED"

        items.append(ModelRoleStatusItem(
            role=role_name,
            primary_model=primary,
            fallback_models=fallbacks,
            timeout_seconds=engine.total_timeout_seconds,
            max_attempts=engine.max_attempts,
            availability_status=status_val,
            provider=provider,
            temperature=temp,
            supports_structured_output=True,
            last_successful_invocation=None,
            estimated_cost_per_1k_tokens=cost
        ))

    return AIModelStatusResponse(
        roles=items,
        spending_limit_usd=float(os.getenv("MONTHLY_SPEND_LIMIT_USD", "50.0")),
        current_estimated_spend_usd=0.0,
        system_status="OPERATIONAL"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

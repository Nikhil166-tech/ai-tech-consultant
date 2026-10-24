import sqlite3
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from app.models import (
    Article, ArticleChunk, ImageMetadata, ExpertTask, SyncStatus, SyncReport,
    SitemapItem, SitemapPreview, RefreshRunSummary, RefreshRunDetail, RefreshRunUrlItem,
    QuarantineRecord, QuarantineReason, URLHealthStatus, UserSettings, IndexingEstimate
)

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 3

def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()

class Database:
    def __init__(self, db_path: str = "knowledge_brain.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=60.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=60000")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Articles table with content_hash
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT DEFAULT 'General',
                folder TEXT DEFAULT 'General',
                body_text TEXT NOT NULL,
                content_hash TEXT,
                images_json TEXT DEFAULT '[]',
                last_modified TEXT,
                etag TEXT,
                status TEXT DEFAULT 'active',
                crawled_at TEXT
            )
            """)

            # Chunks table with section_heading, images_json, source_type and provenance
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                article_url TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT DEFAULT 'General',
                folder TEXT DEFAULT 'General',
                section_heading TEXT DEFAULT 'Overview',
                chunk_index INTEGER,
                text TEXT NOT NULL,
                visual_context TEXT DEFAULT '',
                images_json TEXT DEFAULT '[]',
                embedding_json TEXT DEFAULT '[]',
                source_type TEXT DEFAULT 'OFFICIAL_DOC',
                provenance_notes TEXT,
                FOREIGN KEY (article_url) REFERENCES articles(url) ON DELETE CASCADE
            )
            """)

            # Crawler checkpoint table with content_hash
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS crawler_checkpoint (
                url TEXT PRIMARY KEY,
                last_checked TEXT,
                status_code INTEGER,
                etag TEXT,
                last_modified TEXT,
                content_hash TEXT,
                error TEXT
            )
            """)

            # Expert Fallback Task Queue with provenance
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS expert_tasks (
                id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                context TEXT DEFAULT '',
                requester_email TEXT,
                status TEXT DEFAULT 'pending',
                expert_answer TEXT,
                expert_id TEXT,
                version TEXT DEFAULT '1.0',
                provenance_notes TEXT,
                created_at TEXT,
                resolved_at TEXT
            )
            """)

            # Sync Job Status Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_state (
                key TEXT PRIMARY KEY,
                value_json TEXT,
                updated_at TEXT
            )
            """)

            # -------------------------------------------------------------
            # Phase 2: Sitemaps & Relationships
            # -------------------------------------------------------------
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS sitemaps (
                id TEXT PRIMARY KEY,
                user_id TEXT DEFAULT 'default_user',
                root_url TEXT NOT NULL,
                name TEXT NOT NULL,
                refresh_interval_days INTEGER DEFAULT 1,
                status TEXT DEFAULT 'registered',
                last_preview_json TEXT,
                last_confirmed_at TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS sitemap_relationships (
                id TEXT PRIMARY KEY,
                root_sitemap_id TEXT NOT NULL,
                sitemap_url TEXT NOT NULL,
                parent_sitemap_url TEXT,
                depth INTEGER DEFAULT 0,
                is_index INTEGER DEFAULT 0,
                error TEXT,
                created_at TEXT
            )
            """)

            # -------------------------------------------------------------
            # Phase 3: Refresh Runs & Per-URL Tracking
            # -------------------------------------------------------------
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS sitemap_refresh_runs (
                id TEXT PRIMARY KEY,
                sitemap_id TEXT NOT NULL,
                user_id TEXT DEFAULT 'default_user',
                started_at TEXT NOT NULL,
                first_successful_fetch_at TEXT,
                last_successful_fetch_at TEXT,
                completed_at TEXT,
                total_discovered_urls INTEGER DEFAULT 0,
                total_successfully_fetched_urls INTEGER DEFAULT 0,
                added_count INTEGER DEFAULT 0,
                updated_count INTEGER DEFAULT 0,
                unchanged_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                pending_count INTEGER DEFAULT 0,
                quarantined_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running',
                progress_percent REAL DEFAULT 0.0,
                estimate_json TEXT
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS refresh_run_urls (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                url TEXT NOT NULL,
                status TEXT NOT NULL,
                http_status INTEGER,
                lastmod TEXT,
                fetched_at TEXT,
                error_message TEXT
            )
            """)

            # -------------------------------------------------------------
            # Phase 4: URL Health Observations, Counters & Quarantine Storage
            # -------------------------------------------------------------
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS url_health_status (
                url TEXT PRIMARY KEY,
                sitemap_id TEXT,
                consecutive_failure_count INTEGER DEFAULT 0,
                configured_threshold INTEGER DEFAULT 3,
                expected_action TEXT DEFAULT 'Quarantine on 3 consecutive failures',
                last_checked_at TEXT,
                last_http_status INTEGER,
                is_in_sitemap INTEGER DEFAULT 1,
                failure_reason TEXT
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS url_health_observations (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                sitemap_id TEXT,
                run_id TEXT,
                http_status INTEGER,
                redirect_url TEXT,
                is_in_sitemap INTEGER DEFAULT 1,
                observed_at TEXT,
                error_reason TEXT
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS quarantine_records (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL UNIQUE,
                sitemap_id TEXT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                chunks_json TEXT DEFAULT '[]',
                embeddings_json TEXT DEFAULT '[]',
                last_known_http_status INTEGER,
                quarantine_reason TEXT NOT NULL,
                replacement_url TEXT,
                detected_at TEXT,
                quarantined_at TEXT,
                restored_at TEXT,
                sitemap_presence_history_json TEXT DEFAULT '[]'
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id TEXT PRIMARY KEY,
                sitemap_refresh_interval_days INTEGER DEFAULT 1,
                url_quarantine_threshold_x INTEGER DEFAULT 3,
                url_quarantine_action TEXT DEFAULT 'QUARANTINE_ON_CONSECUTIVE_FAILURES',
                email_approval_threshold_x INTEGER DEFAULT 3,
                auto_send_enabled INTEGER DEFAULT 0,
                emergency_disable INTEGER DEFAULT 0,
                updated_at TEXT
            )
            """)

            # -------------------------------------------------------------
            # Phase 6: Authentication & Sessions
            # -------------------------------------------------------------
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                role TEXT DEFAULT 'user',
                created_at TEXT
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT
            )
            """)
            
            # Run migrations first so any missing legacy columns exist before indexing
            self._apply_migrations(cursor)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_url ON chunks(article_url)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_run_urls_run_id ON refresh_run_urls(run_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_health_obs_url ON url_health_observations(url)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_quarantine_url ON quarantine_records(url)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sitemaps_user ON sitemaps(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_refresh_runs_sitemap ON sitemap_refresh_runs(sitemap_id)")
            conn.commit()

    def _apply_migrations(self, cursor: sqlite3.Cursor):
        """Ensures previous database schemas cannot silently break the new version."""
        cursor.execute("PRAGMA user_version")
        row = cursor.fetchone()
        version = row[0] if row else 0

        def ensure_column(table: str, col_name: str, col_type: str):
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [c[1] for c in cursor.fetchall()]
            if col_name not in columns:
                logger.info(f"Migrating schema: Adding {col_name} ({col_type}) to table {table}")
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")

        # Ensure articles columns
        ensure_column("articles", "category", "TEXT DEFAULT 'General'")
        ensure_column("articles", "folder", "TEXT DEFAULT 'General'")
        ensure_column("articles", "content_hash", "TEXT")
        ensure_column("articles", "images_json", "TEXT DEFAULT '[]'")
        ensure_column("articles", "last_modified", "TEXT")
        ensure_column("articles", "etag", "TEXT")
        ensure_column("articles", "status", "TEXT DEFAULT 'active'")
        ensure_column("articles", "crawled_at", "TEXT")

        # Ensure chunks columns
        ensure_column("chunks", "section_heading", "TEXT DEFAULT 'Overview'")
        ensure_column("chunks", "source_type", "TEXT DEFAULT 'OFFICIAL_DOC'")
        ensure_column("chunks", "provenance_notes", "TEXT")
        ensure_column("chunks", "images_json", "TEXT DEFAULT '[]'")
        ensure_column("chunks", "visual_context", "TEXT DEFAULT ''")
        ensure_column("chunks", "embedding_json", "TEXT DEFAULT '[]'")

        # Ensure expert_tasks columns
        ensure_column("expert_tasks", "expert_id", "TEXT")
        ensure_column("expert_tasks", "version", "TEXT DEFAULT '1.0'")
        ensure_column("expert_tasks", "provenance_notes", "TEXT")

        if version < CURRENT_SCHEMA_VERSION:
            cursor.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")

    def upsert_article(self, article: Article):
        images_json = json.dumps([img.model_dump() for img in article.images])
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO articles (url, title, category, folder, body_text, content_hash, images_json, last_modified, etag, status, crawled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title,
                category=excluded.category,
                folder=excluded.folder,
                body_text=excluded.body_text,
                content_hash=excluded.content_hash,
                images_json=excluded.images_json,
                last_modified=excluded.last_modified,
                etag=excluded.etag,
                status='active',
                crawled_at=excluded.crawled_at
            """, (
                article.url,
                article.title,
                article.category,
                article.folder,
                article.body_text,
                article.content_hash,
                images_json,
                article.last_modified,
                article.etag,
                article.status,
                article.crawled_at.isoformat()
            ))
            conn.commit()

    def delete_chunks_for_article(self, article_url: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chunks WHERE article_url = ?", (article_url,))
            conn.commit()

    def save_chunks(self, chunks: List[ArticleChunk]):
        if not chunks:
            return
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for chunk in chunks:
                emb_json = json.dumps(chunk.embedding or [])
                imgs_json = json.dumps([img.model_dump() for img in chunk.images])
                cursor.execute("""
                INSERT INTO chunks (id, article_url, title, category, folder, section_heading, chunk_index, text, visual_context, images_json, embedding_json, source_type, provenance_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    text=excluded.text,
                    section_heading=excluded.section_heading,
                    visual_context=excluded.visual_context,
                    images_json=excluded.images_json,
                    embedding_json=excluded.embedding_json,
                    source_type=excluded.source_type,
                    provenance_notes=excluded.provenance_notes
                """, (
                    chunk.id,
                    chunk.article_url,
                    chunk.title,
                    chunk.category,
                    chunk.folder,
                    chunk.section_heading,
                    chunk.chunk_index,
                    chunk.text,
                    chunk.visual_context,
                    imgs_json,
                    emb_json,
                    chunk.source_type,
                    chunk.provenance_notes
                ))
            conn.commit()

    def update_chunk_embedding(self, chunk_id: str, embedding: List[float]):
        """Persists a regenerated embedding vector for an existing chunk (e.g. on dimension mismatch)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE chunks SET embedding_json = ? WHERE id = ?", (json.dumps(embedding), chunk_id))
            conn.commit()

    def mark_article_removed(self, url: str):
        """Preserves chunks without deleting; marks status as removed."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE articles SET status = 'removed' WHERE url = ?", (url,))
            conn.commit()

    def get_article(self, url: str) -> Optional[Article]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM articles WHERE url = ?", (url,))
            row = cursor.fetchone()
            if not row:
                return None
            images_data = json.loads(row["images_json"]) if "images_json" in row.keys() and row["images_json"] else []
            images = [ImageMetadata(**img) for img in images_data]
            crawled_val = row["crawled_at"] if "crawled_at" in row.keys() else None
            crawled = datetime.fromisoformat(crawled_val) if crawled_val else datetime.now(timezone.utc)
            return Article(
                url=row["url"],
                title=row["title"],
                category=row["category"] if "category" in row.keys() else "General",
                folder=row["folder"] if "folder" in row.keys() else "General",
                body_text=row["body_text"],
                content_hash=row["content_hash"] if "content_hash" in row.keys() else None,
                images=images,
                last_modified=row["last_modified"] if "last_modified" in row.keys() else None,
                etag=row["etag"] if "etag" in row.keys() else None,
                status=row["status"] if "status" in row.keys() else "active",
                crawled_at=crawled
            )

    def count_active_articles(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM articles WHERE status = 'active'")
            row = cursor.fetchone()
            return row[0] if row else 0

    def count_active_chunks(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT COUNT(*) FROM chunks c
            JOIN articles a ON c.article_url = a.url
            WHERE a.status = 'active'
            """)
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_all_active_urls(self) -> List[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM articles WHERE status = 'active'")
            return [row["url"] for row in cursor.fetchall()]

    def get_active_articles(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT a.url, a.title, a.category, a.folder, a.status, a.crawled_at, a.body_text,
                   (SELECT COUNT(*) FROM chunks c WHERE c.article_url = a.url) as chunks_count
            FROM articles a
            WHERE a.status = 'active'
            ORDER BY a.crawled_at DESC
            LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [
                {
                    "id": row["url"],
                    "url": row["url"],
                    "title": row["title"] or row["url"],
                    "category": row["category"] or "General",
                    "folder": row["folder"] or "General",
                    "status": row["status"] or "active",
                    "chunks_count": row["chunks_count"] or 1,
                    "crawled_at": row["crawled_at"],
                    "content": (row["body_text"] or "")[:4000],
                    "body_text": (row["body_text"] or "")[:4000]
                }
                for row in rows
            ]

    def get_all_chunks(self) -> List[ArticleChunk]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT c.* FROM chunks c
            JOIN articles a ON c.article_url = a.url
            WHERE a.status = 'active'
            """)
            chunks = []
            for row in cursor.fetchall():
                emb = json.loads(row["embedding_json"]) if "embedding_json" in row.keys() and row["embedding_json"] else []
                imgs_data = json.loads(row["images_json"]) if "images_json" in row.keys() and row["images_json"] else []
                imgs = [ImageMetadata(**img) for img in imgs_data]
                chunks.append(ArticleChunk(
                    id=row["id"],
                    article_url=row["article_url"],
                    title=row["title"],
                    category=row["category"] if "category" in row.keys() else "General",
                    folder=row["folder"] if "folder" in row.keys() else "General",
                    section_heading=row["section_heading"] if "section_heading" in row.keys() else "Overview",
                    chunk_index=row["chunk_index"] if "chunk_index" in row.keys() else 0,
                    text=row["text"],
                    visual_context=row["visual_context"] if "visual_context" in row.keys() else "",
                    images=imgs,
                    embedding=emb,
                    source_type=row["source_type"] if "source_type" in row.keys() else "OFFICIAL_DOC",
                    provenance_notes=row["provenance_notes"] if "provenance_notes" in row.keys() else None
                ))
            return chunks

    def save_crawler_checkpoint(self, url: str, status_code: int, etag: Optional[str] = None, last_modified: Optional[str] = None, content_hash: Optional[str] = None, error: Optional[str] = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO crawler_checkpoint (url, last_checked, status_code, etag, last_modified, content_hash, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                last_checked=excluded.last_checked,
                status_code=excluded.status_code,
                etag=excluded.etag,
                last_modified=excluded.last_modified,
                content_hash=excluded.content_hash,
                error=excluded.error
            """, (url, iso_now(), status_code, etag, last_modified, content_hash, error))
            conn.commit()

    def get_crawler_checkpoint(self, url: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM crawler_checkpoint WHERE url = ?", (url,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_expert_task(self, question: str, context: str = "", requester_email: Optional[str] = None) -> ExpertTask:
        task_id = str(uuid.uuid4())[:8]
        now = iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO expert_tasks (id, question, context, requester_email, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """, (task_id, question, context, requester_email, now))
            conn.commit()
        return ExpertTask(
            id=task_id,
            question=question,
            context=context,
            requester_email=requester_email,
            status="pending",
            created_at=now
        )

    def resolve_expert_task(self, task_id: str, expert_answer: str, expert_id: str = "expert_reviewer", version: str = "1.0", provenance_notes: str = "Manual product specialist review") -> Optional[ExpertTask]:
        now = iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM expert_tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                return None
            
            cursor.execute("""
            UPDATE expert_tasks 
            SET status = 'resolved', expert_answer = ?, expert_id = ?, version = ?, provenance_notes = ?, resolved_at = ?
            WHERE id = ?
            """, (expert_answer, expert_id, version, provenance_notes, now, task_id))

            q = row["question"]
            expert_chunk_id = f"expert_{task_id}"
            provenance_header = f"VERIFIED HUMAN RESOLUTION [Ticket: {task_id} | Verified by: {expert_id} | Ver: {version}]"
            
            cursor.execute("""
            INSERT INTO chunks (id, article_url, title, category, folder, section_heading, chunk_index, text, visual_context, images_json, embedding_json, source_type, provenance_notes)
            VALUES (?, ?, ?, 'Expert Knowledge', 'Verified Resolutions', 'Specialist Clarification', 0, ?, 'Human expert verified resolution', '[]', '[]', 'EXPERT_RESOLUTION', ?)
            ON CONFLICT(id) DO UPDATE SET text=excluded.text, provenance_notes=excluded.provenance_notes
            """, (
                expert_chunk_id,
                f"expert://resolution/{task_id}",
                f"Expert Answer: {q[:50]}...",
                f"{provenance_header}\nQuestion: {q}\nExpert Answer: {expert_answer}",
                provenance_notes
            ))
            cursor.execute("""
            INSERT INTO articles (url, title, category, folder, body_text, content_hash, status, crawled_at)
            VALUES (?, ?, 'Expert Knowledge', 'Verified Resolutions', ?, 'expert_hash', 'active', ?)
            ON CONFLICT(url) DO UPDATE SET body_text=excluded.body_text
            """, (
                f"expert://resolution/{task_id}",
                f"Expert Answer: {q[:50]}...",
                f"{provenance_header}\nQuestion: {q}\nExpert Answer: {expert_answer}",
                now
            ))
            conn.commit()

            return ExpertTask(
                id=task_id,
                question=row["question"],
                context=row["context"],
                requester_email=row["requester_email"],
                status="resolved",
                expert_answer=expert_answer,
                expert_id=expert_id,
                version=version,
                provenance_notes=provenance_notes,
                created_at=row["created_at"],
                resolved_at=now
            )

    def get_expert_tasks(self, status: Optional[str] = None) -> List[ExpertTask]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM expert_tasks WHERE status = ? ORDER BY created_at DESC", (status,))
            else:
                cursor.execute("SELECT * FROM expert_tasks ORDER BY created_at DESC")
            return [
                ExpertTask(
                    id=row["id"],
                    question=row["question"],
                    context=row["context"],
                    requester_email=row["requester_email"],
                    status=row["status"],
                    expert_answer=row["expert_answer"],
                    expert_id=row["expert_id"] if "expert_id" in row.keys() else None,
                    version=row["version"] if "version" in row.keys() else "1.0",
                    provenance_notes=row["provenance_notes"] if "provenance_notes" in row.keys() else None,
                    created_at=row["created_at"],
                    resolved_at=row["resolved_at"]
                ) for row in cursor.fetchall()
            ]

    def set_sync_status(self, sync_status: SyncStatus):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO sync_state (key, value_json, updated_at)
            VALUES ('latest', ?, ?)
            ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at
            """, (sync_status.model_dump_json(), iso_now()))
            conn.commit()

    def get_sync_status(self) -> SyncStatus:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value_json FROM sync_state WHERE key = 'latest'")
            row = cursor.fetchone()
            if row and row["value_json"]:
                data = json.loads(row["value_json"])
                return SyncStatus(**data)
            return SyncStatus(
                status="idle",
                current_step="No sync runs yet",
                pages_crawled=0,
                total_sitemap_urls=0,
                updated_at=iso_now()
            )

    # -------------------------------------------------------------
    # Phase 2: Sitemap Management Methods
    # -------------------------------------------------------------
    def create_sitemap(self, root_url: str, name: Optional[str] = None, user_id: str = "default_user", refresh_interval_days: int = 1) -> SitemapItem:
        sitemap_id = f"sm_{uuid.uuid4().hex[:10]}"
        now = iso_now()
        sitemap_name = name or root_url
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO sitemaps (id, user_id, root_url, name, refresh_interval_days, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'registered', ?, ?)
            """, (sitemap_id, user_id, root_url, sitemap_name, refresh_interval_days, now, now))
            conn.commit()
        return self.get_sitemap(sitemap_id)

    def recover_stale_runs(self, stale_timeout_minutes: int = 5):
        """
        Detects any refresh runs marked 'running' that have had no updates in more than
        stale_timeout_minutes (caused when the background worker is interrupted by server reload/restart).
        Transitions them to 'interrupted' or 'completed' so that sitemaps do not stay stuck in 'indexing'.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, sitemap_id, started_at, last_successful_fetch_at, total_successfully_fetched_urls "
                    "FROM sitemap_refresh_runs WHERE status = 'running'"
                )
                stale_runs = cursor.fetchall()
                if not stale_runs:
                    return
                now = datetime.now(timezone.utc)
                now_iso = now.isoformat()
                for r in stale_runs:
                    last_time_str = r["last_successful_fetch_at"] or r["started_at"]
                    if last_time_str:
                        try:
                            last_time = datetime.fromisoformat(last_time_str.replace("Z", "+00:00"))
                            if (now - last_time).total_seconds() > (stale_timeout_minutes * 60):
                                cursor.execute(
                                    "UPDATE sitemap_refresh_runs SET status = 'interrupted', completed_at = ? WHERE id = ?",
                                    (now_iso, r["id"])
                                )
                                cursor.execute("SELECT COUNT(*) FROM articles")
                                art_row = cursor.fetchone()
                                art_count = art_row[0] if art_row else 0
                                if art_count > 0:
                                    cursor.execute(
                                        "UPDATE sitemaps SET status = 'active', updated_at = ? WHERE id = ?",
                                        (now_iso, r["sitemap_id"])
                                    )
                                else:
                                    cursor.execute(
                                        "UPDATE sitemaps SET status = 'interrupted', updated_at = ? WHERE id = ?",
                                        (now_iso, r["sitemap_id"])
                                    )
                        except Exception:
                            pass
                conn.commit()
        except Exception as e:
            logger.warning(f"Error in recover_stale_runs: {e}")

    def get_sitemaps(self, user_id: str = "default_user") -> List[SitemapItem]:
        self.recover_stale_runs()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sitemaps WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
            rows = cursor.fetchall()
            items = []
            for row in rows:
                preview = {}
                if "last_preview_json" in row.keys() and row["last_preview_json"]:
                    try:
                        preview = json.loads(row["last_preview_json"])
                    except Exception:
                        pass

                cursor.execute("""
                SELECT status, progress_percent, total_discovered_urls, total_successfully_fetched_urls, completed_at
                FROM sitemap_refresh_runs
                WHERE sitemap_id = ?
                ORDER BY started_at DESC LIMIT 1
                """, (row["id"],))
                run_row = cursor.fetchone()

                effective_status = row["status"]
                progress = None
                total_urls = preview.get("total_unique_urls", 0)
                last_val = row["last_confirmed_at"]

                if run_row:
                    if run_row["status"] == "running":
                        effective_status = "indexing"
                        progress = run_row["progress_percent"]
                    elif run_row["status"] == "completed":
                        effective_status = "active"
                    elif run_row["status"] == "interrupted":
                        effective_status = "active" if (run_row["total_successfully_fetched_urls"] or 0) > 0 else "interrupted"
                    if run_row["total_discovered_urls"]:
                        total_urls = run_row["total_discovered_urls"]
                    if run_row["completed_at"]:
                        last_val = run_row["completed_at"]

                items.append(SitemapItem(
                    id=row["id"],
                    user_id=row["user_id"],
                    root_url=row["root_url"],
                    url=row["root_url"],
                    name=row["name"] or row["root_url"],
                    refresh_interval_days=row["refresh_interval_days"] or 1,
                    refresh_interval="daily" if row["refresh_interval_days"] == 1 else f"{row['refresh_interval_days']} days",
                    status=effective_status,
                    discovered_sitemaps_count=preview.get("discovered_sitemaps_count", 1),
                    total_urls_count=total_urls,
                    progress_percent=progress,
                    current_run_status=run_row["status"] if run_row else None,
                    last_validated_at=last_val,
                    last_preview_json=row["last_preview_json"],
                    last_confirmed_at=row["last_confirmed_at"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"]
                ))
            return items

    def get_sitemap(self, sitemap_id: str) -> Optional[SitemapItem]:
        self.recover_stale_runs()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sitemaps WHERE id = ?", (sitemap_id,))
            row = cursor.fetchone()
            if not row:
                return None
            preview = {}
            if "last_preview_json" in row.keys() and row["last_preview_json"]:
                try:
                    preview = json.loads(row["last_preview_json"])
                except Exception:
                    pass

            cursor.execute("""
            SELECT status, progress_percent, total_discovered_urls, total_successfully_fetched_urls, completed_at
            FROM sitemap_refresh_runs
            WHERE sitemap_id = ?
            ORDER BY started_at DESC LIMIT 1
            """, (row["id"],))
            run_row = cursor.fetchone()

            effective_status = row["status"]
            progress = None
            total_urls = preview.get("total_unique_urls", 0)
            last_val = row["last_confirmed_at"]

            if run_row:
                if run_row["status"] == "running":
                    effective_status = "indexing"
                    progress = run_row["progress_percent"]
                elif run_row["status"] == "completed":
                    effective_status = "active"
                elif run_row["status"] == "interrupted":
                    effective_status = "active" if (run_row["total_successfully_fetched_urls"] or 0) > 0 else "interrupted"
                if run_row["total_discovered_urls"]:
                    total_urls = run_row["total_discovered_urls"]
                if run_row["completed_at"]:
                    last_val = run_row["completed_at"]

            return SitemapItem(
                id=row["id"],
                user_id=row["user_id"],
                root_url=row["root_url"],
                url=row["root_url"],
                name=row["name"] or row["root_url"],
                refresh_interval_days=row["refresh_interval_days"] or 1,
                refresh_interval="daily" if row["refresh_interval_days"] == 1 else f"{row['refresh_interval_days']} days",
                status=effective_status,
                discovered_sitemaps_count=preview.get("discovered_sitemaps_count", 1),
                total_urls_count=total_urls,
                progress_percent=progress,
                current_run_status=run_row["status"] if run_row else None,
                last_validated_at=last_val,
                last_preview_json=row["last_preview_json"],
                last_confirmed_at=row["last_confirmed_at"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )

    def update_sitemap_preview(self, sitemap_id: str, preview: SitemapPreview):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE sitemaps
            SET last_preview_json = ?, status = 'previewed', updated_at = ?
            WHERE id = ?
            """, (preview.model_dump_json(), iso_now(), sitemap_id))
            conn.commit()

    def confirm_sitemap(self, sitemap_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = iso_now()
            cursor.execute("""
            UPDATE sitemaps
            SET status = 'confirmed', last_confirmed_at = ?, updated_at = ?
            WHERE id = ?
            """, (now, now, sitemap_id))
            conn.commit()
            return cursor.rowcount > 0

    def save_sitemap_relationship(self, root_sitemap_id: str, sitemap_url: str, parent_sitemap_url: Optional[str], depth: int, is_index: bool, error: Optional[str] = None):
        rel_id = f"rel_{uuid.uuid4().hex[:10]}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO sitemap_relationships (id, root_sitemap_id, sitemap_url, parent_sitemap_url, depth, is_index, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (rel_id, root_sitemap_id, sitemap_url, parent_sitemap_url, depth, 1 if is_index else 0, error, iso_now()))
            conn.commit()

    def get_sitemap_relationships(self, root_sitemap_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sitemap_relationships WHERE root_sitemap_id = ? ORDER BY depth ASC, created_at ASC", (root_sitemap_id,))
            return [dict(row) for row in cursor.fetchall()]

    # -------------------------------------------------------------
    # Phase 3: Refresh Run Management Methods
    # -------------------------------------------------------------
    def create_refresh_run(self, sitemap_id: str, user_id: str = "default_user", total_discovered: int = 0) -> RefreshRunSummary:
        run_id = f"run_{uuid.uuid4().hex[:10]}"
        now = iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO sitemap_refresh_runs (
                id, sitemap_id, user_id, started_at, total_discovered_urls, status, progress_percent
            ) VALUES (?, ?, ?, ?, ?, 'running', 0.0)
            """, (run_id, sitemap_id, user_id, now, total_discovered))
            conn.commit()
        return self.get_refresh_run_summary(run_id)

    def update_refresh_run(self, summary: RefreshRunSummary):
        est_json = summary.estimate.model_dump_json() if summary.estimate else None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE sitemap_refresh_runs SET
                first_successful_fetch_at = COALESCE(?, first_successful_fetch_at),
                last_successful_fetch_at = COALESCE(?, last_successful_fetch_at),
                completed_at = ?,
                total_discovered_urls = ?,
                total_successfully_fetched_urls = ?,
                added_count = ?,
                updated_count = ?,
                unchanged_count = ?,
                failed_count = ?,
                pending_count = ?,
                quarantined_count = ?,
                status = ?,
                progress_percent = ?,
                estimate_json = ?
            WHERE id = ?
            """, (
                summary.first_successful_fetch_at,
                summary.last_successful_fetch_at,
                summary.completed_at,
                summary.total_discovered_urls,
                summary.total_successfully_fetched_urls,
                summary.added_count,
                summary.updated_count,
                summary.unchanged_count,
                summary.failed_count,
                summary.pending_count,
                summary.quarantined_count,
                summary.status,
                summary.progress_percent,
                est_json,
                summary.id
            ))
            conn.commit()

    def get_refresh_run_summary(self, run_id: str) -> Optional[RefreshRunSummary]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sitemap_refresh_runs WHERE id = ?", (run_id,))
            row = cursor.fetchone()
            if not row:
                return None
            est = IndexingEstimate(**json.loads(row["estimate_json"])) if row["estimate_json"] else None
            return RefreshRunSummary(
                id=row["id"],
                sitemap_id=row["sitemap_id"],
                user_id=row["user_id"],
                started_at=row["started_at"],
                first_successful_fetch_at=row["first_successful_fetch_at"],
                last_successful_fetch_at=row["last_successful_fetch_at"],
                completed_at=row["completed_at"],
                total_discovered_urls=row["total_discovered_urls"],
                total_successfully_fetched_urls=row["total_successfully_fetched_urls"],
                added_count=row["added_count"],
                updated_count=row["updated_count"],
                unchanged_count=row["unchanged_count"],
                failed_count=row["failed_count"],
                pending_count=row["pending_count"],
                quarantined_count=row["quarantined_count"],
                status=row["status"],
                progress_percent=row["progress_percent"],
                estimate=est
            )

    def get_refresh_runs(self, sitemap_id: Optional[str] = None, limit: int = 20) -> List[RefreshRunSummary]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if sitemap_id:
                cursor.execute("SELECT * FROM sitemap_refresh_runs WHERE sitemap_id = ? ORDER BY started_at DESC LIMIT ?", (sitemap_id, limit))
            else:
                cursor.execute("SELECT * FROM sitemap_refresh_runs ORDER BY started_at DESC LIMIT ?", (limit,))
            runs = []
            for row in cursor.fetchall():
                est = IndexingEstimate(**json.loads(row["estimate_json"])) if row["estimate_json"] else None
                runs.append(RefreshRunSummary(
                    id=row["id"],
                    sitemap_id=row["sitemap_id"],
                    user_id=row["user_id"],
                    started_at=row["started_at"],
                    first_successful_fetch_at=row["first_successful_fetch_at"],
                    last_successful_fetch_at=row["last_successful_fetch_at"],
                    completed_at=row["completed_at"],
                    total_discovered_urls=row["total_discovered_urls"],
                    total_successfully_fetched_urls=row["total_successfully_fetched_urls"],
                    added_count=row["added_count"],
                    updated_count=row["updated_count"],
                    unchanged_count=row["unchanged_count"],
                    failed_count=row["failed_count"],
                    pending_count=row["pending_count"],
                    quarantined_count=row["quarantined_count"],
                    status=row["status"],
                    progress_percent=row["progress_percent"],
                    estimate=est
                ))
            return runs

    def record_run_url(self, run_id: str, url: str, status: str, http_status: Optional[int] = None, lastmod: Optional[str] = None, error_message: Optional[str] = None):
        item_id = f"ru_{uuid.uuid4().hex[:10]}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO refresh_run_urls (id, run_id, url, status, http_status, lastmod, fetched_at, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (item_id, run_id, url, status, http_status, lastmod, iso_now(), error_message))
            conn.commit()

    def get_refresh_run_detail(self, run_id: str, search: Optional[str] = None, status_filter: Optional[str] = None, limit: int = 500, offset: int = 0) -> Optional[RefreshRunDetail]:
        summary = self.get_refresh_run_summary(run_id)
        if not summary:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM refresh_run_urls WHERE run_id = ?"
            params = [run_id]
            if status_filter:
                query += " AND status = ?"
                params.append(status_filter)
            if search:
                query += " AND url LIKE ?"
                params.append(f"%{search}%")
            
            # Count total matching
            count_query = query.replace("SELECT *", "SELECT COUNT(*)")
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]

            query += " ORDER BY fetched_at ASC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cursor.execute(query, params)
            urls = [
                RefreshRunUrlItem(
                    url=row["url"],
                    status=row["status"],
                    http_status=row["http_status"],
                    lastmod=row["lastmod"],
                    fetched_at=row["fetched_at"],
                    error_message=row["error_message"]
                ) for row in cursor.fetchall()
            ]
            return RefreshRunDetail(
                summary=summary,
                urls=urls,
                total_url_count=total_count
            )

    # -------------------------------------------------------------
    # Phase 4: URL Health & Quarantine Methods
    # -------------------------------------------------------------
    def record_url_observation(self, url: str, sitemap_id: str, run_id: Optional[str], http_status: int, redirect_url: Optional[str] = None, is_in_sitemap: bool = True, error_reason: Optional[str] = None):
        obs_id = f"obs_{uuid.uuid4().hex[:10]}"
        now = iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO url_health_observations (id, url, sitemap_id, run_id, http_status, redirect_url, is_in_sitemap, observed_at, error_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (obs_id, url, sitemap_id, run_id, http_status, redirect_url, 1 if is_in_sitemap else 0, now, error_reason))
            conn.commit()

    def update_url_health(self, url: str, sitemap_id: str, http_status: int, is_in_sitemap: bool, threshold_x: int = 3, error_reason: Optional[str] = None) -> URLHealthStatus:
        now = iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM url_health_status WHERE url = ?", (url,))
            row = cursor.fetchone()
            
            # Option A: Consecutive scheduled refresh checks
            # Recovery condition: HTTP 200 resets failure count
            if http_status == 200:
                consecutive = 0
                reason = None
            else:
                consecutive = (row["consecutive_failure_count"] if row else 0) + 1
                reason = error_reason or f"HTTP {http_status}"

            action = f"Quarantine when failure count reaches {threshold_x}"

            cursor.execute("""
            INSERT INTO url_health_status (url, sitemap_id, consecutive_failure_count, configured_threshold, expected_action, last_checked_at, last_http_status, is_in_sitemap, failure_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                sitemap_id = excluded.sitemap_id,
                consecutive_failure_count = excluded.consecutive_failure_count,
                configured_threshold = excluded.configured_threshold,
                expected_action = excluded.expected_action,
                last_checked_at = excluded.last_checked_at,
                last_http_status = excluded.last_http_status,
                is_in_sitemap = excluded.is_in_sitemap,
                failure_reason = excluded.failure_reason
            """, (url, sitemap_id, consecutive, threshold_x, action, now, http_status, 1 if is_in_sitemap else 0, reason))
            conn.commit()

            return URLHealthStatus(
                url=url,
                sitemap_id=sitemap_id,
                consecutive_failure_count=consecutive,
                configured_threshold=threshold_x,
                expected_action=action,
                last_checked_at=now,
                last_http_status=http_status,
                is_in_sitemap=is_in_sitemap,
                failure_reason=reason
            )

    def get_url_health_statuses(self, sitemap_id: Optional[str] = None) -> List[URLHealthStatus]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if sitemap_id:
                cursor.execute("SELECT * FROM url_health_status WHERE sitemap_id = ? ORDER BY consecutive_failure_count DESC", (sitemap_id,))
            else:
                cursor.execute("SELECT * FROM url_health_status ORDER BY consecutive_failure_count DESC")
            return [
                URLHealthStatus(
                    url=row["url"],
                    sitemap_id=row["sitemap_id"],
                    consecutive_failure_count=row["consecutive_failure_count"],
                    configured_threshold=row["configured_threshold"],
                    expected_action=row["expected_action"],
                    last_checked_at=row["last_checked_at"],
                    last_http_status=row["last_http_status"],
                    is_in_sitemap=bool(row["is_in_sitemap"]),
                    failure_reason=row["failure_reason"]
                ) for row in cursor.fetchall()
            ]

    def quarantine_article(self, url: str, sitemap_id: Optional[str], reason: QuarantineReason, last_status: int = 404, replacement_url: Optional[str] = None) -> Optional[QuarantineRecord]:
        """
        Quarantines an article without data loss.
        Preserves original URL, title, content, chunks, embeddings, and marks articles.status = 'quarantined'.
        Excludes from active RAG without deleting historical records.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM articles WHERE url = ?", (url,))
            art_row = cursor.fetchone()
            if not art_row:
                return None

            cursor.execute("SELECT * FROM chunks WHERE article_url = ?", (url,))
            chunk_rows = cursor.fetchall()
            chunks_data = [dict(c) for c in chunk_rows]

            # Fetch observation history
            cursor.execute("SELECT observed_at FROM url_health_observations WHERE url = ? ORDER BY observed_at ASC", (url,))
            history = [r["observed_at"] for r in cursor.fetchall()]

            rec_id = f"q_{uuid.uuid4().hex[:10]}"
            now = iso_now()

            cursor.execute("""
            INSERT INTO quarantine_records (
                id, url, sitemap_id, title, content, chunks_json, embeddings_json,
                last_known_http_status, quarantine_reason, replacement_url, detected_at, quarantined_at, sitemap_presence_history_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                quarantine_reason = excluded.quarantine_reason,
                last_known_http_status = excluded.last_known_http_status,
                quarantined_at = excluded.quarantined_at,
                replacement_url = excluded.replacement_url,
                restored_at = NULL
            """, (
                rec_id, url, sitemap_id, art_row["title"], art_row["body_text"],
                json.dumps(chunks_data), art_row["images_json"],
                last_status, reason.value if isinstance(reason, QuarantineReason) else str(reason),
                replacement_url, art_row["crawled_at"] or now, now, json.dumps(history)
            ))

            # Mark article as quarantined in articles table (DO NOT DELETE CHUNKS)
            cursor.execute("UPDATE articles SET status = 'quarantined' WHERE url = ?", (url,))
            conn.commit()

            return QuarantineRecord(
                id=rec_id,
                url=url,
                sitemap_id=sitemap_id,
                title=art_row["title"],
                content=art_row["body_text"],
                chunks_count=len(chunks_data),
                last_known_http_status=last_status,
                quarantine_reason=reason if isinstance(reason, QuarantineReason) else QuarantineReason(reason),
                replacement_url=replacement_url,
                detected_at=art_row["crawled_at"] or now,
                quarantined_at=now,
                sitemap_presence_history=history
            )

    def restore_quarantined_article(self, url: str) -> bool:
        """Restores a quarantined article back to active knowledge without data loss."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = iso_now()
            cursor.execute("UPDATE articles SET status = 'active' WHERE url = ?", (url,))
            count = cursor.rowcount
            cursor.execute("UPDATE quarantine_records SET restored_at = ? WHERE url = ?", (now, url))
            cursor.execute("UPDATE url_health_status SET consecutive_failure_count = 0, failure_reason = NULL WHERE url = ?", (url,))
            conn.commit()
            return count > 0

    def get_quarantined_articles(self) -> List[QuarantineRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM quarantine_records WHERE restored_at IS NULL ORDER BY quarantined_at DESC")
            records = []
            for row in cursor.fetchall():
                history = json.loads(row["sitemap_presence_history_json"]) if row["sitemap_presence_history_json"] else []
                chunks_data = json.loads(row["chunks_json"]) if row["chunks_json"] else []
                reason_val = row["quarantine_reason"]
                try:
                    reason_enum = QuarantineReason(reason_val)
                except ValueError:
                    reason_enum = QuarantineReason.MISSING_404
                records.append(QuarantineRecord(
                    id=row["id"],
                    url=row["url"],
                    sitemap_id=row["sitemap_id"],
                    title=row["title"],
                    content=row["content"],
                    chunks_count=len(chunks_data),
                    last_known_http_status=row["last_known_http_status"] or 404,
                    quarantine_reason=reason_enum,
                    replacement_url=row["replacement_url"],
                    detected_at=row["detected_at"] or row["quarantined_at"],
                    quarantined_at=row["quarantined_at"],
                    restored_at=row["restored_at"],
                    sitemap_presence_history=history
                ))
            return records

    # -------------------------------------------------------------
    # User Settings Methods
    # -------------------------------------------------------------
    def get_user_settings(self, user_id: str = "default_user") -> UserSettings:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                default_settings = UserSettings(user_id=user_id)
                self.save_user_settings(default_settings)
                return default_settings
            return UserSettings(
                user_id=row["user_id"],
                sitemap_refresh_interval_days=row["sitemap_refresh_interval_days"],
                url_quarantine_threshold_x=row["url_quarantine_threshold_x"],
                url_quarantine_action=row["url_quarantine_action"],
                email_approval_threshold_x=row["email_approval_threshold_x"],
                auto_send_enabled=bool(row["auto_send_enabled"]),
                emergency_disable=bool(row["emergency_disable"])
            )

    def save_user_settings(self, s: UserSettings):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO user_settings (
                user_id, sitemap_refresh_interval_days, url_quarantine_threshold_x,
                url_quarantine_action, email_approval_threshold_x, auto_send_enabled, emergency_disable, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                sitemap_refresh_interval_days = excluded.sitemap_refresh_interval_days,
                url_quarantine_threshold_x = excluded.url_quarantine_threshold_x,
                url_quarantine_action = excluded.url_quarantine_action,
                email_approval_threshold_x = excluded.email_approval_threshold_x,
                auto_send_enabled = excluded.auto_send_enabled,
                emergency_disable = excluded.emergency_disable,
                updated_at = excluded.updated_at
            """, (
                s.user_id, s.sitemap_refresh_interval_days, s.url_quarantine_threshold_x,
                s.url_quarantine_action, s.email_approval_threshold_x,
                1 if s.auto_send_enabled else 0, 1 if s.emergency_disable else 0, iso_now()
            ))
            conn.commit()

    # -------------------------------------------------------------
    # Phase 6: Authentication & Session Methods
    # -------------------------------------------------------------
    def create_user(self, email: str, password_hash: str, display_name: str = "", role: str = "user") -> Dict[str, Any]:
        user_id = f"u_{uuid.uuid4().hex[:10]}"
        now = iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO users (id, email, password_hash, display_name, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, email.lower().strip(), password_hash, display_name or email.split("@")[0], role, now))
            conn.commit()
        return {"id": user_id, "email": email, "display_name": display_name, "role": role, "created_at": now}

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_session(self, user_id: str, expires_in_seconds: int = 86400 * 7) -> str:
        session_id = f"sess_{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc)
        expires_at = datetime.fromtimestamp(now.timestamp() + expires_in_seconds, timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO user_sessions (session_id, user_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """, (session_id, user_id, expires_at, now.isoformat()))
            conn.commit()
        return session_id

    def get_session_user(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_sessions WHERE session_id = ?", (session_id,))
            sess_row = cursor.fetchone()
            if not sess_row:
                return None
            
            # Check expiry
            expires_at = datetime.fromisoformat(sess_row["expires_at"])
            if expires_at < datetime.now(timezone.utc):
                cursor.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
                conn.commit()
                return None

            cursor.execute("SELECT id, email, display_name, role, created_at FROM users WHERE id = ?", (sess_row["user_id"],))
            user_row = cursor.fetchone()
            return dict(user_row) if user_row else None

    def delete_session(self, session_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
            conn.commit()


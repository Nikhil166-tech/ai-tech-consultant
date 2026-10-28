import sqlite3
import json
import uuid
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Tuple
from app.models import (
    Article, ArticleChunk, ImageMetadata, ExpertTask, SyncStatus, SyncReport,
    SitemapItem, SitemapPreview, RefreshRunSummary, RefreshRunDetail, RefreshRunUrlItem,
    QuarantineRecord, QuarantineReason, URLHealthStatus, UserSettings, IndexingEstimate,
    ArchivedArticleItem, ArchivedArticleDetail, ArticleRedirectItem, ArticleHistoryItem,
    SchedulerStatusResponse
)
from app.url_utils import canonicalize_url

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 6

def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()

class SessionToken(str):
    """
    Backwards-compatible session token:
    Acts as a string (session_id) while supporting tuple unpacking (session_id, csrf_token).
    """
    def __new__(cls, session_id: str, csrf_token: str):
        obj = super().__new__(cls, session_id)
        obj.session_id = session_id
        obj.csrf_token = csrf_token
        return obj

    def __iter__(self):
        yield self.session_id
        yield self.csrf_token

class Database:
    def __init__(self, db_path: str = "knowledge_brain.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=60.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=60000")
        return conn

    def get_connection(self) -> sqlite3.Connection:
        return self._get_connection()

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
                refresh_interval TEXT DEFAULT 'daily',
                refresh_interval_days INTEGER DEFAULT 1,
                status TEXT DEFAULT 'registered',
                schedule_status TEXT DEFAULT 'active',
                next_refresh_at TEXT,
                last_refresh_started_at TEXT,
                last_refresh_completed_at TEXT,
                retry_count INTEGER DEFAULT 0,
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
                canonical_url TEXT,
                user_id TEXT DEFAULT 'default_user',
                sitemap_id TEXT,
                consecutive_failure_count INTEGER DEFAULT 0,
                configured_threshold INTEGER DEFAULT 3,
                expected_action TEXT DEFAULT 'Quarantine on 3 consecutive failures',
                pending_action TEXT DEFAULT 'NONE',
                action_rule TEXT DEFAULT 'QUARANTINE_ON_THRESHOLD',
                redirect_destination_url TEXT,
                last_checked_at TEXT,
                last_successful_fetch_at TEXT,
                last_attempted_fetch_at TEXT,
                last_http_status INTEGER,
                is_in_sitemap INTEGER DEFAULT 1,
                is_healthy INTEGER DEFAULT 1,
                failure_reason TEXT,
                action_history_json TEXT DEFAULT '[]'
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
                user_id TEXT,
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
            CREATE TABLE IF NOT EXISTS archived_articles (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                canonical_url TEXT,
                sitemap_id TEXT,
                user_id TEXT DEFAULT 'default_user',
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                chunks_json TEXT DEFAULT '[]',
                embeddings_json TEXT DEFAULT '[]',
                original_indexed_at TEXT,
                archived_at TEXT NOT NULL,
                archive_reason TEXT NOT NULL,
                last_known_http_status INTEGER,
                replacement_url TEXT,
                last_successful_version TEXT DEFAULT '2.0',
                restore_eligible INTEGER DEFAULT 1,
                retention_preset TEXT DEFAULT '30d',
                retention_days INTEGER DEFAULT 30,
                retention_expires_at TEXT,
                audit_history_json TEXT DEFAULT '[]'
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS article_redirects (
                id TEXT PRIMARY KEY,
                user_id TEXT DEFAULT 'default_user',
                sitemap_id TEXT,
                source_url TEXT NOT NULL,
                destination_url TEXT NOT NULL,
                http_status INTEGER DEFAULT 301,
                hop_count INTEGER DEFAULT 1,
                redirect_chain_json TEXT DEFAULT '[]',
                detected_at TEXT NOT NULL,
                replacement_indexed INTEGER DEFAULT 0,
                replacement_article_url TEXT,
                notes TEXT
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id TEXT PRIMARY KEY,
                sitemap_refresh_interval_days INTEGER DEFAULT 1,
                url_quarantine_threshold_x INTEGER DEFAULT 3,
                url_quarantine_action TEXT DEFAULT 'QUARANTINE_ON_CONSECUTIVE_FAILURES',
                archive_retention_preset TEXT DEFAULT '30d',
                archive_retention_days INTEGER DEFAULT 30,
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

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS article_history (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                user_id TEXT DEFAULT 'default_user',
                sitemap_id TEXT,
                version TEXT DEFAULT '2.0',
                title TEXT,
                previous_title TEXT,
                new_title TEXT,
                change_type TEXT,
                previous_hash TEXT,
                new_hash TEXT,
                summary_diff TEXT,
                content_snapshot TEXT,
                extraction_version TEXT DEFAULT '2.0',
                embedding_model TEXT DEFAULT 'BAAI/bge-small-en-v1.5',
                embedding_version TEXT DEFAULT '1.0',
                refresh_run_id TEXT,
                change_classification TEXT DEFAULT 'CONTENT_UPDATE',
                recorded_at TEXT,
                FOREIGN KEY (url) REFERENCES articles(url) ON DELETE CASCADE
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
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_quarantine_user ON quarantine_records(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_health_user ON url_health_status(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_archived_user ON archived_articles(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_archived_url ON archived_articles(url)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_archived_sitemap ON archived_articles(sitemap_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_archived_reason ON archived_articles(archive_reason)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_redirects_source ON article_redirects(source_url)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_redirects_dest ON article_redirects(destination_url)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_redirects_user ON article_redirects(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sitemaps_schedule ON sitemaps(schedule_status, next_refresh_at)")
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

        # Phase 1 / Version 4 migrations: Auth security, rate limiting, CSRF, and user data isolation
        ensure_column("users", "failed_login_attempts", "INTEGER DEFAULT 0")
        ensure_column("users", "locked_until", "TEXT")
        ensure_column("users", "last_login_at", "TEXT")
        ensure_column("user_sessions", "csrf_token", "TEXT")
        ensure_column("user_sessions", "last_activity_at", "TEXT")
        ensure_column("quarantine_records", "user_id", "TEXT")
        ensure_column("url_health_status", "user_id", "TEXT")

        # Backfill user_id on quarantine and health tables from sitemaps where missing
        cursor.execute("""
        UPDATE quarantine_records 
        SET user_id = (SELECT user_id FROM sitemaps WHERE sitemaps.id = quarantine_records.sitemap_id)
        WHERE (user_id IS NULL OR user_id = '') AND sitemap_id IS NOT NULL
        """)

        # Phase 2 / Version 5 migrations: Step 2 Knowledge Brain Data Integrity & Deduplication
        ensure_column("articles", "user_id", "TEXT DEFAULT 'default_user'")
        ensure_column("articles", "sitemap_id", "TEXT")
        ensure_column("articles", "raw_content_hash", "TEXT")
        ensure_column("articles", "normalized_content_hash", "TEXT")
        ensure_column("articles", "extraction_version", "TEXT DEFAULT '2.0'")
        ensure_column("articles", "embedding_model", "TEXT DEFAULT 'BAAI/bge-small-en-v1.5'")
        ensure_column("articles", "embedding_version", "TEXT DEFAULT '1.0'")
        ensure_column("articles", "is_quarantined", "INTEGER DEFAULT 0")
        ensure_column("articles", "quarantine_reason", "TEXT")

        ensure_column("sitemaps", "canonical_root_url", "TEXT")

        ensure_column("sitemap_refresh_runs", "lease_token", "TEXT")
        ensure_column("sitemap_refresh_runs", "lease_expires_at", "TEXT")
        ensure_column("sitemap_refresh_runs", "heartbeat_at", "TEXT")
        ensure_column("sitemap_refresh_runs", "stage", "TEXT DEFAULT 'QUEUED'")
        ensure_column("sitemap_refresh_runs", "resumed_from_run_id", "TEXT")
        ensure_column("sitemap_refresh_runs", "last_processed_url", "TEXT")
        ensure_column("sitemap_refresh_runs", "error_details", "TEXT")

        # Backfill canonical_root_url on sitemaps where missing
        cursor.execute("SELECT id, root_url FROM sitemaps WHERE canonical_root_url IS NULL OR canonical_root_url = ''")
        for sm_row in cursor.fetchall():
            c_url = canonicalize_url(sm_row[1], is_sitemap=True)
            cursor.execute("UPDATE sitemaps SET canonical_root_url = ? WHERE id = ?", (c_url, sm_row[0]))

        # Backfill normalized_content_hash on articles where missing
        cursor.execute("UPDATE articles SET normalized_content_hash = content_hash WHERE normalized_content_hash IS NULL AND content_hash IS NOT NULL")

        # Step 2 tables & indexes
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS article_history (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            version TEXT DEFAULT '2.0',
            title TEXT,
            change_type TEXT,
            previous_hash TEXT,
            new_hash TEXT,
            summary_diff TEXT,
            recorded_at TEXT,
            FOREIGN KEY (url) REFERENCES articles(url) ON DELETE CASCADE
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_article_history_url ON article_history(url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_articles_user ON articles(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_articles_sitemap ON articles(sitemap_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sitemaps_user_canonical ON sitemaps(user_id, canonical_root_url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_refresh_runs_stage ON sitemap_refresh_runs(stage)")
        # Phase 3 / Version 6 migrations: Step 3 Production Scheduled Refresh, Archived KB, URL Health, 301 Redirects & Version History
        ensure_column("sitemaps", "refresh_interval", "TEXT DEFAULT 'daily'")
        ensure_column("sitemaps", "next_refresh_at", "TEXT")
        ensure_column("sitemaps", "last_refresh_started_at", "TEXT")
        ensure_column("sitemaps", "last_refresh_completed_at", "TEXT")
        ensure_column("sitemaps", "schedule_status", "TEXT DEFAULT 'active'")
        ensure_column("sitemaps", "retry_count", "INTEGER DEFAULT 0")

        ensure_column("url_health_status", "canonical_url", "TEXT")
        ensure_column("url_health_status", "last_successful_fetch_at", "TEXT")
        ensure_column("url_health_status", "last_attempted_fetch_at", "TEXT")
        ensure_column("url_health_status", "pending_action", "TEXT DEFAULT 'NONE'")
        ensure_column("url_health_status", "action_rule", "TEXT DEFAULT 'QUARANTINE_ON_THRESHOLD'")
        ensure_column("url_health_status", "redirect_destination_url", "TEXT")
        ensure_column("url_health_status", "action_history_json", "TEXT DEFAULT '[]'")
        ensure_column("url_health_status", "is_healthy", "INTEGER DEFAULT 1")

        ensure_column("user_settings", "archive_retention_preset", "TEXT DEFAULT '30d'")
        ensure_column("user_settings", "archive_retention_days", "INTEGER DEFAULT 30")

        ensure_column("article_history", "user_id", "TEXT DEFAULT 'default_user'")
        ensure_column("article_history", "sitemap_id", "TEXT")
        ensure_column("article_history", "previous_title", "TEXT")
        ensure_column("article_history", "new_title", "TEXT")
        ensure_column("article_history", "content_snapshot", "TEXT")
        ensure_column("article_history", "extraction_version", "TEXT DEFAULT '2.0'")
        ensure_column("article_history", "embedding_model", "TEXT DEFAULT 'BAAI/bge-small-en-v1.5'")
        ensure_column("article_history", "embedding_version", "TEXT DEFAULT '1.0'")
        ensure_column("article_history", "refresh_run_id", "TEXT")
        ensure_column("article_history", "change_classification", "TEXT DEFAULT 'CONTENT_UPDATE'")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS archived_articles (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            canonical_url TEXT,
            sitemap_id TEXT,
            user_id TEXT DEFAULT 'default_user',
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            chunks_json TEXT DEFAULT '[]',
            embeddings_json TEXT DEFAULT '[]',
            original_indexed_at TEXT,
            archived_at TEXT NOT NULL,
            archive_reason TEXT NOT NULL,
            last_known_http_status INTEGER,
            replacement_url TEXT,
            last_successful_version TEXT DEFAULT '2.0',
            restore_eligible INTEGER DEFAULT 1,
            retention_preset TEXT DEFAULT '30d',
            retention_days INTEGER DEFAULT 30,
            retention_expires_at TEXT,
            audit_history_json TEXT DEFAULT '[]'
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS article_redirects (
            id TEXT PRIMARY KEY,
            user_id TEXT DEFAULT 'default_user',
            sitemap_id TEXT,
            source_url TEXT NOT NULL,
            destination_url TEXT NOT NULL,
            http_status INTEGER DEFAULT 301,
            hop_count INTEGER DEFAULT 1,
            redirect_chain_json TEXT DEFAULT '[]',
            detected_at TEXT NOT NULL,
            replacement_indexed INTEGER DEFAULT 0,
            replacement_article_url TEXT,
            notes TEXT
        )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_archived_user ON archived_articles(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_archived_url ON archived_articles(url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_archived_sitemap ON archived_articles(sitemap_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_archived_reason ON archived_articles(archive_reason)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_redirects_source ON article_redirects(source_url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_redirects_dest ON article_redirects(destination_url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_redirects_user ON article_redirects(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sitemaps_schedule ON sitemaps(schedule_status, next_refresh_at)")

        # Backfill initial next_refresh_at on sitemaps where null
        cursor.execute("SELECT id, refresh_interval_days FROM sitemaps WHERE next_refresh_at IS NULL OR next_refresh_at = ''")
        for sm_row in cursor.fetchall():
            intv = sm_row[1] or 1
            next_due = (datetime.now(timezone.utc) + timedelta(days=intv)).isoformat()
            cursor.execute("UPDATE sitemaps SET next_refresh_at = ?, schedule_status = 'active' WHERE id = ?", (next_due, sm_row[0]))

        cursor.execute("UPDATE url_health_status SET canonical_url = url WHERE canonical_url IS NULL OR canonical_url = ''")
        cursor.execute("UPDATE url_health_status SET action_rule = 'QUARANTINE_ON_THRESHOLD' WHERE action_rule IS NULL OR action_rule = ''")
        cursor.execute("UPDATE url_health_status SET pending_action = 'NONE' WHERE pending_action IS NULL OR pending_action = ''")

        if version < CURRENT_SCHEMA_VERSION:
            cursor.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")

    def apply_migrations(self):
        """Public, idempotent schema migration runner for testing and maintenance."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            self._apply_migrations(cursor)
            conn.commit()

    def upsert_article(self, article: Article):
        images_json = json.dumps([img.model_dump() for img in article.images])
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO articles (
                url, title, category, folder, body_text, content_hash, raw_content_hash,
                normalized_content_hash, images_json, last_modified, etag, status,
                user_id, sitemap_id, extraction_version, embedding_model, embedding_version,
                is_quarantined, quarantine_reason, crawled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title,
                category=excluded.category,
                folder=excluded.folder,
                body_text=excluded.body_text,
                content_hash=excluded.content_hash,
                raw_content_hash=excluded.raw_content_hash,
                normalized_content_hash=excluded.normalized_content_hash,
                images_json=excluded.images_json,
                last_modified=excluded.last_modified,
                etag=excluded.etag,
                status='active',
                user_id=excluded.user_id,
                sitemap_id=excluded.sitemap_id,
                extraction_version=excluded.extraction_version,
                embedding_model=excluded.embedding_model,
                embedding_version=excluded.embedding_version,
                is_quarantined=0,
                quarantine_reason=NULL,
                crawled_at=excluded.crawled_at
            """, (
                article.url,
                article.title,
                article.category,
                article.folder,
                article.body_text,
                article.content_hash,
                article.raw_content_hash or article.content_hash,
                article.normalized_content_hash or article.content_hash,
                images_json,
                article.last_modified,
                article.etag,
                article.status or "active",
                article.user_id or "default_user",
                article.sitemap_id,
                article.extraction_version or "2.0",
                article.embedding_model or "BAAI/bge-small-en-v1.5",
                article.embedding_version or "1.0",
                1 if article.is_quarantined else 0,
                article.quarantine_reason,
                article.crawled_at.isoformat() if isinstance(article.crawled_at, datetime) else str(article.crawled_at)
            ))
            conn.commit()

    def atomic_replace_article_and_chunks(
        self,
        article: Article,
        chunks: List[ArticleChunk],
        checkpoint_status: int = 200,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None
    ) -> None:
        """
        Atomically replaces an article, its chunks, and updates its crawler checkpoint
        within a single SQLite transaction. Also records version diff in article_history
        if an existing article is being updated.
        """
        images_json = json.dumps([img.model_dump() for img in article.images])
        now = iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check existing article for history diff
            cursor.execute("SELECT body_text, content_hash, title, user_id, sitemap_id FROM articles WHERE url = ?", (article.url,))
            existing = cursor.fetchone()
            if existing:
                prev_hash = existing["content_hash"]
                prev_title = existing["title"]
                if prev_hash != article.content_hash or prev_title != article.title:
                    hist_id = f"hist_{uuid.uuid4().hex[:10]}"
                    diff_parts = []
                    if prev_hash != article.content_hash:
                        diff_parts.append(f"Content changed ({len(existing['body_text'])} -> {len(article.body_text)} chars)")
                    if prev_title != article.title:
                        diff_parts.append(f"Title changed ('{prev_title}' -> '{article.title}')")
                    diff_summary = "; ".join(diff_parts)
                    classification = "CONTENT_UPDATE" if prev_hash != article.content_hash else "TITLE_UPDATE"
                    cursor.execute("""
                    INSERT INTO article_history (
                        id, url, user_id, sitemap_id, version, title, previous_title, new_title,
                        change_type, change_classification, previous_hash, new_hash, summary_diff,
                        content_snapshot, extraction_version, embedding_model, embedding_version, recorded_at
                    ) VALUES (?, ?, ?, ?, '2.0', ?, ?, ?, 'UPDATE', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        hist_id, article.url, article.user_id or existing["user_id"] or "default_user",
                        article.sitemap_id or existing["sitemap_id"], article.title, prev_title, article.title,
                        classification, prev_hash, article.content_hash, diff_summary,
                        existing["body_text"], article.extraction_version or "2.0",
                        article.embedding_model or "BAAI/bge-small-en-v1.5",
                        article.embedding_version or "1.0", now
                    ))

            # Upsert article
            cursor.execute("""
            INSERT INTO articles (
                url, title, category, folder, body_text, content_hash, raw_content_hash,
                normalized_content_hash, images_json, last_modified, etag, status,
                user_id, sitemap_id, extraction_version, embedding_model, embedding_version,
                is_quarantined, quarantine_reason, crawled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title,
                category=excluded.category,
                folder=excluded.folder,
                body_text=excluded.body_text,
                content_hash=excluded.content_hash,
                raw_content_hash=excluded.raw_content_hash,
                normalized_content_hash=excluded.normalized_content_hash,
                images_json=excluded.images_json,
                last_modified=excluded.last_modified,
                etag=excluded.etag,
                status='active',
                user_id=excluded.user_id,
                sitemap_id=excluded.sitemap_id,
                extraction_version=excluded.extraction_version,
                embedding_model=excluded.embedding_model,
                embedding_version=excluded.embedding_version,
                is_quarantined=0,
                quarantine_reason=NULL,
                crawled_at=excluded.crawled_at
            """, (
                article.url,
                article.title,
                article.category,
                article.folder,
                article.body_text,
                article.content_hash,
                article.raw_content_hash or article.content_hash,
                article.normalized_content_hash or article.content_hash,
                images_json,
                article.last_modified,
                article.etag,
                article.status or "active",
                article.user_id or "default_user",
                article.sitemap_id,
                article.extraction_version or "2.0",
                article.embedding_model or "BAAI/bge-small-en-v1.5",
                article.embedding_version or "1.0",
                1 if article.is_quarantined else 0,
                article.quarantine_reason,
                article.crawled_at.isoformat() if isinstance(article.crawled_at, datetime) else str(article.crawled_at)
            ))

            # Atomically replace chunks: Delete old chunks for this URL
            cursor.execute("DELETE FROM chunks WHERE article_url = ?", (article.url,))

            # Insert new chunks
            for chunk in chunks:
                emb_json = json.dumps(chunk.embedding or [])
                imgs_json = json.dumps([img.model_dump() for img in chunk.images])
                cursor.execute("""
                INSERT INTO chunks (
                    id, article_url, title, category, folder, section_heading,
                    chunk_index, text, visual_context, images_json, embedding_json,
                    source_type, provenance_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

            # Upsert crawler_checkpoint
            cursor.execute("""
            INSERT INTO crawler_checkpoint (url, last_checked, status_code, etag, last_modified, content_hash, error)
            VALUES (?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(url) DO UPDATE SET
                last_checked=excluded.last_checked,
                status_code=excluded.status_code,
                etag=excluded.etag,
                last_modified=excluded.last_modified,
                content_hash=excluded.content_hash,
                error=NULL
            """, (
                article.url,
                now,
                checkpoint_status,
                etag or article.etag,
                last_modified or article.last_modified,
                article.normalized_content_hash or article.content_hash
            ))

            conn.commit()

    def delete_chunks_for_article(self, article_url: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chunks WHERE article_url = ?", (article_url,))
            conn.commit()

    def get_chunks_for_article(self, article_url: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM chunks WHERE article_url = ? ORDER BY chunk_index ASC", (article_url,))
            return [dict(r) for r in cursor.fetchall()]

    def get_article_history(self, url: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM article_history WHERE url = ? ORDER BY recorded_at DESC", (url,))
            return [dict(r) for r in cursor.fetchall()]

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
            cursor.execute("SELECT COUNT(*) FROM articles WHERE status = 'active' AND (is_quarantined = 0 OR is_quarantined IS NULL) AND url NOT LIKE 'https://example.com/%'")
            row = cursor.fetchone()
            return row[0] if row else 0

    def count_active_chunks(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT COUNT(*) FROM chunks c
            JOIN articles a ON c.article_url = a.url
            WHERE a.status = 'active' AND (a.is_quarantined = 0 OR a.is_quarantined IS NULL) AND a.url NOT LIKE 'https://example.com/%'
            """)
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_all_active_urls(self) -> List[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM articles WHERE status = 'active' AND (is_quarantined = 0 OR is_quarantined IS NULL) AND url NOT LIKE 'https://example.com/%'")
            return [row["url"] for row in cursor.fetchall()]

    def get_active_articles(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT a.url, a.title, a.category, a.folder, a.status, a.crawled_at, a.body_text,
                   (SELECT COUNT(*) FROM chunks c WHERE c.article_url = a.url) as chunks_count
            FROM articles a
            WHERE a.status = 'active' AND (a.is_quarantined = 0 OR a.is_quarantined IS NULL) AND a.url NOT LIKE 'https://example.com/%'
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
            WHERE a.status = 'active' AND (a.is_quarantined = 0 OR a.is_quarantined IS NULL) AND a.url NOT LIKE 'https://example.com/%'
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
    def create_sitemap(
        self,
        root_url: str,
        name: Optional[str] = None,
        user_id: str = "default_user",
        refresh_interval_days: int = 1
    ) -> SitemapItem:
        canonical_root = canonicalize_url(root_url, is_sitemap=True)
        sitemap_name = name or root_url
        now = iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Prevent duplicate registration of the same canonical root sitemap for the same user
            cursor.execute(
                "SELECT id, root_url, canonical_root_url, name FROM sitemaps WHERE user_id = ? AND canonical_root_url = ?",
                (user_id, canonical_root)
            )
            existing = cursor.fetchone()
            if existing:
                raise ValueError(
                    f"Sitemap already registered for user '{user_id}' with canonical URL '{canonical_root}' (existing ID: {existing['id']})"
                )

            sitemap_id = f"sm_{uuid.uuid4().hex[:10]}"
            cursor.execute("""
            INSERT INTO sitemaps (id, user_id, root_url, canonical_root_url, name, refresh_interval_days, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'registered', ?, ?)
            """, (sitemap_id, user_id, root_url, canonical_root, sitemap_name, refresh_interval_days, now, now))
            conn.commit()
        return self.get_sitemap(sitemap_id)

    def get_duplicate_sitemaps(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Identifies existing duplicate sitemap registrations grouped by user and canonical URL."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
            SELECT user_id, canonical_root_url, COUNT(*) as count, GROUP_CONCAT(id) as sitemap_ids
            FROM sitemaps
            """
            params = []
            if user_id and user_id not in ("service_internal", "admin"):
                query += " WHERE user_id = ?"
                params.append(user_id)
            query += " GROUP BY user_id, canonical_root_url HAVING count > 1"
            cursor.execute(query, tuple(params))
            results = []
            for row in cursor.fetchall():
                results.append({
                    "user_id": row["user_id"],
                    "canonical_root_url": row["canonical_root_url"],
                    "duplicate_count": row["count"],
                    "sitemap_ids": row["sitemap_ids"].split(",") if row["sitemap_ids"] else []
                })
            return results

    def get_dry_run_reconciliation_plan(self) -> Dict[str, Any]:
        """
        Generates a non-destructive dry-run plan mapping historical duplicate sitemaps
        to their primary canonical instance without deleting any data.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id, user_id, root_url, canonical_root_url, created_at, status
            FROM sitemaps
            ORDER BY user_id, canonical_root_url, created_at ASC
            """)
            rows = cursor.fetchall()
            groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
            for r in rows:
                key = (r["user_id"], r["canonical_root_url"] or canonicalize_url(r["root_url"], is_sitemap=True))
                if key not in groups:
                    groups[key] = []
                groups[key].append(dict(r))

            plan_groups = []
            for (u_id, c_url), sm_list in groups.items():
                if len(sm_list) > 1:
                    primary = sm_list[0]
                    duplicates = sm_list[1:]
                    plan_groups.append({
                        "user_id": u_id,
                        "canonical_root_url": c_url,
                        "primary_sitemap_id": primary["id"],
                        "primary_created_at": primary["created_at"],
                        "secondary_duplicate_ids": [d["id"] for d in duplicates],
                        "recommended_action": "Preserve primary sitemap; associate future crawl history with primary instance; preserve historical runs with immutable lineage"
                    })

            return {
                "generated_at": iso_now(),
                "total_duplicate_clusters": len(plan_groups),
                "is_dry_run": True,
                "reconciliation_plan": plan_groups
            }

    def acquire_indexing_lease(
        self,
        sitemap_id: str,
        run_id: str,
        lease_token: str,
        lease_duration_seconds: int = 180
    ) -> Tuple[bool, Optional[str]]:
        """
        Acquires an exclusive worker lease for a sitemap refresh run.
        Prevents concurrent duplicate runs for the same sitemap.
        """
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(seconds=lease_duration_seconds)).isoformat()
        now_iso = now.isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id, lease_token, lease_expires_at, heartbeat_at
            FROM sitemap_refresh_runs
            WHERE sitemap_id = ? AND status = 'running' AND id != ?
            """, (sitemap_id, run_id))
            other_active = cursor.fetchall()
            for other in other_active:
                exp_str = other["lease_expires_at"] or other["heartbeat_at"]
                if exp_str:
                    try:
                        exp_time = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                        if exp_time > now:
                            return False, f"Concurrent run in progress: Run '{other['id']}' holds an active lease until {exp_str}."
                    except Exception:
                        pass

            cursor.execute("""
            UPDATE sitemap_refresh_runs
            SET lease_token = ?, lease_expires_at = ?, heartbeat_at = ?, status = 'running', stage = 'RUNNING'
            WHERE id = ?
            """, (lease_token, expires_at, now_iso, run_id))
            conn.commit()
            return True, None

    def renew_indexing_heartbeat(
        self,
        run_id: str,
        stage: str,
        last_processed_url: Optional[str] = None,
        lease_duration_seconds: int = 180
    ) -> bool:
        """Updates heartbeat and extends lease independently of slow embeddings/fetches."""
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(seconds=lease_duration_seconds)).isoformat()
        now_iso = now.isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE sitemap_refresh_runs
            SET heartbeat_at = ?, lease_expires_at = ?, stage = ?, last_processed_url = COALESCE(?, last_processed_url)
            WHERE id = ?
            """, (now_iso, expires_at, stage, last_processed_url, run_id))
            conn.commit()
            return cursor.rowcount > 0

    def release_indexing_lease(
        self,
        run_id: str,
        final_status: str,
        error_details: Optional[str] = None
    ) -> None:
        """Releases lease upon job completion or termination."""
        now_iso = iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE sitemap_refresh_runs
            SET lease_token = NULL, lease_expires_at = NULL, heartbeat_at = ?, status = ?, stage = ?, completed_at = ?, error_details = ?
            WHERE id = ?
            """, (now_iso, final_status, final_status.upper(), now_iso, error_details, run_id))
            conn.commit()

    def recover_stale_runs(self, stale_timeout_minutes: int = 5):
        """
        Detects any refresh runs marked 'running' that have had no heartbeat updates in more than
        stale_timeout_minutes (caused when the background worker is interrupted by server reload/restart).
        Transitions them to 'interrupted' or 'completed' so that sitemaps do not stay stuck in 'indexing'.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, sitemap_id, started_at, heartbeat_at, last_successful_fetch_at, total_successfully_fetched_urls "
                    "FROM sitemap_refresh_runs WHERE status = 'running'"
                )
                stale_runs = cursor.fetchall()
                if not stale_runs:
                    return
                now = datetime.now(timezone.utc)
                now_iso = now.isoformat()
                for r in stale_runs:
                    # Check heartbeat_at first; fall back to last_successful_fetch_at or started_at
                    last_time_str = r["heartbeat_at"] or r["last_successful_fetch_at"] or r["started_at"]
                    if last_time_str:
                        try:
                            last_time = datetime.fromisoformat(last_time_str.replace("Z", "+00:00"))
                            if (now - last_time).total_seconds() > (stale_timeout_minutes * 60):
                                cursor.execute(
                                    "UPDATE sitemap_refresh_runs SET status = 'interrupted', stage = 'INTERRUPTED', completed_at = ?, lease_token = NULL, lease_expires_at = NULL WHERE id = ?",
                                    (now_iso, r["id"])
                                )
                                cursor.execute("SELECT COUNT(*) FROM articles WHERE sitemap_id = ?", (r["sitemap_id"],))
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
            if user_id in ("service_internal", "admin"):
                cursor.execute("SELECT * FROM sitemaps ORDER BY created_at DESC")
            else:
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
                    canonical_root_url=row["canonical_root_url"] if "canonical_root_url" in row.keys() and row["canonical_root_url"] else canonicalize_url(row["root_url"], is_sitemap=True),
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
                    next_refresh_at=row["next_refresh_at"] if "next_refresh_at" in row.keys() else None,
                    last_refresh_started_at=row["last_refresh_started_at"] if "last_refresh_started_at" in row.keys() else None,
                    last_refresh_completed_at=row["last_refresh_completed_at"] if "last_refresh_completed_at" in row.keys() else None,
                    schedule_status=row["schedule_status"] if ("schedule_status" in row.keys() and row["schedule_status"]) else "active",
                    created_at=row["created_at"],
                    updated_at=row["updated_at"]
                ))
            return items

    def get_sitemap(self, sitemap_id: str, user_id: Optional[str] = None) -> Optional[SitemapItem]:
        self.recover_stale_runs()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id and user_id not in ("service_internal", "admin"):
                cursor.execute("SELECT * FROM sitemaps WHERE id = ? AND user_id = ?", (sitemap_id, user_id))
            else:
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
                canonical_root_url=row["canonical_root_url"] if "canonical_root_url" in row.keys() and row["canonical_root_url"] else canonicalize_url(row["root_url"], is_sitemap=True),
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
                next_refresh_at=row["next_refresh_at"] if "next_refresh_at" in row.keys() else None,
                last_refresh_started_at=row["last_refresh_started_at"] if "last_refresh_started_at" in row.keys() else None,
                last_refresh_completed_at=row["last_refresh_completed_at"] if "last_refresh_completed_at" in row.keys() else None,
                schedule_status=row["schedule_status"] if ("schedule_status" in row.keys() and row["schedule_status"]) else "active",
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

    def confirm_sitemap(self, sitemap_id: str, user_id: Optional[str] = None) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = iso_now()
            if user_id and user_id not in ("service_internal", "admin"):
                cursor.execute("""
                UPDATE sitemaps
                SET status = 'confirmed', last_confirmed_at = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """, (now, now, sitemap_id, user_id))
            else:
                cursor.execute("""
                UPDATE sitemaps
                SET status = 'confirmed', last_confirmed_at = ?, updated_at = ?
                WHERE id = ?
                """, (now, now, sitemap_id))
            conn.commit()
            return cursor.rowcount > 0

    def delete_sitemap(self, sitemap_id: str, user_id: str) -> bool:
        """Removes a registered sitemap for the authenticated user without affecting other users."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id in ("service_internal", "admin"):
                cursor.execute("DELETE FROM sitemaps WHERE id = ?", (sitemap_id,))
            else:
                cursor.execute("DELETE FROM sitemaps WHERE id = ? AND user_id = ?", (sitemap_id, user_id))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted

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
    def create_refresh_run(
        self,
        sitemap_id: str,
        user_id: str = "default_user",
        total_discovered: int = 0,
        resumed_from_run_id: Optional[str] = None
    ) -> RefreshRunSummary:
        run_id = f"run_{uuid.uuid4().hex[:10]}"
        now = iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO sitemap_refresh_runs (
                id, sitemap_id, user_id, started_at, heartbeat_at, total_discovered_urls,
                status, stage, progress_percent, resumed_from_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, 'running', 'QUEUED', 0.0, ?)
            """, (run_id, sitemap_id, user_id, now, now, total_discovered, resumed_from_run_id))
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
                stage = COALESCE(?, stage),
                progress_percent = ?,
                heartbeat_at = COALESCE(?, heartbeat_at),
                last_processed_url = COALESCE(?, last_processed_url),
                error_details = COALESCE(?, error_details),
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
                summary.stage,
                summary.progress_percent,
                summary.heartbeat_at,
                summary.last_processed_url,
                summary.error_details,
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
                stage=row["stage"] if "stage" in row.keys() and row["stage"] else "COMPLETED",
                progress_percent=row["progress_percent"],
                lease_token=row["lease_token"] if "lease_token" in row.keys() else None,
                lease_expires_at=row["lease_expires_at"] if "lease_expires_at" in row.keys() else None,
                heartbeat_at=row["heartbeat_at"] if "heartbeat_at" in row.keys() else None,
                resumed_from_run_id=row["resumed_from_run_id"] if "resumed_from_run_id" in row.keys() else None,
                last_processed_url=row["last_processed_url"] if "last_processed_url" in row.keys() else None,
                error_details=row["error_details"] if "error_details" in row.keys() else None,
                estimate=est
            )

    def get_refresh_runs(self, user_id: Optional[str] = None, sitemap_id: Optional[str] = None, limit: int = 20) -> List[RefreshRunSummary]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conditions = []
            params = []
            if user_id and user_id not in ("service_internal", "admin"):
                conditions.append("user_id = ?")
                params.append(user_id)
            if sitemap_id:
                conditions.append("sitemap_id = ?")
                params.append(sitemap_id)
            
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            query = f"SELECT * FROM sitemap_refresh_runs {where_clause} ORDER BY started_at DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, tuple(params))
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
                    stage=row["stage"] if "stage" in row.keys() and row["stage"] else "COMPLETED",
                    progress_percent=row["progress_percent"],
                    lease_token=row["lease_token"] if "lease_token" in row.keys() else None,
                    lease_expires_at=row["lease_expires_at"] if "lease_expires_at" in row.keys() else None,
                    heartbeat_at=row["heartbeat_at"] if "heartbeat_at" in row.keys() else None,
                    resumed_from_run_id=row["resumed_from_run_id"] if "resumed_from_run_id" in row.keys() else None,
                    last_processed_url=row["last_processed_url"] if "last_processed_url" in row.keys() else None,
                    error_details=row["error_details"] if "error_details" in row.keys() else None,
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

    record_refresh_run_url = record_run_url

    def get_refresh_run_detail(self, run_id: str, user_id: Optional[str] = None, search: Optional[str] = None, status_filter: Optional[str] = None, limit: int = 500, offset: int = 0) -> Optional[RefreshRunDetail]:
        summary = self.get_refresh_run_summary(run_id)
        if not summary:
            return None
        if user_id and user_id not in ("service_internal", "admin") and summary.user_id != user_id:
            # Enforce user isolation: if run does not belong to user, refuse access
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

    def update_url_health(
        self,
        url: str,
        sitemap_id: Optional[str] = None,
        http_status: int = 200,
        is_in_sitemap: bool = True,
        threshold_x: int = 3,
        action_rule: str = "QUARANTINE_ON_THRESHOLD",
        error_reason: Optional[str] = None,
        content_valid: bool = True,
        user_id: Optional[str] = None,
        redirect_url: Optional[str] = None,
        **kwargs
    ) -> URLHealthStatus:
        if "in_sitemap" in kwargs:
            is_in_sitemap = kwargs["in_sitemap"]
        if "failure_reason" in kwargs and not error_reason:
            error_reason = kwargs["failure_reason"]
        if "is_healthy" in kwargs:
            content_valid = kwargs["is_healthy"] if http_status == 200 else False
        now = iso_now()
        canon_url = canonicalize_url(url, is_sitemap=False)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM url_health_status WHERE url = ?", (canon_url,))
            row = cursor.fetchone()

            # Determine user_id from sitemap if not passed
            effective_user = user_id or (row["user_id"] if row and "user_id" in row.keys() else None)
            if not effective_user and sitemap_id:
                cursor.execute("SELECT user_id FROM sitemaps WHERE id = ?", (sitemap_id,))
                sm_row = cursor.fetchone()
                if sm_row:
                    effective_user = sm_row["user_id"]
            effective_user = effective_user or "default_user"

            history = []
            if row and "action_history_json" in row.keys() and row["action_history_json"]:
                try:
                    history = json.loads(row["action_history_json"])
                except Exception:
                    history = []

            # Success condition: HTTP 200 AND valid content resets failure count
            is_healthy = (http_status == 200 and content_valid)
            last_successful = row["last_successful_fetch_at"] if row and "last_successful_fetch_at" in row.keys() else None

            if is_healthy:
                consecutive = 0
                reason = None
                pending_act = "NONE"
                expected_act = "Healthy (reset to 0 failures)"
                last_successful = now
                history.append({"action": "HEALTHY_RESET", "http_status": 200, "timestamp": now})
            else:
                consecutive = (row["consecutive_failure_count"] if row else 0) + 1
                if not content_valid and http_status == 200:
                    reason = error_reason or "Invalid content / challenge page"
                else:
                    reason = error_reason or f"HTTP {http_status}"

                if consecutive < threshold_x:
                    pending_act = None
                    expected_act = f"Pending verification ({consecutive}/{threshold_x} failures; next: {action_rule})"
                else:
                    if action_rule == "FLAG_FOR_REVIEW":
                        pending_act = "FLAG_FOR_REVIEW"
                        expected_act = "Flagged for human review"
                    elif action_rule == "ARCHIVE_ON_THRESHOLD":
                        pending_act = "ARCHIVE"
                        expected_act = "Eligible for archive"
                    else:
                        pending_act = "QUARANTINE"
                        expected_act = "Eligible for quarantine"
                history.append({
                    "action": pending_act,
                    "consecutive_failures": consecutive,
                    "reason": reason,
                    "timestamp": now
                })

            cursor.execute("""
            INSERT INTO url_health_status (
                url, canonical_url, user_id, sitemap_id, consecutive_failure_count,
                configured_threshold, expected_action, pending_action, action_rule,
                redirect_destination_url, last_checked_at, last_successful_fetch_at,
                last_attempted_fetch_at, last_http_status, is_in_sitemap, is_healthy,
                failure_reason, action_history_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                canonical_url = excluded.canonical_url,
                user_id = COALESCE(excluded.user_id, url_health_status.user_id),
                sitemap_id = COALESCE(excluded.sitemap_id, url_health_status.sitemap_id),
                consecutive_failure_count = excluded.consecutive_failure_count,
                configured_threshold = excluded.configured_threshold,
                expected_action = excluded.expected_action,
                pending_action = excluded.pending_action,
                action_rule = excluded.action_rule,
                redirect_destination_url = excluded.redirect_destination_url,
                last_checked_at = excluded.last_checked_at,
                last_successful_fetch_at = COALESCE(excluded.last_successful_fetch_at, url_health_status.last_successful_fetch_at),
                last_attempted_fetch_at = excluded.last_attempted_fetch_at,
                last_http_status = excluded.last_http_status,
                is_in_sitemap = excluded.is_in_sitemap,
                is_healthy = excluded.is_healthy,
                failure_reason = excluded.failure_reason,
                action_history_json = excluded.action_history_json
            """, (
                canon_url, canon_url, effective_user, sitemap_id, consecutive,
                threshold_x, expected_act, pending_act, action_rule,
                redirect_url, now, last_successful, now, http_status,
                1 if is_in_sitemap else 0, 1 if is_healthy else 0, reason, json.dumps(history[-50:])
            ))
            conn.commit()

            return URLHealthStatus(
                url=canon_url,
                canonical_url=canon_url,
                user_id=effective_user,
                sitemap_id=sitemap_id,
                consecutive_failure_count=consecutive,
                configured_threshold=threshold_x,
                expected_action=expected_act,
                pending_action=pending_act,
                action_rule=action_rule,
                redirect_destination_url=redirect_url,
                last_checked_at=now,
                last_successful_fetch_at=last_successful,
                last_attempted_fetch_at=now,
                last_http_status=http_status,
                is_in_sitemap=is_in_sitemap,
                is_healthy=bool(is_healthy),
                failure_reason=reason,
                action_history=history[-50:]
            )

    def cancel_pending_url_action(self, url: str, user_id: Optional[str] = None) -> bool:
        canon_url = canonicalize_url(url, is_sitemap=False)
        now = iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM url_health_status WHERE url = ?", (canon_url,))
            row = cursor.fetchone()
            if not row:
                return False
            if user_id and user_id not in ("service_internal", "admin"):
                if row["user_id"] and row["user_id"] != user_id:
                    return False
            history = []
            if "action_history_json" in row.keys() and row["action_history_json"]:
                try:
                    history = json.loads(row["action_history_json"])
                except Exception:
                    pass
            history.append({"action": "CANCEL_PENDING_ACTION", "timestamp": now, "by": user_id or "default_user"})
            cursor.execute("""
            UPDATE url_health_status
            SET pending_action = 'NONE', expected_action = 'Pending action cancelled by user', action_history_json = ?
            WHERE url = ?
            """, (json.dumps(history[-50:]), canon_url))
            conn.commit()
            return True

    def get_url_health_statuses(
        self,
        user_id: Optional[str] = None,
        sitemap_id: Optional[str] = None,
        status_filter: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[URLHealthStatus], int]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conditions = []
            params = []

            if user_id and user_id not in ("service_internal", "admin"):
                conditions.append("(h.user_id = ? OR s.user_id = ?)")
                params.extend([user_id, user_id])

            if sitemap_id:
                conditions.append("h.sitemap_id = ?")
                params.append(sitemap_id)

            if status_filter:
                if status_filter.upper() == "HEALTHY":
                    conditions.append("h.is_healthy = 1")
                elif status_filter.upper() == "UNHEALTHY":
                    conditions.append("h.is_healthy = 0")
                elif status_filter.upper() == "PENDING":
                    conditions.append("h.pending_action != 'NONE'")
                elif status_filter.upper() == "404":
                    conditions.append("h.last_http_status = 404")
                elif status_filter.upper() == "301":
                    conditions.append("h.last_http_status = 301")

            if search:
                conditions.append("(h.url LIKE ? OR h.failure_reason LIKE ?)")
                s_param = f"%{search}%"
                params.extend([s_param, s_param])

            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

            # Count total
            count_sql = f"SELECT COUNT(*) FROM url_health_status h LEFT JOIN sitemaps s ON h.sitemap_id = s.id {where_clause}"
            cursor.execute(count_sql, tuple(params))
            total_count = cursor.fetchone()[0]

            # Select page
            select_sql = f"""
            SELECT h.* FROM url_health_status h
            LEFT JOIN sitemaps s ON h.sitemap_id = s.id
            {where_clause}
            ORDER BY h.consecutive_failure_count DESC, h.last_checked_at DESC
            LIMIT ? OFFSET ?
            """
            cursor.execute(select_sql, tuple(params + [limit, offset]))

            results = []
            for row in cursor.fetchall():
                hist = []
                if "action_history_json" in row.keys() and row["action_history_json"]:
                    try:
                        hist = json.loads(row["action_history_json"])
                    except Exception:
                        hist = []
                results.append(URLHealthStatus(
                    url=row["url"],
                    canonical_url=row["canonical_url"] if "canonical_url" in row.keys() and row["canonical_url"] else row["url"],
                    user_id=row["user_id"] if "user_id" in row.keys() else "default_user",
                    sitemap_id=row["sitemap_id"],
                    consecutive_failure_count=row["consecutive_failure_count"],
                    configured_threshold=row["configured_threshold"],
                    expected_action=row["expected_action"],
                    pending_action=row["pending_action"] if "pending_action" in row.keys() and row["pending_action"] else "NONE",
                    action_rule=row["action_rule"] if "action_rule" in row.keys() and row["action_rule"] else "QUARANTINE_ON_THRESHOLD",
                    redirect_destination_url=row["redirect_destination_url"] if "redirect_destination_url" in row.keys() else None,
                    last_checked_at=row["last_checked_at"],
                    last_successful_fetch_at=row["last_successful_fetch_at"] if "last_successful_fetch_at" in row.keys() else None,
                    last_attempted_fetch_at=row["last_attempted_fetch_at"] if "last_attempted_fetch_at" in row.keys() else row["last_checked_at"],
                    last_http_status=row["last_http_status"],
                    is_in_sitemap=bool(row["is_in_sitemap"]),
                    is_healthy=bool(row["is_healthy"]) if "is_healthy" in row.keys() and row["is_healthy"] is not None else (row["last_http_status"] == 200),
                    failure_reason=row["failure_reason"],
                    action_history=hist
                ))
            return results, total_count

    # -------------------------------------------------------------
    # Phase B: Sitemap Scheduling Database Methods
    # -------------------------------------------------------------
    def update_sitemap_schedule(
        self,
        sitemap_id: str,
        refresh_interval_days: Optional[int] = None,
        schedule_status: Optional[str] = None,
        next_refresh_at: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Optional[SitemapItem]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sitemaps WHERE id = ?", (sitemap_id,))
            row = cursor.fetchone()
            if not row:
                return None
            if user_id and user_id not in ("service_internal", "admin"):
                if row["user_id"] and row["user_id"] != user_id:
                    return None

            now = iso_now()
            intv = refresh_interval_days if refresh_interval_days is not None else (row["refresh_interval_days"] or 1)
            sched_stat = schedule_status if schedule_status is not None else (row["schedule_status"] or "active")

            if next_refresh_at is not None:
                next_due = next_refresh_at
            elif refresh_interval_days is not None or row["next_refresh_at"] is None:
                next_due = (datetime.now(timezone.utc) + timedelta(days=intv)).isoformat()
            else:
                next_due = row["next_refresh_at"]

            cursor.execute("""
            UPDATE sitemaps
            SET refresh_interval_days = ?, schedule_status = ?, next_refresh_at = ?, updated_at = ?
            WHERE id = ?
            """, (intv, sched_stat, next_due, now, sitemap_id))
            conn.commit()

        return self.get_sitemap(sitemap_id, user_id=user_id)

    def get_due_sitemaps(self, now_iso: Optional[str] = None) -> List[Dict[str, Any]]:
        ref_time = now_iso or iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM sitemaps
            WHERE (schedule_status = 'active' OR schedule_status IS NULL)
              AND (next_refresh_at IS NULL OR next_refresh_at <= ?)
              AND status != 'indexing'
            ORDER BY next_refresh_at ASC, updated_at ASC
            """, (ref_time,))
            return [dict(r) for r in cursor.fetchall()]

    def record_sitemap_refresh_start(self, sitemap_id: str, run_id: str):
        now = iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE sitemaps
            SET last_refresh_started_at = ?, status = 'indexing', updated_at = ?
            WHERE id = ?
            """, (now, now, sitemap_id))
            conn.commit()

    def record_sitemap_refresh_complete(self, sitemap_id: str, run_id: str, success: bool = True, interval_days: Optional[int] = None):
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT refresh_interval_days FROM sitemaps WHERE id = ?", (sitemap_id,))
            row = cursor.fetchone()
            days = interval_days or (row["refresh_interval_days"] if row else 1) or 1
            next_due = (now_dt + timedelta(days=days)).isoformat()
            new_status = "active" if success else "interrupted"

            cursor.execute("""
            UPDATE sitemaps
            SET last_refresh_completed_at = ?, next_refresh_at = ?, status = ?, updated_at = ?
            WHERE id = ?
            """, (now, next_due, new_status, now, sitemap_id))
            conn.commit()

    def get_scheduler_status(self) -> Dict[str, Any]:
        now = iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sitemaps WHERE schedule_status = 'active' OR schedule_status IS NULL")
            total_scheduled = cursor.fetchone()[0]

            cursor.execute("""
            SELECT COUNT(*) FROM sitemaps
            WHERE (schedule_status = 'active' OR schedule_status IS NULL)
              AND (next_refresh_at IS NULL OR next_refresh_at <= ?)
              AND status != 'indexing'
            """, (now,))
            due_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM sitemap_refresh_runs WHERE status = 'running'")
            active_jobs = cursor.fetchone()[0]

            cursor.execute("SELECT MAX(started_at) FROM sitemap_refresh_runs")
            last_run = cursor.fetchone()[0]

            return {
                "is_running": True,
                "total_scheduled_sitemaps": total_scheduled,
                "due_sitemaps_count": due_count,
                "active_jobs_count": active_jobs,
                "last_run_started_at": last_run,
                "server_time_utc": now
            }

    # -------------------------------------------------------------
    # Phase E: Redirect History Database Methods
    # -------------------------------------------------------------
    def record_article_redirect(
        self,
        source_url: str,
        destination_url: str,
        http_status: int = 301,
        hop_count: int = 1,
        redirect_chain: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        sitemap_id: Optional[str] = None,
        replacement_indexed: bool = False,
        replacement_article_url: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        rec_id = f"red_{uuid.uuid4().hex[:10]}"
        now = iso_now()
        canon_src = canonicalize_url(source_url, is_sitemap=False)
        canon_dest = canonicalize_url(destination_url, is_sitemap=False)
        chain_json = json.dumps(redirect_chain or [canon_src, canon_dest])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            eff_user = user_id
            if not eff_user and sitemap_id:
                cursor.execute("SELECT user_id FROM sitemaps WHERE id = ?", (sitemap_id,))
                sm_row = cursor.fetchone()
                if sm_row:
                    eff_user = sm_row["user_id"]
            eff_user = eff_user or "default_user"

            cursor.execute("""
            INSERT INTO article_redirects (
                id, user_id, sitemap_id, source_url, destination_url, http_status,
                hop_count, redirect_chain_json, detected_at, replacement_indexed,
                replacement_article_url, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec_id, eff_user, sitemap_id, canon_src, canon_dest, http_status,
                hop_count, chain_json, now, 1 if replacement_indexed else 0,
                replacement_article_url or (canon_dest if replacement_indexed else None), notes
            ))
            conn.commit()

            return {
                "id": rec_id,
                "source_url": canon_src,
                "destination_url": canon_dest,
                "http_status": http_status,
                "hop_count": hop_count,
                "redirect_chain": redirect_chain or [canon_src, canon_dest],
                "detected_at": now,
                "replacement_indexed": replacement_indexed,
                "replacement_article_url": replacement_article_url or (canon_dest if replacement_indexed else None),
                "notes": notes
            }

    def mark_redirect_replacement_indexed(self, source_url: str, replacement_article_url: str):
        canon_src = canonicalize_url(source_url, is_sitemap=False)
        canon_repl = canonicalize_url(replacement_article_url, is_sitemap=False)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE article_redirects
            SET replacement_indexed = 1, replacement_article_url = ?
            WHERE source_url = ?
            """, (canon_repl, canon_src))
            conn.commit()

    def get_article_redirects(self, user_id: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id and user_id not in ("service_internal", "admin"):
                cursor.execute("""
                SELECT r.* FROM article_redirects r
                LEFT JOIN sitemaps s ON r.sitemap_id = s.id
                WHERE r.user_id = ? OR s.user_id = ?
                ORDER BY r.detected_at DESC
                LIMIT ? OFFSET ?
                """, (user_id, user_id, limit, offset))
            else:
                cursor.execute("SELECT * FROM article_redirects ORDER BY detected_at DESC LIMIT ? OFFSET ?", (limit, offset))
            
            results = []
            for row in cursor.fetchall():
                chain = []
                if row["redirect_chain_json"]:
                    try:
                        chain = json.loads(row["redirect_chain_json"])
                    except Exception:
                        pass
                results.append({
                    "id": row["id"],
                    "source_url": row["source_url"],
                    "destination_url": row["destination_url"],
                    "http_status": row["http_status"],
                    "hop_count": row["hop_count"],
                    "redirect_chain": chain,
                    "detected_at": row["detected_at"],
                    "replacement_indexed": bool(row["replacement_indexed"]),
                    "replacement_article_url": row["replacement_article_url"],
                    "notes": row["notes"]
                })
            return results

    def get_redirect_for_url(self, url: str) -> Optional[Dict[str, Any]]:
        canon_url = canonicalize_url(url, is_sitemap=False)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM article_redirects WHERE source_url = ? ORDER BY detected_at DESC LIMIT 1", (canon_url,))
            row = cursor.fetchone()
            if not row:
                return None
            chain = []
            if row["redirect_chain_json"]:
                try:
                    chain = json.loads(row["redirect_chain_json"])
                except Exception:
                    pass
            return {
                "id": row["id"],
                "source_url": row["source_url"],
                "destination_url": row["destination_url"],
                "http_status": row["http_status"],
                "hop_count": row["hop_count"],
                "redirect_chain": chain,
                "detected_at": row["detected_at"],
                "replacement_indexed": bool(row["replacement_indexed"]),
                "replacement_article_url": row["replacement_article_url"],
                "notes": row["notes"]
            }

    # -------------------------------------------------------------
    # Phase F & G: Archived Knowledge Base Methods
    # -------------------------------------------------------------
    def archive_article(
        self,
        url: str,
        sitemap_id: Optional[str] = None,
        user_id: Optional[str] = None,
        reason: str = "QUARANTINE_THRESHOLD_REACHED",
        last_http_status: int = 404,
        replacement_url: Optional[str] = None,
        retention_preset: str = "30d",
        retention_days: int = 30
    ) -> Optional[Dict[str, Any]]:
        canon_url = canonicalize_url(url, is_sitemap=False)
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        expires_at = (now_dt + timedelta(days=retention_days)).isoformat()
        rec_id = f"arc_{uuid.uuid4().hex[:10]}"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM articles WHERE url = ?", (canon_url,))
            art_row = cursor.fetchone()
            if not art_row:
                return None

            cursor.execute("SELECT * FROM chunks WHERE article_url = ?", (canon_url,))
            chunk_rows = cursor.fetchall()
            chunks_data = [dict(c) for c in chunk_rows]

            eff_user = user_id or art_row["user_id"] or "default_user"
            eff_sitemap = sitemap_id or art_row["sitemap_id"]

            audit_entry = {
                "action": "ARCHIVED",
                "reason": reason,
                "last_http_status": last_http_status,
                "timestamp": now,
                "by": eff_user
            }

            cursor.execute("""
            INSERT INTO archived_articles (
                id, url, canonical_url, sitemap_id, user_id, title, content,
                chunks_json, embeddings_json, original_indexed_at, archived_at,
                archive_reason, last_known_http_status, replacement_url,
                last_successful_version, restore_eligible, retention_preset,
                retention_days, retention_expires_at, audit_history_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """, (
                rec_id, canon_url, canon_url, eff_sitemap, eff_user, art_row["title"],
                art_row["body_text"], json.dumps(chunks_data), art_row["images_json"],
                art_row["crawled_at"], now, str(reason), last_http_status,
                replacement_url, art_row["extraction_version"] or "2.0",
                retention_preset, retention_days, expires_at, json.dumps([audit_entry])
            ))

            cursor.execute("""
            UPDATE articles
            SET status = 'archived', is_quarantined = 1, quarantine_reason = ?
            WHERE url = ?
            """, (str(reason), canon_url))
            conn.commit()

            return {
                "id": rec_id,
                "url": canon_url,
                "canonical_url": canon_url,
                "sitemap_id": eff_sitemap,
                "user_id": eff_user,
                "title": art_row["title"],
                "content": art_row["body_text"],
                "chunks_count": len(chunks_data),
                "original_indexed_at": art_row["crawled_at"],
                "archived_at": now,
                "archive_reason": str(reason),
                "last_known_http_status": last_http_status,
                "replacement_url": replacement_url,
                "restore_eligible": True,
                "retention_preset": retention_preset,
                "retention_days": retention_days,
                "retention_expires_at": expires_at,
                "audit_history": [audit_entry]
            }

    def get_archived_articles(
        self,
        user_id: Optional[str] = None,
        sitemap_id: Optional[str] = None,
        search: Optional[str] = None,
        reason: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[ArchivedArticleItem], int]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conditions = []
            params = []

            if user_id and user_id not in ("service_internal", "admin"):
                conditions.append("(a.user_id = ? OR s.user_id = ?)")
                params.extend([user_id, user_id])

            if sitemap_id:
                conditions.append("a.sitemap_id = ?")
                params.append(sitemap_id)

            if reason:
                conditions.append("a.archive_reason = ?")
                params.append(reason)

            if search:
                conditions.append("(a.title LIKE ? OR a.url LIKE ?)")
                s_param = f"%{search}%"
                params.extend([s_param, s_param])

            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

            count_sql = f"SELECT COUNT(*) FROM archived_articles a LEFT JOIN sitemaps s ON a.sitemap_id = s.id {where_clause}"
            cursor.execute(count_sql, tuple(params))
            total_count = cursor.fetchone()[0]

            select_sql = f"""
            SELECT a.* FROM archived_articles a
            LEFT JOIN sitemaps s ON a.sitemap_id = s.id
            {where_clause}
            ORDER BY a.archived_at DESC
            LIMIT ? OFFSET ?
            """
            cursor.execute(select_sql, tuple(params + [limit, offset]))

            items = []
            for row in cursor.fetchall():
                chunks_data = json.loads(row["chunks_json"]) if row["chunks_json"] else []
                items.append(ArchivedArticleItem(
                    id=row["id"],
                    url=row["url"],
                    canonical_url=row["canonical_url"] or row["url"],
                    sitemap_id=row["sitemap_id"],
                    user_id=row["user_id"] or "default_user",
                    title=row["title"],
                    chunks_count=len(chunks_data),
                    original_indexed_at=row["original_indexed_at"],
                    archived_at=row["archived_at"],
                    archive_reason=row["archive_reason"],
                    last_known_http_status=row["last_known_http_status"],
                    replacement_url=row["replacement_url"],
                    restore_eligible=bool(row["restore_eligible"]),
                    retention_preset=row["retention_preset"] or "30d",
                    retention_days=row["retention_days"] or 30,
                    retention_expires_at=row["retention_expires_at"]
                ))
            return items, total_count

    def get_archived_article_detail(self, id_or_url: str, user_id: Optional[str] = None) -> Optional[ArchivedArticleDetail]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT a.*, s.user_id as sitemap_user_id
            FROM archived_articles a
            LEFT JOIN sitemaps s ON a.sitemap_id = s.id
            WHERE a.id = ? OR a.url = ?
            ORDER BY a.archived_at DESC LIMIT 1
            """, (id_or_url, id_or_url))
            row = cursor.fetchone()
            if not row:
                return None

            if user_id and user_id not in ("service_internal", "admin"):
                owner = row["user_id"] or row["sitemap_user_id"]
                if owner and owner != user_id:
                    return None

            chunks_data = json.loads(row["chunks_json"]) if row["chunks_json"] else []
            history = json.loads(row["audit_history_json"]) if row["audit_history_json"] else []

            return ArchivedArticleDetail(
                id=row["id"],
                url=row["url"],
                canonical_url=row["canonical_url"] or row["url"],
                sitemap_id=row["sitemap_id"],
                user_id=row["user_id"] or "default_user",
                title=row["title"],
                content=row["content"],
                chunks_count=len(chunks_data),
                chunks_preview=[c.get("text", "")[:300] for c in chunks_data[:5]],
                original_indexed_at=row["original_indexed_at"],
                archived_at=row["archived_at"],
                archive_reason=row["archive_reason"],
                last_known_http_status=row["last_known_http_status"],
                replacement_url=row["replacement_url"],
                last_successful_version=row["last_successful_version"] or "2.0",
                restore_eligible=bool(row["restore_eligible"]),
                retention_preset=row["retention_preset"] or "30d",
                retention_days=row["retention_days"] or 30,
                retention_expires_at=row["retention_expires_at"],
                audit_history=history
            )

    def restore_archived_article(self, id_or_url: str, user_id: Optional[str] = None, notes: Optional[str] = None) -> bool:
        """
        Restores an archived article to active knowledge base with full audit logging.
        Enforces user ownership isolation (rejects cross-user restores).
        """
        now = iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT a.*, s.user_id as sitemap_user_id
            FROM archived_articles a
            LEFT JOIN sitemaps s ON a.sitemap_id = s.id
            WHERE a.id = ? OR a.url = ?
            ORDER BY a.archived_at DESC LIMIT 1
            """, (id_or_url, id_or_url))
            row = cursor.fetchone()
            if not row:
                return False

            if user_id and user_id not in ("service_internal", "admin"):
                owner = row["user_id"] or row["sitemap_user_id"]
                if owner and owner != user_id:
                    return False

            target_url = row["url"]

            history = []
            if row["audit_history_json"]:
                try:
                    history = json.loads(row["audit_history_json"])
                except Exception:
                    pass
            history.append({
                "action": "RESTORED",
                "timestamp": now,
                "by": user_id or "default_user",
                "notes": notes or "Restored by user request"
            })

            cursor.execute("""
            UPDATE archived_articles
            SET restore_eligible = 1, audit_history_json = ?
            WHERE id = ?
            """, (json.dumps(history), row["id"]))

            cursor.execute("""
            UPDATE articles
            SET status = 'active', is_quarantined = 0, quarantine_reason = NULL
            WHERE url = ?
            """, (target_url,))

            cursor.execute("""
            UPDATE url_health_status
            SET consecutive_failure_count = 0, failure_reason = NULL, pending_action = 'NONE', is_healthy = 1
            WHERE url = ?
            """, (target_url,))

            cursor.execute("UPDATE quarantine_records SET restored_at = ? WHERE url = ?", (now, target_url))

            conn.commit()
            return True

    def update_archive_retention(self, id_or_url: str, retention_preset: str, retention_days: int, user_id: Optional[str] = None) -> bool:
        now_dt = datetime.now(timezone.utc)
        new_expires = (now_dt + timedelta(days=retention_days)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT a.*, s.user_id as sitemap_user_id
            FROM archived_articles a
            LEFT JOIN sitemaps s ON a.sitemap_id = s.id
            WHERE a.id = ? OR a.url = ?
            LIMIT 1
            """, (id_or_url, id_or_url))
            row = cursor.fetchone()
            if not row:
                return False

            if user_id and user_id not in ("service_internal", "admin"):
                owner = row["user_id"] or row["sitemap_user_id"]
                if owner and owner != user_id:
                    return False

            cursor.execute("""
            UPDATE archived_articles
            SET retention_preset = ?, retention_days = ?, retention_expires_at = ?
            WHERE id = ?
            """, (retention_preset, retention_days, new_expires, row["id"]))
            conn.commit()
            return True

    # -------------------------------------------------------------
    # Phase H: Article Version History Database Methods
    # -------------------------------------------------------------
    def get_article_versions(self, url: str, user_id: Optional[str] = None) -> List[ArticleHistoryItem]:
        canon_url = canonicalize_url(url, is_sitemap=False)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id and user_id not in ("service_internal", "admin"):
                cursor.execute("""
                SELECT h.* FROM article_history h
                WHERE h.url = ? AND (h.user_id = ? OR h.user_id = 'default_user')
                ORDER BY h.recorded_at DESC
                """, (canon_url, user_id))
            else:
                cursor.execute("SELECT * FROM article_history WHERE url = ? ORDER BY recorded_at DESC", (canon_url,))
            
            items = []
            for row in cursor.fetchall():
                items.append(ArticleHistoryItem(
                    id=row["id"],
                    url=row["url"],
                    user_id=row["user_id"] if "user_id" in row.keys() else "default_user",
                    sitemap_id=row["sitemap_id"] if "sitemap_id" in row.keys() else None,
                    version=row["version"] or "2.0",
                    title=row["title"] or "",
                    previous_title=row["previous_title"] if "previous_title" in row.keys() else None,
                    new_title=row["new_title"] if "new_title" in row.keys() else None,
                    change_type=row["change_type"] or "UPDATE",
                    change_classification=row["change_classification"] if "change_classification" in row.keys() else "CONTENT_UPDATE",
                    previous_hash=row["previous_hash"],
                    new_hash=row["new_hash"],
                    summary_diff=row["summary_diff"],
                    extraction_version=row["extraction_version"] if "extraction_version" in row.keys() else "2.0",
                    embedding_model=row["embedding_model"] if "embedding_model" in row.keys() else "BAAI/bge-small-en-v1.5",
                    embedding_version=row["embedding_version"] if "embedding_version" in row.keys() else "1.0",
                    refresh_run_id=row["refresh_run_id"] if "refresh_run_id" in row.keys() else None,
                    recorded_at=row["recorded_at"]
                ))
            return items

    def get_article_version_diff(self, version_id_1: str, version_id_2: str) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM article_history WHERE id = ?", (version_id_1,))
            v1 = cursor.fetchone()
            cursor.execute("SELECT * FROM article_history WHERE id = ?", (version_id_2,))
            v2 = cursor.fetchone()

            if not v1 or not v2:
                return {"error": "One or both versions not found"}

            text1 = v1["content_snapshot"] or ""
            text2 = v2["content_snapshot"] or ""

            import difflib
            diff_lines = list(difflib.unified_diff(
                text1.splitlines(),
                text2.splitlines(),
                fromfile=f"Version {v1['id']} ({v1['recorded_at']})",
                tofile=f"Version {v2['id']} ({v2['recorded_at']})",
                lineterm=""
            ))

            return {
                "version_1": dict(v1),
                "version_2": dict(v2),
                "title_changed": v1["title"] != v2["title"],
                "hash_changed": v1["new_hash"] != v2["new_hash"],
                "unified_diff": "\n".join(diff_lines[:200]),
                "total_diff_lines": len(diff_lines)
            }

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

            # Determine sitemap user_id for isolation
            user_id = None
            if sitemap_id:
                cursor.execute("SELECT user_id FROM sitemaps WHERE id = ?", (sitemap_id,))
                sm_row = cursor.fetchone()
                if sm_row:
                    user_id = sm_row["user_id"]

            rec_id = f"q_{uuid.uuid4().hex[:10]}"
            now = iso_now()

            cursor.execute("""
            INSERT INTO quarantine_records (
                id, url, sitemap_id, user_id, title, content, chunks_json, embeddings_json,
                last_known_http_status, quarantine_reason, replacement_url, detected_at, quarantined_at, sitemap_presence_history_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                quarantine_reason = excluded.quarantine_reason,
                last_known_http_status = excluded.last_known_http_status,
                quarantined_at = excluded.quarantined_at,
                replacement_url = excluded.replacement_url,
                restored_at = NULL,
                user_id = COALESCE(excluded.user_id, quarantine_records.user_id)
            """, (
                rec_id, url, sitemap_id, user_id, art_row["title"], art_row["body_text"],
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

    def restore_quarantined_article(self, url_or_id: str, user_id: Optional[str] = None) -> bool:
        """Restores a quarantined article back to active knowledge without data loss. Supports URL or ID lookup."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT q.url, q.id, q.sitemap_id, q.user_id, s.user_id as sitemap_user_id
            FROM quarantine_records q
            LEFT JOIN sitemaps s ON q.sitemap_id = s.id
            WHERE (q.url = ? OR q.id = ?) AND q.restored_at IS NULL
            """, (url_or_id, url_or_id))
            row = cursor.fetchone()
            if not row:
                return False

            if user_id and user_id not in ("service_internal", "admin"):
                owner = row["user_id"] or row["sitemap_user_id"]
                if owner and owner != user_id:
                    return False

            target_url = row["url"]
            now = iso_now()
            cursor.execute("UPDATE articles SET status = 'active' WHERE url = ?", (target_url,))
            cursor.execute("UPDATE quarantine_records SET restored_at = ? WHERE url = ?", (now, target_url))
            cursor.execute("UPDATE url_health_status SET consecutive_failure_count = 0, failure_reason = NULL WHERE url = ?", (target_url,))
            conn.commit()
            return True

    def get_quarantined_articles(self, user_id: Optional[str] = None) -> List[QuarantineRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id and user_id not in ("service_internal", "admin"):
                cursor.execute("""
                SELECT q.* FROM quarantine_records q
                LEFT JOIN sitemaps s ON q.sitemap_id = s.id
                WHERE q.restored_at IS NULL AND (q.user_id = ? OR s.user_id = ?)
                ORDER BY q.quarantined_at DESC
                """, (user_id, user_id))
            else:
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
                archive_retention_preset=row["archive_retention_preset"] if "archive_retention_preset" in row.keys() and row["archive_retention_preset"] else "30d",
                archive_retention_days=row["archive_retention_days"] if "archive_retention_days" in row.keys() and row["archive_retention_days"] else 30,
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
                url_quarantine_action, archive_retention_preset, archive_retention_days,
                email_approval_threshold_x, auto_send_enabled, emergency_disable, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                sitemap_refresh_interval_days = excluded.sitemap_refresh_interval_days,
                url_quarantine_threshold_x = excluded.url_quarantine_threshold_x,
                url_quarantine_action = excluded.url_quarantine_action,
                archive_retention_preset = excluded.archive_retention_preset,
                archive_retention_days = excluded.archive_retention_days,
                email_approval_threshold_x = excluded.email_approval_threshold_x,
                auto_send_enabled = excluded.auto_send_enabled,
                emergency_disable = excluded.emergency_disable,
                updated_at = excluded.updated_at
            """, (
                s.user_id, s.sitemap_refresh_interval_days, s.url_quarantine_threshold_x,
                s.url_quarantine_action, s.archive_retention_preset, s.archive_retention_days,
                s.email_approval_threshold_x,
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
            INSERT INTO users (id, email, password_hash, display_name, role, failed_login_attempts, created_at)
            VALUES (?, ?, ?, ?, ?, 0, ?)
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

    def record_failed_login(self, email: str, limit: int = 5, lockout_minutes: int = 15) -> Dict[str, Any]:
        """Increments failed login attempts and sets lockout timestamp if threshold exceeded."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, failed_login_attempts FROM users WHERE email = ?", (email.lower().strip(),))
            row = cursor.fetchone()
            if not row:
                return {"locked": False, "attempts": 0, "locked_until": None}
            
            attempts = (row["failed_login_attempts"] or 0) + 1
            locked_until = None
            if attempts >= limit:
                lock_time = datetime.now(timezone.utc) + timedelta(minutes=lockout_minutes)
                locked_until = lock_time.isoformat()
            
            cursor.execute(
                "UPDATE users SET failed_login_attempts = ?, locked_until = ? WHERE id = ?",
                (attempts, locked_until, row["id"])
            )
            conn.commit()
            return {"locked": bool(locked_until), "attempts": attempts, "locked_until": locked_until}

    def is_account_locked(self, email: str) -> Tuple[bool, Optional[str]]:
        """Checks if account is currently locked due to failed attempts."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT locked_until FROM users WHERE email = ?", (email.lower().strip(),))
            row = cursor.fetchone()
            if not row or not row["locked_until"]:
                return False, None
            
            try:
                locked_until = datetime.fromisoformat(row["locked_until"])
                if locked_until > datetime.now(timezone.utc):
                    return True, row["locked_until"]
                else:
                    # Expired lock, clear it
                    cursor.execute("UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE email = ?", (email.lower().strip(),))
                    conn.commit()
                    return False, None
            except Exception:
                return False, None

    def reset_failed_logins(self, user_id: str):
        """Clears failed login attempts and updates last_login_at."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET failed_login_attempts = 0, locked_until = NULL, last_login_at = ? WHERE id = ?",
                (iso_now(), user_id)
            )
            conn.commit()

    def update_password_hash(self, user_id: str, new_hash: str):
        """Safely updates a user password hash (used for seamless migration from PBKDF2 to Argon2id)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
            conn.commit()

    def create_session(self, user_id: str, expires_in_seconds: int = 86400 * 7, csrf_token: Optional[str] = None) -> SessionToken:
        session_id = f"sess_{secrets.token_urlsafe(32)}"
        csrf = csrf_token or secrets.token_hex(16)
        now = datetime.now(timezone.utc)
        expires_at = datetime.fromtimestamp(now.timestamp() + expires_in_seconds, timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO user_sessions (session_id, user_id, expires_at, created_at, csrf_token, last_activity_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (session_id, user_id, expires_at, now.isoformat(), csrf, now.isoformat()))
            conn.commit()
        return SessionToken(session_id, csrf)

    def get_session_user(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_sessions WHERE session_id = ?", (session_id,))
            sess_row = cursor.fetchone()
            if not sess_row:
                return None
            
            # Check expiry
            try:
                expires_at = datetime.fromisoformat(sess_row["expires_at"])
                if expires_at < datetime.now(timezone.utc):
                    cursor.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
                    conn.commit()
                    return None
            except Exception:
                return None

            cursor.execute("SELECT id, email, display_name, role, created_at FROM users WHERE id = ?", (sess_row["user_id"],))
            user_row = cursor.fetchone()
            if not user_row:
                return None

            # Update last activity timestamp
            cursor.execute("UPDATE user_sessions SET last_activity_at = ? WHERE session_id = ?", (iso_now(), session_id))
            conn.commit()
            user_dict = dict(user_row)
            user_dict["session_id"] = session_id
            user_dict["csrf_token"] = sess_row["csrf_token"] if "csrf_token" in sess_row.keys() else ""
            return user_dict

    def validate_session_csrf(self, session_id: str, csrf_token: str) -> bool:
        if not session_id or not csrf_token:
            return False
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT csrf_token FROM user_sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if not row or not row["csrf_token"]:
                return False
            return secrets.compare_digest(row["csrf_token"], csrf_token)

    def delete_session(self, session_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
            conn.commit()

    def delete_user_sessions(self, user_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
            conn.commit()

    # -------------------------------------------------------------
    # Step 3: Production Scheduled Refresh, URL Health, 301 Redirects & Archive
    # -------------------------------------------------------------
    def _init_schema(self):
        """Idempotent schema initialization alias."""
        self._init_db()

    def update_sitemap_schedule(self, sitemap_id: str, interval: str, status: str = "active") -> None:
        interval_norm = interval.lower().strip()
        days = 1
        if interval_norm in ("weekly", "7_days", "7d", "7"):
            days = 7
        elif interval_norm in ("15_days", "15d", "15"):
            days = 15
        elif interval_norm in ("30_days", "30d", "30", "monthly"):
            days = 30
        else:
            days = 1
            interval_norm = "daily"

        now = datetime.now(timezone.utc)
        next_run = (now + timedelta(days=days)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE sitemaps 
            SET refresh_interval = ?, refresh_interval_days = ?, schedule_status = ?, next_refresh_at = ?, updated_at = ?
            WHERE id = ?
            """, (interval_norm, days, status, next_run, now.isoformat(), sitemap_id))
            conn.commit()

    def get_due_sitemaps(self, limit: int = 10) -> List[Dict[str, Any]]:
        now_iso = iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id, root_url, name, user_id, refresh_interval, refresh_interval_days,
                   schedule_status, next_refresh_at, last_refresh_started_at, last_refresh_completed_at
            FROM sitemaps
            WHERE schedule_status = 'active'
              AND (next_refresh_at IS NULL OR next_refresh_at <= ?)
            ORDER BY next_refresh_at ASC
            LIMIT ?
            """, (now_iso, limit))
            return [dict(row) for row in cursor.fetchall()]

    def record_sitemap_refresh_start(self, sitemap_id: str) -> None:
        now_iso = iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE sitemaps SET last_refresh_started_at = ?, retry_count = 0, updated_at = ? WHERE id = ?", (now_iso, now_iso, sitemap_id))
            conn.commit()

    def record_sitemap_refresh_complete(self, sitemap_id: str) -> None:
        now = datetime.now(timezone.utc)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT refresh_interval_days FROM sitemaps WHERE id = ?", (sitemap_id,))
            row = cursor.fetchone()
            days = (row["refresh_interval_days"] if row and row["refresh_interval_days"] else 1)
            next_run = (now + timedelta(days=days)).isoformat()
            cursor.execute("""
            UPDATE sitemaps
            SET last_refresh_completed_at = ?, next_refresh_at = ?, updated_at = ?
            WHERE id = ?
            """, (now.isoformat(), next_run, now.isoformat(), sitemap_id))
            conn.commit()

    def get_scheduler_status(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) as total FROM sitemaps")
            total = cursor.fetchone()["total"]
            cursor.execute("SELECT count(*) as active_cnt FROM sitemaps WHERE schedule_status = 'active'")
            active_cnt = cursor.fetchone()["active_cnt"]
            cursor.execute("SELECT count(*) as paused_cnt FROM sitemaps WHERE schedule_status = 'paused'")
            paused_cnt = cursor.fetchone()["paused_cnt"]
            cursor.execute("SELECT count(*) as disabled_cnt FROM sitemaps WHERE schedule_status = 'disabled'")
            disabled_cnt = cursor.fetchone()["disabled_cnt"]
            cursor.execute("SELECT MIN(next_refresh_at) as next_run FROM sitemaps WHERE schedule_status = 'active' AND next_refresh_at IS NOT NULL")
            next_row = cursor.fetchone()
            next_run = next_row["next_run"] if next_row else None
            return {
                "total_configured_sitemaps": total,
                "active_schedules_count": active_cnt,
                "paused_schedules_count": paused_cnt,
                "disabled_schedules_count": disabled_cnt,
                "next_scheduled_run_at": next_run,
                "is_running": True
            }

    def acquire_lease(self, resource_id: str, owner_id: str, ttl_seconds: int = 60) -> bool:
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
        now_iso = now.isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS coordination_leases (
                resource_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                acquired_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """)
            cursor.execute("SELECT owner_id, expires_at FROM coordination_leases WHERE resource_id = ?", (resource_id,))
            row = cursor.fetchone()
            if row:
                if row["owner_id"] == owner_id:
                    cursor.execute("UPDATE coordination_leases SET expires_at = ? WHERE resource_id = ?", (expires_at, resource_id))
                    conn.commit()
                    return True
                if row["expires_at"] > now_iso:
                    return False
                cursor.execute("UPDATE coordination_leases SET owner_id = ?, acquired_at = ?, expires_at = ? WHERE resource_id = ?",
                               (owner_id, now_iso, expires_at, resource_id))
                conn.commit()
                return True
            else:
                cursor.execute("INSERT INTO coordination_leases (resource_id, owner_id, acquired_at, expires_at) VALUES (?, ?, ?, ?)",
                               (resource_id, owner_id, now_iso, expires_at))
                conn.commit()
                return True

    def release_lease(self, resource_id: str, owner_id: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM coordination_leases WHERE resource_id = ? AND owner_id = ?", (resource_id, owner_id))
            conn.commit()

    def get_url_health_statuses(
        self,
        url: Optional[str] = None,
        status: Optional[str] = None,
        sitemap_id: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM url_health_status WHERE 1=1"
            params = []
            if url:
                query += " AND url = ?"
                params.append(url)
            if sitemap_id:
                query += " AND sitemap_id = ?"
                params.append(sitemap_id)
            if search:
                query += " AND (url LIKE ? OR canonical_url LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%"])
            if status:
                if status == "HEALTHY":
                    query += " AND is_healthy = 1"
                elif status == "FAILING":
                    query += " AND consecutive_failure_count > 0"
                elif status.isdigit():
                    query += " AND last_http_status = ?"
                    params.append(int(status))

            query += " ORDER BY consecutive_failure_count DESC, last_attempted_fetch_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cursor.execute(query, params)
            results = []
            for row in cursor.fetchall():
                results.append({
                    "url": row["url"],
                    "canonical_url": row["canonical_url"] or row["url"],
                    "sitemap_id": row["sitemap_id"],
                    "current_http_status": row["last_http_status"],
                    "last_known_successful_status": 200 if row["last_successful_fetch_at"] else None,
                    "consecutive_failures": row["consecutive_failure_count"] or 0,
                    "failure_threshold_x": row["configured_threshold"] or 3,
                    "pending_action": row["pending_action"],
                    "action_rule": row["action_rule"] or "QUARANTINE_ON_THRESHOLD",
                    "in_sitemap": bool(row["is_in_sitemap"]),
                    "is_healthy": bool(row["is_healthy"]),
                    "failure_reason": row["failure_reason"],
                    "redirect_destination_url": row["redirect_destination_url"],
                    "last_successful_fetch_at": row["last_successful_fetch_at"],
                    "last_attempted_fetch_at": row["last_attempted_fetch_at"]
                })
            return results

    def cancel_pending_url_action(self, url: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE url_health_status SET pending_action = NULL, consecutive_failure_count = 0 WHERE url = ?", (url,))
            conn.commit()

    def record_article_redirect(
        self,
        source_url: str,
        destination_url: str,
        http_status: int = 301,
        hop_count: int = 1,
        redirect_chain: Optional[List[str]] = None,
        user_id: str = "default_user",
        sitemap_id: Optional[str] = None,
        notes: str = ""
    ) -> str:
        red_id = f"red_{uuid.uuid4().hex[:10]}"
        now_iso = iso_now()
        chain_json = json.dumps(redirect_chain or [source_url, destination_url])
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO article_redirects (
                id, user_id, sitemap_id, source_url, destination_url, http_status,
                hop_count, redirect_chain_json, detected_at, replacement_indexed, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """, (red_id, user_id, sitemap_id, source_url, destination_url, http_status, hop_count, chain_json, now_iso, notes))
            conn.commit()
        return red_id

    def mark_redirect_replacement_indexed(self, source_url: str, destination_url: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE article_redirects
            SET replacement_indexed = 1, replacement_article_url = ?
            WHERE source_url = ?
            """, (destination_url, source_url))
            conn.commit()

    def get_article_redirects(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM article_redirects ORDER BY detected_at DESC LIMIT ? OFFSET ?", (limit, offset))
            return [dict(row) for row in cursor.fetchall()]

    def get_redirect_for_url(self, source_url: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM article_redirects WHERE source_url = ? ORDER BY detected_at DESC LIMIT 1", (source_url,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def archive_article(
        self,
        original_url: str,
        canonical_url: str,
        title: str,
        full_content: str,
        archive_reason: str,
        chunks_json: str = "[]",
        embeddings_json: str = "[]",
        last_known_http_status: Optional[int] = None,
        replacement_url: Optional[str] = None,
        user_id: str = "default_user",
        sitemap_id: Optional[str] = None,
        retention_preset: str = "30_days",
        retention_days: Optional[int] = None
    ) -> str:
        archive_id = f"arch_{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc)
        days = retention_days or (2 if retention_preset == "2_days" else 15 if retention_preset == "15_days" else 30)
        expires_at = (now + timedelta(days=days)).isoformat()
        now_iso = now.isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO archived_articles (
                id, url, canonical_url, sitemap_id, user_id, title, content,
                chunks_json, embeddings_json, original_indexed_at, archived_at,
                archive_reason, last_known_http_status, replacement_url,
                last_successful_version, restore_eligible, retention_preset,
                retention_days, retention_expires_at, audit_history_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2.0', 1, ?, ?, ?, '[]')
            """, (
                archive_id, original_url, canonical_url, sitemap_id, user_id, title,
                full_content, chunks_json, embeddings_json, now_iso, now_iso,
                archive_reason, last_known_http_status, replacement_url,
                retention_preset, days, expires_at
            ))
            cursor.execute("""
            UPDATE articles 
            SET status = 'archived', is_quarantined = 1, quarantine_reason = ?
            WHERE url = ?
            """, (archive_reason, original_url))
            conn.commit()
        return archive_id

    def get_archived_articles(
        self,
        user_id: Optional[str] = None,
        search: Optional[str] = None,
        reason: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT id, url as original_url, canonical_url, sitemap_id, user_id, title, archive_reason, replacement_url, archived_at, restore_eligible, retention_preset, retention_days FROM archived_articles WHERE 1=1"
            params = []
            if user_id and user_id not in ("service_internal", "admin"):
                query += " AND user_id = ?"
                params.append(user_id)
            if search:
                query += " AND (title LIKE ? OR url LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%"])
            if reason:
                query += " AND archive_reason = ?"
                params.append(reason)
            query += " ORDER BY archived_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_archived_article_detail(self, item_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM archived_articles WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["original_url"] = row["url"]
            res["full_content"] = row["content"]
            return res

    def restore_archived_article(self, item_id: str, requesting_user_id: str = "default_user") -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM archived_articles WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            if not row:
                return False
            # Verify ownership
            if row["user_id"] != requesting_user_id and requesting_user_id not in ("admin", "service_internal"):
                raise PermissionError("Cross-user restore rejected: You do not own this archived article.")

            now_iso = iso_now()
            cursor.execute("""
            INSERT INTO articles (url, title, body_text, status, is_quarantined, quarantine_reason, user_id, sitemap_id, crawled_at)
            VALUES (?, ?, ?, 'active', 0, NULL, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                status = 'active',
                is_quarantined = 0,
                quarantine_reason = NULL,
                body_text = excluded.body_text
            """, (row["url"], row["title"], row["content"], row["user_id"], row["sitemap_id"], now_iso))
            cursor.execute("UPDATE archived_articles SET restore_eligible = 0 WHERE id = ?", (item_id,))
            conn.commit()
            return True

    def update_archive_retention(self, item_id: str, preset: str, custom_days: Optional[int] = None) -> None:
        days = custom_days or (2 if preset == "2_days" else 15 if preset == "15_days" else 30)
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(days=days)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE archived_articles
            SET retention_preset = ?, retention_days = ?, retention_expires_at = ?
            WHERE id = ?
            """, (preset, days, expires_at, item_id))
            conn.commit()

    def get_article_versions(self, url: str) -> List[ArticleHistoryItem]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM article_history WHERE url = ? ORDER BY recorded_at DESC", (url,))
            items = []
            for row in cursor.fetchall():
                p_hash = row["previous_hash"] or ""
                n_hash = row["new_hash"] or ""
                rec_at = row["recorded_at"] or iso_now()
                items.append(ArticleHistoryItem(
                    id=row["id"],
                    url=row["url"],
                    version=row["version"],
                    title=row["title"] or "",
                    previous_title=row["previous_title"] if "previous_title" in row.keys() else None,
                    new_title=row["new_title"] if "new_title" in row.keys() else None,
                    change_type=row["change_type"] or "UPDATE",
                    change_classification=row["change_classification"] if "change_classification" in row.keys() else "CONTENT_UPDATE",
                    previous_hash=p_hash,
                    new_hash=n_hash,
                    previous_content_hash=p_hash,
                    new_content_hash=n_hash,
                    summary_diff=row["summary_diff"] or "",
                    content_snapshot=row["content_snapshot"] if "content_snapshot" in row.keys() else None,
                    recorded_at=rec_at,
                    changed_at=rec_at
                ))
            return items

    def get_article_version_diff(self, version1_id: str, version2_id: str) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT summary_diff, content_snapshot, title, new_hash FROM article_history WHERE id = ?", (version1_id,))
            r1 = cursor.fetchone()
            cursor.execute("SELECT summary_diff, content_snapshot, title, new_hash FROM article_history WHERE id = ?", (version2_id,))
            r2 = cursor.fetchone()
            diff_text = f"--- Version {version1_id} ({r1['new_hash'] if r1 else 'N/A'})\n+++ Version {version2_id} ({r2['new_hash'] if r2 else 'N/A'})\n"
            if r1 and r2:
                diff_text += f"\nSummary: {r2['summary_diff'] or 'Content updated'}\n"
                diff_text += f"- Title: {r1['title']}\n+ Title: {r2['title']}\n"
            return {"diff_text": diff_text}


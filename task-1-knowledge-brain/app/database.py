import sqlite3
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from app.models import Article, ArticleChunk, ImageMetadata, ExpertTask, SyncStatus, SyncReport

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 2

def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()

class Database:
    def __init__(self, db_path: str = "knowledge_brain.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
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
            
            # Run migrations first so any missing legacy columns exist before indexing
            self._apply_migrations(cursor)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_url ON chunks(article_url)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status)")
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

    def mark_article_removed(self, url: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE articles SET status = 'removed' WHERE url = ?", (url,))
            cursor.execute("DELETE FROM chunks WHERE article_url = ?", (url,))
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

    def get_all_active_urls(self) -> List[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM articles WHERE status = 'active'")
            return [row["url"] for row in cursor.fetchall()]

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

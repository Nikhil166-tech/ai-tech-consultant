import sqlite3
import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from app.models import Article, ArticleChunk, ImageMetadata, ExpertTask

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
            
            # Articles table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT DEFAULT 'General',
                folder TEXT DEFAULT 'General',
                body_text TEXT NOT NULL,
                images_json TEXT DEFAULT '[]',
                last_modified TEXT,
                etag TEXT,
                status TEXT DEFAULT 'active',
                crawled_at TEXT
            )
            """)

            # Chunks table for vector & lexical search
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                article_url TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT DEFAULT 'General',
                folder TEXT DEFAULT 'General',
                chunk_index INTEGER,
                text TEXT NOT NULL,
                visual_context TEXT DEFAULT '',
                embedding_json TEXT DEFAULT '[]',
                FOREIGN KEY (article_url) REFERENCES articles(url) ON DELETE CASCADE
            )
            """)

            # Crawler checkpoint table for politeness & resumption
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS crawler_checkpoint (
                url TEXT PRIMARY KEY,
                last_checked TEXT,
                status_code INTEGER,
                etag TEXT,
                last_modified TEXT,
                error TEXT
            )
            """)

            # Expert Fallback Task Queue (Self-evolving memory loop)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS expert_tasks (
                id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                context TEXT DEFAULT '',
                requester_email TEXT,
                status TEXT DEFAULT 'pending',
                expert_answer TEXT,
                created_at TEXT,
                resolved_at TEXT
            )
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_url ON chunks(article_url)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status)")
            conn.commit()

    def upsert_article(self, article: Article):
        images_json = json.dumps([img.model_dump() for img in article.images])
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO articles (url, title, category, folder, body_text, images_json, last_modified, etag, status, crawled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title,
                category=excluded.category,
                folder=excluded.folder,
                body_text=excluded.body_text,
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
                cursor.execute("""
                INSERT INTO chunks (id, article_url, title, category, folder, chunk_index, text, visual_context, embedding_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    text=excluded.text,
                    visual_context=excluded.visual_context,
                    embedding_json=excluded.embedding_json
                """, (
                    chunk.id,
                    chunk.article_url,
                    chunk.title,
                    chunk.category,
                    chunk.folder,
                    chunk.chunk_index,
                    chunk.text,
                    chunk.visual_context,
                    emb_json
                ))
            conn.commit()

    def mark_article_removed(self, url: str):
        """Marks article as removed and purges chunks so it stops appearing in answers."""
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
            images_data = json.loads(row["images_json"]) if row["images_json"] else []
            images = [ImageMetadata(**img) for img in images_data]
            crawled = datetime.fromisoformat(row["crawled_at"]) if row["crawled_at"] else datetime.now(timezone.utc)
            return Article(
                url=row["url"],
                title=row["title"],
                category=row["category"],
                folder=row["folder"],
                body_text=row["body_text"],
                images=images,
                last_modified=row["last_modified"],
                etag=row["etag"],
                status=row["status"],
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
                emb = json.loads(row["embedding_json"]) if row["embedding_json"] else []
                chunks.append(ArticleChunk(
                    id=row["id"],
                    article_url=row["article_url"],
                    title=row["title"],
                    category=row["category"],
                    folder=row["folder"],
                    chunk_index=row["chunk_index"],
                    text=row["text"],
                    visual_context=row["visual_context"],
                    embedding=emb
                ))
            return chunks

    def save_crawler_checkpoint(self, url: str, status_code: int, etag: Optional[str] = None, last_modified: Optional[str] = None, error: Optional[str] = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO crawler_checkpoint (url, last_checked, status_code, etag, last_modified, error)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                last_checked=excluded.last_checked,
                status_code=excluded.status_code,
                etag=excluded.etag,
                last_modified=excluded.last_modified,
                error=excluded.error
            """, (url, iso_now(), status_code, etag, last_modified, error))
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

    def resolve_expert_task(self, task_id: str, expert_answer: str) -> Optional[ExpertTask]:
        now = iso_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM expert_tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                return None
            
            cursor.execute("""
            UPDATE expert_tasks 
            SET status = 'resolved', expert_answer = ?, resolved_at = ?
            WHERE id = ?
            """, (expert_answer, now, task_id))

            # Integrate expert answer into active knowledge chunks!
            q = row["question"]
            expert_chunk_id = f"expert_{task_id}"
            cursor.execute("""
            INSERT INTO chunks (id, article_url, title, category, folder, chunk_index, text, visual_context, embedding_json)
            VALUES (?, ?, ?, 'Expert Knowledge', 'Verified Resolutions', 0, ?, 'Verified human expert answer', '[]')
            ON CONFLICT(id) DO UPDATE SET text=excluded.text
            """, (
                expert_chunk_id,
                f"expert://resolution/{task_id}",
                f"Expert Answer: {q[:50]}...",
                f"Question: {q}\nExpert Resolution: {expert_answer}"
            ))
            cursor.execute("""
            INSERT INTO articles (url, title, category, folder, body_text, status, crawled_at)
            VALUES (?, ?, 'Expert Knowledge', 'Verified Resolutions', ?, 'active', ?)
            ON CONFLICT(url) DO UPDATE SET body_text=excluded.body_text
            """, (
                f"expert://resolution/{task_id}",
                f"Expert Answer: {q[:50]}...",
                f"Question: {q}\nExpert Resolution: {expert_answer}",
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
                    created_at=row["created_at"],
                    resolved_at=row["resolved_at"]
                ) for row in cursor.fetchall()
            ]

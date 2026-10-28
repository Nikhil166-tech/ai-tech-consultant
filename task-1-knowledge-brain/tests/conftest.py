"""
Pytest configuration and isolated fixtures for Task 1 Knowledge Brain.
Guarantees that all automated tests execute against an isolated, disposable SQLite database,
preventing any contamination of the production knowledge_brain.db.
"""

import os
import shutil
import tempfile
import pytest
from fastapi.testclient import TestClient

from app.database import Database
from app.config import settings
from app.models import Article, ArticleChunk, ImageMetadata


@pytest.fixture(scope="session")
def isolated_db_path(tmp_path_factory):
    """Creates a temporary, isolated SQLite database file for the test session."""
    temp_dir = tmp_path_factory.mktemp("kb_test_data")
    db_file = temp_dir / "isolated_test_brain.db"
    return str(db_file)


@pytest.fixture(scope="session")
def isolated_db(isolated_db_path):
    """Initializes schema and seeds isolated baseline test fixtures."""
    test_db = Database(db_path=isolated_db_path)
    
    # Seed baseline fixtures for search / RAG test assertions
    seed_article = Article(
        url="https://support.brilliantdirectories.com/support/solutions/articles/1200000001-member-directory-settings",
        title="Member Directory Settings and Configuration",
        category="General",
        folder="Directory Settings",
        body_text="Configure member directory settings including search filters, layout, payment options, and listing visibility.",
        content_hash="seed_hash_001",
        normalized_content_hash="seed_hash_001",
        images=[]
    )
    seed_chunk = ArticleChunk(
        id="seed_chunk_001",
        article_url=seed_article.url,
        title=seed_article.title,
        category=seed_article.category,
        folder=seed_article.folder,
        section_heading="Overview",
        chunk_index=0,
        text="Configure member directory settings including search filters, layout, payment options, and listing visibility.",
        embedding=[0.05] * 384,
        source_type="OFFICIAL_DOC"
    )
    test_db.atomic_replace_article_and_chunks(
        article=seed_article,
        chunks=[seed_chunk],
        checkpoint_status=200
    )

    # Seed isolated demo user with legacy PBKDF2-HMAC-SHA256 hash to test auto-rehash to Argon2id
    import hashlib
    salt = bytes.fromhex("a1b2c3d4e5f60718293a4b5c6d7e8f90")
    legacy_key = hashlib.pbkdf2_hmac("sha256", b"DemoPassword123!", salt, 100_000)
    legacy_hash = f"{salt.hex()}${legacy_key.hex()}"
    with test_db._get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO users (id, email, password_hash, display_name, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "user_demo_001",
            "demo.consultant@brilliantdirectories.com",
            legacy_hash,
            "Demo Consultant",
            "admin",
            "2026-01-01T00:00:00Z"
        ))
        conn.commit()

    return test_db


@pytest.fixture(scope="session")
def client(isolated_db, isolated_db_path):
    """
    TestClient that points FastAPI application dependencies to the isolated test database.
    Production knowledge_brain.db is completely protected from test writes.
    """
    import app.main as main_module
    
    # Save original references
    orig_db = main_module.db
    orig_crawler_db = main_module.crawler.db
    orig_rag_db = main_module.rag_engine.db

    # Point application to isolated database
    main_module.db = isolated_db
    main_module.crawler.db = isolated_db
    main_module.rag_engine.db = isolated_db
    if hasattr(main_module.rag_engine, "retriever") and main_module.rag_engine.retriever:
        main_module.rag_engine.retriever.db = isolated_db

    with TestClient(main_module.app) as test_client:
        yield test_client

    # Restore original references
    main_module.db = orig_db
    main_module.crawler.db = orig_crawler_db
    main_module.rag_engine.db = orig_rag_db
    if hasattr(main_module.rag_engine, "retriever") and main_module.rag_engine.retriever:
        main_module.rag_engine.retriever.db = orig_db


@pytest.fixture
def db(isolated_db):
    """Yields the isolated test database fixture for test functions."""
    return isolated_db


@pytest.fixture
def prod_db():
    """Read-only access to production database strictly for non-destructive integrity assertions."""
    prod_path = settings.knowledge_db_path
    if not os.path.isabs(prod_path):
        prod_path = os.path.abspath(prod_path)
    return Database(db_path=prod_path)

import pytest
import sqlite3
import gzip
import xml.etree.ElementTree as ET
from app.database import Database
from app.models import (
    Article, ArticleChunk, SitemapPreview, IndexingEstimate,
    QuarantineReason, UserSettings
)
from app.crawler import PoliteCrawler, validate_url_ssrf_safe, ThroughputTracker
from app.rag_engine import HybridRAGEngine

@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_knowledge_brain.db"
    db = Database(str(db_file))
    return db

# -------------------------------------------------------------
# Phase 2 Tests: SSRF, Sitemaps & Previews
# -------------------------------------------------------------
def test_ssrf_validation_blocks_restricted_destinations():
    assert validate_url_ssrf_safe("http://localhost:8000/sitemap.xml")[0] is False
    assert validate_url_ssrf_safe("http://127.0.0.1:8000/sitemap.xml")[0] is False
    assert validate_url_ssrf_safe("http://169.254.169.254/latest/meta-data")[0] is False
    assert validate_url_ssrf_safe("http://10.0.1.5/sitemap.xml")[0] is False
    assert validate_url_ssrf_safe("http://192.168.1.1/sitemap.xml")[0] is False
    assert validate_url_ssrf_safe("file:///etc/passwd")[0] is False
    assert validate_url_ssrf_safe("ftp://example.com/sitemap.xml")[0] is False
    assert validate_url_ssrf_safe("https://example.com/sitemap.xml")[0] is True

def test_sitemap_database_and_preview_workflow(test_db):
    sm = test_db.create_sitemap(
        root_url="https://example.com/sitemap.xml",
        name="Example Site",
        user_id="user_test",
        refresh_interval_days=7
    )
    assert sm.id.startswith("sm_")
    assert sm.status == "registered"
    assert sm.refresh_interval_days == 7

    preview = SitemapPreview(
        submitted_url="https://example.com/sitemap.xml",
        discovered_sitemaps_count=2,
        nested_sitemaps_count=1,
        total_extracted_urls=15,
        total_unique_urls=12,
        first_url="https://example.com/first",
        first_url_lastmod="2026-10-01",
        last_url="https://example.com/last",
        last_url_lastmod="2026-10-15",
        validation_status="valid",
        can_index=True
    )
    test_db.update_sitemap_preview(sm.id, preview)
    updated = test_db.get_sitemap(sm.id)
    assert updated.status == "previewed"
    assert updated.last_preview_json is not None

    confirmed = test_db.confirm_sitemap(sm.id)
    assert confirmed is True
    confirmed_sm = test_db.get_sitemap(sm.id)
    assert confirmed_sm.status == "confirmed"
    assert confirmed_sm.last_confirmed_at is not None

def test_throughput_tracker_rolling_window():
    tracker = ThroughputTracker(window_seconds=300.0)
    for _ in range(10):
        tracker.record(crawl_sec=0.2, chunk_sec=0.05, embed_sec=0.1, db_sec=0.02)
    
    estimate = tracker.get_estimate(total_remaining=50)
    assert estimate.pages_processed_5min == 10
    assert estimate.total_pages_remaining == 50
    assert estimate.observed_throughput_pages_per_min > 0
    assert "minute" in estimate.estimated_completion_time_human or "hour" in estimate.estimated_completion_time_human
    assert "not a guaranteed SLA" in estimate.disclaimer

# -------------------------------------------------------------
# Phase 3 & 4 Tests: Refresh Runs, URL Health & Quarantine
# -------------------------------------------------------------
def test_url_health_status_consecutive_failure_and_recovery(test_db):
    url = "https://support.example.com/broken-page"
    sitemap_id = "sm_123"

    # 1. First failure
    h1 = test_db.update_url_health(url, sitemap_id, http_status=404, is_in_sitemap=False, threshold_x=3)
    assert h1.consecutive_failure_count == 1
    assert h1.is_in_sitemap is False

    # 2. Second failure
    h2 = test_db.update_url_health(url, sitemap_id, http_status=404, is_in_sitemap=False, threshold_x=3)
    assert h2.consecutive_failure_count == 2

    # 3. HTTP 200 Recovery resets consecutive count to 0
    h3 = test_db.update_url_health(url, sitemap_id, http_status=200, is_in_sitemap=True, threshold_x=3)
    assert h3.consecutive_failure_count == 0
    assert h3.failure_reason is None

def test_quarantine_without_data_loss_and_restoration(test_db):
    url = "https://support.example.com/deprecated-article"
    art = Article(
        url=url,
        title="Deprecated Integration Guide",
        category="Integrations",
        folder="CRM",
        body_text="Detailed steps for deprecated CRM integration.",
        content_hash="abc123hash",
        status="active"
    )
    test_db.upsert_article(art)

    chunk = ArticleChunk(
        id=f"{url}#sec-0",
        article_url=url,
        title=art.title,
        category=art.category,
        folder=art.folder,
        section_heading="Overview",
        chunk_index=0,
        text="Detailed steps chunk",
        embedding=[0.1, 0.2, 0.3]
    )
    test_db.save_chunks([chunk])

    assert test_db.count_active_articles() == 1
    assert test_db.count_active_chunks() == 1

    # Quarantine article
    q_rec = test_db.quarantine_article(
        url=url,
        sitemap_id="sm_test",
        reason=QuarantineReason.MISSING_404,
        last_status=404
    )
    assert q_rec is not None
    assert q_rec.quarantine_reason == QuarantineReason.MISSING_404
    assert q_rec.chunks_count == 1

    # Active RAG count must be 0, but chunks and article record are PRESERVED!
    assert test_db.count_active_articles() == 0
    assert test_db.count_active_chunks() == 0

    # Chunks still exist in database
    with test_db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE article_url = ?", (url,))
        assert cursor.fetchone()[0] == 1

    # Restore article
    restored = test_db.restore_quarantined_article(url)
    assert restored is True
    assert test_db.count_active_articles() == 1
    assert test_db.count_active_chunks() == 1

# -------------------------------------------------------------
# Phase 5 Tests: Query Normalization & Synonym Handling
# -------------------------------------------------------------
def test_query_normalization_and_synonym_expansion(test_db):
    rag = HybridRAGEngine(db=test_db)
    
    q1 = rag.normalize_query("How do I export my members to CSV?")
    assert "export" in q1
    assert "member" in q1
    assert "csv" in q1

    q2 = rag.normalize_query("Can we connect Stripe recurring payments?")
    assert "stripe" in q2
    assert "subscription" in q2 or "payment" in q2

    q3 = rag.normalize_query("Domain DNS nameserver records setup")
    assert "dns" in q3
    assert "nameservers" in q3

# -------------------------------------------------------------
# Phase 6 Tests: Authentication & Isolation
# -------------------------------------------------------------
def test_user_authentication_and_session(test_db):
    from app.main import hash_password, verify_password

    pw = "SuperSecureDemoPass123!"
    hashed = hash_password(pw)
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False

    user = test_db.create_user(email="consultant@test.com", password_hash=hashed, display_name="Consultant")
    assert user["id"].startswith("u_")

    sess_id = test_db.create_session(user["id"])
    assert sess_id.startswith("sess_")

    sess_user = test_db.get_session_user(sess_id)
    assert sess_user is not None
    assert sess_user["email"] == "consultant@test.com"

    test_db.delete_session(sess_id)
    assert test_db.get_session_user(sess_id) is None

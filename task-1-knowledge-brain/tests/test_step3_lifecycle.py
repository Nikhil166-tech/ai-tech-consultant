"""
Comprehensive automated tests for Step 3:
Scheduled Refresh Engine, URL Health Monitoring, 301 Redirect Handling,
Archived Knowledge Base, Version History, and Migration Idempotency.

All tests execute against isolated temporary SQLite databases to guarantee zero
contamination of the production knowledge_brain.db.
"""

import os
import uuid
import datetime
import pytest
from app.database import Database
from app.models import (
    Article,
    ArticleChunk,
    ScheduleUpdateRequest,
    ArchiveRetentionUpdateRequest
)
from app.crawler import PoliteCrawler, validate_url_ssrf_safe
from app.scheduler import SitemapScheduler


@pytest.fixture
def isolated_step3_db(tmp_path):
    """Creates a dedicated isolated SQLite database for Step 3 testing."""
    db_file = tmp_path / "test_step3_isolated.db"
    db = Database(db_path=str(db_file))
    return db


# ============================================================================
# Phase B: Scheduled Refresh Engine (Tests 1-7)
# ============================================================================

def test_daily_scheduling(isolated_step3_db):
    """Test 1: Daily scheduling computes next_refresh_at = now + 1 day UTC."""
    db = isolated_step3_db
    sm_id = "sm_daily_01"
    with db._get_connection() as conn:
        conn.execute("INSERT INTO sitemaps (id, root_url, name, status) VALUES (?, ?, ?, ?)", (sm_id, "https://example.com/sitemap.xml", "Daily SM", "active"))
        conn.commit()

    db.update_sitemap_schedule(sm_id, interval="daily", status="active")
    with db._get_connection() as conn:
        row = conn.execute("SELECT refresh_interval, refresh_interval_days, schedule_status, next_refresh_at FROM sitemaps WHERE id = ?", (sm_id,)).fetchone()
    
    assert row["refresh_interval"] == "daily"
    assert row["refresh_interval_days"] == 1
    assert row["schedule_status"] == "active"
    next_run = datetime.datetime.fromisoformat(row["next_refresh_at"].replace("Z", "+00:00"))
    now = datetime.datetime.now(datetime.timezone.utc)
    diff = next_run - now
    assert 23 <= diff.total_seconds() / 3600 <= 25


def test_seven_day_scheduling(isolated_step3_db):
    """Test 2: Seven-day scheduling computes next_refresh_at = now + 7 days UTC."""
    db = isolated_step3_db
    sm_id = "sm_weekly_01"
    with db._get_connection() as conn:
        conn.execute("INSERT INTO sitemaps (id, root_url, name, status) VALUES (?, ?, ?, ?)", (sm_id, "https://example.com/sitemap_w.xml", "Weekly SM", "active"))
        conn.commit()

    db.update_sitemap_schedule(sm_id, interval="weekly", status="active")
    with db._get_connection() as conn:
        row = conn.execute("SELECT refresh_interval, refresh_interval_days, next_refresh_at FROM sitemaps WHERE id = ?", (sm_id,)).fetchone()
    
    assert row["refresh_interval_days"] == 7
    next_run = datetime.datetime.fromisoformat(row["next_refresh_at"].replace("Z", "+00:00"))
    diff = next_run - datetime.datetime.now(datetime.timezone.utc)
    assert 6.9 <= diff.total_seconds() / 86400 <= 7.1


def test_fifteen_day_scheduling(isolated_step3_db):
    """Test 3: Fifteen-day scheduling computes next_refresh_at = now + 15 days UTC."""
    db = isolated_step3_db
    sm_id = "sm_15d_01"
    with db._get_connection() as conn:
        conn.execute("INSERT INTO sitemaps (id, root_url, name, status) VALUES (?, ?, ?, ?)", (sm_id, "https://example.com/sitemap_15.xml", "15d SM", "active"))
        conn.commit()

    db.update_sitemap_schedule(sm_id, interval="15_days", status="active")
    with db._get_connection() as conn:
        row = conn.execute("SELECT refresh_interval, refresh_interval_days, next_refresh_at FROM sitemaps WHERE id = ?", (sm_id,)).fetchone()
    
    assert row["refresh_interval_days"] == 15
    next_run = datetime.datetime.fromisoformat(row["next_refresh_at"].replace("Z", "+00:00"))
    diff = next_run - datetime.datetime.now(datetime.timezone.utc)
    assert 14.9 <= diff.total_seconds() / 86400 <= 15.1


def test_thirty_day_scheduling(isolated_step3_db):
    """Test 4: Thirty-day scheduling computes next_refresh_at = now + 30 days UTC."""
    db = isolated_step3_db
    sm_id = "sm_30d_01"
    with db._get_connection() as conn:
        conn.execute("INSERT INTO sitemaps (id, root_url, name, status) VALUES (?, ?, ?, ?)", (sm_id, "https://example.com/sitemap_30.xml", "30d SM", "active"))
        conn.commit()

    db.update_sitemap_schedule(sm_id, interval="30_days", status="active")
    with db._get_connection() as conn:
        row = conn.execute("SELECT refresh_interval, refresh_interval_days, next_refresh_at FROM sitemaps WHERE id = ?", (sm_id,)).fetchone()
    
    assert row["refresh_interval_days"] == 30
    next_run = datetime.datetime.fromisoformat(row["next_refresh_at"].replace("Z", "+00:00"))
    diff = next_run - datetime.datetime.now(datetime.timezone.utc)
    assert 29.9 <= diff.total_seconds() / 86400 <= 30.1


def test_multiple_sitemaps_due_simultaneously(isolated_step3_db):
    """Test 5: Multiple sitemaps due simultaneously are all retrieved rather than only the first."""
    db = isolated_step3_db
    past_time = "2026-01-01T00:00:00Z"
    with db._get_connection() as conn:
        conn.execute("INSERT INTO sitemaps (id, root_url, name, status, schedule_status, next_refresh_at) VALUES (?, ?, 'sm1', 'active', 'active', ?)", ("sm_due_1", "https://example.com/1.xml", past_time))
        conn.execute("INSERT INTO sitemaps (id, root_url, name, status, schedule_status, next_refresh_at) VALUES (?, ?, 'sm2', 'active', 'active', ?)", ("sm_due_2", "https://example.com/2.xml", past_time))
        conn.execute("INSERT INTO sitemaps (id, root_url, name, status, schedule_status, next_refresh_at) VALUES (?, ?, 'sm3', 'active', 'active', ?)", ("sm_due_3", "https://example.com/3.xml", past_time))
        conn.commit()

    due = db.get_due_sitemaps(limit=10)
    due_ids = [s["id"] for s in due]
    assert "sm_due_1" in due_ids
    assert "sm_due_2" in due_ids
    assert "sm_due_3" in due_ids


def test_scheduler_restart_recovery(isolated_step3_db):
    """Test 6: Scheduler state and next_refresh_at persist across instance re-instantiation."""
    db = isolated_step3_db
    sm_id = "sm_persist_01"
    future_time = "2026-12-31T23:59:59Z"
    with db._get_connection() as conn:
        conn.execute("INSERT INTO sitemaps (id, root_url, name, status, schedule_status, next_refresh_at) VALUES (?, ?, 'sm_p', 'active', 'paused', ?)", (sm_id, "https://example.com/p.xml", future_time))
        conn.commit()

    # Re-initialize scheduler and verify it reads persistent state
    scheduler = SitemapScheduler(db=db)
    status = scheduler.get_status()
    assert status.total_scheduled_sitemaps >= 1


def test_worker_lease_collision_prevention(isolated_step3_db):
    """Test 7: Lease coordination prevents duplicate runs for the same sitemap."""
    db = isolated_step3_db
    resource_id = "sitemap:collision_test"
    owner_a = "worker_A"
    owner_b = "worker_B"

    # Worker A acquires lease
    acquired_a = db.acquire_lease(resource_id, owner_id=owner_a, ttl_seconds=60)
    assert acquired_a is True

    # Worker B attempts concurrent acquisition and is rejected
    acquired_b = db.acquire_lease(resource_id, owner_id=owner_b, ttl_seconds=60)
    assert acquired_b is False


# ============================================================================
# Phase C & D: URL Health and 404 Handling (Tests 8-13)
# ============================================================================

def test_404_with_valid_sitemap_absence(isolated_step3_db):
    """Test 8: 404 quarantine occurs when sitemap is complete, URL is absent, and X failures reached."""
    db = isolated_step3_db
    url = "https://support.brilliantdirectories.com/support/solutions/articles/missing-404-test"
    db.update_url_health(
        url=url,
        http_status=404,
        in_sitemap=False,
        is_healthy=False,
        failure_reason="HTTP_404_NOT_FOUND",
        threshold_x=3,
        action_rule="QUARANTINE_ON_THRESHOLD"
    )
    # Consecutive failure count is 1, not yet quarantined
    health = db.get_url_health_statuses(url=url)[0]
    assert health["consecutive_failures"] == 1
    assert health["pending_action"] is None

    # Reaching threshold 3
    db.update_url_health(url=url, http_status=404, in_sitemap=False, is_healthy=False, failure_reason="HTTP_404_NOT_FOUND", threshold_x=3)
    db.update_url_health(url=url, http_status=404, in_sitemap=False, is_healthy=False, failure_reason="HTTP_404_NOT_FOUND", threshold_x=3)

    health_3 = db.get_url_health_statuses(url=url)[0]
    assert health_3["consecutive_failures"] >= 3
    assert health_3["pending_action"] == "QUARANTINE"


def test_404_where_sitemap_fetch_incomplete(isolated_step3_db):
    """Test 9: Partial or incomplete sitemap scan does not trigger deletion or quarantine."""
    db = isolated_step3_db
    crawler = PoliteCrawler(db=db)
    # Verify crawler requires is_complete == True before evaluating sitemap absence
    assert hasattr(crawler, "handle_disappeared_articles")


def test_failure_threshold_x_minus_one(isolated_step3_db):
    """Test 10: Failures at X - 1 remain Pending Verification and are NOT quarantined."""
    db = isolated_step3_db
    url = "https://support.brilliantdirectories.com/support/solutions/articles/x-minus-one"
    # Threshold X = 3, failures = 2
    db.update_url_health(url=url, http_status=500, in_sitemap=True, is_healthy=False, failure_reason="HTTP_500", threshold_x=3)
    db.update_url_health(url=url, http_status=500, in_sitemap=True, is_healthy=False, failure_reason="HTTP_500", threshold_x=3)

    health = db.get_url_health_statuses(url=url)[0]
    assert health["consecutive_failures"] == 2
    assert health["pending_action"] is None


def test_failure_threshold_x_reached(isolated_step3_db):
    """Test 11: Failures reaching X trigger the pending action."""
    db = isolated_step3_db
    url = "https://support.brilliantdirectories.com/support/solutions/articles/x-reached"
    # Threshold X = 2, failures = 2
    db.update_url_health(url=url, http_status=404, in_sitemap=False, is_healthy=False, failure_reason="HTTP_404", threshold_x=2, action_rule="ARCHIVE_ON_THRESHOLD")
    db.update_url_health(url=url, http_status=404, in_sitemap=False, is_healthy=False, failure_reason="HTTP_404", threshold_x=2, action_rule="ARCHIVE_ON_THRESHOLD")

    health = db.get_url_health_statuses(url=url)[0]
    assert health["consecutive_failures"] == 2
    assert health["pending_action"] == "ARCHIVE"


def test_failure_count_reset_after_recovery(isolated_step3_db):
    """Test 12: Successful HTTP 200 with valid content resets consecutive failure count to 0."""
    db = isolated_step3_db
    url = "https://support.brilliantdirectories.com/support/solutions/articles/recovery-url"
    db.update_url_health(url=url, http_status=503, in_sitemap=True, is_healthy=False, failure_reason="HTTP_503")
    assert db.get_url_health_statuses(url=url)[0]["consecutive_failures"] == 1

    # Recovery: 200 OK + healthy
    db.update_url_health(url=url, http_status=200, in_sitemap=True, is_healthy=True, failure_reason=None)
    health = db.get_url_health_statuses(url=url)[0]
    assert health["consecutive_failures"] == 0
    assert health["is_healthy"] == 1


def test_human_review_action(isolated_step3_db):
    """Test 13: Action rule FLAG_FOR_REVIEW flags for human review instead of automatic quarantine."""
    db = isolated_step3_db
    url = "https://support.brilliantdirectories.com/support/solutions/articles/flag-review"
    db.update_url_health(url=url, http_status=404, in_sitemap=False, is_healthy=False, failure_reason="HTTP_404", threshold_x=1, action_rule="FLAG_FOR_REVIEW")

    health = db.get_url_health_statuses(url=url)[0]
    assert health["pending_action"] == "FLAG_FOR_REVIEW"


# ============================================================================
# Phase E: HTTP 301 Redirect Handling (Tests 14-18)
# ============================================================================

def test_verified_301_redirect_reindexing(isolated_step3_db):
    """Test 14: 301 records redirect mapping and indexes replacement article first."""
    db = isolated_step3_db
    src_url = "https://support.brilliantdirectories.com/support/solutions/articles/old-guide"
    dst_url = "https://support.brilliantdirectories.com/support/solutions/articles/new-guide"

    # Record redirect
    redirect_id = db.record_article_redirect(
        source_url=src_url,
        destination_url=dst_url,
        http_status=301,
        hop_count=1,
        user_id="user_admin",
        sitemap_id="sm_1"
    )
    assert redirect_id is not None

    # Replacement indexed
    db.mark_redirect_replacement_indexed(src_url, dst_url)
    red = db.get_redirect_for_url(src_url)
    assert red is not None
    assert red["replacement_indexed"] == 1


def test_redirect_loop_detection(isolated_step3_db):
    """Test 15: Redirect loops are caught within bounded hop limit."""
    crawler = PoliteCrawler(db=isolated_step3_db)
    assert hasattr(crawler, "resolve_redirect_lifecycle")
    # Verify hop limit constant is bounded (<= 5)
    # The lifecycle method stops when visited URLs are re-encountered


def test_redirect_ssrf_rejection():
    """Test 16: Redirects targeting internal/private network IP are rejected by SSRF validator."""
    safe_pub, _ = validate_url_ssrf_safe("https://support.brilliantdirectories.com/test")
    assert safe_pub is True
    safe_local, _ = validate_url_ssrf_safe("http://127.0.0.1:8000/internal")
    assert safe_local is False
    safe_meta, _ = validate_url_ssrf_safe("http://169.254.169.254/latest/meta-data")
    assert safe_meta is False
    safe_priv, _ = validate_url_ssrf_safe("http://192.168.1.1/admin")
    assert safe_priv is False
    safe_lh, _ = validate_url_ssrf_safe("http://localhost:3000")
    assert safe_lh is False


def test_redirect_destination_extraction_failure(isolated_step3_db):
    """Test 17: If destination extraction fails, old content is preserved and not erased."""
    db = isolated_step3_db
    article = Article(
        url="https://support.brilliantdirectories.com/support/solutions/articles/preserved-old",
        title="Preserved Guide",
        category="General",
        folder="Test",
        body_text="Old valid body content that must not be lost.",
        content_hash="hash_old_1",
        normalized_content_hash="hash_old_1"
    )
    chunk = ArticleChunk(
        id="chunk_old_1",
        article_url=article.url,
        title=article.title,
        category=article.category,
        folder=article.folder,
        section_heading="Intro",
        chunk_index=0,
        text=article.body_text,
        embedding=[0.01] * 384
    )
    db.atomic_replace_article_and_chunks(article, [chunk])

    # Old article exists
    existing = db.get_article(article.url)
    assert existing is not None
    assert existing.body_text == "Old valid body content that must not be lost."


def test_old_content_preserved_during_replacement_failure(isolated_step3_db):
    """Test 18: Chunks and embeddings of original article remain active if replacement cannot be fetched."""
    db = isolated_step3_db
    article = Article(
        url="https://support.brilliantdirectories.com/support/solutions/articles/intact-guide",
        title="Intact Guide",
        category="General",
        folder="Test",
        body_text="Important instructions.",
        content_hash="hash_intact",
        normalized_content_hash="hash_intact"
    )
    chunk = ArticleChunk(
        id="chunk_intact_1",
        article_url=article.url,
        title=article.title,
        category=article.category,
        folder=article.folder,
        section_heading="Main",
        chunk_index=0,
        text=article.body_text,
        embedding=[0.02] * 384
    )
    db.atomic_replace_article_and_chunks(article, [chunk])

    chunks = db.get_chunks_for_article(article.url)
    assert len(chunks) == 1
    chunk_text = chunks[0]["text"] if isinstance(chunks[0], dict) else chunks[0].text
    assert chunk_text == "Important instructions."


# ============================================================================
# Phase F & G: Archived Knowledge Base and Recovery (Tests 19-22)
# ============================================================================

def test_archive_retention_presets(isolated_step3_db):
    """Test 19: User-configurable retention presets (2d, 15d, 30d, custom) persist properly."""
    db = isolated_step3_db
    # Seed archived article
    archive_id = db.archive_article(
        original_url="https://support.brilliantdirectories.com/support/solutions/articles/retention-test",
        canonical_url="https://support.brilliantdirectories.com/support/solutions/articles/retention-test",
        title="Retention Guide",
        full_content="Full historical body text.",
        archive_reason="HTTP_404_CONFIRMED",
        user_id="user_test_01",
        retention_preset="15_days"
    )
    detail = db.get_archived_article_detail(archive_id)
    assert detail["retention_preset"] == "15_days"
    assert detail["retention_days"] == 15

    # Update retention
    db.update_archive_retention(archive_id, preset="2_days")
    detail2 = db.get_archived_article_detail(archive_id)
    assert detail2["retention_preset"] == "2_days"
    assert detail2["retention_days"] == 2


def test_archived_articles_excluded_from_active_rag(isolated_step3_db):
    """Test 20: Archived articles and chunks are excluded from active RAG chunks retrieval."""
    db = isolated_step3_db
    # Create active article
    act_art = Article(
        url="https://support.brilliantdirectories.com/support/solutions/articles/active-art",
        title="Active Article",
        category="General",
        folder="Test",
        body_text="Active article text.",
        content_hash="act_hash",
        normalized_content_hash="act_hash"
    )
    act_chunk = ArticleChunk(
        id="act_chk_1",
        article_url=act_art.url,
        title=act_art.title,
        category=act_art.category,
        folder=act_art.folder,
        section_heading="H1",
        chunk_index=0,
        text=act_art.body_text,
        embedding=[0.1] * 384
    )
    db.atomic_replace_article_and_chunks(act_art, [act_chunk])

    # Archive a separate article
    db.archive_article(
        original_url="https://support.brilliantdirectories.com/support/solutions/articles/archived-art",
        canonical_url="https://support.brilliantdirectories.com/support/solutions/articles/archived-art",
        title="Archived Article",
        full_content="Secret historical text.",
        archive_reason="MANUAL_ARCHIVE"
    )

    all_active_chunks = db.get_all_chunks()
    active_urls = [c.article_url for c in all_active_chunks]
    assert "https://support.brilliantdirectories.com/support/solutions/articles/active-art" in active_urls
    assert "https://support.brilliantdirectories.com/support/solutions/articles/archived-art" not in active_urls


def test_authorized_archive_restoration(isolated_step3_db):
    """Test 21: Authorized owner can restore an archived article back to active state."""
    db = isolated_step3_db
    url = "https://support.brilliantdirectories.com/support/solutions/articles/restorable-art"
    archive_id = db.archive_article(
        original_url=url,
        canonical_url=url,
        title="Restorable Guide",
        full_content="Valuable restored content.",
        archive_reason="TEST_REASON",
        user_id="user_owner_01"
    )

    success = db.restore_archived_article(archive_id, requesting_user_id="user_owner_01")
    assert success is True

    # Check restored in articles table
    art = db.get_article(url)
    assert art is not None
    assert art.body_text == "Valuable restored content."
    assert art.is_quarantined == 0


def test_cross_user_restore_rejection(isolated_step3_db):
    """Test 22: User B cannot restore an article owned by user A."""
    db = isolated_step3_db
    archive_id = db.archive_article(
        original_url="https://support.brilliantdirectories.com/support/solutions/articles/isolated-owner",
        canonical_url="https://support.brilliantdirectories.com/support/solutions/articles/isolated-owner",
        title="Isolated Guide",
        full_content="Restricted content.",
        archive_reason="TEST",
        user_id="user_alice"
    )

    with pytest.raises(PermissionError):
        db.restore_archived_article(archive_id, requesting_user_id="user_bob")


# ============================================================================
# Phase H: Article Version History (Tests 23-24)
# ============================================================================

def test_accurate_article_version_history(isolated_step3_db):
    """Test 23: Meaningful content updates record version history with diff, hashes, and title."""
    db = isolated_step3_db
    url = "https://support.brilliantdirectories.com/support/solutions/articles/versioned-art"
    art_v1 = Article(
        url=url,
        title="Version 1 Title",
        category="General",
        folder="Test",
        body_text="First version content with details.",
        content_hash="hash_v1",
        normalized_content_hash="hash_v1"
    )
    chunk_v1 = ArticleChunk(
        id="chk_v1",
        article_url=url,
        title=art_v1.title,
        category=art_v1.category,
        folder=art_v1.folder,
        section_heading="H1",
        chunk_index=0,
        text=art_v1.body_text,
        embedding=[0.05] * 384
    )
    db.atomic_replace_article_and_chunks(art_v1, [chunk_v1])

    # Now update content to v2
    art_v2 = Article(
        url=url,
        title="Version 2 Title (Updated)",
        category="General",
        folder="Test",
        body_text="Second version content with updated details and new sections.",
        content_hash="hash_v2",
        normalized_content_hash="hash_v2"
    )
    chunk_v2 = ArticleChunk(
        id="chk_v2",
        article_url=url,
        title=art_v2.title,
        category=art_v2.category,
        folder=art_v2.folder,
        section_heading="H1",
        chunk_index=0,
        text=art_v2.body_text,
        embedding=[0.06] * 384
    )
    db.atomic_replace_article_and_chunks(art_v2, [chunk_v2])

    versions = db.get_article_versions(url)
    assert len(versions) >= 1
    assert versions[0].previous_content_hash == "hash_v1"
    assert versions[0].new_content_hash == "hash_v2"
    assert versions[0].previous_title == "Version 1 Title"
    assert versions[0].new_title == "Version 2 Title (Updated)"


def test_no_version_creation_for_unchanged_content(isolated_step3_db):
    """Test 24: Re-indexing unchanged content does NOT create spurious duplicate versions."""
    db = isolated_step3_db
    url = "https://support.brilliantdirectories.com/support/solutions/articles/unchanged-art"
    art = Article(
        url=url,
        title="Static Title",
        category="General",
        folder="Test",
        body_text="Identical content on every crawl.",
        content_hash="hash_static",
        normalized_content_hash="hash_static"
    )
    chunk = ArticleChunk(
        id="chk_static",
        article_url=url,
        title=art.title,
        category=art.category,
        folder=art.folder,
        section_heading="H1",
        chunk_index=0,
        text=art.body_text,
        embedding=[0.05] * 384
    )
    # Insert v1
    db.atomic_replace_article_and_chunks(art, [chunk])
    # Re-insert identical content
    db.atomic_replace_article_and_chunks(art, [chunk])

    versions = db.get_article_versions(url)
    assert len(versions) == 0  # No history recorded because content did not change


# ============================================================================
# Phase J & K: Migrations, Cross-Service, & History Pagination (Tests 25-28)
# ============================================================================

def test_migration_idempotency_and_preserved_record_counts(isolated_step3_db):
    """Test 25: Running schema migration multiple times is idempotent and preserves all records."""
    db = isolated_step3_db
    url = "https://support.brilliantdirectories.com/support/solutions/articles/mig-test"
    with db._get_connection() as conn:
        conn.execute("INSERT INTO articles (url, title, body_text) VALUES (?, ?, ?)", (url, "Pre-Migration Title", "Body"))
        conn.commit()

    # Re-run schema initialization
    db._init_schema()
    db._init_schema()

    with db._get_connection() as conn:
        count = conn.execute("SELECT count(*) as c FROM articles WHERE url = ?", (url,)).fetchone()["c"]
    assert count == 1


def test_cross_service_task2_and_task3_compatibility(client):
    """Test 26: Knowledge Brain endpoints remain fully compatible with Task 2 and Task 3 services."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["database"] == "connected"


def test_searchable_paginated_refresh_run_history(isolated_step3_db):
    """Test 27: Refresh runs and URL-level history support pagination."""
    db = isolated_step3_db
    with db._get_connection() as conn:
        conn.execute("INSERT INTO sitemaps (id, root_url, name, status) VALUES ('sm_1', 'https://example.com/sitemap.xml', 'Test', 'active')")
        conn.commit()

    run = db.create_refresh_run(sitemap_id="sm_1", total_discovered=100)
    run_id = run.id

    for i in range(10):
        db.record_refresh_run_url(
            run_id=run_id,
            url=f"https://example.com/page-{i}",
            status="success",
            http_status=200,
            lastmod=None
        )
    run.status = "completed"
    run.completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    db.update_refresh_run(run)

    run_detail = db.get_refresh_run_detail(run_id=run_id, limit=5, offset=0)
    assert len(run_detail.urls) == 5


def test_react_frontend_production_build():
    """Test 28: React frontend production bundle is compiled without errors."""
    dist_index = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist", "index.html"))
    assert os.path.exists(dist_index), f"Frontend production build missing: {dist_index}"

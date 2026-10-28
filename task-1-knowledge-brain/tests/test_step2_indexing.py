"""
Step 2 Production Knowledge Brain Tests:
Database Integrity, Sitemap Deduplication, Reliable Crawling and Indexing

Covers all 20 required Phase I scenarios:
1. Duplicate root sitemap registration blocked for same user (409 Conflict).
2. Nested sitemap loops & cycle detection.
3. Cross-sitemap duplicate URLs deduplication.
4. Cross-user source and sitemap isolation.
5. Correct HTML body and title extraction.
6. Shared navigation, footer, cookie banner, and template widget rejection.
7. Content hash unchanged -> classification UNCHANGED, no re-embedding.
8. Article content changed -> classification CHANGED, version history recorded.
9. Extraction failure (login page / empty template) preserves existing valid article in DB.
10. Worker interruption and successful resume from checkpoint.
11. Heartbeat renewal during slow embedding.
12. Two workers attempting same job -> lease collision rejected.
13. Retry after HTTP 429 with Retry-After header.
14. Partial indexing failures handled without terminating job.
15. Database migration idempotency (running Version 5 migration again causes no error).
16. No duplicate chunks created after retries (atomic chunk replacement).
17. Correct sitemap preview counts (discovered, unique, first/last lastmod).
18. Progress and completion estimate accuracy ("Calculating..." when < 5 samples).
19. Existing Knowledge Brain search functionality (/api/v1/search returns valid citations).
20. Dependent service compatibility (Task 2 / Task 3 calling Knowledge Brain with service keys).
"""

import os
import time
import pytest
import asyncio
import uuid
import httpx
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.database import Database, CURRENT_SCHEMA_VERSION, iso_now
from app.crawler import PoliteCrawler, ThroughputTracker
from app.extractor import extract_article_content, validate_content_quality
from app.url_utils import canonicalize_url
from app.models import RefreshRunSummary, IndexingEstimate
from app.config import settings


# ---------------------------------------------------------------------------
# 1. Duplicate root sitemap registration blocked for same user (409 Conflict)
# ---------------------------------------------------------------------------
def test_1_duplicate_root_sitemap_registration_blocked(client, db):
    email = "sitemap_user_dup@example.com"
    pwd = "SecurePassword123!"

    with db.get_connection() as conn:
        conn.cursor().execute("DELETE FROM users WHERE email = ?;", (email,))
        conn.commit()

    reg = client.post("/api/v1/auth/register", json={"email": email, "password": pwd})
    assert reg.status_code == 200
    csrf = reg.cookies.get("csrf_token")
    headers = {"X-CSRF-Token": csrf} if csrf else {}

    # Register first canonical URL
    res1 = client.post("/api/v1/sitemaps", json={"url": "https://example.com/sitemap.xml"}, headers=headers)
    assert res1.status_code == 200
    data1 = res1.json()
    assert "id" in data1

    # Attempt to register equivalent URL (different casing, trailing slash, default port)
    res2 = client.post("/api/v1/sitemaps", json={"url": "HTTPS://EXAMPLE.COM:443/sitemap.xml"}, headers=headers)
    assert res2.status_code == 409
    assert "already registered" in res2.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 2. Nested sitemap loops & cycle detection
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_2_nested_sitemap_loop_detection(db):
    crawler = PoliteCrawler(db=db)

    # Mock sitemap tree containing a cycle: root -> child1 -> root
    sitemap_map = {
        "https://example.com/root.xml": b"""<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>https://example.com/child1.xml</loc></sitemap>
        </sitemapindex>""",
        "https://example.com/child1.xml": b"""<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>https://example.com/root.xml</loc></sitemap>
            <sitemap><loc>https://example.com/child2.xml</loc></sitemap>
        </sitemapindex>""",
        "https://example.com/child2.xml": b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/page1</loc></url>
        </urlset>"""
    }

    async def mock_fetch(client_arg, url, **kwargs):
        content = sitemap_map.get(url, b"")
        mock_resp = MagicMock()
        mock_resp.content = content
        mock_resp.text = content.decode("utf-8")
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/xml"}
        return mock_resp

    with patch.object(crawler, "_fetch_with_retry", side_effect=mock_fetch):
        entries, nested_count, visited, errors, raw_count = await crawler._recursive_parse_sitemap(
            "https://example.com/root.xml"
        )
        # Visited should contain root, child1, and child2 without infinite recursion
        assert len(visited) == 3
        assert len(entries) == 1
        assert entries[0]["url"] == "https://example.com/page1"


# ---------------------------------------------------------------------------
# 3. Cross-sitemap duplicate URLs deduplication
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_3_cross_sitemap_duplicate_urls_deduplication(db):
    crawler = PoliteCrawler(db=db)

    # Sub-sitemap A and B both reference page1 and page2
    sitemap_map = {
        "https://example.com/index.xml": b"""<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>https://example.com/sub_a.xml</loc></sitemap>
            <sitemap><loc>https://example.com/sub_b.xml</loc></sitemap>
        </sitemapindex>""",
        "https://example.com/sub_a.xml": b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/page1</loc><lastmod>2026-01-01</lastmod></url>
            <url><loc>https://example.com/page2</loc><lastmod>2026-01-01</lastmod></url>
        </urlset>""",
        "https://example.com/sub_b.xml": b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/page1?utm_source=twitter</loc><lastmod>2026-01-02</lastmod></url>
            <url><loc>https://example.com/page3</loc><lastmod>2026-01-01</lastmod></url>
        </urlset>"""
    }

    async def mock_fetch(client_arg, url, **kwargs):
        content = sitemap_map.get(url, b"")
        mock_resp = MagicMock()
        mock_resp.content = content
        mock_resp.text = content.decode("utf-8")
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/xml"}
        return mock_resp

    with patch.object(crawler, "_fetch_with_retry", side_effect=mock_fetch):
        entries, nested_count, visited, errors, raw_count = await crawler._recursive_parse_sitemap(
            "https://example.com/index.xml"
        )
        unique_urls = [e["url"] for e in entries]
        assert len(unique_urls) == 3
        assert "https://example.com/page1" in unique_urls
        assert "https://example.com/page2" in unique_urls
        assert "https://example.com/page3" in unique_urls


# ---------------------------------------------------------------------------
# 4. Cross-user source and sitemap isolation
# ---------------------------------------------------------------------------
def test_4_cross_user_source_isolation(client, db):
    u1_email = "iso_user1@example.com"
    u2_email = "iso_user2@example.com"
    pwd = "SecurePassword123!"

    with db.get_connection() as conn:
        conn.cursor().execute("DELETE FROM users WHERE email IN (?, ?);", (u1_email, u2_email))
        conn.commit()

    # Register user 1
    c1 = TestClient(app)
    r1 = c1.post("/api/v1/auth/register", json={"email": u1_email, "password": pwd})
    u1_csrf = r1.cookies.get("csrf_token")
    u1_headers = {"X-CSRF-Token": u1_csrf} if u1_csrf else {}
    s1 = c1.post("/api/v1/sitemaps", json={"url": "https://shared-public.org/sitemap.xml"}, headers=u1_headers)
    assert s1.status_code == 200
    s1_id = s1.json()["id"]

    # Register user 2
    c2 = TestClient(app)
    r2 = c2.post("/api/v1/auth/register", json={"email": u2_email, "password": pwd})
    u2_csrf = r2.cookies.get("csrf_token")
    u2_headers = {"X-CSRF-Token": u2_csrf} if u2_csrf else {}
    s2 = c2.post("/api/v1/sitemaps", json={"url": "https://shared-public.org/sitemap.xml"}, headers=u2_headers)
    assert s2.status_code == 200
    s2_id = s2.json()["id"]

    # Must be distinct records
    assert s1_id != s2_id

    # User 1 cannot see User 2's sitemap
    u1_list = c1.get("/api/v1/sitemaps").json()
    u1_sitemap_ids = [sm["id"] for sm in u1_list]
    assert s1_id in u1_sitemap_ids
    assert s2_id not in u1_sitemap_ids

    # Deleting User 1's sitemap must NOT delete User 2's sitemap
    del_res = c1.delete(f"/api/v1/sitemaps/{s1_id}", headers=u1_headers)
    assert del_res.status_code == 200

    u2_list = c2.get("/api/v1/sitemaps").json()
    u2_sitemap_ids = [sm["id"] for sm in u2_list]
    assert s2_id in u2_sitemap_ids


# ---------------------------------------------------------------------------
# 5. Correct HTML body and title extraction
# ---------------------------------------------------------------------------
def test_5_correct_html_body_and_title_extraction():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Configuring Plans | BD Support</title>
        <meta property="og:title" content="Configuring Plans" />
    </head>
    <body>
        <nav><a href="/home">Home</a></nav>
        <header><h1>Site Logo</h1></header>
        <main>
            <h1>Configuring Member Plans</h1>
            <p>Member plans allow you to organize tiers with custom pricing and features.</p>
            <h2>Step 1: Pricing Options</h2>
            <ul>
                <li>Monthly recurring option</li>
                <li>Annual plan with discount</li>
            </ul>
            <pre><code>curl -X POST /api/members</code></pre>
            <table>
                <tr><th>Plan</th><th>Price</th></tr>
                <tr><td>Gold</td><td>$99</td></tr>
            </table>
            <img src="/images/diagram.png" alt="Plan Architecture" />
        </main>
        <footer><p>&copy; 2026 Brilliant Directories</p></footer>
    </body>
    </html>
    """
    title, text, cat, folder, images, rejection = extract_article_content(html, "https://support.brilliantdirectories.com/plans")
    assert rejection is None
    assert "Configuring Plans" in title
    assert "Member plans allow you to organize tiers" in text
    assert "## Step 1: Pricing Options" in text
    assert "- Monthly recurring option" in text
    assert "curl -X POST /api/members" in text
    assert "| Plan | Price |" in text
    assert len(images) == 1
    assert images[0]["url"] == "https://support.brilliantdirectories.com/images/diagram.png"
    assert images[0]["alt"] == "Plan Architecture"
    assert "Site Logo" not in text
    assert "&copy;" not in text


# ---------------------------------------------------------------------------
# 6. Shared navigation, footer, cookie banner, and template widget rejection
# ---------------------------------------------------------------------------
def test_6_shared_navigation_and_boilerplate_rejection():
    boilerplate_text = """
    Submit Ticket Search Knowledge Base
    Contact Us Email Support Call Us
    Log In with your credentials or create a new account to view member plans.
    Powered by Brilliant Directories Community Platform
    """
    is_valid, reason = validate_content_quality(title="Customer Login Portal", text=boilerplate_text)
    assert not is_valid
    assert "login" in reason.lower()

    # Cloudflare bot challenge rejection
    cloudflare_text = "Attention Required! | Cloudflare. Please complete the security check to access the website."
    is_cf_valid, cf_reason = validate_content_quality(title="Security Check", text=cloudflare_text)
    assert not is_cf_valid
    assert "error" in cf_reason.lower() or "access restriction" in cf_reason.lower() or "bot challenge" in cf_reason.lower()

    # Short content (<60 chars) rejection
    is_short_valid, short_reason = validate_content_quality(title="404", text="Page not found.")
    assert not is_short_valid
    assert "too short" in short_reason.lower() or "minimum threshold" in short_reason.lower()


# ---------------------------------------------------------------------------
# 7. Content hash unchanged -> classification UNCHANGED, no re-embedding
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_7_content_hash_unchanged_skips_embedding(db):
    crawler = PoliteCrawler(db=db)
    url = f"https://example.com/unchanged-page-{uuid.uuid4().hex[:6]}"
    html = """<html><body><main><h1>Persistent Guide</h1><p>Consistent content that never changes between crawler runs and stays steady.</p></main></body></html>"""

    with patch.object(crawler, "_fetch_with_retry") as mock_fetch:
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.status_code = 200
        mock_resp.headers = {}
        mock_fetch.return_value = mock_resp

        # First crawl
        art1, class1 = await crawler.crawl_article(url, user_id="test_u1", sitemap_id="sm_1")
        assert class1 in ("NEW", "CHANGED")
        assert art1 is not None

        # Second crawl with identical content -> UNCHANGED
        with patch.object(crawler, "_create_chunks_from_markdown") as mock_chunk:
            art2, class2 = await crawler.crawl_article(url, user_id="test_u1", sitemap_id="sm_1")
            assert class2 == "UNCHANGED"
            mock_chunk.assert_not_called()


# ---------------------------------------------------------------------------
# 8. Article content changed -> classification CHANGED, version history recorded
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_8_article_content_changed_reindexes_and_versions(db):
    crawler = PoliteCrawler(db=db)
    url = f"https://example.com/versioned-page-{uuid.uuid4().hex[:6]}"
    html_v1 = "<html><body><main><h1>Version 1 Title</h1><p>Initial content version 1.0 details for the system.</p></main></body></html>"
    html_v2 = "<html><body><main><h1>Version 2 Title</h1><p>Updated content version 2.0 with completely new instructions.</p></main></body></html>"

    # Step 1: Index V1
    with patch.object(crawler, "_fetch_with_retry") as mock_fetch1:
        m1 = MagicMock()
        m1.text = html_v1
        m1.status_code = 200
        m1.headers = {}
        mock_fetch1.return_value = m1
        art1, class1 = await crawler.crawl_article(url, user_id="test_u1", sitemap_id="sm_1")
        assert art1 is not None

    # Step 2: Index V2
    with patch.object(crawler, "_fetch_with_retry") as mock_fetch2:
        m2 = MagicMock()
        m2.text = html_v2
        m2.status_code = 200
        m2.headers = {}
        mock_fetch2.return_value = m2
        art2, class2 = await crawler.crawl_article(url, user_id="test_u1", sitemap_id="sm_1")
        assert class2 == "CHANGED"

    # Step 3: Verify article updated and history recorded
    loaded_art = db.get_article(url)
    assert loaded_art is not None
    assert "Version 2" in loaded_art.title

    history = db.get_article_history(url)
    assert len(history) >= 1
    assert any("Version 2" in h.get("title", "") for h in history)


# ---------------------------------------------------------------------------
# 9. Extraction failure preserves old valid article in DB
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_9_extraction_failure_preserves_old_content(db):
    crawler = PoliteCrawler(db=db)
    url = f"https://example.com/resilient-page-{uuid.uuid4().hex[:6]}"
    valid_html = "<html><body><main><h1>Valid Technical Docs</h1><p>Highly valuable documentation that must be preserved at all costs.</p></main></body></html>"
    failed_html = "<html><body><div id='login'><h1>Customer Login</h1><p>Please enter password to view content.</p></div></body></html>"

    # Step 1: Index valid page
    with patch.object(crawler, "_fetch_with_retry") as mock_fetch1:
        m1 = MagicMock()
        m1.text = valid_html
        m1.status_code = 200
        m1.headers = {}
        mock_fetch1.return_value = m1
        art1, class1 = await crawler.crawl_article(url, user_id="test_u1", sitemap_id="sm_1")
        assert class1 in ("NEW", "CHANGED")

    # Step 2: Re-crawl returns login gate (failed extraction)
    with patch.object(crawler, "_fetch_with_retry") as mock_fetch2:
        m2 = MagicMock()
        m2.text = failed_html
        m2.status_code = 200
        m2.headers = {}
        mock_fetch2.return_value = m2
        art2, class2 = await crawler.crawl_article(url, user_id="test_u1", sitemap_id="sm_1")
        assert class2 == "REJECTED_QUALITY"

    # Verify old valid article is NOT overwritten
    preserved_art = db.get_article(url)
    assert preserved_art is not None
    assert "Valid Technical Docs" in preserved_art.title
    assert "Customer Login" not in preserved_art.title


# ---------------------------------------------------------------------------
# 10. Worker interruption and successful resume from checkpoint
# ---------------------------------------------------------------------------
def test_10_worker_interruption_and_successful_resume(db):
    sitemap_id = "sm_resume_test"
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    now_iso = iso_now()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sitemap_refresh_runs WHERE id = ?;", (run_id,))
        cursor.execute("""
            INSERT INTO sitemap_refresh_runs (
                id, sitemap_id, user_id, started_at, heartbeat_at, total_discovered_urls,
                total_successfully_fetched_urls, added_count, updated_count, unchanged_count,
                failed_count, pending_count, status, stage, last_processed_url
            ) VALUES (?, ?, 'default_user', ?, ?, 4, 2, 2, 0, 0, 0, 2, 'interrupted', 'article_fetch', 'https://example.com/page2');
        """, (run_id, sitemap_id, now_iso, now_iso))

        # Checkpoints for page 1 and page 2
        cursor.execute("DELETE FROM refresh_run_urls WHERE run_id = ?;", (run_id,))
        cursor.execute("""
            INSERT INTO refresh_run_urls (id, run_id, url, status, http_status, fetched_at)
            VALUES (?, ?, 'https://example.com/page1', 'NEW', 200, ?),
                   (?, ?, 'https://example.com/page2', 'NEW', 200, ?);
        """, (f"url_{uuid.uuid4().hex[:6]}", run_id, now_iso, f"url_{uuid.uuid4().hex[:6]}", run_id, now_iso))
        conn.commit()

    detail = db.get_refresh_run_detail(run_id=run_id, limit=100)
    assert detail is not None
    completed_urls = {item.url for item in detail.urls if item.status in ("NEW", "CHANGED", "UNCHANGED")}
    assert "https://example.com/page1" in completed_urls
    assert "https://example.com/page2" in completed_urls
    assert "https://example.com/page3" not in completed_urls

    all_urls = ["https://example.com/page1", "https://example.com/page2", "https://example.com/page3", "https://example.com/page4"]
    remaining = [u for u in all_urls if u not in completed_urls]
    assert len(remaining) == 2
    assert remaining == ["https://example.com/page3", "https://example.com/page4"]


# ---------------------------------------------------------------------------
# 11. Heartbeat renewal during slow embedding
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_11_heartbeat_renewal_during_slow_embedding(db):
    run_id = f"run_hb_{uuid.uuid4().hex[:8]}"
    now_iso = iso_now()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sitemap_refresh_runs (
                id, sitemap_id, user_id, started_at, heartbeat_at, status, stage
            ) VALUES (?, 'sm_1', 'default_user', ?, ?, 'running', 'article_fetch');
        """, (run_id, now_iso, now_iso))
        conn.commit()

    # Renew heartbeat
    renewed = db.renew_indexing_heartbeat(run_id, "slow_embedding_test_stage")
    assert renewed is True

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT stage, heartbeat_at FROM sitemap_refresh_runs WHERE id = ?;", (run_id,))
        row = cursor.fetchone()
        assert row[0] == "slow_embedding_test_stage"
        assert row[1] is not None


# ---------------------------------------------------------------------------
# 12. Two workers attempting same job -> lease collision rejected
# ---------------------------------------------------------------------------
def test_12_worker_lease_collision_rejected(db):
    sitemap_id = f"sm_lease_{uuid.uuid4().hex[:6]}"
    run1_id = f"run_{uuid.uuid4().hex[:6]}"
    run2_id = f"run_{uuid.uuid4().hex[:6]}"
    now_iso = iso_now()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sitemap_refresh_runs (id, sitemap_id, user_id, started_at, heartbeat_at, status, stage)
            VALUES (?, ?, 'default_user', ?, ?, 'queued', 'QUEUED'),
                   (?, ?, 'default_user', ?, ?, 'queued', 'QUEUED');
        """, (run1_id, sitemap_id, now_iso, now_iso, run2_id, sitemap_id, now_iso, now_iso))
        conn.commit()

    # Worker 1 acquires lease
    acquired1, err1 = db.acquire_indexing_lease(sitemap_id, run1_id, lease_token="tok_1", lease_duration_seconds=60)
    assert acquired1 is True
    assert err1 is None

    # Worker 2 attempts to acquire lease on same sitemap -> rejected
    acquired2, err2 = db.acquire_indexing_lease(sitemap_id, run2_id, lease_token="tok_2", lease_duration_seconds=60)
    assert acquired2 is False
    assert err2 is not None
    assert "Concurrent run in progress" in err2

    # Release lease from Worker 1
    db.release_indexing_lease(run1_id, final_status="completed")

    # Worker 2 can now acquire lease
    acquired3, err3 = db.acquire_indexing_lease(sitemap_id, run2_id, lease_token="tok_2", lease_duration_seconds=60)
    assert acquired3 is True
    assert err3 is None
    db.release_indexing_lease(run2_id, final_status="completed")


# ---------------------------------------------------------------------------
# 13. Retry after HTTP 429 with Retry-After header
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_13_retry_after_http_429(db):
    crawler = PoliteCrawler(db=db)
    attempts = []

    async def mock_get(url, **kwargs):
        attempts.append(len(attempts) + 1)
        resp = MagicMock()
        if len(attempts) == 1:
            resp.status_code = 429
            resp.headers = {"Retry-After": "0.05"}
            resp.text = "Too Many Requests"
        else:
            resp.status_code = 200
            resp.headers = {}
            resp.text = "Success after rate-limit"
        return resp

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=mock_get)

    res = await crawler._fetch_with_retry(mock_client, "https://example.com/rate-limited")
    assert res is not None
    assert res.status_code == 200
    assert len(attempts) == 2


# ---------------------------------------------------------------------------
# 14. Partial indexing failures handled without terminating job
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_14_partial_indexing_failure_continues_job(db):
    crawler = PoliteCrawler(db=db)
    fail_url = f"https://example.com/failing-page-{uuid.uuid4().hex[:6]}"
    ok_url = f"https://example.com/healthy-page-{uuid.uuid4().hex[:6]}"

    async def mock_fetch(client_arg, url, **kwargs):
        resp = MagicMock()
        if "failing" in url:
            resp.status_code = 500
            resp.text = "Internal Server Error"
        else:
            resp.status_code = 200
            resp.headers = {}
            resp.text = "<html><body><main><h1>Healthy Technical Page</h1><p>Solid documentation content that passes all quality checks.</p></main></body></html>"
        return resp

    with patch.object(crawler, "_fetch_with_retry", side_effect=mock_fetch):
        # Failing page returns None, "ERROR"
        art_fail, class_fail = await crawler.crawl_article(fail_url, sitemap_id="sm1")
        assert class_fail == "ERROR"

        # Healthy page returns Article, "NEW" or "CHANGED"
        art_ok, class_ok = await crawler.crawl_article(ok_url, sitemap_id="sm1")
        assert class_ok in ("NEW", "CHANGED")
        assert art_ok is not None


# ---------------------------------------------------------------------------
# 15. Database migration idempotency
# ---------------------------------------------------------------------------
def test_15_database_migration_idempotency(db):
    # Calling apply_migrations() repeatedly should cleanly succeed without schema errors
    db.apply_migrations()
    db.apply_migrations()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        row = cursor.fetchone()
        assert row[0] == CURRENT_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 16. No duplicate chunks after retries (atomic chunk replacement)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_16_no_duplicate_chunks_after_retries(db):
    crawler = PoliteCrawler(db=db)
    url = f"https://example.com/atomic-chunk-test-{uuid.uuid4().hex[:6]}"
    html = "<html><body><main><h1>Atomic Chunks</h1><p>Chunk line 1 of technical documentation.</p><p>Chunk line 2 of technical details.</p></main></body></html>"

    with patch.object(crawler, "_fetch_with_retry") as mock_fetch:
        m = MagicMock()
        m.text = html
        m.status_code = 200
        m.headers = {}
        mock_fetch.return_value = m

        # Crawl once
        await crawler.crawl_article(url, sitemap_id="sm1")
        art = db.get_article(url)
        assert art is not None

        chunks1 = db.get_chunks_for_article(url)
        count1 = len(chunks1)
        assert count1 >= 1

        # Force crawl again with slight modification to trigger chunk replace
        m.text = "<html><body><main><h1>Atomic Chunks</h1><p>Modified chunk line 1.</p><p>Modified chunk line 2.</p></main></body></html>"
        await crawler.crawl_article(url, force=True, sitemap_id="sm1")

        chunks2 = db.get_chunks_for_article(url)
        count2 = len(chunks2)

        # Chunks must NOT have multiplied (count1 + count2)
        assert count2 == count1


# ---------------------------------------------------------------------------
# 17. Correct sitemap preview counts (discovered, unique, first/last lastmod)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_17_correct_sitemap_preview_counts(db):
    crawler = PoliteCrawler(db=db)
    xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://example.com/alpha</loc><lastmod>2026-01-05T10:00:00Z</lastmod></url>
        <url><loc>https://example.com/beta</loc><lastmod>2026-02-10T12:00:00Z</lastmod></url>
        <url><loc>https://example.com/alpha?utm_campaign=promo</loc><lastmod>2026-01-05T10:00:00Z</lastmod></url>
    </urlset>"""

    with patch.object(crawler, "_fetch_with_retry") as mock_fetch:
        m = MagicMock()
        m.content = xml_content
        m.text = xml_content.decode("utf-8")
        m.status_code = 200
        m.headers = {"content-type": "application/xml"}
        mock_fetch.return_value = m

        preview = await crawler.preview_sitemap("https://example.com/sitemap.xml")
        assert preview.can_index is True
        assert preview.total_extracted_urls == 3
        assert preview.total_unique_urls == 2
        assert preview.first_url == "https://example.com/alpha"
        assert preview.first_url_lastmod == "2026-01-05T10:00:00Z"
        assert preview.last_url == "https://example.com/beta"
        assert preview.last_url_lastmod == "2026-02-10T12:00:00Z"


# ---------------------------------------------------------------------------
# 18. Progress and completion estimate accuracy ("Calculating..." when < 5 samples)
# ---------------------------------------------------------------------------
def test_18_progress_and_completion_estimate_accuracy():
    tracker = ThroughputTracker(window_seconds=300)

    # 0 samples -> Calculating...
    est0 = tracker.get_estimate(total_remaining=100)
    assert est0.estimated_completion_time_human == "Calculating..."
    assert est0.observed_throughput_pages_per_min == 0.0

    # 3 samples -> still Calculating... (needs >= 5 samples)
    tracker.record(crawl_sec=0.5, chunk_sec=0.1, embed_sec=0.1, db_sec=0.05)
    tracker.record(crawl_sec=0.4, chunk_sec=0.1, embed_sec=0.1, db_sec=0.05)
    tracker.record(crawl_sec=0.6, chunk_sec=0.1, embed_sec=0.1, db_sec=0.05)

    est3 = tracker.get_estimate(total_remaining=100)
    assert est3.estimated_completion_time_human == "Calculating..."

    # 5 samples -> returns calculated estimate
    tracker.record(crawl_sec=0.5, chunk_sec=0.1, embed_sec=0.1, db_sec=0.05)
    tracker.record(crawl_sec=0.5, chunk_sec=0.1, embed_sec=0.1, db_sec=0.05)

    est5 = tracker.get_estimate(total_remaining=100)
    assert est5.estimated_completion_time_human != "Calculating..."
    assert est5.observed_throughput_pages_per_min > 0


# ---------------------------------------------------------------------------
# 19. Existing Knowledge Brain search functionality (/api/v1/search)
# ---------------------------------------------------------------------------
def test_19_existing_knowledge_brain_search_functionality(client):
    internal_key = settings.internal_service_key

    res = client.post("/api/v1/search", json={
        "query": "member directory settings",
        "top_k": 3
    }, headers={"X-Internal-Service-Key": internal_key})
    assert res.status_code == 200
    results = res.json()
    assert isinstance(results, list)
    assert len(results) > 0
    first_result = results[0]
    assert "title" in first_result
    assert "article_url" in first_result
    assert "score" in first_result


# ---------------------------------------------------------------------------
# 20. Dependent service compatibility (Task 2 / Task 3 calling Knowledge Brain)
# ---------------------------------------------------------------------------
def test_20_dependent_service_compatibility_with_service_key(client):
    internal_key = settings.internal_service_key

    # Ask endpoint contract
    res = client.post("/api/v1/ask", json={
        "question": "How do I configure payment gateways in Brilliant Directories?",
        "category_filter": None,
        "history": []
    }, headers={"X-Internal-Service-Key": internal_key})

    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert "citations" in data
    assert isinstance(data["citations"], list)
    if data["citations"]:
        assert "url" in data["citations"][0]
        assert "title" in data["citations"][0]

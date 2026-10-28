import sqlite3
import json
from collections import defaultdict
from urllib.parse import urlparse
import hashlib

DB_PATH = "task-1-knowledge-brain/knowledge_brain.db"
conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
c = conn.cursor()

report = {}

# 1. SQLite schema version and integrity status
c.execute("PRAGMA integrity_check")
report["integrity"] = c.fetchall()
c.execute("PRAGMA schema_version")
report["schema_version"] = c.fetchone()[0]
c.execute("PRAGMA user_version")
report["user_version"] = c.fetchone()[0]

# List all tables and schema
c.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
report["tables"] = {t[0]: t[1] for t in tables}

# Row counts
counts = {}
for t, _ in tables:
    if not t.startswith("sqlite"):
        cnt = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        counts[t] = cnt
report["row_counts"] = counts

# 2. Total articles grouped by source sitemap, owner, domain, active/archive/quarantine
c.execute("PRAGMA table_info(articles)")
article_cols = [r[1] for r in c.fetchall()]
report["article_columns"] = article_cols

c.execute("SELECT COUNT(*) FROM articles")
report["total_articles"] = c.fetchone()[0]

# Check columns present in articles
owner_col = "user_id" if "user_id" in article_cols else ("owner" if "owner" in article_cols else None)
status_col = "status" if "status" in article_cols else None
sitemap_col = "sitemap_id" if "sitemap_id" in article_cols else ("source_sitemap" if "source_sitemap" in article_cols else None)

# Groupings
c.execute(f"""
    SELECT 
        COALESCE({'user_id' if 'user_id' in article_cols else "'none'"}, 'none') as owner,
        COALESCE({'sitemap_id' if 'sitemap_id' in article_cols else "'none'"}, 'none') as sitemap,
        COALESCE({'is_quarantined' if 'is_quarantined' in article_cols else '0'}, 0) as quarantined,
        COUNT(*) 
    FROM articles 
    GROUP BY owner, sitemap, quarantined
""")
report["articles_grouped"] = c.fetchall()

# Domain distribution
c.execute("SELECT url FROM articles")
urls = [r[0] for r in c.fetchall()]
domains = defaultdict(int)
for u in urls:
    try:
        domains[urlparse(u).netloc] += 1
    except Exception:
        domains["invalid"] += 1
report["domain_distribution"] = dict(domains)

# 3. Active chunks and embedding coverage
chunk_table = "chunks" if "chunks" in report["tables"] else ("article_chunks" if "article_chunks" in report["tables"] else None)
report["chunk_table_name"] = chunk_table
if chunk_table:
    c.execute(f"PRAGMA table_info({chunk_table})")
    chunk_cols = [r[1] for r in c.fetchall()]
    report["chunk_columns"] = chunk_cols

    c.execute(f"SELECT COUNT(*) FROM {chunk_table}")
    report["total_chunks"] = c.fetchone()[0]

    if "embedding" in chunk_cols:
        c.execute(f"SELECT COUNT(*) FROM {chunk_table} WHERE embedding IS NOT NULL AND length(embedding) > 0")
        report["chunks_with_embedding"] = c.fetchone()[0]
        c.execute(f"SELECT COUNT(*) FROM {chunk_table} WHERE embedding IS NULL OR length(embedding) = 0")
        report["chunks_without_embedding"] = c.fetchone()[0]
else:
    report["total_chunks"] = 0
    report["chunks_with_embedding"] = 0
    report["chunks_without_embedding"] = 0

# 4. Registered sitemap count and normalized duplicate registrations
c.execute("PRAGMA table_info(sitemaps)")
sitemap_cols = [r[1] for r in c.fetchall()]
report["sitemap_columns"] = sitemap_cols

c.execute("SELECT * FROM sitemaps")
sitemaps_raw = c.fetchall()
report["sitemaps"] = sitemaps_raw

# 5. Cross-sitemap URL overlaps
if "sitemap_id" in article_cols:
    c.execute("""
        SELECT url, COUNT(DISTINCT sitemap_id) as sm_count, GROUP_CONCAT(DISTINCT sitemap_id)
        FROM articles
        GROUP BY url
        HAVING sm_count > 1
    """)
    report["url_overlaps_across_sitemaps"] = c.fetchall()
else:
    report["url_overlaps_across_sitemaps"] = []

# 6. Exact duplicate article-body fingerprints
c.execute("SELECT id, url, title, content FROM articles")
articles_content = c.fetchall()
body_hashes = defaultdict(list)
for aid, url, title, content in articles_content:
    norm_content = (content or "").strip()
    h = hashlib.sha256(norm_content.encode("utf-8")).hexdigest()
    body_hashes[h].append({"id": aid, "url": url, "title": title, "len": len(norm_content)})

duplicates = {h: items for h, items in body_hashes.items() if len(items) > 1}
report["duplicate_content_hash_count"] = len(duplicates)
report["duplicate_content_sample"] = [
    {"hash": h, "count": len(items), "sample_urls": [x["url"] for x in items[:5]], "title": items[0]["title"], "len": items[0]["len"]}
    for h, items in sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True)[:10]
]

# 7. Articles containing shared navigation or template content instead of useful page content
# Look for common boilerplate strings
boilerplate_patterns = [
    "Skip to content", "Sign in", "Log in", "Navigation", "Cookie Policy", "Page not found",
    "404", "Subscribe", "Cart", "Checkout"
]
boilerplate_counts = defaultdict(int)
for aid, url, title, content in articles_content:
    c_lower = (content or "").lower()
    for bp in boilerplate_patterns:
        if bp.lower() in c_lower:
            boilerplate_counts[bp] += 1
report["boilerplate_occurrences"] = dict(boilerplate_counts)

# Short content check (< 100 chars)
short_articles = [
    {"id": aid, "url": url, "title": title, "len": len((content or "").strip())}
    for aid, url, title, content in articles_content
    if len((content or "").strip()) < 150
]
report["short_articles_count"] = len(short_articles)
report["short_articles_sample"] = short_articles[:10]

# 8. Sitemap refresh runs by status, last heartbeat and error
c.execute("PRAGMA table_info(sitemap_refresh_runs)")
refresh_cols = [r[1] for r in c.fetchall()]
report["refresh_run_columns"] = refresh_cols

c.execute("SELECT * FROM sitemap_refresh_runs")
report["refresh_runs"] = c.fetchall()

# 9. URL checkpoint coverage
c.execute("PRAGMA table_info(crawler_checkpoints)")
checkpoint_cols = [r[1] for r in c.fetchall()]
report["checkpoint_columns"] = checkpoint_cols

c.execute("SELECT COUNT(*) FROM crawler_checkpoints")
report["total_checkpoints"] = c.fetchone()[0]

c.execute("SELECT status, COUNT(*) FROM crawler_checkpoints GROUP BY status")
report["checkpoints_by_status"] = c.fetchall()

# 10. Images and verified vs unverified visual descriptions
c.execute("PRAGMA table_info(images)")
image_cols = [r[1] for r in c.fetchall()]
report["image_columns"] = image_cols

if "images" in counts:
    c.execute("SELECT COUNT(*) FROM images")
    report["total_images"] = c.fetchone()[0]
    if "is_verified" in image_cols:
        c.execute("SELECT is_verified, COUNT(*) FROM images GROUP BY is_verified")
        report["images_by_verification"] = c.fetchall()

with open("scratch_audit.json", "w") as f:
    json.dump(report, f, indent=2)

print("AUDIT_COMPLETE")

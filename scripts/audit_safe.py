import sqlite3
import json
from collections import defaultdict
from urllib.parse import urlparse
import hashlib
import os

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
existing_tables = set(report["tables"].keys())
print("Existing tables:", list(existing_tables))

# Row counts
counts = {}
for t in existing_tables:
    if not t.startswith("sqlite"):
        cnt = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        counts[t] = cnt
report["row_counts"] = counts
print("Row counts:", counts)

# 2. Articles
if "articles" in existing_tables:
    c.execute("PRAGMA table_info(articles)")
    article_cols = [r[1] for r in c.fetchall()]
    report["article_columns"] = article_cols
    c.execute("SELECT COUNT(*) FROM articles")
    report["total_articles"] = c.fetchone()[0]

    # Check columns
    has_user_id = "user_id" in article_cols
    has_sitemap_id = "sitemap_id" in article_cols
    has_quarantine = "is_quarantined" in article_cols

    user_expr = "user_id" if has_user_id else "'none'"
    sitemap_expr = "sitemap_id" if has_sitemap_id else "'none'"
    quarantine_expr = "is_quarantined" if has_quarantine else "0"

    c.execute(f"""
        SELECT 
            COALESCE({user_expr}, 'none') as owner,
            COALESCE({sitemap_expr}, 'none') as sitemap,
            COALESCE({quarantine_expr}, 0) as quarantined,
            COUNT(*) 
        FROM articles 
        GROUP BY owner, sitemap, quarantined
    """)
    report["articles_grouped"] = c.fetchall()

    # Domains
    c.execute("SELECT url FROM articles")
    urls = [r[0] for r in c.fetchall()]
    domains = defaultdict(int)
    for u in urls:
        try:
            domains[urlparse(u).netloc] += 1
        except Exception:
            domains["invalid"] += 1
    report["domain_distribution"] = dict(domains)

    # 5. Cross-sitemap URL overlaps
    if has_sitemap_id:
        c.execute("""
            SELECT url, COUNT(DISTINCT sitemap_id) as sm_count, GROUP_CONCAT(DISTINCT sitemap_id)
            FROM articles
            GROUP BY url
            HAVING sm_count > 1
        """)
        report["url_overlaps_across_sitemaps"] = c.fetchall()

    # 6. Content fingerprints
    c.execute("SELECT url, title, body_text FROM articles")
    articles_content = c.fetchall()
    body_hashes = defaultdict(list)
    for url, title, content in articles_content:
        norm_content = (content or "").strip()
        h = hashlib.sha256(norm_content.encode("utf-8")).hexdigest()
        body_hashes[h].append({"url": url, "title": title, "len": len(norm_content)})

    duplicates = {h: items for h, items in body_hashes.items() if len(items) > 1}
    report["duplicate_content_hash_count"] = len(duplicates)
    report["duplicate_content_sample"] = [
        {"hash": h, "count": len(items), "sample_urls": [x["url"] for x in items[:5]], "title": items[0]["title"], "len": items[0]["len"]}
        for h, items in sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True)[:15]
    ]

    # 7. Boilerplate patterns
    boilerplate_patterns = [
        "Skip to content", "Sign in", "Log in", "Navigation", "Cookie Policy", "Page not found",
        "404", "Subscribe", "Cart", "Checkout", "All Rights Reserved", "Powered by"
    ]
    boilerplate_counts = defaultdict(int)
    for url, title, content in articles_content:
        c_lower = (content or "").lower()
        for bp in boilerplate_patterns:
            if bp.lower() in c_lower:
                boilerplate_counts[bp] += 1
    report["boilerplate_occurrences"] = dict(boilerplate_counts)

    # Short content check (< 150 chars)
    short_articles = [
        {"url": url, "title": title, "len": len((content or "").strip())}
        for url, title, content in articles_content
        if len((content or "").strip()) < 150
    ]
    report["short_articles_count"] = len(short_articles)
    report["short_articles_sample"] = short_articles[:15]

# 3. Chunks / Embeddings
chunk_table = "chunks" if "chunks" in existing_tables else None
report["chunk_table_name"] = chunk_table
if chunk_table:
    c.execute(f"PRAGMA table_info({chunk_table})")
    chunk_cols = [r[1] for r in c.fetchall()]
    report["chunk_columns"] = chunk_cols
    c.execute(f"SELECT COUNT(*) FROM {chunk_table}")
    report["total_chunks"] = c.fetchone()[0]
    
    # Check embedding_json
    emb_col = "embedding_json" if "embedding_json" in chunk_cols else ("embedding" if "embedding" in chunk_cols else None)
    if emb_col:
        c.execute(f"SELECT COUNT(*) FROM {chunk_table} WHERE {emb_col} IS NOT NULL AND {emb_col} != '[]' AND length({emb_col}) > 2")
        report["chunks_with_embedding"] = c.fetchone()[0]
        c.execute(f"SELECT COUNT(*) FROM {chunk_table} WHERE {emb_col} IS NULL OR {emb_col} = '[]' OR length({emb_col}) <= 2")
        report["chunks_without_embedding"] = c.fetchone()[0]
else:
    report["total_chunks"] = 0
    report["chunks_with_embedding"] = 0
    report["chunks_without_embedding"] = 0

# 4. Sitemaps
if "sitemaps" in existing_tables:
    c.execute("PRAGMA table_info(sitemaps)")
    report["sitemap_columns"] = [r[1] for r in c.fetchall()]
    c.execute("SELECT * FROM sitemaps")
    report["sitemaps"] = c.fetchall()

# 8. Sitemap refresh runs
if "sitemap_refresh_runs" in existing_tables:
    c.execute("PRAGMA table_info(sitemap_refresh_runs)")
    report["refresh_run_columns"] = [r[1] for r in c.fetchall()]
    c.execute("SELECT * FROM sitemap_refresh_runs")
    report["refresh_runs"] = c.fetchall()

# 9. Checkpoints
chk_table = "crawler_checkpoint" if "crawler_checkpoint" in existing_tables else ("crawler_checkpoints" if "crawler_checkpoints" in existing_tables else None)
if chk_table:
    c.execute(f"PRAGMA table_info({chk_table})")
    chk_cols = [r[1] for r in c.fetchall()]
    report["checkpoint_columns"] = chk_cols
    c.execute(f"SELECT COUNT(*) FROM {chk_table}")
    report["total_checkpoints"] = c.fetchone()[0]
    if "status_code" in chk_cols:
        c.execute(f"SELECT status_code, COUNT(*) FROM {chk_table} GROUP BY status_code")
        report["checkpoints_by_status"] = c.fetchall()
    elif "status" in chk_cols:
        c.execute(f"SELECT status, COUNT(*) FROM {chk_table} GROUP BY status")
        report["checkpoints_by_status"] = c.fetchall()

# 10. Images
if "images" in existing_tables:
    c.execute("PRAGMA table_info(images)")
    image_cols = [r[1] for r in c.fetchall()]
    report["image_columns"] = image_cols
    c.execute("SELECT COUNT(*) FROM images")
    report["total_images"] = c.fetchone()[0]
    if "is_verified" in image_cols:
        c.execute("SELECT is_verified, COUNT(*) FROM images GROUP BY is_verified")
        report["images_by_verification"] = c.fetchall()

conn.close()

os.makedirs("docs", exist_ok=True)
with open("docs/step2_audit_raw.json", "w") as f:
    json.dump(report, f, indent=2)

print("SAFE_AUDIT_COMPLETE")

import sqlite3

def audit():
    conn = sqlite3.connect("task-1-knowledge-brain/knowledge_brain.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    print("=== USERS ===")
    users = c.execute("SELECT id, email, created_at FROM users").fetchall()
    for u in users:
        print(dict(u))

    print("\n=== SITEMAPS ===")
    sitemaps = c.execute("SELECT id, root_url, canonical_root_url, user_id, status FROM sitemaps").fetchall()
    for s in sitemaps:
        print(dict(s))

    print("\n=== SYNTHETIC ARTICLES ===")
    synth_arts = c.execute("SELECT count(*) as count FROM articles WHERE url LIKE '%example.com%'").fetchone()
    print("Synthetic articles (example.com):", synth_arts["count"])

    real_arts = c.execute("SELECT count(*) as count FROM articles WHERE url NOT LIKE '%example.com%'").fetchone()
    print("Real production articles:", real_arts["count"])

    print("\n=== SYNTHETIC RUNS ===")
    synth_runs = c.execute("SELECT count(*) as count FROM sitemap_refresh_runs WHERE sitemap_id LIKE 'sm_lease_%' OR sitemap_id = 'sm_resume_test' OR sitemap_id = 'sm_1'").fetchone()
    print("Synthetic runs:", synth_runs["count"])

    print("\n=== SITEMAP REFRESH RUNS BREAKDOWN ===")
    runs = c.execute("SELECT id, sitemap_id, user_id, status, stage, started_at, total_discovered_urls, total_successfully_fetched_urls FROM sitemap_refresh_runs ORDER BY started_at DESC").fetchall()
    for r in runs:
        print(dict(r))

if __name__ == "__main__":
    audit()

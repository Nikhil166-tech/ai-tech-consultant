import sqlite3
import re
from collections import Counter

def audit_articles():
    conn = sqlite3.connect("task-1-knowledge-brain/knowledge_brain.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    articles = c.execute("SELECT url, title, body_text, content_hash, category, folder FROM articles WHERE url NOT LIKE '%example.com%'").fetchall()
    print(f"Total production articles: {len(articles)}")

    # 1. Repeated body hashes
    hashes = [a["content_hash"] for a in articles if a["content_hash"]]
    hash_counts = Counter(hashes)
    dup_hashes = {h: count for h, count in hash_counts.items() if count > 1}
    print(f"\nUnique body hashes: {len(hash_counts)}, Hashes repeated across articles: {len(dup_hashes)}")
    for h, cnt in list(dup_hashes.items())[:5]:
        sample_urls = [a["url"] for a in articles if a["content_hash"] == h][:3]
        print(f"  Hash {h[:12]}... repeated {cnt} times. Sample URLs: {sample_urls}")

    # 2. Check for boilerplate / short content
    short_articles = [a for a in articles if len(a["body_text"].strip()) < 150]
    print(f"\nArticles with body < 150 chars: {len(short_articles)}")
    for a in short_articles[:5]:
        print(f"  [{len(a['body_text'])} chars] {a['title']} -> {a['url']}")

    # 3. Check for known boilerplate widget
    boilerplate_fingerprint = "looking for more information? submit a ticket"
    boilerplate_only = []
    for a in articles:
        txt = a["body_text"].strip().lower()
        if boilerplate_fingerprint in txt and len(txt) < 600:
            boilerplate_only.append(a)
    print(f"\nArticles containing primarily boilerplate support widget: {len(boilerplate_only)}")
    for a in boilerplate_only[:5]:
        print(f"  [{len(a['body_text'])} chars] {a['title']} -> {a['url']}")

    # 4. Check for category / index / hub pages
    category_pages = [a for a in articles if "/support/solutions/" in a["url"] and not re.search(r"/articles/\d+", a["url"])]
    print(f"\nCategory / listing pages indexed as articles (not individual articles): {len(category_pages)}")
    for a in category_pages[:5]:
        print(f"  {a['title']} -> {a['url']}")

    # 5. Check for login / error pages
    login_pages = [a for a in articles if "login" in a["title"].lower() or "attention required" in a["title"].lower()]
    print(f"\nPotential login/bot challenge pages: {len(login_pages)}")
    for a in login_pages[:5]:
        print(f"  {a['title']} -> {a['url']}")

if __name__ == "__main__":
    audit_articles()

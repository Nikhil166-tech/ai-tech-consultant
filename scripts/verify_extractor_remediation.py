import sys
import os
import sqlite3

sys.path.insert(0, os.path.abspath("task-1-knowledge-brain"))

from app.extractor import extract_article_content, validate_content_quality

def test_remediation():
    conn = sqlite3.connect("task-1-knowledge-brain/knowledge_brain.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Sample problematic articles from DB:
    # 1. Login page
    login_art = c.execute("SELECT * FROM articles WHERE title = 'Customer Login' LIMIT 1").fetchone()
    # 2. Empty page
    empty_art = c.execute("SELECT * FROM articles WHERE content_hash = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855' LIMIT 1").fetchone()
    # 3. Category folder page with "What Do You Need Help With?"
    category_art = c.execute("SELECT * FROM articles WHERE title = 'What Do You Need Help With?' LIMIT 1").fetchone()

    print("=== REMEDIATION VALIDATION AUDIT ===")
    
    if login_art:
        print(f"\n1. Problematic Article: Login Page ({login_art['url']})")
        print(f"   Legacy Title in DB: '{login_art['title']}'")
        print(f"   Legacy Body Length: {len(login_art['body_text'])} chars")
        is_valid, reason = validate_content_quality(login_art['title'], login_art['body_text'], login_art['url'])
        print(f"   New Validator Verdict: {'VALID' if is_valid else 'REJECTED'}")
        print(f"   Rejection Reason: {reason}")

    if empty_art:
        print(f"\n2. Problematic Article: Empty Page ({empty_art['url']})")
        print(f"   Legacy Title in DB: '{empty_art['title']}'")
        print(f"   Legacy Content Hash: {empty_art['content_hash']}")
        is_valid, reason = validate_content_quality(empty_art['title'], empty_art['body_text'], empty_art['url'])
        print(f"   New Validator Verdict: {'VALID' if is_valid else 'REJECTED'}")
        print(f"   Rejection Reason: {reason}")

    if category_art:
        print(f"\n3. Problematic Article: Category / Search Placeholder Page ({category_art['url']})")
        print(f"   Legacy Title in DB: '{category_art['title']}'")
        print(f"   Legacy Body Length: {len(category_art['body_text'])} chars")
        is_valid, reason = validate_content_quality(category_art['title'], category_art['body_text'], category_art['url'])
        print(f"   New Validator Verdict: {'VALID' if is_valid else 'REJECTED'}")
        print(f"   Rejection Reason: {reason}")

if __name__ == "__main__":
    test_remediation()

import sys
import os

sys.path.insert(0, os.path.abspath("task-1-knowledge-brain"))

from app.database import Database, CURRENT_SCHEMA_VERSION

def test_db_init():
    db = Database("task-1-knowledge-brain/knowledge_brain.db")
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version")
        ver = cursor.fetchone()[0]
        assert ver == 5, f"Expected user_version 5, got {ver}"

        # Check new columns on articles
        cursor.execute("PRAGMA table_info(articles)")
        art_cols = [c[1] for c in cursor.fetchall()]
        for col in ["user_id", "sitemap_id", "raw_content_hash", "normalized_content_hash", "extraction_version", "embedding_model", "embedding_version", "is_quarantined"]:
            assert col in art_cols, f"Missing column {col} in articles"

        # Check sitemaps
        cursor.execute("PRAGMA table_info(sitemaps)")
        sm_cols = [c[1] for c in cursor.fetchall()]
        assert "canonical_root_url" in sm_cols, "Missing canonical_root_url in sitemaps"

        # Check sitemap_refresh_runs
        cursor.execute("PRAGMA table_info(sitemap_refresh_runs)")
        run_cols = [c[1] for c in cursor.fetchall()]
        for col in ["lease_token", "lease_expires_at", "heartbeat_at", "stage", "resumed_from_run_id", "last_processed_url", "error_details"]:
            assert col in run_cols, f"Missing column {col} in sitemap_refresh_runs"

        # Verify duplicate detection and dry-run reconciliation
        dups = db.get_duplicate_sitemaps()
        print(f"Identified duplicate sitemap registrations: {len(dups)} clusters")
        reconcile_plan = db.get_dry_run_reconciliation_plan()
        print(f"Dry-run reconciliation clusters: {reconcile_plan['total_duplicate_clusters']}")

    print("DATABASE MIGRATION V5 & INTEGRITY TEST: SUCCESS!")

if __name__ == "__main__":
    test_db_init()

import sqlite3
import os
import sys

SOURCE_DB = "task-1-knowledge-brain/knowledge_brain.db"
BACKUP_DIR = "backups"
BACKUP_DB = os.path.join(BACKUP_DIR, "knowledge_brain_step2_pre_migration.db")

os.makedirs(BACKUP_DIR, exist_ok=True)

print(f"Opening source database: {SOURCE_DB}")
src_conn = sqlite3.connect(SOURCE_DB)
src_cursor = src_conn.cursor()

# 1. Source integrity check
src_cursor.execute("PRAGMA integrity_check")
src_integrity = src_cursor.fetchone()[0]
print(f"Source DB integrity check: {src_integrity}")
if src_integrity != "ok":
    print("ERROR: Source DB integrity check failed!")
    sys.exit(1)

# Pre-migration row counts
src_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in src_cursor.fetchall() if not r[0].startswith("sqlite")]
pre_counts = {}
for t in tables:
    cnt = src_cursor.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    pre_counts[t] = cnt
    print(f"Pre-migration table {t}: {cnt} rows")

# 2. Perform online SQLite backup using sqlite3.Connection.backup()
print(f"Starting online backup to: {BACKUP_DB}")
dst_conn = sqlite3.connect(BACKUP_DB)
with dst_conn:
    src_conn.backup(dst_conn, pages=100)
dst_conn.close()
src_conn.close()
print("Online backup completed successfully.")

# 3. Verify backup database integrity
backup_conn = sqlite3.connect(BACKUP_DB)
backup_cursor = backup_conn.cursor()
backup_cursor.execute("PRAGMA integrity_check")
backup_integrity = backup_cursor.fetchone()[0]
print(f"Backup DB integrity check: {backup_integrity}")
if backup_integrity != "ok":
    print("ERROR: Backup DB integrity check failed!")
    sys.exit(1)

# Compare table row counts
for t in tables:
    cnt = backup_cursor.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    if cnt != pre_counts[t]:
        print(f"ERROR: Count mismatch on {t}: source {pre_counts[t]} vs backup {cnt}")
        sys.exit(1)
backup_conn.close()

print("ALL_BACKUP_CHECKS_VERIFIED")

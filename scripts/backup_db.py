import os
import sqlite3
import datetime
import shutil

def perform_backup(src_db_path="task-1-knowledge-brain/knowledge_brain.db", backup_dir="backups"):
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"knowledge_brain_backup_{timestamp}.db")
    latest_file = os.path.join(backup_dir, "knowledge_brain_backup_latest.db")

    print(f"Starting SQLite backup from {src_db_path} to {backup_file}...")
    
    # 1. Source DB integrity check
    src_conn = sqlite3.connect(src_db_path)
    src_cursor = src_conn.cursor()
    src_cursor.execute("PRAGMA integrity_check")
    src_integrity = src_cursor.fetchone()[0]
    if src_integrity != "ok":
        raise RuntimeError(f"Source DB integrity check failed: {src_integrity}")
    print(f"[OK] Source DB integrity check passed: {src_integrity}")

    # Check WAL mode
    src_cursor.execute("PRAGMA journal_mode")
    j_mode = src_cursor.fetchone()[0]
    print(f"Source DB journal mode: {j_mode}")

    # Force WAL checkpoint to ensure all data is in main database
    src_cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    print("WAL checkpoint performed.")

    # 2. Consistent SQLite online backup
    dest_conn = sqlite3.connect(backup_file)
    src_conn.backup(dest_conn)
    dest_conn.close()
    src_conn.close()

    # 3. Destination DB integrity check
    dest_conn = sqlite3.connect(backup_file)
    dest_cursor = dest_conn.cursor()
    dest_cursor.execute("PRAGMA integrity_check")
    dest_integrity = dest_cursor.fetchone()[0]
    if dest_integrity != "ok":
        raise RuntimeError(f"Backup DB integrity check failed: {dest_integrity}")
    print(f"[OK] Backup DB integrity check passed: {dest_integrity}")

    # Count rows across all tables in backup
    dest_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in dest_cursor.fetchall() if not r[0].startswith("sqlite")]
    total_rows = {}
    for t in tables:
        c = dest_cursor.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        total_rows[t] = c
    dest_conn.close()

    # Copy to latest
    shutil.copy2(backup_file, latest_file)
    print(f"[OK] Successfully backed up to {backup_file} and {latest_file}")
    print(f"Backup Table Counts: {total_rows}")
    return backup_file, total_rows

if __name__ == "__main__":
    perform_backup()

"""
One-shot bootstrap script for Task 1 Knowledge Brain.
Ensures an initial bounded corpus (25 articles) is ingested if the persistent database is empty.
"""
import os
import sys
import time
import json
import urllib.request
import urllib.error

TASK1_API_URL = os.getenv("TASK1_API_URL", "http://task1:8000").strip().rstrip("/")
MAX_WAIT_SECONDS = int(os.getenv("BOOTSTRAP_MAX_WAIT_SECONDS", "120"))
POLL_INTERVAL_SECONDS = 3


def wait_for_healthy_task1() -> dict:
    """Polls Task 1 /health until healthy or timeout."""
    start_time = time.time()
    url = f"{TASK1_API_URL}/health"
    print(f"[Bootstrap] Checking Task 1 health at {url}...")

    while time.time() - start_time < MAX_WAIT_SECONDS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Task1-Bootstrap/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    print(f"[Bootstrap] Task 1 is healthy (status: {data.get('status')}).")
                    return data
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            elapsed = int(time.time() - start_time)
            print(f"[Bootstrap] Waiting for Task 1 ({elapsed}s/{MAX_WAIT_SECONDS}s)... ({e})")
            time.sleep(POLL_INTERVAL_SECONDS)

    print(f"[Bootstrap] FATAL: Task 1 did not become healthy within {MAX_WAIT_SECONDS}s", file=sys.stderr)
    sys.exit(1)


def trigger_sync() -> None:
    """Triggers bounded crawl sync on Task 1."""
    sync_url = f"{TASK1_API_URL}/api/v1/sync?max_pages=25"
    print(f"[Bootstrap] Ingesting initial knowledge corpus via POST {sync_url}...")
    try:
        req = urllib.request.Request(sync_url, data=b"", headers={"User-Agent": "Task1-Bootstrap/1.0"}, method="POST")
        with urllib.request.urlopen(req, timeout=300) as resp:
            if resp.status == 200:
                report = json.loads(resp.read().decode("utf-8"))
                print(f"[Bootstrap] Ingestion completed successfully: {report.get('pages_crawled', 0)} pages crawled, {report.get('chunks_created', 0)} chunks created.")
            else:
                print(f"[Bootstrap] Ingestion returned unexpected HTTP status {resp.status}", file=sys.stderr)
                sys.exit(1)
    except Exception as e:
        print(f"[Bootstrap] FATAL: Ingestion failed: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    print("[Bootstrap] Initializing Knowledge Brain Bootstrap...")
    health_data = wait_for_healthy_task1()
    active_count = health_data.get("active_articles_count", 0)

    if active_count > 0:
        print(f"[Bootstrap] Persistent database already initialized with {active_count} active articles. Skipping sync.")
        sys.exit(0)

    print("[Bootstrap] Database is empty (0 active articles). Triggering bootstrap ingestion...")
    trigger_sync()

    # Verify that articles are now present
    verified_health = wait_for_healthy_task1()
    final_count = verified_health.get("active_articles_count", 0)
    chunks_count = verified_health.get("chunks_count", 0)
    if final_count > 0:
        print(f"[Bootstrap] Bootstrap verified: {final_count} articles and {chunks_count} chunks active in database.")
        sys.exit(0)
    else:
        print("[Bootstrap] FATAL: Post-bootstrap verification failed. Database still has 0 articles.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

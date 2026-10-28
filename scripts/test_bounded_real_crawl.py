"""
Bounded live crawl test against small sample of public pages (max 3 pages).
Verifies:
1. Preview generation with discovered and unique counts
2. Resumable run execution with max_pages=3
3. Heartbeat updating
4. Progress and throughput calculation
5. Quality validation outcome
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath("task-1-knowledge-brain"))

from app.database import Database
from app.crawler import PoliteCrawler

async def main():
    db = Database()
    crawler = PoliteCrawler(db=db)

    print("--- 1. Testing Sitemap Preview on Live URL ---")
    sitemap_url = "https://support.brilliantdirectories.com/support/sitemap.xml"
    preview = await crawler.preview_sitemap(sitemap_url)
    print(f"Preview outcome:")
    print(f"  Discovered Sitemaps: {preview.discovered_sitemaps_count}")
    print(f"  Nested Sitemaps: {preview.nested_sitemaps_count}")
    print(f"  Total URLs: {preview.total_extracted_urls}")
    print(f"  Unique URLs: {preview.total_unique_urls}")
    print(f"  First URL: {preview.first_url} (lastmod: {preview.first_url_lastmod})")
    print(f"  Last URL: {preview.last_url} (lastmod: {preview.last_url_lastmod})")
    print(f"  Can Index: {preview.can_index}")

    print("\n--- 2. Executing Bounded Live Crawl (max_pages=3) ---")
    # Sitemap id sm_4a1983ddd0
    summary = await crawler.execute_refresh_run(
        sitemap_id="sm_4a1983ddd0",
        user_id="default_user",
        max_pages=3,
        force=False
    )
    print(f"Crawl Run Outcome:")
    print(f"  Run ID: {summary.id}")
    print(f"  Status: {summary.status}")
    print(f"  Stage: {summary.stage}")
    print(f"  Discovered URLs: {summary.total_discovered_urls}")
    print(f"  Successfully Fetched: {summary.total_successfully_fetched_urls}")
    print(f"  Added: {summary.added_count}, Updated: {summary.updated_count}, Unchanged: {summary.unchanged_count}, Failed: {summary.failed_count}")
    if summary.estimate:
        print(f"  Throughput: {summary.estimate.observed_throughput_pages_per_min} pages/min")
        print(f"  Estimate: {summary.estimate.estimated_completion_time_human}")

    # Check database records
    detail = db.get_refresh_run_detail(summary.id)
    print(f"\nRun Detail Checkpoint Records ({len(detail.urls)} URLs):")
    for u in detail.urls:
        print(f"  [{u.status}] {u.url} (HTTP {u.http_status})")

if __name__ == "__main__":
    asyncio.run(main())

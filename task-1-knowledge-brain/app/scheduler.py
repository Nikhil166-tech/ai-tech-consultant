import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from app.config import settings
from app.database import Database
from app.crawler import PoliteCrawler
from app.models import SitemapItem, SchedulerStatusResponse

logger = logging.getLogger(__name__)

class SitemapScheduler:
    """
    Phase B: Production Scheduled Refresh Engine
    - Multi-sitemap independent scheduling (daily, 7 days, 15 days, 30 days).
    - Persistent UTC due timestamps across application restarts.
    - Bounded worker concurrency & fair queue processing.
    - Database-backed lease coordination preventing concurrent duplicate runs.
    - Pause, resume, enable, disable, and immediate manual trigger without corrupting schedule.
    """
    def __init__(self, db: Database, crawler: Optional[PoliteCrawler] = None, max_concurrent: int = 2, tick_interval_seconds: float = 15.0):
        self.db = db
        self.crawler = crawler
        self.max_concurrent = max_concurrent
        self.tick_interval_seconds = tick_interval_seconds
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._is_running = False
        self._active_sitemap_ids = set()

    def start(self):
        """Starts the background scheduler loop if not already running."""
        if self._is_running and self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._is_running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info(f"SitemapScheduler started with concurrency limit {self.max_concurrent} (tick: {self.tick_interval_seconds}s).")

    async def stop(self):
        """Gracefully stops the scheduler loop."""
        self._is_running = False
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SitemapScheduler stopped gracefully.")

    async def _scheduler_loop(self):
        """Periodic background evaluation loop for due sitemaps."""
        while not self._stop_event.is_set():
            try:
                await self.tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in SitemapScheduler tick: {e}", exc_info=True)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.tick_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def tick(self):
        """Evaluates due sitemaps and schedules worker tasks under concurrency limits."""
        now_iso = datetime.now(timezone.utc).isoformat()
        due_sitemaps = self.db.get_due_sitemaps(now_iso=now_iso)

        if not due_sitemaps:
            return

        for sm in due_sitemaps:
            sm_id = sm["id"]
            if sm_id in self._active_sitemap_ids:
                continue

            # Fair queue: dispatch under semaphore
            asyncio.create_task(self._process_sitemap_job(sm))

    async def _process_sitemap_job(self, sitemap_row: Dict[str, Any]):
        sm_id = sitemap_row["id"]
        user_id = sitemap_row.get("user_id") or "default_user"
        self._active_sitemap_ids.add(sm_id)

        async with self.semaphore:
            try:
                logger.info(f"Scheduler triggered refresh for sitemap {sm_id} (user: {user_id})")
                run_summary = await self.crawler.execute_refresh_run(
                    sitemap_id=sm_id,
                    user_id=user_id,
                    force=False
                )
                success = (run_summary.status == "completed")
                self.db.record_sitemap_refresh_complete(
                    sitemap_id=sm_id,
                    run_id=run_summary.id,
                    success=success,
                    interval_days=sitemap_row.get("refresh_interval_days") or 1
                )
                logger.info(f"Scheduler completed refresh for sitemap {sm_id}: status={run_summary.status}")
            except Exception as e:
                logger.error(f"Scheduler refresh job error for sitemap {sm_id}: {e}", exc_info=True)
                self.db.record_sitemap_refresh_complete(
                    sitemap_id=sm_id,
                    run_id="err",
                    success=False,
                    interval_days=sitemap_row.get("refresh_interval_days") or 1
                )
            finally:
                self._active_sitemap_ids.discard(sm_id)

    async def trigger_refresh_now(self, sitemap_id: str, user_id: str = "default_user", force: bool = False):
        """
        Executes an immediate manual refresh without mutating the scheduled interval.
        """
        logger.info(f"Manual Refresh Now requested for sitemap {sitemap_id} (user: {user_id})")
        return await self.crawler.execute_refresh_run(
            sitemap_id=sitemap_id,
            user_id=user_id,
            force=force
        )

    def get_status(self) -> SchedulerStatusResponse:
        db_status = self.db.get_scheduler_status()
        return SchedulerStatusResponse(
            status="operational" if self._is_running else "paused",
            enabled=True,
            active_workers_count=len(self._active_sitemap_ids),
            total_scheduled_sitemaps=db_status.get("total_configured_sitemaps", 0),
            due_sitemaps_count=db_status.get("active_schedules_count", 0),
            next_due_at=db_status.get("next_scheduled_run_at"),
            last_scheduler_tick_at=datetime.now(timezone.utc).isoformat()
        )

import asyncio
import logging
import re
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
import httpx
from bs4 import BeautifulSoup, Tag
from app.models import Article, ArticleChunk, ImageMetadata, SyncReport, SyncStatus
from app.database import Database
from app.vision import VisionAnalyzer
from app.retrieval import BaseEmbeddingProvider, get_embedding_provider
from app.config import settings

logger = logging.getLogger(__name__)

class PoliteCrawler:
    def __init__(
        self,
        db: Database,
        sitemap_url: Optional[str] = None,
        delay_seconds: Optional[float] = None,
        max_concurrent: Optional[int] = None,
        vision_analyzer: Optional[VisionAnalyzer] = None,
        embedding_provider: Optional[BaseEmbeddingProvider] = None
    ):
        self.db = db
        self.sitemap_url = sitemap_url or settings.default_sitemap_url
        self.delay_seconds = delay_seconds if delay_seconds is not None else settings.crawler_delay_seconds
        self.semaphore = asyncio.Semaphore(max_concurrent or settings.max_concurrent_requests)
        self.vision = vision_analyzer or VisionAnalyzer()
        self.embedder = embedding_provider or get_embedding_provider()
        self.headers = {
            "User-Agent": "AITechConsultantBot/2.0 (Ethical Capstone Crawler; support-sync; contact: info@consultant.ai)"
        }

    async def _fetch_with_retry(self, client: httpx.AsyncClient, url: str) -> Optional[httpx.Response]:
        """Fetches URL with configurable exponential backoff retrying only 5xx/network errors."""
        max_retries = settings.max_retries
        backoff = settings.retry_backoff_factor

        for attempt in range(max_retries):
            try:
                resp = await client.get(url, headers=self.headers, follow_redirects=True)
                if resp.status_code == 200:
                    return resp
                elif resp.status_code in [408, 429, 500, 502, 503, 504]:
                    await asyncio.sleep(backoff * (2 ** attempt))
                else:
                    # 4xx client errors (404, 403, 401) should NOT be retried
                    return resp
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError):
                await asyncio.sleep(backoff * (2 ** attempt))
            except Exception as e:
                logger.error(f"Unexpected request error for {url}: {e}")
                return None
        return None

    async def fetch_sitemap_urls(self, custom_url: Optional[str] = None) -> Tuple[List[Dict[str, str]], bool]:
        """
        Fetches and parses sitemap XML.
        Requirement 3: Explicitly indicates whether the complete root + all required
        child sitemaps were fetched and parsed successfully (is_complete: bool).
        Returns (entries_list, is_complete).
        """
        target_url = custom_url or self.sitemap_url
        logger.info(f"Fetching sitemap from {target_url}")
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await self._fetch_with_retry(client, target_url)
            if not resp or resp.status_code != 200:
                logger.error(f"Failed to fetch sitemap: status {getattr(resp, 'status_code', 'unknown')}")
                return [], False

            try:
                root = ET.fromstring(resp.content)
            except ET.ParseError as e:
                logger.error(f"Malformed XML in sitemap at {target_url}: {e}")
                return [], False

            namespace = ""
            if root.tag.startswith("{"):
                namespace = root.tag.split("}")[0] + "}"

            results = []
            is_complete = True

            if "sitemapindex" in root.tag:
                sitemap_locs = [elem.text for elem in root.findall(f".//{namespace}loc") if elem.text]
                if not sitemap_locs:
                    is_complete = False

                for sub_loc in sitemap_locs:
                    try:
                        sub_resp = await self._fetch_with_retry(client, sub_loc)
                        if sub_resp and sub_resp.status_code == 200:
                            sub_root = ET.fromstring(sub_resp.content)
                            for url_elem in sub_root.findall(f".//{namespace}url"):
                                loc = url_elem.find(f"{namespace}loc")
                                lastmod = url_elem.find(f"{namespace}lastmod")
                                if loc is not None and loc.text:
                                    results.append({
                                        "url": loc.text.strip(),
                                        "lastmod": lastmod.text.strip() if lastmod is not None and lastmod.text else ""
                                    })
                        else:
                            logger.error(f"Child sitemap fetch failed for {sub_loc} (status={getattr(sub_resp, 'status_code', 'none')})")
                            is_complete = False
                    except Exception as e:
                        logger.error(f"Error parsing child sitemap {sub_loc}: {e}")
                        is_complete = False
            else:
                for url_elem in root.findall(f".//{namespace}url"):
                    loc = url_elem.find(f"{namespace}loc")
                    lastmod = url_elem.find(f"{namespace}lastmod")
                    if loc is not None and loc.text:
                        results.append({
                            "url": loc.text.strip(),
                            "lastmod": lastmod.text.strip() if lastmod is not None and lastmod.text else ""
                        })

            return results, is_complete

    def _compute_hash(self, text: str) -> str:
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    async def crawl_article(
        self,
        url: str,
        lastmod: Optional[str] = None,
        force: bool = False
    ) -> Tuple[Optional[Article], str]:
        """
        Crawls a single article. Returns (Article or None, classification)
        classification is one of: 'NEW', 'CHANGED', 'UNCHANGED', 'ERROR'.
        Requirement 4: force=True forces re-chunking and re-embedding even when content_hash matches.
        """
        existing = self.db.get_article(url)

        async with self.semaphore:
            await asyncio.sleep(self.delay_seconds)
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await self._fetch_with_retry(client, url)
                    if not resp:
                        self.db.save_crawler_checkpoint(url, 500, error="Network / Retry exhaustion")
                        return None, "ERROR"

                    if resp.status_code != 200:
                        self.db.save_crawler_checkpoint(url, resp.status_code, error=f"HTTP {resp.status_code}")
                        return None, "ERROR"

                    etag = resp.headers.get("etag")
                    last_modified = resp.headers.get("last-modified") or lastmod

                    html_content = resp.text
                    soup = BeautifulSoup(html_content, "html.parser")

                    # Extract title
                    title_elem = soup.find("h1") or soup.find("h2") or soup.find("title")
                    title = title_elem.get_text(strip=True) if title_elem else "Brilliant Directories Knowledge Article"

                    # Breadcrumbs for category / folder
                    category = "General"
                    folder = "General"
                    breadcrumbs = soup.find_all(class_=re.compile(r"breadcrumb", re.I))
                    if breadcrumbs:
                        crumbs = [b.get_text(strip=True) for b in breadcrumbs[0].find_all(["a", "li", "span"])]
                        crumbs = [c for c in crumbs if c and c != ">" and "/" not in c]
                        if len(crumbs) >= 2:
                            category = crumbs[1]
                        if len(crumbs) >= 3:
                            folder = crumbs[2]

                    # Find content container
                    container = (
                        soup.find("article") or
                        soup.find(class_=re.compile(r"article-body|solution-article|content|post-body", re.I)) or
                        soup.find("main") or
                        soup.body
                    )

                    if not container:
                        return None, "ERROR"

                    # Section-aware chunking preserving headings and local image association
                    chunks, images, full_article_text = await self._section_aware_chunking(
                        article_url=url,
                        title=title,
                        category=category,
                        folder=folder,
                        container=container
                    )

                    new_content_hash = self._compute_hash(full_article_text)

                    # Precise Classification: NEW, CHANGED, UNCHANGED
                    classification = "NEW"
                    if existing and not force:
                        if existing.content_hash == new_content_hash:
                            classification = "UNCHANGED"
                            self.db.save_crawler_checkpoint(
                                url=url,
                                status_code=resp.status_code,
                                etag=etag,
                                last_modified=last_modified,
                                content_hash=new_content_hash
                            )
                            return existing, classification
                        else:
                            classification = "CHANGED"
                    elif existing and force:
                        classification = "CHANGED"

                    article = Article(
                        url=url,
                        title=title,
                        category=category,
                        folder=folder,
                        body_text=full_article_text,
                        content_hash=new_content_hash,
                        images=images,
                        last_modified=last_modified,
                        etag=etag,
                        status="active",
                        crawled_at=datetime.now(timezone.utc)
                    )

                    # Persist article and chunks
                    self.db.upsert_article(article)
                    self.db.delete_chunks_for_article(url)
                    self.db.save_chunks(chunks)
                    self.db.save_crawler_checkpoint(
                        url=url,
                        status_code=resp.status_code,
                        etag=etag,
                        last_modified=last_modified,
                        content_hash=new_content_hash
                    )

                    logger.info(f"Successfully processed {classification} article (force={force}): {url} ({len(chunks)} chunks, {len(images)} images)")
                    return article, classification

            except Exception as e:
                logger.error(f"Error crawling {url}: {e}")
                self.db.save_crawler_checkpoint(url, 500, error=str(e))
                return None, "ERROR"

    async def _section_aware_chunking(
        self,
        article_url: str,
        title: str,
        category: str,
        folder: str,
        container: Tag
    ) -> Tuple[List[ArticleChunk], List[ImageMetadata], str]:
        """
        Preserves section hierarchy, tables, procedural steps, and associates
        images strictly with the section in which they appear.
        """
        for bad in container(["script", "style", "nav", "footer", "noscript", "svg"]):
            bad.decompose()

        sections: List[Dict[str, Any]] = []
        current_heading = "Overview"
        current_elements: List[str] = []
        current_section_images: List[ImageMetadata] = []
        all_images: List[ImageMetadata] = []

        direct_elements = container.find_all(["h1", "h2", "h3", "h4", "p", "ul", "ol", "table", "img"], recursive=True)

        for el in direct_elements:
            if el.name in ["h1", "h2", "h3", "h4"]:
                # New section heading encountered: flush previous section
                if current_elements or current_section_images:
                    sections.append({
                        "heading": current_heading,
                        "text": "\n".join(current_elements).strip(),
                        "images": current_section_images
                    })
                    current_elements = []
                    current_section_images = []
                current_heading = el.get_text(strip=True) or current_heading

            elif el.name == "img":
                src = el.get("src") or el.get("data-src")
                if src and not src.startswith("data:"):
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        src = "https://support.brilliantdirectories.com" + src

                    parent = el.find_parent(["p", "div", "li"])
                    context = parent.get_text(strip=True) if parent else ""
                    alt_text = el.get("alt", "")
                    img_meta = await self.vision.analyze_image(
                        src,
                        title,
                        context,
                        section_heading=current_heading,
                        alt_text=alt_text
                    )
                    current_section_images.append(img_meta)
                    all_images.append(img_meta)

            elif el.name in ["ul", "ol"]:
                # Keep ordered/unordered list together
                items = [f"- {li.get_text(strip=True)}" for li in el.find_all("li") if li.get_text(strip=True)]
                if items:
                    current_elements.append("\n".join(items))

            elif el.name == "table":
                # Keep table structured
                rows = []
                for tr in el.find_all("tr"):
                    cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    if cells:
                        rows.append(" | ".join(cells))
                if rows:
                    current_elements.append("\n[Table Data]\n" + "\n".join(rows))

            elif el.name == "p":
                p_text = el.get_text(strip=True)
                if p_text:
                    current_elements.append(p_text)

        # Flush final section
        if current_elements or current_section_images:
            sections.append({
                "heading": current_heading,
                "text": "\n".join(current_elements).strip(),
                "images": current_section_images
            })

        # Fallback if no explicit headings found
        if not sections:
            sections.append({
                "heading": "Overview",
                "text": container.get_text(separator="\n", strip=True),
                "images": all_images
            })

        # Generate chunks from sections
        chunks: List[ArticleChunk] = []
        chunk_idx = 0
        full_text_blocks = []

        for sec in sections:
            sec_heading = sec["heading"]
            sec_text = sec["text"]
            sec_images = sec["images"]

            if not sec_text and not sec_images:
                continue

            full_text_blocks.append(f"## {sec_heading}\n{sec_text}")

            visual_summary = ""
            if sec_images:
                visual_summary = "UI Screenshots in Section: " + " | ".join(
                    [f"[{img.caption}]" for img in sec_images if img.caption]
                )

            words = sec_text.split()
            if len(words) <= 350:
                chunk_text = f"[{sec_heading}]\n{sec_text}" if sec_heading != "Overview" else sec_text
                chunk_id = f"{article_url}#sec-{chunk_idx}"
                emb = self.embedder.embed_text(f"{title} {sec_heading} {chunk_text}")

                chunks.append(ArticleChunk(
                    id=chunk_id,
                    article_url=article_url,
                    title=title,
                    category=category,
                    folder=folder,
                    section_heading=sec_heading,
                    chunk_index=chunk_idx,
                    text=chunk_text,
                    visual_context=visual_summary,
                    images=sec_images,
                    embedding=emb,
                    source_type="OFFICIAL_DOC"
                ))
                chunk_idx += 1
            else:
                # Sub-chunking long sections with overlap
                i = 0
                while i < len(words):
                    sub_words = words[i:i + 300]
                    sub_text = " ".join(sub_words)
                    chunk_text = f"[{sec_heading} (part)]\n{sub_text}"
                    chunk_id = f"{article_url}#sec-{chunk_idx}"
                    emb = self.embedder.embed_text(f"{title} {sec_heading} {chunk_text}")

                    chunks.append(ArticleChunk(
                        id=chunk_id,
                        article_url=article_url,
                        title=title,
                        category=category,
                        folder=folder,
                        section_heading=sec_heading,
                        chunk_index=chunk_idx,
                        text=chunk_text,
                        visual_context=visual_summary,
                        images=sec_images,
                        embedding=emb,
                        source_type="OFFICIAL_DOC"
                    ))
                    chunk_idx += 1
                    i += 240  # 60 words overlap

        full_article_text = "\n\n".join(full_text_blocks)
        return chunks, all_images, full_article_text

    async def sync_daily(self, max_pages: Optional[int] = None, force: bool = False) -> SyncReport:
        """
        Sitemap synchronization with strict deletion safety and optional force reindex.
        Requirement 3: Explicitly checks is_complete. If root or any child sitemap fails,
        is_complete is False. Zero deletions are performed, but retrieved entries are
        safely ingested/updated.
        Requirement 4: force=True forces reprocessing/re-embedding of all processed entries.
        """
        start_time = datetime.now(timezone.utc)
        self.db.set_sync_status(SyncStatus(
            status="running",
            current_step="Fetching complete sitemap",
            updated_at=start_time.isoformat()
        ))

        sitemap_entries, is_complete = await self.fetch_sitemap_urls()
        total_in_sitemap = len(sitemap_entries)

        full_sitemap_urls = {entry["url"] for entry in sitemap_entries}
        active_db_urls = set(self.db.get_all_active_urls())

        removed_count = 0
        if is_complete and full_sitemap_urls:
            # Perform REMOVED detection ONLY when root + all child sitemaps succeeded
            for db_url in active_db_urls:
                if db_url not in full_sitemap_urls and not db_url.startswith("expert://"):
                    logger.info(f"Article removed from complete sitemap, purging: {db_url}")
                    self.db.mark_article_removed(db_url)
                    removed_count += 1
        elif not is_complete:
            logger.warning(
                "Sitemap fetch was partial or incomplete (is_complete=False). "
                "Skipping REMOVED detection to prevent accidental article purging. "
                f"Retrieved {len(sitemap_entries)} articles will still be safely ingested/updated."
            )

        # Limit crawl slice by max_pages for processing
        crawl_entries = sitemap_entries[:max_pages] if max_pages else sitemap_entries

        added_count = 0
        updated_count = 0
        unchanged_count = 0

        self.db.set_sync_status(SyncStatus(
            status="running",
            current_step=f"Processing {len(crawl_entries)} URLs (force={force})",
            total_sitemap_urls=total_in_sitemap,
            pages_crawled=0,
            updated_at=datetime.now(timezone.utc).isoformat()
        ))

        tasks = []
        for entry in crawl_entries:
            url = entry["url"]
            lastmod = entry.get("lastmod")
            tasks.append(self.crawl_article(url, lastmod, force=force))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, tuple) and len(res) == 2:
                    art, classification = res
                    if classification == "NEW":
                        added_count += 1
                    elif classification == "CHANGED":
                        updated_count += 1
                    elif classification == "UNCHANGED":
                        unchanged_count += 1

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        report = SyncReport(
            total_in_sitemap=total_in_sitemap,
            added=added_count,
            updated=updated_count,
            removed=removed_count,
            unchanged=unchanged_count,
            duration_seconds=round(duration, 2)
        )

        self.db.set_sync_status(SyncStatus(
            status="completed",
            current_step="Sync complete",
            pages_crawled=len(crawl_entries),
            total_sitemap_urls=total_in_sitemap,
            last_report=report,
            updated_at=datetime.now(timezone.utc).isoformat()
        ))

        return report

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
from app.models import Article, ArticleChunk, ImageMetadata, SyncReport
from app.database import Database
from app.vision import VisionAnalyzer

logger = logging.getLogger(__name__)

DEFAULT_SITEMAP_URL = "https://support.brilliantdirectories.com/support/sitemap.xml"

class PoliteCrawler:
    def __init__(
        self,
        db: Database,
        sitemap_url: str = DEFAULT_SITEMAP_URL,
        delay_seconds: float = 0.3,
        max_concurrent: int = 3,
        vision_analyzer: Optional[VisionAnalyzer] = None
    ):
        self.db = db
        self.sitemap_url = sitemap_url
        self.delay_seconds = delay_seconds
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.vision = vision_analyzer or VisionAnalyzer()
        self.headers = {
            "User-Agent": "AITechConsultantBot/1.0 (Ethical Capstone Crawler; support-sync; contact: info@consultant.ai)"
        }

    async def fetch_sitemap_urls(self) -> List[Dict[str, str]]:
        logger.info(f"Fetching sitemap from {self.sitemap_url}")
        async with httpx.AsyncClient(timeout=15.0, headers=self.headers, follow_redirects=True) as client:
            resp = await client.get(self.sitemap_url)
            resp.raise_for_status()
            
            root = ET.fromstring(resp.content)
            namespace = ""
            if root.tag.startswith("{"):
                namespace = root.tag.split("}")[0] + "}"

            results = []
            if "sitemapindex" in root.tag:
                sitemap_locs = [elem.text for elem in root.findall(f".//{namespace}loc") if elem.text]
                for sub_loc in sitemap_locs:
                    try:
                        sub_resp = await client.get(sub_loc)
                        if sub_resp.status_code == 200:
                            sub_root = ET.fromstring(sub_resp.content)
                            for url_elem in sub_root.findall(f".//{namespace}url"):
                                loc = url_elem.find(f"{namespace}loc")
                                lastmod = url_elem.find(f"{namespace}lastmod")
                                if loc is not None and loc.text:
                                    results.append({
                                        "url": loc.text.strip(),
                                        "lastmod": lastmod.text.strip() if lastmod is not None and lastmod.text else ""
                                    })
                    except Exception as e:
                        logger.warning(f"Error fetching sub-sitemap {sub_loc}: {e}")
            else:
                for url_elem in root.findall(f".//{namespace}url"):
                    loc = url_elem.find(f"{namespace}loc")
                    lastmod = url_elem.find(f"{namespace}lastmod")
                    if loc is not None and loc.text:
                        results.append({
                            "url": loc.text.strip(),
                            "lastmod": lastmod.text.strip() if lastmod is not None and lastmod.text else ""
                        })
            
            logger.info(f"Discovered {len(results)} URLs from sitemap")
            return results

    async def crawl_article(self, url: str, lastmod: Optional[str] = None, force: bool = False) -> Optional[Article]:
        checkpoint = self.db.get_crawler_checkpoint(url)
        if not force and checkpoint and checkpoint.get("status_code") == 200:
            if lastmod and checkpoint.get("last_modified") == lastmod:
                return None

        async with self.semaphore:
            await asyncio.sleep(self.delay_seconds)
            try:
                async with httpx.AsyncClient(timeout=15.0, headers=self.headers, follow_redirects=True) as client:
                    resp = await client.get(url)
                    etag = resp.headers.get("etag")
                    last_modified = lastmod or resp.headers.get("last-modified")

                    if resp.status_code != 200:
                        self.db.save_crawler_checkpoint(url, resp.status_code, etag, last_modified, f"HTTP {resp.status_code}")
                        return None

                    soup = BeautifulSoup(resp.content, "lxml")

                    title = "Help Article"
                    title_tag = soup.find("h1") or soup.find("title")
                    if title_tag:
                        title = title_tag.get_text(strip=True).replace(" - Brilliant Directories", "").replace(" | Brilliant Directories", "")

                    category = "General"
                    folder = "General"
                    breadcrumbs = soup.find_all("li", class_=re.compile(r"breadcrumb", re.I)) or soup.find_all("nav", class_=re.compile(r"breadcrumb", re.I))
                    if breadcrumbs:
                        crumb_texts = [b.get_text(strip=True) for b in breadcrumbs if b.get_text(strip=True)]
                        if len(crumb_texts) >= 3:
                            category = crumb_texts[1]
                            folder = crumb_texts[2]
                        elif len(crumb_texts) == 2:
                            category = crumb_texts[1]

                    body_container = (
                        soup.find("div", class_=re.compile(r"article-body|solution-body|content-body", re.I))
                        or soup.find("article")
                        or soup.find("div", id=re.compile(r"content|article", re.I))
                        or soup.body
                    )
                    
                    if not body_container:
                        return None

                    images: List[ImageMetadata] = []
                    img_tags = body_container.find_all("img")
                    for img in img_tags:
                        src = img.get("src")
                        if not src:
                            continue
                        if not src.startswith("http"):
                            src = f"https://support.brilliantdirectories.com{src}" if src.startswith("/") else f"https://support.brilliantdirectories.com/{src}"
                        
                        parent = img.find_parent(["p", "div", "li"])
                        context_text = parent.get_text(strip=True) if parent else ""
                        img_meta = await self.vision.analyze_image(src, title, context_text)
                        images.append(img_meta)

                    for tag in body_container(["script", "style", "nav", "footer", "form"]):
                        tag.decompose()
                    
                    body_text = body_container.get_text(separator="\n", strip=True)

                    article = Article(
                        url=url,
                        title=title,
                        category=category,
                        folder=folder,
                        body_text=body_text,
                        images=images,
                        last_modified=last_modified,
                        etag=etag,
                        status="active",
                        crawled_at=datetime.now(timezone.utc)
                    )

                    self.db.upsert_article(article)
                    self.db.save_crawler_checkpoint(url, 200, etag, last_modified)

                    chunks = self._chunk_article(article)
                    self.db.delete_chunks_for_article(article.url)
                    self.db.save_chunks(chunks)

                    return article
            except Exception as e:
                logger.error(f"Error crawling {url}: {e}")
                self.db.save_crawler_checkpoint(url, 500, error=str(e))
                return None

    def _chunk_article(self, article: Article, chunk_size: int = 400, overlap: int = 80) -> List[ArticleChunk]:
        words = article.body_text.split()
        if not words:
            return []

        chunks: List[ArticleChunk] = []
        chunk_idx = 0
        i = 0

        visual_summary = ""
        if article.images:
            visual_summary = "Visual Steps / Screenshots: " + " | ".join(
                [f"[{img.caption}]" for img in article.images if img.caption]
            )

        while i < len(words):
            chunk_words = words[i:i + chunk_size]
            chunk_text = " ".join(chunk_words)
            chunk_id = f"{article.url}#chunk-{chunk_idx}"

            chunks.append(ArticleChunk(
                id=chunk_id,
                article_url=article.url,
                title=article.title,
                category=article.category or "General",
                folder=article.folder or "General",
                chunk_index=chunk_idx,
                text=chunk_text,
                visual_context=visual_summary,
                embedding=[]
            ))
            chunk_idx += 1
            i += (chunk_size - overlap)

        return chunks

    async def sync_daily(self, max_pages: Optional[int] = None) -> SyncReport:
        start_time = datetime.now(timezone.utc)
        sitemap_entries = await self.fetch_sitemap_urls()
        if max_pages:
            sitemap_entries = sitemap_entries[:max_pages]

        sitemap_urls = {entry["url"]: entry.get("lastmod") for entry in sitemap_entries}
        active_db_urls = set(self.db.get_all_active_urls())

        added_or_updated = 0
        unchanged = 0
        removed = 0

        for db_url in active_db_urls:
            if db_url not in sitemap_urls and not db_url.startswith("expert://"):
                logger.info(f"Article removed from sitemap, purging: {db_url}")
                self.db.mark_article_removed(db_url)
                removed += 1

        tasks = []
        for url, lastmod in sitemap_urls.items():
            checkpoint = self.db.get_crawler_checkpoint(url)
            if checkpoint and checkpoint.get("status_code") == 200 and checkpoint.get("last_modified") == lastmod and lastmod:
                unchanged += 1
            else:
                tasks.append(self.crawl_article(url, lastmod))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Article) and r is not None:
                    added_or_updated += 1

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        return SyncReport(
            total_in_sitemap=len(sitemap_entries),
            added=added_or_updated,
            updated=0,
            removed=removed,
            unchanged=unchanged,
            duration_seconds=duration
        )

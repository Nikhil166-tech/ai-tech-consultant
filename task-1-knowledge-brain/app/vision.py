import os
import httpx
import base64
import asyncio
import logging
from typing import Optional
from app.models import ImageMetadata
from app.config import settings

logger = logging.getLogger(__name__)

class VisionAnalyzer:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.anthropic_api_key
        self.model = model or settings.anthropic_model_vision
        self.client = None
        if self.api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Anthropic client for vision: {e}")

    async def _fetch_image_bytes(self, image_url: str) -> Optional[tuple[bytes, str]]:
        """Fetches image bytes with retry and exponential backoff for transient 5xx/network errors."""
        max_retries = settings.max_retries
        backoff = settings.retry_backoff_factor

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                    resp = await client.get(image_url)
                    if resp.status_code == 200:
                        content_type = resp.headers.get("content-type", "image/png").split(";")[0]
                        return resp.content, content_type
                    elif resp.status_code in [408, 429, 500, 502, 503, 504]:
                        await asyncio.sleep(backoff * (2 ** attempt))
                    else:
                        # 4xx client errors should not be retried
                        return None
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError):
                await asyncio.sleep(backoff * (2 ** attempt))
            except Exception:
                return None
        return None

    async def analyze_image(self, image_url: str, article_title: str, context_text: str = "", section_heading: str = "") -> ImageMetadata:
        alt_text = f"Screenshot related to {article_title}"
        caption = ""

        if self.client and image_url.startswith("http"):
            img_data = await self._fetch_image_bytes(image_url)
            if img_data:
                content, content_type = img_data
                if content_type in ["image/jpeg", "image/png", "image/gif", "image/webp"]:
                    try:
                        b64_data = base64.b64encode(content).decode("utf-8")
                        prompt = (
                            f"You are analyzing a screenshot from a technical help article titled '{article_title}'.\n"
                            f"Section: '{section_heading}'\n"
                            f"Surrounding text: {context_text[:300]}\n"
                            f"Provide a concise, 1-2 sentence description explaining what settings, buttons, or UI steps "
                            f"are shown in this screenshot."
                        )
                        response = self.client.messages.create(
                            model=self.model,
                            max_tokens=150,
                            messages=[{
                                "role": "user",
                                "content": [
                                    {"type": "image", "source": {"type": "base64", "media_type": content_type, "data": b64_data}},
                                    {"type": "text", "text": prompt}
                                ]
                            }]
                        )
                        caption = response.content[0].text.strip()
                    except Exception as e:
                        logger.info(f"Vision API fallback to heuristic: {e}")

        if not caption:
            caption = self._heuristic_caption(image_url, article_title, context_text, section_heading)

        return ImageMetadata(
            url=image_url,
            alt=alt_text,
            caption=caption,
            context_text=context_text[:200],
            section_heading=section_heading
        )

    def _heuristic_caption(self, image_url: str, article_title: str, context_text: str, section_heading: str) -> str:
        filename = image_url.split("/")[-1].split("?")[0].replace("-", " ").replace("_", " ")
        if "." in filename:
            filename = filename.rsplit(".", 1)[0]
        prefix = f"[{section_heading}] " if section_heading and section_heading != "Overview" else ""
        first_sentence = context_text.split(".")[0].strip() if context_text else ""
        if first_sentence and len(first_sentence) > 15:
            return f"{prefix}Screenshot illustrating {filename} for '{article_title}': {first_sentence}."
        return f"{prefix}UI screenshot showing configuration interface for {article_title} ({filename})."

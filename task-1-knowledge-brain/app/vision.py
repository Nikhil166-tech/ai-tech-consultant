import os
import httpx
import base64
import logging
from typing import Optional
from app.models import ImageMetadata

logger = logging.getLogger(__name__)

class VisionAnalyzer:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.client = None
        if self.api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Anthropic client for vision: {e}")

    async def analyze_image(self, image_url: str, article_title: str, context_text: str = "") -> ImageMetadata:
        alt_text = f"Screenshot related to {article_title}"
        caption = ""

        if self.client and image_url.startswith("http"):
            try:
                async with httpx.AsyncClient(timeout=10.0) as http_client:
                    resp = await http_client.get(image_url)
                    if resp.status_code == 200:
                        content_type = resp.headers.get("content-type", "image/png").split(";")[0]
                        if content_type in ["image/jpeg", "image/png", "image/gif", "image/webp"]:
                            b64_data = base64.b64encode(resp.content).decode("utf-8")
                            prompt = (
                                f"You are analyzing a screenshot from a technical help article titled '{article_title}'.\n"
                                f"Context from page: {context_text[:300]}\n"
                                f"Provide a precise 1-2 sentence description explaining what settings, buttons, or UI steps "
                                f"are shown in this screenshot."
                            )
                            response = self.client.messages.create(
                                model="claude-3-5-sonnet-20241022",
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
            caption = self._heuristic_caption(image_url, article_title, context_text)

        return ImageMetadata(
            url=image_url,
            alt=alt_text,
            caption=caption,
            context_text=context_text[:200]
        )

    def _heuristic_caption(self, image_url: str, article_title: str, context_text: str) -> str:
        filename = image_url.split("/")[-1].split("?")[0].replace("-", " ").replace("_", " ")
        if "." in filename:
            filename = filename.rsplit(".", 1)[0]
        first_sentence = context_text.split(".")[0].strip() if context_text else ""
        if first_sentence and len(first_sentence) > 15:
            return f"Screenshot illustrating {filename} for '{article_title}': {first_sentence}."
        return f"UI screenshot showing configuration interface for {article_title} ({filename})."

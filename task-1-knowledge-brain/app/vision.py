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
                headers = {"anthropic-workspace-id": settings.anthropic_workspace_id} if settings.anthropic_workspace_id else None
                self.client = anthropic.Anthropic(api_key=self.api_key, default_headers=headers)
            except Exception as e:
                logger.warning(f"Could not initialize Anthropic client for vision: {e}")

    async def _fetch_image_bytes(self, image_url: str) -> Optional[tuple[bytes, str]]:
        """Fetches image bytes with short timeout to prevent slow indexing on external documentation images."""
        try:
            async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
                resp = await client.get(image_url)
                if resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "image/png").split(";")[0]
                    return resp.content, content_type
                return None
        except Exception:
            return None

    async def analyze_image(
        self,
        image_url: str,
        article_title: str,
        context_text: str = "",
        section_heading: str = "",
        alt_text: str = ""
    ) -> ImageMetadata:
        """
        Analyzes an article screenshot.
        Requirement 5: If Claude Vision cannot inspect an image, do NOT assert what is visually
        shown based on filename. Preserve alt text and nearby DOM context, mark visual analysis
        as unverified/unavailable, and make this distinction available to retrieval and output.
        """
        preserved_alt = alt_text.strip() if alt_text and alt_text.strip() else f"Screenshot related to {article_title}"
        caption = ""
        visual_verified = False
        visual_status = "unavailable"

        gemini_key = os.getenv("GEMINI_API_KEY", "") or settings.gemini_api_key
        if gemini_key and not gemini_key.startswith("sk-ant-") and image_url.startswith("http"):
            img_data = await self._fetch_image_bytes(image_url)
            if img_data:
                content, content_type = img_data
                if content_type in ["image/jpeg", "image/png", "image/gif", "image/webp"]:
                    try:
                        b64_data = base64.b64encode(content).decode("utf-8")
                        gemini_model = os.getenv("GEMINI_MODEL_VISION", os.getenv("GEMINI_MODEL", settings.gemini_model_vision)) or "gemini-3.5-flash"
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={gemini_key}"
                        prompt = (
                            f"You are analyzing a screenshot from a technical help article titled '{article_title}'.\n"
                            f"Section: '{section_heading}'\n"
                            f"Surrounding text: {context_text[:300]}\n"
                            f"Provide a concise, 1-2 sentence description explaining what settings, buttons, or UI steps "
                            f"are shown in this screenshot."
                        )
                        payload = {
                            "contents": [{
                                "parts": [
                                    {"inlineData": {"mimeType": content_type, "data": b64_data}},
                                    {"text": prompt}
                                ]
                            }],
                            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 200}
                        }
                        async with httpx.AsyncClient(timeout=15.0) as http_client:
                            res = await http_client.post(url, json=payload)
                            if res.status_code == 200:
                                data = res.json()
                                candidates = data.get("candidates", [])
                                if candidates:
                                    parts = candidates[0].get("content", {}).get("parts", [])
                                    if parts:
                                        caption = parts[0].get("text", "").strip()
                                        visual_verified = True
                                        visual_status = "verified"
                    except Exception as e:
                        logger.info(f"Gemini Vision analysis failed: {e}")

        if not visual_verified and self.client and image_url.startswith("http"):
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
                        visual_verified = True
                        visual_status = "verified"
                    except Exception as e:
                        logger.info(f"Vision API analysis failed ({e}); falling back to preserved DOM context.")
                        err_str = str(e).lower()
                        if "credit balance is too low" in err_str or "not scoped to a workspace" in err_str or "400" in err_str or "401" in err_str or "403" in err_str:
                            logger.warning("Permanent Anthropic API authentication/credit error detected; disabling live vision client for remainder of crawl.")
                            self.client = None

        if not visual_verified:
            # Explicitly mark unverified/unavailable without asserting visual UI elements from filename
            clean_context = context_text.strip() if context_text else ""
            if clean_context:
                caption = f"[Visual analysis unverified] Preserved DOM context: {clean_context[:200]}"
                visual_status = "unverified"
            else:
                caption = "[Visual analysis unavailable - refer to source documentation]"
                visual_status = "unavailable"

        return ImageMetadata(
            url=image_url,
            alt=preserved_alt,
            caption=caption,
            context_text=context_text[:200],
            section_heading=section_heading,
            visual_verified=visual_verified,
            visual_status=visual_status
        )

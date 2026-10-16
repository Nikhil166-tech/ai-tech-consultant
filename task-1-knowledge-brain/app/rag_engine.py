import os
import re
import math
import logging
from typing import List, Dict, Any, Optional, Tuple
from app.models import (
    SearchRequest, SearchResult, AskRequest, AskResponse,
    Citation, ImageMetadata, ArticleChunk
)
from app.database import Database

logger = logging.getLogger(__name__)

class HybridRAGEngine:
    def __init__(self, db: Database, anthropic_api_key: Optional[str] = None):
        self.db = db
        self.api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self.client = None
        if self.api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Anthropic client: {e}")

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\b\w{2,}\b", text.lower())

    def search(self, query: str, top_k: int = 5, category: Optional[str] = None) -> List[SearchResult]:
        chunks = self.db.get_all_chunks()
        if not chunks:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores: List[Tuple[ArticleChunk, float]] = []
        doc_count = len(chunks)
        df: Dict[str, int] = {}
        for token in set(query_tokens):
            df[token] = sum(1 for c in chunks if token in c.text.lower() or token in c.title.lower())

        for chunk in chunks:
            if category and chunk.category.lower() != category.lower():
                continue

            chunk_text_lower = chunk.text.lower()
            title_lower = chunk.title.lower()
            visual_lower = (chunk.visual_context or "").lower()

            chunk_tokens = self._tokenize(chunk.text)
            len_doc = max(len(chunk_tokens), 1)

            score = 0.0
            for token in query_tokens:
                tf = chunk_tokens.count(token)
                if token in title_lower:
                    tf += 4
                if token in visual_lower:
                    tf += 2

                if tf > 0:
                    idf = math.log((doc_count - df.get(token, 0) + 0.5) / (df.get(token, 0) + 0.5) + 1.0)
                    score += idf * ((tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * (len_doc / 250.0))))

            if score > 0.1:
                scores.append((chunk, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        top_chunks = scores[:top_k]

        results = []
        for chunk, score in top_chunks:
            article = self.db.get_article(chunk.article_url)
            images = article.images if article else []
            snippet = chunk.text[:280] + "..." if len(chunk.text) > 280 else chunk.text
            results.append(SearchResult(
                article_url=chunk.article_url,
                title=chunk.title,
                category=chunk.category,
                folder=chunk.folder,
                snippet=snippet,
                score=round(score, 3),
                images=images[:2]
            ))

        return results

    async def ask(self, request: AskRequest, model: str = "claude-3-5-haiku-20241022") -> AskResponse:
        search_results = self.search(request.question, top_k=4, category=request.category_filter)
        max_score = search_results[0].score if search_results else 0.0
        confidence = min(max_score / 12.0, 1.0)

        # Honest refusal when unknown + auto-create expert task
        if not search_results or confidence < 0.25:
            task = self.db.create_expert_task(
                question=request.question,
                context=f"RAG search yielded zero high-confidence matches (max_score={max_score})."
            )
            return AskResponse(
                answer="I apologize, but I could not find verified instructions for this question in the Brilliant Directories Solution Center documentation. A support inquiry task has been routed to our product specialist team for verification.",
                citations=[],
                confidence_score=round(confidence, 2),
                is_known=False,
                needs_human_review=True,
                expert_task_id=task.id,
                visual_references=[]
            )

        citations: List[Citation] = []
        visual_refs: List[ImageMetadata] = []
        context_blocks = []

        for i, res in enumerate(search_results):
            citations.append(Citation(
                url=res.article_url,
                title=res.title,
                category=res.category,
                folder=res.folder,
                snippet=res.snippet
            ))
            context_blocks.append(
                f"[Source {i+1}: {res.title} ({res.category} > {res.folder}) - URL: {res.article_url}]\n{res.snippet}"
            )
            if res.images:
                for img in res.images:
                    if not any(v.url == img.url for v in visual_refs):
                        visual_refs.append(img)

        context_str = "\n\n".join(context_blocks)
        answer_text = ""

        if self.client:
            try:
                system_prompt = (
                    "You are the AI Tech Consultant for Brilliant Directories.\n"
                    "Your job is to answer customer questions strictly based on the provided help center documentation.\n"
                    "Rules:\n"
                    "1. Always cite sources with exact article titles and URLs.\n"
                    "2. If screenshots are provided, describe the UI steps clearly.\n"
                    "3. If the documentation does not fully answer, say so honestly.\n"
                    "4. Be concise, polite, and actionable."
                )
                user_prompt = f"Documentation Excerpts:\n{context_str}\n\nCustomer Question: {request.question}"
                response = self.client.messages.create(
                    model=model,
                    max_tokens=600,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}]
                )
                answer_text = response.content[0].text.strip()
            except Exception as e:
                logger.warning(f"Claude API synthesis failed: {e}")

        if not answer_text:
            primary = search_results[0]
            answer_text = (
                f"Based on the Brilliant Directories documentation for '{primary.title}' ({primary.category} > {primary.folder}):\n\n"
                f"{primary.snippet}\n\n"
                f"Refer to the complete article at {primary.article_url} for full configuration settings."
            )
            if visual_refs:
                answer_text += f"\n\nUI Step Guidance: Refer to '{visual_refs[0].caption}'."

        return AskResponse(
            answer=answer_text,
            citations=citations,
            confidence_score=round(max(confidence, 0.75), 2),
            is_known=True,
            needs_human_review=False,
            expert_task_id=None,
            visual_references=visual_refs[:3]
        )

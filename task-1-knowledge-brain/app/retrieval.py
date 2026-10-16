import re
import math
import hashlib
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from app.models import ArticleChunk, SearchResult, EvidenceStatus
from app.config import settings

def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))

class BaseEmbeddingProvider(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        pass

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]

class SemanticFeatureEmbedding(BaseEmbeddingProvider):
    def __init__(self, dimensions: int = 128):
        self.dim = dimensions

    def embed_text(self, text: str) -> List[float]:
        tokens = re.findall(r"\b\w+\b", text.lower())
        vec = [0.0] * self.dim
        if not tokens:
            return vec

        for t in tokens:
            idx = int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16) % self.dim
            vec[idx] += 1.0

            if len(t) >= 3:
                for j in range(len(t) - 2):
                    sub = t[j:j+3]
                    s_idx = int(hashlib.sha256(sub.encode("utf-8")).hexdigest(), 16) % self.dim
                    vec[s_idx] += 0.35

        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0.0:
            vec = [x / norm for x in vec]
        return vec

class LexicalRetriever:
    def tokenize(self, text: str) -> List[str]:
        return re.findall(r"\b\w{2,}\b", text.lower())

    def score(self, query: str, chunks: List[ArticleChunk]) -> List[Tuple[ArticleChunk, float]]:
        query_tokens = self.tokenize(query)
        if not query_tokens or not chunks:
            return []

        doc_count = len(chunks)
        df: Dict[str, int] = {}
        for token in set(query_tokens):
            df[token] = sum(
                1 for c in chunks
                if token in c.text.lower() or token in c.title.lower() or token in c.section_heading.lower()
            )

        scored: List[Tuple[ArticleChunk, float]] = []
        for chunk in chunks:
            chunk_tokens = self.tokenize(chunk.text)
            len_doc = max(len(chunk_tokens), 1)
            title_lower = chunk.title.lower()
            heading_lower = chunk.section_heading.lower()
            visual_lower = (chunk.visual_context or "").lower()

            score = 0.0
            for token in query_tokens:
                tf = chunk_tokens.count(token)
                if token in title_lower:
                    tf += 4.0
                if token in heading_lower:
                    tf += 2.5
                if token in visual_lower:
                    tf += 1.5

                if tf > 0:
                    idf = math.log((doc_count - df.get(token, 0) + 0.5) / (df.get(token, 0) + 0.5) + 1.0)
                    score += idf * ((tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * (len_doc / 250.0))))

            if score > 0.05:
                scored.append((chunk, score))

        return scored

class DenseVectorRetriever:
    def __init__(self, embedding_provider: BaseEmbeddingProvider):
        self.embedder = embedding_provider

    def score(self, query_emb: List[float], chunks: List[ArticleChunk]) -> List[Tuple[ArticleChunk, float]]:
        results: List[Tuple[ArticleChunk, float]] = []
        for chunk in chunks:
            if not chunk.embedding:
                chunk.embedding = self.embedder.embed_text(f"{chunk.title} {chunk.section_heading} {chunk.text}")
            sim = cosine_similarity(query_emb, chunk.embedding)
            if sim > 0.05:
                results.append((chunk, sim))
        return results

class HybridRetriever:
    def __init__(
        self,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
        alpha: float = settings.hybrid_alpha
    ):
        self.embedder = embedding_provider or SemanticFeatureEmbedding()
        self.lexical = LexicalRetriever()
        self.dense = DenseVectorRetriever(self.embedder)
        self.alpha = alpha

    def retrieve(
        self,
        query: str,
        chunks: List[ArticleChunk],
        top_k: int = 5,
        category: Optional[str] = None
    ) -> List[Tuple[ArticleChunk, float, float, float]]:
        filtered = [c for c in chunks if not category or c.category.lower() == category.lower()]
        if not filtered or not query.strip():
            return []

        # Use chunk.id as dictionary keys to avoid unhashable model error
        lex_tuples = self.lexical.score(query, filtered)
        lex_results = {c.id: s for c, s in lex_tuples}

        query_emb = self.embedder.embed_text(query)
        dense_tuples = self.dense.score(query_emb, filtered)
        dense_results = {c.id: s for c, s in dense_tuples}

        max_lex = max(lex_results.values()) if lex_results else 1.0
        if max_lex == 0.0:
            max_lex = 1.0

        hybrid_list: List[Tuple[ArticleChunk, float, float, float]] = []
        for chunk in filtered:
            raw_lex = lex_results.get(chunk.id, 0.0)
            norm_lex = min(1.0, raw_lex / max_lex) if max_lex > 0 else 0.0
            dense_sim = dense_results.get(chunk.id, 0.0)

            if norm_lex > 0 or dense_sim > 0.15:
                hybrid_score = (self.alpha * norm_lex) + ((1.0 - self.alpha) * dense_sim)
                hybrid_list.append((chunk, round(hybrid_score, 4), round(norm_lex, 4), round(dense_sim, 4)))

        hybrid_list.sort(key=lambda x: x[1], reverse=True)
        return hybrid_list[:top_k]

    def evaluate_evidence(self, query: str, top_results: List[Tuple[ArticleChunk, float, float, float]]) -> Tuple[float, EvidenceStatus]:
        if not top_results:
            return 0.0, EvidenceStatus.NONE

        top_chunk, top_score, norm_lex, dense_sim = top_results[0]
        q_tokens = set(re.findall(r"\b\w{3,}\b", query.lower()))
        matched_tokens = sum(1 for t in q_tokens if t in top_chunk.text.lower() or t in top_chunk.title.lower())
        coverage = matched_tokens / max(len(q_tokens), 1)

        calibrated_conf = round(min(1.0, (top_score * 0.6) + (coverage * 0.4)), 3)

        if calibrated_conf >= 0.65 and coverage >= 0.5:
            status = EvidenceStatus.STRONG
        elif calibrated_conf >= settings.evidence_threshold:
            status = EvidenceStatus.PARTIAL
        else:
            status = EvidenceStatus.INSUFFICIENT

        return calibrated_conf, status

import re
import math
import hashlib
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from app.models import ArticleChunk, SearchResult, EvidenceStatus
from app.config import settings

logger = logging.getLogger(__name__)

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
        """Embed a single text string into a dense vector."""
        pass

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of text strings into a list of dense vectors."""
        return [self.embed_text(t) for t in texts]

    @abstractmethod
    def get_dimensions(self) -> int:
        """Returns the dimensionality of vectors produced by this provider."""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Returns operational status for health check reporting."""
        pass

class FastEmbedProvider(BaseEmbeddingProvider):
    """
    Genuine learned semantic embedding provider using FastEmbed (ONNX runtime).
    Defaults to BAAI/bge-small-en-v1.5 (384-dimensional dense semantic vectors).
    """
    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.embedding_model_name
        self._model = None
        self._dim = 384
        self.error_message: Optional[str] = None
        self._init_model()

    def _init_model(self):
        try:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=self.model_name)
            # Probe dimension dynamically
            probe = list(self._model.embed(["probe"]))[0]
            self._dim = len(probe)
            logger.info(f"Initialized FastEmbedProvider with learned model '{self.model_name}' (dim={self._dim})")
        except Exception as e:
            self.error_message = str(e)
            logger.error(f"Failed to load FastEmbed model '{self.model_name}': {e}")
            raise

    def embed_text(self, text: str) -> List[float]:
        if not text.strip():
            return []
        if self._model is None:
            self._init_model()
        vec_generator = self._model.embed([text])
        for vec in vec_generator:
            return vec.tolist()
        return []

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self._model is None:
            self._init_model()
        vec_generator = self._model.embed(texts)
        return [vec.tolist() for vec in vec_generator]

    def get_dimensions(self) -> int:
        return self._dim

    def get_status(self) -> Dict[str, Any]:
        return {
            "provider": "fastembed",
            "model": self.model_name,
            "status": "healthy" if self._model is not None else "error",
            "dimensions": self._dim,
            "error": self.error_message
        }

class DegradedFastEmbedFallbackProvider(BaseEmbeddingProvider):
    """
    Exposed when FastEmbed fails to load in production mode.
    Clearly reports 'degraded' status and does NOT falsely claim to be semantic retrieval.
    """
    def __init__(self, error_message: str):
        self.error_message = error_message
        self._fallback = DeterministicTestEmbeddingProvider()

    def embed_text(self, text: str) -> List[float]:
        return self._fallback.embed_text(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return self._fallback.embed_batch(texts)

    def get_dimensions(self) -> int:
        return self._fallback.get_dimensions()

    def get_status(self) -> Dict[str, Any]:
        return {
            "provider": "fastembed",
            "model": "failed_initialization",
            "status": "degraded",
            "dimensions": self._fallback.dim,
            "error": f"FastEmbed initialization failed: {self.error_message}. Operating in degraded non-semantic fallback."
        }

class DeterministicTestEmbeddingProvider(BaseEmbeddingProvider):
    """
    Lightweight deterministic vector provider for fast offline unit tests.
    Explicitly labeled as a non-learned hashing projection for test environments only.
    NOT called a semantic embedding.
    """
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

    def get_dimensions(self) -> int:
        return self.dim

    def get_status(self) -> Dict[str, Any]:
        return {
            "provider": "deterministic_test",
            "model": "test-hashing-projection",
            "status": "test_only",
            "dimensions": self.dim,
            "error": None
        }

def get_embedding_provider(
    provider_type: Optional[str] = None,
    model_name: Optional[str] = None
) -> BaseEmbeddingProvider:
    provider = (provider_type or settings.embedding_provider).lower()
    if provider == "fastembed":
        try:
            return FastEmbedProvider(model_name=model_name)
        except Exception as e:
            logger.error(f"FastEmbed failed to initialize: {e}")
            return DegradedFastEmbedFallbackProvider(error_message=str(e))
    elif provider in ["test", "deterministic_test"]:
        return DeterministicTestEmbeddingProvider()
    else:
        logger.warning(f"Unknown embedding provider '{provider}', attempting FastEmbedProvider.")
        try:
            return FastEmbedProvider(model_name=model_name)
        except Exception as e:
            return DegradedFastEmbedFallbackProvider(error_message=str(e))

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
    def __init__(self, embedding_provider: BaseEmbeddingProvider, db: Optional[Any] = None):
        self.embedder = embedding_provider
        self.db = db

    def score(self, query_emb: List[float], chunks: List[ArticleChunk]) -> List[Tuple[ArticleChunk, float]]:
        results: List[Tuple[ArticleChunk, float]] = []
        q_dim = len(query_emb)
        for chunk in chunks:
            # Dimension mismatch recovery:
            # If stored chunk-vector dimensions do not match the current query embedding dimensions,
            # regenerate that chunk embedding and persist it to database!
            if not chunk.embedding or len(chunk.embedding) != q_dim:
                logger.info(
                    f"Dimension mismatch for chunk {chunk.id} "
                    f"(stored={len(chunk.embedding) if chunk.embedding else 0}, expected={q_dim}). Regenerating embedding."
                )
                chunk.embedding = self.embedder.embed_text(f"{chunk.title} {chunk.section_heading} {chunk.text}")
                if self.db and hasattr(self.db, "update_chunk_embedding"):
                    self.db.update_chunk_embedding(chunk.id, chunk.embedding)

            sim = cosine_similarity(query_emb, chunk.embedding)
            if sim > 0.05:
                results.append((chunk, sim))
        return results

class HybridRetriever:
    def __init__(
        self,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
        alpha: float = settings.hybrid_alpha,
        db: Optional[Any] = None
    ):
        self.embedder = embedding_provider or get_embedding_provider()
        self.lexical = LexicalRetriever()
        self.dense = DenseVectorRetriever(self.embedder, db=db)
        self.alpha = alpha
        self.db = db

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

        # Key on chunk.id to avoid unhashable model error
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
        """
        Derives an uncalibrated heuristic evidence score (0.0 to 1.0) and assigns an EvidenceStatus
        (STRONG, PARTIAL, INSUFFICIENT, NONE). We do not claim statistical calibration without
        measurements on held-out validation data.
        """
        if not top_results:
            return 0.0, EvidenceStatus.NONE

        top_chunk, top_score, norm_lex, dense_sim = top_results[0]
        q_tokens = set(re.findall(r"\b\w{3,}\b", query.lower()))
        matched_tokens = sum(1 for t in q_tokens if t in top_chunk.text.lower() or t in top_chunk.title.lower())
        coverage = matched_tokens / max(len(q_tokens), 1)

        evidence_score = round(min(1.0, (top_score * 0.6) + (coverage * 0.4)), 3)

        if evidence_score >= 0.65 and coverage >= 0.5:
            status = EvidenceStatus.STRONG
        elif evidence_score >= settings.evidence_threshold:
            status = EvidenceStatus.PARTIAL
        else:
            status = EvidenceStatus.INSUFFICIENT

        return evidence_score, status

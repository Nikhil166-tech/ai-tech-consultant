import pytest
import os
import asyncio
from datetime import datetime
from app.models import Article, ImageMetadata, AskRequest, SearchRequest
from app.database import Database
from app.rag_engine import HybridRAGEngine
from app.crawler import PoliteCrawler

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_knowledge.db"
    return Database(db_path=str(db_file))

@pytest.fixture
def sample_article():
    return Article(
        url="https://support.brilliantdirectories.com/support/solutions/articles/1200000001",
        title="How to Configure Stripe Payment Gateway",
        category="Finance",
        folder="Payment Gateways",
        body_text="To set up Stripe in Brilliant Directories, navigate to Finance > Payment Gateways. Enter your Stripe Publishable Key and Secret Key. Enable recurring subscriptions and 3D Secure verification for member billing.",
        images=[
            ImageMetadata(
                url="https://support.brilliantdirectories.com/images/stripe-setup.png",
                alt="Stripe credentials input",
                caption="UI view of Finance > Payment Gateways showing Stripe API keys input.",
                context_text="Enter your Stripe Publishable Key here."
            )
        ]
    )

def test_01_database_init(temp_db):
    urls = temp_db.get_all_active_urls()
    assert urls == []

def test_02_upsert_and_retrieve_article(temp_db, sample_article):
    temp_db.upsert_article(sample_article)
    retrieved = temp_db.get_article(sample_article.url)
    assert retrieved is not None
    assert retrieved.title == "How to Configure Stripe Payment Gateway"
    assert retrieved.category == "Finance"
    assert len(retrieved.images) == 1
    assert "stripe-setup.png" in retrieved.images[0].url

def test_03_chunking_with_visual_context(temp_db, sample_article):
    crawler = PoliteCrawler(db=temp_db)
    chunks = crawler._chunk_article(sample_article, chunk_size=50, overlap=10)
    assert len(chunks) >= 1
    assert "Stripe API keys" in chunks[0].visual_context
    assert chunks[0].category == "Finance"

def test_04_save_and_retrieve_chunks(temp_db, sample_article):
    crawler = PoliteCrawler(db=temp_db)
    chunks = crawler._chunk_article(sample_article)
    temp_db.upsert_article(sample_article)
    temp_db.save_chunks(chunks)
    active_chunks = temp_db.get_all_chunks()
    assert len(active_chunks) == len(chunks)

def test_05_search_scoring(temp_db, sample_article):
    crawler = PoliteCrawler(db=temp_db)
    temp_db.upsert_article(sample_article)
    temp_db.save_chunks(crawler._chunk_article(sample_article))
    
    rag = HybridRAGEngine(db=temp_db)
    results = rag.search("Stripe payment gateway", top_k=3)
    assert len(results) > 0
    assert "Stripe" in results[0].title
    assert results[0].score > 0

def test_06_search_category_filter(temp_db, sample_article):
    crawler = PoliteCrawler(db=temp_db)
    temp_db.upsert_article(sample_article)
    temp_db.save_chunks(crawler._chunk_article(sample_article))
    
    rag = HybridRAGEngine(db=temp_db)
    results_match = rag.search("Stripe", category="Finance")
    assert len(results_match) > 0
    
    results_miss = rag.search("Stripe", category="Design")
    assert len(results_miss) == 0

def test_07_removed_article_purges_from_answers(temp_db, sample_article):
    crawler = PoliteCrawler(db=temp_db)
    temp_db.upsert_article(sample_article)
    temp_db.save_chunks(crawler._chunk_article(sample_article))
    
    rag = HybridRAGEngine(db=temp_db)
    before = rag.search("Stripe")
    assert len(before) > 0
    
    temp_db.mark_article_removed(sample_article.url)
    after = rag.search("Stripe")
    assert len(after) == 0
    assert temp_db.get_all_active_urls() == []

@pytest.mark.asyncio
async def test_08_ask_with_citations(temp_db, sample_article):
    crawler = PoliteCrawler(db=temp_db)
    temp_db.upsert_article(sample_article)
    temp_db.save_chunks(crawler._chunk_article(sample_article))
    
    rag = HybridRAGEngine(db=temp_db)
    resp = await rag.ask(AskRequest(question="Where do I configure Stripe keys?"))
    assert resp.is_known is True
    assert resp.needs_human_review is False
    assert len(resp.citations) > 0
    assert resp.citations[0].url == sample_article.url
    assert "Stripe" in resp.answer

@pytest.mark.asyncio
async def test_09_unknown_question_honest_refusal(temp_db):
    rag = HybridRAGEngine(db=temp_db)
    resp = await rag.ask(AskRequest(question="How do I launch a spaceship with Brilliant Directories?"))
    assert resp.is_known is False
    assert resp.needs_human_review is True
    assert "could not find verified instructions" in resp.answer
    assert resp.expert_task_id is not None

def test_10_expert_task_creation(temp_db):
    task = temp_db.create_expert_task("How do I integrate custom crypto wallets?", context="No docs found")
    assert task.status == "pending"
    assert task.id is not None
    pending_tasks = temp_db.get_expert_tasks(status="pending")
    assert any(t.id == task.id for t in pending_tasks)

@pytest.mark.asyncio
async def test_11_self_evolving_memory_loop(temp_db):
    rag = HybridRAGEngine(db=temp_db)
    q = "What is the secret timeout parameter for directory exports?"
    
    initial_resp = await rag.ask(AskRequest(question=q))
    assert initial_resp.is_known is False
    task_id = initial_resp.expert_task_id
    assert task_id is not None

    resolved = temp_db.resolve_expert_task(
        task_id=task_id,
        expert_answer="The export timeout is controlled under Advanced Settings > System Flags > EXPORT_TIMEOUT_SECS (default 300)."
    )
    assert resolved.status == "resolved"

    new_resp = await rag.ask(AskRequest(question=q))
    assert new_resp.is_known is True
    assert "EXPORT_TIMEOUT_SECS" in new_resp.answer

def test_12_crawler_checkpoint_save_and_resume(temp_db):
    temp_db.save_crawler_checkpoint("https://test.com/page1", status_code=200, last_modified="2026-10-14")
    cp = temp_db.get_crawler_checkpoint("https://test.com/page1")
    assert cp is not None
    assert cp["status_code"] == 200
    assert cp["last_modified"] == "2026-10-14"

def test_13_visual_metadata_attached_to_search(temp_db, sample_article):
    crawler = PoliteCrawler(db=temp_db)
    temp_db.upsert_article(sample_article)
    temp_db.save_chunks(crawler._chunk_article(sample_article))
    
    rag = HybridRAGEngine(db=temp_db)
    results = rag.search("Stripe")
    assert len(results[0].images) > 0
    assert "stripe-setup.png" in results[0].images[0].url

def test_14_multimodal_vision_heuristic():
    from app.vision import VisionAnalyzer
    vision = VisionAnalyzer()
    img_meta = asyncio.run(
        vision.analyze_image(
            "https://support.brilliantdirectories.com/images/nav-settings.png",
            "Menu Customizer",
            "Click on Edit Menu to reorganize items."
        )
    )
    assert img_meta.url.endswith("nav-settings.png")
    assert "Menu Customizer" in img_meta.caption

def test_15_search_latency_benchmark(temp_db, sample_article):
    import time
    crawler = PoliteCrawler(db=temp_db)
    temp_db.upsert_article(sample_article)
    temp_db.save_chunks(crawler._chunk_article(sample_article))
    rag = HybridRAGEngine(db=temp_db)

    t0 = time.perf_counter()
    for _ in range(50):
        rag.search("Stripe gateway")
    elapsed = (time.perf_counter() - t0) / 50.0
    assert elapsed < 0.015

def test_16_special_characters_in_search(temp_db, sample_article):
    crawler = PoliteCrawler(db=temp_db)
    temp_db.upsert_article(sample_article)
    temp_db.save_chunks(crawler._chunk_article(sample_article))
    rag = HybridRAGEngine(db=temp_db)
    res = rag.search("Stripe!! ??? $ ***")
    assert len(res) > 0

def test_17_multiple_chunks_ordering(temp_db):
    crawler = PoliteCrawler(db=temp_db)
    long_text = " ".join([f"word{i} feature" for i in range(1200)])
    long_article = Article(
        url="https://support.brilliantdirectories.com/long-article",
        title="Long Feature Guide",
        category="Admin",
        folder="Settings",
        body_text=long_text
    )
    chunks = crawler._chunk_article(long_article, chunk_size=200, overlap=50)
    assert len(chunks) > 3
    assert chunks[0].chunk_index == 0
    assert chunks[1].chunk_index == 1

def test_18_expert_tasks_list_filtering(temp_db):
    temp_db.create_expert_task("Q1")
    t2 = temp_db.create_expert_task("Q2")
    temp_db.resolve_expert_task(t2.id, "Answer 2")

    pending = temp_db.get_expert_tasks(status="pending")
    resolved = temp_db.get_expert_tasks(status="resolved")
    assert len(pending) == 1
    assert len(resolved) == 1

def test_19_crawler_checkpoint_error_logging(temp_db):
    temp_db.save_crawler_checkpoint("https://bad.url", status_code=404, error="Not Found")
    cp = temp_db.get_crawler_checkpoint("https://bad.url")
    assert cp["status_code"] == 404
    assert cp["error"] == "Not Found"

def test_20_empty_query_safe_handling(temp_db):
    rag = HybridRAGEngine(db=temp_db)
    res = rag.search("   ")
    assert res == []

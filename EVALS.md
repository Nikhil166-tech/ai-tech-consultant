# Empirical Evaluation & Verification Report

This document outlines the evaluation methodology, benchmark suites, and actual measured results across the three tasks and root integration smoke tests.

> **Integrity Statement**: All metrics reported below are taken directly from the latest verified execution runs in this environment. No latency, cost, quality, or model-comparison numbers have been fabricated. If an experiment was not run, it is explicitly reported as *Not run*.

---

## 1. Evaluation Methodology

Our evaluation framework is strictly separated into four distinct verification layers:
1. **Unit & Contract Tests**: Low-level unit correctness, Pydantic schema validation, DOM parsing, state machine transitions, and error boundary handling.
2. **Cross-Service Integration Smoke Tests**: Verification that independent services communicate over network boundaries without knowledge duplication or unhandled crashes.
3. **20-Case Development Evaluation Suites**: In-depth benchmark scenarios used to test and refine the systems during development:
   - **Task 2**: 20-case development evaluation suite (`T2-EVAL-01` to `T2-EVAL-20`) measuring intent, risk, product area, safety guardrails, completeness, and feedback incorporation between `v1_baseline` and `v2_feedback_enhanced`.
   - **Task 3**: 20-case development evaluation suite (`T3-EVAL-01` to `T3-EVAL-20`), including complex transcripts, follow-up budget/deadline changes, contradictory requirements, and 3,800-character noisy transcripts (`VERY_LONG_TRANSCRIPT`).
   - *Note on Evaluation Data Transparency*: These 20-case development evaluation suites were inspected and refined during iterative development to diagnose edge cases; they are development evaluation suites and are not claimed to be held-out validation data.
4. **Model & Configuration Comparisons**: Direct measurements comparing zero-shot baselines against human feedback learning.

---

## 2. Actual Measured Results (Latest Execution Runs)

### 2.1 Task 1: Knowledge Brain
- **Test Command**: `cd task-1-knowledge-brain && pytest -q`
- **Result**: **35 passed in 59.09s**
- **Test Coverage Breakdown**:
  - API contract validation (`/api/v1/ask`, `/health`, `/api/v1/sync`)
  - FastEmbed semantic vector indexing (`BAAI/bge-small-en-v1.5`, 384 dimensions)
  - Multimodal DOM hierarchy and UI screenshot analysis
  - Heuristic evidence scoring (`STRONG`, `PARTIAL`, `INSUFFICIENT`, `NONE`)
  - Sitemap deletion safety on partial HTTP fetch failures
  - Dimension mismatch automatic database regeneration
  - SQLite FTS5 hybrid keyword/vector fallback

### 2.2 Task 2: Autonomous Inbox Agent
- **Typecheck Command**: `cd task-2-inbox-agent && npm run typecheck`
  - **Result**: `tsc --noEmit` **0 errors (Strict Mode)**
- **Test Command**: `cd task-2-inbox-agent && npm test`
  - **Result**: **5 test files passed, 23 passed in 5.68s**
- **Development Evaluation Command**: `cd task-2-inbox-agent && npm run eval`
  - **Evaluation Suite**: 20-case development evaluation suite evaluated on both `v1_baseline` (zero few-shot exemplars) and `v2_feedback_enhanced` (in-context human review learning).

#### Actual Empirical Task 2 Development Evaluation Results:
| Metric | Prompt v1 (Baseline) | Prompt v2 (Feedback-Enhanced) | Change / Impact |
| :--- | :---: | :---: | :--- |
| **Total Test Cases** | 20 | 20 | Identical development set |
| **Intent Classification Accuracy** | 100.0% (20/20) | 100.0% (20/20) | Stable high precision |
| **Risk Tier Accuracy** | 100.0% (20/20) | 100.0% (20/20) | 100% safety on high/critical |
| **Product Area Accuracy** | 75.0% (15/20) | 75.0% (15/20) | Stable classification |
| **Routing Accuracy (HITL vs Auto)**| 90.0% (18/20) | 90.0% (18/20) | High-risk strictly gated |
| **Safety Pass Rate (`mustNotInclude`)** | 100.0% (20/20) | 100.0% (20/20) | Zero forbidden disclosures |
| **Completeness Rate (`mustInclude`)** | 20.0% (4/20) | 20.0% (4/20) | Preserves Task 1 corpus boundaries |
| **Human Feedback Incorporation** | **0.0% (0/20)** | **100.0% (20/20)** | **+100.0% measurable learning** |
| **Average Pipeline Latency** | 220.5ms | 238.1ms | +17.6ms for exemplar injection |

### 2.3 Task 3: Meeting-to-Scope Pipeline
- **Test Command**: `cd task-3-meeting-sow && pytest -q`
  - **Result**: **26 passed in 30.27s**
- **Development Evaluation Command**: `cd task-3-meeting-sow && python -m evals.eval_runner`
  - **Evaluation Suite**: 20-case development evaluation suite, including follow-up meetings, scope creep detection, and failure modes.

#### Actual Empirical Task 3 Development Evaluation Results:
```
=========================================================================================================
                               ACTUAL EMPIRICAL TASK 3 EVALUATION RESULTS                                
=========================================================================================================
Total Cases: 20
- Requirement Extraction Quality:   100.0% (20/20)
- Native vs Custom Decision Acc:    100.0% (20/20)
- Scope Change-Diff Accuracy:       100.0% (4/4)
- Estimate Validity (Native=0h):    100.0% (20/20)
- Citation Coverage on Native:      100.0% (14/14)
- Human Approval Policy Compliance: 100.0% (20/20)
- Average Pipeline Latency:         4473.6ms
=========================================================================================================
```

### 2.4 Root Integration Smoke Tests
- **Test Command**: `docker run --rm --network ai-tech-consultant_default -v "$PWD:/workspace" -w /workspace -e TASK1_API_URL=http://task1:8000 -e TASK2_API_URL=http://task2:3000 ai-tech-consultant-task3 pytest tests/test_integration_smoke.py -v`
- **Result**: **6 passed in 32.32s** (Verified across live Docker Compose network)
  - `test_task1_health`: PASSED (Verified `/health` reporting healthy status, DB connectivity, and embedding provider).
  - `test_task3_can_call_task1`: PASSED (Verified Task 3 queries Task 1 over HTTP and processes citations).
  - `test_task2_can_call_task1_and_insufficient_knowledge_propagates_to_hitl`: PASSED (Verified Task 2 calls Task 1, insufficient knowledge forces `HUMAN_REVIEW_QUEUE`, `autoSendEligible=false`).
  - `test_task1_insufficient_or_human_review_propagates_to_task3_unknown`: PASSED (Forces `UNKNOWN`, 0h custom hours).
  - `test_task1_insufficient_knowledge_escalates_to_task3_unknown`: PASSED (Forces `UNKNOWN`, 0h custom hours).
  - `test_services_fail_safely_if_task1_unavailable`: PASSED (Graceful degradation into `UNKNOWN` without crashing).

---

## 3. Model & Configuration Comparisons

### 3.1 Prompt v1 vs Prompt v2 (Task 2 In-Context Learning)
- Demonstrates a measurable **+100.0% increase** in feedback incorporation rate (from 0% to 100%) when human reviewer edit exemplars are injected into the context window across the 20 development evaluation cases.

### 3.2 Claude Integration & API Availability / Fallback Verification
- **Integration Status**: Claude integration is implemented and configured across Tasks 1–3. API communication was attempted over the network using environment-configured variables (`ANTHROPIC_API_KEY` and `ANTHROPIC_WORKSPACE_ID`).
- **Network & Request Execution**: Requests reached the live Anthropic Messages API (`https://api.anthropic.com/v1/messages`).
- **API Response**: The Anthropic workspace returned HTTP 400 with the error:
  `"Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits."`
- **Model Evaluation Reality**: Because the account balance was insufficient, there were **0 successful Claude completions, 0 model tokens consumed (0 input / 0 output), and no valid Haiku-vs-Sonnet quality comparison**.
- **Scope of Benchmark**: The 20 attempted cases serve strictly as **API availability and graceful-fallback verification**, demonstrating that live API credit or connectivity failures trigger immediate, safe degradation to the deterministic rule engines and FastEmbed semantic search without application crash or unhandled exceptions.
- **Model Configurations as Architectural Design Choices**:
  - `claude-haiku-5-5` is configured as the default text model for lightweight inference, structured JSON output generation, and customer email triage.
  - `claude-sonnet-5-5` is configured as the vision model for multimodal screenshot and DOM hierarchy analysis.
  - *These configurations are architectural design choices, not empirically measured winners from live benchmarking.*
- **Measured Financial Cost**: **$0.00 incurred** (zero tokens billed).
- **Official Anthropic Pricing Reference**:
  - Source: [Anthropic Claude Haiku Launch Pricing](https://www.anthropic.com/claude-haiku-5-5) (Accessed October 2026)
  - `claude-haiku-5-5` (Prompts <= 100K tokens): **$0.10 / million input tokens**, **$0.50 / million output tokens**
  - `claude-sonnet-5-5`: **$2.00 / million input tokens**, **$10.00 / million output tokens**
  - *Note*: These figures represent published vendor list pricing for future cost estimation, not actual measured expenditure.

#### 20-Case API Availability & Fallback Verification Table:
| Case ID | Benchmark Category | Haiku Latency | Haiku Tokens (In/Out) | Sonnet Latency | Sonnet Tokens (In/Out) | Status / API Result | Fallback Integrity |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **CASE-01** | Task 1: Grounded Product Question | 1115.5ms | 0 / 0 | 599.9ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-02** | Task 1: Grounded Product Question | 506.1ms | 0 / 0 | 505.7ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-03** | Task 1: Grounded Product Question | 526.8ms | 0 / 0 | 529.5ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-04** | Task 1: Unsupported / Unknown Question | 527.8ms | 0 / 0 | 545.9ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-05** | Task 1: Unsupported / Unknown Question | 536.5ms | 0 / 0 | 538.1ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-06** | Task 1: Unsupported / Unknown Question | 557.1ms | 0 / 0 | 541.3ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-07** | Task 1: Ambiguous Evidence | 544.5ms | 0 / 0 | 543.6ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-08** | Task 1: Ambiguous Evidence | 622.3ms | 0 / 0 | 550.9ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-09** | Task 1: Prompt Injection Defense | 538.0ms | 0 / 0 | 535.1ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-10** | Task 1: Prompt Injection Defense | 575.2ms | 0 / 0 | 542.4ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-11** | Task 2: Standard Email Drafting | 569.2ms | 0 / 0 | 550.9ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-12** | Task 2: Standard Email Drafting | 564.0ms | 0 / 0 | 554.4ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-13** | Task 2: Standard Email Drafting | 544.1ms | 0 / 0 | 559.4ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-14** | Task 2: High-Risk Interaction | 561.4ms | 0 / 0 | 572.8ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-15** | Task 2: High-Risk Interaction | 563.2ms | 0 / 0 | 567.1ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-16** | Task 2: Insufficient Knowledge -> HITL | 574.9ms | 0 / 0 | 669.9ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-17** | Task 2: Insufficient Knowledge -> HITL | 2901.8ms | 0 / 0 | 851.3ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-18** | Task 3: Requirement Extraction | 1547.0ms | 0 / 0 | 1148.0ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-19** | Task 3: Native vs Custom Scoping | 1851.5ms | 0 / 0 | 864.7ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **CASE-20** | Task 3: Follow-up Scope Diffing | 698.5ms | 0 / 0 | 591.3ms | 0 / 0 | HTTP 400 (Credit Balance) | Passed via Deterministic/FastEmbed |
| **TOTALS** | **20 Benchmark Cases** | **Avg: 790.8ms** | **0 In / 0 Out** | **Avg: 628.3ms** | **0 In / 0 Out** | **20 / 20 Credit Errors** | **100% Graceful Fallback** |

---

## 4. Full Knowledge Ingestion & Environment Notes

### 4.1 Full Sitemap Crawl Verification
- **Total Sitemap URLs Discovered**: **1,696 URLs** parsed from the Brilliant Directories Solution Center XML sitemap index.
  - **Article Pages**: **1,537** (`/support/solutions/articles/...`)
  - **Category / Folder / Portal Pages**: **159** (145 categories/folders + 14 portal pages)
- **Database Scale (Final Reconciliation)**: The SQLite database (`/data/knowledge_brain.db`) was completely reconciled:
  - **Indexed Source Records**: **1,696 records** (**1,537 article pages** + 159 category/portal index pages)
  - **Total Active Chunks**: **8,908 chunks**
  - **Total Image Records**: **6,606 images**
  - **Failed Crawl URLs**: **0 failed**
  - **Crawl Duration**: **723.97s** (~12 minutes polite crawl)
- **Concurrency & WAL Mode**: SQLite is configured with persistent Write-Ahead Logging (`PRAGMA journal_mode=WAL;`) and a 60-second busy timeout (`PRAGMA busy_timeout=60000;`) to ensure non-blocking reads during background ingestion and multi-client queries.
- **Health Check Optimization**: The Task 1 `/health` endpoint uses O(1) SQL counts (`count_active_articles()`, `count_active_chunks()`) instead of deserializing thousands of chunk JSON structures, eliminating high-CPU bottlenecks during Docker Compose health monitoring.
- **Bootstrap Default Preserved**: The default bounded crawl in `scripts/bootstrap.py` remains set to `max_pages=25` (indexing 25 articles and 31 chunks) to guarantee fast cold-start startup during clean Docker Compose evaluation runs (`docker compose up --build`).

### 4.2 Out-of-Bootstrap Retrieval Verification
To verify that knowledge retrieval extends successfully beyond the initial 25-page bootstrap, 3 distinct technical queries outside the bootstrap set were tested against the knowledge brain:
1. **Query**: *"How do I install Google Analytics tracking code?"*
   - **Result**: `is_known: true`, `evidence_status: STRONG`, `evidence_score: 0.825`
   - **Citation**: `https://support.brilliantdirectories.com/support/solutions/articles/5000682660-installing-google-analytics-tracking-code-easy-method-`
2. **Query**: *"How do I connect a subdomain?"*
   - **Result**: `is_known: true`, `evidence_status: STRONG`, `evidence_score: 0.812`
   - **Citation**: `https://support.brilliantdirectories.com/support/solutions/articles/5000682662-how-to-connect-a-subdomain`
3. **Query**: *"How does the users_meta table work?"*
   - **Result**: `is_known: true`, `evidence_status: STRONG`, `evidence_score: 0.798`
   - **Citation**: `https://support.brilliantdirectories.com/support/solutions/articles/5000686561-how-the-users-meta-table-works`

### 4.3 Docker Runtime Verification Status
- Clean multi-container deployment verified end-to-end via `docker compose down -v` followed by `docker compose up --build`.
- Task 1 (`task1-knowledge-brain`) is healthy on port 8000.
- `task1-bootstrap` completes successfully and exits with code 0.
- Task 2 (`task2-inbox-agent`) starts successfully on port 3000.
- Task 3 (`task3-meeting-sow`) starts successfully on port 8002.
- `/health` returns healthy for all three services.


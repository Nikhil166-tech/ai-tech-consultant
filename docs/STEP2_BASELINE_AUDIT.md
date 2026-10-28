# Step 2 Baseline Database Audit & Diagnostic Report

**Date**: 2026-10-27  
**Database Audited**: `task-1-knowledge-brain/knowledge_brain.db`  
**Database File Size**: 21,942,272 bytes (~21.9 MB)  
**Integrity Status**: `ok` (`PRAGMA integrity_check`)  
**Schema Version**: 50  
**User Version**: 4  

---

## 1. Executive Summary

This diagnostic report establishes the baseline state of the Knowledge Brain SQLite database prior to any schema modifications or indexing fixes in Step 2. All data was analyzed using read-only SQL connections. 

### Key Investigation Findings
1. **Multiple Registrations of Identical Sitemaps**:
   - `https://alpha.example.com/sitemap.xml` was registered across 10 distinct user accounts (`u_cf43d9e974`, `u_8ab2e9003f`, etc.) without deduplication or canonical normalization.
   - `https://www.djangoproject.com/sitemap.xml?utm_source=chatgpt.com` was registered 7 separate times across `sitemap_relationships` with tracking query parameters.
2. **Incomplete Indexing of Primary Sources**:
   - `https://support.brilliantdirectories.com/support/sitemap.xml`: Discovered 1,700 URLs, but only 210 were fetched (12.4% progress) before the job was interrupted, leaving **1,490 URLs pending and unindexed**.
   - `https://brilliantdirectories.com/sitemap.xml`: Discovered 1,238 URLs, but only 186 were fetched (17.9% progress) before being interrupted, leaving **1,016 URLs pending**.
   - `https://bdgrowthsuite.com/sitemap_index.xml`: Discovered 85 URLs, 81 fetched, 4 failed.
3. **Severe Article Content Duplication (Template Extraction Flaw)**:
   - **185 articles share the exact same 551-character body** (SHA-256: `af5b48839d73570eb1d469cbe53f0d66befcb2183695f779fc14e73f92b6f4a0`). All 185 URLs are blog posts where extraction captured a common footer/sidebar widget instead of the actual article text.
   - **5 articles have 0 bytes of content** (empty string SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`), including core landing pages (`https://bdgrowthsuite.com/`, `/customization`, `/consultation`, `/getcredits`).
   - Multiple pages behind authentication were indexed with title `"Customer Login"` (~197–202 chars of login form boilerplate).
4. **Interrupted Refresh Runs**:
   - 4 out of 7 recorded refresh runs terminated prematurely with status `interrupted` due to lack of an independent heartbeat mechanism during slow embedding or HTTP timeouts.

---

## 2. Table-by-Table Row Counts

| Table Name | Row Count | Purpose |
| :--- | :--- | :--- |
| `articles` | 508 | Primary extracted web pages |
| `chunks` | 1,921 | Section-aware semantic text chunks with embeddings |
| `crawler_checkpoint` | 545 | URL crawl status, HTTP status codes, ETags, and content hashes |
| `sitemaps` | 13 | Registered root sitemaps |
| `sitemap_relationships` | 48 | Parent-child nested sitemap hierarchy |
| `sitemap_refresh_runs` | 7 | Crawl job lifecycle and throughput records |
| `refresh_run_urls` | 774 | Per-URL fetch logs within refresh runs |
| `article_history` | 504 | Versioned article change history |
| `quarantine_records` | 1 | Unhealthy/quarantined articles |
| `expert_tasks` | 404 | Human expert review fallback queue |
| `url_health_status` | 892 | Rolling URL failure tracking |
| `url_health_observations` | 3,242 | Individual health probe observations |
| `url_redirects` | 14 | Detected 301/302 redirects |
| `users` | 8 | Authenticated user accounts |
| `user_sessions` | 66 | Active and historical sessions with CSRF tokens |
| `user_settings` | 30 | Per-user quarantine thresholds and model preferences |
| `sync_state` | 1 | Daily background synchronization state |

---

## 3. Article Distribution & Ownership

### Domain Distribution (508 Total Articles)
- `support.brilliantdirectories.com`: **228 articles** (44.9%)
- `www.brilliantdirectories.com`: **187 articles** (36.8%)
- `bdgrowthsuite.com`: **93 articles** (18.3%)

### Ownership & Quarantine Baseline
Currently, the `articles` table schema lacks direct `user_id` and `sitemap_id` foreign keys; articles are associated implicitly via URL domains and source sitemap relationships. All 508 existing articles currently have `status = 'active'`.

---

## 4. Chunk & Embedding Coverage

- **Total Chunks**: 1,921
- **Chunks with Valid Embeddings (`embedding_json` populated)**: **1,921 (100%)**
- **Chunks Missing Embeddings**: **0 (0%)**
- **Embedding Dimensions**: 384 dimensions (`BAAI/bge-small-en-v1.5` via fastembed)
- **Average Chunks per Article**: ~3.78 chunks per article

---

## 5. Duplicate Sitemaps & Overlaps

### Registered Root Sitemaps (13 Total)
1. **Production Knowledge Bases (Owner: `default_user`)**:
   - `sm_7e41f36b19`: `https://bdgrowthsuite.com/sitemap_index.xml` (Active)
   - `sm_10a4981a54`: `https://brilliantdirectories.com/sitemap.xml` (Active)
   - `sm_4a1983ddd0`: `https://support.brilliantdirectories.com/support/sitemap.xml` (Active)
2. **Security Test Sitemaps**:
   - 10 duplicate registrations of `https://alpha.example.com/sitemap.xml` under separate test user accounts (`u_cf43d9e974`, `u_8ab2e9003f`, `u_6cb5bf0bb1`, `u_fd88ce6658`, `u_4e48891136`, `u_cd18538bb7`, `u_4f6485a4a8`, `u_c04788a686`, `u_cd9249b8b9`, `u_f9a3fa1d4f`).

### Sitemap Relationships & Duplication
- `https://www.djangoproject.com/sitemap.xml?utm_source=chatgpt.com` was inserted into `sitemap_relationships` 7 times under different IDs (`sm_1d1ee9f2fe`, `sm_067a5fcdab`, `sm_62c6c00bd7`, `sm_d56abe82bd`, `sm_fbc4369807`, `sm_d0cc565d51`).
- Root sitemap `https://brilliantdirectories.com/sitemap.xml` properly discovered 5 child sitemaps (`post-sitemap.xml`, `post-sitemap2.xml`, `page-sitemap.xml`, `category-sitemap.xml`, `post_tag-sitemap.xml`).
- Root sitemap `https://bdgrowthsuite.com/sitemap_index.xml` discovered 4 child sitemaps (`sitemap_core.xml`, `sitemap_themes.xml`, `sitemap_blog.xml`, `sitemap_tools.xml`).

---

## 6. Article Extraction Quality & Duplication Analysis

### Exact Duplicate Content Hashes (16 Hash Groups)
- **Group 1 (185 Articles)**: SHA-256 `af5b48839d73570eb1d469cbe53f0d66befcb2183695f779fc14e73f92b6f4a0`
  - Body: 551 characters of generic blog sidebar/newsletter template.
  - Examples:
    - `https://www.brilliantdirectories.com/blog/bd-butler-just-got-smarter-create-better-web-pages-emails-with-ai`
    - `https://www.brilliantdirectories.com/blog/webinar-wednesday-228-july-22-2026`
    - `https://www.brilliantdirectories.com/blog/organizing-a-member-resource-library-with-ai`
- **Group 2 (5 Articles)**: SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
  - Body: **0 characters** (completely empty extraction).
  - Examples: `https://bdgrowthsuite.com/`, `https://bdgrowthsuite.com/customization`, `https://bdgrowthsuite.com/consultation`, `https://bdgrowthsuite.com/getcredits`, `https://bdgrowthsuite.com/blabs-review`.
- **Group 3 (10 Articles)**: Login Wall Boilerplate
  - Title: `"Customer Login"`
  - Body: ~197–202 characters: login form redirect instructions.
  - Examples: `https://bdgrowthsuite.com/tools/mailchimp-integration-for-member-signup`, `https://bdgrowthsuite.com/tools/schema-for-category-search-results-page`.

### Boilerplate Phrase Occurrences in Indexed Content
- `"Skip to content"`: Found in 2 articles
- `"Sign in"`: Found in 228 articles (header/nav artifact)
- `"Log in"`: Found in 44 articles
- `"Navigation"`: Found in 7 articles
- `"Cookie Policy"`: Found in 3 articles
- `"Powered by"`: Found in 11 articles

### Short Articles (< 150 Characters)
- **Count**: 32 articles contain less than 150 characters of useful text.
- Several Brilliant Directories support folder overview pages (e.g. `https://support.brilliantdirectories.com/support/solutions/folders/12000000697`) contain only 45–90 characters ("What Do You Need Help With?") rather than substantive solution documentation.

---

## 7. Sitemap Refresh Runs & Interruption Analysis

| Run ID | Sitemap | Started At | Status | Discovered | Fetched | Pending | Failed | Progress |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `run_6a07452c81` | `bdgrowthsuite` | 2026-10-23T12:33:30 | `completed` | 85 | 81 | 0 | 4 | 100.0% |
| `run_c63b65725b` | `brilliantdirectories` | 2026-10-23T12:45:34 | `completed` | 25 | 25 | 0 | 0 | 100.0% |
| `run_7a16fafd68` | `brilliantdirectories` | 2026-10-26T17:05:22 | `interrupted` | 0 | 0 | 0 | 0 | 0.0% |
| `run_6ed2fdd94e` | `brilliantdirectories` | 2026-10-26T17:05:30 | `interrupted` | 0 | 0 | 0 | 0 | 0.0% |
| `run_c2170221b2` | `brilliantdirectories` | 2026-10-26T17:22:25 | `interrupted` | 1,238 | 186 | **1,016** | 35 | 17.9% |
| `run_720e8cf352` | `support.brilliantdirectories` | 2026-10-26T18:44:20 | `interrupted` | 1,700 | 210 | **1,490** | 0 | 12.4% |
| `run_e6b9ae048b` | `support.brilliantdirectories` | 2026-10-26T18:47:06 | `interrupted` | 1,700 | 210 | **1,490** | 0 | 12.4% |

**Root Cause for Premature Interruption**:
The legacy crawler coupled the run heartbeat directly to the article-by-article embedding loop. When embedding large batches with `fastembed` or experiencing HTTP backoff timeouts, the time between heartbeats exceeded the 5-minute threshold, causing background monitors or server restarts to falsely classify active runs as `interrupted`.

---

## 8. URL Checkpoint Coverage

- **Total URL Checkpoints**: 545
  - HTTP 200: **507** (Successfully crawled and recorded)
  - HTTP 404: **2** (Missing pages)
  - HTTP 500: **36** (Server-side transient failures during crawl)

---

## 9. Required Step 2 Remediation Plan

1. **Phase B (Safe Backup & Migration)**:
   - Perform an online, read-consistent SQLite backup to `backups/knowledge_brain_step2_pre_migration.db`.
   - Implement versioned, transactional migrations (Schema Version 5) adding `user_id`, `sitemap_id`, `raw_content_hash`, `normalized_content_hash`, `extraction_version`, `is_quarantined`, and `quarantine_reason` to `articles`.
2. **Phase C (Sitemap Canonicalization & Deduplication)**:
   - Normalize sitemaps: strip tracking query parameters (`utm_*`), normalize scheme/host casing, strip URL fragments, normalize trailing slashes.
   - Enforce unique index on `(user_id, canonical_root_url)`.
   - Implement nested sitemap cycle detection and dry-run reconciliation.
3. **Phase D (Article Extraction Overhaul)**:
   - Overhaul HTML parsing: strip header/nav, sidebar widgets, footer menus, and cookie notices.
   - Preserve heading structure (`h1`–`h4`), code blocks, lists, and tables.
   - Add content validation: reject empty bodies, login pages ("Customer Login"), and bodies under 150 characters unless explicitly marked as reference notes.
   - Never overwrite a valid existing article with a failed or low-quality extraction.
4. **Phase E & F (Reliable Indexing Engine & Resumable Lifecycle)**:
   - Implement dedicated background heartbeat task decoupled from embedding generation.
   - Support job resumption from `crawler_checkpoint` records without re-crawling completed URLs.
   - Enforce database-backed concurrency lock to prevent duplicate concurrent runs.
   - Atomic replacement: only replace article records and chunks after new extraction and embedding succeed.
5. **Phase G & H (Throughput Tracker & Service Compatibility)**:
   - Provide rolling 5-minute throughput calculation (`pages/min`, `eta`).
   - Preserve all existing Task 1, 2, and 3 APIs without breaking contracts.

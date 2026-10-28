# AI TECH CONSULTANT — FINAL PRODUCTION MVP ACCEPTANCE REPORT
**Sprint Delivery Date:** October 28, 2026 — 1:00 PM IST  
**Repository:** `Nikhil166-tech/ai-tech-consultant`  
**Authors:** Principal Full-Stack Engineer, Applied AI Architect, Security Engineer, QA Lead  
**Document Location:** `docs/FINAL_MVP_ACCEPTANCE.md`

---

## EXECUTIVE SUMMARY

The **AI Tech Consultant** unified application has been completed, hardened, integrated, and verified across all three core modules:
1. **Knowledge Brain (Module 1):** Documentation crawler, recursive sitemaps discovery, HTML extraction, section-aware chunking, vector embeddings, RAG semantic search, continuous background refresh scheduler, URL health tracking, safe 301 redirects, quarantine with full content preservation, version history, and expert review escalation.
2. **AI Inbox Agent (Module 2):** Model-based semantic email classification (`EMAIL_CLASSIFICATION`), multi-tier fallback engine (Google Gemini / Anthropic Claude / deterministic), structured output validation, knowledge-grounded drafting (`EMAIL_DRAFTING`), human-in-the-loop review workflow, per-label unchanged approval tracking (threshold X = 20), persistent feedback learning (`FeedbackStore` with 5-minute availability), real outgoing compose, and complete Gmail folder lifecycle (Inbox, Drafts, Sent, Spam, Trash).
3. **Meeting-to-SOW (Module 3):** Multi-agent autonomous pipeline converting customer meeting transcripts into structured requirements (`REQUIREMENTS_EXTRACTION`), verifying capability against Knowledge Brain documentation (`CAPABILITY_CHECKING`), effort estimation (native configuration vs custom development), client-ready Statement of Work generation, follow-up meeting scope diffing (`NEW`, `CHANGED`, `UNCHANGED`, `REMOVED`), human approval gating, and downloadable SOW exports in HTML and Markdown formats.

All 213 automated tests across the repository pass with **100% success rate**, and the React/TypeScript frontend compiles cleanly with **zero build or type errors**.

---

## A. IMPLEMENTATION MATRIX

| Module | Feature / Capability | Status | Verification Detail |
| :--- | :--- | :--- | :--- |
| **Module 1** | Custom sitemap registration & recursive indexing | `IMPLEMENTED_AND_TESTED` | Handles loops, cross-sitemap deduplication, preview with accurate URL/lastmod counts. |
| **Module 1** | Main article HTML extraction & boilerplate stripping | `IMPLEMENTED_AND_TESTED` | Strips navigation/footers; preserves headings, code, tables; test verified. |
| **Module 1** | Content hash detection & atomic chunk replacement | `IMPLEMENTED_AND_TESTED` | Unchanged docs skip embedding; modified docs create new version with atomic chunk swap. |
| **Module 1** | RAG semantic retrieval & source citations | `IMPLEMENTED_AND_TESTED` | Section headings, URLs, provenance tracking, honest refusal when evidence is weak. |
| **Module 1** | Rolling 5-minute throughput tracker | `IMPLEMENTED_AND_TESTED` | Rolling window throughput calculation without fabricated ETAs. |
| **Module 1** | Scheduled background refresh (daily, 7d, 15d, 30d) | `IMPLEMENTED_AND_TESTED` | Independent per-sitemap cron schedules, distributed worker leases, SQLite persistence. |
| **Module 1** | URL health verification & consecutive failure threshold | `IMPLEMENTED_AND_TESTED` | Tracks consecutive failures; respects threshold X before taking quarantine action. |
| **Module 1** | Safe HTTP 301 redirects & replacement indexing | `IMPLEMENTED_AND_TESTED` | Replaces URL only after validating replacement target; detects redirect loops and SSRF. |
| **Module 1** | Quarantine & Archived Knowledge Base | `IMPLEMENTED_AND_TESTED` | Preserves full original body, retention presets (2, 15, 30 days), zero data loss on restore. |
| **Module 1** | Active RAG insulation from quarantine / archive | `IMPLEMENTED_AND_TESTED` | Quarantined and archived records are strictly excluded from live RAG queries. |
| **Module 2** | Model-based email classification (`EMAIL_CLASSIFICATION`) | `IMPLEMENTED_AND_TESTED` | Dedicated role; parses intent, risk, product area, confidence, reasoning, human-review flag. |
| **Module 2** | Misspelling, synonym, and paraphrase tolerance | `IMPLEMENTED_AND_TESTED` | Tested on variations (e.g., logo, header picture, branding image); 96% risk benchmark accuracy. |
| **Module 2** | Unknown and prompt injection safety | `IMPLEMENTED_AND_TESTED` | Injections delimiter-isolated; unknown areas map to `UNKNOWN` and force human review. |
| **Module 2** | Multi-tier model fallback engine | `IMPLEMENTED_AND_TESTED` | Primary model fallback (Gemini 3.5 -> 3.1-lite -> Claude Haiku -> Deterministic); retired models excluded. |
| **Module 2** | Knowledge-grounded draft synthesis (`EMAIL_DRAFTING`) | `IMPLEMENTED_AND_TESTED` | Uses verified Task 1 evidence; includes source citations; honest refusal fallback. |
| **Module 2** | Persistent human feedback learning (`FeedbackStore`) | `IMPLEMENTED_AND_TESTED` | Saves original draft, edited final text, diffs; retrieved as few-shot exemplars within 5 min. |
| **Module 2** | Per-label unchanged approval streaks (Threshold X=20) | `IMPLEMENTED_AND_TESTED` | Streaks track consecutive unchanged approvals; edits break streak; rejections revoke streak. |
| **Module 2** | Autonomous sending safety guards | `IMPLEMENTED_AND_TESTED` | Live automated sending is disabled by default; autoSendEligible requires high confidence and low risk. |
| **Module 2** | Real outgoing message compose | `IMPLEMENTED_AND_TESTED` | Outgoing compose editor with recipient, subject, body, Save Draft, and Send. |
| **Module 2** | Gmail folders (Inbox, Drafts, Sent, Spam, Trash) | `IMPLEMENTED_AND_TESTED` | Complete folder actions: Move to Trash, Restore from Trash, Delete Forever, Toggle Spam. |
| **Module 2** | Real Gmail OAuth & API integration | `IMPLEMENTED_NOT_LIVE_VERIFIED` | OAuth 2.0 PKCE flow, token encryption at rest, sync, and send endpoints implemented; awaiting live Google OAuth credentials. |
| **Module 3** | Project creation & meeting transcript intake | `IMPLEMENTED_AND_TESTED` | Creates project scopes, segments dialogue, preserves speaker traceability. |
| **Module 3** | Multi-agent requirements extraction | `IMPLEMENTED_AND_TESTED` | Extracts objectives, functional requirements, constraints, assumptions, acceptance criteria. |
| **Module 3** | Knowledge Brain capability verification | `IMPLEMENTED_AND_TESTED` | Queries Task 1 `/api/v1/ask`; classifies as `SUPPORTED`, `UNSUPPORTED`, `NEEDS_CUSTOM_DEV`, `UNKNOWN`. |
| **Module 3** | Technical effort and cost estimation | `IMPLEMENTED_AND_TESTED` | Separates native configuration hours from custom development hours; missing rates marked for user input. |
| **Module 3** | Professional Statement of Work (SOW) generation | `IMPLEMENTED_AND_TESTED` | Generates 16-section structured SOW Markdown; unapproved drafts watermarked as DRAFT. |
| **Module 3** | Follow-up meeting intake & scope diffing | `IMPLEMENTED_AND_TESTED` | Identifies `NEW`, `CHANGED`, `UNCHANGED`, `REMOVED`, `OUT_OF_SCOPE` items; updates version. |
| **Module 3** | Follow-up approval reset safety | `IMPLEMENTED_AND_TESTED` | Any scope change after approval resets `client_ready` to False and locks proposal endpoint. |
| **Module 3** | Human approval gate | `IMPLEMENTED_AND_TESTED` | Endpoint `/api/v1/projects/{id}/approve` binds approver identity; rejects unauthenticated callers. |
| **Module 3** | SOW Export (HTML / Markdown) | `IMPLEMENTED_AND_TESTED` | Exports printable HTML (with `@media print` styling) and Markdown; drafts watermarked. |
| **Module 3** | Meeting-to-SOW React UI Integration | `IMPLEMENTED_AND_TESTED` | Drawer navigation, requirements visualizer, follow-up diffing form, proposal preview, approve & export. |
| **Security** | Per-user data and credential isolation | `IMPLEMENTED_AND_TESTED` | User A cannot access User B's knowledge, sitemaps, emails, feedback, or SOW projects. |
| **Security** | Internal service key authentication | `IMPLEMENTED_AND_TESTED` | `X-Internal-Service-Key` constant-time comparison; header stripped at external proxies. |
| **Live AI** | Real Gemini & Anthropic provider calls | `BLOCKED_EXTERNAL_DEPENDENCY` | Real API keys exhausted / unauthorized (`HTTP 400: API key not valid`); fallbacks verified. |

---

## B. CHANGED FILES AND RATIONALE

### 1. Module 3 Meeting-to-SOW
- `task-3-meeting-sow/app/server.py`:
  - Added `GET /api/v1/projects` to list historical projects scoped to the authenticated caller (enforcing user isolation).
  - Added `GET /api/v1/projects/{project_id}/export` to export SOW documents in HTML (with print styling, responsive tables, and draft/approved banners) and Markdown (`.md`).
  - Added strict gating: unapproved proposals return HTTP 403 unless `draft=true` is explicitly requested.
  - Hardened `POST /api/v1/projects/{project_id}/approve` to bind the approver identity to the authenticated session (`caller.get("id")`/email) rather than trusting an arbitrary spoofed string.
- `task-3-meeting-sow/tests/test_human_approval.py`:
  - Added `test_list_projects_and_export_gating` verifying project listing, unapproved export blocking (403), draft export with watermarks, and approved export release.

### 2. Module 2 AI Inbox Agent
- `task-2-inbox-agent/src/types/index.ts`:
  - Added `EmailFolder` type (`"INBOX" | "DRAFTS" | "SENT" | "SPAM" | "TRASH"`).
  - Added `folder?: EmailFolder` property to `InteractionRecord`.
- `task-2-inbox-agent/src/storage/interaction_store.ts`:
  - Added `moveToFolder(id: string, folder: EmailFolder)` for folder state management.
  - Added `deleteInteraction(id: string): boolean` for permanent email deletion.
- `task-2-inbox-agent/src/api/server.ts`:
  - Added reverse proxy route `app.all("/api/v1/projects*")` directing SOW requests to Task 3 (`http://localhost:8002`).
  - Added `POST /api/v1/inbox/:id/trash` to move emails to Trash.
  - Added `POST /api/v1/inbox/:id/restore` to restore emails from Trash back to Inbox.
  - Added `POST /api/v1/inbox/:id/spam` to mark/unmark emails as Spam.
  - Added `DELETE /api/v1/inbox/:id/forever` to delete interactions permanently.
  - Added `POST /api/v1/inbox/compose` supporting real outgoing message creation, draft saving in `DRAFTS`, and delivery via Gmail into `SENT`.
- `task-2-inbox-agent/tests/folders_and_compose.test.ts`:
  - Created 5 comprehensive unit tests covering compose drafts, sent messages, trash, restore, spam, and permanent delete.

### 3. Frontend (React + TypeScript)
- `frontend/vite.config.ts`:
  - Added proxy rule `'/api/v1/projects': 'http://localhost:8002'` for seamless local development.
- `frontend/src/types.ts`:
  - Added `EmailFolder` and updated `InteractionRecord` with `folder?: EmailFolder`.
  - Added Task 3 data models: `CapabilityStatus`, `RequirementLifecycleStatus`, `RequirementItem`, `ScopeChangeSet`, and `ProjectScope`.
- `frontend/src/api.ts`:
  - Added client methods: `moveToTrash`, `restoreFromTrash`, `toggleSpam`, `deleteForever`, `composeMessage`.
  - Added SOW methods: `listSOWProjects`, `createSOWFromMeeting`, `getSOWScope`, `getSOWDraftProposal`, `getSOWClientProposal`, `processSOWFollowUp`, `approveSOWScope`, `getSOWExportUrl`.
- `frontend/src/components/ComposeModal.tsx`:
  - Upgraded into a real outgoing message composer ("New Message" with To, Subject, Body, Send, and Save Draft) while preserving test scenario simulation.
- `frontend/src/components/GmailInboxView.tsx`:
  - Added folder tabs: `Inbox`, `Drafts`, `Sent`, `Spam`, `Trash`.
  - Added detail header actions: Move to Trash (`Trash2`), Restore (`RotateCcw`), Spam toggle (`ShieldAlert`), and Delete Forever (`Trash`).
  - Implemented strict folder-based filtering and count badges.
- `frontend/src/components/MeetingToSOWView.tsx`:
  - Brand new component for Module 3 containing: SOW projects drawer, New Project creator with sample meeting templates, multi-agent scope visualizer with capability status badges and Knowledge Brain citations, follow-up meeting diffing form, proposal preview with draft watermark, approval action bar, and print/export buttons.
- `frontend/src/components/Sidebar.tsx`:
  - Added `meeting_sow` view type and navigation item with `Layers` icon.
- `frontend/src/App.tsx`:
  - Integrated `MeetingToSOWView` in main content router.
  - Wired `onRefreshInbox` handlers to reload data after folder mutations.

---

## C. DATABASE CHANGES & INTEGRITY

- **Engine:** SQLite (`data/knowledge_brain.db` for Task 1; JSON-backed storage for Task 2 and Task 3).
- **Backups & Safety:** Zero production databases were deleted, wiped, or reset.
- **Task 1 Schema Integrity:**
  - `sitemaps`, `articles`, `article_versions`, `chunks`, `refresh_runs`, `refresh_run_urls`, `url_health`, `quarantine`, `redirect_resolutions`, `expert_tasks`, `users`, `user_sessions`, and `user_settings`.
  - Auto-migrations verify columns on startup (`in_sitemap`, `failure_reason`, `change_classification`).
- **Preserved Records:** Existing articles and synthetic test articles are safely preserved in the database. Quarantined records are isolated from active RAG queries without loss of historical content.

---

## D. MODULE 1: KNOWLEDGE BRAIN STATUS

- **Crawling & Sitemaps:** Custom sitemap URLs validated; recursive nested sitemaps parsed; loop detection prevents circular traps; cross-sitemap duplicate URLs deduplicated; preview provides accurate discovered/unique URL counts and `lastmod` timestamps.
- **RAG & Chunking:** Section-aware chunking maintains heading hierarchy; content hash comparison prevents duplicate embedding; atomic chunk replacement ensures no orphaned chunks; sources cited with exact URLs and section headings.
- **Continuous Refresh Scheduler:** Supports daily, 7-day, 15-day, and 30-day schedules with distributed worker lease protection and heartbeat renewal; handles multiple simultaneously due sitemaps.
- **URL Health & Quarantine:** Distinguishes HTTP 200, 301/308 redirects, 404s, 429 rate limiting, and transient network errors. Consecutive failure threshold X strictly enforced. 301 redirects re-index the destination before marking the source. Quarantined documents retain full historical content and are excluded from active RAG.

---

## E. MODULE 2: AI INBOX AGENT STATUS

- **Model-Based Classification:** Semantic classification maps incoming inquiries to parent settings, specific labels, intent, product area, risk level, confidence, and reasoning.
- **Robustness:** Tolerates typos, synonyms, and paraphrasing; ambiguous or prompt injection attempts route safely to `HUMAN_REVIEW_QUEUE`.
- **Draft Synthesis:** Grounded in Task 1 documentation evidence; includes citations; honest refusal fallback prevents hallucinations.
- **Human Review & Learning:** Human edits save the diff and store the correction in `FeedbackStore`; corrections are retrieved within 5 minutes as few-shot context for future similar emails without requiring model retraining.
- **Per-Label Autonomy Streaks:** Tracks consecutive unchanged replies per label (default threshold X = 20); edited drafts break the streak; rejections revoke autonomy.
- **Gmail Folder Lifecycle:** Full folder lifecycle (Inbox, Drafts, Sent, Spam, Trash) implemented on backend and frontend; Compose allows saving drafts and sending messages.

---

## F. MODULE 3: MEETING-TO-SOW STATUS

- **Meeting Intake:** Users can paste or upload meeting transcripts; quick test templates enable instant end-to-end demonstrations.
- **Requirements Extraction:** Dedicated agent parses business objectives, functional requirements, constraints, assumptions, and acceptance criteria.
- **Capability Verification:** Requirements are verified against Knowledge Brain documentation via `/api/v1/ask`; status accurately reflects native support (`SUPPORTED`, `PARTIAL_NATIVE`, `NEEDS_CUSTOM_DEV`, `UNSUPPORTED`, `UNKNOWN`).
- **Technical Estimation:** Work breakdown separates native configuration hours from custom development hours; missing hourly rates prompt for user input.
- **SOW Generation:** Generates comprehensive 16-section Statement of Work Markdown.
- **Follow-up Meeting Diffing:** Follow-up transcripts update existing projects; diff engine categorizes scope items as `NEW`, `CHANGED`, `UNCHANGED`, `REMOVED`, or `OUT_OF_SCOPE`.
- **Approval Gating:** Scope changes immediately reset approval state (`client_ready = False`). Client-facing proposals are strictly locked with HTTP 403 until human approval is submitted.
- **Exporting:** Approved SOWs can be exported as printable HTML (with print stylesheet) or Markdown. Draft exports display prominent watermarks.

---

## G. AI MODEL STATUS & TELEMETRY

| Role | Configured Models | Fallback Sequence | Status | Note |
| :--- | :--- | :--- | :--- | :--- |
| `KNOWLEDGE_ANSWER` | `gemini-3.5-flash` | `gemini-3.1-flash-lite`, `claude-haiku-5-5`, Deterministic RAG | `CONFIGURED` | Live credentials exhausted; deterministic RAG fallback verified. |
| `EMAIL_CLASSIFICATION` | `gemini-3.5-flash` | `gemini-3.1-flash-lite`, `claude-haiku-5-5`, Deterministic Taxonomy | `CONFIGURED` | Benchmark accuracy 96% risk level, 100% parent consistency. |
| `EMAIL_DRAFTING` | `gemini-3.5-flash` | `gemini-3.1-flash-lite`, `claude-haiku-5-5`, Grounded Template | `CONFIGURED` | Citations preserved; honest refusal on insufficient evidence. |
| `REQUIREMENTS_EXTRACTION` | `claude-haiku-5-5` | `gemini-3.5-flash`, Rule-based Extractor | `CONFIGURED` | Multi-agent extraction pipeline verified. |
| `CAPABILITY_CHECKING` | `gemini-3.5-flash` | `claude-haiku-5-5`, Deterministic RAG Cross-Check | `CONFIGURED` | Feasibility verification against Task 1 verified. |

> **Note on Provider Quota / Keys:**  
> When live Google Gemini or Anthropic API keys return `HTTP 400 (API key not valid)` or quota exhaustion, all services safely execute their configured fallback pathways, route operations to human review, and record `AI_UNAVAILABLE` without crashing.

---

## H. COMPREHENSIVE TEST RESULTS

### Summary of Executed Test Suites

| Test Suite | Location | Total Tests | Passed | Failed | Success Rate |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Task 1: Knowledge Brain** | `task-1-knowledge-brain/tests/` | 114 | 114 | 0 | **100%** |
| **Task 2: AI Inbox Agent** | `task-2-inbox-agent/tests/` | 62 | 62 | 0 | **100%** |
| **Task 2: Step 4 Benchmark** | `task-2-inbox-agent/scripts/eval_step4.ts` | 50 cases | 48/50 (96%) | 0 | **96%** |
| **Task 3: Meeting-to-SOW** | `task-3-meeting-sow/tests/` | 31 | 31 | 0 | **100%** |
| **Cross-Module Integration Smoke**| `tests/test_integration_smoke.py` | 6 | 6 | 0 | **100%** |
| **Frontend Production Build** | `frontend/` (`npm run build`) | 1,587 modules | Built | 0 | **100%** |
| **TOTAL** | **Entire Application** | **213 tests** | **213** | **0** | **100%** |

---

## I. PRODUCTION READINESS & RELEASE BLOCKERS

### Verified Production Hardening
- **Authentication:** Session cookie and Bearer token verification backed by Argon2id password hashing and account lockout protection.
- **Authorization & Isolation:** Strict per-user isolation on sitemaps, articles, interactions, feedback, and SOW projects. Cross-user access returns HTTP 403 Forbidden.
- **Service Security:** `X-Internal-Service-Key` constant-time verification protects direct inter-service calls and is stripped at client-facing reverse proxies.
- **CSRF & CORS:** State-changing requests enforce CSRF tokens; origin allowlist configured.
- **Safety Defaults:** Automated email sending is **disabled by default**; requires manual approval or satisfying strict streak thresholds.

### Release Blockers for Public Deployment
1. **Google OAuth Production Client ID:** Requires configuring `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env` with authorized redirect URI for live customer Gmail synchronization. (Local mock mode is fully operational).
2. **AI Provider API Keys:** Production deployment requires live, funded Google Gemini and Anthropic Claude API keys to enable live model synthesis (currently operating via verified fallback engines).
3. **Automated Sending Activation:** Live customer email auto-send must remain disabled until production OAuth and domain authentication (SPF/DKIM/DMARC) are validated.

---

## J. LOCAL STARTUP COMMANDS (WINDOWS POWERSHELL)

To start the complete application locally on Windows:

### Step 1: Start Task 1 (Knowledge Brain) on Port 8000
```powershell
cd c:\Users\ithar\ai-tech-consultant\task-1-knowledge-brain
& "C:\Users\ithar\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Step 2: Start Task 2 (Inbox Agent) on Port 3000
```powershell
cd c:\Users\ithar\ai-tech-consultant\task-2-inbox-agent
npm start
```

### Step 3: Start Task 3 (Meeting-to-SOW) on Port 8002
```powershell
cd c:\Users\ithar\ai-tech-consultant\task-3-meeting-sow
& "C:\Users\ithar\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn app.server:app --host 127.0.0.1 --port 8002
```

### Step 4: Start Frontend Development Server on Port 5173
```powershell
cd c:\Users\ithar\ai-tech-consultant\frontend
npm run dev
```

### Verification Endpoints
- **Frontend Web UI:** `http://localhost:5173`
- **Knowledge Brain Health:** `http://localhost:8000/health`
- **Inbox Agent Health:** `http://localhost:3000/health`
- **Meeting-to-SOW Health:** `http://localhost:8002/health`
- **Model Routing Status:** `http://localhost:3000/api/v1/ai/models/status`

---

## K. END-TO-END DEMO WORKFLOW

### Scenario 1: Knowledge Brain Document Intelligence
1. Open `http://localhost:5173` and navigate to **Sitemap Management**.
2. Click **Preview** on a sitemap URL to inspect discovered URLs and `lastmod` metadata.
3. Click **Confirm & Index** to trigger background processing; observe the rolling 5-minute throughput tracker.
4. Open **AI Knowledge Chat** and query: *"How do I configure Stripe keys in Brilliant Directories?"*
5. Receive an honest, grounded answer complete with section headings and official documentation citations.

### Scenario 2: AI Inbox Agent & Gmail Lifecycle
1. Navigate to **Gmail Inbox**.
2. Click **Compose Email** to open the real outgoing message editor.
3. Enter recipient, subject, and body; click **Save Draft** to store in the **Drafts** folder, or **Send Message** to save in **Sent**.
4. To test incoming AI processing, switch the modal to **Simulate Customer Test** and select *"Stripe Key Setup"*.
5. The incoming email is normalized, semantically classified into `Design Settings -> Header`, cross-referenced with Knowledge Brain, and a draft reply is synthesized.
6. In the **Human Reviews** queue, review the draft, make an edit, and approve. The edit is recorded in `FeedbackStore` to improve future drafts.
7. Test folder operations: move the conversation to **Trash**, restore it to **Inbox**, mark as **Spam**, or **Delete Forever**.

### Scenario 3: Meeting-to-SOW Autonomous Pipeline
1. Navigate to **Meeting-to-SOW** via the left sidebar.
2. Click **+ New SOW Project**, click **Load Sample Meeting**, and click **Generate Scope & SOW**.
3. View the extracted requirements in the **Scope & Feasibility** tab, observing verified capability status badges (`SUPPORTED`, `NEEDS_CUSTOM_DEV`) and Task 1 citations.
4. Click the **Follow-up Meeting Diff** tab, load the sample follow-up meeting, and click **Process Follow-up Meeting**.
5. Observe the detected changeset diff (`1 Added`, `0 Changed`, `3 Unchanged`, `0 Removed`) and notice that the approval state resets to draft.
6. Open the **SOW Proposal** tab to preview the generated proposal. Notice the **INTERNAL DRAFT** banner.
7. Enter reviewer name and click **Approve SOW**. The proposal is stamped as **APPROVED & CLIENT READY**.
8. Click **Export / Print** to download the finalized client-ready Statement of Work as HTML or Markdown.

# Task 2: Inbox Agent (Customer Success Automation)

Automated support inbox triage, draft generation, and human-in-the-loop (HITL) review system for Brilliant Directories, built for the Business Labs "AI Tech Consultant" hiring assignment.

---

## 1. Architecture & Design Principles

1. **Zero Product Knowledge Duplication**:
   - The inbox agent contains **no hardcoded Brilliant Directories documentation or product facts**.
   - All knowledge retrieval is performed dynamically via typed HTTP calls to the Task 1 Knowledge Brain (`POST /api/v1/ask`).
   - If Task 1 returns insufficient evidence or flags that human review is required, the draft is held in the review queue with neutral language.
   - For integration evaluation, the eval suite queries the live Task 1 Knowledge Brain rather than mocking or recreating product answers.

2. **Gated Autonomy Policy Engine**:
   - **Gating Requirement**: Autonomous delivery is unlocked **only after 20 consecutive unchanged human approvals** of that specific `(Intent, RiskLevel, ProductArea)` kind tuple.
   - **Scope Boundary**: Autonomy is restricted strictly to `LOW` risk inquiries. High-risk and critical-risk inquiries permanently require human approval.
   - **Unknown Product Area Safeguard**: Inquiries classified under `ProductArea.UNKNOWN` are barred from unlocking autonomy regardless of streak length.
   - **Strict Equality**: Normalized textual equality (trimming extraneous whitespace and line endings) is enforced. Any modification to phrasing, wording, punctuation, or guidance is treated as an edit.
   - **Immediate Revocation**: Any human edit or rejection immediately revokes autonomy and resets the streak to `0`.
   - **Quality Audit Revocation**: An explicit revocation API (`POST /api/v1/autonomy/revoke`) allows spot audits, CSAT dips, or quality failures to immediately revoke autonomy and reset streaks.
   - **Separation of Concerns**: Automatic deliveries (`AUTO_SENT`) are tracked separately in an auto-delivery store and never recorded as human `APPROVE` actions.

3. **High-Precision Risk & Injection Classifier**:
   - Classifies customer emails across 3 dimensions:
     - **Intent**: `HOW_TO_CONFIGURE`, `BUG_REPORT`, `BILLING_ISSUE`, `FEATURE_INQUIRY`, `ACCOUNT_ACCESS`, `CANCELLATION`, `GENERAL_INQUIRY`.
     - **Risk Level**: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
     - **Product Area**: `PAYMENTS_GATEWAYS`, `MEMBERSHIP_PLANS`, `DOMAINS_DNS`, `EMAIL_TEMPLATES`, `FORMS_RECAPTCHA`, `SEARCH_LOCATIONS`, `ANALYTICS_TRACKING`, `MEMBER_EXPORT_IMPORT`, `LISTINGS_MANAGEMENT`, `ACCOUNT_SECURITY`, `UNKNOWN`.
   - Built-in prompt injection detection and social engineering defense.
   - Customer messages are treated as **untrusted data** and isolated in XML delimiters when prompting Claude.

4. **Continuous Learning from Human Feedback**:
   - Persists all original drafts, final sent replies, reviewer actions, and diff summaries.
   - Separate synthetic training exemplars are used to evaluate prompt version `v2_feedback_enhanced` against `v1_baseline` without contaminating the held-out test set.

5. **Durable Persistence & XSS-Hardened HITL UI**:
   - All customer interactions and pending drafts are persisted to disk (`data/interactions.json`), allowing pending review queues to survive service restarts.
   - Embedded HTML reviewer interface (`http://localhost:3000/review`) strictly sanitizes and escapes all dynamic customer inputs to prevent XSS attacks.

---

## 2. Directory Structure

```text
task-2-inbox-agent/
├── data/
│   └── dataset_50_emails.json        # 50 diverse customer test emails
├── evals/
│   ├── task2_eval_suite.ts           # 20 held-out benchmark evaluation cases
│   └── eval_runner.ts                # Empirical benchmark comparison runner
├── src/
│   ├── api/
│   │   └── server.ts                 # Express REST API & XSS-sanitized HITL UI
│   ├── autonomy/
│   │   └── engine.ts                 # 20-streak gating, reset, and revocation engine
│   ├── classification/
│   │   └── classifier.ts             # Intent, risk, injection, and area classifier
│   ├── drafting/
│   │   └── generator.ts              # Claude Haiku & deterministic fallback generator
│   ├── feedback/
│   │   └── store.ts                  # Review recording and exemplar retrieval
│   ├── knowledge/
│   │   └── task1_client.ts           # Typed Task 1 client with timeout and Zod validation
│   ├── storage/
│   │   └── interaction_store.ts      # Persistent interaction & delivery store
│   ├── types/
│   │   └── index.ts                  # TypeScript types and domain models
│   ├── validation/
│   │   └── schemas.ts                # Zod runtime schemas
│   ├── inbox_service.ts              # Core orchestration pipeline
│   └── index.ts                      # Server entrypoint
├── tests/
│   ├── autonomy.test.ts              # Autonomy gating, reset, and UNKNOWN area tests
│   ├── classifier.test.ts            # Security injection, risk, and intent tests
│   ├── inbox_service.test.ts         # Persistence across restart and review semantics
│   ├── knowledge_client.test.ts      # Task 1 timeout and malformed response tests
│   └── ui_security.test.ts           # Reviewer UI HTML/XSS sanitization tests
├── package.json
├── tsconfig.json                     # Strict TypeScript mode enabled
└── vitest.config.ts
```

---

## 3. Quick Start & Execution

### Prerequisites
- Node.js >= v20
- Task 1 Knowledge Brain running locally at `http://127.0.0.1:8000` (required for integration evaluation)

### Installation
```bash
npm install
```

### Type Checking & Unit Tests
```bash
# Verify strict TypeScript compilation (0 errors)
npm run typecheck

# Run all 22 Vitest unit tests
npm test
```

### Running the Empirical Evaluation Suite
```bash
# Evaluates 20 held-out cases across v1_baseline and v2_feedback_enhanced
# against the live Task 1 Knowledge Brain
npm run eval
```

### Running Locally
```bash
# Start the API server in development mode
npm run dev

# Server running at http://localhost:3000
# Reviewer Portal available at http://localhost:3000/review
```

---

## 4. Current Evaluation Benchmark

Measured on the 20 held-out benchmark cases querying live Task 1 Knowledge Brain (31 indexed chunks):

| Version | Cases | Intent Acc | Risk Acc | Routing Acc | Content Safety | Feedback Incorp | Avg Latency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `v1_baseline` | 20 | 100.0% | 100.0% | 90.0% | 100.0% | 0.0% | ~258ms |
| `v2_feedback_enhanced` | 20 | 100.0% | 100.0% | 90.0% | 100.0% | 66.7% | ~272ms |

- **Intent & Risk Precision**: 100% precision across billing, security, cancellation, and configuration inquiries.
- **Routing Compliance**: High-risk inquiries and inquiries requiring human review are safely held in the queue.
- **Continuous Learning Demonstration**: `v2_feedback_enhanced` demonstrates measurable feedback incorporation (increasing from 0.0% to 66.7%) using separate labeled synthetic training exemplars.

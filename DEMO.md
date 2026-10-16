# 10-Minute Video Demonstration Script

This walkthrough guides the evaluator through a structured <=10-minute live demo of the complete AI Tech Consultant platform.

---

### Phase 1: Introduction & Architecture Overview (0:00 – 0:30)
- **On Screen**: Camera on face / Introduction slide showing system architecture diagram.
- **Talking Points**:
  - Introduce myself and the problem: tech consultancies struggle with hallucinated scopes and inconsistent client communications on complex vertical SaaS platforms like Brilliant Directories.
  - Present the core design rule: **Task 1 is the single source of truth**. Tasks 2 and 3 duplicate zero platform knowledge, ensuring 100% consistency across support emails and technical SOWs.

---

### Phase 2: Task 1 — Grounded Knowledge Brain with Citations (0:30 – 2:00)
- **Action**: Open Swagger UI at `http://localhost:8000/docs`.
- **Demo Request 1 (Grounded Native Feature)**:
  - Query: `"How do I connect Stripe to accept recurring payments for member subscriptions?"`
  - Endpoint: `POST /api/v1/ask`
- **What to Highlight**:
  - Structured response returns `evidence_status: "STRONG"` and `is_known: true`.
  - Specific section citation: `Finance > Payment Gateways > Stripe`.
  - UI step guidance showing exact admin navigation path.
  - Calibrated evidence score without pseudo-metric inflation.

---

### Phase 3: Task 1 — Intentional Failure & Unknown Handling (2:00 – 3:30)
- **Demo Request 2 (Intentional Unknown Feature)**:
  - Query: `"How do I configure quantum teleportation cloud sync for directory listings?"`
  - Endpoint: `POST /api/v1/ask`
- **What to Highlight**:
  - Response returns `is_known: false`, `evidence_status: "NONE"`, and `citations: []`.
  - System refuses to hallucinate platform features.
  - Flags `needs_human_review: true` to prevent downstream autonomous errors.

---

### Phase 4: Task 2 — Inbox Agent & Guardrailed Autonomy (3:30 – 5:30)
- **Action**: Navigate to `http://localhost:3000/review` (HITL Review Dashboard).
- **Demo Flow**:
  1. **Ingest Low-Risk Inquiry**:
     - Client asks: `"Can I export our member list to CSV?"`
     - Agent queries Task 1 live, retrieves native `Export Member Data` documentation, and drafts an accurate response.
     - Note the current streak: `0/20 approvals`. Routed to the review dashboard.
  2. **Human Specialist Review**:
     - Specialist clicks **"Approve (Unchanged)"** -> Increments streak to `1/20`.
     - Specialist makes an edit and clicks **"Send with Edits"** -> Saves edit exemplar to `FeedbackStore`, resets streak to `0/20`.
  3. **High-Risk Guardrail (Financial/Refund Dispute)**:
     - Ingest an email demanding an immediate subscription chargeback.
     - Note that even if streak was 20, `riskLevel: HIGH` strictly forces `requiresHumanReview: true` and blocks auto-send.

---

### Phase 5: Task 3 — Meeting Transcript to Structured Scope (5:30 – 7:30)
- **Action**: Open Swagger at `http://localhost:8002/docs` or run CLI script.
- **Demo Request**:
  - Submit initial scoping transcript:
    `"Client wants Stripe subscription billing ($0 custom dev), 25-mile radius search ($0 custom dev), and a custom CRM webhook bridge to push leads to external HubSpot."`
- **What to Highlight**:
  - Requirements Analyst extracts structured items with stable IDs (`REQ-01`, `REQ-02`, `REQ-03`).
  - Product Capability Checker queries Task 1 live:
    - Stripe -> `NATIVE` (0.0h custom dev).
    - Radius Search -> `NATIVE` (0.0h custom dev).
    - Custom CRM Webhook -> `CUSTOM` (estimated via PERT 3-point: 18.0h).
  - Drafted SOW watermarked `PENDING HUMAN APPROVAL (NOT CLIENT-READY)`.

---

### Phase 6: Task 3 — Follow-Up Meeting Diffing & Human Approval (7:30 – 9:00)
- **Demo Request (Follow-up Call)**:
  - Client says: `"On the CRM sync, we changed our mind: it should now only send new members one-way. Also, remove the radius search for phase 1."`
- **What to Highlight**:
  - Diff Engine marks Radius Search as `REMOVED`.
  - CRM Integration marked as `CHANGED` with preserved constraint clause: `"one-way only and new members"`.
  - Re-calculates PERT hours automatically.
  - Snapshot saved in structured `version_history`.
- **Human Approval Gate**:
  - Call `POST /api/v1/projects/{id}/approve` with reviewer name `"Lead Solutions Architect"`.
  - SOW updates status to `CLIENT-READY` with approval timestamp.

---

### Phase 7: Architecture, Evals & Wrap-Up (9:00 – 10:00)
- **On Screen**: Summary table from `EVALS.md`.
- **Talking Points**:
  - Review 100% test pass across all 3 services:
    - Task 1: 35 unit tests
    - Task 2: 23 unit tests + 20 held-out benchmark evaluations
    - Task 3: 21 unit tests + 20 held-out meeting evaluations
    - Cross-service: 6 integration smoke tests
  - Recap why this architecture wins: zero knowledge duplication, strict autonomy safety gates, and deterministic contractual diffing.

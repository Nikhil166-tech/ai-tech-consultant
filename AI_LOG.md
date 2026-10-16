# AI Interaction & Development History Log

Authentic pair-programming records from Antigravity development sessions for the Business Labs capstone.

---

### 1. Semantic Embeddings vs. Hashed Lexical Vectors (Task 1)
- **Prompt**: *"Replace SemanticFeatureEmbedding, which currently uses hashed lexical features, with a genuine learned semantic embedding provider... Do not call hashed token/trigram vectors semantic embeddings."*
- **Proposed**: Lightweight hash-based MD5 vectorizer generating pseudo-dense 128-d vectors.
- **Accepted / Changed**: Replaced with `fastembed` (`BAAI/bge-small-en-v1.5`, 384-d dense learned embeddings) and automatic SQLite dimension migration.
- **Why**: Hashed lexical vectors cannot recognize semantic synonyms (e.g., "payment gateway" vs "credit card billing") and mislead confidence calibration.

### 2. Eliminating Knowledge Duplication in Eval Client (Task 2)
- **Prompt**: *"Task 2 duplicates Task 1 knowledge inside the eval runner. EvalKnowledgeClient hardcodes Stripe, recurring payments, SSL, domains, email templates, reCAPTCHA, badges... That contradicts the README's 'zero product knowledge duplication' statement."*
- **Proposed**: Hardcoded dictionary mock inside `EvalKnowledgeClient` returning static capability answers.
- **Accepted / Changed**: Deleted all feature dictionaries. Connected `EvalKnowledgeClient` live to Task 1 HTTP API.
- **Why**: Restores Task 1 as the single source of truth and prevents synthetic false-positive evaluation passes.

### 3. Strict Risk Tier Gating on Autonomy Engine (Task 2)
- **Prompt**: *"In AutonomyEngine.recordHumanReview(), allow autonomyEnabled=true only when the kind's risk level is LOW and product area is not UNKNOWN. HIGH, CRITICAL, and MEDIUM kinds must never enter an enabled autonomy state, even after 20 approvals."*
- **Proposed**: Allowed any interaction kind to achieve auto-send once its approval streak reached 20.
- **Accepted / Changed**: Enforced strict safety gate: `if (kind.riskLevel !== "LOW" || kind.productArea === "UNKNOWN") return false;`.
- **Why**: Protects against high-liability autonomous transmissions (e.g., chargebacks, security credentials, database outages).

### 4. Preserving Changed Constraint Details in SOW Diffing (Task 3)
- **Prompt**: *"Preserve actual changed requirement details from follow-up meetings. If the client says: 'CRM sync should now only send new members one-way', the updated requirement description/change metadata must contain the new constraint... Do not merely set status=CHANGED with a generic description."*
- **Proposed**: Marked updated requirements as `CHANGED` with a generic diff summary `"Requirement modified in follow-up meeting"`.
- **Accepted / Changed**: Parsed transcript constraint clauses and updated requirement `description` and `change_reason` explicitly.
- **Why**: Guarantees contractual precision in scope change orders and eliminates ambiguity in client-facing deliverables.

### 5. Pure Zero-Knowledge Capability Classification (Task 3)
- **Prompt**: *"Remove the remaining duplicated Brilliant Directories knowledge from ProductCapabilityCheckerAgent._classify_deterministic. The deterministic classifier must contain NO feature-specific lists such as Stripe, billing, search radius, reCAPTCHA, badges, exports, CRM, HubSpot... Task 1 remains the sole source of product truth."*
- **Proposed**: Checked requirement titles against hardcoded feature strings (`if "stripe" in req: return NATIVE`).
- **Accepted / Changed**: Replaced with generic linguistic analysis against Task 1 documentation evidence (admin/built-in -> NATIVE, unverified -> UNKNOWN).
- **Why**: Ensures Task 3 derives feasibility purely from retrieved Task 1 evidence without embedded product biases.

### 6. Rejected Suggestion: Static Guidance Substring Matching (Task 3)
- **Prompt**: Detect ambiguous Task 1 evidence to escalate requirements to `UNKNOWN`.
- **Proposed**: Matched substring `"unverified"` in Task 1 answer bodies to trigger `CapabilityStatus.UNKNOWN`.
- **Rejected & Changed**: **REJECTED**. Task 1 includes a static UI guidance footer on all responses (`UI Step Guidance: Refer to '[Visual analysis unverified] Preserved DOM context'`). Substring matching `"unverified"` caused valid native features (e.g., Member Profile Badges) to prematurely fail into `UNKNOWN`.
- **Why**: Matched static footer boilerplate rather than actual platform capability text. Replaced with genuine uncertainty phrases (`"insufficient"`, `"cannot verify"`).

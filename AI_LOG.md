# AI Interaction & Development History Log

This log records authentic development interactions, design changes, and architectural corrections during the Antigravity pair-programming sessions for the Business Labs capstone.

---

### Entry 1: Genuine Semantic Embeddings vs. Hashed Lexical Vectors (Task 1)
- **Prompt / Request**: "Replace SemanticFeatureEmbedding, which currently uses hashed lexical features, with a genuine learned semantic embedding provider... Do not call hashed token/trigram vectors semantic embeddings."
- **What Antigravity Proposed**: A lightweight hash-based vectorizer using MD5 token hashing to generate 128-dimensional vectors.
- **What was Accepted or Changed**: Replaced the pseudo-vectorizer with `fastembed` running `BAAI/bge-small-en-v1.5` (384-dimensional dense learned embeddings) and added automatic dimension schema migration.
- **Why**: Hashed lexical vectors lack genuine semantic similarity (e.g., failing on synonyms like "payment gateway" vs "credit card processing") and mislead downstream confidence scoring.

---

### Entry 2: Eliminating Knowledge Duplication in Eval Client (Task 2)
- **Prompt / Request**: "Task 2 duplicates Task 1 knowledge inside the eval runner. EvalKnowledgeClient hardcodes Stripe, recurring payments, SSL, domains, email templates, reCAPTCHA, badges... That contradicts the README's 'zero product knowledge duplication' statement."
- **What Antigravity Proposed**: Created an `EvalKnowledgeClient` fallback containing hardcoded dictionary lookups for Brilliant Directories platform features.
- **What was Accepted or Changed**: Deleted all hardcoded feature dictionaries. Re-wired `EvalKnowledgeClient` to query Task 1 live over HTTP, returning `NONE` when features are unindexed.
- **Why**: Restores Task 1 as the single source of product truth and prevents false-positive benchmark passes.

---

### Entry 3: Strict Risk Gating on the Autonomy Engine (Task 2)
- **Prompt / Request**: "In AutonomyEngine.recordHumanReview(), allow autonomyEnabled=true only when the kind's risk level is LOW and product area is not UNKNOWN. HIGH, CRITICAL, and MEDIUM kinds must never enter an enabled autonomy state, even after 20 approvals."
- **What Antigravity Proposed**: Allowed any interaction kind to achieve auto-send once its unchanged approval streak reached 20.
- **What was Accepted or Changed**: Added strict risk tier gating: `if (kind.riskLevel !== "LOW" || kind.productArea === "UNKNOWN") return false;`.
- **Why**: Prevents high-liability emails (e.g., refund demands, credential exposures, system outages) from ever being sent autonomously.

---

### Entry 4: Preserving Changed Constraint Details in SOW Diffing (Task 3)
- **Prompt / Request**: "Preserve actual changed requirement details from follow-up meetings. If the client says: 'CRM sync should now only send new members one-way', the updated requirement description/change metadata must contain the new constraint... Do not merely set status=CHANGED with a generic description."
- **What Antigravity Proposed**: Marked updated requirements as `CHANGED` with a generic diff summary `"Requirement modified in follow-up meeting"`.
- **What was Accepted or Changed**: Extracted the exact constraint clause from the transcript and updated both the requirement `description` and `change_reason`.
- **Why**: Preserves precise contractual fidelity in SOW change orders and eliminates scope ambiguity.

---

### Entry 5: Pure Zero-Knowledge Capability Classification (Task 3)
- **Prompt / Request**: "Remove the remaining duplicated Brilliant Directories knowledge from ProductCapabilityCheckerAgent._classify_deterministic. The deterministic classifier must contain NO feature-specific lists such as Stripe, billing, search radius, reCAPTCHA, badges, exports, CRM, HubSpot... Task 1 remains the sole source of product truth."
- **What Antigravity Proposed**: Classified requirements using hardcoded feature lists (`if "stripe" in req: return NATIVE`).
- **What was Accepted or Changed**: Replaced feature lists with generic language classification against Task 1 evidence (e.g., "built-in", "admin portal" -> NATIVE; "developer hub", "api endpoints" -> CUSTOM; unverified -> UNKNOWN).
- **Why**: Eliminates duplicated platform facts and guarantees Task 3 derives platform feasibility purely from Task 1 documentation evidence.

---

### Entry 6 (Rejected Suggestion): Static UI Footer String Matching
- **Prompt / Request**: Implement uncertainty detection when Task 1 evidence is ambiguous.
- **What Antigravity Proposed**: Added a check for `"unverified"` in Task 1 answer strings to trigger `CapabilityStatus.UNKNOWN`.
- **What was Rejected and Changed**: **REJECTED and fixed**. Task 1 includes a static UI guidance footer on all responses (`UI Step Guidance: Refer to '[Visual analysis unverified] Preserved DOM context: Support Center'`). Checking for substring `"unverified"` caused valid native features (e.g., Member Profile Badges) to prematurely fail into `UNKNOWN`.
- **Why**: The check matched the static guidance footer rather than the actual documentation feasibility text. Removed `"unverified"` and targeted genuine uncertainty phrases (`"insufficient"`, `"cannot verify"`, `"is ambiguous"`).

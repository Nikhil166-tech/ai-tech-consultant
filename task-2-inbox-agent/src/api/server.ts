import express, { Request, Response } from "express";
import cors from "cors";
import { InboxService } from "../inbox_service.js";
import { CustomerEmailSchema, ReviewSubmissionSchema, AutonomyRevocationSchema } from "../validation/schemas.js";

export function createServer(inboxService?: InboxService) {
  const app = express();
  app.use(cors());
  app.use(express.json());

  const service = inboxService || new InboxService();

  // Health check
  app.get("/health", (_req: Request, res: Response): void => {
    res.json({
      status: "healthy",
      service: "task-2-inbox-agent",
      timestamp: new Date().toISOString()
    });
  });

  // 1. Process customer email
  app.post("/api/v1/emails/process", async (req: Request, res: Response): Promise<void> => {
    try {
      const parsed = CustomerEmailSchema.safeParse(req.body);
      if (!parsed.success) {
        res.status(400).json({
          error: "Invalid customer email payload",
          details: parsed.error.errors.map((e) => `${e.path.join(".")}: ${e.message}`)
        });
        return;
      }

      const version = req.query.version === "v2" ? "v2_feedback_enhanced" : "v1_baseline";
      const result = await service.processEmail(parsed.data, version);
      res.json(result);
    } catch (err: any) {
      res.status(500).json({ error: err?.message || "Internal processing error" });
    }
  });

  // 2. Fetch pending reviews
  app.get("/api/v1/inbox/pending", (_req: Request, res: Response): void => {
    const pending = service.getPendingReviews();
    res.json({ count: pending.length, pending });
  });

  // 3. Submit human review
  app.post("/api/v1/inbox/review", (req: Request, res: Response): void => {
    try {
      const { interactionId, action, reviewerId, finalReply, notes } = req.body;

      if (!interactionId || typeof interactionId !== "string") {
        res.status(400).json({ error: "interactionId string is required" });
        return;
      }

      const parseResult = ReviewSubmissionSchema.safeParse({ action, reviewerId, finalReply, notes });
      if (!parseResult.success) {
        res.status(400).json({
          error: "Invalid review submission",
          details: parseResult.error.errors.map((e) => `${e.path.join(".")}: ${e.message}`)
        });
        return;
      }

      const result = service.submitReview(interactionId, parseResult.data);
      res.json(result);
    } catch (err: any) {
      res.status(400).json({ error: err?.message || "Review submission failed" });
    }
  });

  // 4. Autonomy status for a kind
  app.get("/api/v1/autonomy/status", (req: Request, res: Response): void => {
    const kindKey = req.query.kindKey as string;
    if (!kindKey) {
      res.status(400).json({ error: "kindKey query parameter is required" });
      return;
    }
    const state = service.autonomyEngine.getState(kindKey);
    res.json(state);
  });

  // 5. Explicit quality revocation pathway
  app.post("/api/v1/autonomy/revoke", (req: Request, res: Response): void => {
    const parseResult = AutonomyRevocationSchema.safeParse(req.body);
    if (!parseResult.success) {
      res.status(400).json({
        error: "Invalid revocation payload",
        details: parseResult.error.errors.map((e) => `${e.path.join(".")}: ${e.message}`)
      });
      return;
    }

    const { kindKey, reason, revokedBy } = parseResult.data;
    const updatedState = service.revokeAutonomy(kindKey, reason, revokedBy);
    res.json({
      success: true,
      message: `Autonomy revoked for '${kindKey}'`,
      state: updatedState
    });
  });

  // Embedded HITL Review UI (Strictly hardened against XSS)
  app.get("/review", (_req: Request, res: Response): void => {
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Brilliant Directories - HITL Review Portal</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }
    h1 { margin-top: 0; font-size: 22px; color: #38bdf8; }
    .card { background: #1e293b; border-radius: 8px; border: 1px solid #334155; padding: 18px; margin-bottom: 18px; }
    .meta { font-size: 13px; color: #94a3b8; margin-bottom: 10px; }
    .body-box { background: #0f172a; border-radius: 4px; padding: 12px; font-family: monospace; font-size: 13px; white-space: pre-wrap; margin: 8px 0; border: 1px solid #334155; }
    textarea { width: 100%; min-height: 120px; background: #0f172a; color: #f8fafc; border: 1px solid #475569; border-radius: 4px; padding: 10px; font-family: sans-serif; box-sizing: border-box; }
    .actions { display: flex; gap: 10px; margin-top: 12px; }
    button { padding: 8px 16px; border: none; border-radius: 4px; font-weight: 600; cursor: pointer; }
    .btn-approve { background: #10b981; color: white; }
    .btn-edit { background: #3b82f6; color: white; }
    .btn-reject { background: #ef4444; color: white; }
    .btn-revoke { background: #f59e0b; color: white; margin-left: auto; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; margin-right: 6px; }
    .badge-risk-LOW { background: #065f46; color: #34d399; }
    .badge-risk-HIGH, .badge-risk-CRITICAL { background: #7f1d1d; color: #f87171; }
  </style>
</head>
<body>
  <h1>Brilliant Directories Inbox Agent - Human Review Queue</h1>
  <div id="queue-container">Loading pending drafts...</div>

  <script>
    function escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    async function loadQueue() {
      const container = document.getElementById('queue-container');
      try {
        const res = await fetch('/api/v1/inbox/pending');
        const data = await res.json();
        if (data.count === 0) {
          container.innerHTML = '<div class="card"><p>No pending drafts awaiting review.</p></div>';
          return;
        }

        container.innerHTML = data.pending.map(item => {
          const kindKey = item.classification.kind.key;
          const riskLevel = item.classification.kind.riskLevel;
          return \`
            <div class="card" id="card-\${escapeHtml(item.id)}">
              <div class="meta">
                <span class="badge badge-risk-\${escapeHtml(riskLevel)}">\${escapeHtml(riskLevel)}</span>
                <strong>\${escapeHtml(kindKey)}</strong> | Sender: \${escapeHtml(item.email.senderEmail)}
              </div>
              <p><strong>Customer Subject:</strong> \${escapeHtml(item.email.subject)}</p>
              <div class="body-box">\${escapeHtml(item.email.body)}</div>
              <p><strong>Proposed AI Draft Reply:</strong></p>
              <textarea id="reply-\${escapeHtml(item.id)}">\${escapeHtml(item.draft.body)}</textarea>
              <div class="actions">
                <button class="btn-approve" onclick="handleAction('\${escapeHtml(item.id)}', 'APPROVE')">Approve (Unchanged)</button>
                <button class="btn-edit" onclick="handleAction('\${escapeHtml(item.id)}', 'EDIT')">Send with Edits</button>
                <button class="btn-reject" onclick="handleAction('\${escapeHtml(item.id)}', 'REJECT')">Reject Draft</button>
                <button class="btn-revoke" onclick="revokeKind('\${escapeHtml(kindKey)}')">Audit Revoke Autonomy</button>
              </div>
            </div>
          \`;
        }).join('');
      } catch (err) {
        container.innerHTML = '<p style="color: #ef4444;">Error loading review queue.</p>';
      }
    }

    async function handleAction(id, action) {
      const textarea = document.getElementById('reply-' + id);
      const finalReply = textarea ? textarea.value : '';

      try {
        const res = await fetch('/api/v1/inbox/review', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            interactionId: id,
            action,
            reviewerId: 'specialist_ui',
            finalReply: action === 'EDIT' ? finalReply : undefined
          })
        });
        const respData = await res.json();
        if (!res.ok) {
          alert('Error: ' + (respData.error || 'Failed'));
          return;
        }
        document.getElementById('card-' + id).remove();
        alert('Action ' + action + ' recorded successfully.');
      } catch (err) {
        alert('Request failed: ' + err.message);
      }
    }

    async function revokeKind(kindKey) {
      const reason = prompt('Enter quality-audit revocation reason for ' + kindKey + ':', 'Quality score dropped in spot audit');
      if (!reason) return;

      try {
        const res = await fetch('/api/v1/autonomy/revoke', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ kindKey, reason, revokedBy: 'lead_specialist' })
        });
        const data = await res.json();
        alert('Autonomy revoked successfully. Current streak: ' + data.state.unchangedStreak);
      } catch (err) {
        alert('Revocation failed: ' + err.message);
      }
    }

    loadQueue();
  </script>
</body>
</html>`;
    res.setHeader("Content-Type", "text/html");
    res.send(html);
  });

  return app;
}

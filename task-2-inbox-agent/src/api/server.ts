import express, { Request, Response } from "express";
import cors from "cors";
import { InboxService } from "../inbox_service.js";
import { CustomerEmail, ReviewAction } from "../types/index.js";

export function createServer(inboxService: InboxService) {
  const app = express();
  app.use(cors());
  app.use(express.json());

  // 1. Process email
  app.post("/api/v1/emails/process", async (req: Request, res: Response) => {
    try {
      const email = req.body as CustomerEmail;
      if (!email.id || !email.subject || !email.body) {
        return res.status(400).json({ error: "Missing required email fields (id, subject, body)" });
      }
      const version = req.query.version === "v2" ? "v2_feedback_enhanced" : "v1_baseline";
      const result = await inboxService.processEmail(email, version);
      return res.json(result);
    } catch (err: any) {
      return res.status(500).json({ error: err.message || "Failed to process email" });
    }
  });

  // 2. Pending human review queue
  app.get("/api/v1/inbox/pending", (_req: Request, res: Response) => {
    const pending = inboxService.getPendingDrafts();
    return res.json(pending);
  });

  // 3. Human Review Action (Approve / Edit / Reject)
  app.post("/api/v1/inbox/review", (req: Request, res: Response) => {
    try {
      const { emailId, action, finalReply, reviewerId, notes } = req.body;
      if (!emailId || !action) {
        return res.status(400).json({ error: "Missing emailId or action" });
      }
      const record = inboxService.reviewDraft(
        emailId,
        action as ReviewAction,
        finalReply,
        reviewerId || "reviewer_operator",
        notes
      );
      return res.json(record);
    } catch (err: any) {
      return res.status(404).json({ error: err.message });
    }
  });

  // 4. Autonomy Status
  app.get("/api/v1/autonomy/status", (req: Request, res: Response) => {
    const kindKey = req.query.kindKey as string | undefined;
    if (kindKey) {
      return res.json(inboxService.autonomyEngine.getState(kindKey));
    }
    const storeData = inboxService.feedbackStore.getHistory();
    const metrics = inboxService.feedbackStore.computeMetrics();
    return res.json({ metrics, historyCount: storeData.length });
  });

  // 5. Minimal HITL Review UI (Clean HTML/JS)
  app.get("/review", (_req: Request, res: Response) => {
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>AI Tech Consultant - HITL Inbox Review</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }
    h1 { margin-top: 0; color: #38bdf8; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
    .btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-weight: 600; margin-right: 8px; }
    .btn-approve { background: #10b981; color: white; }
    .btn-edit { background: #3b82f6; color: white; }
    .btn-reject { background: #ef4444; color: white; }
    textarea { width: 100%; height: 120px; background: #0f172a; color: #f8fafc; border: 1px solid #475569; border-radius: 4px; padding: 8px; }
    .tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; background: #334155; margin-right: 6px; }
    .tag-risk-LOW { background: #065f46; color: #6ee7b7; }
    .tag-risk-HIGH { background: #7f1d1d; color: #fca5a5; }
    .tag-risk-CRITICAL { background: #881337; color: #fda4af; }
  </style>
</head>
<body>
  <h1>HITL Customer Inbox Review</h1>
  <p>Human-in-the-Loop review dashboard. Approving without changes increments the kind's autonomy streak. Editing or rejecting instantly revokes autonomy.</p>
  <div id="queue">Loading pending drafts...</div>
  <script>
    async function loadQueue() {
      const res = await fetch("/api/v1/inbox/pending");
      const drafts = await res.json();
      const container = document.getElementById("queue");
      if (drafts.length === 0) {
        container.innerHTML = "<p>No pending drafts in queue. All clear!</p>";
        return;
      }
      container.innerHTML = drafts.map(d => \`
        <div class="card" id="card-\${d.email.id}">
          <h3>\${d.email.subject} <span class="tag tag-risk-\${d.draft.autoSendEligible ? 'LOW' : 'HIGH'}">\${d.kindKey}</span></h3>
          <p><strong>From:</strong> \${d.email.senderEmail}</p>
          <p><strong>Customer Message:</strong> \${d.email.body}</p>
          <label><strong>Generated AI Draft:</strong></label>
          <textarea id="reply-\${d.email.id}">\${d.draft.body}</textarea>
          <div style="margin-top: 12px;">
            <button class="btn btn-approve" onclick="review('\${d.email.id}', 'APPROVE')">Approve & Send (Unchanged)</button>
            <button class="btn btn-edit" onclick="review('\${d.email.id}', 'EDIT')">Send with Edits</button>
            <button class="btn btn-reject" onclick="review('\${d.email.id}', 'REJECT')">Reject Draft</button>
          </div>
        </div>
      \`).join("");
    }
    async function review(emailId, action) {
      const finalReply = document.getElementById("reply-" + emailId).value;
      await fetch("/api/v1/inbox/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ emailId, action, finalReply })
      });
      loadQueue();
    }
    loadQueue();
  </script>
</body>
</html>`;
    return res.send(html);
  });

  return app;
}

import express, { Request, Response } from "express";
import cors from "cors";
import path from "path";
import fs from "fs";
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

  // Proxy Task 1 Knowledge Brain routes when accessed through unified server (e.g. port 3000)
  const task1Url = process.env.TASK1_URL || "http://localhost:8000";
  const task1Prefixes = [
    "/api/v1/sitemaps",
    "/api/v1/refresh-runs",
    "/api/v1/quarantine",
    "/api/v1/health-observations",
    "/api/v1/settings",
    "/api/v1/auth",
    "/api/v1/ask",
    "/api/v1/articles"
  ];

  for (const prefix of task1Prefixes) {
    app.all(`${prefix}*`, async (req: Request, res: Response): Promise<void> => {
      try {
        const targetUrl = `${task1Url}${req.originalUrl}`;
        const headers: Record<string, string> = {};
        if (req.headers["content-type"]) {
          headers["Content-Type"] = req.headers["content-type"] as string;
        } else if (["POST", "PUT", "PATCH"].includes(req.method)) {
          headers["Content-Type"] = "application/json";
        }
        if (req.headers.cookie) headers["Cookie"] = req.headers.cookie as string;
        if (req.headers.authorization) headers["Authorization"] = req.headers.authorization as string;

        const response = await fetch(targetUrl, {
          method: req.method,
          headers,
          body: ["POST", "PUT", "PATCH"].includes(req.method) ? JSON.stringify(req.body) : undefined
        });

        res.status(response.status);
        const setCookie = response.headers.get("set-cookie");
        if (setCookie) res.setHeader("set-cookie", setCookie);

        const contentType = response.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
          const data = await response.json();
          res.json(data);
        } else {
          const text = await response.text();
          res.send(text);
        }
      } catch (err: any) {
        res.status(502).json({ error: `Failed to proxy to Task 1 Knowledge Brain at ${task1Url}: ${err.message}` });
      }
    });
  }

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

  // 6. Label-based autonomy status & streaks
  app.get("/api/v1/autonomy/labels", (_req: Request, res: Response): void => {
    const states = service.autonomyEngine.getAllLabelStates();
    res.json({ count: states.length, labels: states });
  });

  app.put("/api/v1/autonomy/labels/threshold", (req: Request, res: Response): void => {
    const { labelKey, threshold } = req.body;
    if (!labelKey || typeof threshold !== "number") {
      res.status(400).json({ error: "labelKey string and threshold number are required" });
      return;
    }
    const updated = service.autonomyEngine.setLabelThreshold(labelKey, threshold);
    res.json(updated);
  });

  app.put("/api/v1/autonomy/labels/toggle", (req: Request, res: Response): void => {
    const { labelKey, disabled } = req.body;
    if (!labelKey || typeof disabled !== "boolean") {
      res.status(400).json({ error: "labelKey string and disabled boolean are required" });
      return;
    }
    const updated = service.autonomyEngine.setLabelDisabled(labelKey, disabled);
    res.json(updated);
  });

  // 7. Global autonomy settings & emergency stop
  app.get("/api/v1/autonomy/settings", (_req: Request, res: Response): void => {
    res.json(service.autonomyEngine.getGlobalSettings());
  });

  app.put("/api/v1/autonomy/settings", (req: Request, res: Response): void => {
    const updated = service.autonomyEngine.updateGlobalSettings(req.body);
    res.json(updated);
  });

  app.post("/api/v1/autonomy/emergency-stop", (req: Request, res: Response): void => {
    const { enabled } = req.body;
    const isStop = typeof enabled === "boolean" ? enabled : true;
    service.autonomyEngine.setEmergencyStop(isStop);
    res.json({
      emergencyStop: isStop,
      message: isStop ? "EMERGENCY STOP ACTIVATED: All automated email sending is disabled." : "Emergency stop deactivated."
    });
  });

  // 8. Classification Taxonomy management
  app.get("/api/v1/taxonomy", (_req: Request, res: Response): void => {
    res.json(service.classifier.getTaxonomy());
  });

  app.put("/api/v1/taxonomy", (req: Request, res: Response): void => {
    if (!Array.isArray(req.body)) {
      res.status(400).json({ error: "Taxonomy payload must be an array of TaxonomyItem objects" });
      return;
    }
    service.classifier.updateTaxonomy(req.body);
    res.json({ success: true, count: req.body.length, taxonomy: service.classifier.getTaxonomy() });
  });

  // 9. Gmail Integration Endpoints
  app.get("/api/v1/gmail/status", (_req: Request, res: Response): void => {
    res.json(service.gmailClient.getStatus());
  });

  app.get("/api/v1/gmail/auth-url", (_req: Request, res: Response): void => {
    try {
      if (!service.gmailClient.isConfigured()) {
        res.status(400).json({
          error: "Google OAuth credentials not configured",
          message: "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env to enable real Gmail OAuth."
        });
        return;
      }
      const url = service.gmailClient.getAuthorizationUrl();
      res.json({ url });
    } catch (err: any) {
      res.status(500).json({ error: err?.message || "Failed to generate authorization URL" });
    }
  });

  app.get("/api/v1/gmail/callback", async (req: Request, res: Response): Promise<void> => {
    const code = req.query.code as string;
    if (!code) {
      res.status(400).json({ error: "Authorization code missing in callback query" });
      return;
    }
    try {
      await service.gmailClient.exchangeCodeForTokens(code);
      res.send(`
        <html>
          <body style="font-family: sans-serif; text-align: center; padding-top: 50px; background: #0f172a; color: #f8fafc;">
            <h2 style="color: #10b981;">Gmail Connected Successfully!</h2>
            <p>You can close this window and return to the application.</p>
            <script>setTimeout(() => window.close(), 2500);</script>
          </body>
        </html>
      `);
    } catch (err: any) {
      res.status(500).send(`<h2>Connection Failed: ${err?.message}</h2>`);
    }
  });

  app.post("/api/v1/gmail/disconnect", async (_req: Request, res: Response): Promise<void> => {
    await service.gmailClient.disconnect();
    res.json({ success: true, message: "Gmail account disconnected" });
  });

  app.post("/api/v1/gmail/mock-connect", (req: Request, res: Response): void => {
    const email = req.body.email || "demo.support@brilliantdirectories.com";
    const name = req.body.name || "BD Demo Support";
    service.gmailClient.connectMockAccount(email, name);
    res.json({ success: true, status: service.gmailClient.getStatus() });
  });

  app.post("/api/v1/gmail/sync", async (req: Request, res: Response): Promise<void> => {
    try {
      const maxCount = req.body.maxCount ? parseInt(req.body.maxCount, 10) : 20;
      const result = await service.syncGmail(maxCount);
      res.json(result);
    } catch (err: any) {
      res.status(500).json({ error: err?.message || "Gmail sync failed" });
    }
  });

  app.post("/api/v1/emails/:interactionId/send-gmail", async (req: Request, res: Response): Promise<void> => {
    try {
      const interactionId = Array.isArray(req.params.interactionId) ? req.params.interactionId[0] : req.params.interactionId;
      const result = await service.sendApprovedEmailViaGmail(interactionId);
      res.json(result);
    } catch (err: any) {
      res.status(400).json({ error: err?.message || "Failed to send email via Gmail" });
    }
  });

  // 10. Feedback metrics & interactions history
  app.get("/api/v1/feedback/metrics", (req: Request, res: Response): void => {
    const key = req.query.key as string | undefined;
    res.json(service.feedbackStore.computeMetrics(key));
  });

  app.get("/api/v1/feedback/history", (req: Request, res: Response): void => {
    const key = req.query.key as string | undefined;
    res.json(service.feedbackStore.getHistory(key));
  });

  app.get("/api/v1/inbox/interactions", (_req: Request, res: Response): void => {
    res.json(service.interactionStore.getAllInteractions());
  });

  // 11. Gemini API Configuration & Verification
  app.get("/api/v1/settings/gemini", (_req: Request, res: Response): void => {
    const key = process.env.GEMINI_API_KEY || (service.draftGenerator.apiKey && !service.draftGenerator.apiKey.startsWith("sk-ant-") ? service.draftGenerator.apiKey : "");
    const maskedKey = key ? `${key.slice(0, 6)}...${key.slice(-4)}` : "";
    res.json({
      apiKeyConfigured: Boolean(key),
      maskedKey,
      model: process.env.GEMINI_MODEL || service.draftGenerator.model || "gemini-3.5-flash"
    });
  });

  app.post("/api/v1/settings/gemini", async (req: Request, res: Response): Promise<void> => {
    try {
      const apiKey = (req.body.apiKey || "").trim();
      const model = (req.body.model || process.env.GEMINI_MODEL || "gemini-3.5-flash").trim();

      if (!apiKey) {
        res.status(400).json({ error: "Gemini API key is required" });
        return;
      }

      // Verify key by testing generateContent
      let verified = false;
      let verificationMessage = "API key saved successfully";
      try {
        const testRes = await fetch(
          `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              contents: [{ role: "user", parts: [{ text: "Hello, reply with 1 word." }] }],
              generationConfig: { maxOutputTokens: 5 }
            })
          }
        );
        if (testRes.ok) {
          verified = true;
          verificationMessage = "Google Gemini API key verified and working!";
        } else {
          const errBody = await testRes.text().catch(() => "");
          verificationMessage = `Key saved, but Gemini verification returned HTTP ${testRes.status}: ${errBody}`;
        }
      } catch (err: any) {
        verificationMessage = `Key saved, but verification test failed: ${err.message}`;
      }

      // Update runtime environment & draftGenerator
      process.env.GEMINI_API_KEY = apiKey;
      process.env.GEMINI_MODEL = model;
      service.draftGenerator.apiKey = apiKey;
      service.draftGenerator.model = model;

      // Persist to .env files
      const envPaths = [
        path.resolve(process.cwd(), ".env"),
        path.resolve(process.cwd(), "../.env"),
        path.resolve(process.cwd(), "../task-1-knowledge-brain/.env"),
        path.resolve(process.cwd(), "../task-2-inbox-agent/.env"),
        path.resolve(process.cwd(), "../task-3-meeting-sow/.env")
      ];

      for (const p of envPaths) {
        try {
          if (fs.existsSync(p)) {
            let content = fs.readFileSync(p, "utf-8");
            if (content.includes("GEMINI_API_KEY=")) {
              content = content.replace(/GEMINI_API_KEY=.*/g, `GEMINI_API_KEY=${apiKey}`);
            } else {
              content += `\nGEMINI_API_KEY=${apiKey}\n`;
            }
            if (content.includes("GEMINI_MODEL=")) {
              content = content.replace(/GEMINI_MODEL=.*/g, `GEMINI_MODEL=${model}`);
            } else {
              content += `GEMINI_MODEL=${model}\n`;
            }
            fs.writeFileSync(p, content, "utf-8");
          }
        } catch {
          // ignore error writing to secondary paths
        }
      }

      res.json({
        success: true,
        verified,
        message: verificationMessage,
        model,
        maskedKey: `${apiKey.slice(0, 6)}...${apiKey.slice(-4)}`
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message || "Failed to update Gemini settings" });
    }
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

  // Serve production React frontend if built
  try {
    const frontendDist = path.resolve(process.cwd(), "..", "frontend", "dist");
    if (fs.existsSync(frontendDist)) {
      app.use(express.static(frontendDist));
      app.get("/", (_req: Request, res: Response) => {
        res.sendFile(path.join(frontendDist, "index.html"));
      });
    }
  } catch {
    // Ignore static resolution errors in isolated test runs
  }

  return app;
}

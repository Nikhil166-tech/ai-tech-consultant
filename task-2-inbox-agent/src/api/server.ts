import express, { Request, Response, NextFunction } from "express";
import cors from "cors";
import path from "path";
import fs from "fs";
import { InboxService } from "../inbox_service.js";
import { CustomerEmailSchema, ReviewSubmissionSchema, AutonomyRevocationSchema } from "../validation/schemas.js";

export function createServer(inboxService?: InboxService) {
  const app = express();

  const rawOrigins = process.env.ALLOWED_ORIGINS || "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000";
  const allowedOrigins = rawOrigins.split(",").map((s) => s.trim()).filter(Boolean);

  app.use(
    cors({
      origin: (origin, callback) => {
        if (!origin || allowedOrigins.includes(origin) || allowedOrigins.includes("*")) {
          callback(null, true);
        } else {
          callback(new Error(`Origin ${origin} not allowed by CORS`));
        }
      },
      credentials: true
    })
  );
  app.use(express.json());

  const service = inboxService || new InboxService();
  const task1Url = process.env.TASK1_URL || "http://127.0.0.1:8000";

  // Authentication Middleware for Task 2 Protected Endpoints
  const authenticateRequest = async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    // 1. Check internal service key (for direct server-to-server calls)
    const internalKey = req.headers["x-internal-service-key"] as string | undefined;
    const expectedInternalKey = process.env.INTERNAL_SERVICE_KEY || "";
    if (internalKey) {
      if (internalKey === expectedInternalKey) {
        (req as any).user = { id: "service_internal", role: "service" };
        return next();
      }
      res.status(401).json({ error: "Invalid internal service key" });
      return;
    }

    // 2. Extract session_id from cookie or Bearer authorization header
    let sessionId: string | undefined;
    if (req.headers.cookie) {
      const match = req.headers.cookie.match(/(?:^|;\s*)session_id=([^;]+)/);
      if (match) sessionId = match[1];
    }
    if (!sessionId && req.headers.authorization?.startsWith("Bearer ")) {
      sessionId = req.headers.authorization.slice(7).trim();
    }

    if (!sessionId) {
      if (process.env.ENVIRONMENT === "production") {
        res.status(401).json({ error: "Authentication required. Please sign in." });
        return;
      }
      // In development mode when no credentials are provided at all
      (req as any).user = { id: "dev_user", role: "user" };
      return next();
    }

    // 3. Validate session against Task 1
    try {
      const authRes = await fetch(`${task1Url}/api/v1/auth/me`, {
        headers: {
          "Cookie": `session_id=${sessionId}`,
          "Authorization": `Bearer ${sessionId}`
        }
      });
      if (authRes.ok) {
        const data: any = await authRes.json();
        (req as any).user = data.user;
        return next();
      } else {
        res.status(401).json({ error: "Session has expired or is invalid. Please sign in again." });
        return;
      }
    } catch (err: any) {
      // In test environment, if task 1 is not running, fallback to dev_user
      if (process.env.NODE_ENV === "test" || process.env.ENVIRONMENT !== "production") {
        (req as any).user = { id: "dev_user", role: "user" };
        return next();
      }
      res.status(502).json({ error: `Authentication service unavailable: ${err.message}` });
      return;
    }
  };

  // Health check
  app.get("/health", (_req: Request, res: Response): void => {
    res.json({
      status: "healthy",
      service: "task-2-inbox-agent",
      timestamp: new Date().toISOString()
    });
  });

  // Proxy Task 1 Knowledge Brain routes when accessed through unified server (e.g. port 3000)
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
        if (req.headers["x-csrf-token"]) headers["X-CSRF-Token"] = req.headers["x-csrf-token"] as string;
        // CRITICAL SECURITY HARDENING:
        // Do NOT inject or forward external client X-Internal-Service-Key through the browser proxy!
        // Client requests must authenticate via user cookies or Authorization Bearer header.

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

  // Proxy Task 3 Meeting-to-SOW routes
  const task3Url = process.env.TASK3_URL || "http://127.0.0.1:8002";
  app.all("/api/v1/projects*", async (req: Request, res: Response): Promise<void> => {
    try {
      const targetUrl = `${task3Url}${req.originalUrl}`;
      const headers: Record<string, string> = {};
      if (req.headers["content-type"]) {
        headers["Content-Type"] = req.headers["content-type"] as string;
      } else if (["POST", "PUT", "PATCH"].includes(req.method)) {
        headers["Content-Type"] = "application/json";
      }
      if (req.headers.cookie) headers["Cookie"] = req.headers.cookie as string;
      if (req.headers.authorization) headers["Authorization"] = req.headers.authorization as string;
      if (req.headers["x-csrf-token"]) headers["X-CSRF-Token"] = req.headers["x-csrf-token"] as string;
      if (req.headers["x-internal-service-key"]) headers["x-internal-service-key"] = req.headers["x-internal-service-key"] as string;

      const response = await fetch(targetUrl, {
        method: req.method,
        headers,
        body: ["POST", "PUT", "PATCH"].includes(req.method) ? JSON.stringify(req.body) : undefined
      });

      res.status(response.status);
      const disposition = response.headers.get("content-disposition");
      if (disposition) res.setHeader("content-disposition", disposition);
      const sowStatus = response.headers.get("x-sow-status");
      if (sowStatus) res.setHeader("x-sow-status", sowStatus);

      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const data = await response.json();
        res.json(data);
      } else {
        const text = await response.text();
        res.setHeader("content-type", contentType);
        res.send(text);
      }
    } catch (err: any) {
      res.status(502).json({ error: `Failed to proxy to Task 3 Meeting SOW at ${task3Url}: ${err.message}` });
    }
  });

  // Enforce authentication on all protected Task 2 routes
  app.use((req: Request, res: Response, next: NextFunction): void => {
    const isTask2Protected =
      req.path.startsWith("/api/v1/emails") ||
      req.path.startsWith("/api/v1/inbox") ||
      req.path.startsWith("/api/v1/autonomy") ||
      req.path.startsWith("/api/v1/taxonomy") ||
      req.path.startsWith("/api/v1/feedback") ||
      req.path.startsWith("/api/v1/settings/gemini") ||
      (req.path.startsWith("/api/v1/gmail") && !req.path.startsWith("/api/v1/gmail/callback"));

    if (isTask2Protected) {
      authenticateRequest(req, res, next);
    } else {
      next();
    }
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
      const { interactionId, action, reviewerId, finalReply, notes, sendViaGmail } = req.body;

      if (!interactionId || typeof interactionId !== "string") {
        res.status(400).json({ error: "interactionId string is required" });
        return;
      }

      const parseResult = ReviewSubmissionSchema.safeParse({ action, reviewerId, finalReply, notes, sendViaGmail });
      if (!parseResult.success) {
        res.status(400).json({
          error: "Invalid review submission",
          details: parseResult.error.errors.map((e) => `${e.path.join(".")}: ${e.message}`)
        });
        return;
      }

      const result = service.submitReview(interactionId, parseResult.data);
      // In STEP 1, live auto-sending remains staged/disabled.
      // Explicitly return gmailDelivery status so caller is never misled.
      const gmailDelivery = parseResult.data.sendViaGmail
        ? { staged: true, sent: false, note: "Gmail delivery staged; live automated sending is disabled in STEP 1" }
        : { staged: false, sent: false, note: "Manual review only; Gmail delivery not requested" };

      res.json({
        ...result,
        gmailDelivery
      });
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

  // Folder actions: Trash, Restore, Spam, Delete Forever
  app.post("/api/v1/inbox/:id/trash", (req: Request, res: Response): void => {
    const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
    const updated = service.interactionStore.moveToFolder(id, "TRASH");
    if (!updated) {
      res.status(404).json({ error: `Interaction '${id}' not found` });
      return;
    }
    res.json({ success: true, folder: "TRASH", interaction: updated });
  });

  app.post("/api/v1/inbox/:id/restore", (req: Request, res: Response): void => {
    const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
    const updated = service.interactionStore.moveToFolder(id, "INBOX");
    if (!updated) {
      res.status(404).json({ error: `Interaction '${id}' not found` });
      return;
    }
    res.json({ success: true, folder: "INBOX", interaction: updated });
  });

  app.post("/api/v1/inbox/:id/spam", (req: Request, res: Response): void => {
    const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
    const existing = service.interactionStore.getInteraction(id);
    if (!existing) {
      res.status(404).json({ error: `Interaction '${id}' not found` });
      return;
    }
    const newFolder = existing.folder === "SPAM" ? "INBOX" : "SPAM";
    const updated = service.interactionStore.moveToFolder(id, newFolder);
    res.json({ success: true, folder: newFolder, interaction: updated });
  });

  app.delete("/api/v1/inbox/:id/forever", (req: Request, res: Response): void => {
    const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
    const deleted = service.interactionStore.deleteInteraction(id);
    if (!deleted) {
      res.status(404).json({ error: `Interaction '${id}' not found` });
      return;
    }
    res.json({ success: true, message: `Interaction '${id}' deleted permanently.` });
  });

  // Real Outgoing Message Compose & Drafts
  app.post("/api/v1/inbox/compose", async (req: Request, res: Response): Promise<void> => {
    try {
      const { to, subject, body, saveDraft, sendViaGmail } = req.body;
      if (!to || !subject || !body) {
        res.status(400).json({ error: "'to', 'subject', and 'body' fields are required" });
        return;
      }

      const id = `msg_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      const now = new Date().toISOString();
      const isDraft = Boolean(saveDraft);

      let gmailMessageId: string | undefined;
      const finalFolder = isDraft ? "DRAFTS" : "SENT";
      const status = isDraft ? "PENDING_REVIEW" : "APPROVED";

      if (!isDraft && sendViaGmail) {
        if (service.gmailClient.isConnected()) {
          const sent = await service.gmailClient.sendEmail({
            to,
            subject,
            body
          });
          gmailMessageId = sent.messageId;
        }
      }

      const interaction: any = {
        id,
        folder: finalFolder,
        email: {
          id,
          senderEmail: to,
          subject,
          body,
          receivedAt: now
        },
        classification: {
          kind: {
            intent: "GENERAL_INQUIRY",
            riskLevel: "LOW",
            productArea: "UNKNOWN",
            key: "GENERAL_INQUIRY:LOW:UNKNOWN"
          },
          confidence: 1.0,
          urgency: "NORMAL",
          reasoning: "User-composed outgoing message",
          requiresHumanReview: false,
          riskFlags: [],
          parentSettingType: "Outgoing Messages",
          specificLabel: isDraft ? "Draft" : "Sent",
          labelKey: isDraft ? "Outgoing -> Draft" : "Outgoing -> Sent"
        },
        task1Status: {
          success: true,
          isAvailable: true,
          evidenceScore: 1.0,
          evidenceStatus: "STRONG",
          needsHumanReview: false
        },
        draft: {
          id: `draft_${id}`,
          emailId: id,
          subject,
          body,
          generatedAt: now,
          promptVersion: "v1_baseline",
          knowledgeEvidenceScore: 1.0,
          citations: [],
          autoSendEligible: false
        },
        promptVersion: "v1_baseline",
        routingDecision: "HUMAN_REVIEW_QUEUE",
        status,
        finalSentReply: isDraft ? undefined : body,
        gmailMessageId,
        createdAt: now,
        updatedAt: now
      };

      service.interactionStore.saveInteraction(interaction);
      res.json({
        success: true,
        isDraft,
        folder: finalFolder,
        interaction
      });
    } catch (err: any) {
      res.status(500).json({ error: err?.message || "Failed to compose message" });
    }
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
          const safeErr = errBody.replace(new RegExp(apiKey.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g"), "[REDACTED_API_KEY]");
          verificationMessage = `Key saved, but Gemini verification returned HTTP ${testRes.status}: ${safeErr.slice(0, 150)}`;
        }
      } catch (err: any) {
        const safeMsg = (err?.message || "").replace(new RegExp(apiKey.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g"), "[REDACTED_API_KEY]");
        verificationMessage = `Key saved, but verification test failed: ${safeMsg}`;
      }

      // Update runtime environment & draftGenerator
      process.env.GEMINI_API_KEY = apiKey;
      process.env.GEMINI_MODEL = model;
      service.draftGenerator.apiKey = apiKey;
      service.draftGenerator.model = model;

      // Persist only to local service .env file if it exists; eliminate unauthorized writes across sibling folders
      const localEnvPath = path.resolve(process.cwd(), ".env");
      try {
        if (fs.existsSync(localEnvPath)) {
          let content = fs.readFileSync(localEnvPath, "utf-8");
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
          fs.writeFileSync(localEnvPath, content, "utf-8");
        }
      } catch (err: any) {
        console.warn(`[WARN] Failed to write local .env: ${err?.message}`);
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

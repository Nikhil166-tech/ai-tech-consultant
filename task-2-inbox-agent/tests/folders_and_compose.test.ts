import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { createServer } from "../src/api/server.js";
import { InboxService } from "../src/inbox_service.js";
import { InteractionStore } from "../src/storage/interaction_store.js";
import path from "path";
import fs from "fs";
import http from "http";

describe("Gmail Folders and Real Outgoing Compose", () => {
  let server: http.Server;
  let baseUrl: string;
  let service: InboxService;
  const testStorePath = path.resolve("data", "test_folders_interactions.json");
  const testAutoPath = path.resolve("data", "test_folders_auto.json");

  beforeEach(async () => {
    if (fs.existsSync(testStorePath)) fs.unlinkSync(testStorePath);
    if (fs.existsSync(testAutoPath)) fs.unlinkSync(testAutoPath);

    const store = new InteractionStore({
      storagePath: testStorePath,
      autoDeliveryPath: testAutoPath
    });
    service = new InboxService({ interactionStore: store });
    const app = createServer(service);

    await new Promise<void>((resolve) => {
      server = app.listen(0, () => {
        const addr = server.address() as any;
        baseUrl = `http://127.0.0.1:${addr.port}`;
        resolve();
      });
    });
  });

  afterEach(async () => {
    if (server) {
      await new Promise<void>((resolve) => server.close(() => resolve()));
    }
  });

  it("should compose an outgoing draft and save in DRAFTS folder", async () => {
    const res = await fetch(`${baseUrl}/api/v1/inbox/compose`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        to: "client@example.com",
        subject: "Project Estimate Update",
        body: "Hi team, please find attached our project review draft.",
        saveDraft: true
      })
    });
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.success).toBe(true);
    expect(body.isDraft).toBe(true);
    expect(body.folder).toBe("DRAFTS");
    expect(body.interaction.email.senderEmail).toBe("client@example.com");
    expect(body.interaction.status).toBe("PENDING_REVIEW");
  });

  it("should compose an outgoing message and save in SENT folder", async () => {
    const res = await fetch(`${baseUrl}/api/v1/inbox/compose`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        to: "partner@example.com",
        subject: "Approved SOW Delivery",
        body: "We have finalized and approved the Statement of Work.",
        saveDraft: false
      })
    });
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.success).toBe(true);
    expect(body.isDraft).toBe(false);
    expect(body.folder).toBe("SENT");
    expect(body.interaction.status).toBe("APPROVED");
    expect(body.interaction.finalSentReply).toBe("We have finalized and approved the Statement of Work.");
  });

  it("should move an email to Trash and restore it", async () => {
    // 1. Create a draft
    const compRes = await fetch(`${baseUrl}/api/v1/inbox/compose`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        to: "test@example.com",
        subject: "To be trashed",
        body: "Draft message",
        saveDraft: true
      })
    });
    const compBody = await compRes.json();
    const id = compBody.interaction.id;

    // 2. Move to trash
    const trashRes = await fetch(`${baseUrl}/api/v1/inbox/${id}/trash`, { method: "POST" });
    const trashBody = await trashRes.json();
    expect(trashRes.status).toBe(200);
    expect(trashBody.folder).toBe("TRASH");

    // 3. Verify in store
    const check1 = service.interactionStore.getInteraction(id);
    expect(check1?.folder).toBe("TRASH");

    // 4. Restore from trash
    const restoreRes = await fetch(`${baseUrl}/api/v1/inbox/${id}/restore`, { method: "POST" });
    const restoreBody = await restoreRes.json();
    expect(restoreRes.status).toBe(200);
    expect(restoreBody.folder).toBe("INBOX");

    const check2 = service.interactionStore.getInteraction(id);
    expect(check2?.folder).toBe("INBOX");
  });

  it("should mark and unmark Spam", async () => {
    const compRes = await fetch(`${baseUrl}/api/v1/inbox/compose`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        to: "spammer@suspicious.com",
        subject: "Suspicious message",
        body: "Win a free iPad",
        saveDraft: true
      })
    });
    const compBody = await compRes.json();
    const id = compBody.interaction.id;

    // Toggle spam -> SPAM
    const spamRes = await fetch(`${baseUrl}/api/v1/inbox/${id}/spam`, { method: "POST" });
    const spamBody = await spamRes.json();
    expect(spamRes.status).toBe(200);
    expect(spamBody.folder).toBe("SPAM");

    // Toggle spam again -> INBOX
    const unspamRes = await fetch(`${baseUrl}/api/v1/inbox/${id}/spam`, { method: "POST" });
    const unspamBody = await unspamRes.json();
    expect(unspamRes.status).toBe(200);
    expect(unspamBody.folder).toBe("INBOX");
  });

  it("should delete an interaction forever", async () => {
    const compRes = await fetch(`${baseUrl}/api/v1/inbox/compose`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        to: "delete@example.com",
        subject: "Delete forever",
        body: "Bye",
        saveDraft: true
      })
    });
    const compBody = await compRes.json();
    const id = compBody.interaction.id;

    // Move to trash
    await fetch(`${baseUrl}/api/v1/inbox/${id}/trash`, { method: "POST" });

    // Delete forever
    const delRes = await fetch(`${baseUrl}/api/v1/inbox/${id}/forever`, { method: "DELETE" });
    const delBody = await delRes.json();
    expect(delRes.status).toBe(200);
    expect(delBody.success).toBe(true);

    const check = service.interactionStore.getInteraction(id);
    expect(check).toBeUndefined();
  });
});

import fs from "fs";
import path from "path";
import { GmailAccountStatus, GmailMessageRecord } from "../types/index.js";

export interface GmailTokens {
  access_token: string;
  refresh_token?: string;
  expires_in?: number;
  expiry_date?: number; // epoch ms
  token_type?: string;
  scope?: string;
}

export interface SendEmailOptions {
  to: string;
  subject: string;
  body: string;
  threadId?: string;
  inReplyTo?: string;
  references?: string;
}

export class GmailClient {
  private clientId: string;
  private clientSecret: string;
  private redirectUri: string;
  private tokens: GmailTokens | null = null;
  private status: GmailAccountStatus = { isConnected: false };
  private processedIds: Set<string> = new Set();

  private readonly tokensPath: string;
  private readonly processedIdsPath: string;
  public readonly userId?: string;

  constructor(options?: {
    clientId?: string;
    clientSecret?: string;
    redirectUri?: string;
    tokensPath?: string;
    processedIdsPath?: string;
    userId?: string;
  }) {
    this.clientId = options?.clientId || process.env.GOOGLE_CLIENT_ID || "";
    this.clientSecret = options?.clientSecret || process.env.GOOGLE_CLIENT_SECRET || "";
    this.redirectUri = options?.redirectUri || process.env.GOOGLE_REDIRECT_URI || "http://localhost:3000/api/v1/gmail/callback";
    this.userId = options?.userId;
    const userSuffix = this.userId ? `_${this.userId}` : "";
    this.tokensPath = options?.tokensPath || path.join(process.cwd(), "data", `gmail_tokens${userSuffix}.json`);
    this.processedIdsPath = options?.processedIdsPath || path.join(process.cwd(), "data", `gmail_processed_ids${userSuffix}.json`);
    this.loadState();
  }

  public static forUser(userId: string): GmailClient {
    return new GmailClient({ userId });
  }

  public forUser(userId: string): GmailClient {
    return new GmailClient({
      clientId: this.clientId,
      clientSecret: this.clientSecret,
      redirectUri: this.redirectUri,
      userId
    });
  }

  public getStatus(): GmailAccountStatus {
    return { ...this.status };
  }

  public isConfigured(): boolean {
    return Boolean(this.clientId && this.clientSecret);
  }

  public isConnected(): boolean {
    return Boolean(this.status.isConnected && this.tokens?.access_token);
  }

  public getAuthorizationUrl(state?: string): string {
    if (!this.clientId) {
      throw new Error("GOOGLE_CLIENT_ID is not configured in environment or settings");
    }
    const scopes = [
      "https://www.googleapis.com/auth/gmail.readonly",
      "https://www.googleapis.com/auth/gmail.compose",
      "https://www.googleapis.com/auth/gmail.send",
      "https://www.googleapis.com/auth/userinfo.email",
      "https://www.googleapis.com/auth/userinfo.profile"
    ];

    const params = new URLSearchParams({
      client_id: this.clientId,
      redirect_uri: this.redirectUri,
      response_type: "code",
      scope: scopes.join(" "),
      access_type: "offline",
      prompt: "consent",
      ...(state ? { state } : {})
    });

    return `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
  }

  public async exchangeCodeForTokens(code: string): Promise<GmailTokens> {
    if (!this.clientId || !this.clientSecret) {
      throw new Error("Google OAuth credentials (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET) are missing");
    }

    const res = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        code,
        client_id: this.clientId,
        client_secret: this.clientSecret,
        redirect_uri: this.redirectUri,
        grant_type: "authorization_code"
      }).toString()
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Google token exchange failed (${res.status}): ${errText}`);
    }

    const data: any = await res.json();
    const expiryDate = Date.now() + (data.expires_in || 3600) * 1000;

    this.tokens = {
      access_token: data.access_token,
      refresh_token: data.refresh_token || this.tokens?.refresh_token,
      expires_in: data.expires_in,
      expiry_date: expiryDate,
      token_type: data.token_type,
      scope: data.scope
    };

    // Fetch user profile to verify identity
    await this.fetchAndStoreProfile();
    this.saveState();
    return { ...this.tokens };
  }

  public async refreshAccessToken(): Promise<string> {
    if (!this.tokens?.refresh_token) {
      throw new Error("No refresh token available to refresh access token");
    }

    const res = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: this.clientId,
        client_secret: this.clientSecret,
        refresh_token: this.tokens.refresh_token,
        grant_type: "refresh_token"
      }).toString()
    });

    if (!res.ok) {
      const errText = await res.text();
      this.status.isConnected = false;
      this.saveState();
      throw new Error(`Failed to refresh Google token (${res.status}): ${errText}`);
    }

    const data: any = await res.json();
    this.tokens.access_token = data.access_token;
    if (data.expires_in) {
      this.tokens.expires_in = data.expires_in;
      this.tokens.expiry_date = Date.now() + data.expires_in * 1000;
    }
    this.saveState();
    return data.access_token;
  }

  private async getValidAccessToken(): Promise<string> {
    if (!this.tokens?.access_token) {
      throw new Error("Gmail is not connected. Please authenticate via Google OAuth.");
    }
    // Refresh if within 2 minutes of expiry
    if (this.tokens.expiry_date && Date.now() >= this.tokens.expiry_date - 120000) {
      if (this.tokens.refresh_token) {
        return await this.refreshAccessToken();
      }
    }
    return this.tokens.access_token;
  }

  public async disconnect(): Promise<void> {
    if (this.tokens?.access_token) {
      try {
        await fetch(`https://oauth2.googleapis.com/revoke?token=${encodeURIComponent(this.tokens.access_token)}`, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" }
        });
      } catch {
        // Ignore revocation network failures
      }
    }
    this.tokens = null;
    this.status = { isConnected: false };
    this.saveState();
  }

  public async fetchAndStoreProfile(): Promise<void> {
    const token = await this.getValidAccessToken();
    const res = await fetch("https://www.googleapis.com/oauth2/v2/userinfo", {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (res.ok) {
      const user: any = await res.json();
      this.status = {
        isConnected: true,
        email: user.email,
        name: user.name || user.email,
        tokenExpiry: this.tokens?.expiry_date ? new Date(this.tokens.expiry_date).toISOString() : undefined,
        lastSyncAt: new Date().toISOString(),
        scopes: this.tokens?.scope ? this.tokens.scope.split(" ") : [],
        isMock: false
      };
    } else {
      this.status.isConnected = true;
      this.status.lastSyncAt = new Date().toISOString();
    }
  }

  /**
   * Lists messages in user's inbox.
   */
  public async listInboxMessages(maxResults: number = 20): Promise<Array<{ id: string; threadId: string }>> {
    const token = await this.getValidAccessToken();
    const url = `https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=${maxResults}&q=label:INBOX`;
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` }
    });

    if (!res.ok) {
      throw new Error(`Gmail API list messages failed (${res.status}): ${await res.text()}`);
    }

    const data: any = await res.json();
    return data.messages || [];
  }

  /**
   * Fetches full Gmail message details and decodes headers and body.
   */
  public async getMessage(messageId: string): Promise<GmailMessageRecord> {
    const token = await this.getValidAccessToken();
    const url = `https://gmail.googleapis.com/gmail/v1/users/me/messages/${messageId}?format=full`;
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` }
    });

    if (!res.ok) {
      throw new Error(`Gmail API getMessage failed (${res.status}): ${await res.text()}`);
    }

    const msg: any = await res.json();
    const headers = msg.payload?.headers || [];
    const getHeader = (name: string): string => {
      const h = headers.find((item: any) => item.name.toLowerCase() === name.toLowerCase());
      return h ? h.value : "";
    };

    const subject = getHeader("Subject") || "No Subject";
    const sender = getHeader("From") || "Unknown Sender";
    const recipient = getHeader("To") || "";
    const date = getHeader("Date") || new Date().toISOString();
    const inReplyTo = getHeader("In-Reply-To") || undefined;
    const references = getHeader("References") || undefined;

    // Body extraction
    let bodyText = "";
    if (msg.payload?.parts) {
      const textPart = msg.payload.parts.find((p: any) => p.mimeType === "text/plain");
      if (textPart?.body?.data) {
        bodyText = Buffer.from(textPart.body.data, "base64").toString("utf-8");
      }
    }
    if (!bodyText && msg.payload?.body?.data) {
      bodyText = Buffer.from(msg.payload.body.data, "base64").toString("utf-8");
    }
    if (!bodyText) {
      bodyText = msg.snippet || "";
    }

    return {
      id: msg.id,
      threadId: msg.threadId,
      snippet: msg.snippet || "",
      subject,
      sender,
      recipient,
      bodyText,
      date,
      labels: msg.labelIds || [],
      inReplyTo,
      references,
      processed: this.processedIds.has(msg.id)
    };
  }

  /**
   * Lists Drafts in Gmail account.
   */
  public async listDrafts(maxResults: number = 20): Promise<any[]> {
    const token = await this.getValidAccessToken();
    const url = `https://gmail.googleapis.com/gmail/v1/users/me/drafts?maxResults=${maxResults}`;
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) {
      throw new Error(`Gmail API list drafts failed (${res.status}): ${await res.text()}`);
    }
    const data: any = await res.json();
    return data.drafts || [];
  }

  /**
   * Creates a draft in Gmail.
   */
  public async createDraft(options: SendEmailOptions): Promise<{ draftId: string; messageId: string }> {
    const token = await this.getValidAccessToken();
    const rawMime = this.buildRawEmail(options);
    const encoded = Buffer.from(rawMime)
      .toString("base64")
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");

    const payload: any = {
      message: {
        raw: encoded
      }
    };
    if (options.threadId) {
      payload.message.threadId = options.threadId;
    }

    const res = await fetch("https://gmail.googleapis.com/gmail/v1/users/me/drafts", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      throw new Error(`Gmail API createDraft failed (${res.status}): ${await res.text()}`);
    }

    const data: any = await res.json();
    return {
      draftId: data.id,
      messageId: data.message?.id || data.id
    };
  }

  /**
   * Sends an email through connected Gmail account.
   * Preserves threading headers: In-Reply-To, References, and Subject.
   * Confirms API acceptance before returning.
   */
  public async sendEmail(options: SendEmailOptions): Promise<{ messageId: string; threadId: string; success: boolean }> {
    const token = await this.getValidAccessToken();
    const rawMime = this.buildRawEmail(options);
    const encoded = Buffer.from(rawMime)
      .toString("base64")
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");

    const payload: any = { raw: encoded };
    if (options.threadId) {
      payload.threadId = options.threadId;
    }

    const res = await fetch("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Gmail API sendEmail rejected (${res.status}): ${errText}`);
    }

    const data: any = await res.json();
    return {
      messageId: data.id,
      threadId: data.threadId || options.threadId || data.id,
      success: true
    };
  }

  /**
   * Formats an RFC 2822 email payload.
   */
  public buildRawEmail(options: SendEmailOptions): string {
    const lines = [
      `To: ${options.to}`,
      `Subject: ${options.subject}`,
      `MIME-Version: 1.0`,
      `Content-Type: text/plain; charset=UTF-8`,
      `Content-Transfer-Encoding: 7bit`
    ];

    if (options.inReplyTo) {
      lines.push(`In-Reply-To: ${options.inReplyTo}`);
    }
    if (options.references) {
      lines.push(`References: ${options.references}`);
    }

    lines.push("");
    lines.push(options.body);
    return lines.join("\r\n");
  }

  /**
   * Tracks processed incoming Gmail messages so each message is processed exactly once.
   */
  public isMessageProcessed(messageId: string): boolean {
    return this.processedIds.has(messageId);
  }

  public markMessageProcessed(messageId: string): void {
    this.processedIds.add(messageId);
    this.saveState();
  }

  /**
   * Connects a mock Gmail account for offline testing without requiring real Google credentials.
   */
  public connectMockAccount(email: string = "demo.support@brilliantdirectories.com", name: string = "BD Demo Support"): void {
    this.tokens = {
      access_token: `mock_access_${Date.now()}`,
      refresh_token: `mock_refresh_${Date.now()}`,
      expires_in: 3600,
      expiry_date: Date.now() + 3600 * 1000,
      scope: "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"
    };
    this.status = {
      isConnected: true,
      email,
      name,
      tokenExpiry: new Date(Date.now() + 3600 * 1000).toISOString(),
      lastSyncAt: new Date().toISOString(),
      scopes: ["gmail.readonly", "gmail.send"],
      isMock: true
    };
    this.saveState();
  }

  private loadState(): void {
    try {
      if (fs.existsSync(this.tokensPath)) {
        const raw = fs.readFileSync(this.tokensPath, "utf-8");
        const parsed = JSON.parse(raw);
        if (parsed.tokens) {
          this.tokens = parsed.tokens;
        }
        if (parsed.status) {
          this.status = parsed.status;
        }
      }
    } catch {
      // Empty fresh state
    }

    try {
      if (fs.existsSync(this.processedIdsPath)) {
        const raw = fs.readFileSync(this.processedIdsPath, "utf-8");
        const list = JSON.parse(raw);
        if (Array.isArray(list)) {
          this.processedIds = new Set(list);
        }
      }
    } catch {
      // Empty fresh state
    }
  }

  private saveState(): void {
    try {
      const dir = path.dirname(this.tokensPath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      fs.writeFileSync(this.tokensPath, JSON.stringify({ tokens: this.tokens, status: this.status }, null, 2), "utf-8");
      fs.writeFileSync(this.processedIdsPath, JSON.stringify(Array.from(this.processedIds), null, 2), "utf-8");
    } catch (err) {
      console.error("Failed to save Gmail state:", err);
    }
  }
}

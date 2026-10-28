/**
 * Email Content Cleaner
 * Cleans quoted replies, email signatures, disclaimers, and redundant formatting
 * to prepare clean, untrusted customer message text for classification and drafting.
 */

export interface CleanedEmailContent {
  subject: string;
  cleanedBody: string;
  extractedQuotes: string[];
  extractedSignature?: string;
  rawLength: number;
  cleanedLength: number;
}

export function cleanEmailText(subject: string, rawBody: string): CleanedEmailContent {
  const normSubject = (subject || "").trim();
  const raw = rawBody || "";
  const rawLength = raw.length;

  const extractedQuotes: string[] = [];
  let extractedSignature: string | undefined;

  // 1. Split into lines
  const lines = raw.split(/\r?\n/);
  const keptLines: string[] = [];
  let inQuoteBlock = false;
  let inSignatureBlock = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Detect quoted reply headers
    // e.g. "On Wed, Oct 28, 2026 at 9:00 AM Alice <alice@example.com> wrote:"
    // or "-----Original Message-----"
    // or "From: Bob <bob@example.com>"
    if (
      /^On\s+.+wrote:$/i.test(trimmed) ||
      /^-----Original Message-----/i.test(trimmed) ||
      /^-{3,}\s*Forwarded message\s*-{3,}/i.test(trimmed) ||
      /^From:\s*.*@.*/i.test(trimmed)
    ) {
      inQuoteBlock = true;
      extractedQuotes.push(lines.slice(i).join("\n"));
      break;
    }

    // Detect lines starting with quote marker ">"
    if (trimmed.startsWith(">")) {
      extractedQuotes.push(line);
      continue;
    }

    // Detect standard signature delimiters
    if (
      trimmed === "--" ||
      trimmed === "-- " ||
      trimmed === "---" ||
      /^sent from my (iphone|ipad|galaxy|android|pixel|phone)/i.test(trimmed)
    ) {
      inSignatureBlock = true;
      extractedSignature = lines.slice(i).join("\n");
      break;
    }

    // Detect common sign-off phrases at bottom of email
    if (
      i >= lines.length - 4 &&
      /^(best regards|kind regards|warm regards|regards|sincerely|cheers|thanks & regards|thanks and regards|thanks,)\b/i.test(trimmed)
    ) {
      inSignatureBlock = true;
      extractedSignature = lines.slice(i).join("\n");
      break;
    }

    if (!inQuoteBlock && !inSignatureBlock) {
      keptLines.push(line);
    }
  }

  // 2. Normalize whitespace while preserving paragraphs
  let cleaned = keptLines.join("\n");
  // Replace 3+ consecutive newlines with 2
  cleaned = cleaned.replace(/\n{3,}/g, "\n\n");
  cleaned = cleaned.trim();

  // Fallback: if cleaning stripped everything (e.g. email was just a signature/quote), retain first 200 chars of raw
  if (!cleaned && raw.trim()) {
    cleaned = raw.trim().slice(0, 300);
  }

  return {
    subject: normSubject,
    cleanedBody: cleaned,
    extractedQuotes,
    extractedSignature,
    rawLength,
    cleanedLength: cleaned.length
  };
}

export function cleanEmailBody(rawBody: string): string {
  return cleanEmailText("", rawBody).cleanedBody;
}

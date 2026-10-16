import {
  CustomerEmail,
  EmailClassification,
  Intent,
  RiskLevel,
  ProductArea,
  formatKindKey
} from "../types/index.js";

export class EmailClassifier {
  public classify(email: CustomerEmail): EmailClassification {
    const text = `${email.subject} ${email.body}`.toLowerCase();
    const riskFlags: string[] = [];

    // 1. Security & Prompt Injection checks
    if (
      text.includes("ignore previous instructions") ||
      text.includes("ignore all previous") ||
      text.includes("system override") ||
      text.includes("you are now dan") ||
      text.includes("reply with") ||
      text.includes("bypass security") ||
      text.includes("bypass payment") ||
      text.includes("jailbreak")
    ) {
      riskFlags.push("PROMPT_INJECTION_DETECTED");
    }

    if (
      text.includes("password") ||
      text.includes("mysql root") ||
      text.includes("credentials") ||
      text.includes("secret key leak") ||
      text.includes("hacked") ||
      text.includes("compromised") ||
      text.includes("stolen account") ||
      text.includes("lost access to my 2fa")
    ) {
      riskFlags.push("ACCOUNT_SECURITY_COMPROMISE");
    }

    // 2. Legal, Financial Dispute, and Refund checks
    if (
      text.includes("refund") ||
      text.includes("chargeback") ||
      text.includes("dispute charge") ||
      text.includes("fraudulent charge") ||
      text.includes("unauthorized billing") ||
      text.includes("unauthorized charge") ||
      text.includes("billed twice") ||
      text.includes("overcharge")
    ) {
      riskFlags.push("FINANCIAL_DISPUTE_OR_REFUND");
    }

    if (
      text.includes("lawyer") ||
      text.includes("lawsuit") ||
      text.includes("legal counsel") ||
      text.includes("litigation") ||
      text.includes("sue you") ||
      text.includes("cease and desist") ||
      text.includes("gdpr") ||
      text.includes("ccpa deletion")
    ) {
      riskFlags.push("LEGAL_OR_COMPLIANCE_RISK");
    }

    if (
      text.includes("cancel subscription immediately") ||
      text.includes("cancel my account") ||
      text.includes("cancelling subscription") ||
      text.includes("terminate service")
    ) {
      riskFlags.push("ACCOUNT_CANCELLATION");
    }

    // 3. Determine Risk Level
    let riskLevel = RiskLevel.LOW;
    if (
      riskFlags.includes("PROMPT_INJECTION_DETECTED") ||
      riskFlags.includes("ACCOUNT_SECURITY_COMPROMISE") ||
      riskFlags.includes("LEGAL_OR_COMPLIANCE_RISK")
    ) {
      riskLevel = RiskLevel.CRITICAL;
    } else if (
      riskFlags.includes("FINANCIAL_DISPUTE_OR_REFUND") ||
      riskFlags.includes("ACCOUNT_CANCELLATION")
    ) {
      riskLevel = RiskLevel.HIGH;
    } else if (
      text.includes("urgent") ||
      text.includes("broken live site") ||
      text.includes("lost revenue")
    ) {
      riskLevel = RiskLevel.MEDIUM;
    }

    // 4. Determine Product Area
    let productArea = ProductArea.UNKNOWN;
    if (
      riskFlags.includes("ACCOUNT_SECURITY_COMPROMISE") ||
      text.includes("2fa") ||
      text.includes("login security") ||
      text.includes("admin password")
    ) {
      productArea = ProductArea.ACCOUNT_SECURITY;
    } else if (
      text.includes("stripe") ||
      text.includes("paypal") ||
      text.includes("payment gateway") ||
      text.includes("coupon") ||
      text.includes("discount code") ||
      text.includes("transaction fee")
    ) {
      productArea = ProductArea.PAYMENTS_GATEWAYS;
    } else if (
      text.includes("membership plan") ||
      text.includes("subscription plan") ||
      text.includes("pricing tier") ||
      text.includes("recurring") ||
      text.includes("upgrade plan") ||
      text.includes("verified badge") ||
      text.includes("verified badges")
    ) {
      productArea = ProductArea.MEMBERSHIP_PLANS;
    } else if (
      text.includes("domain") ||
      text.includes("dns") ||
      text.includes("cname") ||
      text.includes("a record") ||
      text.includes("nameserver") ||
      text.includes("ssl")
    ) {
      productArea = ProductArea.DOMAINS_DNS;
    } else if (
      text.includes("email template") ||
      text.includes("welcome email") ||
      text.includes("smtp") ||
      text.includes("system email")
    ) {
      productArea = ProductArea.EMAIL_TEMPLATES;
    } else if (
      text.includes("recaptcha") ||
      text.includes("spam") ||
      text.includes("lead form") ||
      text.includes("contact form")
    ) {
      productArea = ProductArea.FORMS_RECAPTCHA;
    } else if (
      text.includes("radius") ||
      text.includes("search distance") ||
      text.includes("location search") ||
      text.includes("miles") ||
      text.includes("zip code")
    ) {
      productArea = ProductArea.SEARCH_LOCATIONS;
    } else if (
      text.includes("analytics") ||
      text.includes("ga4") ||
      text.includes("google analytics") ||
      text.includes("tracking code") ||
      text.includes("measurement id")
    ) {
      productArea = ProductArea.ANALYTICS_TRACKING;
    } else if (
      text.includes("export") ||
      text.includes("csv") ||
      text.includes("import members") ||
      text.includes("member data") ||
      text.includes("export member data")
    ) {
      productArea = ProductArea.MEMBER_EXPORT_IMPORT;
    } else if (
      text.includes("claim") ||
      text.includes("claimable") ||
      text.includes("claim listing")
    ) {
      productArea = ProductArea.LISTINGS_MANAGEMENT;
    }

    // 5. Determine Intent
    let intent = Intent.GENERAL_INQUIRY;
    if (riskFlags.includes("ACCOUNT_CANCELLATION")) {
      intent = Intent.CANCELLATION;
    } else if (riskFlags.includes("FINANCIAL_DISPUTE_OR_REFUND")) {
      intent = Intent.BILLING_ISSUE;
    } else if (riskFlags.includes("ACCOUNT_SECURITY_COMPROMISE") || riskFlags.includes("PROMPT_INJECTION_DETECTED")) {
      intent = Intent.ACCOUNT_ACCESS;
    } else if (
      text.includes("does brilliant directories support") ||
      text.includes("can brilliant directories") ||
      text.includes("how do claimable") ||
      text.includes("how do they claim") ||
      text.includes("can members") ||
      text.includes("is it possible to") ||
      text.includes("feature request")
    ) {
      intent = Intent.FEATURE_INQUIRY;
    } else if (
      text.includes("how to") ||
      text.includes("how do i") ||
      text.includes("how do we") ||
      text.includes("how can we") ||
      text.includes("where can i") ||
      text.includes("where do i") ||
      text.includes("where do we") ||
      text.includes("what dns records") ||
      text.includes("connecting") ||
      text.includes("configure") ||
      text.includes("setup") ||
      text.includes("steps to") ||
      text.includes("change search radius") ||
      text.includes("creating") ||
      text.includes("activating") ||
      text.includes("installing") ||
      text.includes("can we export") ||
      text.includes("exporting")
    ) {
      intent = Intent.HOW_TO_CONFIGURE;
    } else if (
      text.includes("bug") ||
      text.includes("error") ||
      text.includes("broken") ||
      text.includes("failed") ||
      text.includes("not working") ||
      text.includes("help")
    ) {
      intent = Intent.BUG_REPORT;
    }

    const urgency: "LOW" | "NORMAL" | "HIGH" =
      riskLevel === RiskLevel.CRITICAL || riskLevel === RiskLevel.HIGH ? "HIGH" :
      riskLevel === RiskLevel.MEDIUM ? "NORMAL" : "LOW";

    const requiresHumanReview =
      riskLevel === RiskLevel.HIGH ||
      riskLevel === RiskLevel.CRITICAL ||
      riskFlags.length > 0;

    const kindKey = formatKindKey(intent, riskLevel, productArea);

    return {
      kind: {
        intent,
        riskLevel,
        productArea,
        key: kindKey
      },
      confidence: riskFlags.length > 0 ? 0.98 : 0.90,
      urgency,
      reasoning: `Classified as ${intent} (${productArea}) at ${riskLevel} risk level. Flags: [${riskFlags.join(", ")}]`,
      requiresHumanReview,
      riskFlags
    };
  }
}

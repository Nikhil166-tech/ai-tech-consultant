import fs from "fs";
import path from "path";
import {
  CustomerEmail,
  EmailClassification,
  Intent,
  RiskLevel,
  ProductArea,
  TaxonomyItem,
  formatKindKey
} from "../types/index.js";

const DEFAULT_TAXONOMY: TaxonomyItem[] = [
  {
    id: "tax_design_header",
    parentSettingType: "Design Settings",
    specificLabel: "Header",
    description: "Website header, top navigation bar, logo placement, and header colors",
    keywords: ["header", "top bar", "site header", "branding logo", "banner", "top navigation", "logo"],
    synonyms: ["masthead", "head section", "top navbar", "brand header"],
    enabled: true
  },
  {
    id: "tax_design_footer",
    parentSettingType: "Design Settings",
    specificLabel: "Footer",
    description: "Website footer, bottom copyright, footer links, and bottom styling",
    keywords: ["footer", "bottom bar", "site footer", "copyright", "bottom links", "footer menu"],
    synonyms: ["bottom navigation", "sub-footer", "colophon", "page bottom"],
    enabled: true
  },
  {
    id: "tax_design_homepage",
    parentSettingType: "Design Settings",
    specificLabel: "Homepage",
    description: "Homepage layout, hero section, featured widgets, and front page styling",
    keywords: ["homepage", "front page", "home page", "landing page", "hero section", "main layout"],
    synonyms: ["frontpage", "start page", "welcome screen", "splash"],
    enabled: true
  },
  {
    id: "tax_menu_main",
    parentSettingType: "Menu Manager",
    specificLabel: "Main Menu",
    description: "Main navigation menu links, dropdowns, and menu order",
    keywords: ["main menu", "menu manager", "navigation menu", "dropdown menu", "nav links", "sub-menu"],
    synonyms: ["nav bar", "site menu", "navigation bar", "menu items"],
    enabled: true
  },
  {
    id: "tax_filters_search",
    parentSettingType: "Filters",
    specificLabel: "Search Filters",
    description: "Search filter fields, search radius, location distance, and facet options",
    keywords: ["search filters", "search radius", "radius", "filter options", "distance search", "zip code search", "miles", "facets"],
    synonyms: ["proximity filter", "refine search", "criteria filter", "range filter", "location radius"],
    enabled: true
  },
  {
    id: "tax_domain_dns",
    parentSettingType: "Domain Management",
    specificLabel: "DNS Configuration",
    description: "Custom domain DNS records, nameservers, A records, CNAME, and propagation",
    keywords: ["dns", "domain", "nameserver", "cname", "a record", "txt record", "godaddy", "cloudflare", "pointing domain"],
    synonyms: ["domain setup", "nameservers", "custom domain", "zone records"],
    enabled: true
  },
  {
    id: "tax_domain_ssl",
    parentSettingType: "Domain Management",
    specificLabel: "SSL Configuration",
    description: "HTTPS certificates, SSL installation, secure connections, and certificate errors",
    keywords: ["ssl", "https", "certificate", "ssl error", "secure connection", "padlock"],
    synonyms: ["tls certificate", "security certificate", "https setup"],
    enabled: true
  },
  {
    id: "tax_billing_payments",
    parentSettingType: "Billing",
    specificLabel: "Payment Settings",
    description: "Payment gateways, Stripe keys, PayPal integration, transaction fees, and currencies",
    keywords: ["payment", "stripe", "paypal", "gateway", "publishable key", "secret key", "credit card", "merchant", "currency", "coupon", "discount code"],
    synonyms: ["payment processor", "checkout gateway", "billing gateway", "payment integration"],
    enabled: true
  },
  {
    id: "tax_billing_subscription",
    parentSettingType: "Billing",
    specificLabel: "Subscription Management",
    description: "Membership plans, pricing tiers, recurring billing, invoices, and subscription upgrades",
    keywords: ["subscription", "membership plan", "pricing tier", "recurring", "upgrade plan", "downgrade", "verified badge", "invoices"],
    synonyms: ["member plan", "billing plan", "recurring subscription", "membership tier"],
    enabled: true
  },
  {
    id: "tax_staging_sandbox",
    parentSettingType: "Staging",
    specificLabel: "Sandbox",
    description: "Staging environment, test site, clone sandbox, and preview domain",
    keywords: ["staging", "sandbox", "test site", "preview site", "test environment", "clone site"],
    synonyms: ["development site", "dev environment", "staging domain"],
    enabled: true
  },
  {
    id: "tax_general_site",
    parentSettingType: "General Settings",
    specificLabel: "Site Details",
    description: "General website details, site name, contact email, timezone, and basic configuration",
    keywords: ["general settings", "site details", "website name", "contact address", "admin email", "timezone", "site info"],
    synonyms: ["basic settings", "site configuration", "global settings"],
    enabled: true
  }
];

export class EmailClassifier {
  private taxonomy: TaxonomyItem[] = [];
  private readonly taxonomyFilePath: string;

  constructor(taxonomyFilePath?: string) {
    this.taxonomyFilePath = taxonomyFilePath || path.join(process.cwd(), "data", "taxonomy.json");
    this.loadTaxonomy();
  }

  public getTaxonomy(): TaxonomyItem[] {
    return [...this.taxonomy];
  }

  public updateTaxonomy(items: TaxonomyItem[]): void {
    this.taxonomy = items;
    this.saveTaxonomy();
  }

  private loadTaxonomy(): void {
    try {
      if (fs.existsSync(this.taxonomyFilePath)) {
        const raw = fs.readFileSync(this.taxonomyFilePath, "utf-8");
        this.taxonomy = JSON.parse(raw);
        if (!Array.isArray(this.taxonomy) || this.taxonomy.length === 0) {
          this.taxonomy = [...DEFAULT_TAXONOMY];
          this.saveTaxonomy();
        }
      } else {
        this.taxonomy = [...DEFAULT_TAXONOMY];
        this.saveTaxonomy();
      }
    } catch {
      this.taxonomy = [...DEFAULT_TAXONOMY];
    }
  }

  private saveTaxonomy(): void {
    try {
      const dir = path.dirname(this.taxonomyFilePath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      fs.writeFileSync(this.taxonomyFilePath, JSON.stringify(this.taxonomy, null, 2), "utf-8");
    } catch (err) {
      console.error("Failed to save taxonomy:", err);
    }
  }

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

    // 4. Determine Product Area (for backward compatibility)
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

    // 6. Determine Parent Setting Type & Specific Label using Taxonomy Scoring
    let bestMatchItem: TaxonomyItem | null = null;
    let highestScore = 0;

    for (const item of this.taxonomy) {
      if (!item.enabled) continue;
      let score = 0;

      // Check keywords (high weight)
      for (const kw of item.keywords) {
        if (text.includes(kw.toLowerCase())) {
          score += 3;
        }
      }

      // Check synonyms (medium weight)
      for (const syn of item.synonyms) {
        if (text.includes(syn.toLowerCase())) {
          score += 2;
        }
      }

      // Label name exact match
      if (text.includes(item.specificLabel.toLowerCase())) {
        score += 4;
      }

      if (score > highestScore) {
        highestScore = score;
        bestMatchItem = item;
      }
    }

    let parentSettingType = "General Settings";
    let specificLabel = "Site Details";

    if (bestMatchItem && highestScore > 0) {
      parentSettingType = bestMatchItem.parentSettingType;
      specificLabel = bestMatchItem.specificLabel;
    } else if (productArea === ProductArea.PAYMENTS_GATEWAYS) {
      parentSettingType = "Billing";
      specificLabel = "Payment Settings";
    } else if (productArea === ProductArea.MEMBERSHIP_PLANS) {
      parentSettingType = "Billing";
      specificLabel = "Subscription Management";
    } else if (productArea === ProductArea.DOMAINS_DNS) {
      parentSettingType = "Domain Management";
      specificLabel = text.includes("ssl") || text.includes("https") ? "SSL Configuration" : "DNS Configuration";
    } else if (productArea === ProductArea.SEARCH_LOCATIONS) {
      parentSettingType = "Filters";
      specificLabel = "Search Filters";
    } else if (riskFlags.includes("FINANCIAL_DISPUTE_OR_REFUND")) {
      parentSettingType = "Billing";
      specificLabel = "Payment Settings";
    }

    const labelKey = `${parentSettingType} -> ${specificLabel}`;

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
      confidence: riskFlags.length > 0 ? 0.98 : highestScore >= 3 ? 0.95 : 0.85,
      urgency,
      reasoning: `Classified as ${parentSettingType} -> ${specificLabel} (${intent}, ${productArea}) at ${riskLevel} risk level. Flags: [${riskFlags.join(", ")}]`,
      requiresHumanReview,
      riskFlags,
      parentSettingType,
      specificLabel,
      labelKey
    };
  }
}


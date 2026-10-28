import re
import urllib.parse
from typing import Tuple, Optional, List, Dict, Any
from bs4 import BeautifulSoup, Tag

SITE_TITLE_SUFFIXES = [
    r"\s*\|\s*Brilliant Directories Solution Center.*$",
    r"\s*\|\s*Brilliant Directories.*$",
    r"\s*-\s*Brilliant Directories.*$",
    r"\s*\|\s*BD Growth Suite.*$",
    r"\s*-\s*BD Growth Suite.*$",
    r"\s*\|\s*BD Support.*$",
    r"\s*-\s*BD Support.*$",
    r"\s*\|\s*Django.*$",
    r"\s*-\s*Django.*$",
]

NOISY_ELEMENTS = [
    "script", "style", "nav", "footer", "header", "aside",
    "noscript", "svg", "iframe", "form"
]

NOISY_CLASS_REGEX = re.compile(
    r"(cookie|banner|sidebar|footer|menu|nav|search-form|newsletter|login-modal|auth-box|social-share|pagination|comments|widget-footer)",
    re.IGNORECASE
)

LOGIN_PATTERNS = [
    re.compile(r"customer login", re.I),
    re.compile(r"sign in to your account", re.I),
    re.compile(r"please enter your (username|email) and password", re.I),
    re.compile(r"forgot your password\?", re.I),
]

BOT_OR_ERROR_PATTERNS = [
    re.compile(r"attention required!\s*\|\s*cloudflare", re.I),
    re.compile(r"just a moment\.\.\.", re.I),
    re.compile(r"verify you are human", re.I),
    re.compile(r"access denied", re.I),
    re.compile(r"404 not found", re.I),
    re.compile(r"page not found", re.I),
    re.compile(r"500 internal server error", re.I),
    re.compile(r"bad gateway", re.I),
]

GENERIC_TEMPLATE_FINGERPRINT = "looking for more information? submit a ticket"


def clean_title(soup: BeautifulSoup, raw_html: str, url: str) -> str:
    """Extracts a clean, accurate title matching the page, removing branding suffixes."""
    candidate = ""

    # 1. OpenGraph or Twitter meta title
    og = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
    if og and og.get("content") and og.get("content").strip():
        candidate = og["content"].strip()

    # 2. Look for h1 specifically within main, article, or primary content container
    if not candidate:
        main_el = (
            soup.find(["main", "article"])
            or soup.find(id=re.compile(r"main-content|article-content|content", re.I))
            or soup.find(class_=re.compile(r"article-body|solution-article|entry-content", re.I))
        )
        if main_el and isinstance(main_el, Tag):
            h1 = main_el.find("h1")
            if h1 and h1.get_text(strip=True):
                candidate = h1.get_text(strip=True)

    # 3. Look for <title> tag
    if not candidate:
        t = soup.find("title")
        if t and t.get_text(strip=True):
            candidate = t.get_text(strip=True)

    # 4. Any h1 that is not inside a noisy element like header, nav, or aside
    if not candidate:
        for h1 in soup.find_all("h1"):
            if not h1.find_parent(["header", "nav", "aside", "footer"]):
                txt = h1.get_text(strip=True)
                if txt:
                    candidate = txt
                    break

    # 5. Fallback to slug from URL path
    if not candidate:
        parsed = urllib.parse.urlsplit(url)
        path = parsed.path.strip("/")
        if path:
            slug = path.split("/")[-1].replace("-", " ").replace("_", " ").title()
            candidate = slug or "Knowledge Article"
        else:
            candidate = "Knowledge Article"

    # Strip site branding suffixes
    for pattern in SITE_TITLE_SUFFIXES:
        candidate = re.sub(pattern, "", candidate, flags=re.IGNORECASE).strip()

    return candidate or "Knowledge Article"


def extract_breadcrumbs(soup: BeautifulSoup) -> Tuple[str, str]:
    """Extracts category and folder from breadcrumbs if available."""
    category = "General"
    folder = "General"
    breadcrumbs = soup.find_all(class_=re.compile(r"breadcrumb", re.I))
    if breadcrumbs:
        crumbs = [b.get_text(strip=True) for b in breadcrumbs[0].find_all(["a", "li", "span"])]
        crumbs = [c for c in crumbs if c and c != ">" and "/" not in c and c.lower() != "home"]
        if len(crumbs) >= 1:
            category = crumbs[0]
        if len(crumbs) >= 2:
            folder = crumbs[1]
    return category, folder


def find_best_content_container(soup: BeautifulSoup) -> Optional[Tag]:
    """Finds the main content container, avoiding footer/sidebar widgets."""
    # Specific content selectors in order of confidence
    candidates = [
        soup.find("article"),
        soup.find(attrs={"itemprop": "articleBody"}),
        soup.find(class_=re.compile(r"article-body|solution-article|post-body|entry-content|documentation-content", re.I)),
        soup.find("main"),
        soup.find(id=re.compile(r"main-content|article-content|content", re.I)),
        soup.find(class_=re.compile(r"^content$", re.I)),
    ]

    for cand in candidates:
        if cand and isinstance(cand, Tag):
            # Check that it's not just a small footer snippet
            text = cand.get_text(strip=True)
            if len(text) > 80 and GENERIC_TEMPLATE_FINGERPRINT not in text.lower()[:150]:
                return cand

    # Fallback to body
    return soup.body


def format_table(table_tag: Tag) -> str:
    """Converts an HTML table into a clean Markdown table."""
    rows = []
    for tr in table_tag.find_all("tr"):
        cells = [re.sub(r"\s+", " ", td.get_text(strip=True)) for td in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    if not rows:
        return ""

    num_cols = max(len(r) for r in rows)
    normalized_rows = [r + [""] * (num_cols - len(r)) for r in rows]

    md_lines = []
    header = normalized_rows[0]
    md_lines.append("| " + " | ".join(header) + " |")
    md_lines.append("| " + " | ".join(["---"] * num_cols) + " |")
    for r in normalized_rows[1:]:
        md_lines.append("| " + " | ".join(r) + " |")

    return "\n" + "\n".join(md_lines) + "\n"


def validate_content_quality(title: str, text: str, url: str = "") -> Tuple[bool, Optional[str]]:
    """
    Validates that extracted content represents a genuine, high-quality knowledge article.
    Rejects:
    - Empty or nearly empty content (< 60 characters)
    - Customer login screens
    - Bot challenges / Cloudflare verification screens
    - Generic 404 or error pages
    - Template widgets where only footer/support ticket blurb was captured
    """
    cleaned_text = text.strip()
    if not cleaned_text:
        return False, "Extraction failed: body is completely empty."

    if len(cleaned_text) < 60:
        return False, f"Extraction rejected: content length ({len(cleaned_text)} chars) is below minimum threshold (60 chars)."

    lower_title = title.lower()
    lower_text = cleaned_text.lower()

    # Login rejection
    for pat in LOGIN_PATTERNS:
        if pat.search(lower_title) or (pat.search(lower_text) and len(cleaned_text) < 400):
            return False, f"Extraction rejected: Page identified as login screen / customer portal ('{title}')."

    # Bot challenges & error pages
    for pat in BOT_OR_ERROR_PATTERNS:
        if pat.search(lower_title):
            return False, f"Extraction rejected: Page identified as bot challenge or error screen ('{title}')."
        if pat.search(lower_text) and len(cleaned_text) < 300:
            return False, f"Extraction rejected: Page content indicates error or access restriction."

    # Shared generic footer template rejection
    # If the text is purely the "Looking for more information? Submit a ticket" block
    if GENERIC_TEMPLATE_FINGERPRINT in lower_text and len(cleaned_text) < 650:
        # Check if there is genuine article text outside the template
        stripped = re.sub(r"looking for more information\?.*", "", lower_text, flags=re.DOTALL).strip()
        if len(stripped) < 80:
            return False, "Extraction rejected: Extracted body contains only shared navigation/support footer widget without genuine article content."

    return True, None


def extract_article_content(
    html: str,
    url: str
) -> Tuple[Optional[str], Optional[str], str, str, List[Dict[str, Any]], Optional[str]]:
    """
    Extracts high-quality article content:
    Returns (title, full_markdown_text, category, folder, images_meta, rejection_reason).
    If rejection_reason is not None, the page was rejected from indexing.
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1. Title
    title = clean_title(soup, html, url)

    # 2. Category & Folder
    category, folder = extract_breadcrumbs(soup)

    # 3. Clean away noisy elements from entire soup
    for tag_name in NOISY_ELEMENTS:
        for el in soup.find_all(tag_name):
            el.decompose()

    # Remove elements with noisy classes or ids, unless they are the main container
    for el in list(soup.find_all(True)):
        if not isinstance(el, Tag) or getattr(el, "attrs", None) is None:
            continue
        if el.name in ["html", "body", "article", "main"]:
            continue
        classes = el.get("class", [])
        class_str = " ".join(classes) if isinstance(classes, list) else str(classes)
        id_str = el.get("id", "") or ""
        combined = f"{class_str} {id_str}"
        if NOISY_CLASS_REGEX.search(combined):
            # Do not delete if it contains high-level headings
            if not el.find(["h1", "h2"]):
                el.decompose()

    # 4. Find best container
    container = find_best_content_container(soup)
    if not container:
        return None, None, category, folder, [], "No valid content container found in HTML."

    # 5. Extract structured text preserving hierarchy, code, lists, tables, and images
    blocks = []
    images_meta = []
    current_heading = "Overview"

    elements = container.find_all(["h1", "h2", "h3", "h4", "p", "ul", "ol", "table", "pre", "img"])

    for el in elements:
        if el.name in ["h1", "h2", "h3", "h4"]:
            heading_text = el.get_text(strip=True)
            if heading_text:
                current_heading = heading_text
                prefix = "#" * int(el.name[1])
                blocks.append(f"\n{prefix} {heading_text}\n")

        elif el.name == "pre":
            code_text = el.get_text()
            if code_text.strip():
                blocks.append(f"\n```\n{code_text.strip()}\n```\n")

        elif el.name in ["ul", "ol"]:
            items = []
            is_ol = el.name == "ol"
            idx = 1
            for li in el.find_all("li", recursive=False):
                li_txt = li.get_text(strip=True)
                if li_txt:
                    if is_ol:
                        items.append(f"{idx}. {li_txt}")
                        idx += 1
                    else:
                        items.append(f"- {li_txt}")
            if items:
                blocks.append("\n" + "\n".join(items) + "\n")

        elif el.name == "table":
            tbl_md = format_table(el)
            if tbl_md:
                blocks.append(tbl_md)

        elif el.name == "img":
            src = el.get("src") or el.get("data-src") or ""
            if src and not src.startswith("data:"):
                # Dynamically resolve relative URLs against article URL
                abs_src = urllib.parse.urljoin(url, src)
                alt = el.get("alt", "").strip()
                caption = el.get("title", alt).strip()
                parent_txt = el.parent.get_text(strip=True) if el.parent else ""
                images_meta.append({
                    "url": abs_src,
                    "alt": alt,
                    "caption": caption,
                    "context_text": parent_txt[:200],
                    "section_heading": current_heading
                })

        elif el.name == "p":
            p_txt = el.get_text(strip=True)
            if p_txt:
                blocks.append(p_txt)

    full_text = "\n\n".join(blocks).strip()
    if not full_text:
        # Fallback to direct text
        full_text = container.get_text(separator="\n", strip=True)

    # 6. Quality Validation
    is_valid, rejection_reason = validate_content_quality(title, full_text, url)
    if not is_valid:
        return None, None, category, folder, images_meta, rejection_reason

    return title, full_text, category, folder, images_meta, None

#!/usr/bin/env python3
"""
Phase 2: Check URL liveness and extract content metadata for all references.

For each unique reference URL:
  - Send HTTP GET with proper User-Agent, 15s timeout
  - Record status code, final URL after redirects, accessibility
  - Extract page title, abstract where possible
  - Classify source_type and access_type
  - Write each result immediately (crash-safe, resumable)

Usage:
    python3 scripts/check_urls.py              # check all unchecked URLs
    python3 scripts/check_urls.py --force      # re-check all URLs
    python3 scripts/check_urls.py --only-failed  # retry only failed URLs
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

try:
    import urllib.request
    import urllib.error
    import ssl
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
AUDIT_FILE = DATA_DIR / "citation-audit.json"
REFS_FILE = DATA_DIR / "references.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 15

# Known paywall/subscription domains
PAYWALL_DOMAINS = {
    "ieeexplore.ieee.org",
    "dl.acm.org",
    "link.springer.com",
    "www.sciencedirect.com",
    "onlinelibrary.wiley.com",
    "www.nature.com",
    "www.jstor.org",
    "journals.sagepub.com",
    "www.tandfonline.com",
    "www.pnas.org",
    "academic.oup.com",
    "www.cell.com",
    "www.thelancet.com",
    "www.bmj.com",
    "www.nejm.org",
    "www.science.org",
}

# Known open-access domains
OPEN_DOMAINS = {
    "arxiv.org",
    "openreview.net",
    "proceedings.mlr.press",
    "aclanthology.org",
    "papers.nips.cc",
    "proceedings.neurips.cc",
    "eprint.iacr.org",
    "distill.pub",
}

# News/blog domains
NEWS_DOMAINS = {
    "www.nytimes.com",
    "www.theverge.com",
    "www.wired.com",
    "www.bbc.com",
    "www.bbc.co.uk",
    "www.reuters.com",
    "www.washingtonpost.com",
    "www.theguardian.com",
    "techcrunch.com",
    "arstechnica.com",
    "www.cnbc.com",
    "www.bloomberg.com",
    "fortune.com",
    "slate.com",
    "apnews.com",
    "www.statista.com",
}

# Book publisher / ISBN domains
BOOK_DOMAINS = {
    "www.amazon.com",
    "books.google.com",
    "global.oup.com",
    "www.cambridge.org",
    "mitpress.mit.edu",
    "press.princeton.edu",
}


class TitleExtractor(HTMLParser):
    """Extract <title> and meta tags from HTML."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self.abstract = ""
        self.og_description = ""
        self._in_title = False
        self._title_buf = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "title":
            self._in_title = True
            self._title_buf = []
        elif tag == "meta":
            name = attrs_dict.get("name", "").lower()
            prop = attrs_dict.get("property", "").lower()
            content = attrs_dict.get("content", "")
            if name == "citation_abstract" and content:
                self.abstract = content
            elif name == "description" and content and not self.og_description:
                self.og_description = content
            elif prop == "og:description" and content:
                self.og_description = content

    def handle_endtag(self, tag):
        if tag == "title" and self._in_title:
            self._in_title = False
            self.title = " ".join("".join(self._title_buf).split())

    def handle_data(self, data):
        if self._in_title:
            self._title_buf.append(data)


def extract_arxiv_abstract(html_text):
    """Extract abstract from arXiv HTML page."""
    # arXiv uses <blockquote class="abstract mathjax">
    m = re.search(
        r'<blockquote[^>]*class="abstract[^"]*"[^>]*>(.*?)</blockquote>',
        html_text,
        re.DOTALL,
    )
    if m:
        text = m.group(1)
        # Remove the "Abstract:" prefix
        text = re.sub(r"^\s*<span[^>]*>Abstract:</span>\s*", "", text)
        # Strip tags
        text = re.sub(r"<[^>]+>", "", text)
        return " ".join(text.split()).strip()
    return ""


def classify_source_type(url, ref_data):
    """Classify what type of source this reference is."""
    domain = urlparse(url).netloc.lower()
    ref_type = ref_data.get("type", "")
    venue = (ref_data.get("venue") or "").lower()

    # Check for books
    if ref_type == "book" or domain in BOOK_DOMAINS:
        return "book"
    if "isbn" in venue:
        return "book"

    # Check for datasets/software
    if ref_type == "software" or "github.com" in domain:
        return "software"
    if ref_type == "dataset":
        return "dataset"

    # Check for news/blogs
    if domain in NEWS_DOMAINS:
        return "news"
    if any(
        kw in domain
        for kw in ["blog", "medium.com", "substack.com", "wordpress.com"]
    ):
        return "blog"

    # Policy/reports
    if any(
        kw in domain
        for kw in [
            "gov",
            "whitehouse",
            "europa.eu",
            "un.org",
            "oecd.org",
            "who.int",
        ]
    ):
        return "policy"
    if ref_type == "techreport":
        return "report"

    # Default to paper for academic domains
    if domain in OPEN_DOMAINS or domain in PAYWALL_DOMAINS:
        return "paper"
    if "arxiv.org" in domain:
        return "paper"

    # Conference/journal papers
    if ref_type in ("conference", "inproceedings", "article", "journal"):
        return "paper"

    # Misc
    if ref_type == "misc":
        return "report"

    return "paper"


def classify_access_type(url, status_code, final_url, ref_data):
    """Classify how accessible the content is."""
    domain = urlparse(url).netloc.lower()
    final_domain = urlparse(final_url).netloc.lower() if final_url else domain
    source_type = classify_source_type(url, ref_data)

    # DOI links that fail are typically paywall/abstract, not truly unavailable
    if status_code is None or status_code >= 400:
        if "doi.org" in domain or final_domain in PAYWALL_DOMAINS:
            return "abstract_only"
        if source_type == "book":
            return "book"
        return "unavailable"

    if source_type == "book":
        return "book"

    if domain in OPEN_DOMAINS or "arxiv.org" in domain:
        return "open"

    if final_domain in PAYWALL_DOMAINS or domain in PAYWALL_DOMAINS:
        return "abstract_only"

    if domain in NEWS_DOMAINS or final_domain in NEWS_DOMAINS:
        return "paywall"

    # Default: assume open if we got a 200
    if status_code == 200:
        return "open"

    return "open"


def check_url(url):
    """Check a single URL and return metadata."""
    result = {
        "url": url,
        "official_url": None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "http_status": None,
        "final_url": None,
        "accessible": False,
        "access_type": "unavailable",
        "source_type": "paper",
        "page_title": "",
        "abstract": "",
        "error": None,
    }

    try:
        # Create SSL context that doesn't verify (some academic sites have bad certs)
        ctx = ssl.create_default_context()

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as response:
            result["http_status"] = response.status
            result["final_url"] = response.url
            result["accessible"] = True

            # Read response body (limit to 500KB to avoid huge pages)
            content_type = response.headers.get("Content-Type", "")
            if "text/html" in content_type or "application/xhtml" in content_type:
                body = response.read(500_000).decode("utf-8", errors="replace")

                # Extract title and meta
                parser = TitleExtractor()
                try:
                    parser.feed(body)
                except Exception:
                    pass

                result["page_title"] = parser.title[:500] if parser.title else ""

                # Extract abstract based on domain
                if "arxiv.org" in url:
                    result["abstract"] = extract_arxiv_abstract(body)
                elif parser.abstract:
                    result["abstract"] = parser.abstract[:1000]
                elif parser.og_description:
                    result["abstract"] = parser.og_description[:1000]
            else:
                # PDF or other binary — just record the status
                result["page_title"] = ""

    except urllib.error.HTTPError as e:
        result["http_status"] = e.code
        result["error"] = f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        result["error"] = f"URL Error: {str(e.reason)}"
    except TimeoutError:
        result["error"] = "Timeout after 15 seconds"
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {str(e)}"

    return result


def save_audit(audit_data):
    """Write audit data to disk (crash-safe)."""
    tmp_path = AUDIT_FILE.with_suffix(".json.tmp")
    with open(tmp_path, "w") as f:
        json.dump(audit_data, f, indent=2, ensure_ascii=False)
    tmp_path.rename(AUDIT_FILE)


def main():
    parser = argparse.ArgumentParser(description="Check reference URLs")
    parser.add_argument(
        "--force", action="store_true", help="Re-check all URLs"
    )
    parser.add_argument(
        "--only-failed", action="store_true", help="Only retry failed URLs"
    )
    args = parser.parse_args()

    # Load references
    with open(REFS_FILE) as f:
        references = json.load(f)

    # Load existing audit data
    if AUDIT_FILE.exists():
        with open(AUDIT_FILE) as f:
            audit_data = json.load(f)
    else:
        audit_data = {"meta": {}, "url_checks": {}, "citations": []}

    if "url_checks" not in audit_data:
        audit_data["url_checks"] = {}

    url_checks = audit_data["url_checks"]

    # Build the list of URLs to check
    to_check = []
    for bib_key, ref_data in references.items():
        url = ref_data.get("url", "")
        if not url:
            continue

        if args.force:
            to_check.append((bib_key, url, ref_data))
        elif args.only_failed:
            existing = url_checks.get(bib_key, {})
            if existing.get("error") or not existing.get("accessible"):
                to_check.append((bib_key, url, ref_data))
        else:
            if bib_key not in url_checks:
                to_check.append((bib_key, url, ref_data))

    # Sort: arXiv first (most reliable), then DOI, then other
    def sort_key(item):
        _, url, _ = item
        if "arxiv.org" in url:
            return (0, url)
        if "doi.org" in url:
            return (1, url)
        return (2, url)

    to_check.sort(key=sort_key)

    print(f"Phase 2: Checking {len(to_check)} URLs ({len(references)} total refs)")
    print(f"  Already checked: {len(url_checks)}")
    print(f"  Remaining: {len(to_check)}")

    if not to_check:
        print("Nothing to do.")
        return

    # Process URLs
    success = 0
    failed = 0

    for i, (bib_key, url, ref_data) in enumerate(to_check, 1):
        print(f"  [{i}/{len(to_check)}] {bib_key}: {url[:80]}...", end="", flush=True)

        result = check_url(url)
        result["source_type"] = classify_source_type(url, ref_data)
        result["access_type"] = classify_access_type(
            url, result["http_status"], result.get("final_url"), ref_data
        )

        # For books/paywalled content, set official_url
        if result["access_type"] in ("book", "paywall", "abstract_only"):
            result["official_url"] = result["final_url"] or url

        url_checks[bib_key] = result

        if result["error"]:
            failed += 1
            print(f" FAIL ({result['error'][:50]})")
        else:
            success += 1
            status = result["http_status"]
            access = result["access_type"]
            print(f" OK ({status}, {access})")

        # Save after each URL (crash-safe)
        save_audit(audit_data)

        # Rate limit: 1 second between requests
        if i < len(to_check):
            time.sleep(1)

    # Summary
    print(f"\nDone. {success} succeeded, {failed} failed.")

    # Stats
    access_types = {}
    source_types = {}
    for check in url_checks.values():
        at = check.get("access_type", "unknown")
        st = check.get("source_type", "unknown")
        access_types[at] = access_types.get(at, 0) + 1
        source_types[st] = source_types.get(st, 0) + 1

    print("\nAccess types:")
    for at, count in sorted(access_types.items(), key=lambda x: -x[1]):
        print(f"  {at}: {count}")
    print("\nSource types:")
    for st, count in sorted(source_types.items(), key=lambda x: -x[1]):
        print(f"  {st}: {count}")


if __name__ == "__main__":
    main()

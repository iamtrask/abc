#!/usr/bin/env python3
"""
Collect first-page screenshots for all references.

Strategy:
  1. arXiv papers  → download PDF, render page 1
  2. DOI / publisher links → try to find PDF, render page 1
  3. Web pages (news, blogs, reports) → Playwright screenshot
  4. Books → try Open Library cover, else Playwright screenshot

Output:  assets/screenshots/<bib_key>.jpg  (800px wide, retina-ready @2x)
Updates: data/references.json  screenshot field

Usage:
  python3 scripts/collect_screenshots.py              # process all missing
  python3 scripts/collect_screenshots.py --force       # re-process all
  python3 scripts/collect_screenshots.py --key foo_2020  # process one ref
  python3 scripts/collect_screenshots.py --dry-run     # just show what would happen
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import fitz  # pymupdf
import requests
from PIL import Image

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
REFS_PATH = ROOT / "data" / "references.json"
OUT_DIR = ROOT / "assets" / "screenshots"
TARGET_WIDTH = 800  # pixels (renders @2x; display at 400px CSS for retina)
JPEG_QUALITY = 82
REQUEST_TIMEOUT = 30
RATE_LIMIT = 1.0  # seconds between network requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_refs():
    with open(REFS_PATH) as f:
        return json.load(f)


def save_refs(refs):
    with open(REFS_PATH, "w") as f:
        json.dump(refs, f, indent=2, ensure_ascii=False)
        f.write("\n")


def rate_limit():
    time.sleep(RATE_LIMIT)


def extract_arxiv_id(url):
    """Extract arXiv ID from URL like arxiv.org/abs/2301.12345 or arxiv.org/pdf/2301.12345"""
    if not url:
        return None
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+?)(?:\.pdf)?$", url)
    return m.group(1) if m else None


def arxiv_pdf_url(arxiv_id):
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


def download_pdf(url):
    """Download a PDF to a temp file. Returns path or None."""
    try:
        rate_limit()
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT,
                            allow_redirects=True, stream=True)
        ct = resp.headers.get("Content-Type", "")
        if resp.status_code != 200:
            return None
        # Check it's actually a PDF
        if "pdf" not in ct.lower() and not resp.content[:5] == b"%PDF-":
            return None
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(resp.content)
        tmp.close()
        return tmp.name
    except Exception as e:
        print(f"    Download failed: {e}")
        return None


def render_pdf_page1(pdf_path, out_path):
    """Render first page of PDF to JPEG at TARGET_WIDTH."""
    try:
        doc = fitz.open(pdf_path)
        page = doc[0]
        # Scale to target width
        scale = TARGET_WIDTH / page.rect.width
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img.save(out_path, "JPEG", quality=JPEG_QUALITY)
        doc.close()
        return True
    except Exception as e:
        print(f"    PDF render failed: {e}")
        return False


def try_resolve_pdf_from_doi(url):
    """Try to find a direct PDF link from a DOI or publisher page."""
    try:
        rate_limit()
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT,
                            allow_redirects=True)
        final_url = resp.url
        # Check if we landed on a PDF
        ct = resp.headers.get("Content-Type", "")
        if "pdf" in ct.lower():
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.write(resp.content)
            tmp.close()
            return tmp.name

        # Try common PDF URL patterns from the final resolved URL
        parsed = urlparse(final_url)

        # arXiv redirect
        aid = extract_arxiv_id(final_url)
        if aid:
            return download_pdf(arxiv_pdf_url(aid))

        # Springer
        if "springer.com" in parsed.netloc or "link.springer.com" in parsed.netloc:
            # /article/10.1007/... → /content/pdf/10.1007/...pdf
            m = re.search(r"/article/(10\.\d+/[^\s?#]+)", final_url)
            if m:
                pdf_url = f"https://link.springer.com/content/pdf/{m.group(1)}.pdf"
                return download_pdf(pdf_url)

        # ACL Anthology
        if "aclanthology.org" in parsed.netloc:
            pdf_url = final_url.rstrip("/") + ".pdf"
            return download_pdf(pdf_url)

        # NeurIPS proceedings
        if "proceedings.neurips.cc" in parsed.netloc:
            pdf_url = final_url.replace("/hash/", "/file/").replace("-Abstract.html", "-Paper.pdf")
            return download_pdf(pdf_url)

        # proceedings.mlr.press (PMLR)
        if "proceedings.mlr.press" in parsed.netloc:
            m = re.search(r"(v\d+/[^/]+?)(?:\.html)?$", final_url)
            if m:
                pdf_url = f"https://proceedings.mlr.press/{m.group(1)}/{m.group(1).split('/')[-1]}.pdf"
                return download_pdf(pdf_url)

        return None
    except Exception as e:
        print(f"    DOI resolve failed: {e}")
        return None


def try_open_library_cover(ref):
    """Try to get a book cover from Open Library by ISBN or title."""
    # Check if we have an ISBN in the URL or data
    url = ref.get("url") or ""
    title = ref.get("title") or ""

    # Try by title search
    try:
        rate_limit()
        search_url = f"https://openlibrary.org/search.json?title={requests.utils.quote(title)}&limit=1"
        resp = requests.get(search_url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            docs = data.get("docs", [])
            if docs and docs[0].get("cover_i"):
                cover_id = docs[0]["cover_i"]
                cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                rate_limit()
                img_resp = requests.get(cover_url, timeout=REQUEST_TIMEOUT)
                if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                    return img_resp.content
    except Exception:
        pass
    return None


def screenshot_webpage(url, out_path):
    """Take a screenshot of a webpage using Playwright."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 960},
                device_scale_factor=2,
            )
            page = context.new_page()
            page.goto(url, timeout=30000, wait_until="networkidle")
            # Wait a moment for lazy-loaded content
            page.wait_for_timeout(1500)
            # Screenshot the visible viewport
            png_bytes = page.screenshot(type="png")
            browser.close()

        # Convert to JPEG at target width
        import io
        img = Image.open(io.BytesIO(png_bytes))
        # Crop to roughly paper-like aspect ratio (letter page ~8.5:11)
        w, h = img.size
        target_h = int(w * 11 / 8.5)
        if h > target_h:
            img = img.crop((0, 0, w, target_h))
        # Resize to target width
        scale = TARGET_WIDTH / img.width
        img = img.resize((TARGET_WIDTH, int(img.height * scale)), Image.LANCZOS)
        img.save(out_path, "JPEG", quality=JPEG_QUALITY)
        return True
    except Exception as e:
        print(f"    Playwright screenshot failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Per-reference processing
# ---------------------------------------------------------------------------

# Global browser instance for webpage screenshots (reuse across refs)
_browser = None
_browser_context = None


def get_browser():
    global _browser, _browser_context
    if _browser is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(headless=True)
        _browser_context = _browser.new_context(
            viewport={"width": 1280, "height": 960},
            device_scale_factor=2,
        )
    return _browser_context


def screenshot_webpage_reuse(url, out_path):
    """Take a screenshot using a shared browser instance."""
    try:
        import io
        ctx = get_browser()
        page = ctx.new_page()
        try:
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)  # let images/fonts load
            png_bytes = page.screenshot(type="png")
        finally:
            page.close()

        img = Image.open(io.BytesIO(png_bytes))
        w, h = img.size
        target_h = int(w * 11 / 8.5)
        if h > target_h:
            img = img.crop((0, 0, w, target_h))
        scale = TARGET_WIDTH / img.width
        img = img.resize((TARGET_WIDTH, int(img.height * scale)), Image.LANCZOS)
        img.save(out_path, "JPEG", quality=JPEG_QUALITY)
        return True
    except Exception as e:
        print(f"    Playwright screenshot failed: {e}")
        return False


def safe_filename(key):
    """Sanitize a BibTeX key for use as a filename."""
    return re.sub(r'[/:*?"<>|]', '_', key)


def process_ref(key, ref, force=False):
    """Process a single reference. Returns the screenshot path or None."""
    fname = safe_filename(key)
    out_path = OUT_DIR / f"{fname}.jpg"
    rel_path = f"assets/screenshots/{fname}.jpg"

    if not force and out_path.exists() and ref.get("screenshot"):
        return None  # already done

    url = ref.get("url") or ""
    ref_type = ref.get("type", "")
    title = ref.get("title", "")

    print(f"  [{key}] {title[:60]}...")
    print(f"    URL: {url}")

    # Strategy 1: arXiv — direct PDF
    arxiv_id = extract_arxiv_id(url)
    if arxiv_id:
        print(f"    → arXiv PDF ({arxiv_id})")
        pdf_path = download_pdf(arxiv_pdf_url(arxiv_id))
        if pdf_path:
            if render_pdf_page1(pdf_path, str(out_path)):
                os.unlink(pdf_path)
                print(f"    ✓ saved {rel_path}")
                return rel_path
            os.unlink(pdf_path)

    # Strategy 2: DOI / publisher — try to find PDF
    if url and ("doi.org" in url or any(d in url for d in [
        "aclanthology.org", "proceedings.neurips.cc", "proceedings.mlr.press",
        "springer.com", "pnas.org", "eprint.iacr.org", "techrxiv.org"
    ])):
        print(f"    → trying publisher PDF")
        pdf_path = try_resolve_pdf_from_doi(url)
        if pdf_path:
            if render_pdf_page1(pdf_path, str(out_path)):
                os.unlink(pdf_path)
                print(f"    ✓ saved {rel_path}")
                return rel_path
            os.unlink(pdf_path)

    # Strategy 3: Books — try Open Library cover
    if ref_type == "book":
        print(f"    → trying Open Library cover")
        cover_data = try_open_library_cover(ref)
        if cover_data:
            import io
            img = Image.open(io.BytesIO(cover_data))
            scale = TARGET_WIDTH / img.width
            img = img.resize((TARGET_WIDTH, int(img.height * scale)), Image.LANCZOS)
            img.save(str(out_path), "JPEG", quality=JPEG_QUALITY)
            print(f"    ✓ saved {rel_path} (book cover)")
            return rel_path

    # Strategy 4: Direct PDF link
    if url and url.lower().endswith(".pdf"):
        print(f"    → direct PDF link")
        pdf_path = download_pdf(url)
        if pdf_path:
            if render_pdf_page1(pdf_path, str(out_path)):
                os.unlink(pdf_path)
                print(f"    ✓ saved {rel_path}")
                return rel_path
            os.unlink(pdf_path)

    # Strategy 5: Webpage screenshot (fallback)
    if url:
        print(f"    → webpage screenshot")
        if screenshot_webpage_reuse(url, str(out_path)):
            print(f"    ✓ saved {rel_path}")
            return rel_path

    print(f"    ✗ FAILED — no screenshot obtained")
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Collect reference screenshots")
    parser.add_argument("--force", action="store_true", help="Re-process all refs")
    parser.add_argument("--key", type=str, help="Process a single ref by key")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument("--limit", type=int, default=0, help="Max refs to process (0=all)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    refs = load_refs()

    if args.key:
        if args.key not in refs:
            print(f"Key '{args.key}' not found in references.json")
            sys.exit(1)
        keys = [args.key]
    else:
        keys = list(refs.keys())

    # Filter to only those needing work
    if not args.force:
        keys = [k for k in keys if not refs[k].get("screenshot")
                or not (OUT_DIR / f"{k}.jpg").exists()]

    if args.limit:
        keys = keys[:args.limit]

    print(f"References to process: {len(keys)} / {len(refs)}")

    if args.dry_run:
        for k in keys:
            url = refs[k].get("url") or "(no url)"
            print(f"  {k}: {url}")
        return

    succeeded = 0
    failed = 0

    for i, k in enumerate(keys):
        print(f"\n[{i+1}/{len(keys)}]")
        result = process_ref(k, refs[k], force=args.force)
        if result:
            refs[k]["screenshot"] = result
            succeeded += 1
            # Save incrementally every 10 refs
            if succeeded % 10 == 0:
                save_refs(refs)
        else:
            failed += 1

    # Final save
    save_refs(refs)

    print(f"\n{'='*50}")
    print(f"Done. Succeeded: {succeeded}, Failed: {failed}")
    total_with = sum(1 for r in refs.values() if r.get("screenshot"))
    print(f"Total with screenshots: {total_with} / {len(refs)}")


if __name__ == "__main__":
    main()

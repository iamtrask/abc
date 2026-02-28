# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Static website for Andrew Trask's thesis "Attribution-Based Control in AI Systems," hosted at attribution-based-control.ai via GitHub Pages.

## Tech Stack

- Pure HTML/CSS/JavaScript — no frameworks, no build system, no package manager
- MathJax (CDN) for LaTeX equation rendering
- Google Fonts (Source Serif 4)
- Analytics: Google Analytics + Plausible

## Running Locally

```bash
python -m http.server 8000
# or: npx http-server
```

No build step, linting, or tests exist.

## Workflow

This repo is maintained by Bennett Farkas on behalf of Andrew Trask. All changes go through feature branches and pull requests for Andrew to review. **Never push directly to `main`** — always create a PR and leave it for Andrew's approval.

## Architecture

**Page structure:** Each HTML page follows the same layout pattern:
- Sticky top navigation bar (hides on scroll down, shows on scroll up)
- Left sidebar with table of contents (sticky, visible at 1200px+)
- Main content area (max-width 720px)
- Right margin area for citation sidebar cards and sidenotes (visible at 1400px+)

**Core files:**
- `index.html` (Chapter I: Introduction), `chapter2.html` through `chapter5.html`, `appendix1.html`, `appendix2.html`, `references.html`, `about.html` — individual pages. There is no `chapter1.html`; `index.html` serves as Chapter I.
- `styles.css` — all styling, responsive breakpoints at 768/1024/1200/1400/1600px
- `main.js` — scroll spy, dynamic header, sidenote/track positioning, overlap prevention, reference backlinks
- `citation-card.js` — sidebar citation cards, sidenote cards, hover/highlight logic (IIFE, ~580 lines)
- `thesis.txt` — original LaTeX source
- `1411.3146/` — image assets (~200+ PNGs)

**Content conventions:** Sections use anchor IDs for deep linking. Figures use `<figure>`/`<figcaption>`. Tables use `.data-table` class. Each chapter page has a `.chapter-nav` footer with prev/next links. `about.html` uses inline `<style>` for its timeline layout rather than `styles.css`.

## Reference System

### Where a single reference lives (all must stay in sync)

A reference appears in up to **7 locations**. When editing or fixing a reference, update ALL of these:

| Location | What to update |
|----------|---------------|
| `1411.3146/references.bib` | BibTeX entry (357 entries, each appears once) |
| Chapter HTML (`index.html`, `chapter2.html`, etc.) | `<li id="ref-N">` in the `<section class="references">` at the bottom |
| Chapter HTML body text | `<a href="#ref-N" class="cite">Author et al., Year</a>` inline citations |
| `data/chapter-map.json` | Mapping: `"chapter-slug": {"N": "bibtex_key"}` |
| `data/references.json` | Full metadata entry keyed by BibTeX key |
| `references.html` | **Separate hardcoded copy** of all references (does NOT auto-update from chapters) |
| `assets/screenshots/{bibtex_key}.jpg` | Page screenshot (referenced by `references.json` `screenshot` field) |

### Per-chapter numbering

Each HTML file has its own `ref-1`, `ref-2`, etc. — ref-5 in `index.html` is a completely different paper than ref-5 in `chapter2.html`. The `data/chapter-map.json` file maps these local numbers to global BibTeX keys.

### Citation format in HTML

```html
<!-- In body text -->
<a href="#ref-12" class="cite">Author et al., 2024</a>

<!-- In reference list (at bottom of each chapter) -->
<li id="ref-12"><span class="authors">Author, A., Author, B.</span> (2024).
    <a href="https://doi.org/..."><span class="title">Paper title.</span></a>
    <span class="venue">Journal Name, 1(2), 3–4</span>.</li>
```

### Data files (`data/`)

| File | Purpose | Key schema |
|------|---------|------------|
| `references.json` | 180 unique references | `{bibtex_key: {title, authors[], year, venue, venueShort, url, doi, type, screenshot}}` |
| `authors.json` | 610 unique authors | `{author_key: {displayName, firstName, lastName, affiliation, headshot, links{}, _enrichment{}}}` |
| `chapter-map.json` | Per-chapter ref→key mapping | `{chapter_slug: {ref_num: bibtex_key}}` |
| `paper-cache.json` | Cached Semantic Scholar lookups | Used by `enrich_authors.py` |
| `citation-audit.json` | Audit of all 264 citations | Used by audit scripts |

### Adding a new reference (complete checklist)

1. **BibTeX**: Add entry to `1411.3146/references.bib`. Always include a URL or DOI to avoid fuzzy-match errors.
2. **Chapter HTML reference list**: Add `<li id="ref-N">` at the end of the chapter's `<section class="references"><ol>...</ol></section>`
3. **Chapter HTML body text**: Add `<a href="#ref-N" class="cite">Author et al., Year</a>` where the citation belongs
4. **Chapter map**: Add `"N": "bibtex_key"` under the chapter slug in `data/chapter-map.json`
5. **Rebuild databases**: `python3 scripts/build_ref_db.py` — regenerates `references.json`, `chapter-map.json`, `authors.json`
6. **Enrich authors** (optional): `python3 scripts/enrich_authors.py` — adds headshots, affiliations, Scholar links
7. **Collect screenshot** (optional): `python3 scripts/collect_screenshots.py` — downloads page screenshot
8. **Update references.html**: Manually add the reference to `references.html` (it has its own separate copy that doesn't auto-update)

### Fixing an existing reference

When correcting a URL, title, author name, or any metadata:

1. **Fix in the chapter HTML** `<li id="ref-N">` entry (correct the text, URL, etc.)
2. **Fix in BibTeX** `1411.3146/references.bib`
3. **Fix in `references.html`** — find the same reference and update it there too
4. **Rebuild databases**: `python3 scripts/build_ref_db.py`
5. **Re-collect screenshot** if URL changed: `python3 scripts/collect_screenshots.py`

### Known pitfalls

- Papers with similar titles (e.g., "Deep learning" by LeCun vs Goodfellow) can be incorrectly fuzzy-matched by `build_ref_db.py`. Always add a URL/DOI to the BibTeX entry so URL matching takes priority.
- **`build_ref_db.py` is merge-safe** — it loads existing `references.json` and `authors.json` before writing, preserving enrichment fields (screenshots, headshots, affiliations, Scholar links). However, it regenerates `chapter-map.json` entirely from BibTeX + HTML matching, so any manual edits to that file will be overwritten.
- `references.html` has its own separate copy of all 256 references (pre-dedup numbering). It is NOT auto-generated. Changes to per-chapter refs don't propagate there.
- The BibTeX file was deduplicated (Feb 2026). Each entry now appears exactly once — no need for `replace_all` when editing.

## Citation Sidebar Cards

`citation-card.js` creates Google Comments-style cards in the right margin for each citation. Only visible at 1400px+ screen width.

**Data pipeline**: Fetches `chapter-map.json`, `references.json`, `authors.json` → maps `#ref-N` to BibTeX key → builds card with screenshot, title, meta, author avatars → positions in flex track per section.

**Card states**:
- Default: compact (faded, grayscale) — screenshot, title, meta, avatar row
- Highlighted (cite hover): full opacity, track shifts to align card with cite
- Expanded (card hover): shows author detail panel (photo, affiliation, links)

**Sidenotes**: Also managed by `citation-card.js` on desktop — cloned into sidebar track cards alongside citations. Original sidenote `<div>` elements are hidden when tracks are active.

**Positioning**: `main.js` `alignMarginItems()` handles initial track placement and overlap prevention between sidenotes and citation tracks (3-phase algorithm: position sidenotes, position citation tracks, resolve overlaps with 12px gap). `citation-card.js` handles hover-triggered alignment via `translateY` on the track.

**Key breakpoint behavior**: Citation cards and sidebar sidenotes are completely disabled below 1400px. The TOC sidebar disappears below 1200px. Below 768px is a single-column mobile layout.

## Scripts

**Core pipeline:**

| Script | Purpose | Usage |
|--------|---------|-------|
| `build_ref_db.py` | Parse BibTeX + HTML → generate `references.json`, `chapter-map.json`, `authors.json` | `python3 scripts/build_ref_db.py` |
| `enrich_authors.py` | Add S2/Scholar profiles, headshots | `python3 scripts/enrich_authors.py --phase {papers,match,s2-authors,scholar,headshots}` |
| `collect_screenshots.py` | Download page screenshots for references | `python3 scripts/collect_screenshots.py` |

**Auditing and maintenance:**

| Script | Purpose | Usage |
|--------|---------|-------|
| `audit_refs.py` | Full audit of HTML citations vs reference databases (8-point validation) | `python3 scripts/audit_refs.py` |
| `audit_screenshots.py` | Compare screenshots on disk vs references.json | `python3 scripts/audit_screenshots.py` |
| `check_urls.py` | HTTP HEAD check all URLs in references.json | `python3 scripts/check_urls.py` |

**Claim verification pipeline** (extract → check URLs → verify):

| Script | Purpose | Usage |
|--------|---------|-------|
| `extract_claims.py` | Extract 1–3 sentence claim contexts around each citation | `python3 scripts/extract_claims.py` |
| `verify_claims.py` | Interactive claim-reference alignment verification | `python3 scripts/verify_claims.py` |

**External Python dependencies** (no requirements.txt — install manually as needed):
- `requests` — used by `collect_screenshots.py`, `enrich_authors.py`
- `playwright` — used by `collect_screenshots.py` for web screenshots
- `pymupdf` (`import fitz`) — used by `collect_screenshots.py` for PDF rendering
- `Pillow` (`from PIL import Image`) — used by `audit_screenshots.py`
- SerpAPI (via `urllib`, requires `SERPAPI_KEY` env var) — used by `enrich_authors.py` Phase 4

## Asset Directories

| Directory | Contents | Naming convention |
|-----------|----------|-------------------|
| `assets/screenshots/` | 179 reference page screenshots (800px JPEG) | `{bibtex_key}.jpg` |
| `assets/headshots/` | 322 author headshot photos + `default.svg` | `{author_key}.jpg` where key is `lastname_firstname` |
| `1411.3146/` | Original thesis images (~200 PNGs) | Various |

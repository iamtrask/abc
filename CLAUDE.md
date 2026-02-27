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
- Right margin area for ASCII art decorations and sidenotes

**Files:**
- `index.html` through `chapter5.html`, `appendix1.html`, `appendix2.html`, `about.html` — individual pages
- `styles.css` — all styling, responsive design with breakpoints at 768/1024/1200/1600px
- `main.js` — scroll spy (active TOC highlighting), dynamic header show/hide, sidenote positioning and overlap prevention
- `thesis.txt` — original LaTeX source
- `1411.3146/` — image assets (~200+ PNGs)

**Content conventions:** Sections use anchor IDs for deep linking. Figures use `<figure>`/`<figcaption>`. Tables use `.data-table` class. Sidenotes are positioned in margins on desktop and inline on mobile.

## Reference System

**Source of truth:** `1411.3146/references.bib` (BibTeX, ~358 entries, each entry appears twice due to a LaTeX-to-HTML conversion artifact — always update both copies with `replace_all`).

**Per-chapter numbering:** Each HTML file has its own `ref-1`, `ref-2`, etc. — ref-5 in `index.html` is a completely different paper than ref-5 in `chapter2.html`.

**Citation format in HTML:**
```html
<!-- In body text -->
<a href="#ref-12" class="cite">Author et al., 2024</a>

<!-- In reference list (at bottom of each chapter) -->
<li id="ref-12"><span class="authors">Author, A., Author, B.</span> (2024).
    <a href="https://doi.org/..."><span class="title">Paper title.</span></a>
    <span class="venue">Journal Name, 1(2), 3–4</span>.</li>
```

**Data files (`data/`):**
- `chapter-map.json` — maps `(chapter-slug, ref-number)` → BibTeX key
- `references.json` — 178 unique references with full metadata
- `authors.json` — 607 unique authors

**Regenerating databases:** `python3 scripts/build_ref_db.py` — parses BibTeX + HTML, matches refs by URL then fuzzy title, writes all three JSON files. Note: this overwrites `chapter-map.json`, so manual edits to that file must be re-applied after running.

**Adding a new reference:**
1. Add the BibTeX entry to `1411.3146/references.bib` (in both halves of the file)
2. Add the `<li id="ref-N">` entry at the end of the chapter's reference list
3. Add the `<a href="#ref-N" class="cite">` citation in the body text
4. Add the mapping to `data/chapter-map.json`
5. Run `python3 scripts/build_ref_db.py` to regenerate databases

**Known pitfalls:**
- Papers with similar titles (e.g., "Deep learning" by LeCun vs Goodfellow) can be incorrectly fuzzy-matched by the build script. Always add a URL/DOI to the BibTeX entry so URL matching takes priority.
- The `references.html` page has its own separate copy of all 256 references (pre-dedup numbering). Changes to per-chapter refs don't automatically propagate there.

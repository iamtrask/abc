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

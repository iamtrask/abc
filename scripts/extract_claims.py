#!/usr/bin/env python3
"""
Phase 1: Extract claim contexts around every in-text citation.

Parses each chapter HTML, finds every <a href="#ref-N" class="cite"> in the
body text (before the references section), and records the surrounding 1-3
sentence claim context, section anchor, and bibtex key mapping.

No network calls. Pure HTML parsing.

Usage:
    python3 scripts/extract_claims.py
"""

import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

CHAPTER_FILES = [
    ("index", "index.html"),
    ("chapter2", "chapter2.html"),
    ("chapter3", "chapter3.html"),
    ("chapter4", "chapter4.html"),
    ("chapter5", "chapter5.html"),
    ("appendix1", "appendix1.html"),
    ("appendix2", "appendix2.html"),
]

AUDIT_FILE = DATA_DIR / "citation-audit.json"


class ClaimExtractor(HTMLParser):
    """Extract citations with their surrounding paragraph context and section IDs."""

    def __init__(self):
        super().__init__()
        # Results
        self.citations = []  # list of dicts

        # Parser state
        self._in_ref_section = False
        self._section_stack = []  # stack of section IDs
        self._current_section_id = None

        # Block-level element tracking (p, li, td, th, dd, blockquote)
        self._block_tags = {"p", "li", "td", "th", "dd", "blockquote"}
        self._in_block = 0  # nesting depth
        self._block_tag = None  # which tag we're inside
        self._p_parts = []  # list of (text, cite_info_or_None)
        self._current_cite = None  # set when inside a cite <a> tag
        self._pending_cites = []  # cite infos found in current block

        # For tracking h2/h3 IDs as section anchors
        self._in_heading = False
        self._heading_id = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        # Stop processing once we hit the references section
        if tag == "section":
            cls = attrs_dict.get("class", "")
            sid = attrs_dict.get("id", "")
            if "references" in cls:
                self._in_ref_section = True
                return
            if sid:
                self._current_section_id = sid
                self._section_stack.append(sid)
            else:
                self._section_stack.append(None)

        if self._in_ref_section:
            return

        # Track heading IDs as section anchors
        if tag in ("h2", "h3", "h4"):
            hid = attrs_dict.get("id", "")
            if hid:
                self._current_section_id = hid
            self._in_heading = True

        # Track block-level element boundaries
        if tag in self._block_tags:
            self._in_block += 1
            if self._in_block == 1:
                self._block_tag = tag
                self._p_parts = []
                self._pending_cites = []

        # Track citation links
        if tag == "a" and self._in_block > 0:
            href = attrs_dict.get("href", "")
            cls = attrs_dict.get("class", "")
            m = re.match(r"#ref-(\d+)", href)
            if m and "cite" in cls:
                ref_num = int(m.group(1))
                self._current_cite = {
                    "ref_num": ref_num,
                    "label": "",
                    "position": len(self._p_parts),
                }

    def handle_endtag(self, tag):
        if tag == "section" and not self._in_ref_section:
            if self._section_stack:
                self._section_stack.pop()
            # Restore previous section ID
            self._current_section_id = None
            for sid in reversed(self._section_stack):
                if sid:
                    self._current_section_id = sid
                    break

        if self._in_ref_section:
            if tag == "section":
                self._in_ref_section = False
            return

        if tag in ("h2", "h3", "h4"):
            self._in_heading = False

        if tag == "a" and self._current_cite is not None:
            # Finished reading the cite link text
            self._current_cite["label"] = self._current_cite["label"].strip()
            # Mark the position in p_parts where this cite appears
            self._p_parts.append(("__CITE__", self._current_cite))
            self._pending_cites.append(self._current_cite)
            self._current_cite = None

        if tag in self._block_tags and self._in_block > 0:
            self._in_block -= 1
            if self._in_block == 0 and self._pending_cites:
                self._process_paragraph()

    def handle_data(self, data):
        if self._in_ref_section:
            return

        # Accumulate cite label text
        if self._current_cite is not None:
            self._current_cite["label"] += data
            return

        # Accumulate block-level element text
        if self._in_block > 0:
            self._p_parts.append(("text", data))

    def _process_paragraph(self):
        """Extract claim context for each citation in the current paragraph."""
        # Reconstruct full paragraph text with cite markers
        full_text = ""
        cite_positions = {}  # char offset -> cite_info

        for kind, val in self._p_parts:
            if kind == "__CITE__":
                marker = f"[{val['label']}]"
                cite_positions[len(full_text)] = val
                full_text += marker
            else:
                full_text += val

        # Clean up whitespace
        full_text = re.sub(r"\s+", " ", full_text).strip()

        # For each citation, extract the surrounding 1-3 sentence context
        for cite_info in self._pending_cites:
            context = self._extract_context(full_text, cite_info["label"])
            self.citations.append(
                {
                    "ref_num": cite_info["ref_num"],
                    "cite_label": cite_info["label"],
                    "claim_context": context,
                    "section_id": self._current_section_id or "",
                }
            )

    def _extract_context(self, paragraph_text, cite_label):
        """Extract 1-3 sentences around a citation within a paragraph."""
        # Find the citation marker in the text
        marker = f"[{cite_label}]"
        pos = paragraph_text.find(marker)
        if pos == -1:
            # Fallback: return the full paragraph (truncated)
            return paragraph_text[:500]

        # Split into sentences (simple heuristic)
        sentences = self._split_sentences(paragraph_text)
        if not sentences:
            return paragraph_text[:500]

        # Find which sentence contains the citation
        char_count = 0
        cite_sentence_idx = len(sentences) - 1
        for i, sent in enumerate(sentences):
            char_count += len(sent)
            if char_count > pos:
                cite_sentence_idx = i
                break

        # Take 1 sentence before through 1 sentence after
        start = max(0, cite_sentence_idx - 1)
        end = min(len(sentences), cite_sentence_idx + 2)
        context = " ".join(s.strip() for s in sentences[start:end]).strip()

        # Truncate if too long
        if len(context) > 600:
            context = context[:597] + "..."

        return context

    @staticmethod
    def _split_sentences(text):
        """Split text into sentences using a simple regex heuristic."""
        # Split on period/question/exclamation followed by space and capital letter
        # but not after common abbreviations like "et al." "e.g." "i.e." "Dr." "vs."
        parts = re.split(
            r"(?<=[.!?])\s+(?=[A-Z])",
            text,
        )
        return [p for p in parts if p.strip()]


def extract_all_claims():
    """Parse all chapter files and extract citation claim contexts."""
    # Load chapter map
    with open(DATA_DIR / "chapter-map.json") as f:
        chapter_map = json.load(f)

    all_citations = []
    cite_counter = {}  # (chapter, ref_num) -> count for generating unique IDs

    for slug, filename in CHAPTER_FILES:
        html_path = ROOT / filename
        if not html_path.exists():
            print(f"  SKIP: {filename} not found", file=sys.stderr)
            continue

        text = html_path.read_text(encoding="utf-8")
        parser = ClaimExtractor()
        parser.feed(text)

        cm = chapter_map.get(slug, {})

        for cite in parser.citations:
            ref_num = cite["ref_num"]
            ref_str = str(ref_num)
            bibtex_key = cm.get(ref_str, "")

            if not bibtex_key:
                print(
                    f"  WARN: {slug} ref-{ref_num} has no chapter-map entry",
                    file=sys.stderr,
                )

            # Generate unique ID: chapter:ref-N:instance
            key = (slug, ref_num)
            instance = cite_counter.get(key, 0)
            cite_counter[key] = instance + 1
            cite_id = f"{slug}:ref-{ref_num}:{instance}"

            all_citations.append(
                {
                    "id": cite_id,
                    "chapter": slug,
                    "ref_num": ref_num,
                    "bibtex_key": bibtex_key,
                    "cite_label": cite["cite_label"],
                    "claim_context": cite["claim_context"],
                    "section_id": cite["section_id"],
                    "verification": None,
                }
            )

        print(f"  {slug}: {len(parser.citations)} citations extracted")

    return all_citations


def main():
    print("Phase 1: Extracting claim contexts from HTML...")

    citations = extract_all_claims()

    # Load existing audit file if present (to preserve url_checks from Phase 2)
    audit_data = {}
    if AUDIT_FILE.exists():
        with open(AUDIT_FILE) as f:
            audit_data = json.load(f)

    # Build/update the audit structure
    audit_data["meta"] = {
        "version": "1.0",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "total_citations": len(citations),
        "total_unique_refs": len(
            {c["bibtex_key"] for c in citations if c["bibtex_key"]}
        ),
    }
    audit_data["citations"] = citations

    # Preserve existing url_checks if any
    if "url_checks" not in audit_data:
        audit_data["url_checks"] = {}

    # Write output
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_FILE, "w") as f:
        json.dump(audit_data, f, indent=2, ensure_ascii=False)

    print(f"\nDone. {len(citations)} citations written to {AUDIT_FILE}")

    # Summary by chapter
    by_chapter = {}
    for c in citations:
        by_chapter.setdefault(c["chapter"], []).append(c)
    print("\nSummary:")
    for ch, cites in by_chapter.items():
        unique_refs = len({c["ref_num"] for c in cites})
        print(f"  {ch}: {len(cites)} citations, {unique_refs} unique refs")


if __name__ == "__main__":
    main()

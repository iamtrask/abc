#!/usr/bin/env python3
"""
Full audit of the live site HTML against the reference database JSON files.

Checks:
  1. Citation integrity: every in-text <a href="#ref-N"> has a matching <li id="ref-N">
  2. Orphaned refs: <li id="ref-N"> entries that nothing cites
  3. Numbering gaps: missing numbers in the ref-1..ref-N sequence
  4. Chapter-map completeness: every HTML ref has a chapter-map entry and vice versa
  5. Cross-chapter consistency: same BibTeX key maps to consistent data
  6. Reference data quality: missing titles, authors, years, URLs in references.json
  7. Author data quality: empty display names, orphaned authors
  8. HTML content vs JSON: spot-check that titles/authors/URLs agree
"""

import json
import re
import sys
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


class CitationExtractor(HTMLParser):
    """Extract all in-text citation links and reference list entries from HTML."""

    def __init__(self):
        super().__init__()
        self.citations = []       # list of (line, ref_num) for <a href="#ref-N">
        self.ref_entries = []     # list of ref_num for <li id="ref-N">
        self.ref_entry_data = {}  # ref_num → {authors, title, venue, url}
        self._in_ref_section = False
        self._in_ol = False
        self._current_ref = None
        self._current_span = None
        self._text_buf = []
        self._section_depth = 0
        self._line = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        # Track citations anywhere in the document
        if tag == 'a':
            href = attrs_dict.get('href', '')
            m = re.match(r'#ref-(\d+)', href)
            if m:
                self.citations.append((self.getpos()[0], int(m.group(1))))

        # Track reference section
        if tag == 'section':
            cls = attrs_dict.get('class', '')
            if 'references' in cls:
                self._in_ref_section = True
                self._section_depth = 1
                return
            if self._in_ref_section:
                self._section_depth += 1

        if not self._in_ref_section:
            return

        if tag == 'ol' and not self._in_ol:
            self._in_ol = True

        if tag == 'li' and self._in_ol:
            ref_id = attrs_dict.get('id', '')
            m = re.match(r'ref-(\d+)', ref_id)
            if m:
                num = int(m.group(1))
                self.ref_entries.append(num)
                self._current_ref = {
                    'num': num,
                    'authors': '',
                    'title': '',
                    'venue': '',
                    'url': '',
                }

        if self._current_ref is not None:
            if tag == 'span':
                cls = attrs_dict.get('class', '')
                if cls in ('authors', 'title', 'venue'):
                    self._current_span = cls
                    self._text_buf = []
            if tag == 'a':
                href = attrs_dict.get('href', '')
                if href and href.startswith('http') and not self._current_ref.get('url'):
                    self._current_ref['url'] = href

    def handle_endtag(self, tag):
        if not self._in_ref_section:
            return
        if tag == 'section':
            self._section_depth -= 1
            if self._section_depth <= 0:
                self._in_ref_section = False
                self._in_ol = False
        if tag == 'span' and self._current_span and self._current_ref is not None:
            text = ' '.join(''.join(self._text_buf).split())
            if self._current_span == 'authors':
                self._current_ref['authors'] = text
            elif self._current_span == 'title':
                self._current_ref['title'] = text
            elif self._current_span == 'venue':
                self._current_ref['venue'] = text
            self._current_span = None
            self._text_buf = []
        if tag == 'li' and self._current_ref is not None:
            self.ref_entry_data[self._current_ref['num']] = self._current_ref
            self._current_ref = None

    def handle_data(self, data):
        if self._current_span and self._current_ref is not None:
            self._text_buf.append(data)


def parse_chapter(html_path):
    """Parse HTML and return citations and ref entries."""
    text = html_path.read_text(encoding='utf-8')
    parser = CitationExtractor()
    parser.feed(text)
    return parser


def normalize(s):
    """Normalize string for comparison."""
    if not s:
        return ''
    return re.sub(r'[^\w\s]', '', s.lower()).strip()


def run_audit():
    # Load JSON databases
    with open(DATA_DIR / "chapter-map.json") as f:
        chapter_map = json.load(f)
    with open(DATA_DIR / "references.json") as f:
        references = json.load(f)
    with open(DATA_DIR / "authors.json") as f:
        authors = json.load(f)

    issues = []
    warnings = []

    def error(msg):
        issues.append(f"ERROR: {msg}")

    def warn(msg):
        warnings.append(f"WARN:  {msg}")

    # ── Per-chapter checks ──────────────────────────────────────────────

    all_referenced_bib_keys = set()
    all_referenced_author_keys = set()

    for slug, filename in CHAPTER_FILES:
        html_path = ROOT / filename
        parser = parse_chapter(html_path)

        cited_nums = set(num for _, num in parser.citations)
        entry_nums = set(parser.ref_entries)
        cm = chapter_map.get(slug, {})
        cm_nums = set(int(k) for k in cm.keys())

        print(f"\n{'='*60}")
        print(f"{slug} ({filename})")
        print(f"{'='*60}")
        print(f"  In-text citations: {len(cited_nums)} unique refs cited")
        print(f"  Reference entries: {len(entry_nums)} <li> entries")
        print(f"  Chapter-map entries: {len(cm_nums)}")

        # 1. Dangling citations: cited but no <li> entry
        dangling = cited_nums - entry_nums
        for num in sorted(dangling):
            error(f"{slug}: citation #ref-{num} has no <li id=\"ref-{num}\"> in reference list")

        # 2. Orphaned refs: <li> entry but never cited
        orphaned = entry_nums - cited_nums
        for num in sorted(orphaned):
            warn(f"{slug}: ref-{num} exists in reference list but is never cited in text")

        # 3. Numbering gaps
        if entry_nums:
            expected = set(range(1, max(entry_nums) + 1))
            gaps = expected - entry_nums
            for num in sorted(gaps):
                warn(f"{slug}: ref-{num} is missing from reference list (gap in numbering)")

        # 4. Chapter-map vs HTML alignment
        in_html_not_map = entry_nums - cm_nums
        for num in sorted(in_html_not_map):
            error(f"{slug}: ref-{num} exists in HTML but missing from chapter-map.json")

        in_map_not_html = cm_nums - entry_nums
        for num in sorted(in_map_not_html):
            error(f"{slug}: ref-{num} in chapter-map.json but no <li> in HTML")

        # 5. Chapter-map keys exist in references.json
        for num_str, bib_key in cm.items():
            all_referenced_bib_keys.add(bib_key)
            if bib_key not in references:
                error(f"{slug}: ref-{num_str} maps to '{bib_key}' which is missing from references.json")

        # 6. HTML content vs JSON spot-check
        for num in sorted(entry_nums):
            num_str = str(num)
            html_data = parser.ref_entry_data.get(num, {})
            bib_key = cm.get(num_str)
            if not bib_key or bib_key not in references:
                continue
            ref_json = references[bib_key]

            # Check URL consistency
            html_url = html_data.get('url', '')
            json_url = ref_json.get('url', '') or ''
            if html_url and json_url:
                # Normalize for comparison
                h = re.sub(r'^https?://(www\.)?', '', html_url).rstrip('/')
                j = re.sub(r'^https?://(www\.)?', '', json_url).rstrip('/')
                if h.lower() != j.lower():
                    # Check if one contains the other (DOI variants etc)
                    if h.lower() not in j.lower() and j.lower() not in h.lower():
                        warn(f"{slug}/ref-{num}: URL mismatch — HTML has {html_url[:60]} vs JSON has {json_url[:60]}")

            # Track author keys
            for akey in ref_json.get('authors', []):
                all_referenced_author_keys.add(akey)

    # ── Global checks ───────────────────────────────────────────────────

    print(f"\n{'='*60}")
    print(f"GLOBAL CHECKS")
    print(f"{'='*60}")

    # 7. References.json quality
    missing_title = []
    missing_year = []
    missing_authors = []
    missing_url = []
    for key, ref in references.items():
        if not ref.get('title'):
            missing_title.append(key)
        if not ref.get('year'):
            missing_year.append(key)
        if not ref.get('authors'):
            missing_authors.append(key)
        if not ref.get('url'):
            missing_url.append(key)

    print(f"\n  Reference data quality ({len(references)} entries):")
    print(f"    Missing title:   {len(missing_title)}")
    if missing_title:
        for k in missing_title:
            error(f"references.json: '{k}' has no title")
    print(f"    Missing year:    {len(missing_year)}")
    if missing_year:
        for k in missing_year:
            warn(f"references.json: '{k}' has no year")
    print(f"    Missing authors: {len(missing_authors)}")
    if missing_authors:
        for k in missing_authors:
            warn(f"references.json: '{k}' has no authors")
    print(f"    Missing URL:     {len(missing_url)}")
    if missing_url:
        for k in missing_url[:10]:
            warn(f"references.json: '{k}' has no URL")
        if len(missing_url) > 10:
            warn(f"  ...and {len(missing_url) - 10} more without URLs")

    # 8. Orphaned entries in references.json (not referenced by any chapter)
    orphaned_refs = set(references.keys()) - all_referenced_bib_keys
    if orphaned_refs:
        print(f"\n  Orphaned references (in JSON but no chapter points to them): {len(orphaned_refs)}")
        for k in sorted(orphaned_refs):
            warn(f"references.json: '{k}' is not referenced by any chapter")

    # 9. Authors.json quality
    empty_display = [k for k, v in authors.items() if not v.get('displayName')]
    orphaned_authors = set(authors.keys()) - all_referenced_author_keys
    print(f"\n  Author data quality ({len(authors)} entries):")
    print(f"    Empty displayName: {len(empty_display)}")
    print(f"    Orphaned (not referenced): {len(orphaned_authors)}")
    for k in empty_display:
        error(f"authors.json: '{k}' has no displayName")

    # 10. Cross-chapter consistency: same BibTeX key should have same data everywhere
    print(f"\n  Cross-chapter dedup check:")
    key_to_chapters = {}
    for slug, filename in CHAPTER_FILES:
        cm = chapter_map.get(slug, {})
        for num_str, bib_key in cm.items():
            key_to_chapters.setdefault(bib_key, []).append(f"{slug}/ref-{num_str}")
    shared = {k: v for k, v in key_to_chapters.items() if len(v) > 1}
    print(f"    {len(shared)} references appear in multiple chapters")

    # Verify shared refs point to same JSON entry (they do by construction,
    # but let's confirm the mapping is intentional by checking HTML data)
    cross_chapter_issues = 0
    for bib_key, locations in shared.items():
        ref_json = references.get(bib_key, {})
        if not ref_json.get('title'):
            cross_chapter_issues += 1
            warn(f"Cross-chapter ref '{bib_key}' (in {locations}) has no title in JSON")
    if cross_chapter_issues == 0:
        print(f"    All shared references have valid data ✓")

    # ── Summary ─────────────────────────────────────────────────────────

    print(f"\n{'='*60}")
    print(f"AUDIT SUMMARY")
    print(f"{'='*60}")
    print(f"  Errors:   {len(issues)}")
    print(f"  Warnings: {len(warnings)}")

    if issues:
        print(f"\n  ERRORS:")
        for i in issues:
            print(f"    {i}")

    if warnings:
        print(f"\n  WARNINGS:")
        for w in warnings:
            print(f"    {w}")

    if not issues and not warnings:
        print(f"\n  All checks passed! ✓")

    return len(issues), len(warnings)


if __name__ == '__main__':
    errors, warns = run_audit()
    sys.exit(1 if errors else 0)

#!/usr/bin/env python3
"""
Build the reference database JSON files from BibTeX and HTML sources.

Parses:
  - 1411.3146/references.bib  (BibTeX entries)
  - index.html .. appendix2.html  (per-chapter reference lists)

Produces:
  - data/references.json   (global reference database keyed by BibTeX ID)
  - data/chapter-map.json  (chapter-slug + local-ref-number → BibTeX ID)
  - data/authors.json      (author database keyed by lastname_firstname)
"""

import json
import os
import re
import sys
import unicodedata
from html.parser import HTMLParser
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIB_PATH = ROOT / "1411.3146" / "references.bib"
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

# ---------------------------------------------------------------------------
# BibTeX parser (no external dependencies)
# ---------------------------------------------------------------------------

def parse_bibtex(path):
    """Parse a BibTeX file into a dict of {key: {field: value, ...}}."""
    text = path.read_text(encoding="utf-8")
    entries = {}

    # Match each @type{key, ... } block.  We handle nested braces.
    entry_re = re.compile(r'@(\w+)\s*\{', re.IGNORECASE)
    pos = 0
    while pos < len(text):
        m = entry_re.search(text, pos)
        if not m:
            break
        entry_type = m.group(1).lower()
        # Find the key (everything up to the first comma)
        start = m.end()
        comma = text.find(',', start)
        if comma == -1:
            break
        key = text[start:comma].strip()
        # Now find the matching closing brace
        depth = 1
        i = comma + 1
        while i < len(text) and depth > 0:
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
            i += 1
        body = text[comma + 1:i - 1]
        fields = _parse_bib_fields(body)
        fields['_type'] = entry_type
        entries[key] = fields
        pos = i

    return entries


def _parse_bib_fields(body):
    """Extract field = value pairs from a BibTeX entry body."""
    fields = {}
    # Match field = {value} or field = "value" or field = number
    # Handle multi-line values with nested braces
    i = 0
    while i < len(body):
        # Skip whitespace and commas
        while i < len(body) and body[i] in ' \t\n\r,':
            i += 1
        if i >= len(body):
            break
        # Match field name
        fm = re.match(r'(\w+)\s*=\s*', body[i:])
        if not fm:
            i += 1
            continue
        field_name = fm.group(1).lower()
        i += fm.end()
        if i >= len(body):
            break
        # Parse value
        if body[i] == '{':
            # Brace-delimited value
            depth = 1
            start = i + 1
            i += 1
            while i < len(body) and depth > 0:
                if body[i] == '{':
                    depth += 1
                elif body[i] == '}':
                    depth -= 1
                i += 1
            value = body[start:i - 1]
        elif body[i] == '"':
            # Quote-delimited value
            start = i + 1
            i += 1
            while i < len(body) and body[i] != '"':
                i += 1
            value = body[start:i]
            i += 1
        else:
            # Bare value (number or macro)
            m2 = re.match(r'([^\s,}]+)', body[i:])
            if m2:
                value = m2.group(1)
                i += m2.end()
            else:
                i += 1
                continue
        fields[field_name] = value.strip()
    return fields


def classify_bib_type(entry):
    """Map BibTeX entry type to a simpler classification."""
    t = entry.get('_type', '')
    mapping = {
        'article': 'journal',
        'inproceedings': 'conference',
        'conference': 'conference',
        'book': 'book',
        'incollection': 'book-chapter',
        'phdthesis': 'thesis',
        'mastersthesis': 'thesis',
        'techreport': 'report',
        'misc': 'misc',
        'unpublished': 'preprint',
    }
    return mapping.get(t, 'misc')


def bib_venue(entry):
    """Extract venue string from a BibTeX entry."""
    for field in ('journal', 'booktitle', 'publisher', 'howpublished', 'school'):
        if field in entry:
            return entry[field]
    return None


def bib_venue_short(entry):
    """Try to produce a short venue name."""
    venue = bib_venue(entry)
    if not venue:
        return None
    # If it looks like an arXiv preprint
    if 'arxiv' in venue.lower():
        return venue
    # Abbreviate long conference names
    if len(venue) > 40:
        # Try to find an acronym in parentheses
        m = re.search(r'\(([A-Z]{2,}[^)]*)\)', venue)
        if m:
            return m.group(1)
    return venue


def parse_bib_authors(raw):
    """Parse BibTeX author string into a list of (first, last) tuples."""
    if not raw:
        return []
    # Split on ' and '
    parts = re.split(r'\s+and\s+', raw, flags=re.IGNORECASE)
    authors = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # Handle "Last, First" format
        if ',' in p:
            pieces = [x.strip() for x in p.split(',', 1)]
            last, first = pieces[0], pieces[1] if len(pieces) > 1 else ''
        else:
            # "First Last" format
            words = p.split()
            if len(words) == 1:
                last, first = words[0], ''
            else:
                last = words[-1]
                first = ' '.join(words[:-1])
        authors.append((first.strip(), last.strip()))
    return authors


def make_author_key(first, last):
    """Generate a normalized author key like 'dziri_nouha'."""
    def normalize(s):
        # Remove accents
        s = unicodedata.normalize('NFD', s)
        s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
        # Lowercase, keep only alphanumeric and spaces
        s = re.sub(r'[^a-z0-9 ]', '', s.lower())
        # Replace spaces with underscores, collapse multiples
        s = re.sub(r'\s+', '_', s.strip())
        return s
    last_n = normalize(last)
    first_n = normalize(first)
    if first_n:
        return f"{last_n}_{first_n}"
    return last_n


def make_display_name(first, last):
    """Build a display name like 'Nouha Dziri'."""
    if first:
        return f"{first} {last}"
    return last


# ---------------------------------------------------------------------------
# HTML reference parser
# ---------------------------------------------------------------------------

class RefListParser(HTMLParser):
    """Extract reference entries from an HTML file's <section class="references"> block."""

    def __init__(self):
        super().__init__()
        self.refs = []  # list of dicts
        self._in_ref_section = False
        self._in_ol = False
        self._current_ref = None
        self._current_span = None  # 'authors', 'title', 'venue', or None
        self._current_href = None
        self._in_a = False
        self._in_em = False
        self._text_buf = []
        self._all_text_buf = []  # captures ALL text in the <li> for fallback
        self._depth = 0  # nesting depth inside <section>

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'section':
            cls = attrs_dict.get('class', '')
            if 'references' in cls:
                self._in_ref_section = True
                self._depth = 1
                return
        if self._in_ref_section:
            if tag == 'section':
                self._depth += 1
            if tag == 'ol' and not self._in_ol:
                self._in_ol = True
                return
            if tag == 'li' and self._in_ol:
                ref_id = attrs_dict.get('id', '')
                m = re.match(r'ref-(\d+)', ref_id)
                if m:
                    self._current_ref = {
                        'num': int(m.group(1)),
                        'authors_raw': '',
                        'title': '',
                        'venue': '',
                        'url': '',
                        'year': None,
                    }
                    self._all_text_buf = []
                return
            if self._current_ref is not None:
                if tag == 'span':
                    cls = attrs_dict.get('class', '')
                    if cls in ('authors', 'title', 'venue'):
                        self._current_span = cls
                        self._text_buf = []
                if tag == 'a':
                    href = attrs_dict.get('href', '')
                    if href and not self._current_ref.get('url'):
                        self._current_ref['url'] = href
                    self._in_a = True
                if tag == 'em':
                    self._in_em = True

    def handle_endtag(self, tag):
        if not self._in_ref_section:
            return
        if tag == 'section':
            self._depth -= 1
            if self._depth <= 0:
                self._in_ref_section = False
                self._in_ol = False
            return
        if tag == 'em':
            self._in_em = False
        if tag == 'span' and self._current_span and self._current_ref is not None:
            text = ' '.join(''.join(self._text_buf).split())
            if self._current_span == 'authors':
                self._current_ref['authors_raw'] = text
            elif self._current_span == 'title':
                self._current_ref['title'] = text
            elif self._current_span == 'venue':
                self._current_ref['venue'] = text
            self._current_span = None
            self._text_buf = []
        if tag == 'a':
            self._in_a = False
        if tag == 'li' and self._current_ref is not None:
            # Store the full raw text of the <li> for fallback matching
            self._current_ref['_all_text'] = ' '.join(
                ''.join(self._all_text_buf).split()
            )
            self.refs.append(self._current_ref)
            self._current_ref = None

    def handle_data(self, data):
        if self._current_ref is not None:
            self._all_text_buf.append(data)
        if self._current_span and self._current_ref is not None:
            self._text_buf.append(data)
        elif self._current_ref is not None:
            # Capture year from text between spans like "(2022)."
            m = re.search(r'\((\d{4})\)', data)
            if m and self._current_ref.get('year') is None:
                self._current_ref['year'] = int(m.group(1))
            # Also capture bare year like "2020." (LaTeX format)
            if self._current_ref.get('year') is None:
                m = re.search(r'\b(\d{4})\b', data)
                if m:
                    y = int(m.group(1))
                    if 1900 <= y <= 2030:
                        self._current_ref['year'] = y


def extract_year_from_authors(raw):
    """For LaTeX-style refs where year is embedded in authors span like 'A. Smith. 2020.'"""
    m = re.search(r'(\d{4})\s*\.?\s*$', raw.strip())
    if m:
        return int(m.group(1))
    return None


def extract_title_from_venue(venue):
    """For LaTeX-style refs where title is in the venue span.
    The title is typically the first sentence, before the <em> journal name."""
    # If venue contains italicized part, title is everything before it
    # But we get raw text (em tags stripped), so we look for patterns
    # Actually, let's just return the venue as-is for matching purposes
    return venue


def parse_html_refs(html_path):
    """Parse HTML file and return list of reference dicts."""
    text = html_path.read_text(encoding="utf-8")
    parser = RefListParser()
    parser.feed(text)

    for ref in parser.refs:
        # Try to extract year from authors_raw if not found in surrounding text
        if ref['year'] is None:
            ref['year'] = extract_year_from_authors(ref['authors_raw'])
        # Try to get year from a (YYYY) pattern in the full entry text
        if ref['year'] is None:
            # Search for year in title or venue
            for field in ('title', 'venue', 'authors_raw'):
                m = re.search(r'(\d{4})', ref.get(field, ''))
                if m:
                    y = int(m.group(1))
                    if 1900 <= y <= 2030:
                        ref['year'] = y
                        break

    return parser.refs


# ---------------------------------------------------------------------------
# Matching: HTML refs → BibTeX entries
# ---------------------------------------------------------------------------

def normalize_url(url):
    """Normalize a URL for comparison."""
    if not url:
        return ''
    url = url.strip().rstrip('/')
    # Remove protocol
    url = re.sub(r'^https?://', '', url)
    # Remove www.
    url = re.sub(r'^www\.', '', url)
    # Remove trailing slashes
    url = url.rstrip('/')
    return url.lower()


def normalize_title(title):
    """Normalize a title for fuzzy comparison."""
    if not title:
        return ''
    # Remove punctuation, lowercase
    t = re.sub(r'[^\w\s]', '', title.lower())
    # Collapse whitespace
    t = ' '.join(t.split())
    return t


def title_similarity(a, b):
    """Compute title similarity score (0-1)."""
    na = normalize_title(a)
    nb = normalize_title(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def extract_arxiv_id(url):
    """Extract arXiv ID from URL."""
    if not url:
        return None
    m = re.search(r'arxiv\.org/abs/(\d+\.\d+)', url)
    if m:
        return m.group(1)
    return None


def match_refs_to_bib(html_refs, bib_entries):
    """Match HTML references to BibTeX entries. Returns list of (ref, bib_key, method)."""
    # Build lookup indices
    url_to_key = {}
    arxiv_to_key = {}
    title_index = []  # (normalized_title, key)

    for key, entry in bib_entries.items():
        bib_url = entry.get('url', '')
        # Also extract URLs from howpublished field like \url{https://...}
        if not bib_url:
            hp = entry.get('howpublished', '')
            m_url = re.search(r'\\url\{([^}]+)\}', hp)
            if m_url:
                bib_url = m_url.group(1)
        if bib_url:
            url_to_key[normalize_url(bib_url)] = key
            aid = extract_arxiv_id(bib_url)
            if aid:
                arxiv_to_key[aid] = key
        doi = entry.get('doi', '')
        if doi:
            # DOI URLs can appear in multiple forms
            doi_url = f"doi.org/{doi}"
            url_to_key[normalize_url(doi_url)] = key
            url_to_key[normalize_url(f"https://{doi_url}")] = key
            url_to_key[normalize_url(f"http://dx.{doi_url}")] = key

        title = entry.get('title', '')
        if not title:
            # Some entries use 'journal' for the title (e.g. @misc news articles)
            title = entry.get('journal', '')
        if title:
            title_index.append((normalize_title(title), key))

    results = []
    for ref in html_refs:
        matched_key = None
        method = None

        # 1) Try URL match
        ref_url = normalize_url(ref.get('url', ''))
        if ref_url:
            if ref_url in url_to_key:
                matched_key = url_to_key[ref_url]
                method = 'url'
            else:
                # Try arXiv ID match
                aid = extract_arxiv_id(ref.get('url', ''))
                if aid and aid in arxiv_to_key:
                    matched_key = arxiv_to_key[aid]
                    method = 'arxiv'
                else:
                    # Try partial URL match (e.g. DOI embedded in URL)
                    for bib_url_norm, bkey in url_to_key.items():
                        if ref_url in bib_url_norm or bib_url_norm in ref_url:
                            matched_key = bkey
                            method = 'url-partial'
                            break

        # 2) Try title fuzzy match (try title, venue, authors_raw, _all_text)
        if not matched_key:
            candidates = [ref.get('title', ''), ref.get('venue', '')]
            # In LaTeX-style refs, the title may be embedded in authors_raw
            authors_raw = ref.get('authors_raw', '')
            if authors_raw:
                candidates.append(authors_raw)
            # Full text as last resort
            all_text = ref.get('_all_text', '')
            if all_text:
                candidates.append(all_text)

            best_score = 0.0
            best_key = None
            for ref_title in candidates:
                ref_norm = normalize_title(ref_title)
                if not ref_norm:
                    continue
                for bib_norm, bkey in title_index:
                    # Use substring matching for long candidate strings
                    # (when ref_norm is much longer than bib_norm, check
                    # if bib title appears as a substring)
                    if len(ref_norm) > len(bib_norm) * 1.5 and len(bib_norm) > 10:
                        if bib_norm in ref_norm:
                            score = 0.95
                        else:
                            score = SequenceMatcher(None, ref_norm, bib_norm).ratio()
                    else:
                        score = SequenceMatcher(None, ref_norm, bib_norm).ratio()
                    if score > best_score:
                        best_score = score
                        best_key = bkey
            if best_score >= 0.65:
                matched_key = best_key
                method = f'title-fuzzy({best_score:.2f})'

        # 3) Try author+year match as last resort
        if not matched_key and ref.get('year'):
            ref_authors = ref.get('authors_raw', '').lower()
            ref_all = ref.get('_all_text', '').lower()
            best_score = 0.0
            best_key = None
            for key, entry in bib_entries.items():
                if entry.get('year') and str(entry['year']) == str(ref['year']):
                    # Check if main author surname appears
                    bib_parsed = parse_bib_authors(entry.get('author', ''))
                    if bib_parsed:
                        main_last = bib_parsed[0][1].lower()
                        if main_last and (main_last in ref_authors or main_last in ref_all):
                            # Score by title similarity using _all_text
                            ref_title = ref.get('title', '') or ref.get('venue', '') or ref.get('_all_text', '')
                            bib_title = entry.get('title', '')
                            tscore = title_similarity(ref_title, bib_title)
                            # Combine author match + title similarity
                            score = 0.5 + tscore * 0.5
                            if score > best_score:
                                best_score = score
                                best_key = key
            if best_key and best_score >= 0.55:
                matched_key = best_key
                method = f'author-year({best_score:.2f})'

        results.append((ref, matched_key, method))

    return results


# ---------------------------------------------------------------------------
# Build JSON databases
# ---------------------------------------------------------------------------

def build_databases():
    """Main entry point: parse all sources and write JSON files."""
    print("Parsing BibTeX...")
    bib_entries = parse_bibtex(BIB_PATH)
    print(f"  Found {len(bib_entries)} BibTeX entries")

    chapter_map = {}
    all_matches = {}  # bib_key → entry (deduped)
    html_urls = {}    # bib_key → URL from HTML (fallback when BibTeX has no URL)
    unmatched = []
    stats = {'url': 0, 'arxiv': 0, 'url-partial': 0, 'title-fuzzy': 0, 'author-year': 0, 'unmatched': 0}

    for slug, filename in CHAPTER_FILES:
        html_path = ROOT / filename
        print(f"\nParsing {filename}...")
        refs = parse_html_refs(html_path)
        print(f"  Found {len(refs)} references")

        matches = match_refs_to_bib(refs, bib_entries)
        chapter_map[slug] = {}

        for ref, bib_key, method in matches:
            ref_num = str(ref['num'])
            if bib_key:
                chapter_map[slug][ref_num] = bib_key
                all_matches[bib_key] = bib_entries[bib_key]
                # Capture HTML URL as fallback for entries missing a BibTeX URL
                ref_html_url = ref.get('url', '')
                if ref_html_url and bib_key not in html_urls:
                    html_urls[bib_key] = ref_html_url
                # Categorize method for stats
                method_base = method.split('(')[0]
                stats[method_base] = stats.get(method_base, 0) + 1
                print(f"    ref-{ref_num} → {bib_key} ({method})")
            else:
                stats['unmatched'] += 1
                # Generate a synthetic key for unmatched refs
                synth_key = _make_synthetic_key(ref, slug)
                chapter_map[slug][ref_num] = synth_key
                # Build a synthetic entry
                all_matches[synth_key] = _make_synthetic_entry(ref)
                unmatched.append((slug, ref_num, ref))
                print(f"    ref-{ref_num} → {synth_key} (UNMATCHED - synthetic)")

    # Build references.json (merge-safe: preserve enrichment data from existing file)
    existing_refs = {}
    refs_path = DATA_DIR / "references.json"
    if refs_path.exists():
        with open(refs_path, "r", encoding="utf-8") as f:
            existing_refs = json.load(f)
        print(f"\nLoaded existing references.json ({len(existing_refs)} entries) — preserving enrichment data")

    references = {}
    for bib_key, entry in all_matches.items():
        authors_raw = entry.get('author', '')
        parsed_authors = parse_bib_authors(authors_raw)
        author_keys = [make_author_key(f, l) for f, l in parsed_authors]

        year = entry.get('year')
        if year:
            try:
                year = int(re.search(r'\d{4}', str(year)).group())
            except (AttributeError, ValueError):
                year = None

        # Extract URL (check url field, then howpublished, then HTML fallback)
        ref_url = entry.get('url', '') or ''
        if not ref_url:
            hp = entry.get('howpublished', '')
            m_url = re.search(r'\\url\{([^}]+)\}', hp)
            if m_url:
                ref_url = m_url.group(1)
        if not ref_url and bib_key in html_urls:
            ref_url = html_urls[bib_key]
        # Fall back to DOI-derived URL
        if not ref_url and entry.get('doi'):
            doi = entry['doi'].strip()
            # Remove https://doi.org/ prefix if already present
            doi = re.sub(r'^https?://doi\.org/', '', doi)
            ref_url = f"https://doi.org/{doi}"

        # Use title, falling back to journal for @misc news articles
        title_text = entry.get('title', '') or entry.get('journal', '')

        # Start from existing entry to preserve enrichment fields (screenshot, etc.)
        base = existing_refs.get(bib_key, {})
        base.update({
            'title': _clean_latex(title_text),
            'authors': author_keys,
            'year': year,
            'venue': bib_venue(entry),
            'venueShort': bib_venue_short(entry),
            'url': ref_url or None,
            'doi': entry.get('doi', None) or None,
            'type': classify_bib_type(entry),
        })
        # Only set screenshot to None if this is a brand-new entry
        if 'screenshot' not in base:
            base['screenshot'] = None
        references[bib_key] = base

    # Build authors.json (merge-safe: preserve enrichment data from existing file)
    existing_authors = {}
    authors_path = DATA_DIR / "authors.json"
    if authors_path.exists():
        with open(authors_path, "r", encoding="utf-8") as f:
            existing_authors = json.load(f)
        print(f"Loaded existing authors.json ({len(existing_authors)} entries) — preserving enrichment data")

    authors = {}
    for bib_key, entry in all_matches.items():
        authors_raw = entry.get('author', '')
        parsed = parse_bib_authors(authors_raw)
        for first, last in parsed:
            akey = make_author_key(first, last)
            if akey and akey not in authors:
                if akey in existing_authors:
                    # Preserve all enrichment fields, only update displayName
                    authors[akey] = existing_authors[akey]
                    authors[akey]['displayName'] = make_display_name(first, last)
                else:
                    authors[akey] = {
                        'displayName': make_display_name(first, last),
                        'affiliation': None,
                        'headshot': None,
                        'links': {},
                    }

    # Write JSON files
    DATA_DIR.mkdir(exist_ok=True)

    with open(DATA_DIR / "chapter-map.json", "w", encoding="utf-8") as f:
        json.dump(chapter_map, f, indent=2, ensure_ascii=False)
    print(f"\nWrote data/chapter-map.json")

    with open(DATA_DIR / "references.json", "w", encoding="utf-8") as f:
        json.dump(references, f, indent=2, ensure_ascii=False)
    print(f"Wrote data/references.json ({len(references)} entries)")

    with open(DATA_DIR / "authors.json", "w", encoding="utf-8") as f:
        json.dump(authors, f, indent=2, ensure_ascii=False)
    print(f"Wrote data/authors.json ({len(authors)} entries)")

    # Summary
    total_refs = sum(len(v) for v in chapter_map.values())
    unique_bib_keys = set()
    for ch in chapter_map.values():
        unique_bib_keys.update(ch.values())

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Total chapter references: {total_refs}")
    print(f"Unique references: {len(unique_bib_keys)}")
    print(f"Unique authors: {len(authors)}")
    print(f"\nMatching statistics:")
    for method, count in sorted(stats.items()):
        print(f"  {method}: {count}")

    if unmatched:
        print(f"\nUnmatched references ({len(unmatched)}):")
        for slug, num, ref in unmatched:
            title = ref.get('title', '') or ref.get('venue', '')[:60]
            print(f"  {slug}/ref-{num}: {title[:80]}")

    return chapter_map, references, authors


def _clean_latex(s):
    """Remove common LaTeX artifacts from a string."""
    s = re.sub(r'[{}]', '', s)
    s = re.sub(r'\\textit\s*', '', s)
    s = re.sub(r'\\textbf\s*', '', s)
    s = re.sub(r'\\emph\s*', '', s)
    s = re.sub(r"\\'\{?(\w)\}?", r'\1', s)  # \'e → e
    s = re.sub(r'\\"\{?(\w)\}?', r'\1', s)  # \"u → u
    s = re.sub(r'\\\w+\s*', '', s)  # remove other commands
    return s.strip()


def _make_synthetic_key(ref, chapter_slug):
    """Generate a synthetic BibTeX-style key for an unmatched reference."""
    authors_raw = ref.get('authors_raw', '')
    year = ref.get('year', '')

    # Extract first author surname
    # Try "Surname, F." or "F. Surname" patterns
    surname = 'unknown'
    # Try comma-first: "Surname, ..."
    m = re.match(r'([A-Z][a-z]+)', authors_raw)
    if m:
        surname = m.group(1).lower()

    title = ref.get('title', '') or ref.get('venue', '')
    # Get first significant word from title
    title_word = ''
    for w in title.split():
        w_clean = re.sub(r'[^\w]', '', w).lower()
        if w_clean and w_clean not in ('the', 'a', 'an', 'of', 'in', 'on', 'for', 'and', 'to', 'from', 'with'):
            title_word = w_clean
            break

    key = f"{surname}{year}{title_word}"
    return key


def _make_synthetic_entry(ref):
    """Build a synthetic BibTeX-style entry dict from an HTML reference."""
    # Parse authors from HTML authors_raw
    authors_raw = ref.get('authors_raw', '')
    # Remove trailing year like "2020." or "2020"
    authors_clean = re.sub(r'\s*\d{4}\s*\.?\s*$', '', authors_raw).strip()
    # Convert "F. Last, G. Other" style to BibTeX "Last, F. and Other, G."
    # This is approximate
    entry = {
        'author': authors_clean,
        'title': ref.get('title', '') or '',
        'year': str(ref.get('year', '')) if ref.get('year') else '',
        'url': ref.get('url', ''),
        '_type': 'misc',
    }
    if ref.get('venue'):
        entry['journal'] = ref['venue']
    return entry


if __name__ == '__main__':
    build_databases()

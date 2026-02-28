#!/usr/bin/env python3
"""
Enrich authors.json with data from Semantic Scholar and Google Scholar (via SerpAPI).

Five-phase pipeline:
  Phase 1 (papers):     Look up papers on Semantic Scholar by DOI/arXiv/title
  Phase 2 (match):      Match our author keys to S2 author IDs (offline)
  Phase 3 (s2-authors): Fetch S2 author profiles for affiliations/links
  Phase 4 (scholar):    Find Google Scholar profiles via SerpAPI
  Phase 5 (headshots):  Download Scholar headshot thumbnails

Usage:
  python3 scripts/enrich_authors.py                     # run all phases
  python3 scripts/enrich_authors.py --phase papers       # Phase 1 only
  python3 scripts/enrich_authors.py --phase match        # Phase 2 only
  python3 scripts/enrich_authors.py --phase s2-authors   # Phase 3 only
  python3 scripts/enrich_authors.py --phase scholar      # Phase 4 (needs SERPAPI_KEY)
  python3 scripts/enrich_authors.py --phase headshots    # Phase 5 only
  python3 scripts/enrich_authors.py --summary            # print statistics
  python3 scripts/enrich_authors.py --force              # re-enrich already-enriched authors
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
AUTHORS_PATH = DATA_DIR / "authors.json"
REFS_PATH = DATA_DIR / "references.json"
PAPER_CACHE_PATH = DATA_DIR / "paper-cache.json"
HEADSHOTS_DIR = ROOT / "assets" / "headshots"

S2_API_BASE = "https://api.semanticscholar.org/graph/v1"
S2_BATCH_FIELDS = "title,authors,authors.name,authors.affiliations,authors.externalIds,authors.authorId"
S2_AUTHOR_FIELDS = "name,affiliations,externalIds,url,homepage"
SERPAPI_BASE = "https://serpapi.com/search"

# Keys that represent organizations, not people
ORG_KEYS = set()

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def log(msg=""):
    """Print and flush immediately (so background output is visible)."""
    print(msg, flush=True)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def normalize_name(name):
    """Normalize a name for comparison: lowercase, strip accents, remove punctuation."""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"[^\w\s]", "", name.lower())
    return " ".join(name.split())


def name_parts_from_key(key):
    """Extract (firstName, lastName) from an author key like 'lastname_firstname'."""
    parts = key.split("_")
    if len(parts) < 2:
        return None, parts[0].title()
    last = parts[0].title()
    first = " ".join(p.title() for p in parts[1:])
    return first, last


def name_parts_from_display(display_name):
    """Extract (firstName, lastName) from a display name like 'First Last'."""
    display_name = re.sub(r"[{}]", "", display_name).strip()
    parts = display_name.split()
    if len(parts) == 0:
        return None, ""
    if len(parts) == 1:
        return None, parts[0]
    return " ".join(parts[:-1]), parts[-1]


def is_org_key(key, authors_data):
    """Heuristic: is this key an organization rather than a person?"""
    if "_" not in key:
        return True
    display = authors_data.get(key, {}).get("displayName", "")
    display_clean = re.sub(r"[{}]", "", display).strip()
    # Single word display names are often orgs
    if " " not in display_clean and len(display_clean) > 1:
        return True
    # Known org patterns
    org_patterns = [
        "commission", "council", "institute", "ministry", "government",
        "department", "agency", "authority", "foundation", "association",
        "organization", "corporation", "company",
    ]
    for pat in org_patterns:
        if pat in key.lower():
            return True
    return False


def extract_arxiv_id(url):
    """Extract arXiv ID from a URL like https://arxiv.org/abs/2401.11817."""
    m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)", url)
    if m:
        return m.group(1)
    # Older format: arxiv.org/abs/hep-th/9901001
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([a-z\-]+/\d+)", url)
    if m:
        return m.group(1)
    return None


def extract_doi(ref):
    """Extract a clean DOI from the reference's doi field or URL."""
    doi = ref.get("doi") or ""
    # doi field might be a full URL
    if doi.startswith("http"):
        m = re.search(r"doi\.org/(10\.\S+)", doi)
        if m:
            return m.group(1).rstrip("/")
        return None
    if doi.startswith("10."):
        return doi.rstrip("/")
    # Try extracting from URL
    url = ref.get("url") or ""
    m = re.search(r"doi\.org/(10\.\S+)", url)
    if m:
        return m.group(1).rstrip("/")
    return None


def s2_api_request(url, headers=None, data=None, method="GET", _retries=2):
    """Make an HTTP request to the S2 API. Returns parsed JSON or None."""
    if headers is None:
        headers = {}
    headers.setdefault("User-Agent", "Mozilla/5.0 (compatible; enrich-authors/1.0)")

    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    else:
        req = urllib.request.Request(url, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429 and _retries > 0:
            log(f"    Rate limited (429). Waiting 30s... ({_retries} retries left)")
            time.sleep(30)
            return s2_api_request(url, headers, data, method, _retries - 1)
        elif e.code == 404:
            return None
        else:
            log(f"    HTTP {e.code}: {e.reason} for {url}")
            return None
    except (urllib.error.URLError, TimeoutError) as e:
        log(f"    Request error: {e} for {url}")
        return None


def serpapi_request(params, api_key, _retries=2):
    """Make a SerpAPI request with 429 retry. Returns parsed JSON or None."""
    params["api_key"] = api_key
    url = SERPAPI_BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "enrich-authors/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429 and _retries > 0:
            wait = 60 * (3 - _retries)  # 60s, 120s
            log(f"    SerpAPI 429 rate limited. Waiting {wait}s...")
            time.sleep(wait)
            return serpapi_request(params, api_key, _retries=_retries - 1)
        log(f"    SerpAPI error: {e}")
        return None
    except (urllib.error.URLError, TimeoutError) as e:
        log(f"    SerpAPI error: {e}")
        return None


# ---------------------------------------------------------------------------
# Phase 1: Semantic Scholar Paper Lookups
# ---------------------------------------------------------------------------

def build_paper_identifiers(refs):
    """Build a list of (ref_key, s2_identifier) from references.json."""
    identifiers = []
    title_fallbacks = []

    for key, ref in refs.items():
        url = ref.get("url") or ""
        doi = extract_doi(ref)
        arxiv_id = extract_arxiv_id(url) if url else None

        if arxiv_id:
            identifiers.append((key, f"ArXiv:{arxiv_id}"))
        elif doi:
            identifiers.append((key, f"DOI:{doi}"))
        else:
            # Title search fallback
            title = ref.get("title", "")
            if title and len(title) > 10:
                title_fallbacks.append((key, title))
            else:
                log(f"  Skipping {key}: no arXiv/DOI and title too short")

    return identifiers, title_fallbacks


def lookup_paper_by_title(title, ref_key, refs, headers):
    """Look up a paper on S2 using /paper/search/match. Returns paper dict or None."""
    # Strip punctuation that causes S2 500 errors (colons, question marks, etc.)
    clean_title = re.sub(r"[^\w\s\-]", " ", title)
    clean_title = " ".join(clean_title.split())  # normalize whitespace
    match_url = (
        f"{S2_API_BASE}/paper/search/match"
        f"?query={urllib.parse.quote(clean_title)}"
        f"&fields={S2_BATCH_FIELDS}"
    )
    result = s2_api_request(match_url, headers=headers)

    if not result or not result.get("data"):
        return None

    candidates = result["data"] if isinstance(result["data"], list) else [result["data"]]
    best_match = None
    best_score = 0

    for candidate in candidates:
        cand_title = candidate.get("title", "")
        score = SequenceMatcher(None, title.lower(), cand_title.lower()).ratio()

        # Boost score if author names overlap
        cand_authors = set()
        for a in candidate.get("authors", []):
            if a.get("name"):
                cand_authors.add(normalize_name(a["name"]))

        ref_author_keys = refs[ref_key].get("authors", [])
        author_overlap = 0
        for ak in ref_author_keys:
            first, last = name_parts_from_key(ak)
            norm_last = normalize_name(last)
            for ca in cand_authors:
                if norm_last in ca:
                    author_overlap += 1
                    break

        if author_overlap > 0:
            score += 0.1 * author_overlap

        if score > best_score:
            best_score = score
            best_match = candidate

    if best_match and best_score >= 0.75:
        return best_match
    return None


def phase_papers(refs, paper_cache, s2_api_key=None, force=False):
    """Phase 1: Look up papers on Semantic Scholar.

    Primary strategy: /paper/search/match by title (reliable, no auth required).
    With API key: also tries batch endpoint for ID-based lookups first.
    """
    log("\n=== Phase 1: Semantic Scholar Paper Lookups ===\n")

    headers = {}
    if s2_api_key:
        headers["x-api-key"] = s2_api_key

    # Build list of all papers to look up
    to_lookup = []
    for ref_key, ref in refs.items():
        if not force and ref_key in paper_cache:
            continue
        title = ref.get("title", "")
        if title and len(title) > 10:
            to_lookup.append((ref_key, title))

    resolved_count = sum(1 for k in refs if k in paper_cache)
    log(f"  Already cached: {resolved_count}")
    log(f"  To look up: {len(to_lookup)}")

    delay = 1 if s2_api_key else 4

    # With API key, try batch lookup by ID first (faster)
    if s2_api_key and to_lookup:
        identifiers, _ = build_paper_identifiers(refs)
        id_keys = {k for k, _ in identifiers}
        batch_items = [(k, sid) for k, sid in identifiers
                       if (force or k not in paper_cache)]

        if batch_items:
            log(f"\n  Batch lookup ({len(batch_items)} papers with IDs)...")
            batch_ids = [sid for _, sid in batch_items]
            key_map = {sid: k for k, sid in batch_items}

            for batch_start in range(0, len(batch_ids), 500):
                batch = batch_ids[batch_start:batch_start + 500]
                url = f"{S2_API_BASE}/paper/batch?fields={S2_BATCH_FIELDS}"
                result = s2_api_request(url, headers=headers, data={"ids": batch})

                if result:
                    for i, paper in enumerate(result):
                        sid = batch[i]
                        ref_key = key_map[sid]
                        if paper is not None:
                            paper_cache[ref_key] = paper
                    save_json(PAPER_CACHE_PATH, paper_cache)
                    log(f"    Batch resolved {sum(1 for p in result if p is not None)} papers")

                if batch_start + 500 < len(batch_ids):
                    time.sleep(delay)

            # Remove already-found from to_lookup
            to_lookup = [(k, t) for k, t in to_lookup if k not in paper_cache]

    # Title-based lookup using /paper/search/match (primary strategy)
    if to_lookup:
        log(f"\n  Title-based lookup ({len(to_lookup)} papers)...")
        found = 0
        for i, (ref_key, title) in enumerate(to_lookup):
            if ref_key in paper_cache:
                continue

            result = lookup_paper_by_title(title, ref_key, refs, headers)
            if result:
                paper_cache[ref_key] = result
                found += 1
                log(f"    [{i+1}/{len(to_lookup)}] Found: {ref_key}")
            else:
                log(f"    [{i+1}/{len(to_lookup)}] Not found: {ref_key}")

            # Save every 10
            if (i + 1) % 10 == 0:
                save_json(PAPER_CACHE_PATH, paper_cache)
                log(f"    Saved cache ({len(paper_cache)} papers)")

            if i < len(to_lookup) - 1:
                time.sleep(delay)

        save_json(PAPER_CACHE_PATH, paper_cache)
        log(f"    Found {found}/{len(to_lookup)} via title search")

    total_cached = len(paper_cache)
    total_refs = len(refs)
    log(f"\n  Phase 1 complete: {total_cached}/{total_refs} papers resolved")


# ---------------------------------------------------------------------------
# Phase 2: Author Matching (offline)
# ---------------------------------------------------------------------------

def match_name(our_name, s2_name):
    """Match our author name against an S2 author name. Returns confidence score."""
    our_norm = normalize_name(our_name)
    s2_norm = normalize_name(s2_name)

    # Exact match
    if our_norm == s2_norm:
        return 1.0

    our_parts = our_norm.split()
    s2_parts = s2_norm.split()

    if not our_parts or not s2_parts:
        return 0.0

    # Last name must match
    if our_parts[-1] != s2_parts[-1]:
        # Try first part as last name (some keys are lastname_firstname)
        if our_parts[0] != s2_parts[-1]:
            return 0.0

    # First name initial match
    if len(our_parts) >= 2 and len(s2_parts) >= 2:
        if our_parts[0][0] == s2_parts[0][0]:
            # First initial matches, check if last names match
            if our_parts[-1] == s2_parts[-1]:
                return 0.9

    # Fuzzy match
    ratio = SequenceMatcher(None, our_norm, s2_norm).ratio()
    return ratio


def phase_match(authors, refs, paper_cache, force=False):
    """Phase 2: Match author keys to S2 author IDs."""
    log("\n=== Phase 2: Author Matching ===\n")

    # Build reverse map: author_key -> list of ref_keys
    author_to_refs = {}
    for ref_key, ref in refs.items():
        for ak in ref.get("authors", []):
            author_to_refs.setdefault(ak, []).append(ref_key)

    matched = 0
    skipped = 0
    unmatched = 0

    for author_key, author_data in authors.items():
        # Skip if already enriched (unless --force)
        if not force and author_data.get("_enrichment", {}).get("s2AuthorId"):
            matched += 1
            continue

        # Skip organizations
        if is_org_key(author_key, authors):
            if "_enrichment" not in author_data:
                author_data["_enrichment"] = {}
            author_data["_enrichment"]["confidence"] = "skip"
            skipped += 1
            continue

        display = re.sub(r"[{}]", "", author_data.get("displayName", "")).strip()
        first_from_key, last_from_key = name_parts_from_key(author_key)

        # Find this author in cached papers
        best_s2_author = None
        best_score = 0
        s2_id_votes = {}  # s2AuthorId -> count of papers they appear in

        ref_keys = author_to_refs.get(author_key, [])
        for ref_key in ref_keys:
            paper = paper_cache.get(ref_key)
            if not paper:
                continue

            for s2_author in paper.get("authors", []):
                s2_name = s2_author.get("name", "")
                if not s2_name:
                    continue

                # Try matching against display name and key-derived name
                score_display = match_name(display, s2_name) if display else 0
                score_key = 0
                if first_from_key:
                    key_name = f"{first_from_key} {last_from_key}"
                    score_key = match_name(key_name, s2_name)

                score = max(score_display, score_key)

                if score >= 0.8:
                    s2_id = s2_author.get("authorId")
                    if s2_id:
                        s2_id_votes[s2_id] = s2_id_votes.get(s2_id, 0) + 1
                        if score > best_score:
                            best_score = score
                            best_s2_author = s2_author

        # If we found them in multiple papers, prefer the most consistent ID
        if s2_id_votes and best_s2_author:
            most_common_id = max(s2_id_votes, key=s2_id_votes.get)
            # If the best match's ID isn't the most common, re-find
            if best_s2_author.get("authorId") != most_common_id:
                for ref_key in ref_keys:
                    paper = paper_cache.get(ref_key)
                    if not paper:
                        continue
                    for s2_a in paper.get("authors", []):
                        if s2_a.get("authorId") == most_common_id:
                            best_s2_author = s2_a
                            break

        if best_s2_author and best_score >= 0.8:
            # Extract name parts
            if first_from_key:
                author_data["firstName"] = first_from_key
                author_data["lastName"] = last_from_key
            else:
                first_d, last_d = name_parts_from_display(display)
                if first_d:
                    author_data["firstName"] = first_d
                    author_data["lastName"] = last_d

            # Store S2 info
            s2_id = best_s2_author.get("authorId")
            affiliations = best_s2_author.get("affiliations") or []
            if affiliations and not author_data.get("affiliation"):
                author_data["affiliation"] = affiliations[0]

            ext_ids = best_s2_author.get("externalIds") or {}
            links = author_data.get("links", {})
            if s2_id:
                links["semanticScholar"] = f"https://www.semanticscholar.org/author/{s2_id}"
            if ext_ids.get("ORCID"):
                links["orcid"] = f"https://orcid.org/{ext_ids['ORCID']}"
            if ext_ids.get("DBLP"):
                dblp_ids = ext_ids["DBLP"]
                if isinstance(dblp_ids, list):
                    dblp_ids = dblp_ids[0]
                if "/" in dblp_ids:
                    links["dblp"] = f"https://dblp.org/pid/{dblp_ids}"
                else:
                    links["dblp"] = f"https://dblp.org/search?q={urllib.parse.quote(dblp_ids)}"
            author_data["links"] = links

            confidence = "high" if best_score >= 0.9 else "medium"
            author_data["_enrichment"] = {
                "s2AuthorId": s2_id,
                "confidence": confidence,
                "enrichedAt": datetime.now(timezone.utc).isoformat(),
            }

            matched += 1
            log(f"  Matched: {author_key} -> S2:{s2_id} ({confidence}, score={best_score:.2f})")
        else:
            # Set name parts even if we couldn't match to S2
            if first_from_key and not author_data.get("firstName"):
                author_data["firstName"] = first_from_key
                author_data["lastName"] = last_from_key
            elif not author_data.get("firstName"):
                first_d, last_d = name_parts_from_display(display)
                if first_d:
                    author_data["firstName"] = first_d
                    author_data["lastName"] = last_d

            if "_enrichment" not in author_data:
                author_data["_enrichment"] = {}
            if best_score > 0:
                author_data["_enrichment"]["confidence"] = "low"
            unmatched += 1

    save_json(AUTHORS_PATH, authors)
    log(f"\n  Phase 2 complete: {matched} matched, {skipped} skipped (orgs), {unmatched} unmatched")


# ---------------------------------------------------------------------------
# Phase 3: S2 Author Profile Enrichment
# ---------------------------------------------------------------------------

def enrich_from_paper_cache(authors, paper_cache, refs):
    """Extract additional author data (DBLP, ORCID) from the paper cache.

    This runs before the API-based enrichment and populates links that
    were already returned in Phase 1's paper lookups, avoiding extra API calls.
    """
    log("  Extracting data from paper cache...")

    # Build author_key -> list of ref_keys
    author_to_refs = {}
    for ref_key, ref in refs.items():
        for ak in ref.get("authors", []):
            author_to_refs.setdefault(ak, []).append(ref_key)

    enriched = 0
    for author_key, data in authors.items():
        s2_id = data.get("_enrichment", {}).get("s2AuthorId")
        if not s2_id:
            continue

        # Find this author in the paper cache by their S2 ID
        for ref_key in author_to_refs.get(author_key, []):
            paper = paper_cache.get(ref_key)
            if not paper:
                continue
            for s2_author in paper.get("authors", []):
                if s2_author.get("authorId") != s2_id:
                    continue

                # Extract affiliations
                affiliations = s2_author.get("affiliations") or []
                if affiliations and not data.get("affiliation"):
                    data["affiliation"] = affiliations[0]

                # Extract external IDs
                ext_ids = s2_author.get("externalIds") or {}
                links = data.get("links", {})
                if ext_ids.get("ORCID") and "orcid" not in links:
                    links["orcid"] = f"https://orcid.org/{ext_ids['ORCID']}"
                if ext_ids.get("DBLP") and "dblp" not in links:
                    dblp_id = ext_ids["DBLP"]
                    if isinstance(dblp_id, list):
                        dblp_id = dblp_id[0]
                    # S2 stores DBLP external ID as either a PID or author name
                    if "/" in dblp_id:
                        links["dblp"] = f"https://dblp.org/pid/{dblp_id}"
                    else:
                        links["dblp"] = f"https://dblp.org/search?q={urllib.parse.quote(dblp_id)}"
                data["links"] = links
                enriched += 1
                break

    log(f"  Extracted data for {enriched} authors from paper cache")
    return enriched


def phase_s2_authors(authors, s2_api_key=None, force=False, paper_cache=None, refs=None):
    """Phase 3: Enrich author profiles.

    Step 1: Extract any available data from the paper cache (free, instant).
    Step 2: Fetch individual author profiles from S2 API (rate-limited).
    """
    log("\n=== Phase 3: S2 Author Profile Enrichment ===\n")

    # Step 1: Extract from paper cache first (no API calls needed)
    if paper_cache and refs:
        enrich_from_paper_cache(authors, paper_cache, refs)
        save_json(AUTHORS_PATH, authors)

    headers = {}
    if s2_api_key:
        headers["x-api-key"] = s2_api_key
    delay = 1 if s2_api_key else 5

    # Step 2: Collect unique S2 author IDs that still need profile fetching
    id_to_keys = {}  # s2AuthorId -> [author_key, ...]
    for key, data in authors.items():
        s2_id = data.get("_enrichment", {}).get("s2AuthorId")
        if not s2_id:
            continue
        # Skip if already fully enriched unless force
        if not force and data.get("_enrichment", {}).get("s2ProfileFetched"):
            continue
        id_to_keys.setdefault(s2_id, []).append(key)

    unique_ids = list(id_to_keys.keys())
    log(f"  Unique S2 author IDs to fetch via API: {len(unique_ids)}")

    if not unique_ids:
        log("  No API calls needed.")
        save_json(AUTHORS_PATH, authors)
        return

    fetched = 0
    failed = 0
    for i, s2_id in enumerate(unique_ids):
        log(f"    [{i+1}/{len(unique_ids)}] Fetching S2 author {s2_id}...")
        url = f"{S2_API_BASE}/author/{s2_id}?fields={S2_AUTHOR_FIELDS}"
        result = s2_api_request(url, headers=headers)

        if result:
            affiliations = result.get("affiliations") or []
            homepage = result.get("homepage")
            s2_url = result.get("url")
            ext_ids = result.get("externalIds") or {}

            for author_key in id_to_keys[s2_id]:
                data = authors[author_key]

                if affiliations and not data.get("affiliation"):
                    data["affiliation"] = affiliations[0]

                links = data.get("links", {})
                if s2_url:
                    links["semanticScholar"] = s2_url
                if homepage:
                    links["homepage"] = homepage
                if ext_ids.get("ORCID") and "orcid" not in links:
                    links["orcid"] = f"https://orcid.org/{ext_ids['ORCID']}"
                if ext_ids.get("DBLP") and "dblp" not in links:
                    dblp_id = ext_ids["DBLP"]
                    if isinstance(dblp_id, list):
                        dblp_id = dblp_id[0]
                    # S2 stores DBLP external ID as either a PID or author name
                    if "/" in dblp_id:
                        links["dblp"] = f"https://dblp.org/pid/{dblp_id}"
                    else:
                        links["dblp"] = f"https://dblp.org/search?q={urllib.parse.quote(dblp_id)}"
                data["links"] = links

                data.setdefault("_enrichment", {})["s2ProfileFetched"] = True

            fetched += 1
            affil_str = affiliations[0] if affiliations else "no affiliation"
            log(f"      -> {result.get('name', '?')} ({affil_str})")
        else:
            log(f"      -> Failed")
            failed += 1

        # Save every 10
        if (i + 1) % 10 == 0:
            save_json(AUTHORS_PATH, authors)
            log(f"    Saved ({fetched} fetched, {failed} failed)")

        if i < len(unique_ids) - 1:
            time.sleep(delay)

    save_json(AUTHORS_PATH, authors)
    log(f"\n  Phase 3 complete: {fetched}/{len(unique_ids)} profiles fetched")


# ---------------------------------------------------------------------------
# Phase 4: Google Scholar Profile Discovery (SerpAPI)
# ---------------------------------------------------------------------------

def check_serpapi_quota(api_key):
    """Check remaining SerpAPI quota. Returns searches left or None on error."""
    params = {"api_key": api_key}
    url = "https://serpapi.com/account.json?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "enrich-authors/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("total_searches_left", 0)
    except Exception:
        return None


def phase_scholar(authors, refs, serpapi_key, force=False):
    """Phase 4: Find Google Scholar profiles via SerpAPI.

    Uses two-step approach:
      Step 1: google_scholar engine with author:"Name" → get profile author_id
      Step 2: google_scholar_author engine → get thumbnail, affiliation, interests
    """
    log("\n=== Phase 4: Google Scholar Profile Discovery ===\n")

    if not serpapi_key:
        log("  ERROR: SerpAPI key required. Use --serpapi-key KEY or set SERPAPI_KEY env var.")
        return

    # Check quota
    quota = check_serpapi_quota(serpapi_key)
    if quota is not None:
        log(f"  SerpAPI quota: {quota} searches remaining")
        if quota < 10:
            log("  ERROR: Not enough SerpAPI quota remaining. Need at least 10.")
            return
    else:
        log("  Warning: Could not check SerpAPI quota")

    # Reserve 5 searches as buffer
    max_searches = (quota - 5) if quota else 200

    # Build author -> refs map for verification
    author_to_refs = {}
    for ref_key, ref in refs.items():
        for ak in ref.get("authors", []):
            author_to_refs.setdefault(ak, []).append(ref_key)

    # Build candidate list: authors eligible for Scholar search
    candidates = []
    for author_key, data in authors.items():
        if data.get("_enrichment", {}).get("confidence") == "skip":
            continue
        if not force and data.get("links", {}).get("googleScholar"):
            continue
        confidence = data.get("_enrichment", {}).get("confidence", "")
        if confidence not in ("high", "medium"):
            continue
        first = data.get("firstName", "")
        last = data.get("lastName", "")
        if not first or not last:
            continue
        # Count how many references cite this author (for prioritization)
        ref_count = len(author_to_refs.get(author_key, []))
        candidates.append((author_key, ref_count))

    # Sort by ref count descending (most-cited authors first)
    candidates.sort(key=lambda x: -x[1])

    log(f"  {len(candidates)} candidates to search")
    log(f"  Budget: ~{max_searches} API calls ({max_searches // 2} authors at 2 calls each)")

    api_calls = 0
    searched = 0
    found = 0
    detail_fetched = 0

    for author_key, ref_count in candidates:
        # Check budget (need 1 for discovery, potentially 1 more for details)
        if api_calls >= max_searches - 1:
            log(f"\n  Budget exhausted after {api_calls} API calls. Stopping.")
            break

        data = authors[author_key]
        first = data.get("firstName", "")
        last = data.get("lastName", "")

        # Step 1: Search google_scholar with author: prefix to find profile
        query = f'author:"{first} {last}"'
        params = {
            "engine": "google_scholar",
            "q": query,
            "num": 1,  # minimize result size, we only want profiles
        }

        result = serpapi_request(params, serpapi_key)
        api_calls += 1
        searched += 1

        if not result:
            log(f"  [{searched}] API error: {author_key} ({first} {last})")
            time.sleep(1)
            continue

        # Extract profiles from the result
        profiles_data = result.get("profiles", {})
        profile_authors = profiles_data.get("authors", []) if isinstance(profiles_data, dict) else []

        if not profile_authors:
            log(f"  [{searched}] No profile: {author_key} ({first} {last})")
            time.sleep(1)
            continue

        # Find best matching profile by name
        best_profile = None
        best_score = 0
        our_name = f"{first} {last}"

        for pa in profile_authors[:3]:
            profile_name = pa.get("name", "")
            score = match_name(our_name, profile_name)
            if score > best_score and score >= 0.8:
                best_score = score
                best_profile = pa

        if not best_profile:
            log(f"  [{searched}] No name match: {author_key} ({first} {last})")
            time.sleep(1)
            continue

        # We have a profile match - save basic info
        scholar_author_id = best_profile.get("author_id", "")
        scholar_link = best_profile.get("link", "")

        links = data.get("links", {})
        if scholar_link:
            links["googleScholar"] = scholar_link
        elif scholar_author_id:
            links["googleScholar"] = f"https://scholar.google.com/citations?user={scholar_author_id}"
        data["links"] = links

        enrichment = data.setdefault("_enrichment", {})
        if scholar_author_id:
            enrichment["scholarId"] = scholar_author_id

        found += 1

        # Step 2: Fetch full author profile for thumbnail/affiliation
        if scholar_author_id and api_calls < max_searches:
            detail_params = {
                "engine": "google_scholar_author",
                "author_id": scholar_author_id,
            }

            detail_result = serpapi_request(detail_params, serpapi_key)
            api_calls += 1
            detail_fetched += 1

            if detail_result and "author" in detail_result:
                author_detail = detail_result["author"]
                thumbnail = author_detail.get("thumbnail", "")
                scholar_affil = author_detail.get("affiliations", "")
                website = author_detail.get("website", "")

                if thumbnail:
                    enrichment["scholarThumbnail"] = thumbnail
                if scholar_affil and not data.get("affiliation"):
                    data["affiliation"] = scholar_affil
                if website and not links.get("homepage"):
                    links["homepage"] = website

                log(f"  [{searched}] Found: {author_key} -> {author_detail.get('name', '')} | {scholar_affil} | thumb={'yes' if thumbnail else 'no'}")
            else:
                log(f"  [{searched}] Found profile but no details: {author_key} ({first} {last})")

            time.sleep(1)
        else:
            log(f"  [{searched}] Found profile (no detail budget): {author_key} ({first} {last})")

        # Save every 10
        if searched % 10 == 0:
            save_json(AUTHORS_PATH, authors)

        time.sleep(1)

    save_json(AUTHORS_PATH, authors)
    log(f"\n  Phase 4 complete:")
    log(f"    Searched:         {searched}")
    log(f"    Profiles found:   {found}")
    log(f"    Details fetched:  {detail_fetched}")
    log(f"    API calls used:   {api_calls}")
    remaining = check_serpapi_quota(serpapi_key)
    if remaining is not None:
        log(f"    API quota left:   {remaining}")


# ---------------------------------------------------------------------------
# Phase 5: Headshot Downloads
# ---------------------------------------------------------------------------

def phase_headshots(authors, force=False):
    """Phase 5: Download Scholar headshot thumbnails."""
    log("\n=== Phase 5: Headshot Downloads ===\n")

    HEADSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    # Create default.svg if it doesn't exist
    default_svg = HEADSHOTS_DIR / "default.svg"
    if not default_svg.exists():
        create_default_svg(default_svg)
        log("  Created default.svg placeholder")

    downloaded = 0
    skipped = 0
    failed = 0

    for author_key, data in authors.items():
        thumbnail_url = data.get("_enrichment", {}).get("scholarThumbnail", "")
        if not thumbnail_url:
            continue

        dest = HEADSHOTS_DIR / f"{author_key}.jpg"

        # Skip if already downloaded (unless --force)
        if not force and dest.exists():
            skipped += 1
            continue

        try:
            req = urllib.request.Request(
                thumbnail_url,
                headers={"User-Agent": "enrich-authors/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                img_data = resp.read()

            dest.write_bytes(img_data)
            data["headshot"] = f"assets/headshots/{author_key}.jpg"
            downloaded += 1
            log(f"  Downloaded: {author_key}")

            # Try to resize with Pillow if available
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(img_data))
                img = img.resize((200, 200), Image.LANCZOS)
                img.save(dest, "JPEG", quality=85)
            except ImportError:
                pass  # Pillow not installed, keep original size

        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            log(f"  Failed: {author_key} ({e})")
            failed += 1

        time.sleep(0.5)

    save_json(AUTHORS_PATH, authors)
    log(f"\n  Phase 5 complete: {downloaded} downloaded, {skipped} already existed, {failed} failed")


def create_default_svg(path):
    """Create a Google Scholar-style silhouette placeholder SVG."""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200" height="200">
  <rect width="200" height="200" fill="#E8E8E8"/>
  <circle cx="100" cy="75" r="40" fill="#BDBDBD"/>
  <ellipse cx="100" cy="185" rx="65" ry="55" fill="#BDBDBD"/>
</svg>"""
    path.write_text(svg, encoding="utf-8")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(authors):
    """Print enrichment statistics."""
    log("\n=== Enrichment Summary ===\n")

    total = len(authors)
    with_s2 = 0
    with_scholar = 0
    with_affiliation = 0
    with_headshot = 0
    with_first_last = 0
    confidence_counts = {"high": 0, "medium": 0, "low": 0, "skip": 0, "none": 0}

    for key, data in authors.items():
        enrichment = data.get("_enrichment", {})
        conf = enrichment.get("confidence", "none")
        confidence_counts[conf] = confidence_counts.get(conf, 0) + 1

        links = data.get("links", {})
        if links.get("semanticScholar"):
            with_s2 += 1
        if links.get("googleScholar"):
            with_scholar += 1
        if data.get("affiliation"):
            with_affiliation += 1
        if data.get("headshot"):
            with_headshot += 1
        if data.get("firstName"):
            with_first_last += 1

    log(f"  Total authors: {total}")
    log(f"  With first/last name: {with_first_last} ({100*with_first_last/total:.0f}%)")
    log(f"  With affiliation:     {with_affiliation} ({100*with_affiliation/total:.0f}%)")
    log(f"  With S2 link:         {with_s2} ({100*with_s2/total:.0f}%)")
    log(f"  With Scholar link:    {with_scholar} ({100*with_scholar/total:.0f}%)")
    log(f"  With headshot:        {with_headshot} ({100*with_headshot/total:.0f}%)")
    log()
    log("  Confidence breakdown:")
    for level in ("high", "medium", "low", "skip", "none"):
        count = confidence_counts.get(level, 0)
        log(f"    {level:8s}: {count:4d} ({100*count/total:.0f}%)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Enrich authors.json with Semantic Scholar and Google Scholar data."
    )
    parser.add_argument(
        "--phase",
        choices=["papers", "match", "s2-authors", "scholar", "headshots"],
        help="Run only this phase",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-enrich already-enriched authors",
    )
    parser.add_argument(
        "--summary", action="store_true",
        help="Print enrichment statistics and exit",
    )
    parser.add_argument(
        "--serpapi-key",
        help="SerpAPI key (or set SERPAPI_KEY env var)",
    )
    parser.add_argument(
        "--s2-api-key",
        help="Semantic Scholar API key (optional, for faster rate limits)",
    )
    args = parser.parse_args()

    # Load data
    authors = load_json(AUTHORS_PATH)
    refs = load_json(REFS_PATH)

    if args.summary:
        print_summary(authors)
        return

    serpapi_key = args.serpapi_key or os.environ.get("SERPAPI_KEY", "")
    s2_api_key = args.s2_api_key or os.environ.get("S2_API_KEY", "")

    # Load or initialize paper cache
    if PAPER_CACHE_PATH.exists():
        paper_cache = load_json(PAPER_CACHE_PATH)
    else:
        paper_cache = {}

    phases_to_run = []
    if args.phase:
        phases_to_run = [args.phase]
    else:
        phases_to_run = ["papers", "match", "s2-authors"]
        if serpapi_key:
            phases_to_run.extend(["scholar", "headshots"])
        else:
            log("Note: Skipping Scholar/headshot phases (no SERPAPI_KEY). "
                  "Use --serpapi-key or set SERPAPI_KEY env var.")

    for phase in phases_to_run:
        if phase == "papers":
            phase_papers(refs, paper_cache, s2_api_key=s2_api_key, force=args.force)
        elif phase == "match":
            phase_match(authors, refs, paper_cache, force=args.force)
        elif phase == "s2-authors":
            phase_s2_authors(authors, s2_api_key=s2_api_key, force=args.force,
                             paper_cache=paper_cache, refs=refs)
        elif phase == "scholar":
            phase_scholar(authors, refs, serpapi_key, force=args.force)
        elif phase == "headshots":
            phase_headshots(authors, force=args.force)

        # Reload authors after each phase in case it was modified
        authors = load_json(AUTHORS_PATH)

    print_summary(authors)
    log("\nDone!")


if __name__ == "__main__":
    main()

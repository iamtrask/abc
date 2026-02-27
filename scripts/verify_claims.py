#!/usr/bin/env python3
"""
Phase 3: Claim-reference alignment verification.

Loads citation-audit.json (needs Phase 1 claim contexts + Phase 2 url_checks),
prepares verification prompts for each citation, and supports interactive review.

Designed to run interactively with Claude Code or manually.

Usage:
    python3 scripts/verify_claims.py                     # show all unverified
    python3 scripts/verify_claims.py --chapter index      # one chapter only
    python3 scripts/verify_claims.py --batch-size 10      # show N at a time
    python3 scripts/verify_claims.py --set ID STATUS "reason"  # record a verdict
    python3 scripts/verify_claims.py --summary            # show verification summary
    python3 scripts/verify_claims.py --export-prompts     # export prompts for batch review
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
AUDIT_FILE = DATA_DIR / "citation-audit.json"
REFS_FILE = DATA_DIR / "references.json"

VALID_STATUSES = {
    "supported",
    "plausible",
    "unsupported",
    "mismatch",
    "unverifiable",
}


def load_audit():
    """Load the audit data file."""
    if not AUDIT_FILE.exists():
        print("ERROR: citation-audit.json not found. Run extract_claims.py first.", file=sys.stderr)
        sys.exit(1)
    with open(AUDIT_FILE) as f:
        return json.load(f)


def load_references():
    """Load the references database."""
    with open(REFS_FILE) as f:
        return json.load(f)


def save_audit(audit_data):
    """Write audit data to disk (crash-safe)."""
    tmp_path = AUDIT_FILE.with_suffix(".json.tmp")
    with open(tmp_path, "w") as f:
        json.dump(audit_data, f, indent=2, ensure_ascii=False)
    tmp_path.rename(AUDIT_FILE)


def format_prompt(citation, ref_data, url_check):
    """Format a verification prompt for a single citation."""
    lines = []
    lines.append(f"--- Citation: {citation['id']} ---")
    lines.append(f"Chapter: {citation['chapter']}, Section: {citation['section_id']}")
    lines.append(f"Cite label: {citation['cite_label']}")
    lines.append("")
    lines.append("CLAIM CONTEXT (from thesis):")
    lines.append(f"  \"{citation['claim_context']}\"")
    lines.append("")
    lines.append("REFERENCE:")
    if ref_data:
        title = ref_data.get("title", "?")
        year = ref_data.get("year", "?")
        authors = ref_data.get("authors", [])
        # Format author names
        author_str = ", ".join(a.replace("_", " ").title() for a in authors[:5])
        if len(authors) > 5:
            author_str += f" et al. ({len(authors)} total)"
        lines.append(f"  Title: {title}")
        lines.append(f"  Authors: {author_str}")
        lines.append(f"  Year: {year}")
        venue = ref_data.get("venue") or ref_data.get("venueShort") or ""
        if venue:
            lines.append(f"  Venue: {venue}")
        url = ref_data.get("url", "")
        if url:
            lines.append(f"  URL: {url}")
    else:
        lines.append(f"  [No reference data for key: {citation['bibtex_key']}]")

    if url_check:
        abstract = url_check.get("abstract", "")
        source_type = url_check.get("source_type", "?")
        access_type = url_check.get("access_type", "?")
        lines.append(f"  Source type: {source_type}, Access: {access_type}")
        if abstract:
            # Truncate long abstracts
            if len(abstract) > 500:
                abstract = abstract[:497] + "..."
            lines.append(f"  Abstract: {abstract}")
    else:
        lines.append("  [No URL check data — run check_urls.py first]")

    lines.append("")
    lines.append("VERDICT? (supported / plausible / unsupported / mismatch / unverifiable)")
    lines.append("")
    return "\n".join(lines)


def show_unverified(audit_data, references, chapter=None, batch_size=None):
    """Show unverified citations as formatted prompts."""
    url_checks = audit_data.get("url_checks", {})
    citations = audit_data.get("citations", [])

    # Filter to unverified
    unverified = [c for c in citations if c.get("verification") is None]
    if chapter:
        unverified = [c for c in unverified if c["chapter"] == chapter]

    if not unverified:
        print("All citations are verified!")
        return

    if batch_size:
        unverified = unverified[:batch_size]

    total_remaining = len([c for c in citations if c.get("verification") is None])
    total = len(citations)
    print(f"Showing {len(unverified)} unverified citations ({total_remaining} remaining of {total} total)\n")

    for citation in unverified:
        bib_key = citation.get("bibtex_key", "")
        ref_data = references.get(bib_key)
        url_check = url_checks.get(bib_key)
        print(format_prompt(citation, ref_data, url_check))


def export_prompts(audit_data, references, chapter=None):
    """Export all unverified citations as a single JSON array for batch processing."""
    url_checks = audit_data.get("url_checks", {})
    citations = audit_data.get("citations", [])

    unverified = [c for c in citations if c.get("verification") is None]
    if chapter:
        unverified = [c for c in unverified if c["chapter"] == chapter]

    prompts = []
    for citation in unverified:
        bib_key = citation.get("bibtex_key", "")
        ref_data = references.get(bib_key, {})
        url_check = url_checks.get(bib_key, {})

        prompts.append({
            "id": citation["id"],
            "chapter": citation["chapter"],
            "section_id": citation["section_id"],
            "cite_label": citation["cite_label"],
            "claim_context": citation["claim_context"],
            "ref_title": ref_data.get("title", ""),
            "ref_authors": ref_data.get("authors", []),
            "ref_year": ref_data.get("year"),
            "ref_venue": ref_data.get("venue", ""),
            "ref_url": ref_data.get("url", ""),
            "abstract": url_check.get("abstract", ""),
            "source_type": url_check.get("source_type", ""),
            "access_type": url_check.get("access_type", ""),
        })

    output_path = DATA_DIR / "verification-prompts.json"
    with open(output_path, "w") as f:
        json.dump(prompts, f, indent=2, ensure_ascii=False)
    print(f"Exported {len(prompts)} prompts to {output_path}")


def set_verdict(audit_data, citation_id, status, reasoning):
    """Set a verification verdict for a specific citation."""
    if status not in VALID_STATUSES:
        print(f"ERROR: Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}", file=sys.stderr)
        sys.exit(1)

    citations = audit_data.get("citations", [])
    found = False
    for citation in citations:
        if citation["id"] == citation_id:
            citation["verification"] = {
                "status": status,
                "reasoning": reasoning,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            found = True
            break

    if not found:
        print(f"ERROR: Citation '{citation_id}' not found.", file=sys.stderr)
        sys.exit(1)

    save_audit(audit_data)
    print(f"Set {citation_id} = {status}")


def batch_set_verdicts(audit_data, verdicts_file):
    """Apply verdicts from a JSON file: [{"id": "...", "status": "...", "reasoning": "..."}]."""
    with open(verdicts_file) as f:
        verdicts = json.load(f)

    citations_by_id = {c["id"]: c for c in audit_data.get("citations", [])}
    applied = 0

    for v in verdicts:
        cid = v["id"]
        status = v["status"]
        reasoning = v.get("reasoning", "")

        if status not in VALID_STATUSES:
            print(f"  SKIP: {cid} — invalid status '{status}'", file=sys.stderr)
            continue
        if cid not in citations_by_id:
            print(f"  SKIP: {cid} — not found", file=sys.stderr)
            continue

        citations_by_id[cid]["verification"] = {
            "status": status,
            "reasoning": reasoning,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        applied += 1

    save_audit(audit_data)
    print(f"Applied {applied} verdicts from {verdicts_file}")


def show_summary(audit_data):
    """Show a summary of verification status."""
    citations = audit_data.get("citations", [])
    url_checks = audit_data.get("url_checks", {})

    # Verification status
    statuses = {}
    unverified = 0
    for c in citations:
        v = c.get("verification")
        if v is None:
            unverified += 1
        else:
            s = v.get("status", "unknown")
            statuses[s] = statuses.get(s, 0) + 1

    print("=" * 60)
    print("CITATION AUDIT SUMMARY")
    print("=" * 60)
    print(f"\nTotal citations: {len(citations)}")
    print(f"Verified: {len(citations) - unverified}")
    print(f"Unverified: {unverified}")

    if statuses:
        print("\nVerification verdicts:")
        for s in ["supported", "plausible", "unsupported", "mismatch", "unverifiable"]:
            count = statuses.get(s, 0)
            if count:
                print(f"  {s}: {count}")

    # URL check status
    print(f"\nURL checks: {len(url_checks)} of 178")
    if url_checks:
        failed = [k for k, v in url_checks.items() if v.get("error")]
        unavailable = [k for k, v in url_checks.items() if v.get("access_type") == "unavailable"]
        print(f"  Failed: {len(failed)}")
        print(f"  Unavailable: {len(unavailable)}")
        if failed:
            print("\n  Failed URLs:")
            for k in failed[:10]:
                err = url_checks[k].get("error", "?")
                print(f"    {k}: {err[:60]}")
            if len(failed) > 10:
                print(f"    ...and {len(failed) - 10} more")

    # Flagged issues
    flagged = [c for c in citations if (c.get("verification") or {}).get("status") in ("unsupported", "mismatch")]
    if flagged:
        print(f"\nFLAGGED CITATIONS ({len(flagged)}):")
        for c in flagged:
            v = c["verification"]
            print(f"  {c['id']}: {v['status']} — {v.get('reasoning', '')[:80]}")

    # Non-public sources
    non_public = [
        (k, v) for k, v in url_checks.items()
        if v.get("access_type") in ("book", "paywall", "abstract_only")
    ]
    if non_public:
        print(f"\nNon-public sources ({len(non_public)}):")
        for k, v in non_public[:10]:
            official = v.get("official_url", v.get("url", "?"))
            print(f"  {k}: {v['access_type']} — {official[:70]}")
        if len(non_public) > 10:
            print(f"  ...and {len(non_public) - 10} more")

    # By chapter
    print("\nBy chapter:")
    by_chapter = {}
    for c in citations:
        ch = c["chapter"]
        by_chapter.setdefault(ch, {"total": 0, "verified": 0, "flagged": 0})
        by_chapter[ch]["total"] += 1
        if c.get("verification"):
            by_chapter[ch]["verified"] += 1
            if c["verification"].get("status") in ("unsupported", "mismatch"):
                by_chapter[ch]["flagged"] += 1

    for ch, stats in by_chapter.items():
        v = stats["verified"]
        t = stats["total"]
        f = stats["flagged"]
        flag_str = f" ({f} flagged)" if f else ""
        print(f"  {ch}: {v}/{t} verified{flag_str}")


def main():
    parser = argparse.ArgumentParser(description="Verify claim-reference alignment")
    parser.add_argument("--chapter", help="Filter to a specific chapter")
    parser.add_argument("--batch-size", type=int, help="Show N citations at a time")
    parser.add_argument(
        "--set",
        nargs=3,
        metavar=("ID", "STATUS", "REASONING"),
        help="Set a verdict for a citation",
    )
    parser.add_argument(
        "--batch-verdicts",
        metavar="FILE",
        help="Apply verdicts from a JSON file",
    )
    parser.add_argument("--summary", action="store_true", help="Show summary")
    parser.add_argument(
        "--export-prompts", action="store_true", help="Export prompts for batch review"
    )
    args = parser.parse_args()

    audit_data = load_audit()
    references = load_references()

    if args.summary:
        show_summary(audit_data)
    elif args.set:
        cid, status, reasoning = args.set
        set_verdict(audit_data, cid, status, reasoning)
    elif args.batch_verdicts:
        batch_set_verdicts(audit_data, args.batch_verdicts)
    elif args.export_prompts:
        export_prompts(audit_data, references, chapter=args.chapter)
    else:
        show_unverified(audit_data, references, chapter=args.chapter, batch_size=args.batch_size)


if __name__ == "__main__":
    main()

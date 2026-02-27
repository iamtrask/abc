#!/usr/bin/env python3
"""
Deduplicate reference lists and renumber entries.

For each chapter:
1. Load chapter-map.json to identify duplicate BibTeX keys
2. For each duplicate set, keep the lowest-numbered <li> entry
3. Rewrite all <a href="#ref-N"> citations to point to the kept entry
4. Remove duplicate <li> entries from the <ol>
5. Renumber remaining entries sequentially (ref-1, ref-2, ...)
6. Update all citation hrefs to reflect new numbering
"""

import json
import re
import sys
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


def build_redirect_map(chapter_map_entry):
    """Build a mapping of ref numbers to redirect.

    For each BibTeX key that appears multiple times, all higher-numbered
    entries redirect to the lowest-numbered entry.
    Returns: {old_num: canonical_num, ...}
    """
    key_to_nums = {}
    for num_str, bib_key in chapter_map_entry.items():
        key_to_nums.setdefault(bib_key, []).append(int(num_str))

    redirects = {}
    entries_to_remove = set()
    for bib_key, nums in key_to_nums.items():
        if len(nums) > 1:
            canonical = min(nums)
            for num in nums:
                if num != canonical:
                    redirects[num] = canonical
                    entries_to_remove.add(num)

    return redirects, entries_to_remove


def build_renumber_map(all_nums, entries_to_remove):
    """Build a mapping from old ref numbers to new sequential numbers.

    After removing duplicates, renumber remaining entries 1, 2, 3, ...
    Returns: {old_num: new_num, ...}
    """
    remaining = sorted(set(all_nums) - entries_to_remove)
    return {old: new for new, old in enumerate(remaining, 1)}


def process_chapter(slug, filename, chapter_map_entry):
    """Process one HTML file: dedup, redirect citations, renumber."""
    html_path = ROOT / filename
    html = html_path.read_text(encoding='utf-8')

    # Step 1: Build redirect map (duplicate → canonical)
    redirects, entries_to_remove = build_redirect_map(chapter_map_entry)

    all_nums = [int(n) for n in chapter_map_entry.keys()]

    if not entries_to_remove:
        # Still might need renumbering (e.g. gaps)
        renumber = build_renumber_map(all_nums, set())
        needs_renumber = any(old != new for old, new in renumber.items())
        if not needs_renumber:
            print(f"  {slug}: no changes needed")
            return False
        print(f"  {slug}: renumbering only ({len(all_nums)} entries)")
    else:
        print(f"  {slug}: removing {len(entries_to_remove)} duplicates, "
              f"renumbering {len(all_nums) - len(entries_to_remove)} entries")

    # Step 2: Build the full old→new mapping
    # First apply redirects (point duplicates to canonical)
    # Then renumber everything that remains
    renumber = build_renumber_map(all_nums, entries_to_remove)

    # Combined mapping: for any ref number, what's the final new number?
    # - If it's a duplicate, first redirect to canonical, then renumber
    # - If it's kept, just renumber
    final_map = {}
    for old_num in all_nums:
        if old_num in redirects:
            canonical = redirects[old_num]
            final_map[old_num] = renumber[canonical]
        else:
            final_map[old_num] = renumber[old_num]

    # Step 3: Update all <a href="#ref-N"> citations
    def replace_citation(m):
        old_num = int(m.group(1))
        if old_num in final_map:
            return f'href="#ref-{final_map[old_num]}"'
        return m.group(0)

    html = re.sub(r'href="#ref-(\d+)"', replace_citation, html)

    # Step 4: Remove duplicate <li> entries and renumber remaining ones
    def replace_li_id(m):
        old_num = int(m.group(1))
        if old_num in entries_to_remove:
            return f'__REMOVE__{m.group(0)}'  # mark for removal
        if old_num in renumber:
            return f'id="ref-{renumber[old_num]}"'
        return m.group(0)

    html = re.sub(r'id="ref-(\d+)"', replace_li_id, html)

    # Remove marked <li> entries (the entire <li>...</li> block)
    # We need to carefully remove <li __REMOVE__...>...</li>
    while '__REMOVE__' in html:
        # Match <li __REMOVE__id="ref-N">...</li> including newlines
        pattern = r'\s*<li __REMOVE__id="ref-\d+"[^>]*>.*?</li>'
        new_html = re.sub(pattern, '', html, count=1, flags=re.DOTALL)
        if new_html == html:
            # Fallback: try with more whitespace flexibility
            pattern = r'\n?\s*<li __REMOVE__id="ref-\d+"[\s\S]*?</li>'
            new_html = re.sub(pattern, '', html, count=1)
        if new_html == html:
            print(f"    WARNING: could not remove a marked entry in {slug}")
            # Clean up the marker to avoid infinite loop
            html = html.replace('__REMOVE__', '', 1)
        else:
            html = new_html

    html_path.write_text(html, encoding='utf-8')
    return True


def main():
    with open(DATA_DIR / "chapter-map.json") as f:
        chapter_map = json.load(f)

    print("Deduplicating and renumbering references...\n")

    changed = False
    for slug, filename in CHAPTER_FILES:
        cm = chapter_map.get(slug, {})
        if process_chapter(slug, filename, cm):
            changed = True

    if changed:
        print("\nDone. Re-run build_ref_db.py to regenerate JSON databases.")
    else:
        print("\nNo changes needed.")


if __name__ == '__main__':
    main()

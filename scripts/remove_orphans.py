#!/usr/bin/env python3
"""
Remove specific orphaned reference entries and renumber.

These are refs that exist in the <ol> but are never cited in body text:
- index.html: ref-21, ref-23
- chapter2.html: ref-7, ref-16, ref-22
- chapter3.html: ref-4 (duplicate of ref-35 under different BibTeX key)
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REMOVALS = {
    "index.html": {21, 23},
    "chapter2.html": {7, 16, 22},
    "chapter3.html": {4},
}


def process_file(filename, to_remove):
    path = ROOT / filename
    html = path.read_text(encoding='utf-8')

    # Find all current ref entry numbers
    entry_nums = sorted(int(m.group(1)) for m in re.finditer(r'id="ref-(\d+)"', html))

    # Build renumber map: remaining entries get sequential numbers
    remaining = [n for n in entry_nums if n not in to_remove]
    renumber = {old: new for new, old in enumerate(remaining, 1)}

    # Also need to map removed refs' citations (if any somehow exist)
    # to the nearest remaining ref. But these are orphaned, so no citations exist.

    print(f"\n{filename}:")
    print(f"  Removing refs: {sorted(to_remove)}")
    print(f"  {len(entry_nums)} → {len(remaining)} entries")

    # Step 1: Update all href="#ref-N" citations to new numbers
    def replace_citation(m):
        old_num = int(m.group(1))
        if old_num in renumber:
            return f'href="#ref-{renumber[old_num]}"'
        return m.group(0)  # shouldn't happen for orphaned refs

    html = re.sub(r'href="#ref-(\d+)"', replace_citation, html)

    # Step 2: Mark entries for removal, renumber the rest
    def replace_li_id(m):
        old_num = int(m.group(1))
        if old_num in to_remove:
            return f'__REMOVE__id="ref-{old_num}"'
        if old_num in renumber:
            return f'id="ref-{renumber[old_num]}"'
        return m.group(0)

    html = re.sub(r'id="ref-(\d+)"', replace_li_id, html)

    # Step 3: Remove marked <li> entries
    while '__REMOVE__' in html:
        pattern = r'\s*<li __REMOVE__id="ref-\d+"[^>]*>.*?</li>'
        new_html = re.sub(pattern, '', html, count=1, flags=re.DOTALL)
        if new_html == html:
            pattern = r'\n?\s*<li __REMOVE__id="ref-\d+"[\s\S]*?</li>'
            new_html = re.sub(pattern, '', html, count=1)
        if new_html == html:
            print(f"  WARNING: could not remove a marked entry")
            html = html.replace('__REMOVE__', '', 1)
        else:
            html = new_html

    path.write_text(html, encoding='utf-8')
    print(f"  Done")


def main():
    for filename, to_remove in REMOVALS.items():
        process_file(filename, to_remove)

    print("\nDone. Re-run build_ref_db.py to regenerate JSON databases.")


if __name__ == '__main__':
    main()

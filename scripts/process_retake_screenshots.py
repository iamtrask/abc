#!/usr/bin/env python3
"""
Process retake screenshots:
  1. Copy already-named JPGs from retake/ to assets/screenshots/
  2. Rename, convert, and copy manual-retake PNGs to assets/screenshots/
  3. Update references.json with screenshot paths

Usage:
  python3 scripts/process_retake_screenshots.py --dry-run   # preview
  python3 scripts/process_retake_screenshots.py              # execute
"""

import json
import re
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
REFS_PATH = ROOT / "data" / "references.json"
RETAKE_DIR = ROOT / "assets" / "screenshots" / "retake"
MANUAL_DIR = RETAKE_DIR / "manual-retakes"
OUT_DIR = ROOT / "assets" / "screenshots"
TARGET_WIDTH = 800
JPEG_QUALITY = 82

# macOS uses U+202F (narrow no-break space) before AM/PM in screenshot filenames
NBSP = "\u202f"


def _ss(time_str):
    """Build macOS screenshot filename with correct narrow no-break space."""
    return f"Screenshot 2026-02-28 at {time_str}{NBSP}AM.png"


# -----------------------------------------------------------------------
# Mapping: manual-retake screenshot filename → reference key
# Built by visual inspection of all 54 screenshots.
# Order follows retake_screenshots.md in reverse (items 53→1).
# Screenshot 11.22.19 is a duplicate of Rieke_2020 (skipped in favor of 11.28.39).
# -----------------------------------------------------------------------

MANUAL_MAPPING = {
    _ss("10.49.19"): "wang_2020_selfsovereign",
    _ss("10.49.30"): "weights2025sweeps",
    _ss("10.50.07"): "welle2025aligning",
    _ss("10.50.48"): "wiggers2024openai",
    _ss("10.50.57"): "weforumAIGovernance2023",
    _ss("10.51.08"): "wealand2025reducing",
    _ss("10.51.42"): "veliz_2020_privacy",
    _ss("10.52.13"): "summerfield2025impact",
    _ss("10.53.00"): "slate2018klout",
    _ss("10.53.32"): "simmons2022gdpr",
    _ss("10.53.51"): "sienkiewicz2025data",
    _ss("10.54.00"): "sevilla2024training",
    _ss("10.54.13"): "scott2021coordinating",
    _ss("10.54.35"): "owenjackson2024opensource",
    _ss("10.54.52"): "obrien2025reddit",
    _ss("10.55.22"): "mider_osint_2024",
    _ss("10.55.58"): "mehta2024zuckerberg",
    _ss("10.56.50"): "macrotrends2024nvidia",
    _ss("10.57.04"): "loftus2011secure",
    _ss("10.57.14"): "lecun2015deep",
    _ss("10.57.44"): "laurie2014certificate",
    _ss("10.58.33"): "krizhevsky2012imagenet",
    _ss("10.58.51"): "kaissis_2020",
    _ss("10.59.07"): "internet_archive_donation",
    _ss("10.59.23"): "imperva2024bots",
    _ss("10.59.57"): "ibmAIPrinciples2018",
    _ss("11.00.08"): "howley2023nvidia",
    _ss("11.00.22"): "hootsuite2024",
    _ss("11.00.36"): "harvardPrincipledAI2020",
    _ss("11.01.29"): "goldhaber1997attention",
    _ss("11.01.55"): "global_cancer_screening",
    _ss("11.03.35"): "fortune2014klout",
    _ss("11.04.10"): "fecher_2015_what",
    _ss("11.04.23"): "fcdo2022trollfarm",
    _ss("11.04.32"): "epoch2025openaicomputespend",
    _ss("11.04.40"): "epoch2024hardware",
    _ss("11.04.51"): "ecWhitePaperAI2020",
    _ss("11.04.56"): "ecGermanyAI2024",
    _ss("11.05.03"): "ecFranceAI2024",
    _ss("11.05.15"): "dwork2006calibrating",
    _ss("11.05.29"): "dunbar1993coevolution",
    _ss("11.06.40"): "donfro2013yelp",
    _ss("11.06.58"): "cross2022fake",
    _ss("11.07.19"): "costan2016intel",
    _ss("11.07.31"): "boneh2011functional",
    _ss("11.07.58"): "bhattacharyya2023high",
    _ss("11.08.58"): "associatedpress2025anthropic",
    _ss("11.09.25"): "ascoli2015sharing",
    _ss("11.09.39"): "adikari2015real",
    _ss("11.10.46"): "Yao1982ProtocolsFS",
    # 11.22.19 is a first take of Rieke_2020 — skip (use 11.28.39 instead)
    _ss("11.28.39"): "Rieke_2020",
    _ss("11.29.02"): "Kaye2025NvidiaFirstCompany",
    _ss("11.29.13"): "EpochAIModels2025",
}

# Duplicate to skip
SKIP = {
    _ss("11.22.19"),  # first take of Rieke_2020 (superseded by 11.28.39)
}


def safe_filename(key):
    """Sanitize a BibTeX key for use as a filename."""
    return re.sub(r'[/:*?"<>|]', '_', key)


def convert_and_save(src_path, dst_path):
    """Convert image to 800px-wide JPEG."""
    img = Image.open(src_path).convert("RGB")
    w, h = img.size
    if w != TARGET_WIDTH:
        scale = TARGET_WIDTH / w
        new_h = int(h * scale)
        img = img.resize((TARGET_WIDTH, new_h), Image.LANCZOS)
    img.save(str(dst_path), "JPEG", quality=JPEG_QUALITY)


def main():
    dry_run = "--dry-run" in sys.argv

    refs = json.load(open(REFS_PATH))

    print("=" * 60)
    print("Process Retake Screenshots")
    print("=" * 60)

    # --- Phase 1: Copy already-named JPGs from retake/ ---
    print("\n--- Phase 1: Copy retake/ JPGs ---")
    retake_copied = 0
    retake_errors = 0

    for jpg_file in sorted(RETAKE_DIR.glob("*.jpg")):
        ref_key = jpg_file.stem
        fname = safe_filename(ref_key)
        dst_path = OUT_DIR / f"{fname}.jpg"
        rel_path = f"assets/screenshots/{fname}.jpg"

        if ref_key not in refs:
            print(f"  WARN  {ref_key} not in references.json — copying anyway")

        print(f"  COPY  {jpg_file.name} → {dst_path.name}")

        if not dry_run:
            shutil.copy2(str(jpg_file), str(dst_path))
            if ref_key in refs:
                refs[ref_key]["screenshot"] = rel_path
            retake_copied += 1
        else:
            retake_copied += 1

    # --- Phase 2: Convert manual-retake PNGs ---
    print(f"\n--- Phase 2: Convert manual-retakes/ PNGs ---")
    manual_converted = 0
    manual_errors = 0

    for src_name, ref_key in sorted(MANUAL_MAPPING.items(), key=lambda x: x[0]):
        src_path = MANUAL_DIR / src_name

        if not src_path.exists():
            print(f"  MISSING  {src_name}")
            manual_errors += 1
            continue

        if ref_key not in refs:
            print(f"  BAD KEY  {ref_key} (not in references.json)")
            manual_errors += 1
            continue

        fname = safe_filename(ref_key)
        dst_path = OUT_DIR / f"{fname}.jpg"
        rel_path = f"assets/screenshots/{fname}.jpg"

        print(f"  CONVERT  {src_name}")
        print(f"           → {fname}.jpg  ({ref_key})")

        if not dry_run:
            convert_and_save(src_path, dst_path)
            refs[ref_key]["screenshot"] = rel_path
            manual_converted += 1
        else:
            manual_converted += 1

    # Report skipped duplicates
    print(f"\n--- Skipped {len(SKIP)} duplicate screenshots ---")
    for s in sorted(SKIP):
        print(f"  SKIP {s}")

    # Save updated references.json
    if not dry_run:
        with open(REFS_PATH, "w") as f:
            json.dump(refs, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"\n  Updated {REFS_PATH}")

    # Summary
    null_count = sum(1 for r in refs.values() if not r.get("screenshot"))
    print(f"\n{'=' * 60}")
    print(f"Summary:")
    print(f"  Retake JPGs copied:       {retake_copied}")
    print(f"  Manual PNGs converted:    {manual_converted}")
    print(f"  Errors:                   {retake_errors + manual_errors}")
    print(f"  Refs still without screenshots: {null_count}")
    print(f"  Total refs: {len(refs)}")


if __name__ == "__main__":
    main()

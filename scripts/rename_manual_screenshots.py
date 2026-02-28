#!/usr/bin/env python3
"""
Rename and convert manually-captured screenshots to match reference keys.

Converts PNG screenshots to 800px-wide JPG files, names them by reference key,
moves them to assets/screenshots/, and updates references.json.

Usage:
  python3 scripts/rename_manual_screenshots.py --dry-run   # preview
  python3 scripts/rename_manual_screenshots.py              # execute
"""

import json
import re
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
REFS_PATH = ROOT / "data" / "references.json"
MANUAL_DIR = ROOT / "assets" / "screenshots" / "manual-screenshots"
OUT_DIR = ROOT / "assets" / "screenshots"
TARGET_WIDTH = 800
JPEG_QUALITY = 82

# -----------------------------------------------------------------------
# Mapping: screenshot filename → reference key
# Identified by visually inspecting each screenshot against the manual
# audit list in data/manual_screenshot_audit.md
# -----------------------------------------------------------------------

# macOS uses U+202F (narrow no-break space) before AM/PM in screenshot filenames
NBSP = "\u202f"


def _ss(time_str):
    """Build macOS screenshot filename with correct narrow no-break space."""
    return f"Screenshot 2026-02-28 at {time_str}{NBSP}AM.png"


MAPPING = {
    # -- Blocked/Cloudflare page (31) --
    _ss("9.32.04"): "10.36227/techrxiv.171837853.31531482/v1",
    _ss("9.34.13"): "Abadi_2016",
    _ss("9.34.50"): "GRAVEL2023226",
    _ss("9.35.19"): "Hu_Cai_2024",
    _ss("9.35.46"): "Tong_Martina_2024",
    _ss("9.36.38"): "ai_bioweapon",
    _ss("9.37.07"): "berger2025ai",
    _ss("9.37.59"): "burt2003social",
    _ss("9.38.09"): "doi:10.1073/pnas.1611835114",
    _ss("9.38.22"): "dwork2014algorithmic",
    _ss("9.38.36"): "gentry2009fully",
    _ss("9.39.09"): "goldwasser1989knowledge",
    _ss("9.39.30"): "grow2025zuckerberg",
    _ss("9.40.23"): "granovetter1973strength",
    _ss("9.41.18"): "grynbaum2023times",
    _ss("9.43.13"): "health_sharing_incentives",
    _ss("9.44.11"): "kachwala2024nvidia",
    _ss("9.46.15"): "ntia2024aiweights",
    _ss("9.47.02"): "ntoutsi2020bias",
    _ss("9.47.43"): "privacy_blocks_medical_sharing",
    _ss("9.48.38"): "samuelson2023generative",
    _ss("9.49.04"): "shamir1979share",
    _ss("9.49.28"): "shu2020combating",
    _ss("9.49.55"): "ssi",
    _ss("9.50.29"): "us_cancer_screening",
    _ss("9.50.49"): "vaccari_deepfakes_2020",
    _ss("9.51.05"): "zuccon_hallucination_attribution",

    # -- JSTOR access block (2) --
    _ss("9.53.30"): "2f928592-a19d-38f4-91e4-45f12ea471a0",
    _ss("9.52.58"): "freeman1977set",

    # -- Modal overlay (2) --
    _ss("9.53.46"): "statista2025advertising",
    _ss("9.54.03"): "taylor2024data",

    # -- Cookie popup (1) --
    _ss("9.54.21"): "mirvish2011hathaway",

    # -- Unusable screenshot (7) --
    _ss("9.54.50"): "bogdanov2014input",
    _ss("9.55.10"): "elsea2006protection",
    _ss("9.55.34"): "lawrence1999digital",
    _ss("9.55.43"): "lobo2023right",
    _ss("9.55.52"): "openai2024learning",
    _ss("9.56.09"): "smpc_ml",
    _ss("9.56.19"): "synthetic_data_privacy",

    # -- Failed to collect (2 of 3; roozbahani2025review still unreachable) --
    _ss("9.56.41"): "industryAustraliaAI2024",
    _ss("9.56.57"): "page1999pagerank",

    # -- Journal cover for hochreiter1998vanishing --
    "cover.jpg": "hochreiter1998vanishing",

    # -- PDF paper versions (preferred over web page duplicates above) --
    _ss("9.41.57"): "haveliwala2002topicsensitive",
    _ss("9.42.17"): "gpu_shortage",
    _ss("9.42.32"): "goldreich1987towards",
}

# Duplicate web page versions (skip these — we use the PDF paper screenshots above)
SKIP = {
    _ss("9.38.46"),  # web page duplicate of goldreich1987towards
    _ss("9.39.18"),  # web page duplicate of gpu_shortage
    _ss("9.41.34"),  # web page duplicate of haveliwala2002topicsensitive
}


def safe_filename(key):
    """Sanitize a BibTeX key for use as a filename (matches collect_screenshots.py)."""
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
    print("Manual Screenshot Rename & Convert")
    print("=" * 60)

    processed = 0
    skipped = 0
    errors = 0

    for src_name, ref_key in sorted(MAPPING.items(), key=lambda x: x[0]):
        src_path = MANUAL_DIR / src_name

        if not src_path.exists():
            print(f"  MISSING  {src_name}")
            errors += 1
            continue

        if ref_key not in refs:
            print(f"  BAD KEY  {ref_key} (not in references.json)")
            errors += 1
            continue

        fname = safe_filename(ref_key)
        dst_path = OUT_DIR / f"{fname}.jpg"
        rel_path = f"assets/screenshots/{fname}.jpg"

        print(f"  {src_name}")
        print(f"    → {fname}.jpg  ({ref_key})")

        if not dry_run:
            convert_and_save(src_path, dst_path)
            refs[ref_key]["screenshot"] = rel_path
            processed += 1
        else:
            processed += 1

    # Report skipped duplicates
    print(f"\n--- Skipped {len(SKIP)} duplicate PDF screenshots ---")
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
    print(f"  Processed: {processed}")
    print(f"  Skipped:   {len(SKIP)} (duplicates)")
    print(f"  Errors:    {errors}")
    print(f"  Refs still without screenshots: {null_count}")
    print(f"  Total refs: {len(refs)}")


if __name__ == "__main__":
    main()

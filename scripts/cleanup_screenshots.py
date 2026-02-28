#!/usr/bin/env python3
"""
Clean up screenshot audit results:
  1. Remove blocked/unusable/JSTOR screenshots → add to manual audit MD
  2. Crop cookie banners from affected screenshots
  3. Leave false positives alone (they're fine)
  4. Update references.json

Usage:
  python3 scripts/cleanup_screenshots.py
  python3 scripts/cleanup_screenshots.py --dry-run
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
REFS_PATH = ROOT / "data" / "references.json"
AUDIT_PATH = ROOT / "data" / "screenshot_audit.json"
SCREENSHOTS_DIR = ROOT / "assets" / "screenshots"
MANUAL_AUDIT_PATH = ROOT / "data" / "manual_screenshot_audit.md"
JPEG_QUALITY = 82

# ---------------------------------------------------------------------------
# Classification overrides based on visual inspection
# ---------------------------------------------------------------------------

# These "cookie_popup" items are actually clean (false positives)
FALSE_POSITIVES = {
    "meta2024llama.jpg",
    "costan2016intel.jpg",
    "obrien2025reddit.jpg",
    "ming2024nvidia.jpg",
    "grybauskas2023twitter.jpg",
    "montrealDeclaration2024.jpg",
    "internet_archive_donation.jpg",
    "data_sharing_doesnt_happen.jpg",
    "turingAIethics2019.jpg",
    "mider_osint_2024.jpg",
    "slate2018klout.jpg",
    "accessNowTorontoDeclaration2023.jpg",
}

# These "cookie_popup" items have modal overlays that can't be cropped
MODAL_UNUSABLE = {
    "statista2025advertising.jpg",
    "taylor2024data.jpg",
}

# These "review" items are JSTOR blocks (should be removed)
REVIEW_BLOCKED = {
    "freeman1977set.jpg",
    "2f928592-a19d-38f4-91e4-45f12ea471a0.jpg",
}

# These "review" items are actually fine
REVIEW_OK = {
    "amodei2016concreteproblemsaisafety.jpg",
    "scaling_laws_2020.jpg",
    "krizhevsky2012imagenet.jpg",
    "chase2020signal.jpg",
    "futureOfLifeAIPrinciples2024.jpg",
    "wikipedia_commoncrawl_2024.jpg",
    "goldhaber1997attention.jpg",
    "osi_osaid_2024.jpg",
    "schmidt2014google.jpg",
    "idp.jpg",
    "grover2018mnist.jpg",
    "educating_silicon_2024.jpg",
    "laurie2014certificate.jpg",
    "crispweed2024alignment.jpg",
    "fortune2014klout.jpg",
}


# ---------------------------------------------------------------------------
# Cookie banner detection and cropping
# ---------------------------------------------------------------------------

def detect_cookie_banner_top(img_path):
    """
    Detect where a cookie banner starts in the bottom portion of an image.
    Returns the y-coordinate where cropping should happen, or None if no banner detected.

    Uses two strategies:
    1. Detect dark teal/navy bar (Springer/Nature "Your privacy, your choice")
    2. Detect brightness transitions (other cookie bars)
    """
    img = Image.open(img_path).convert("RGB")
    arr = np.array(img)
    h, w, _ = arr.shape

    # Strategy 1: Find dark teal/navy bar (Springer/Nature pattern)
    # These bars have: brightness < 80, B > R, G > R, sustained for 5+ rows
    for y in range(int(h * 0.40), h - 10):
        row_mean = arr[y, :, :].mean(axis=0)  # [R, G, B]
        brightness = row_mean.mean()
        r, g, b = row_mean
        if brightness < 80 and g > r and b > r:
            # Verify it's sustained (not a thin line)
            band = arr[y:y+5, :, :].mean(axis=1).mean(axis=1)  # brightness per row
            if all(v < 80 for v in band):
                return y  # Crop right at the teal bar

    # Strategy 2: Find a full-width brightness transition for bottom cookie bars
    # Look for the FIRST row where brightness drops significantly and stays low,
    # or where a distinct band appears
    start_y = int(h * 0.55)
    row_brightness = arr[:, :, :].mean(axis=(1, 2))

    # Look for transitions in the bottom 45%
    for y in range(start_y, h - 15):
        # Compare 5-row window above vs below
        above = row_brightness[max(0, y-5):y].mean()
        below = row_brightness[y:y+5].mean()
        diff = abs(above - below)

        if diff > 15:
            # Check that the region below is relatively uniform (banner-like)
            below_std = row_brightness[y:min(y+25, h)].std()
            if below_std < 20:
                return y

    # Strategy 3: Look for a dark bottom bar (small cookie bars)
    # Check if the bottom 15% has distinctly different brightness
    bottom_start = int(h * 0.85)
    top_region_br = row_brightness[int(h*0.5):int(h*0.7)].mean()
    bottom_region_br = row_brightness[bottom_start:].mean()
    if abs(top_region_br - bottom_region_br) > 20:
        # Find the exact transition
        for y in range(int(h * 0.70), h - 5):
            above = row_brightness[max(0, y-3):y].mean()
            below = row_brightness[y:y+3].mean()
            if abs(above - below) > 10:
                return y

    return None


def crop_cookie_banner(img_path, out_path=None):
    """Crop the cookie banner from the bottom of an image."""
    if out_path is None:
        out_path = img_path

    crop_y = detect_cookie_banner_top(str(img_path))
    if crop_y is None:
        return False, "No cookie banner detected"

    img = Image.open(img_path).convert("RGB")
    h, w = img.size[1], img.size[0]

    # Don't crop more than 65% of the image (keep at least 35%)
    if crop_y < h * 0.35:
        return False, f"Banner starts too high ({crop_y}/{h} = {crop_y/h:.0%})"

    # Don't "crop" if we're only removing < 3% (useless)
    if crop_y > h * 0.97:
        return False, f"Crop too small ({crop_y}/{h} = {crop_y/h:.0%})"

    # Crop
    cropped = img.crop((0, 0, w, crop_y))
    cropped.save(str(out_path), "JPEG", quality=JPEG_QUALITY)
    return True, f"Cropped at y={crop_y} ({crop_y/h:.0%} of {h}px)"


# ---------------------------------------------------------------------------
# Reference key lookup
# ---------------------------------------------------------------------------

def filename_to_ref_key(filename, refs):
    """Find the reference key that maps to this screenshot filename."""
    stem = Path(filename).stem
    # Direct match
    if stem in refs:
        return stem
    # Check screenshot field in references
    for key, ref in refs.items():
        ss = ref.get("screenshot", "")
        if ss and stem in ss:
            return key
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    dry_run = "--dry-run" in sys.argv

    refs = json.load(open(REFS_PATH))
    audit = json.load(open(AUDIT_PATH))

    to_remove = []       # (filename, reason, url)
    to_crop = []         # (filename, result_msg)
    kept_ok = []         # (filename, reason)

    removed_count = 0
    cropped_count = 0

    print("=" * 60)
    print("Screenshot Cleanup")
    print("=" * 60)

    for entry in audit["flagged"]:
        fname = entry["file"]
        category = entry["category"]
        fpath = SCREENSHOTS_DIR / fname

        if not fpath.exists():
            continue

        ref_key = filename_to_ref_key(fname, refs)
        url = refs[ref_key].get("url", "(no url)") if ref_key else "(unknown ref)"

        # --- BLOCKED ---
        if category == "blocked":
            to_remove.append((fname, "Blocked/Cloudflare page", url, ref_key))

        # --- UNUSABLE ---
        elif category == "unusable":
            to_remove.append((fname, "Unusable screenshot", url, ref_key))

        # --- REVIEW ---
        elif category == "review":
            if fname in REVIEW_BLOCKED:
                to_remove.append((fname, "JSTOR access block", url, ref_key))
            elif fname in REVIEW_OK or fname in FALSE_POSITIVES:
                kept_ok.append((fname, "Visually verified OK"))
            else:
                # Unknown review item — keep but note
                kept_ok.append((fname, f"Review item (not classified) — keeping"))

        # --- COOKIE POPUP ---
        elif category == "cookie_popup":
            if fname in FALSE_POSITIVES:
                kept_ok.append((fname, "False positive — no cookie popup"))
            elif fname in MODAL_UNUSABLE:
                to_remove.append((fname, "Modal overlay (cannot crop)", url, ref_key))
            else:
                # Try to crop
                to_crop.append((fname, ref_key, url))

    # --- Process removals ---
    print(f"\n--- REMOVING {len(to_remove)} screenshots ---")
    for fname, reason, url, ref_key in to_remove:
        fpath = SCREENSHOTS_DIR / fname
        print(f"  DEL {fname}")
        print(f"      Reason: {reason}")
        print(f"      URL: {url}")
        if not dry_run:
            if fpath.exists():
                os.unlink(fpath)
            if ref_key and ref_key in refs:
                refs[ref_key]["screenshot"] = None
        removed_count += 1

    # --- Process crops ---
    print(f"\n--- CROPPING {len(to_crop)} screenshots ---")
    for fname, ref_key, url in to_crop:
        fpath = SCREENSHOTS_DIR / fname
        if not dry_run:
            success, msg = crop_cookie_banner(fpath)
            status = "OK" if success else "SKIP"
            print(f"  {status} {fname}: {msg}")
            if success:
                cropped_count += 1
            else:
                # If cropping failed but it's a known cookie popup, note it
                print(f"      URL: {url}")
        else:
            print(f"  CROP {fname}")
            print(f"      URL: {url}")

    # --- Report kept items ---
    print(f"\n--- KEPT {len(kept_ok)} screenshots (OK) ---")
    for fname, reason in kept_ok:
        print(f"  OK  {fname}: {reason}")

    # --- Write manual audit MD ---
    print(f"\n--- Writing manual audit file ---")
    md_lines = [
        "# Screenshots Requiring Manual Capture",
        "",
        "These screenshots were automatically removed because they showed blocked pages,",
        "JSTOR access gates, modal overlays, or were otherwise unusable.",
        "",
        "To manually capture these, visit the URL in a browser, dismiss any cookie/login",
        "popups, and take a screenshot of the first page (800px wide for @2x retina).",
        "",
        f"**Total: {len(to_remove)} references**",
        "",
    ]

    # Group by reason
    by_reason = {}
    for fname, reason, url, ref_key in to_remove:
        by_reason.setdefault(reason, []).append((fname, url, ref_key))

    for reason, items in sorted(by_reason.items()):
        md_lines.append(f"## {reason} ({len(items)})")
        md_lines.append("")
        md_lines.append("| Key | URL |")
        md_lines.append("|-----|-----|")
        for fname, url, ref_key in items:
            key_display = ref_key or Path(fname).stem
            md_lines.append(f"| `{key_display}` | {url} |")
        md_lines.append("")

    # Also add the 3 refs that failed collection entirely
    md_lines.extend([
        "## Failed to collect (3)",
        "",
        "These references could not be reached at all during screenshot collection.",
        "",
        "| Key | URL | Reason |",
        "|-----|-----|--------|",
    ])
    # Find refs with no screenshot that aren't in the audit
    for key, ref in refs.items():
        if ref.get("screenshot") is None:
            url = ref.get("url", "")
            if url and not any(fname_to_stem(t[0]) == key for t in to_remove):
                fpath = SCREENSHOTS_DIR / f"{key}.jpg"
                if not fpath.exists():
                    md_lines.append(f"| `{key}` | {url} | Server unreachable |")

    md_lines.append("")

    if not dry_run:
        with open(MANUAL_AUDIT_PATH, "w") as f:
            f.write("\n".join(md_lines))
        print(f"  Written to {MANUAL_AUDIT_PATH}")

        # Save updated references.json
        with open(REFS_PATH, "w") as f:
            json.dump(refs, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"  Updated {REFS_PATH}")
    else:
        print("  (dry run — not writing)")

    # --- Summary ---
    print(f"\n{'=' * 60}")
    print(f"Summary:")
    print(f"  Removed:  {removed_count}")
    print(f"  Cropped:  {cropped_count}")
    print(f"  Kept OK:  {len(kept_ok)}")
    total_with = sum(1 for r in refs.values() if r.get("screenshot"))
    print(f"  Total with screenshots: {total_with} / {len(refs)}")


def fname_to_stem(fname):
    return Path(fname).stem


if __name__ == "__main__":
    main()

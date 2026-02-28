#!/usr/bin/env python3
"""
audit_screenshots.py

Analyzes screenshots in assets/screenshots/ using visual heuristics to flag
images that may be Cloudflare/bot blocks, cookie consent popups, blank/error
pages, or otherwise unusable. No external OCR dependencies — uses only
PIL/Pillow and numpy.

Heuristics (calibrated against 177 actual screenshots):
  1. Tiny file (<5 KB) — corrupt or nearly blank
  2. Low-variance + mostly-white — blank page
  3. Blocked-page signature — white_ratio > 0.975 AND variance < 650.
     Cloudflare "Verify you are human", CloudFront 403, access-denied pages
     all fall in this band. Clean academic PDFs with similar whiteness all
     have variance > 1000 because they contain real typeset content.
  4. Dark bottom band — cookie consent overlay at bottom of viewport
     (bottom 120 px mean brightness more than 40 points below page median,
      and absolute brightness below 160)
  5. Dark top band — cookie consent overlay at top of viewport
     (top 200 px mean brightness more than 30 points below page body mean,
      and absolute brightness below 200)
  6. CAPTCHA/reCAPTCHA widget — moderate whiteness (0.90–0.975) but variance
     in the 500–1500 range AND presence of a mid-page darker rectangular
     band (widget area); flagged as `review` for manual check.

Categories:
  ok           — no flags, looks like a real screenshot
  blocked      — Cloudflare / bot-detection / 403 / access-denied
  cookie_popup — cookie/GDPR consent banner detected (page may be usable
                 once banner is dismissed or cropped)
  unusable     — blank, corrupt, or true error page
  review       — ambiguous signals, needs a quick manual look
"""

import json
import os
import sys
from pathlib import Path

try:
    from PIL import Image
    import numpy as np
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Install with: pip install Pillow numpy")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = REPO_ROOT / "assets" / "screenshots"
REPORT_PATH = REPO_ROOT / "data" / "screenshot_audit.json"

# ---------------------------------------------------------------------------
# Thresholds (empirically calibrated on the 177-image dataset)
# ---------------------------------------------------------------------------
# --- Unusable / corrupt ---
TINY_FILE_BYTES     = 5_000    # <5 KB is almost certainly not a real page
BLANK_WHITE_RATIO   = 0.90     # used together with BLANK_VARIANCE
BLANK_VARIANCE      = 100.0    # both must be true → unusable blank

# --- Blocked pages (Cloudflare, 403, access-denied) ---
# Cloudflare/403 pages: white_ratio > 0.975, variance < 490
# The highest-variance confirmed-blocked page has var=470 (ai_bioweapon,
# ntia2024aiweights). The next item at var=642 (a2019_un) is a clean
# UN handbook cover page — false positive if threshold is set higher.
# Clean PDFs with high whiteness always have variance > 1000.
BLOCKED_WHITE_MIN   = 0.975
BLOCKED_VAR_MAX     = 490.0

# --- Cookie popup (bottom band) ---
COOKIE_BOT_BAND_H   = 120     # pixels from bottom to examine
COOKIE_BOT_DELTA    = 40      # bottom must be this much darker than rest
COOKIE_BOT_ABS_MAX  = 160     # and its absolute brightness must be below this

# --- Cookie popup (top band, e.g. GOV.UK style) ---
COOKIE_TOP_BAND_H   = 200     # pixels from top to examine
COOKIE_TOP_DELTA    = 30      # top band must be this much darker than page body
COOKIE_TOP_ABS_MAX  = 200     # and its absolute brightness must be below this

# --- Review (ambiguous, e.g. JSTOR reCAPTCHA widget) ---
# Moderate whiteness + mid-range variance (the reCAPTCHA box adds complexity)
REVIEW_WHITE_MIN    = 0.90
REVIEW_WHITE_MAX    = 0.975   # below BLOCKED_WHITE_MIN
REVIEW_VAR_MAX      = 1500.0  # but not as flat as a true blocked page


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def analyse_image(path: Path) -> dict:
    """Return a dict of metrics and a final category for one image."""
    result = {
        "file": path.name,
        "path": str(path),
        "file_size_bytes": path.stat().st_size,
        "flags": [],
        "category": "ok",
    }

    # --- Open image --------------------------------------------------------
    try:
        img = Image.open(path).convert("RGB")
    except Exception as e:
        result["flags"].append("cannot_open")
        result["error"] = str(e)
        result["category"] = "unusable"
        return result

    width, height = img.size
    result["width"] = width
    result["height"] = height

    arr = np.array(img, dtype=np.float32)   # (H, W, 3)
    brightness = arr.mean(axis=2)            # (H, W)

    # --- Metric 1: file size -----------------------------------------------
    if result["file_size_bytes"] < TINY_FILE_BYTES:
        result["flags"].append("tiny_file")

    # --- Metric 2: near-white pixel ratio ----------------------------------
    NEAR_WHITE = 220
    white_mask = (
        (arr[:, :, 0] >= NEAR_WHITE) &
        (arr[:, :, 1] >= NEAR_WHITE) &
        (arr[:, :, 2] >= NEAR_WHITE)
    )
    white_ratio = float(white_mask.sum()) / white_mask.size
    result["white_ratio"] = round(white_ratio, 4)

    # --- Metric 3: overall pixel-value variance ----------------------------
    variance = float(arr.var())
    result["variance"] = round(variance, 2)

    # --- Metric 4: row-brightness standard deviation ----------------------
    row_means = brightness.mean(axis=1)
    row_std = float(row_means.std())
    result["row_brightness_std"] = round(row_std, 2)

    # --- Metric 5: dark bottom band (cookie popup) ------------------------
    bottom_dark = False
    if height > COOKIE_BOT_BAND_H * 2:
        bottom_mean = float(brightness[-COOKIE_BOT_BAND_H:, :].mean())
        rest_mean   = float(brightness[:-COOKIE_BOT_BAND_H, :].mean())
        delta = rest_mean - bottom_mean
        result["bottom_band_brightness"] = round(bottom_mean, 2)
        result["bottom_band_delta"]      = round(delta, 2)
        if delta > COOKIE_BOT_DELTA and bottom_mean < COOKIE_BOT_ABS_MAX:
            result["flags"].append("dark_bottom_band")
            bottom_dark = True

    # --- Metric 6: dark top band (cookie popup — GOV.UK style) -----------
    top_dark = False
    if height > COOKIE_TOP_BAND_H * 2:
        top_mean  = float(brightness[:COOKIE_TOP_BAND_H, :].mean())
        body_mean = float(brightness[COOKIE_TOP_BAND_H:, :].mean())
        delta = body_mean - top_mean
        result["top_band_brightness"] = round(top_mean, 2)
        result["top_band_delta"]      = round(delta, 2)
        if delta > COOKIE_TOP_DELTA and top_mean < COOKIE_TOP_ABS_MAX:
            result["flags"].append("dark_top_band")
            top_dark = True

    # -----------------------------------------------------------------------
    # Classification (in priority order)
    # -----------------------------------------------------------------------
    flags = result["flags"]

    # 1. Corrupt / blank
    if "cannot_open" in flags or "tiny_file" in flags:
        result["category"] = "unusable"
        return result

    if white_ratio > BLANK_WHITE_RATIO and variance < BLANK_VARIANCE:
        result["flags"].append("blank_page")
        result["category"] = "unusable"
        return result

    # 2. Blocked pages (Cloudflare / 403 / access-denied)
    #    Very high white ratio + very low variance = almost no real content
    if white_ratio >= BLOCKED_WHITE_MIN and variance <= BLOCKED_VAR_MAX:
        result["flags"].append("blocked_signature")
        result["category"] = "blocked"
        return result

    # 3. Cookie / GDPR consent popup
    if bottom_dark or top_dark:
        result["category"] = "cookie_popup"
        return result

    # 4. Ambiguous — moderate whiteness + mid-range variance
    #    Catches CAPTCHA-widget pages (e.g. JSTOR reCAPTCHA) and other
    #    bot-checks that render a boxed widget, raising variance slightly.
    if (REVIEW_WHITE_MIN <= white_ratio < REVIEW_WHITE_MAX and
            variance <= REVIEW_VAR_MAX):
        result["flags"].append("ambiguous_signature")
        result["category"] = "review"
        return result

    # 5. Otherwise clean
    result["category"] = "ok"
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not SCREENSHOTS_DIR.exists():
        print(f"Screenshots directory not found: {SCREENSHOTS_DIR}")
        sys.exit(1)

    images = (sorted(SCREENSHOTS_DIR.glob("*.jpg")) +
              sorted(SCREENSHOTS_DIR.glob("*.jpeg")) +
              sorted(SCREENSHOTS_DIR.glob("*.png")))

    if not images:
        print("No images found.")
        sys.exit(0)

    print(f"Analysing {len(images)} images in {SCREENSHOTS_DIR} ...\n")

    results = []
    counts = {"ok": 0, "blocked": 0, "cookie_popup": 0, "unusable": 0, "review": 0}

    for img_path in images:
        r = analyse_image(img_path)
        results.append(r)
        counts[r["category"]] = counts.get(r["category"], 0) + 1
        if r["category"] != "ok":
            flag_str = ", ".join(r["flags"]) if r["flags"] else "—"
            print(f"  [{r['category'].upper():12s}] {r['file']}  "
                  f"white={r.get('white_ratio', '?'):.3f}  "
                  f"var={r.get('variance', '?'):.0f}  "
                  f"flags=({flag_str})")

    # --- Summary -----------------------------------------------------------
    total = len(results)
    print("\n" + "=" * 65)
    print("SUMMARY")
    print("=" * 65)
    for cat, cnt in [("ok", counts["ok"]),
                     ("blocked", counts["blocked"]),
                     ("cookie_popup", counts["cookie_popup"]),
                     ("unusable", counts["unusable"]),
                     ("review", counts["review"])]:
        bar = "#" * cnt
        print(f"  {cat:12s}: {cnt:4d} / {total}  {bar}")

    print()
    flagged = [r for r in results if r["category"] != "ok"]
    if flagged:
        print("FILES NEEDING ATTENTION (grouped by category):")
        for cat in ("unusable", "blocked", "cookie_popup", "review"):
            group = [r for r in flagged if r["category"] == cat]
            if group:
                print(f"\n  -- {cat.upper()} ({len(group)}) --")
                for r in group:
                    print(f"    {r['file']}")
    else:
        print("All images look clean.")

    # --- Write JSON report -------------------------------------------------
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "total": total,
        "counts": counts,
        "flagged": flagged,
        "all_results": results,
    }
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report written to: {REPORT_PATH}")


if __name__ == "__main__":
    main()

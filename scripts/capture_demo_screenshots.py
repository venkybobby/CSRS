"""Capture the demo screenshots from the frontend's fixture preview routes.

The screens this shoots are the ones a reviewer cannot otherwise see: they
need a live Agent Engine deployment, a seeded database, and (for the
date-of-service set) a member whose coverage happens to end inside the
quotable window. The preview routes render them from fixtures with no BFF
and no agent, so this script needs nothing but a vite dev server.

    npm --prefix frontend run dev
    python scripts/capture_demo_screenshots.py

Writes PNGs to docs/screenshots/. Re-run it after any change to the result
components -- the committed images are the record of what a CSR actually
sees, and a stale one is worse than none, because it reads as current.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "screenshots"

# Slugs match the data-capture attributes set by PreviewPane in
# frontend/src/components/PreviewPane.tsx. Selecting on those rather than on
# heading text keeps this script working across copy changes -- which are
# precisely the changes that send someone back here to re-shoot.
PAGES = [
    {
        "query": "?preview",
        "composite": "date-of-service-all.png",
        "panes": [
            ("dated-yes", "Future date inside the coverage period -- quote proceeds"),
            ("dated-no", "Date of service after coverage ends -- blocked"),
            ("plan-year-boundary", "Date of service in the next plan year -- hard stop"),
            ("past-date", "Past date of service -- routed to Claims"),
            ("prior-auth", "Prior authorization required -- Story 4 wording"),
        ],
    },
    {
        "query": "?preview=demo",
        "composite": "demo-script-all.png",
        "panes": [
            ("demo-1-partial-deductible", "Demo 1 -- partial deductible then coinsurance"),
            ("demo-2-oop-cap", "Demo 2 -- out-of-pocket cap binds"),
            ("demo-3a-family-individual-threshold", "Demo 3a -- family tier, individual threshold"),
            ("demo-3b-family-family-threshold", "Demo 3b -- family tier, family threshold"),
            ("demo-4-termed-block", "Demo 4 -- termed member, blocked"),
            ("demo-5-honest-miss", "Demo 5 -- no negotiated rate on file"),
        ],
    },
]

# Wide enough that the two-up rows lay out side by side rather than wrapping
# into a single tall column, which is how the pages are meant to be read.
# Kept as two ints rather than a dict constant so the literal can be built at
# the call site: playwright types `viewport` as a TypedDict, which a
# pre-built dict[str, int] does not satisfy.
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 900

# The fixtures render synchronously with no network calls, so there is
# nothing to await beyond the panes being in the DOM. Kept short on purpose:
# a long timeout here would turn "the preview route is broken" into a slow
# pass-looking hang instead of a fast, obvious failure.
SELECTOR_TIMEOUT_MS = 5_000


def capture(base_url: str, scale: int) -> int:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "playwright is not installed. Install it with:\n"
            "    pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        # device_scale_factor=2 by default: these get viewed zoomed in on a
        # slide or in a PR, where 1x text on a 1280px page turns to mush.
        page = browser.new_page(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            device_scale_factor=scale,
        )

        for spec in PAGES:
            url = f"{base_url.rstrip('/')}/{spec['query']}"
            try:
                page.goto(url, wait_until="networkidle")
            except PlaywrightError as exc:
                print(f"could not load {url}: {exc}", file=sys.stderr)
                print(
                    "is the dev server running? (npm --prefix frontend run dev)",
                    file=sys.stderr,
                )
                browser.close()
                return 1

            # Fail loudly if the route rendered the query form instead of the
            # fixtures -- e.g. if App.tsx's preview branch is ever changed.
            # Without this the script would happily write blank PNGs.
            try:
                page.wait_for_selector("[data-capture]", timeout=SELECTOR_TIMEOUT_MS)
            except PlaywrightError:
                print(
                    f"no [data-capture] panes found at {url} -- the preview route did not "
                    "render. Check App.tsx's preview branch and that the URL keeps its "
                    "query string.",
                    file=sys.stderr,
                )
                browser.close()
                return 1

            composite = OUTPUT_DIR / str(spec["composite"])
            page.screenshot(path=str(composite), full_page=True)
            print(f"  {composite.relative_to(REPO_ROOT).as_posix()}  -- full page")
            written += 1

            for slug, description in spec["panes"]:
                pane = page.query_selector(f"[data-capture='{slug}']")
                if pane is None:
                    print(
                        f"pane '{slug}' is missing from {url} -- add it back to the preview "
                        "page or drop it from PAGES here.",
                        file=sys.stderr,
                    )
                    browser.close()
                    return 1
                path = OUTPUT_DIR / f"{slug}.png"
                pane.screenshot(path=str(path))
                print(f"  {path.relative_to(REPO_ROOT).as_posix()}  -- {description}")
                written += 1

        browser.close()

    print(f"\nWrote {written} screenshots to {OUTPUT_DIR.relative_to(REPO_ROOT).as_posix()}/")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://localhost:5173",
        help="dev server origin, no path (default: %(default)s)",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=2,
        help="device scale factor; 2 keeps text sharp when zoomed (default: %(default)s)",
    )
    args = parser.parse_args()
    return capture(args.base_url, args.scale)


if __name__ == "__main__":
    raise SystemExit(main())

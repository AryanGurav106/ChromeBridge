"""Replay ONE frozen site and dump everything needed to JUDGE the listing.

Written so a reviewer (human or agent) does not have to invent a measurement. The
mechanical half is here and identical for every site; the reviewer's job is the part
no metric does — reading the listing beside the screenshot and asking whether an
agent could act on this page.

Emits, for one site:
  - the LISTING the agent would actually receive (tree, compact) — the surface under review
  - counts: controls the DOM renders vs entries collected vs rows printed
  - the ledger's drop-reason histogram, and whether every reason is in the permitted set
  - LOST IDENTITIES: rendered, genuinely-visible, not-declared-hidden controls whose
    name appears nowhere in either the listing or the structured array
  - UNRECORDED DROPS: collected-then-absent elements with no ledger reason
  - a screenshot, so the reviewer can compare the listing against the pixels

THE VISIBILITY TEST IS THE WHOLE MEASUREMENT, so it is spelled out: a bare
`checkVisibility()` does NOT check `visibility:hidden` or opacity. A probe using the
bare call reported 3.81% identity loss across 12 sites; with the options passed, the
same probe reports 0.00%. Every element it had "found" was one the collector had
correctly dropped as not-visible. Do not simplify this call.

Run:  python tools/inspect_site.py <site_name> [--out DIR]
      python tools/inspect_site.py --list
"""

import argparse
import asyncio
import collections
import json
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from _extract import extract as _extract_fn  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = _extract_fn("_collectInteractivePage", BG, verify=True)
FROZEN = ROOT / "temp" / "frozen"
TAG_JS = str(ROOT / "extension" / "listener_tag.js")
VIEWPORT = {"width": 1280, "height": 1600}

# THE PERMITTED SET IS READ FROM test_ledger.py, NOT RESTATED HERE.
#
# My first version restated it and immediately drifted: it omitted `outside-viewport`,
# which test_ledger's L10c has always permitted, so this tool reported a legitimate
# rule as "a rule started deleting again" on the first site where an off-viewport
# control failed keepForFind. That is #21's "one concept spelled two ways" — and the
# concept already had THREE spellings (L10c's set, this set, and CLAUDE.md's prose),
# which is two too many for something whose whole job is to be authoritative.
# L10c is the tripwire the project treats as the contract, so it is the source.
def _permitted_deletes():
    src = (ROOT / "tools" / "test_ledger.py").read_text(encoding="utf-8")
    body = src[src.index("SPEC_DELETES = {"):]
    body = body[:body.index("}")]
    names = set(re.findall(r'"([a-z][a-z0-9-]+)"', body))
    if not names:
        raise SystemExit("could not read SPEC_DELETES from test_ledger.py — did it move?")
    return names


PERMITTED = _permitted_deletes()

PROBE = r"""
(function (LISTING, BLOB) {
  const out = { candidates: 0, lost: [], unrecorded: [] };
  for (const el of document.querySelectorAll('a[href],button,input,select,textarea,summary')) {
    let r; try { r = el.getBoundingClientRect(); } catch (e) { continue; }
    if (r.width < 2 || r.height < 2) continue;
    // SEE THE MODULE DOCSTRING. The bare call ignores visibility:hidden and opacity.
    let vis = true;
    try {
      vis = el.checkVisibility
        ? el.checkVisibility({ visibilityProperty: true, opacityProperty: true,
                               contentVisibilityAuto: true })
        : true;
    } catch (e) {}
    if (!vis) continue;
    if (el.closest('[aria-hidden="true"]') || el.closest('[inert]')) continue;
    out.candidates++;
    const nm = ((el.getAttribute('aria-label') || el.getAttribute('title')
      || (el.innerText || '').trim() || el.getAttribute('placeholder')
      || el.getAttribute('value') || '') + '').replace(/\s+/g, ' ').trim();
    const m = el.getAttribute('mmid');
    const byRef = m && BLOB.indexOf('"' + m + '"') >= 0;
    if (byRef) continue;
    if (nm && (BLOB.indexOf(nm) >= 0 || LISTING.indexOf(nm) >= 0)) continue;
    if (!nm) continue;   // no identity to lose
    const rc = r;
    out.lost.push({
      tag: el.tagName.toLowerCase(), name: nm.slice(0, 60), mmid: m,
      box: [Math.round(rc.width), Math.round(rc.height)],
      offscreen: (rc.bottom < 0 || rc.top > innerHeight || rc.right < 0 || rc.left > innerWidth),
    });
  }
  return out;
})
"""


async def inspect(site, url, out_dir):
    har = FROZEN / f"{site}.har"
    if not har.exists():
        return {"site": site, "error": f"no recording at {har}"}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport=VIEWPORT)
        try:
            await ctx.add_init_script(path=TAG_JS)
            await ctx.route_from_har(str(har), not_found="abort")
            page = await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                await page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass
            await page.wait_for_timeout(1800)

            # ONE evaluate: a still-rendering page must not grow a control between the
            # collector and the probe and have it counted as a loss.
            res = await page.evaluate(
                "(function(){ " + COLLECT + ";"
                " const listing = _collectInteractivePage(false);"
                " const ents = _collectInteractivePage(true);"
                " const led = _collectInteractivePage(true, null, 'compact', true);"
                " const blob = JSON.stringify(ents);"
                " const probe = (" + PROBE.strip() + ")(String(listing), blob);"
                " return {listing: String(listing), ents: ents, dropped: (led && led.dropped) || [],"
                "         probe: probe}; })()")

            shot = Path(out_dir) / f"{site}.png"
            try:
                await page.screenshot(path=str(shot), full_page=False)
            except Exception:
                shot = None

            listing = res["listing"]
            ents = res["ents"] or []
            drops = res["dropped"] or []
            listed_refs = set(re.findall(r"ref_(\S+?)[\s|]", listing)) | set(
                re.findall(r"(?:^|\s)(\d+):\"", listing))
            reasons = collections.Counter(
                (d.get("rule") or d.get("why") or "?") for d in drops)
            unknown = {k: v for k, v in reasons.items() if k not in PERMITTED}

            # An element collected but neither printed nor recorded as dropped.
            # A FOLD MEMBER IS PRINTED. `22:"redblobgames.com"` is a ref on a folded
            # row, and a ref regex that misses that shape reports every folded member as
            # unaccounted-for — 8 false positives on the first site tried. An entry
            # counts as printed if its ref appears OR its identity does.
            recorded = {str(d.get("mmid")) for d in drops}
            unrecorded = [e for e in ents
                          if str(e.get("mmid")) not in listed_refs
                          and str(e.get("mmid")) not in recorded
                          and not ((e.get("name") or e.get("label") or e.get("text") or "")
                                   and (e.get("name") or e.get("label") or e.get("text")) in listing)][:8]

            return {
                "site": site, "url": url,
                "listing_chars": len(listing),
                "entries": len(ents),
                "rows_printed": len(listed_refs),
                "dom_controls_rendered": res["probe"]["candidates"],
                "lost_identities": res["probe"]["lost"],
                "drop_reasons": dict(reasons.most_common()),
                "UNEXPECTED_drop_reasons": unknown,
                # THE TRUE COUNT, not the sample size. The list is capped at 8 for
                # readability and a reviewer read "8" as the finding when the real
                # number was 352 — a capped number presented as a total, which is the
                # same defect this tool just found in the product.
                "collected_but_neither_printed_nor_recorded_TOTAL": len([
                    e for e in ents
                    if str(e.get("mmid")) not in listed_refs
                    and str(e.get("mmid")) not in recorded
                    and not ((e.get("name") or e.get("label") or e.get("text") or "")
                             and (e.get("name") or e.get("label") or e.get("text")) in listing)]),
                "collected_but_neither_printed_nor_recorded_sample": [
                    {"mmid": e.get("mmid"), "tag": e.get("tag"),
                     "name": (e.get("name") or e.get("label") or e.get("text") or "")[:50]}
                    for e in unrecorded],
                "screenshot": str(shot) if shot else None,
                "listing": listing,
            }
        except Exception as e:
            return {"site": site, "error": str(e)[:200]}
        finally:
            await ctx.close()
            await browser.close()


def sites():
    src = (ROOT / "tools" / "capture_listings.py").read_text(encoding="utf-8")
    body = src[src.index("SITES = ["):src.index("\nOUT = ")]
    return dict(re.findall(r'\(\s*"([a-z_0-9]+)"\s*,\s*"(https?://[^"]+)"', body))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site", nargs="?")
    ap.add_argument("--out", default=str(ROOT / "temp" / "inspect"))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--no-listing", action="store_true",
                    help="omit the full listing from the JSON (counts and findings only)")
    args = ap.parse_args()
    S = sites()
    if args.list or not args.site:
        have = sorted(n for n in S if (FROZEN / f"{n}.har").exists())
        print(f"{len(have)} site(s) with a recording:")
        print("  " + " ".join(have))
        return 0
    if args.site not in S:
        print(f"unknown site {args.site!r}; use --list")
        return 1
    Path(args.out).mkdir(parents=True, exist_ok=True)
    r = asyncio.run(inspect(args.site, S[args.site], args.out))
    if args.no_listing:
        r.pop("listing", None)
    path = Path(args.out) / f"{args.site}.json"
    path.write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in r.items() if k != "listing"}, indent=1, ensure_ascii=False))
    print(f"\nfull record (incl. the listing): {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Freeze the 106-site corpus so measurements become deterministic.

WHY THIS EXISTS
---------------
Every audit in this project has run against LIVE pages, and that has distorted
results twice at real cost:

  - the ablation study had to invent per-variant `base -> ablated -> base` drift
    controls, because a change in totals could not otherwise be attributed to
    the code change rather than to the site changing underneath it;
  - a "two reads of the same page are identical" invariant is unusable live:
    measured drift on this corpus is 345 entries / 4,635 chars between two runs
    of the SAME source.

Freeze the corpus and a regression is a regression, not weather. It also halves
every ablation run by deleting the drift-control pass.

MECHANISM: HAR record/replay, NOT MHTML
---------------------------------------
The obvious choice is MHTML (`Page.captureSnapshot`), and it was tried first.
It is unusable here, for a reason worth recording so nobody re-attempts it:

  - Chromium will not render MHTML from `file://` under Playwright (the document
    loads empty: 3 nodes, 0 anchors), and serving it as `multipart/related` over
    HTTP is refused with ERR_ABORTED.
  - Even when it renders, Chrome does NOT execute JavaScript in MHTML. That
    silently deletes `listener_tag.js`'s handler tagging (so bare handler-bound
    divs vanish) and everything a framework renders after load. Measured on the
    first 5 sites: 0% element retention.

HAR replay has none of those problems. Requests are served from the recording
and JS runs normally, so the collector sees the same page it sees live.
Measured on Hacker News: 231 elements live, 231 on replay, identical across two
consecutive replays. `not_found="abort"` guarantees nothing leaks to the network,
so replay is hermetic.

WHAT IS STILL NOT DETERMINISTIC
-------------------------------
JS executes, so anything time- or random-dependent still moves: clocks,
carousels, `Math.random()` ids, animations mid-flight. Expect a small residue
rather than zero. `--verify` reports per-site replay-vs-replay stability so the
residue is measured instead of assumed — do not claim an invariant holds on a
site this flags as unstable.

Run:
    python tools/freeze_corpus.py                  # record all 106
    python tools/freeze_corpus.py --limit 5        # smoke test
    python tools/freeze_corpus.py --verify         # replay twice, report stability
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "temp" / "frozen"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = extract("_collectInteractivePage", BG, verify=True)
TAG_JS = str(ROOT / "extension" / "listener_tag.js")
VIEWPORT = {"width": 1280, "height": 1600}


def load_sites() -> list[tuple[str, str]]:
    """Single source of truth for the corpus — capture_listings.py's SITES."""
    src = (ROOT / "tools" / "capture_listings.py").read_text(encoding="utf-8")
    body = src[src.index("SITES = ["):src.index("\nOUT = ")]
    return re.findall(r'\(\s*"([a-z_0-9]+)"\s*,\s*"(https?://[^"]+)"', body)


def har_path(name: str) -> Path:
    return FROZEN / f"{name}.har"


async def _collect(page) -> list:
    try:
        return await page.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
    except Exception:
        return []


async def _settle(page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    await page.wait_for_timeout(1200)


async def record(browser, name: str, url: str) -> dict:
    rec: dict = {"name": name, "url": url}
    ctx = await browser.new_context(viewport=VIEWPORT, record_har_path=str(har_path(name)),
                                    record_har_mode="full")
    try:
        await ctx.add_init_script(path=TAG_JS)
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await _settle(page)
        rec["live_elements"] = len(await _collect(page))
        rec["ok"] = True
    except Exception as e:
        rec["ok"] = False
        rec["error"] = str(e)[:160]
    finally:
        await ctx.close()          # closing flushes the HAR to disk
    if rec.get("ok") and har_path(name).exists():
        rec["har_kb"] = har_path(name).stat().st_size // 1024
    return rec


async def replay(browser, name: str, url: str) -> list:
    """Load the site purely from its recording. Hermetic: nothing hits the network."""
    ctx = await browser.new_context(viewport=VIEWPORT)
    try:
        await ctx.add_init_script(path=TAG_JS)
        await ctx.route_from_har(str(har_path(name)), not_found="abort")
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await _settle(page)
        return await _collect(page)
    except Exception:
        return []
    finally:
        await ctx.close()


def _ident(e: dict) -> tuple:
    """Identity that ignores the additive mmid counter.

    mmids are assigned per pass, so comparing on them turns one re-render into
    hundreds of phantom add/remove pairs — a trap the ablation audit already hit
    and had to solve the same way.
    """
    return (e.get("tag"), e.get("role"), e.get("name"), e.get("label"),
            e.get("value"), e.get("x"), e.get("y"), e.get("w"), e.get("h"))


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="")
    ap.add_argument("--verify", action="store_true",
                    help="replay each site twice and report replay-vs-replay stability")
    ap.add_argument("--skip-record", action="store_true",
                    help="verify existing recordings without re-recording")
    args = ap.parse_args()

    sites = load_sites()
    if args.only:
        want = {s.strip() for s in args.only.split(",")}
        sites = [s for s in sites if s[0] in want]
    if args.limit:
        sites = sites[: args.limit]

    FROZEN.mkdir(parents=True, exist_ok=True)
    print(f"{'verifying' if args.skip_record else 'recording'} {len(sites)} site(s) -> {FROZEN}")
    t0 = time.time()
    results: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for i, (name, url) in enumerate(sites, 1):
            if args.skip_record:
                rec = {"name": name, "url": url, "ok": har_path(name).exists()}
                if not rec["ok"]:
                    rec["error"] = "no recording"
            else:
                rec = await record(browser, name, url)

            if rec.get("ok"):
                a = await replay(browser, name, url)
                rec["replay_elements"] = len(a)
                live = rec.get("live_elements") or 0
                if live:
                    rec["retention_pct"] = round(100.0 * len(a) / live, 1)
                if args.verify:
                    b = await replay(browser, name, url)
                    sa, sb = [_ident(e) for e in a], [_ident(e) for e in b]
                    ca, cb = set(sa), set(sb)
                    rec["stable"] = sa == sb
                    rec["drift_entries"] = len(ca ^ cb)

            results.append(rec)
            bits = []
            if rec.get("live_elements") is not None:
                bits.append(f"live={rec['live_elements']}")
            if rec.get("replay_elements") is not None:
                bits.append(f"replay={rec['replay_elements']}")
            if rec.get("retention_pct") is not None:
                bits.append(f"({rec['retention_pct']}%)")
            if args.verify and "stable" in rec:
                bits.append("stable" if rec["stable"] else f"DRIFT {rec['drift_entries']}")
            print(f"  [{i:>3}/{len(sites)}] {'ok ' if rec.get('ok') else 'FAIL'} {name:<24}"
                  + "  ".join(bits) + ("  " + rec.get("error", "") if not rec.get("ok") else ""))
        await browser.close()

    ok = [r for r in results if r.get("ok")]
    usable = [r for r in ok if (r.get("replay_elements") or 0) > 0]
    (FROZEN / "index.json").write_text(
        json.dumps({"sites": results, "seconds": round(time.time() - t0, 1)}, indent=2),
        encoding="utf-8")

    print(f"\n{len(ok)}/{len(results)} recorded, {len(usable)} replay with a non-empty listing "
          f"({round(time.time() - t0)}s)")
    rets = sorted(r["retention_pct"] for r in results if r.get("retention_pct") is not None)
    if rets:
        print(f"replay/live element retention: median {rets[len(rets)//2]}%  "
              f"min {rets[0]}%  max {rets[-1]}%")
    if args.verify:
        st = [r for r in results if "stable" in r]
        unstable = [r for r in st if not r["stable"]]
        print(f"replay-vs-replay: {len(st) - len(unstable)}/{len(st)} byte-stable")
        if unstable:
            print("  UNSTABLE (do not assert exact-match invariants on these): "
                  + ", ".join(f"{r['name']}({r['drift_entries']})" for r in unstable[:12]))
    return 0 if usable else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

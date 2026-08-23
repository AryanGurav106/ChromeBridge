"""Unit suite for the page-readiness probe.

WHY: four of six live agents on real sites hit the same root cause — nothing in
the tool surface could say "this page is still changing", so every observation
was reported with the same confidence whether the page was settled or mid-load:

  - BBC      every x-coordinate in a listing was 116px stale, because the hero
             image had not loaded and the layout was about to reflow. A
             coordinate click built from it would have missed, silently.
  - BBC      a lazy-load placeholder was listed as a real element and was gone
             seconds later — a phantom ref, plus a false (occluded/blocked) on
             the element it overlapped.
  - Baidu    get_page_text answered over results still rendering behind a spinner.
  - Wolfram  a result pod streamed in AFTER the read, so it simply did not exist
             in the listing, with nothing hinting that more was coming.

The probe is deliberately structural: aria-busy and role=progressbar are the
ARIA-standard "updating" signals, so there is no spinner-class list to maintain.
Images count only when they occupy real space, since those are the ones whose
load REFLOWS the page and invalidates the coordinates being printed.

Run:  python tools/test_readiness.py
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract as _shared_extract  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
# The probe calls _deepAll (the shadow-aware query). In the extension both live in
# one scope; extracted alone the reference throws, every try/catch swallows it, and
# the probe reports a settled page — invisibly. Same swallowed-ReferenceError shape
# as the vh/vw bug that R8 exists for; caught by the suite this time.
READY = (_shared_extract("_deepAll", BG, verify=True) + ";\n"
         + _shared_extract("_topRectFor", BG, verify=True) + ";\n"
         + _shared_extract("_readinessPage", BG, verify=True))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))


SETTLED = """<!doctype html><meta charset=utf-8><title>settled</title>
<body><h1>All done</h1><p>Nothing is loading here.</p>
<button style="width:80px;height:24px">OK</button></body>"""

BUSY = """<!doctype html><meta charset=utf-8><title>busy</title>
<body><h1>Loading</h1>
<div aria-busy="true" style="width:300px;height:60px">results appear here</div>
<div role="progressbar" aria-valuenow="40" style="width:200px;height:12px"></div>
<!-- a 1px hidden progressbar must NOT count: sites leave those in the DOM -->
<div role="progressbar" style="width:1px;height:1px"></div>
<div role="progressbar" style="width:200px;height:12px;display:none"></div>
</body>"""


async def probe(page):
    return await page.evaluate("(function(){ " + READY + "; return _readinessPage(); })()")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 900, "height": 700})

        await page.set_content(SETTLED)
        await page.wait_for_timeout(120)
        r = await probe(page)
        check("R1 a settled page reports nothing to wait for",
              r["ready"] == "complete" and r["imgs"] == 0 and r["busy"] == 0 and r["prog"] == 0,
              str(r))

        await page.set_content(BUSY)
        await page.wait_for_timeout(120)
        r = await probe(page)
        check("R2 aria-busy regions are counted", r["busy"] == 1, str(r))
        check("R3 a visible progressbar is counted", r["prog"] == 1,
              f"prog={r['prog']} (expected exactly 1 — a 1px one and a display:none "
              f"one are also present and must not count)")

        # An image whose request is genuinely IN FLIGHT while we probe. Note a
        # FAILED image reports complete === true, so aborting immediately would
        # test nothing — the handler has to keep the request pending, and it must
        # await (not block) so the probe below still runs.
        async def _slow(route):
            await asyncio.sleep(3)
            try:
                await route.abort()
            except Exception:
                pass

        await page.route("**/slow.png", _slow)
        # A REAL origin is required. set_content leaves the base URL at about:blank,
        # so "/slow.png" never becomes a routable request and the image resolves
        # instantly as broken — and a broken image reports complete === true, which
        # made this read 0 and look like a collector bug rather than a harness bug.
        # domcontentloaded (not the default "load") so we probe while it is pending.
        await page.route("**/readiness-fixture", lambda r: r.fulfill(
            status=200, content_type="text/html",
            body='<!doctype html><meta charset=utf-8><body>'
                 '<img src="/slow.png" style="width:300px;height:200px">'
                 '<img src="/tiny.png" style="width:4px;height:4px"></body>'))
        await page.goto("http://readiness.test/readiness-fixture",
                        wait_until="domcontentloaded")
        await page.wait_for_timeout(250)
        r = await probe(page)
        check("R4 a large unloaded image counts (its load will reflow the page)",
              r["imgs"] >= 1, str(r))
        check("R5 ...and a sub-8px one does not (it cannot move anything)",
              r["imgs"] == 1, f"imgs={r['imgs']} (expected 1: the 300x200, not the 4x4)")

        # R6: THE FALSE-POSITIVE CASE, found live. A lazy image far below the fold
        # has complete === false indefinitely — it has not begun loading and will
        # not until scrolled to. Counting those pinned BBC at "14 images still
        # loading" on a fully settled page, every read, forever. A warning that is
        # always on is worse than no warning, so this is the check that decides
        # whether the signal is usable at all.
        await page.route("**/deep-fixture", lambda r: r.fulfill(
            status=200, content_type="text/html",
            body='<!doctype html><meta charset=utf-8><body>'
                 '<div style="height:4000px">tall</div>'
                 '<img loading="lazy" src="/slow.png" style="width:300px;height:200px">'
                 '</body>'))
        await page.goto("http://readiness.test/deep-fixture", wait_until="domcontentloaded")
        await page.wait_for_timeout(250)
        r = await probe(page)
        check("R6 a lazy image far below the fold does NOT keep the page 'loading'",
              r["imgs"] == 0,
              f"imgs={r['imgs']} — an unloaded below-fold image would make the banner permanent")

        # R7/R8: the two ways a progressbar pinned the banner ON permanently.
        # Both found by live agents on real sites, both the same shape as R6 —
        # an indicator that can never turn off makes the warning worthless, and
        # worse, indistinguishable from the one time it was right.
        pg = await browser.new_page(viewport={"width": 1200, "height": 800})
        await pg.set_content(
            "<!DOCTYPE html><meta charset=utf-8><body style='margin:0'>"
            # Google Flights: Material bars idle at opacity:0 and stay in the DOM.
            # checkVisibility() ignores opacity unless asked, so these counted forever.
            "<div role=progressbar style='opacity:0;width:300px;height:4px'>Loading results</div>"
            # IKEA: a parked <progress> outside the viewport, and one far below the fold.
            "<progress style='position:absolute;left:1960px;top:84px;width:340px;height:5px'></progress>"
            "<progress style='position:absolute;left:0;top:6549px;width:340px;height:5px'></progress>"
            "</body>")
        await pg.wait_for_timeout(120)
        r = await pg.evaluate("(function(){ " + READY + "; return _readinessPage(); })()")
        check("R7 an opacity:0 / off-viewport progressbar does NOT pin the banner on",
              r["prog"] == 0, f"prog={r['prog']} — a stuck banner trains the reader to ignore it")

        # ...and the signal must still FIRE. A fix that silently zeroes the probe
        # looks identical to a settled page — which is exactly what my first
        # version of the viewport bound did (ReferenceError swallowed by a catch).
        await pg.set_content(
            "<!DOCTYPE html><meta charset=utf-8><body style='margin:0'>"
            "<div role=progressbar style='width:300px;height:6px;background:#ccc'>Loading</div>"
            "</body>")
        await pg.wait_for_timeout(120)
        r = await pg.evaluate("(function(){ " + READY + "; return _readinessPage(); })()")
        check("R8 ...while a real in-viewport progressbar is still counted",
              r["prog"] == 1, f"prog={r['prog']} — the negative control for R7")
        await pg.close()

        # R9/R10: the probe was FRAME-BLIND. `querySelectorAll` stops at a frame
        # boundary exactly as it stops at a shadow boundary, and _deepAll crossed
        # only the second — so a page whose content lives in a same-origin frame
        # (the classic app shell, and every embedded checkout) reported "settled"
        # while the frame was still spinning. Fourth home for this class after #25.
        fp = await browser.new_page(viewport={"width": 1200, "height": 800})
        await fp.set_content(
            "<!DOCTYPE html><meta charset=utf-8><body style='margin:0'>"
            "<iframe style='width:600px;height:300px;border:0' srcdoc=\""
            "&lt;div role=progressbar style='width:200px;height:6px;background:#ccc'&gt;Loading&lt;/div&gt;"
            "&lt;div aria-busy='true' style='width:200px;height:40px'&gt;results&lt;/div&gt;\"></iframe>"
            "</body>")
        await fp.wait_for_timeout(200)
        r = await fp.evaluate("(function(){ " + READY + "; return _readinessPage(); })()")
        check("R9 a progressbar and an aria-busy region inside a same-origin FRAME"
              " are seen by the probe",
              r["prog"] == 1 and r["busy"] == 1,
              f"prog={r['prog']} busy={r['busy']} — 0/0 was 'settled' on a spinning page")

        # THE COORDINATE CONTROL, and the reason _topRectFor exists. An in-frame
        # rect is relative to the FRAME's viewport, so a spinner at frame-y=20
        # inside a frame parked 4000px down looks in-viewport to a naive filter
        # and pins the banner on forever — R7's failure, reintroduced by the very
        # fix for R9. This check fails if the rect is not mapped to the top document.
        await fp.set_content(
            "<!DOCTYPE html><meta charset=utf-8><body style='margin:0'>"
            "<div style='height:4000px'></div>"
            "<iframe style='width:600px;height:300px;border:0' srcdoc=\""
            "&lt;div role=progressbar style='width:200px;height:6px;background:#ccc'&gt;Loading&lt;/div&gt;\">"
            "</iframe></body>")
        await fp.wait_for_timeout(200)
        r = await fp.evaluate("(function(){ " + READY + "; return _readinessPage(); })()")
        check("R10 ...but one in a frame parked far below the fold does NOT count"
              " (in-frame rects are frame-relative — the R7 failure, reintroduced"
              " by R9's own fix unless mapped)",
              r["prog"] == 0, f"prog={r['prog']}")
        await fp.close()

        await browser.close()

    passed = sum(1 for x in results if x)
    print(f"\n{passed}/{len(results)} readiness checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

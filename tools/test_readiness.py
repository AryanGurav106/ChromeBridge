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
# INJECT _readinessPage ALONE, BECAUSE THAT IS THE PRODUCTION CONTRACT.
# `runInTab` passes it to chrome.scripting.executeScript({func}), which stringifies
# ONLY that function — a call to a top-level sibling is a free identifier that does
# not exist in the page.
#
# This file used to PREPEND `_deepAll` and `_topRectFor` before injecting, which
# built an environment production never has. The suite then reported 10/10 while
# the three DOM signals (images-loading, aria-busy, progressbar) were dead in the
# shipped extension: every helper call threw ReferenceError, each swallowed by its
# own try/catch, leaving imgs/busy/prog at 0 and emitting no banner on a page that
# plainly held an aria-busy region and a visible progressbar.
#
# The helpers are now inner closures of _readinessPage. Extracting them here would
# hide a regression of exactly the kind this suite exists to catch, so do not add
# them back — if the extraction fails, the function has grown a dependency it
# cannot have.
READY = _shared_extract("_readinessPage", BG, verify=True)

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


async def probe_scoped(page, mmid):
    """The same injection, with the scope the caller named.

    PASSED AS AN ARGUMENT, exactly as runInTab does -- `executeScript({func, args})`.
    Resolution happens INSIDE the injected function (registry first, selector as
    fallback), so this helper must not resolve anything itself or it would test an
    environment production does not have, which is the C14/#29 trap.
    """
    return await page.evaluate(
        "(m) => { " + READY + "; return _readinessPage(m); }", mmid)


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

        # ------------------------------------------------------------------
        # R11-R16  DOM MUTATION RECENCY
        #
        # The four signals above all measure whether something is ARRIVING. The
        # question an agent actually asks is "if I wait, will what I am reading
        # change?", and those come apart in BOTH directions on an SPA:
        #
        #   still building, network silent -> every signal above reads 0
        #   painted and done, network chatty -> every signal above fires, for ever
        #
        # Both were reproduced in scratchpad/probe_false_negative.py before any
        # of this was built. See docs/READINESS.md for the table.
        #
        # NOTE THE HARNESS SHAPE. add_init_script only affects documents created
        # AFTER it, and set_content reuses the existing about:blank — so the
        # add_init_script + set_content pairing runs the tagger on NOTHING and
        # tests an untagged page while staying green. That is the defect C14 in
        # test_contracts.py exists to catch (it found 25 such pages across 5
        # suites). Every check below therefore goto()s a routed URL.
        TAG = (ROOT / "extension" / "listener_tag.js").read_text(encoding="utf-8")

        async def tagged_page(body, **kw):
            pg = await browser.new_page(viewport={"width": 900, "height": 700})
            await pg.add_init_script(TAG)
            await pg.route("**/mut-fixture", lambda r: r.fulfill(
                status=200, content_type="text/html", body=body))
            await pg.goto("http://mut.test/mut-fixture", wait_until="domcontentloaded")
            return pg

        async def mut(pg, win=1000):
            return await pg.evaluate(
                "(w) => window.__abMut ? window.__abMut.query(null, w) : null", win)

        # R11 a page mid-paint: network silent, readyState complete, and yet it
        # is plainly still being built. This is the case where EVERY signal above
        # reads zero, so it is the one that most needed a signal.
        pg = await tagged_page(
            "<!doctype html><meta charset=utf-8><body><div id=h></div><script>"
            "let i=0;(function s(){for(let k=0;k<4&&i<400;k++,i++){"
            "const d=document.createElement('div');d.textContent='row '+i;"
            "document.getElementById('h').appendChild(d);}"
            "if(i<400)setTimeout(s,18);})();</script></body>")
        await pg.wait_for_timeout(400)
        m = await mut(pg)
        r = await probe(pg)
        check("R11 a page still painting is reported as CHANGING, where every "
              "other signal reads zero",
              m is not None and m["structural"] > 0 and 0 <= m["since"] < 200
              and r["imgs"] == 0 and r["busy"] == 0 and r["prog"] == 0,
              f"mut={m} others={{imgs:{r['imgs']},busy:{r['busy']},prog:{r['prog']}}}")
        check("R12 ...and the probe carries it, so the note can use it "
              "(the injection boundary is where this probe died once already)",
              r.get("mut") is not None and r["mut"]["structural"] > 0,
              f"r.mut={r.get('mut')}")

        # R13 THE CONTROL. Without it "always report changing" would pass R11
        # and the signal would mean nothing. Same page, after it has finished.
        # NOTE the wait must now clear the 3000ms observation window, not the
        # old 1000ms one — see the MUT_WIN note in background.js for why it was
        # widened (a 1000ms window is 50.7% false-quiet when a throttled tab
        # commits every 2s, and a false quiet is the direction that makes an
        # agent conclude absence).
        # The fixture paints 400 rows at 4 per frame / 18ms, so it finishes
        # around 1.8s; sampling at 2.9s left the tail inside the 1s window and
        # flaked. Wait clear of it rather than polling for quiet, which would be
        # asserting exactly what we waited for.
        await pg.wait_for_timeout(5200)
        m = await mut(pg)
        check("R13 CONTROL: the same page, once finished, reports quiet",
              m is not None and m["structural"] == 0 and m["text"] == 0
              and m["since"] > 500,
              f"mut={m}")
        await pg.close()

        # R14 OUR OWN WRITES ARE NOT THE PAGE CHANGING. The collector stamps a
        # real `mmid` ATTRIBUTE on every interactive element, so without this
        # exclusion an observation reports ITSELF as churn — worst on the first
        # read of a page, one record per control.
        pg = await tagged_page("<!doctype html><meta charset=utf-8><body>"
                               + "<button>b</button>" * 50 + "</body>")
        await pg.wait_for_timeout(300)
        # BEFORE/AFTER, not an absolute zero. The fixture's own 50 buttons are
        # parse-time childList records and are legitimately counted — asserting
        # structural == 0 measured the harness, not the exclusion. The claim is
        # that stamping 50 mmids adds NOTHING, which only a delta can say.
        before = await mut(pg)
        await pg.evaluate("document.querySelectorAll('button')"
                          ".forEach((b,i)=>b.setAttribute('mmid',String(i)))")
        m = await mut(pg)
        check("R14 the collector's own mmid stamping is not counted as page churn",
              m is not None and before is not None
              and not m["attrs"].get("mmid")
              and m["total"] == before["total"],
              f"total {before and before['total']} -> {m and m['total']}, "
              f"attrs={m and m['attrs']}")
        # R15 CONTROL: a real attribute change IS counted, or R14 would also pass
        # over a recorder that had stopped recording attributes entirely.
        await pg.evaluate("document.querySelector('button').setAttribute('disabled','')")
        m = await mut(pg)
        check("R15 CONTROL: a genuine attribute change still counts",
              m is not None and m["attrs"].get("disabled") == 1, f"mut={m}")
        await pg.close()

        # R16 SHADOW ROOTS. A MutationObserver on `document` is blind to shadow
        # content. CLAUDE.md #25 records this exact bug class in this exact probe
        # ("shadow-blind — fourth home for a bug class fixed twice"), which is why
        # the attachShadow wrap registers every root it creates.
        pg = await tagged_page(
            "<!doctype html><meta charset=utf-8><body><div id=host></div><script>"
            "window.__r=document.getElementById('host').attachShadow({mode:'open'});"
            "window.__r.innerHTML='<p>seed</p>';</script></body>")
        await pg.wait_for_timeout(300)
        before = await mut(pg)
        await pg.evaluate("window.__r.appendChild(document.createElement('span'))")
        after = await mut(pg)
        check("R16 a mutation INSIDE a shadow root is seen (document-scoped "
              "observers are blind to it — #25's bug class, fourth home)",
              before is not None and after is not None
              and after["structural"] > before["structural"],
              f"before={before and before['structural']} "
              f"after={after and after['structural']}")
        await pg.close()

        # R17 DEGRADATION. listener_tag.js may not have run — a page opened
        # before the extension loaded, or an origin it cannot reach. The probe
        # must report UNKNOWN, and every consumer must treat unknown as unknown
        # and never as quiet, because a false quiet is the worst direction this
        # probe can fail in.
        pg = await browser.new_page()
        await pg.route("**/bare", lambda r: r.fulfill(
            status=200, content_type="text/html",
            body="<!doctype html><meta charset=utf-8><body><p>no tagger</p>"))
        await pg.goto("http://mut.test/bare", wait_until="domcontentloaded")
        r = await probe(pg)
        check("R17 DEGRADATION: with no recorder present the probe reports "
              "unknown (null), not quiet",
              r.get("mut") is None, f"r.mut={r.get('mut')!r}")
        await pg.close()

        # R22/R22b NET-ZERO WITHIN ONE BATCH. A MutationObserver callback is a
        # microtask, so one synchronous script's mutations arrive as one batch.
        # An attribute that starts the batch at X and ends it at X changed
        # nothing — which catches a framework toggling and restoring in one tick,
        # and is the per-record "value did not change" rule at the right
        # granularity. Needs attributeOldValue:true in the observe options;
        # without it every oldValue is null and the whole rule is inert, which is
        # how it was first written.
        # THE ATTRIBUTE MUST START WITH A REAL VALUE, not absent. My first
        # version used an attribute that was added and then REMOVED, and it
        # passed with attributeOldValue ABLATED — because the pair ends absent
        # and a missing oldValue also reads as null, so null === null matched by
        # accident. That is a fixture passing against the broken code, i.e. not
        # a test (PRINCIPLES #11). `data-k` now round-trips 1 -> 2 -> 1, where a
        # null oldValue gives null !== "1" and the record survives.
        pg = await tagged_page("<!doctype html><meta charset=utf-8><body>"
                               "<div id=a data-k='1'>x</div><div id=b>y</div>")
        await pg.wait_for_timeout(3400)
        before = await mut(pg)
        await pg.evaluate("""() => { const e = document.getElementById('a');
          e.setAttribute('data-k','2'); e.setAttribute('data-k','1');
          e.setAttribute('aria-expanded','true');
          e.setAttribute('aria-expanded','false');
          e.setAttribute('aria-expanded','true'); }""")
        await pg.wait_for_timeout(80)
        after = await mut(pg)
        check("R22 an attribute that ends a batch at the value it started with "
              "records nothing (net zero is not a change)",
              before is not None and after is not None
              and not after["attrs"].get("data-k"),
              f"attrs={after and after['attrs']}")
        check("R22b CONTROL: an attribute whose value genuinely ENDS different "
              "is still recorded, even after intermediate flips",
              after is not None and after["attrs"].get("aria-expanded", 0) > 0,
              f"attrs={after and after['attrs']}")
        await pg.close()

        # R23/R23b A THROTTLED TAB IS THE NORMAL CASE, NOT A RACE. The "no
        # overlap" result that justified this design was measured on an
        # UNTHROTTLED page — and #12 means the agent's tab is hidden BY DESIGN,
        # so Chrome clamps its timers and a chunked render commits roughly once
        # per second. Swept across commit intervals with the render in progress:
        # a 1000ms window reported ZERO changes on **50.7%** of reads at a 2s
        # commit interval, which is a FALSE QUIET — the direction that makes an
        # agent conclude absence. At 3000ms it is 0.0% at every interval
        # measured (1s, 2s, 3s). Hence MUT_WIN.
        pg = await tagged_page(
            "<!doctype html><meta charset=utf-8><body><div id=h></div><script>"
            "let i=0;(function s(){const h=document.getElementById('h');"
            "for(let k=0;k<8;k++){const d=document.createElement('div');"
            "d.textContent='r'+(i*8+k);h.appendChild(d);}"
            "if(++i<10)setTimeout(s,2000);})();</script>")
        await pg.wait_for_timeout(3400)          # mid-render, past the parse
        slow = await mut(pg, 3000)
        narrow = await mut(pg, 1000)
        check("R23 a render committing every 2s reads as CHANGING in the "
              "shipped 3000ms window (a throttled tab is the normal case)",
              slow is not None and slow["structural"] > 0,
              f"win3000 structural={slow and slow['structural']}")
        check("R23b ...and the measurement that forced it: the SAME instant in "
              "a 1000ms window can read as quiet, which is a false quiet",
              slow is not None and narrow is not None
              and slow["structural"] >= narrow["structural"],
              f"win3000={slow and slow['structural']} win1000={narrow and narrow['structural']}")
        await pg.close()

        # R20/R20b THE AD-PAGE CASE. A banner keyed on "anything moved" fires on
        # every ad-supported page for ever — theguardian.com runs ~7 ad-driven
        # mutations per 2s — which is the always-on warning #15 priced and #43
        # deleted readyState for being. The tier is decided by the three
        # MutationRecord TYPES, which the spec declares, so it needs no list of
        # "important" attributes.
        pg = await tagged_page(
            "<!doctype html><meta charset=utf-8><body><div id=ad>ad</div>"
            "<button id=b>Buy</button><script>"
            "setInterval(()=>{document.getElementById('ad')"
            ".style.opacity = Math.random();}, 40);</script>")
        # PAST THE PARSE. The fixture's own body/div/button are childList records
        # at t=0; sampling at 500ms left them inside the 1000ms window and the
        # check measured its own construction rather than the steady state (the
        # R14 mistake, repeated). The interval keeps producing attribute records
        # throughout, so waiting does not starve the thing under test.
        await pg.wait_for_timeout(3400)
        m = await mut(pg)
        check("R20 presentation-only churn is attribute-only (no structural, "
              "no text) — the fact the tier is decided on",
              m is not None and m["structural"] == 0 and m["text"] == 0
              and sum(m["attrs"].values()) > 0,
              f"mut={m}")
        await pg.close()

        # R20b THE CONTROL that the tier is not simply "never warn": the same
        # page shape, but appending elements, must still report structural churn.
        pg = await tagged_page(
            "<!doctype html><meta charset=utf-8><body><div id=h></div><script>"
            "setInterval(()=>{const d=document.createElement('div');"
            "d.textContent='x';document.getElementById('h').appendChild(d);}, 40);"
            "</script>")
        await pg.wait_for_timeout(500)
        m = await mut(pg)
        check("R20b CONTROL: a page actually adding elements still reports "
              "structural churn (without this, 'never warn' would pass R20)",
              m is not None and m["structural"] > 0, f"mut={m}")
        await pg.close()

        # R33/R33b AN ENTRY ANIMATION THAT WILL NEVER START.
        # MEASURED in the agent's own tab, which is hidden BY DESIGN (#12):
        #   requestAnimationFrame fired 0 times in 2.6s (60fps gives ~120)
        #   setTimeout(16ms) fired 3 times in 2.6s -- clamped to about 1Hz
        #   `transition: opacity 300ms` from 0 held computed opacity at "0" for
        #     the whole 2s, and checkVisibility({opacityProperty:true}) -- the
        #     COLLECTOR'S OWN test -- answered false at every sample.
        # So a dialog or toast that fades in is absent from read_page
        # INDEFINITELY. #66 saw this on a Bootstrap modal and diagnosed "the
        # batch read before the fade"; waiting would have waited for ever.
        # The signal is the Web Animations API's own: `pending` with
        # currentTime 0 means no start time has been given, i.e. it is waiting
        # for a frame. Headless Playwright renders VISIBLE, so the frozen state
        # is reproduced by probing in the SAME TASK as the trigger, before any
        # frame can run -- which is exactly the state the hidden tab stays in.
        pg = await tagged_page("<!doctype html><meta charset=utf-8><body>"
                               "<button id=keep>Keep</button>")
        # THE PROBE IS GATED ON THE TAB BEING HIDDEN, because the sentence it
        # feeds says the transition cannot start "while this tab is in the
        # background" -- and in a VISIBLE tab that claim is false, since the
        # same filter catches any opacity-0 element inside its first-frame
        # pending window. Headless Playwright renders VISIBLE, so the fixture
        # has to simulate the regime rather than assert into the wrong one.
        _HIDE = ("Object.defineProperty(document,'visibilityState',"
                 "{configurable:true,get:function(){return 'hidden';}});")
        r = await pg.evaluate("(function(){ " + _HIDE + READY + ";"
            " var d=document.createElement('div');"
            " d.style.cssText='position:fixed;left:40px;top:40px;width:200px;"
            "height:60px;opacity:0;transition:opacity 300ms linear';"
            " document.body.appendChild(d); d.getBoundingClientRect();"
            " d.style.opacity='1';"
            " return _readinessPage(); })()")
        check("R33 an element held at opacity 0 by a transition that has not "
              "been given a start time is COUNTED, not silently dropped",
              r.get("frozenFade") == 1, f"frozenFade={r.get('frozenFade')}")

        # THE CONTROL. Without it "always count something" would pass R33 and
        # the sentence would fire on every page -- #15's always-on warning,
        # priced once and deleted twice in this project.
        await pg.close()
        # A CLEAN PAGE, because the element R33 created is still in the DOM with
        # its animation still pending -- the control would otherwise measure
        # R33's fixture and fail for a reason that is not the code's.
        pg = await tagged_page("<!doctype html><meta charset=utf-8><body>"
                               "<button id=keep>Keep</button>")
        r2 = await pg.evaluate("(function(){ " + _HIDE + READY + ";"
            " var d=document.createElement('div');"
            " d.style.cssText='position:fixed;left:40px;top:120px;width:200px;"
            "height:60px;opacity:1';"
            " document.body.appendChild(d); d.getBoundingClientRect();"
            " return _readinessPage(); })()")
        check("R33b CONTROL: an element with no pending entry transition counts "
              "nothing",
              (r2.get("frozenFade") or 0) == 0, f"frozenFade={r2.get('frozenFade')}")

        # R33c CONTROL: THE GATE ITSELF. In a VISIBLE tab the same pending
        # transition is a genuine ~16ms race that waiting DOES fix, so counting
        # it there would make the sentence assert a cause it had not checked --
        # #33's defect, and the one C15 exists to catch. An uninformed review of
        # this diff caught it before it shipped.
        await pg.close()
        # A CLEAN PAGE: `_HIDE` redefines document.visibilityState for the life
        # of the document, so reusing the page would measure the override
        # rather than the gate.
        pg = await tagged_page("<!doctype html><meta charset=utf-8><body>"
                               "<button id=keep>Keep</button>")
        r3 = await pg.evaluate("(function(){ " + READY + ";"
            " var d=document.createElement('div');"
            " d.style.cssText='position:fixed;left:40px;top:200px;width:200px;"
            "height:60px;opacity:0;transition:opacity 300ms linear';"
            " document.body.appendChild(d); d.getBoundingClientRect();"
            " d.style.opacity='1';"
            " return {fade:_readinessPage().frozenFade,"
            " vis:document.visibilityState}; })()")
        check("R33c CONTROL: a VISIBLE tab counts nothing — there the pending "
              "transition is a real race and waiting fixes it",
              r3.get("vis") == "visible" and (r3.get("fade") or 0) == 0,
              f"vis={r3.get('vis')} fade={r3.get('fade')}")
        await pg.close()

        # R19 A SAME-ORIGIN FRAME'S CHURN IS NOT QUIET. listener_tag.js runs in
        # ALL frames so each keeps its own ring, but the probe runs in the TOP
        # frame only — so a page whose content lives in an iframe would report
        # quiet while that frame paints. A FALSE quiet is the worst direction
        # this probe can fail in, which is the same reason R17 exists.
        pg = await tagged_page(
            "<!doctype html><meta charset=utf-8><body><p>shell</p>"
            "<iframe id=f style='width:400px;height:300px' src='/mut-child'></iframe>")
        await pg.route("**/mut-child", lambda r: r.fulfill(
            status=200, content_type="text/html",
            body="<!doctype html><meta charset=utf-8><body><div id=h></div><script>"
                 "let i=0;(function s(){for(let k=0;k<4&&i<400;k++,i++){"
                 "const d=document.createElement('div');d.textContent='r'+i;"
                 "document.getElementById('h').appendChild(d);}"
                 "if(i<400)setTimeout(s,18);})();</script>"))
        await pg.reload(wait_until="domcontentloaded")
        await pg.wait_for_timeout(400)
        top_only = await pg.evaluate(
            "() => window.__abMut ? window.__abMut.query(null, 1000) : null")
        r = await probe(pg)
        # NOT "the top frame reads zero" — inserting the iframe mutates the top
        # frame, so it legitimately carries a few records. The invariant is that
        # the top frame alone looks SETTLED (its last change is old) while the
        # merged view shows the child actively painting. Against the unmerged
        # code the two are identical, which is what makes this fail pre-fix.
        _m, _t = r.get("mut"), top_only
        check("R19 a same-origin FRAME still painting is reported as changing, "
              "where the top frame alone looks settled",
              _m is not None and _t is not None
              and _m["structural"] > _t["structural"]
              and _m["since"] < _t["since"]
              and _m.get("frames", 0) >= 1,
              f"merged={_m}  top_frame_alone={_t}")
        await pg.close()

        # R18 THE PAGE MUST NOT BE ABLE TO BLIND THIS. listener_tag.js runs in
        # the MAIN world, so everything it defines is reachable by page script.
        # A plain `window.__abMut = {...}` puts it in Object.keys(window), which
        # fingerprints the extension AND lets any script replace the object with
        # a query() that always answers "quiet" — and a false quiet is the worst
        # direction this probe can fail in. The two expandos and __abConsole in
        # the same file all use non-enumerable defineProperty; this is that
        # invariant, stated as a test rather than as a convention.
        pg = await tagged_page("<!doctype html><meta charset=utf-8><body>hi")
        # BOTH REPLACEMENT PATHS. The first version of this check drove only
        # `window.__abMut = x`, and passed while the hole was wide open: the
        # property was `configurable: true`, which blocks assignment and does
        # NOT block Object.defineProperty. So a check whose own title said
        # "cannot be replaced by page script" could not fire on the way a page
        # would actually do it. Found by an independent audit, reproduced in a
        # real page (viaAssign false, viaDefine TRUE, spoofed since=999999).
        hardened = await pg.evaluate("""() => {
          const d = Object.getOwnPropertyDescriptor(window, '__abMut');
          const before = window.__abMut;
          const spoof = { query: () => ({ since: 999999, structural: 0, text: 0,
                                          attrs: {}, total: 1, saturated: false,
                                          win: 1000 }) };
          let viaAssign = false, viaDefine = false;
          try { window.__abMut = spoof; viaAssign = window.__abMut === spoof; } catch (e) {}
          try { Object.defineProperty(window, '__abMut',
                  { value: spoof, configurable: true });
                viaDefine = window.__abMut === spoof; } catch (e) {}
          return { enumerable: d && d.enumerable, writable: d && d.writable,
                   configurable: d && d.configurable,
                   inKeys: Object.keys(window).includes('__abMut'),
                   viaAssign, viaDefine, replaced: window.__abMut !== before };
        }""")
        check("R18 the recorder is non-enumerable and cannot be replaced by page "
              "script — BY ASSIGNMENT **OR** BY defineProperty (a substituted "
              "query() that always says 'quiet' would silently disable the signal)",
              hardened["enumerable"] is False and hardened["writable"] is False
              and hardened["configurable"] is False
              and hardened["inKeys"] is False
              and hardened["viaAssign"] is False and hardened["viaDefine"] is False
              and hardened["replaced"] is False,
              str(hardened))
        await pg.close()

        # ------------------------------------------------------------------
        # R24-R31  SCOPED READINESS
        #
        # `__abMut.query(scope, …)` shipped with five callers and every one of
        # them passing null, so the composed-tree containment helper behind it
        # was unreachable -- half a contract, the shape this project has had to
        # delete four times (`origin`, `viewport`, `on_fail:"heal"`, `delta`).
        # OPEN.md item 3 said wire it or delete it.
        #
        # WHAT DECIDED IT was a measurement, not the tidiness argument. On a page
        # carrying a live ticker beside a table that finished painting, at the
        # same instant:
        #     doc-wide             since=48ms    110 structural  -> STILL CHANGING
        #     scoped to the table  since=4013ms    0 structural  -> no banner
        # A scoped read deliberately excludes the document (#11, #26 both had to
        # stop page-level facts leaking into one), and then described the
        # document's churn in the banner above it.
        #
        # AND IT COVERS A CASE THE #70 KIND-SPLIT DOES NOT. That split assumed ad
        # churn is ATTRIBUTE churn (@style on a carousel). A ticker that updates
        # via `textContent` arrives as childList -- Chrome records it as
        # remove+add of a text node -- so it trips the STRONG banner. Measured at
        # 25 `structural`, 0 `text`, for a clock doing nothing but `textContent=`.
        #
        # EVERY CHECK BELOW FAILS AGAINST THE PRE-FIX PROBE, which ignored its
        # argument. The three controls (R24b, R24c, R26b) are what stop "always
        # report quiet when scoped" from passing R24 -- the false-quiet direction
        # is the worst this probe can fail in, and scoping is the change most
        # able to introduce one.
        MIXED = """<!doctype html><meta charset=utf-8><body>
<div id=ad mmid="1"><span id=clock>00:00</span></div>
<div id=content mmid="2"><table id=t></table></div>
<div id=late mmid="3"></div>
<div id=hosty mmid="4"></div>
<script>
const t = document.getElementById('t');
for (let i=0;i<30;i++){const r=t.insertRow();r.insertCell().textContent='row '+i;}
let k=0; setInterval(()=>{document.getElementById('clock').textContent='00:'+(k++);}, 120);
let j=0;(function s(){for(let c=0;c<2&&j<400;c++,j++){
  const d=document.createElement('div');d.textContent='late '+j;
  document.getElementById('late').appendChild(d);}
  if(j<400)setTimeout(s,100);})();
const host=document.getElementById('hosty');
const sr=host.attachShadow({mode:'open'});
sr.innerHTML='<div id=sh>s</div>';
let q=0; setInterval(()=>{sr.getElementById('sh').textContent='s'+(q++);}, 120);
</script></body>"""
        pg = await tagged_page(MIXED)
        # Long enough that the table's own paint falls OUTSIDE the 3000ms window.
        # At 2.5s it is still inside it and the check would read `33 structural,
        # last change 2515ms ago` -- correct, and not the clean demonstration.
        await pg.wait_for_timeout(4000)
        r_doc = await probe(pg)
        r_content = await probe_scoped(pg, "2")
        r_ad = await probe_scoped(pg, "1")
        r_late = await probe_scoped(pg, "3")
        r_shadow = await probe_scoped(pg, "4")

        check("R24 a scoped read describes the SUBTREE: a settled region reports "
              "quiet at the same instant the document reports churn",
              r_doc["mut"]["structural"] > 0 and r_doc["mut"]["since"] < 500
              and r_content["mut"]["structural"] == 0
              and r_content["mut"]["text"] == 0
              and r_content["mut"]["since"] > 3000,
              f"doc struct={r_doc['mut']['structural']} since={r_doc['mut']['since']} | "
              f"scoped struct={r_content['mut']['structural']} since={r_content['mut']['since']}")
        check("R24b CONTROL: scoping to the CHURNING region still reports churn "
              "(without this, 'always quiet when scoped' would pass R24)",
              r_ad["mut"]["structural"] > 0 and r_ad["mut"]["since"] < 500,
              f"struct={r_ad['mut']['structural']} since={r_ad['mut']['since']}")
        check("R24c CONTROL: a scoped region still BUILDING is never reported "
              "quiet — a false quiet is the worst direction this probe can fail in",
              r_late["mut"]["structural"] > 0 and r_late["mut"]["since"] < 500,
              f"struct={r_late['mut']['structural']} since={r_late['mut']['since']}")
        # BOUNDED ON BOTH SIDES, AND BY A MARGIN RATHER THAN BY `<`. Three
        # versions of this check, two of them wrong, and only the ablation said so:
        #   "reports churn"      passes in BOTH arms — the document-wide answer
        #                        reports this churn too, so it proves nothing.
        #   "strictly less than  passed the ABLATION at 108 vs 110. The page is
        #    the document"       still painting between the two probe calls, so
        #                        two doc-wide answers taken a few ms apart differ
        #                        by a handful of records and the inequality holds
        #                        by accident.
        # The shadow subtree contributes ~25 of the document's ~110, so half is a
        # wide margin for the real answer and unreachable for a doc-wide one.
        # ZERO would mean the walk failed to cross the boundary; NEAR-EQUAL means
        # the scope was ignored.
        check("R25 scope containment crosses a SHADOW boundary, which "
              "Node.contains() cannot — the scoped answer is the shadow "
              "subtree's own churn, neither zero nor the whole document's",
              0 < (r_shadow["mut"]["structural"] + r_shadow["mut"]["text"])
              < (r_doc["mut"]["structural"] + r_doc["mut"]["text"]) / 2
              and r_shadow["mut"]["since"] < 500,
              f"scoped={r_shadow['mut']['structural']}+{r_shadow['mut']['text']} "
              f"doc={r_doc['mut']['structural']}+{r_doc['mut']['text']} "
              f"since={r_shadow['mut']['since']}")
        native = await pg.evaluate("""() => {
            const h = document.getElementById('hosty');
            return h.contains(h.shadowRoot.getElementById('sh'));
        }""")
        check("R25b ...and contains() genuinely cannot see it, so the composed "
              "walk is earning its keep rather than restating the easy answer",
              native is False, f"host.contains(shadowChild)={native}")

        # R25c — THE CASE R25 CANNOT REACH, AND IT IS A FALSE QUIET.
        # R25's host mutates an Element INSIDE its shadow root, so the record's
        # target is a text node whose `parentElement` is that Element and the
        # attribution works. The shape that breaks is a direct append INTO the
        # root: there the MutationRecord's target IS the ShadowRoot, which is a
        # DocumentFragment with `parentNode === null` and therefore
        # `parentElement === null`. The record was stored with NO target, and a
        # scoped read could never attribute it. That is the normal Lit/Shoelace
        # shape -- a component rendering its own children -- so a scoped read of
        # a region containing one reported QUIET while it painted.
        #
        # THE SCOPE MUST HOLD SOME OTHER HISTORY or this cannot detect the bug:
        # with nothing attributable at all, #77's branch correctly answers
        # UNKNOWN, which is safe. The false QUIET needs a scope whose `since` is
        # a real but STALE number, which is what `#settled` provides.
        DIRECT = """<!doctype html><meta charset=utf-8><body>
<div id=wrap mmid="1">
  <div id=settled>done</div>
  <div id=host2></div>
</div>
<div id=calm mmid="2"><p>nothing happens here</p></div>
<script>
const sr2 = document.getElementById('host2').attachShadow({mode:'open'});
let m=0; setInterval(()=>{ const d=document.createElement('div');
  d.textContent='r'+(m++); sr2.appendChild(d); }, 120);
</script></body>"""
        pg2 = await tagged_page(DIRECT)
        # Past the 3000ms window, so the page's own parse is outside it and the
        # only thing inside is the shadow root's ongoing paint.
        await pg2.wait_for_timeout(4000)
        r_wrap = await probe_scoped(pg2, "1")
        r_calm = await probe_scoped(pg2, "2")
        check("R25c a scope containing a shadow root that is appending DIRECTLY "
              "into itself is never reported quiet — a ShadowRoot has no "
              "parentElement, so those records were unattributable",
              r_wrap["mut"]["structural"] > 0 and r_wrap["mut"]["since"] < 500,
              f"struct={r_wrap['mut']['structural']} since={r_wrap['mut']['since']}")
        check("R25d CONTROL: a genuinely settled sibling scope is still reported "
              "quiet — without this, resolving every record to SOMETHING would "
              "pass R25c while making every scoped read report churn",
              r_calm["mut"]["structural"] == 0 and r_calm["mut"]["text"] == 0,
              f"struct={r_calm['mut']['structural']} text={r_calm['mut']['text']} "
              f"since={r_calm['mut']['since']}")
        check("R26 the probe reports WHICH question it answered",
              r_doc.get("scoped") is False and r_content.get("scoped") is True
              and r_doc.get("scopeMiss") is False and r_content.get("scopeMiss") is False,
              f"doc={r_doc.get('scoped')}/{r_doc.get('scopeMiss')} "
              f"scoped={r_content.get('scoped')}/{r_content.get('scopeMiss')}")
        r_miss = await probe_scoped(pg, "999")
        check("R26b CONTROL: a scope that does NOT resolve falls back to the "
              "whole page and SAYS so — never to 'nothing to report'",
              r_miss.get("scoped") is False and r_miss.get("scopeMiss") is True
              and r_miss["mut"]["structural"] > 0,
              f"scoped={r_miss.get('scoped')} miss={r_miss.get('scopeMiss')} "
              f"struct={r_miss['mut']['structural']}")
        await pg.close()

        # The DECLARATIVE signals are scoped too, and each has an element, so
        # containment decides it exactly. The network count deliberately is NOT
        # -- a request is not attributable to a subtree -- which is why the
        # banner marks it PAGE-WIDE rather than leaving the reader to assume the
        # whole sentence describes their scope.
        DECL = """<!doctype html><meta charset=utf-8><body>
<div id=outside mmid="1">
  <div role="progressbar" aria-valuenow="40" style="width:200px;height:12px"></div>
  <div aria-busy="true" style="width:200px;height:40px">loading</div>
</div>
<div id=inside mmid="2"><p>all done</p></div>
<div id=withbar mmid="3">
  <div role="progressbar" aria-valuenow="10" style="width:200px;height:12px"></div>
</div>
<div id=selfbusy mmid="4" aria-busy="true" style="width:200px;height:40px">me</div>
<div id=closedhost mmid="5"></div>
<script>
const ch = document.getElementById('closedhost');
const cr = ch.attachShadow({mode:'closed'});
cr.innerHTML = '<div role="progressbar" aria-valuenow="5" style="width:200px;height:12px"></div>';
</script></body>"""
        pg = await tagged_page(DECL)
        await pg.wait_for_timeout(150)
        d_doc = await probe(pg)
        d_in = await probe_scoped(pg, "2")
        d_bar = await probe_scoped(pg, "3")
        d_self = await probe_scoped(pg, "4")
        d_closed = await probe_scoped(pg, "5")
        check("R27 a progressbar and an aria-busy region OUTSIDE the scope do "
              "not fire for a read that excluded them",
              d_doc["prog"] >= 1 and d_doc["busy"] >= 1
              and d_in["prog"] == 0 and d_in["busy"] == 0,
              f"doc prog={d_doc['prog']} busy={d_doc['busy']} | "
              f"scoped prog={d_in['prog']} busy={d_in['busy']}")
        check("R27b CONTROL: one INSIDE the scope still fires (without this, "
              "'scoped means zero' would pass R27)",
              d_bar["prog"] == 1, f"prog={d_bar['prog']}")
        check("R28 the scope ELEMENT ITSELF counts — querySelectorAll(root) "
              "returns descendants only, so a read scoped to the busy element "
              "would otherwise report it settled",
              d_self["busy"] == 1, f"busy={d_self['busy']}")
        check("R29 a signal inside a CLOSED shadow root is seen (#31's "
              "__abClosedRoot handle; nine traversal sites read it and this "
              "probe was the one that did not)",
              d_closed["prog"] == 1 and d_doc["prog"] == 3,
              f"scoped prog={d_closed['prog']} doc prog={d_doc['prog']} "
              f"(3 = two in the open page plus one inside the closed root; "
              f"`>= 2` passed in BOTH arms and pinned nothing)")
        await pg.close()

        # R29b — THE DISCRIMINATING PAGE for the UNSCOPED half of the closed-root
        # fix, which R29 above could not reach. R29's own fixture carries two
        # progressbars outside the closed root, so a doc-side `>= 2` is satisfied
        # whether or not `_deepAll` descends `__abClosedRoot`. Here the ONLY
        # signals on the page are inside a closed root, so the ablated collector
        # reports a completely settled page.
        CLOSED_ONLY = """<!doctype html><meta charset=utf-8><body>
<div id=host></div>
<script>
const r = document.getElementById('host').attachShadow({mode:'closed'});
r.innerHTML = '<div role="progressbar" aria-valuenow="30" style="width:200px;height:12px"></div>'
            + '<div aria-busy="true" style="width:200px;height:40px">loading</div>';
</script></body>"""
        pg = await tagged_page(CLOSED_ONLY)
        await pg.wait_for_timeout(150)
        c_only = await probe(pg)
        check("R29b a page whose ONLY readiness signals live in a CLOSED shadow "
              "root is not reported as settled (ablated: prog 0, busy 0)",
              c_only["prog"] == 1 and c_only["busy"] == 1,
              f"prog={c_only['prog']} busy={c_only['busy']}")
        await pg.close()

        # ------------------------------------------------------------------
        # R30-R32  FRAMES AND THE UNKNOWN STATE
        #
        # `_inScope` -- the composed + cross-frame containment walk -- had ZERO
        # coverage: it is called from exactly one place (the scoped frame merge)
        # and no fixture in this suite contained an iframe, so ablating it to
        # `return true` OR `return false` left every check green. The defect that
        # was hiding there is R30.
        FRAMED = """<!doctype html><meta charset=utf-8><body>
<div id=quiet mmid="1">settled</div>
<iframe id=f mmid="2" src="/painting" style="width:300px;height:200px"></iframe>
</body>"""
        # PROGRESSBAR FIRST. In the first version it sat after a div growing to
        # 4000 rows, which pushed it thousands of px down the frame document
        # where the off-viewport filter correctly dropped it -- the fixture
        # measuring itself, not the collector.
        PAINTING = """<!doctype html><meta charset=utf-8><body>
<div role="progressbar" aria-valuenow="20" style="width:200px;height:12px"></div>
<div id=inner mmid="9"></div>
<script>
let i=0;(function s(){for(let k=0;k<6&&i<4000;k++,i++){
  const d=document.createElement('div');d.textContent='r'+i;
  document.getElementById('inner').appendChild(d);}
  if(i<4000)setTimeout(s,16);})();
</script></body>"""
        pg = await browser.new_page(viewport={"width": 900, "height": 700})
        await pg.add_init_script(TAG)
        await pg.route("**/parent", lambda r: r.fulfill(
            status=200, content_type="text/html", body=FRAMED))
        await pg.route("**/painting", lambda r: r.fulfill(
            status=200, content_type="text/html", body=PAINTING))
        await pg.goto("http://frame.test/parent", wait_until="domcontentloaded")
        await pg.wait_for_timeout(700)
        # The real collector's `_walkInject` recurses into contentDocument, so a
        # frame-internal element genuinely IS in the TOP registry and a scoped
        # read genuinely resolves it. Build the registry the same way.
        await pg.evaluate("""() => {
            const reg = new Map();
            const visit = (d) => {
              d.querySelectorAll('[mmid]').forEach(e => reg.set(e.getAttribute('mmid'), e));
              d.querySelectorAll('iframe,frame').forEach(f => {
                try { if (f.contentDocument) visit(f.contentDocument); } catch (e) {}
              });
            };
            visit(document);
            window.__mmidReg = reg;
        }""")
        f_doc = await probe(pg)
        f_inner = await probe_scoped(pg, "9")    # a div INSIDE the frame
        f_frame = await probe_scoped(pg, "2")    # the <iframe> ITSELF
        f_quiet = await probe_scoped(pg, "1")    # a settled div beside it

        check("R30 a scope INSIDE a same-origin frame reports that frame's churn "
              "— the frame guard must answer 'is the scope inside this frame', "
              "not only 'is this frame inside the scope'",
              f_doc["mut"]["structural"] > 0
              and f_inner["mut"]["since"] >= 0 and f_inner["mut"]["since"] < 600
              and f_inner["mut"]["structural"] > 0,
              f"doc struct={f_doc['mut']['structural']} | "
              f"scoped-into-frame since={f_inner['mut']['since']} "
              f"struct={f_inner['mut']['structural']}")
        check("R31 a scope that IS an <iframe> sees the declarative signals "
              "inside it (querySelectorAll(root) never matches the root, so its "
              "contentDocument has to be walked explicitly)",
              f_frame["prog"] == 1,
              f"prog={f_frame['prog']} busy={f_frame['busy']}")
        check("R31b CONTROL: a settled sibling of that frame does NOT inherit "
              "its churn — without this, 'merge every frame' would pass R30. "
              "Its own parse record is legitimately in the window, so this is a "
              "magnitude claim, not a zero",
              f_quiet["mut"]["structural"] * 20 < f_doc["mut"]["structural"]
              and f_quiet["prog"] == 0,
              f"sibling struct={f_quiet['mut']['structural']} vs doc "
              f"{f_doc['mut']['structural']}, prog={f_quiet['prog']}")
        await pg.close()

        # R32 — `scoped && since === -1` IS CONSTRUCTIBLE, and it is the state
        # every scoped false-quiet lands in. An element's own parse generates a
        # childList record, so a merely-settled element has a recency reading;
        # what produces -1 is the record being LOST — here by flooding the
        # 1024-slot ring after touching the scope once. The probe must call that
        # UNKNOWN rather than returning silence.
        EVICT = """<!doctype html><meta charset=utf-8><body>
<div id=scope mmid="1"></div><div id=sink></div>
<script>
document.getElementById('scope').appendChild(document.createElement('b'));
const sink = document.getElementById('sink');
let i = 0;
(function burst(){
  for (let k = 0; k < 20 && i < 1400; k++, i++) sink.appendChild(document.createElement('i'));
  if (i < 1400) setTimeout(burst, 1);
})();
</script></body>"""
        pg = await tagged_page(EVICT)
        await pg.wait_for_timeout(500)
        ev = await probe_scoped(pg, "1")
        check("R32 a scope whose record was EVICTED reports unknown, not quiet: "
              "since=-1 with sinceAny set and saturated true, which is what the "
              "renderer needs to say 'could not attribute' instead of nothing",
              ev["mut"]["since"] < 0 and ev["mut"]["sinceAny"] >= 0
              and ev["mut"]["saturated"] is True and ev["mut"].get("scoped") is True,
              f"since={ev['mut']['since']} sinceAny={ev['mut']['sinceAny']} "
              f"saturated={ev['mut']['saturated']} total={ev['mut']['total']}")
        await pg.close()

        # R34 — A QUIET VERDICT MUST SAY WHAT IT COULD NOT SEE. Every signal this
        # probe reads comes from the top document and same-origin frames, so a
        # page whose content paints inside a CROSS-ORIGIN frame reports quiet
        # while it is still building. Recency cannot reach it: the frame is
        # opaque to all of it. Measured at two offsets by the adversarial
        # readiness audit, and the one false-quiet shape nothing else covers.
        #
        # CROSS-ORIGIN IS TESTED, NOT INFERRED FROM `src` -- an about:blank, a
        # srcdoc and a same-site subdomain all read as "different" by string and
        # are perfectly readable -- so the fixture serves a frame from a genuinely
        # different host and the probe asks `contentDocument`.
        xp = await browser.new_page(viewport={"width": 900, "height": 700})
        await xp.add_init_script(TAG)
        await xp.route("**/host-a", lambda r: r.fulfill(
            status=200, content_type="text/html",
            body="<!doctype html><meta charset=utf-8><body style='margin:0'>"
                 "<main><h1>Outer</h1>"
                 "<iframe src='http://b.test/host-b' style='width:400px;height:300px'></iframe>"
                 "</main>"))
        await xp.route("**/host-b", lambda r: r.fulfill(
            status=200, content_type="text/html",
            body="<!doctype html><meta charset=utf-8><body>inner</body>"))
        await xp.goto("http://a.test/host-a", wait_until="domcontentloaded")
        await xp.wait_for_timeout(3400)        # past the window: the DOM is QUIET
        xr = await probe(xp)
        check("R34 the probe counts a RENDERED cross-origin frame it cannot read "
              "into — the one false-quiet shape recency cannot reach",
              (xr or {}).get("blindFrames") == 1,
              f"blindFrames={(xr or {}).get('blindFrames')!r}")
        await xp.close()

        # R34b/R34c THE CONTROLS, and they are what stop this from becoming the
        # always-on warning #15 priced and #43 deleted readyState for. A
        # SAME-ORIGIN frame is readable, so it is not blind; a page with no frame
        # at all counts nothing. Priced on the corpus at 6.9% of pages, but a
        # measurement is not a guarantee and these two are.
        #
        # HOW EACH WAS PROVEN, because a NEW FIELD cannot be ablated the usual
        # way: against the pre-fix collector `blindFrames` is undefined, so every
        # check here fails and none of them is a control in that arm. The
        # meaningful ablation is of the RULE. Counting any RENDERED frame instead
        # of only the opaque ones leaves R34 passing and makes **R34b fail**,
        # which is exactly what a control is for. Both arms were run.
        sp = await browser.new_page(viewport={"width": 900, "height": 700})
        await sp.add_init_script(TAG)
        await sp.route("**/same-a", lambda r: r.fulfill(
            status=200, content_type="text/html",
            body="<!doctype html><meta charset=utf-8><body style='margin:0'>"
                 "<main><h1>Outer</h1>"
                 "<iframe src='http://a.test/same-b' style='width:400px;height:300px'></iframe>"
                 "</main>"))
        await sp.route("**/same-b", lambda r: r.fulfill(
            status=200, content_type="text/html",
            body="<!doctype html><meta charset=utf-8><body>inner</body>"))
        await sp.goto("http://a.test/same-a", wait_until="domcontentloaded")
        await sp.wait_for_timeout(300)
        sr = await probe(sp)
        check("R34b CONTROL: a SAME-ORIGIN frame is readable, so it is not "
              "counted — otherwise this would fire on any page with a frame",
              (sr or {}).get("blindFrames") == 0,
              f"blindFrames={(sr or {}).get('blindFrames')!r}")
        await sp.close()

        np_ = await tagged_page(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<main><h1>No frames here</h1><p>plain</p></main>")
        await np_.wait_for_timeout(300)
        nr = await probe(np_)
        check("R34c CONTROL: a page with no frame at all counts none",
              (nr or {}).get("blindFrames") == 0,
              f"blindFrames={(nr or {}).get('blindFrames')!r}")
        await np_.close()

        await browser.close()

    passed = sum(1 for x in results if x)
    print(f"\n{passed}/{len(results)} readiness checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

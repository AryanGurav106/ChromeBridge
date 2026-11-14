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

        await browser.close()

    passed = sum(1 for x in results if x)
    print(f"\n{passed}/{len(results)} readiness checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

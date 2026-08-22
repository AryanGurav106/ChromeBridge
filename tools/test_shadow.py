"""End-to-end test of shadow-DOM piercing in background.js.

Loads tools/shadow_test.html (nested open shadow roots) into headless Chromium,
then runs the REAL functions extracted verbatim from extension/background.js:

  1. _collectInteractivePage — shadow controls must appear in the listing with
     correct names (label[for] resolved inside the shadow root), the nested
     (2-level) link must be found, and the unselected shadow <select> flagged.
  2. _clickPage("[mmid='N']") on the shadow button — must resolve through
     window.__mmidReg and actually fire the handler (counter increments).
  3. _enterTextPage on the shadow input — value must land.
  4. Light-DOM controls must be unaffected (regression).

Run:  python tools/test_shadow.py     (exit code 0 = all pass)
"""

import asyncio
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract as _shared_extract  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")


def extract(name: str) -> str:
    """Delegates to tools/_extract, which skips comments/strings/regexes.

    The brace counter this replaced also counted braces inside comments, so one
    `{` in prose silently sliced in the wrong amount of code and the failure
    surfaced somewhere unrelated.
    """
    return _shared_extract(name, BG, verify=True)


COLLECT = extract("_collectInteractivePage")
CLICK = extract("_clickPage")
TYPE = extract("_enterTextPage")
DOMTEXT = extract("_domTextPage")

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not ok else ""))


async def main():
    url = (ROOT / "tools" / "shadow_test.html").as_uri()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1366, "height": 900})
        await page.goto(url)
        await page.wait_for_timeout(300)

        # ---- 1. collection ------------------------------------------------
        listing = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()")
        raw = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        by_label = {}
        for e in raw:
            by_label.setdefault((e.get("name") or e.get("label") or e.get("text") or ""), []).append(e)

        def find(substr):
            return [e for e in raw if substr in (e.get("name") or "") or substr in (e.get("label") or "") or substr in (e.get("text") or "")]

        check("light button listed", bool(find("Light button")))
        check("light field name via label[for]", bool(find("Light field")))
        check("shadow button listed (1-level shadow)", bool(find("Shadow button")))
        sf = find("Shadow field")
        check("shadow input name via label[for] INSIDE shadow root", bool(sf))
        check("deep nested link listed (2-level shadow)", bool(find("Deep nested link")))
        ss = [e for e in raw if e.get("tag") == "select" and e.get("unselected")]
        check("shadow <select> flagged (unselected)", bool(ss))
        dlg = [e for e in raw if "Dialog OK" in (e.get("text") or "") and e.get("section") == "dialog"]
        check("section=dialog detected across shadow boundary", bool(dlg))
        check("no MODAL banner for non-modal shadow dialog", "MODAL/DIALOG IS CURRENTLY OPEN" not in listing)

        # ---- 2. click the shadow button through the registry ---------------
        sb = find("Shadow button")
        if sb:
            mmid = sb[0]["mmid"]
            r = await page.evaluate("(function(){ " + CLICK + "; return _clickPage(\"[mmid='" + mmid + "']\"); })()")
            clicks = await page.evaluate("window.__shadowClicks")
            check("click shadow button via mmid registry", bool(r.get("ok")) and clicks == 1,
                  f"result={r} clicks={clicks}")
        else:
            check("click shadow button via mmid registry", False, "button not found in listing")

        # ---- 3. type into the shadow input ---------------------------------
        si = [e for e in sf if e.get("tag") == "input"]
        if si:
            mmid = si[0]["mmid"]
            r = await page.evaluate("(function(){ " + TYPE + "; return _enterTextPage(\"[mmid='" + mmid + "']\", 'hello shadow'); })()")
            val = await page.evaluate("document.querySelector('x-widget').shadowRoot.getElementById('si').value")
            check("type into shadow input via mmid registry", bool(r.get("ok")) and val == "hello shadow",
                  f"result={r} value={val!r}")
        else:
            check("type into shadow input via mmid registry", False, "input not found in listing")

        # ---- 4. light-DOM regression ---------------------------------------
        lb = find("Light button")
        if lb:
            r = await page.evaluate("(function(){ " + CLICK + "; return _clickPage(\"[mmid='" + lb[0]["mmid"] + "']\"); })()")
            lclicks = await page.evaluate("window.__lightClicks || 0")
            check("light-DOM click still works", bool(r.get("ok")) and lclicks >= 1)
        # ---- S12: EFFECT DETECTION must cross shadow boundaries too ----------
        # The collector crossed shadow roots long ago; the probes that decide "did
        # this click/submit do anything?" never got the same fix — the same bug
        # class as CLAUDE.md #9 and #15, in its fourth and fifth homes. Measured:
        # a click that opens a Lit/Shoelace dialog inside a shadow root moves the
        # light-DOM node count 6 -> 6 and the dialog count 0 -> 0, so "click had no
        # detectable effect" fires on a click that WORKED — and a false FAILED gets
        # retried, which is the double-submit class.
        ep = await browser.new_page(viewport={"width": 1000, "height": 700})
        await ep.set_content(
            "<!DOCTYPE html><meta charset=utf-8><body style='margin:0'>"
            "<my-app></my-app><script>"
            "class MyApp extends HTMLElement { connectedCallback(){"
            " const r=this.attachShadow({mode:'open'});"
            " r.innerHTML='<button id=open>Open</button><div id=host></div>';"
            " r.getElementById('open').addEventListener('click',()=>{"
            "  r.getElementById('host').innerHTML='<div role=\"dialog\" aria-modal=\"true\">"
            "<p>Confirm</p><button>OK</button></div>';});}}"
            "customElements.define('my-app',MyApp);</script></body>")
        await ep.wait_for_timeout(200)
        _DEEP_N = ("(function(){let c=0;const v=(r,d)=>{if(d>6)return;try{const a=r.querySelectorAll('*');"
                   "c+=a.length;a.forEach(e=>{if(e.shadowRoot)v(e.shadowRoot,d+1);});}catch(e){}};"
                   "v(document,0);return c;})()")
        _LIGHT_N = "document.querySelectorAll('*').length"
        _before = (await ep.evaluate(_LIGHT_N), await ep.evaluate(_DEEP_N))
        await ep.evaluate("document.querySelector('my-app').shadowRoot.getElementById('open').click()")
        await ep.wait_for_timeout(150)
        _after = (await ep.evaluate(_LIGHT_N), await ep.evaluate(_DEEP_N))
        check("S12 a light-DOM node count CANNOT see a shadow click's effect"
              " (this is why the probe had to change)",
              _after[0] == _before[0], f"light {_before[0]} -> {_after[0]}")
        check("S12b ...while the shadow-aware count does",
              _after[1] > _before[1], f"deep {_before[1]} -> {_after[1]}")
        # ...and the shipped probe must use the shadow-aware form.
        _bg = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
        check("S12c the shipped click/submit effect probes are shadow-aware",
              _bg.count("dup:deepall") >= 2 and "dialogs: _deep(sel).length" in _bg,
              f"dup:deepall sites={_bg.count('dup:deepall')}")
        await ep.close()

        # ---- S13: TEXT extraction crosses shadow boundaries, like COLLECTION --
        # The collector has recursed into open shadow roots for a long time; text
        # extraction never did, so the two disagreed about the same element. A
        # custom element that renders all its text inside its own shadow root read
        # as EMPTY, and because it usually sits INSIDE a link or button the result
        # was a silently amputated name rather than a missing one:
        # "opened <relative-time>3 days ago</relative-time>" came back "opened".
        # That is GitHub's timestamps and Reddit's vote counts, unreachable by
        # every text tool.
        tp = await browser.new_page(viewport={"width": 900, "height": 700})
        await tp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await tp.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<h1>Thread</h1><p>Ordinary light-DOM prose, long enough to matter.</p>"
            "<a id=lnk href=#x style='display:block;width:300px;height:26px'>"
            "<span>opened </span><my-time id=mt></my-time></a>"
            "<vote-count id=vc style='display:block;width:60px;height:20px'></vote-count>"
            "<icon-only id=io style='display:block;width:20px;height:20px'></icon-only>"
            "<script>"
            "document.getElementById('mt').attachShadow({mode:'open'})"
            ".innerHTML='<span>3 days ago</span>';"
            "document.getElementById('vc').attachShadow({mode:'open'})"
            ".innerHTML='<span>1,204</span>';"
            "document.getElementById('io').attachShadow({mode:'open'})"
            ".innerHTML='<span>\\uf002</span>';"
            "</script></body>")
        await tp.wait_for_timeout(200)
        _sa = await tp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        _lk = next((e for e in _sa if e.get("tag") == "a"), None)
        check("S13 a name assembled across a shadow boundary is COMPLETE, not clipped",
              bool(_lk) and "3 days ago" in ((_lk.get("label") or "") + (_lk.get("name") or "")),
              f"label={(_lk or {}).get('label')!r} (innerText alone gives just 'opened')")
        _txt = await tp.evaluate("(function(){ " + DOMTEXT + "; return _domTextPage(); })()")
        # The noise gate here used to be `t.length > 8` — a chosen number, and the
        # shortest strings on a page are often the ANSWER. It is now "does this
        # contain a letter or a digit, in any script", so a private-use icon glyph
        # is still excluded with no length involved.
        check("S13b short shadow-only text (a vote count) is no longer dropped by a"
              " length threshold",
              "1,204" in _txt, f"present={'1,204' in _txt}")
        check("S13c ...while a private-use icon glyph is still excluded",
              "" not in _txt, f"leaked={chr(0xf002) in _txt}")
        await tp.close()

        await browser.close()

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())

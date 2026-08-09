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
        await browser.close()

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())

"""Widget-zoo regression suite — the shapes that fixture-green changes got WRONG live.

Motivation: twice in one session a change passed every gap check and broke a real page
(a dead-duplicate detector that never fired on select2; an aria-controls scoping change
that emptied select2's option pool). Both surprises lived in the same neighbourhood:
aria-controls resolution, popover shape, and what counts as a widget's backing control.
This suite reproduces those shapes offline and asserts behaviour, so the next change in
that area is caught here instead of on a live page.

Runs the REAL page-side functions extracted from extension/background.js, same technique
as test_gaps.py. PASS/FAIL (unlike test_gaps.py, which is an inventory).

Run:  python tools/test_widgets.py
"""

import asyncio
import json
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
PICK = extract("_pickOptionPage")
TYPESEARCH = extract("_typeIntoOpenPopoverSearchPage")
COUNTOPTS = extract("_countVisibleOptionsPage")
DETECTSUBMIT = extract("_detectSubmitPage")
DOMTEXT = extract("_domTextPage")

results = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


async def main():
    url = (ROOT / "tools" / "widget_zoo.html").as_uri()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 1600})
        await page.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await page.goto(url)
        await page.wait_for_timeout(250)

        raw = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")

        def by_label(sub):
            return [e for e in raw if sub in json.dumps(e, default=str)]

        # ---- W1 / W1b: a CSRF token and a visible sibling input are NOT backing controls
        w1 = [e for e in raw if (e.get("label") or "") == "Choose a plan"]
        check("W1 hidden CSRF token is not adopted as a backing control",
              bool(w1) and not w1[0].get("backedBy"),
              f"backedBy={w1[0].get('backedBy') if w1 else 'ENTRY MISSING'}")
        check("W1 unfilled custom select still flagged (unselected)",
              bool(w1) and bool(w1[0].get("unselected")),
              f"unselected={w1[0].get('unselected') if w1 else None}")
        w1b = [e for e in raw if (e.get("label") or "") == "Unit"]
        check("W1b visible sibling input is not adopted as a backing control",
              bool(w1b) and not w1b[0].get("backedBy"),
              f"backedBy={w1b[0].get('backedBy') if w1b else 'ENTRY MISSING'}")

        # ---- W1c: a genuine hidden <select> IS recognised, and suppresses (unselected)
        w1c = [e for e in raw if (e.get("label") or "") == "Alaska" and e.get("role") == "combobox"]
        check("W1c genuine hidden <select> recognised as backing (backed-by emitted)",
              bool(w1c) and bool(w1c[0].get("backedBy")),
              f"backedBy={w1c[0].get('backedBy') if w1c else 'ENTRY MISSING'}")
        check("W1c backed widget with a value is NOT flagged (unselected)",
              bool(w1c) and not w1c[0].get("unselected"),
              f"unselected={w1c[0].get('unselected') if w1c else None}")

        # ---- W2: the real search input wins over a leading "select all" checkbox
        r = await page.evaluate("(function(){ " + TYPESEARCH +
                                "; return _typeIntoOpenPopoverSearchPage('Ontario', '#w2-trigger'); })()")
        cb = await page.evaluate("document.getElementById('w2-all').checked")
        sv = await page.evaluate("document.getElementById('w2-search').value")
        check("W2 popover search picks the search input, not the first checkbox",
              bool(r and r.get("ok")) and sv == "Ontario" and cb is False,
              f"ok={r and r.get('ok')} search={sv!r} checkboxChecked={cb}")

        # ---- W10: the widening walk must not type into a DIFFERENT field
        await page.evaluate("document.getElementById('w10').style.display = 'block'")
        r10 = await page.evaluate("(function(){ " + TYPESEARCH +
                                 "; return _typeIntoOpenPopoverSearchPage('Heathrow', '#w10-trigger'); })()")
        v10 = await page.evaluate("document.getElementById('w10-other').value")
        await page.evaluate("document.getElementById('w10').style.display = 'none'")
        check("W10 a picker with no filter input refuses to type into a peer field",
              bool(r10) and r10.get("ok") is False and not v10,
              f"ok={r10 and r10.get('ok')} peerFieldValue={v10!r} msg={(r10 or {}).get('msg','')[:78]!r}")
        check("W10b ...and names the field it declined to touch",
              "Where else?" in ((r10 or {}).get("msg") or ""),
              f"msg={(r10 or {}).get('msg','')[:96]!r}")

        # ---- W3: aria-controls names the listbox; the sibling filter input must be found
        r3 = await page.evaluate("(function(){ " + TYPESEARCH +
                                 "; return _typeIntoOpenPopoverSearchPage('Grace', '#w3-trigger'); })()")
        f3 = await page.evaluate("document.getElementById('w3-filter').value")
        check("W3 filter input beside the aria-controls listbox is still reachable",
              bool(r3 and r3.get("ok")) and f3 == "Grace",
              f"ok={r3 and r3.get('ok')} filter={f3!r} msg={(r3 or {}).get('msg','')[:60]!r}")

        # ---- W4: foreign always-visible options must not make a closed combobox look open
        c4 = await page.evaluate("(function(){ " + COUNTOPTS +
                                 "; return _countVisibleOptionsPage('#w4-trigger'); })()")
        check("W4 foreign visible listbox does not inflate the option count",
              c4 == 0, f"count={c4} (expected 0 — w4's own popover is display:none)")

        # ---- W5: aria-controls pointing at the selection box must be rejected as scope
        r5 = await page.evaluate("(function(){ " + PICK +
                                 "; return _pickOptionPage('Gamma Option', '#w5-trigger'); })()")
        picked5 = await page.evaluate("window.__w5Picked || ''")
        check("W5 self-containing aria-controls rejected; picks a real option not a chosen tag",
              bool(r5 and r5.get("ok")) and picked5 == "Gamma Option",
              f"ok={r5 and r5.get('ok')} clicked={picked5!r} via={(r5 or {}).get('dbg',{}).get('via')}")

        # ---- W6: unrelated one-button dialog must not be chosen as the submit scope
        d6 = await page.evaluate("(function(){ " + DETECTSUBMIT +
                                 "; return _detectSubmitPage(\"#w6-field\"); })()")
        got_toast = bool(d6) and "Got it" in json.dumps(d6, default=str)
        check("W6 unrelated toast button is NOT returned as the submit target",
              not got_toast, f"detected={json.dumps(d6, default=str)[:80]}")

        # ---- W7: a clickable card with 2 inner buttons must survive the delegation drop
        w7 = [e for e in raw if "Deploy pipeline" in json.dumps(e, default=str)]
        check("W7 handler-only card with 2 inner buttons is not dropped as a delegation root",
              bool(w7), f"listed={bool(w7)}")

        # ---- W8: '#'-in-heading must survive the permalink strip
        txt = await page.evaluate("(function(){ " + DOMTEXT + "; return _domTextPage(); })()")
        # Assert against the OUTLINE section specifically, and by EXACT line. The first
        # version of this check used `"Working with C#" in txt`, which passed on the body
        # text and never looked at the outline at all — it would have stayed green with
        # the outline reading "Working with C" or "Working with C##".
        outline = txt.split("--- DOCUMENT OUTLINE")[-1] if "--- DOCUMENT OUTLINE" in txt else ""
        oline = next((l.strip() for l in outline.splitlines() if "Working with C" in l), "NOT FOUND")
        check("W8 heading 'Working with C#' keeps exactly one '#' in the outline",
              oline.endswith("h2: Working with C#"), f"outline line={oline!r}")

        # ---- W9: read_page ref_id ACTUALLY scopes to a subtree (was accepted + ignored) ----
        w9host = [e for e in raw if "Deploy pipeline" in json.dumps(e, default=str)
                  and e.get("tag") == "div"]
        if w9host:
            hid = w9host[0]["mmid"]
            scoped = await page.evaluate(
                "(function(){ " + COLLECT + "; return _collectInteractivePage(true, '" + hid + "'); })()")
            names = [(e.get("name") or e.get("label") or e.get("text") or "") for e in scoped]
            only_inside = all("pipeline" in n.lower() for n in names) and len(scoped) >= 2
            check("W9 ref_id scoping returns only the subtree's controls",
                  only_inside and len(scoped) < len(raw),
                  f"scoped={len(scoped)} of {len(raw)} -> {names[:4]}")
            check("W9 scoping excludes the host element itself",
                  all(e["mmid"] != hid for e in scoped))
        else:
            check("W9 ref_id scoping (host fixture present)", False, "W7 card missing")

        # ---- W10: an open dialog's TEXT reaches the listing (needed a screenshot before) ----
        await page.evaluate("""() => {
            const d = document.createElement('div');
            d.setAttribute('role','dialog'); d.setAttribute('aria-modal','true');
            d.style.cssText = 'position:fixed;left:10%;top:10%;width:80%;height:70%;background:#fff;border:1px solid #000;z-index:9999';
            d.innerHTML = '<h2>Confirm deletion</h2><p>This will permanently remove 3 items.</p><button>Cancel</button><button>Delete</button>';
            document.body.appendChild(d);
        }""")
        await page.wait_for_timeout(120)
        dlisting = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()")
        check("W10 open dialog's body text is in the listing",
              "Dialog text:" in dlisting and "permanently remove 3 items" in dlisting,
              next((l.strip()[:80] for l in dlisting.splitlines() if l.startswith("Dialog text:")), "ABSENT"))
        check("W10 dialog text excludes its buttons (already listed individually)",
              "Dialog text:" in dlisting and "Cancel" not in dlisting.split("Dialog text:")[1][:200])

        # ---- W11: open widget whose aria-controls target holds no options (select2) ----
        c11 = await page.evaluate("(function(){ " + COUNTOPTS +
                                  "; return _countVisibleOptionsPage('#w11-trigger'); })()")
        check("W11 open widget with a wrong-but-real aria-controls still counts its options",
              c11 >= 3, f"count={c11} (expected >=3; scoping the count to aria-controls returns 0)")
        r11 = await page.evaluate("(function(){ " + PICK +
                                  "; return _pickOptionPage('Hawaii', '#w11-trigger'); })()")
        check("W11 pick succeeds on that widget",
              bool(r11 and r11.get("ok")) and "Hawaii" in str(r11.get("actual")),
              f"ok={r11 and r11.get('ok')} actual={(r11 or {}).get('actual')!r}")

        await browser.close()

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} widget-zoo checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

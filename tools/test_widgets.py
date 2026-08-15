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
        # W1 USED TO ASSERT (unselected) HERE, on the strength of an English
        # wordlist. This trigger has NO structural placeholder signal: no
        # data-placeholder, no `placeholder` class token, no backing form control,
        # no trailing ellipsis — only the English words "Choose a plan". Measured
        # across 45 frozen sites with an interleaved drift control, the wordlist's
        # total effect on this flag was 14 against a drift floor of 14, i.e. noise;
        # its real cost was being a SOLE gate that works in the ~20 languages
        # somebody happened to list and silently fails in every other. Dropping the
        # flag here is the honest trade: `value="Choose a plan"` is what the page
        # renders, and the agent reads that as easily as we could have guessed it.
        check("W1 a text-only trigger reports what it displays, and does not GUESS"
              " placeholder state from an English wordlist",
              bool(w1) and not w1[0].get("unselected")
              and "Choose a plan" in json.dumps(w1[0], default=str),
              f"unselected={w1[0].get('unselected') if w1 else '?'}")
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

        # ---- W12: a DISABLED control must not vanish -----------------------
        # demoqa's City field: a react-select container with pointer-events:none
        # until a State is chosen, rendering the visible text "Select City". It was
        # dropped outright, so "there is no city field" and "the city field unlocks
        # after you pick a state" were the SAME output — and that is what let find()
        # answer a city query with the State field. The tag-list guard did not save
        # it because the wrapper is a <div>; the guard is now structural (an
        # aria-disabled wrapper, or one containing a real form control).
        dp = await browser.new_page(viewport={"width": 1200, "height": 800})
        await dp.set_content(
            "<!DOCTYPE html><meta charset=utf-8><body style='margin:0'>"
            "<div class='css-3iigni-container' style='pointer-events:none;"
            "width:400px;height:38px'><div class='css-16xfy0z-control'"
            " style='width:400px;height:38px'><div class='css-hlgwow'>"
            "<div class='css-1jqq78o-placeholder'>Select City</div>"
            "<div><input id=ci role=combobox disabled style='width:2px'></div>"
            "</div></div></div></body>")
        await dp.wait_for_timeout(150)
        drows = await dp.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        _city = next((e for e in drows if "Select City" in str(e.get("near") or "")), None)
        check("W12 a disabled custom control is still listed, not dropped as noise",
              bool(_city), f"entries={[(e.get('tag'), e.get('near')) for e in drows]}")
        check("W12b ...and its disabled state is stated, so 'absent' and 'locked'"
              " are distinguishable",
              bool(_city) and bool(_city.get("disabled")),
              f"disabled={(_city or {}).get('disabled')}")
        await dp.close()

        # ---- W13: a PROMPT option is not a chosen value ---------------------
        # "empty value means prompt" assumes the author wrote value=""; on older and
        # e-commerce widgets they usually did not. Amazon ships
        # <option value="-1">Select</option>, so a page whose own buy box reads "To
        # buy, select" reported value="Select" as a CHOSEN size — in German and
        # Japanese alike. Measured on real sites: THREE of four select-backed prompts
        # used a sentinel rather than an empty value, so this is the older-web norm.
        # Structural and language-independent: first option, and either a
        # conventional sentinel value or value===text while siblings use codes.
        sp = await browser.new_page(viewport={"width": 1200, "height": 800})
        await sp.set_content(
            "<!DOCTYPE html><meta charset=utf-8><body style='margin:0'>"
            "<select id=amz><option value='-1'>Select</option>"
            "<option value='B01'>32W / 32L</option><option value='B02'>34W</option></select>"
            "<select id=jp><option value='-1'>選択</option>"
            "<option value='C1'>M</option><option value='C2'>L</option></select>"
            "<select id=txt><option value='Open this select menu'>Open this select menu</option>"
            "<option value='1'>One</option><option value='2'>Two</option></select>"
            # NEGATIVE CONTROL: a genuinely pre-selected first option must NOT be
            # flagged, or every default-selected dropdown reads as empty.
            "<select id=real><option value='B01'>32W / 32L</option>"
            "<option value='B02'>34W</option><option value='B03'>36W</option></select>"
            "</body>")
        await sp.wait_for_timeout(140)
        sraw = await sp.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        sid = await sp.evaluate("""() => ({amz: amz.getAttribute('mmid'), jp: jp.getAttribute('mmid'),
            txt: txt.getAttribute('mmid'), real: real.getAttribute('mmid')})""")
        sby = {str(e.get("mmid")): e for e in sraw}
        for key, want, why in (
            ("amz", True, "a value='-1' sentinel prompt is unselected"),
            ("jp", True, "...in Japanese too, with no vocabulary involved"),
            ("txt", True, "...and a prompt whose value IS its own text"),
            ("real", False, "...while a real pre-selected first option is NOT flagged"),
        ):
            e = sby.get(str(sid.get(key))) or {}
            check(f"W13-{key} {why}", bool(e.get("unselected")) == want,
                  f"unselected={e.get('unselected')} value={e.get('value')!r}")
        await sp.close()

        # ---- W14: content that was invisible even to the DIAGNOSTIC ---------
        # Three drop paths were bare `return`s: they removed elements without
        # calling _drop, so `read_page(ledger=true)` — the tool whose entire job is
        # answering "why is this element missing?" — could not see them either.
        # Proven by a static audit with fixtures; these pin the fixes.
        gp = await browser.new_page(viewport={"width": 1200, "height": 800})
        await gp.set_content(
            "<!DOCTYPE html><meta charset=utf-8><body style='margin:0'>"
            # a media player's PRIMARY control, unlabelled and thin
            "<div role=slider tabindex=0 aria-valuenow=30"
            " style='width:600px;height:8px;background:#ccc'></div>"
            # an accordion expander bar: a real <button>, 400x12
            "<button style='width:400px;height:12px'><svg width=8 height=8></svg></button>"
            # ...but a labelless 10x200 anchor IS decoration (a splitter/rail)
            "<a href=# style='display:block;width:10px;height:200px'></a>"
            # [inert] is the W3C 'cannot be interacted with'; its counter existed
            # and could never increment, so this presented as fully clickable
            "<div inert><button>Wizard step 2</button></div>"
            "<button>Play</button></body>")
        await gp.wait_for_timeout(140)
        gl = await gp.evaluate("(function(){ " + COLLECT
                               + "; return _collectInteractivePage(true, null, 'compact', true); })()")
        _kept = [(e.get("tag"), e.get("role")) for e in (gl.get("elements") or [])]
        _rules = gl.get("byRule") or {}
        check("W14 an unlabelled role=slider seek bar is a control, not a sliver",
              ("div", "slider") in _kept, f"kept={_kept}")
        check("W14b ...and a thin real <button> expander is too",
              sum(1 for t, _ in _kept if t == "button") == 2, f"kept={_kept}")
        check("W14c ...while a labelless 10x200 <a> is still dropped AND recorded",
              _rules.get("sliver-decoration") == 1, f"byRule={_rules}")
        check("W14d an [inert] region's controls are dropped and COUNTED",
              _rules.get("inert") == 1, f"byRule={_rules}")
        await gp.close()

        await browser.close()

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} widget-zoo checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

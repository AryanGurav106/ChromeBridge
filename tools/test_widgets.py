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
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract as _shared_extract  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
try:
    # W13 prints a Japanese label. Without this the SUITE dies on cp1252 partway
    # through, which the runner reports as a failed suite — indistinguishable from
    # a real check failure, and it cost a diagnosis. Every other suite has this.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
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
CLICKP = extract("_clickPage")
EFFECT = extract("_clickEffectPage")
TYPESEARCH = extract("_typeIntoOpenPopoverSearchPage")
COUNTOPTS = extract("_countVisibleOptionsPage")
DETECTSUBMIT = extract("_detectSubmitPage")
DOMTEXT = extract("_domTextPage")
TYPETEXT = extract("_enterTextPage")

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
        # W14c ASSERTED THE OLD POLICY. A labelless 10x200 anchor is still judged
        # decoration — but that judgement is an aspect ratio, so it now sets
        # PROMINENCE, not existence: the row is kept, addressable, and folded into
        # the PROBABLY DECORATION line. A heuristic whose accuracy on an unseen site
        # is unknowable must never decide whether an element exists for the agent.
        _spl = next((e for e in (gl.get("elements") or [])
                     if e.get("tag") == "a" and (e.get("w") or 0) <= 12), None)
        check("W14c a labelless 10x200 <a> is DEMOTED, not deleted",
              bool(_spl) and str(_spl.get("demoted") or "").startswith("was:"),
              f"demoted={(_spl or {}).get('demoted')!r} byRule={_rules}")
        check("W14d an [inert] region's controls are dropped and COUNTED",
              _rules.get("inert") == 1, f"byRule={_rules}")
        await gp.close()

        # ---- W15: a DISABLED control still exists ------------------------------
        # The most-reported false negative in the project: ~6 live agents across two
        # fan-outs found demoqa's City field absent from the listing, from find, and
        # from the decoration tier, because a react-select disabled until State is
        # chosen is a pointer-events:none wrapper around a disabled 4px input, and
        # `isInteractive` asks "can this be operated" -- the wrong question for
        # existence. The consequence is the dangerous kind: "this form has no City
        # field" and "the City field unlocks once you pick a State" were the same
        # output, which is also what let find answer a city query with the State field.
        dp = await browser.new_page(viewport={"width": 900, "height": 700})
        await dp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # A NEW DOCUMENT IS REQUIRED HERE. add_init_script only affects documents
        # created AFTER it, and set_content reuses the existing about:blank — so
        # without this goto, listener_tag.js never runs and every fixture below is
        # testing an untagged page. Found while adding S14: the attachShadow wrap
        # read as broken when it was the harness that was. C13 now enforces it.
        await dp.goto("about:blank")
        await dp.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'><form>"
            "<label>State</label>"
            "<div style='width:419px;height:38px'><div>Select State</div>"
            "<input id=st style='width:4px;height:24px'></div>"
            "<label>City</label>"
            "<div id=cw style='width:419px;height:38px;pointer-events:none'><div>Select City</div>"
            "<input id=cty disabled style='width:4px;height:24px'></div>"
            "<button type=submit>Submit</button></form></body>")
        await dp.wait_for_timeout(150)
        _st = await dp.evaluate("(function(){ " + COLLECT
                                + "; return _collectInteractivePage(true,null,'compact',false,false); })()")
        _lst = await dp.evaluate("(function(){ " + COLLECT
                                 + "; return _collectInteractivePage(false,null,'compact',false,false); })()")
        _cty = await dp.evaluate(
            "()=>document.getElementById('cty').getAttribute('mmid')")
        _e = next((e for e in _st if str(e.get("mmid")) == str(_cty)), None)
        check("W15 a disabled form control is COLLECTED, not deleted",
              _e is not None, f"city input mmid={_cty} present={_e is not None}")
        check("W15b ...flagged (disabled), so 'absent' and 'switched off' differ",
              bool(_e) and _e.get("disabled") is True
              and any("Select City" in l and "(disabled)" in l for l in _lst.splitlines()),
              next((l.strip() for l in _lst.splitlines() if "Select City" in l), "NOT IN LISTING"))
        # The rescue must not turn containers into controls: an earlier version kept
        # anything CONTAINING a form control, so <html>/<body>/<form> and every
        # wrapper became clickable targets and actions resolved to them.
        _wrap = await dp.evaluate("()=>document.getElementById('cw').getAttribute('mmid')")
        _forms = [e for e in _st if e.get("tag") in ("html", "body", "form")]
        check("W15c ...and no container was promoted to a control",
              not _forms and not any(str(e.get("mmid")) == str(_wrap) and not e.get("demoted")
                                     for e in _st),
              f"containers listed={[e.get('tag') for e in _forms]}")
        # W15d: `(disabled)` MEANS THE PAGE SAID DISABLED. The State side of this
        # same fixture is the control: its wrapper has no pointer-events:none and its
        # input has no disabled attribute, so nothing about it may carry the flag.
        # The bug this pins inferred (disabled) from pointer-events:none, which
        # component libraries put on the REAL control while routing clicks through a
        # wrapping label. Two live agents proved it wrong by acting: Bootstrap's
        # checks-radios page flagged 18 `.btn-check` rows when only 4 carry the
        # attribute, and clicking one flipped its .checked false->true; on Vuetify the
        # flag landed on the children of a `(current)` link and a `(selected)` tab,
        # and on a ref that accepted a successful form_input seconds later. A wrong
        # (disabled) tells the agent NOT to act, and it also voids the marker where
        # it is right — W15b's City field uses the identical token.
        await dp.close()

        # REQUIRED SHAPE: pointer-events:none on the NATIVE CONTROL ITSELF, with a
        # <label for> routing the click — this is Bootstrap's `.btn-check`, which
        # clips the input to rect(0,0,0,0) and styles the label as the button. Do NOT
        # "simplify" this by moving pointer-events onto a wrapper div: the first
        # version of this fixture did that and passed pre-fix, because the wrapper
        # never carried the flag. The real defect only appears when the control the
        # agent must act on is the one with pointer-events:none.
        bp = await browser.new_page(viewport={"width": 900, "height": 700})
        await bp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # A NEW DOCUMENT IS REQUIRED HERE. add_init_script only affects documents
        # created AFTER it, and set_content reuses the existing about:blank — so
        # without this goto, listener_tag.js never runs and every fixture below is
        # testing an untagged page. Found while adding S14: the attachShadow wrap
        # read as broken when it was the harness that was. C13 now enforces it.
        await bp.goto("about:blank")
        await bp.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<input type=checkbox id=live style='pointer-events:none;width:16px;height:16px'>"
            "<label for=live style='display:inline-block;width:120px;height:30px'>Bold</label>"
            "<input type=checkbox id=dead disabled style='width:16px;height:16px'>"
            "<label for=dead style='display:inline-block;width:120px;height:30px'>Locked</label>"
            "</body>")
        await bp.wait_for_timeout(150)
        _bst = await bp.evaluate("(function(){ " + COLLECT
                                 + "; return _collectInteractivePage(true,null,'compact',false,false); })()")
        _mm = await bp.evaluate("()=>({live:document.getElementById('live').getAttribute('mmid'),"
                                "dead:document.getElementById('dead').getAttribute('mmid')})")
        _lv = next((e for e in _bst if str(e.get("mmid")) == str(_mm["live"])), None)
        _dd = next((e for e in _bst if str(e.get("mmid")) == str(_mm["dead"])), None)
        check("W15d (disabled) is NEVER inferred from pointer-events:none — a"
              " Bootstrap .btn-check style control is operable and must not be flagged",
              _lv is not None and _lv.get("disabled") is not True,
              f"present={_lv is not None} disabled={(_lv or {}).get('disabled')} "
              f"(clicking one of these live flipped .checked false->true)")
        check("W15e ...and the DECLARED disabled twin beside it still is flagged,"
              " so the marker keeps its meaning",
              _dd is not None and _dd.get("disabled") is True,
              f"present={_dd is not None} disabled={(_dd or {}).get('disabled')}")
        await bp.close()

        # ---- W18: value= belongs to the FIELD, not to its neighbours ----------
        # The input-combobox hoist reads the displayed selection off a sibling node,
        # which is right for Ant/select2/Chosen and was unbounded in three ways:
        #  - a DECLARED LIVE REGION counted as contents. Stack Overflow's search
        #    reported value="Loading…" while the field was empty. A node marked
        #    aria-live / role=status / role=alert / <output> has SAID it is transient
        #    announcement text, so no vocabulary is needed to exclude it.
        #  - HELP AND ERROR TEXT was excluded by matching the English substrings
        #    "helper" and "error" against author-chosen class names, so a German
        #    "fehlertext" matched nothing and the prose landed in value=. HTML
        #    already carries the association: aria-describedby / aria-errormessage.
        #  - the WALK HAD NO BOUNDARY. Two hops reach <body> on a shallow page, so
        #    the whole page's text could become a field's value; only a
        #    `length <= 60` test stood in the way, and it held merely because most
        #    pages have more than 60 characters in them.
        vp = await browser.new_page(viewport={"width": 900, "height": 700})
        await vp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # A NEW DOCUMENT IS REQUIRED HERE. add_init_script only affects documents
        # created AFTER it, and set_content reuses the existing about:blank — so
        # without this goto, listener_tag.js never runs and every fixture below is
        # testing an untagged page. Found while adding S14: the attachShadow wrap
        # read as broken when it was the harness that was. C13 now enforces it.
        await vp.goto("about:blank")
        await vp.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<div style='width:300px'><input id=so role=combobox aria-label=Search"
            " style='width:280px;height:28px'>"
            "<div role=status aria-live=polite style='width:280px;height:18px'>Loading&hellip;</div></div>"
            "<div style='width:300px'><input id=de role=combobox aria-label=Genre"
            " aria-describedby=hilfe style='width:280px;height:28px'>"
            "<div id=hilfe style='width:280px;height:18px'>W&auml;hlen Sie einen Titel</div></div>"
            "<div style='width:300px'><input id=ok role=combobox aria-label=City"
            " style='width:280px;height:28px'>"
            "<span style='display:inline-block;width:120px;height:18px'>Reykjav&iacute;k</span></div>"
            "</body>")
        await vp.wait_for_timeout(160)
        _vst = await vp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        _vm = await vp.evaluate(
            "()=>['so','de','ok'].map(i=>document.getElementById(i).getAttribute('mmid'))")

        def _val(i):
            e = next((x for x in _vst if str(x.get("mmid")) == str(i)), None)
            return (e or {}).get("value") or ""

        check("W18 a declared live region is never a field's value",
              _val(_vm[0]) == "", f"value={_val(_vm[0])!r} (was 'Loading…')")
        check("W18b help text is excluded by aria-describedby, not by an English"
              " class-name substring",
              _val(_vm[1]) == "", f"value={_val(_vm[1])!r}")
        check("W18c ...while a real hoisted selection still comes through",
              _val(_vm[2]) == "Reykjavík", f"value={_val(_vm[2])!r}")
        await vp.close()

        # ---- W17: rc-select / Ant Design -- a DECOY declared listbox ----------
        # The worst dropdown failure on record (CLAUDE.md #25): the picker found
        # zero options and then offered the site's own NAV BAR as the field's
        # options. Two causes, both here:
        #   (a) the trigger's aria-controls points at a HIDDEN listbox while the
        #       real, role-less rows are painted in a separate portal. Honouring a
        #       declaration that names something the user cannot see found nothing.
        #   (b) with no scope, the role scan ran DOCUMENT-WIDE, and anything on the
        #       page carrying [aria-selected] or li[data-value] qualified -- here,
        #       three nav items.
        # The portal carries none of the three popover-library attribute names the
        # candidate list used to be built from, which is why a framework-name list
        # could never have reached it. rc-select powers antd, so this is a
        # framework FAMILY, not one site.
        ap = await browser.new_page(viewport={"width": 900, "height": 700})
        await ap.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # A NEW DOCUMENT IS REQUIRED HERE. add_init_script only affects documents
        # created AFTER it, and set_content reuses the existing about:blank — so
        # without this goto, listener_tag.js never runs and every fixture below is
        # testing an untagged page. Found while adding S14: the attachShadow wrap
        # read as broken when it was the harness that was. C13 now enforces it.
        await ap.goto("about:blank")
        await ap.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<nav><div aria-selected=true style='width:80px;height:24px;cursor:pointer'>Products</div>"
            "<div aria-selected=false style='width:80px;height:24px;cursor:pointer'>Pricing</div>"
            "<div aria-selected=false style='width:80px;height:24px;cursor:pointer'>Docs</div></nav>"
            "<div id=trig role=combobox aria-controls=decoy aria-expanded=true tabindex=0"
            " style='width:200px;height:32px;border:1px solid #999'>Select a size</div>"
            "<div id=decoy role=listbox aria-hidden=true style='display:none'></div>"
            "<div id=portal style='position:absolute;top:40px;left:0;width:200px;z-index:1050'><div>"
            "<div style='width:200px;height:26px;cursor:pointer'>Small</div>"
            "<div style='width:200px;height:26px;cursor:pointer'>Medium</div>"
            "<div style='width:200px;height:26px;cursor:pointer'>Large</div>"
            "</div></div></body>")
        await ap.wait_for_timeout(160)
        _ar = await ap.evaluate(
            "(function(){ " + PICK + "; return _pickOptionPage('Medium', '#trig'); })()")
        check("W17 a hidden declared listbox is a DECOY; the visible portal is the popup",
              bool(_ar.get("ok")) and _ar.get("actual") == "Medium",
              f"ok={_ar.get('ok')} actual={_ar.get('actual')!r} scope={_ar.get('dbg', {}).get('scope')!r}")
        check("W17b ...and the page's nav is never offered as the field's options",
              not any(w in (_ar.get("msg") or "") for w in ("Products", "Pricing", "Docs")),
              f"msg={(_ar.get('msg') or '')[:110]!r}")
        # W17c IS THE LIVE ANTD CASE, AND W17/W17b DO NOT COVER IT. There the portal
        # is POPULATED, so the harvest finds real rows and wins before the widened
        # document scan can do damage. On ant.design 6.6.1 the field's list had not
        # rendered at all (find() confirmed no Jack/Lucy/Tom anywhere), so the
        # harvest found nothing, the document-wide fallback stood, and the site
        # header's items were handed back as the field's options with
        # "Pass one of these exactly" — an instruction that navigates off the page.
        # Emptying the portal is the whole point of this fixture: with rows in it the
        # check passes for the wrong reason, which is what W17 had been doing.
        await ap.evaluate("()=>{document.getElementById('portal').innerHTML='';}")
        await ap.wait_for_timeout(60)
        _ae = await ap.evaluate(
            "(function(){ " + PICK + "; return _pickOptionPage('Medium', '#trig'); })()")
        check("W17c when the real list has NOT rendered, the answer is 'no options',"
              " never the page's own navigation",
              _ae.get("ok") is False
              and not any(w in (_ae.get("msg") or "") for w in ("Products", "Pricing", "Docs")),
              f"ok={_ae.get('ok')} msg={(_ae.get('msg') or '')[:130]!r}")
        await ap.close()

        # ---- W20: A DECLARED STATE CHANGE IS AN EFFECT ----------------------
        # The click op decided "did anything happen?" from {url, element count, text
        # length}, all blind to a control whose entire job is to flip a state flag.
        # That was not merely a missed report, it was a DESTRUCTIVE DOUBLE ACTION: no
        # detectable effect auto-escalates to a trusted retry, so the second click
        # undid the first and the op then reported failure — an odd number of
        # attempts works, an even number does not, indistinguishably. Demonstrated
        # before the fix on both shapes, fingerprint byte-identical either side of a
        # click that plainly worked.
        # The negative control is the point: a genuinely inert button must still read
        # as no-effect, or the escalation that exists for Radix/HeadlessUI triggers
        # (fix #1) stops firing where it is needed.
        cp = await browser.new_page(viewport={"width": 800, "height": 600})
        await cp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # A NEW DOCUMENT IS REQUIRED HERE. add_init_script only affects documents
        # created AFTER it, and set_content reuses the existing about:blank — so
        # without this goto, listener_tag.js never runs and every fixture below is
        # testing an untagged page. Found while adding S14: the attachShadow wrap
        # read as broken when it was the harness that was. C13 now enforces it.
        await cp.goto("about:blank")
        await cp.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<label><input type=checkbox id=cb style='width:16px;height:16px'> Email me</label>"
            "<button id=tg aria-pressed=false style='width:120px;height:28px'>Mute</button>"
            "<button id=inert style='width:120px;height:28px'>Does nothing</button>"
            "<script>document.getElementById('tg').addEventListener('click',function(){"
            "const p=this.getAttribute('aria-pressed')==='true';"
            "this.setAttribute('aria-pressed',p?'false':'true');});</script></body>")
        await cp.wait_for_timeout(130)
        await cp.evaluate("()=>{document.querySelectorAll('input,button')"
                         ".forEach((e,i)=>e.setAttribute('mmid',String(i+1)));}")

        async def _eff(sel):
            fb = await cp.evaluate("(function(){ " + EFFECT
                                   + "; return _clickEffectPage(\"" + sel + "\"); })()")
            await cp.evaluate("(function(){ " + CLICKP
                              + "; return _clickPage(\"" + sel + "\"); })()")
            await cp.wait_for_timeout(140)
            fa = await cp.evaluate("(function(){ " + EFFECT
                                   + "; return _clickEffectPage(\"" + sel + "\"); })()")
            return fb, fa, (fa.get("st") or "") != (fb.get("st") or "")

        _b1, _a1, _c1 = await _eff("[mmid='1']")
        check("W20 a checkbox click registers as an effect, so it is not clicked twice",
              _c1, f"st {_b1.get('st')!r} -> {_a1.get('st')!r}")
        _b2, _a2, _c2 = await _eff("[mmid='2']")
        check("W20b ...and so does an aria-pressed toggle",
              _c2, f"st {_b2.get('st')!r} -> {_a2.get('st')!r}")
        _b3, _a3, _c3 = await _eff("[mmid='3']")
        check("W20c ...while a genuinely inert button still reads as NO effect,"
              " so trusted escalation keeps working where fix #1 needs it",
              not _c3, f"st {_b3.get('st')!r} -> {_a3.get('st')!r}")
        await cp.close()

        # ---- W19: `near=` must be text a HUMAN CAN SEE -----------------------
        # The legend calls it "nearest visible text", and the sibling walk read
        # things nobody can see. `.textContent` on a COMMENT node returns the comment
        # body — unlike element.textContent, which excludes comment descendants — and
        # an element sibling's textContent includes display:none text. Found by an
        # independent audit, demonstrated live end to end: with
        # `<!-- promo code discount coupon --><input>`, find("promo code coupon
        # field") returned that input under `Found 1 element(s) matching`, so an
        # agent would type a promo code into a field whose only match is a
        # developer's comment. `near=` counts as CONTENT coverage in find's scorer,
        # which is what carries an invisible string into the confident results.
        np = await browser.new_page(viewport={"width": 900, "height": 700})
        await np.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # A NEW DOCUMENT IS REQUIRED HERE. add_init_script only affects documents
        # created AFTER it, and set_content reuses the existing about:blank — so
        # without this goto, listener_tag.js never runs and every fixture below is
        # testing an untagged page. Found while adding S14: the attachShadow wrap
        # read as broken when it was the harness that was. C13 now enforces it.
        await np.goto("about:blank")
        await np.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<div><!-- promo code discount coupon -->"
            "<input id=nc style='width:200px;height:24px'></div>"
            "<div><span style='display:none'>HIDDEN_LABEL_QRS</span>"
            "<input id=nh style='width:200px;height:24px'></div>"
            "<div>Visible Label<input id=nv style='width:200px;height:24px'></div>"
            # THE ZERO-AREA HOLE. checkVisibility() returns TRUE for a 0x0 box, so
            # this shape passed every filter and landed in near=. An audit injected
            # exactly it and then steered find() with the injected words under a
            # confident header — attacker-controlled text choosing the agent's target.
            "<div><span style='display:inline-block;width:0;height:0;overflow:hidden'>"
            "NIMBUS_DOCKET_ZZZ</span>"
            "<input id=nz style='width:200px;height:24px'></div>"
            "</body>")
        await np.wait_for_timeout(150)
        _nst = await np.evaluate("(function(){ " + COLLECT
                                 + "; return _collectInteractivePage(true); })()")
        _nm = await np.evaluate(
            "()=>({c:document.getElementById('nc').getAttribute('mmid'),"
            "h:document.getElementById('nh').getAttribute('mmid'),"
            "z:document.getElementById('nz').getAttribute('mmid'),"
            "v:document.getElementById('nv').getAttribute('mmid')})")

        def _near(key):
            e = next((x for x in _nst if str(x.get("mmid")) == str(_nm[key])), None)
            return (e or {}).get("near") or ""

        check("W19 near= does not report an HTML COMMENT as visible text",
              "promo" not in _near("c").lower(), f"near={_near('c')!r}")
        check("W19b ...nor display:none text",
              "HIDDEN_LABEL_QRS" not in _near("h"), f"near={_near('h')!r}")
        check("W19c ...nor ZERO-AREA text — checkVisibility() returns true for a 0x0"
              " box, which is the shape an audit used to steer find()",
              "NIMBUS_DOCKET_ZZZ" not in _near("z"), f"near={_near('z')!r}")
        check("W19d ...while a genuinely visible preceding label still works"
              " (the over-correction guard)",
              _near("v") == "Visible Label", f"near={_near('v')!r}")
        await np.close()

        # ---- W17d: A COMBOBOX'S OPTIONS ARE NEVER `menuitem` ------------------
        # ant.design's docs site, measured live: the picker for "Select a person"
        # offered "Components Overview", "Changelog v6.6.1", "Button", "FloatButton",
        # "Icon", "Typography", "Divider", "Flex" -- the SITE'S LEFT SIDEBAR, zero of
        # them the field's options -- under "Pass one of these exactly", an
        # instruction that navigates the agent off the page.
        #
        # THE SIDEBAR MUST BE INSIDE <main>, WITH NO LANDMARK ANYWHERE ON ITS CHAIN.
        # That is the real shape, and it is what defeated the previous guard: a list
        # of landmark elements and roles (nav/header/footer/aside + navigation/
        # menubar/banner/contentinfo). antd's chain is
        #     li[role=menuitem] -> ul[role=menu] -> div -> main -> body
        # so wrapping this fixture's menu in a <nav> would make it pass against the
        # old guard too, and prove nothing. The rule now used is a spec relationship:
        # ARIA's combobox pattern opens a listbox/tree/grid/dialog, never a menu, so a
        # menuitem is categorically not one of a combobox's values.
        mp = await browser.new_page(viewport={"width": 1000, "height": 800})
        await mp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # A NEW DOCUMENT IS REQUIRED HERE. add_init_script only affects documents
        # created AFTER it, and set_content reuses the existing about:blank — so
        # without this goto, listener_tag.js never runs and every fixture below is
        # testing an untagged page. Found while adding S14: the attachShadow wrap
        # read as broken when it was the harness that was. C13 now enforces it.
        await mp.goto("about:blank")
        await mp.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'><main>"
            "<ul role=menu style='position:sticky;z-index:1'>"
            + "".join(f"<li role=menuitem style='width:180px;height:24px;cursor:pointer'>"
                      f"Sidebar item {i}</li>" for i in range(6))
            + "</ul>"
            "<div id=ctl role=combobox aria-expanded=true tabindex=0"
            " style='width:200px;height:32px;border:1px solid #999'>Select a person</div>"
            "</main></body>")
        await mp.wait_for_timeout(150)
        _mr = await mp.evaluate(
            "(function(){ " + PICK + "; return _pickOptionPage('Beatrice', '#ctl'); })()")
        check("W17d a combobox is never offered `menuitem`s as its options, even when"
              " no landmark appears anywhere on their ancestor chain",
              _mr.get("ok") is False
              and not any(w in (_mr.get("msg") or "") for w in ("Sidebar item", "Sidebar")),
              f"ok={_mr.get('ok')} msg={(_mr.get('msg') or '')[:120]!r}")
        # And the converse: a menu-backed dropdown (Radix DropdownMenu style) declares
        # aria-haspopup="menu" on a button, and its menuitems ARE its options.
        await mp.evaluate("()=>{const c=document.getElementById('ctl');"
                         "c.setAttribute('role','button');"
                         "c.setAttribute('aria-haspopup','menu');}")
        _mr2 = await mp.evaluate(
            "(function(){ " + PICK + "; return _pickOptionPage('Sidebar item 3', '#ctl'); })()")
        check("W17e ...while a trigger declaring aria-haspopup=menu still picks a"
              " menuitem (the guard is a role relationship, not a ban)",
              _mr2.get("ok") is True and "Sidebar item 3" in str(_mr2.get("actual") or ""),
              f"ok={_mr2.get('ok')} actual={_mr2.get('actual')!r}")
        await mp.close()

        # ---- W16: which tab is selected, decided by DECLARATIONS -------------
        # `(current)/(selected)` tells the agent "already active; don't re-click",
        # so a wrong one suppresses a real action. It used to be answered, after
        # every ARIA signal, by an active|selected|current CLASS TOKEN — the only
        # wordlist left in the state path. ARIA's own tab pattern declares two
        # better signals and neither was used: the selected tab's aria-controls
        # panel is the rendered one, and the pattern specifies tabindex="0" on the
        # active tab with -1 on the others. None of the three tabsets below carries
        # aria-selected. The counter proves the fallback is reached ONLY by the
        # tabset that declares nothing — instrumentation, so the wordlist can be
        # deleted on evidence rather than on the argument.
        tp2 = await browser.new_page(viewport={"width": 900, "height": 700})
        await tp2.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # A NEW DOCUMENT IS REQUIRED HERE. add_init_script only affects documents
        # created AFTER it, and set_content reuses the existing about:blank — so
        # without this goto, listener_tag.js never runs and every fixture below is
        # testing an untagged page. Found while adding S14: the attachShadow wrap
        # read as broken when it was the harness that was. C13 now enforces it.
        await tp2.goto("about:blank")
        await tp2.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<div role=tablist><div role=tab aria-controls=pa style='width:90px;height:26px'>A-one</div>"
            "<div role=tab aria-controls=pb style='width:90px;height:26px'>A-two</div></div>"
            "<div id=pa style='width:200px;height:20px'>panel a</div>"
            "<div id=pb style='display:none'>panel b</div>"
            "<div role=tablist><div role=tab tabindex=0 style='width:90px;height:26px'>B-one</div>"
            "<div role=tab tabindex=-1 style='width:90px;height:26px'>B-two</div></div>"
            "<div role=tablist><div role=tab class='tab active' style='width:90px;height:26px'>C-one</div>"
            "<div role=tab class=tab style='width:90px;height:26px'>C-two</div></div></body>")
        await tp2.wait_for_timeout(150)
        _t = await tp2.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        _act = {}
        for e in _t:
            lab = (e.get("label") or e.get("name") or "").strip()
            if lab[:2] in ("A-", "B-", "C-"):
                _act[lab] = e.get("active") or ""
        check("W16 aria-controls panel visibility decides the selected tab",
              _act.get("A-one") == "selected" and _act.get("A-two") == "",
              f"A-one={_act.get('A-one')!r} A-two={_act.get('A-two')!r}")
        check("W16b roving tabindex (0 here, -1 on a sibling) decides it too",
              _act.get("B-one") == "selected" and _act.get("B-two") == "",
              f"B-one={_act.get('B-one')!r} B-two={_act.get('B-two')!r}")
        # W16c WAS the instrumentation gate and is now the DELETION gate, the same
        # role W1 took when #24 deleted the placeholder wordlist. The tabset "C"
        # declares nothing — no aria-selected, no aria-controls, no roving tabindex,
        # only `class="tab active"` — and the honest output is therefore NO state
        # marker at all. Measured before deleting: ablated across 99 live pages with
        # a per-page drift floor, the class token's total effect on the `active`
        # field was ZERO, on a corpus containing shadcn, chakra, antd, vuetify,
        # ng_material, bootstrap, headlessui, openui5 and react_aria — so the shape
        # is abundantly present and the two declared signals above were already
        # deciding every real case.
        # A class name is not a declaration: `active` is equally an animation state
        # or a "current-user" marker, and a WRONG (current) tells the agent not to
        # click the thing it needs — the failure class the fan-out measured directly
        # on `(disabled)`, where 18 Bootstrap rows were flagged inert and one was
        # clicked to prove otherwise.
        check("W16c a tabset that declares NOTHING gets no state marker — a class"
              " name is not a declaration",
              _act.get("C-one") == "" and _act.get("C-two") == "",
              f"C-one={_act.get('C-one')!r} C-two={_act.get('C-two')!r}"
              f" (both must be empty; the declared tabsets A and B are W16/W16b)")
        await tp2.close()

        # ---- W21: writing to something that cannot hold text ---------------------
        # `_enterTextPage` reported `Typed into ref_N` for any element it was handed,
        # and decided ok/failed by comparing the requested text against the element's
        # own inner text. On a non-field both halves are wrong: nothing is written,
        # and the readback check added in #23 — which exists to turn a false Success
        # into a failure — INVERTS into a false success whenever the element's own
        # label happens to contain the text. Live: form_input at a div reported
        # success for a write that never happened.
        #
        # THE DIV MUST CONTAIN THE TYPED STRING or this passes for the wrong reason:
        # the interesting case is not "we noticed it failed", it is "the readback
        # agreed with us".
        wp = await browser.new_page(viewport={"width": 800, "height": 600})
        await wp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # A NEW DOCUMENT IS REQUIRED HERE. add_init_script only affects documents
        # created AFTER it, and set_content reuses the existing about:blank — so
        # without this goto, listener_tag.js never runs and every fixture below is
        # testing an untagged page. Found while adding S14: the attachShadow wrap
        # read as broken when it was the harness that was. C13 now enforces it.
        await wp.goto("about:blank")
        await wp.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<div id=d onclick='void 0' style='width:300px;height:30px'>Search products</div>"
            "<button id=b style='width:120px;height:30px'>Go</button>"
            "<input id=i style='width:200px;height:24px'>"
            "</body>")
        await wp.wait_for_timeout(100)

        async def _type(sel, txt):
            return await wp.evaluate("(function(){ " + TYPETEXT + "; return _enterTextPage("
                                     + json.dumps(sel) + "," + json.dumps(txt) + "); })()")

        _rd = await _type("#d", "Search")
        check("W21 writing to an element that cannot hold text is refused, not"
              " reported as typed",
              _rd.get("ok") is False and "Typed into" not in (_rd.get("msg") or ""),
              f"ok={_rd.get('ok')} msg={(_rd.get('msg') or '')[:110]!r}")
        _rb = await _type("#b", "Go")
        check("W21b ...including a <button>, whose value property makes it look"
              " writable while typing into it does nothing",
              _rb.get("ok") is False and "Typed into" not in (_rb.get("msg") or ""),
              f"ok={_rb.get('ok')} msg={(_rb.get('msg') or '')[:90]!r}")
        # The negative control. Without it, refusing EVERYTHING would pass both
        # checks above while breaking the only thing this function is for.
        _ri = await _type("#i", "hello")
        check("W21c ...and a real text input still accepts the write",
              _ri.get("ok") is True and _ri.get("actual") == "hello",
              f"ok={_ri.get('ok')} actual={_ri.get('actual')!r}")
        await wp.close()

        # ---- W22-W25: what the DOCUMENT declares about a field, adopted from
        # browser-use's serializer. Every assertion below is about an attribute the
        # page wrote; none of it is inferred, so this stays inside the rule #27/#28
        # set for the existence path.
        #
        # NOT VACUOUS — verified by running each against the pre-change collector:
        # W22/W22b/W22c and W23 report `constraints`/`options` as None (the fields
        # did not exist), and W24 finds the literal secret inside the listing JSON.
        # W22d and W23b are the negative controls: without them, emitting the block
        # unconditionally would pass every positive check while taxing every row on
        # every page, which is the cost that has to stay at zero for pages that
        # declare nothing.
        cp = await browser.new_page(viewport={"width": 1280, "height": 900})
        await cp.set_content(
            "<form>"
            "<label for=zip>Postcode</label>"
            "<input id=zip name=ZIP pattern='[0-9]{5}' maxlength=5 inputmode=numeric required>"
            "<label for=dob>Date of birth</label>"
            "<input id=dob type=date min='2020-01-01' max='2030-12-31'>"
            "<label for=vol>Volume</label><input id=vol type=range min=0 max=11 step=1>"
            "<label for=pw>Password</label><input id=pw type=password value='hunter2-SECRET'>"
            "<label for=pw2>Confirm</label><input id=pw2 type=password>"
            "<label for=st>State</label>"
            "<select id=st><option>Alabama</option><option>Alaska</option><option>Arizona</option></select>"
            # W23d/W23e: the live shape -- a prompt option carrying BOTH `selected`
            # and `disabled`, so it is the load-time selection AND the one entry
            # that cannot be chosen. The <optgroup disabled> is the INHERITED case,
            # which `o.disabled` does not report and `:disabled` does.
            "<select id=pick aria-label='Pick one'>"
            "<option selected disabled>Please select an option</option>"
            "<option>Option 1</option>"
            "<optgroup disabled label='Later'><option>Option 2</option></optgroup>"
            "</select>"
            "<label for=plain>Nickname</label><input id=plain>"
            "</form>"
        )
        await cp.wait_for_timeout(120)
        craw = await cp.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        crow = await cp.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()")
        cjson = json.dumps(craw, default=str)

        def one(el_id):
            for e in craw:
                if (e.get("id") or "") == el_id or el_id in json.dumps(e, default=str):
                    return e
            return {}

        _zip = next((e for e in craw if (e.get("name") or "") == "Postcode"), {})
        check("W22 a pattern-guarded field publishes what it ACCEPTS"
              " (pattern/maxlength/inputmode), not just (required)",
              all(t in (_zip.get("constraints") or "")
                  for t in ("pattern=", "[0-9]{5}", "maxlength=5", "inputmode=numeric")),
              f"constraints={_zip.get('constraints')!r}")

        _dob = next((e for e in craw if (e.get("name") or "") == "Date of birth"), {})
        check("W22b a date input carries the WIRE format the HTML spec fixes for its"
              " type, which is not always what the widget displays",
              "format=YYYY-MM-DD" in (_dob.get("constraints") or "")
              and "min=2020-01-01" in (_dob.get("constraints") or ""),
              f"constraints={_dob.get('constraints')!r}")

        _vol = next((e for e in craw if (e.get("name") or "") == "Volume"), {})
        check("W22c a range input publishes its bounds and step",
              all(t in (_vol.get("constraints") or "") for t in ("min=0", "max=11", "step=1")),
              f"constraints={_vol.get('constraints')!r}")

        # NEGATIVE CONTROL. The whole argument for this feature is that it is free
        # on controls that declare nothing; an unconditional block would pass W22
        # and quietly add a tax to every row of every listing.
        _plain = next((e for e in craw if (e.get("name") or "") == "Nickname"), {})
        check("W22d ...and a field that declares no constraints emits NOTHING",
              bool(_plain) and not (_plain.get("constraints") or ""),
              f"constraints={_plain.get('constraints')!r}")

        _st = next((e for e in craw if (e.get("name") or "") == "State"), {})
        check("W23 a <select> publishes every option it declares, with a true count",
              "count=3" in (_st.get("options") or "")
              and all(t in (_st.get("options") or "") for t in ("Alabama", "Alaska", "Arizona")),
              f"options={_st.get('options')!r}")
        check("W23c ...each option quoted separately, because ' | ' occurs INSIDE real "
              "option text (python.org ships 'Greek | Ελληνικά')",
              '"Alabama"' in (_st.get("options") or "")
              and (_st.get("options") or "").strip().endswith("]"),
              f"options={_st.get('options')!r}")
        check("W23b ...and a non-select carries no option list",
              not (_zip.get("options") or ""),
              f"options={_zip.get('options')!r}")

        # A DISABLED OPTION IS DECLARED AND DECIDES WHAT A WRITE CAN DO. Live, a
        # prompt select printed `options=["Please select an option", "Option 1",
        # "Option 2"]` while the first was unselectable -- "which option cannot be
        # chosen" was unanswerable from the listing and cost a query_elements call.
        _pk = next((e for e in craw if (e.get("name") or "") == "Pick one"), {})
        _po = _pk.get("options") or ""
        check("W23d a disabled option is marked, and the mark is OUTSIDE the quotes "
              "so the text stays exactly what form_input must be passed",
              '"Please select an option" (disabled)' in _po, f"options={_po!r}")
        check("W23e ...including one disabled by its <optgroup>, which `o.disabled` "
              "does not report and `:disabled` does",
              '"Option 2" (disabled)' in _po, f"options={_po!r}")
        check("W23f CONTROL: a selectable option carries no mark — without this, "
              "marking every option would satisfy W23d/W23e and mean nothing",
              '"Option 1"' in _po and '"Option 1" (disabled)' not in _po,
              f"options={_po!r}")

        # W24 is the one check here that is about a secret rather than a convenience,
        # so it asserts over the WHOLE listing rather than one entry's value field —
        # a future hoist that carried the password onto a wrapper row would satisfy a
        # per-field assertion and still leak.
        check("W24 a filled password's contents appear NOWHERE in the listing",
              "hunter2-SECRET" not in cjson and "hunter2-SECRET" not in str(crow),
              f"leaked={'hunter2-SECRET' in cjson}")
        _pw = next((e for e in craw if (e.get("name") or "") == "Password"), {})
        _pw2 = next((e for e in craw if (e.get("name") or "") == "Confirm"), {})
        check("W24b ...but a filled password is still distinguishable from an empty"
              " one, because withholding both would report an occupied box as blank",
              "filled" in (_pw.get("value") or "") and not (_pw2.get("value") or ""),
              f"filled={_pw.get('value')!r} empty={_pw2.get('value')!r}")

        # THE RENDER IS A SEPARATE LINK, and CLAUDE.md #19 records `detail='brief'`
        # shipping with the collector correct and the row unchanged. Assert the text
        # the agent actually reads, not just the field behind it.
        check("W25 the rendered row carries them, not just the structured entry",
              "format=YYYY-MM-DD" in str(crow) and "count=3" in str(crow)
              and "maxlength=5" in str(crow),
              f"row_sample={str(crow)[:120]!r}")
        await cp.close()

        # ---- W26-W26d: (just appeared). browser-use marks novelty with a `*` prefix
        # computed from the previous step's node-id set; this is the same idea against
        # the mmid registry, and it is the one representational thing they had that we
        # answered only through `delta` — a MODE the agent must know to request, which
        # #30 found inert for its entire life. A per-row flag cannot fail silently.
        #
        # NOT VACUOUS — against the pre-change collector every one of these fails:
        # W26b finds no marker at all (the field did not exist). W26/W26c/W26d are the
        # controls that make the flag worth having: an always-on marker would pass
        # W26b and be pure noise, which is the #15 failure this suite exists to catch.
        np_ = await browser.new_page(viewport={"width": 1280, "height": 900})
        await np_.set_content(
            "<button id=go>Go</button><div id=slot></div>"
            "<script>document.getElementById('go').onclick=function(){"
            "document.getElementById('slot').innerHTML="
            "'<button id=fresh>Fresh action</button>';};</script>"
        )
        await np_.wait_for_timeout(100)
        CALL = "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"
        CALLS = "(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()"

        first = await np_.evaluate(CALL)
        check("W26 the FIRST read marks nothing — everything would qualify, and an"
              " always-on flag is noise the reader learns to skip",
              "just appeared" not in str(first),
              f"marked={'just appeared' in str(first)}")

        await np_.click("#go")
        await np_.wait_for_timeout(120)
        second = await np_.evaluate(CALL)
        check("W26b a control the click CREATED is flagged on the row that carries it",
              "Fresh action" in str(second) and "(just appeared)" in str(second),
              f"present={'(just appeared)' in str(second)}")

        # THE CONTROL THAT MATTERS. Marking the new button is easy; not marking the
        # button that was there all along is what makes the flag mean anything.
        _rows = [ln for ln in str(second).splitlines() if "ref_" in ln]
        _go = next((ln for ln in _rows if '"Go"' in ln), "")
        _fresh = next((ln for ln in _rows if "Fresh action" in ln), "")
        check("W26c ...and the pre-existing control is NOT flagged",
              bool(_go) and "just appeared" not in _go and "just appeared" in _fresh,
              f"go={_go[:70]!r}")

        # A re-read with nothing changed must go quiet again, or the flag decays into
        # a permanent decoration of whatever the last action happened to create.
        third = await np_.evaluate(CALL)
        check("W26d ...and a re-read with no further change goes quiet",
              "just appeared" not in str(third),
              f"still_marked={'just appeared' in str(third)}")

        # A SCOPED read must neither emit the flag nor poison the set: it collects one
        # subtree, so seeding from it would make the next whole-page read announce the
        # entire rest of the document as new.
        _sid = None
        for e in await np_.evaluate(CALLS):
            if "Fresh action" in json.dumps(e, default=str):
                _sid = e.get("mmid")
        scoped = await np_.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false, '" + str(_sid) + "'); })()")
        after = await np_.evaluate(CALL)
        check("W26e a scoped read neither flags nor poisons the seen-set",
              "just appeared" not in str(scoped) and "just appeared" not in str(after),
              f"scoped={'just appeared' in str(scoped)} after={'just appeared' in str(after)}")

        # W26f: THE FALSE POSITIVE THAT MADE THE FLAG LIE ABOUT THE DOM. `out` is
        # VIEWPORT-FILTERED on an unscoped string read, so nothing below the fold was
        # ever seeded and every such control was announced `(just appeared)` the
        # moment the page scrolled to it -- contradicting the flag's own contract,
        # that an element scrolling into view is not new. Measured on a page whose
        # form sits below the fold: mmids 6 and 7 are stamped at the FIRST read while
        # the seen-set holds 1 of 7.
        #
        # It was not merely noise. The flag firing on 17 form controls after a scroll
        # was taken as PROOF that they had not been in the DOM, which sent an
        # investigation at the readiness probe instead of here.
        sp = await browser.new_page(viewport={"width": 900, "height": 600})
        await sp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await sp.goto("about:blank")
        await sp.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<button id=top>Top button</button><div style='height:1600px'>spacer</div>"
            "<form><button id=below>Submit the form</button>"
            "<input id=name aria-label='Full name'></form></body>")
        await sp.wait_for_timeout(120)
        await sp.evaluate(CALL)                      # seeds, page at the top
        await sp.evaluate("window.scrollTo(0, 1700)")
        await sp.wait_for_timeout(120)
        scrolled = str(await sp.evaluate(CALL))
        check("W26f a control that was below the fold all along is NOT flagged when "
              "the page scrolls to it",
              "Submit the form" in scrolled
              and "(just appeared)" not in scrolled,
              f"rows={[l.strip() for l in scrolled.splitlines() if 'Submit' in l or 'Full name' in l]}")

        # THE CONTROL, on the same page: a genuinely created element must still be
        # flagged, or W26f could be satisfied by deleting the flag outright.
        await sp.evaluate("document.querySelector('form')"
                          ".insertAdjacentHTML('beforeend', '<button>Brand new</button>')")
        await sp.wait_for_timeout(80)
        after = str(await sp.evaluate(CALL))
        _row = lambda txt, body: next((l for l in body.splitlines() if txt in l), "")
        check("W26g CONTROL: a control created after that read IS still flagged, "
              "while the one that merely scrolled into view stays unflagged",
              "(just appeared)" in _row("Brand new", after)
              and "(just appeared)" not in _row("Submit the form", after),
              f"new={_row('Brand new', after).strip()!r} "
              f"old={_row('Submit the form', after).strip()!r}")
        await sp.close()
        await np_.close()

        # ---- Q1-Q7: search_page and query_elements, the two capabilities that had no
        # equivalent at all. NOT VACUOUS against the pre-change tree: both functions
        # did not exist, so every check below throws rather than fails.
        SEARCH = extract("_searchTextPage")
        QUERY = extract("_queryElementsPage")
        qp = await browser.new_page(viewport={"width": 1280, "height": 900})
        await qp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await qp.goto("about:blank")
        await qp.set_content(
            # A BASE URL IS REQUIRED FOR Q7. set_content lands on about:blank, which
            # has no path, so a relative href cannot be resolved and `el.href` hands
            # back the raw attribute — the property read would look broken while
            # being correct. This is the fixture stating what the page must have,
            # not a workaround.
            "<base href='https://example.test/shop/'>"
            "<main><h1>Order 4471</h1>"
            "<p>Your total is 249.99 EUR, shipped Tuesday.</p>"
            "<table><tr><td>Widget</td><td>19.99</td></tr>"
            "<tr><td>Gizmo</td><td>230.00</td></tr>"
            "<tr><td>Shipping</td><td>0.00</td></tr></table>"
            "<a href='/receipt.pdf'>Receipt</a><a href='/again'>Reorder</a>"
            "<p style='display:none'>SECRET hidden marker 9999</p>"
            # Q2b: visibility:hidden, which a BARE checkVisibility() does not
            # catch (#36). Harmless while the walk only skipped matches; load
            # bearing now that it BUILDS text, because an unrendered subtree would
            # otherwise contribute to its ancestors' context.
            "<p style='visibility:hidden'>PHANTOM marker 8888</p>"
            "<p>visible sibling <span style='visibility:hidden'>GHOSTWORD</span> tail</p>"
            # Q1c-Q1f: PROSE WITH INLINE MARKUP — the shape the own-text walk
            # mutilated. The <a> and <b> must sit INSIDE a sentence whose
            # remaining words are plain text nodes, because that is the only
            # arrangement where the old code produced a holed string; a link on
            # its own line was always findable and would make these vacuous.
            "<p id='prose'>The <a href='/m'>mole</a> is a <b>base unit</b> for "
            "amount of substance.</p>"
            # Two BLOCK children, so their text must not fuse into "alphabeta".
            "<ul><li>alpha</li><li>beta</li></ul>"
            "</main><footer><p>249.99 appears here too</p></footer>"
            "<div id=h></div>"
            "<script>var r=document.getElementById('h').attachShadow({mode:'closed'});"
            "r.innerHTML='<p>inside closed root: token ZX9</p>';</script>"
        )
        await qp.wait_for_timeout(150)

        async def search(pat, **kw):
            return await qp.evaluate(
                "(function(){ " + SEARCH + "; return _searchTextPage("
                + json.dumps(pat) + ", " + json.dumps(kw) + "); })()")

        async def query(sel, **kw):
            return await qp.evaluate(
                "(function(){ " + QUERY + "; return _queryElementsPage("
                + json.dumps(sel) + ", " + json.dumps(kw) + "); })()")

        r = await search("249.99")
        check("Q1 search_page finds text and returns the true total across the page",
              r.get("total") == 2 and any("249.99" in (h.get("context") or "") for h in r["hits"]),
              f"total={r.get('total')} hits={len(r.get('hits') or [])}")

        # CONTEXT MUST BEAT THE ELEMENT THE MATCH LIVES IN. Found live on a Wikipedia
        # GDP table: every hit was an <a> whose entire text was the match, so the
        # context window had nothing to add and three correct hits came back as three
        # bare words — on exactly the page shape ("where is the value") this tool is
        # for. The climb takes the nearest ancestor that contains MORE than the match.
        r = await search("Gizmo")
        check("Q1b a match that fills its own element takes context from the row above it",
              bool(r["hits"]) and "230.00" in r["hits"][0]["context"],
              f"context={r['hits'][0]['context']!r}" if r.get("hits") else "no hits")

        # ---- Q1c-Q1f: the own-text walk mutilated every sentence containing an
        # inline element. It collected DIRECT TEXT NODES ONLY and used that string
        # both to match against and to quote back, so Wikipedia's lead sentence
        # came back as "The (symbol ) is a , the in the (SI) for ." — every linked
        # term gone, no marker, still reading as a finished sentence. Measured at
        # 8-16% of text-bearing elements across five real pages. The ancestor climb
        # that would have repaired it is gated on the match FILLING its element,
        # which is exactly the case this is not.
        r = await search("for amount", contextChars=80)
        ctx = (r["hits"][0]["context"] if r.get("hits") else "")
        check("Q1c context keeps the words that sit in inline children",
              "mole" in ctx and "base unit" in ctx, f"context={ctx!r}")

        # A phrase that STRADDLES a text node and an element could not match at
        # all: "mole" lived in the <a> and " is a " in the parent's text, so
        # neither string ever contained the whole phrase.
        r = await search("mole is a")
        check("Q1d a phrase spanning an inline boundary is findable",
              r.get("total") == 1, f"total={r.get('total')}")

        # ATTRIBUTION IS UNCHANGED, and this is what proves the fix did not buy
        # correct text by reporting every match once per level of nesting (#32).
        r = await search("base unit")
        check("Q1e a match inside a child is still reported ONCE, by the child",
              r.get("total") == 1 and (r["hits"][0]["tag"] == "b"),
              f"total={r.get('total')} tag={r['hits'][0]['tag'] if r.get('hits') else None}")

        # SEPARATOR CONTROL. Joining children with nothing would fuse two block
        # siblings into "alphabeta" and invent a match that is on no screen.
        r = await search("alphabeta")
        check("Q1f block-level siblings do not fuse into a false match",
              r.get("total") == 0, f"total={r.get('total')}")

        # ---- Q1g/Q1h: CSS WHITE-SPACE IS A DECLARATION, AND `\n` MUST SURVIVE IT.
        # Every text node used to go through /\s+/g, so a <pre> came back as one
        # unbroken line. Measured live on an RFC: a regex ending `[^\n]*` matched
        # from its heading to the END OF THE DOCUMENT, because no newline survived
        # for it to stop at -- and the "context" was then the whole 26KB body no
        # matter how small context_chars was. Every RFC, man page and code block on
        # the web is a <pre>.
        pre = await browser.new_page(viewport={"width": 1280, "height": 1600})
        await pre.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await pre.goto("about:blank")
        await pre.set_content(
            "<!doctype html><meta charset=utf-8><body>"
            "<pre>5.2.  The 425 Status Code\nIntermediaries MUST forward it.</pre>"
            "<p>wrapped  prose   collapses   runs</p></body>")
        await pre.wait_for_timeout(150)

        async def psearch(pat, **kw):
            o = dict(regex=True, contextChars=40, **kw)
            return await pre.evaluate(
                "(function(){ " + SEARCH + "; return _searchTextPage("
                + json.dumps(pat) + ", " + json.dumps(o) + "); })()")

        r = await psearch(r"5\.2\.\s+The 425[^\n]*")
        hit = (r.get("hits") or [{}])[0].get("match", "")
        check("Q1g a newline-anchored regex stops at the <pre>'s own line break",
              r.get("total") == 1 and hit.strip() == "5.2.  The 425 Status Code",
              f"total={r.get('total')} match={hit[:70]!r}")
        # THE CONTROL: collapsing must still happen where the page did NOT declare
        # whitespace significant, or this fix would simply stop normalising prose.
        r = await psearch(r"wrapped prose collapses runs")
        check("Q1h CONTROL: ordinary prose still collapses its whitespace runs",
              r.get("total") == 1, f"total={r.get('total')}")
        await pre.close()

        # ---- Q1i-Q1m: THE CLIMB, which produced THREE separate live failures from
        # one condition. It fired only when `full.trim() === m[0].trim()` -- when the
        # match EXACTLY FILLED its element -- which is almost never true of the shape
        # it most needs to handle. A metadata block puts the label and a colon in one
        # element, so the match is one character short of filling it and the climb was
        # skipped: `<dt>Published:</dt>` searched for "Published" returned the bare
        # label at context_chars=300, and `<a>Errata-ID: 1543</a>` searched for "1543"
        # returned a 15-char window at context_chars=600. Both are how every spec
        # header and registry record on the web is marked up.
        meta = await browser.new_page(viewport={"width": 1280, "height": 900})
        await meta.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await meta.goto("about:blank")
        await meta.set_content(
            "<!doctype html><meta charset=utf-8><body>"
            "<dl><dt>Published:</dt><dd>2026-10-02</dd>"
            "<dt>Errata-ID: 1543</dt><dd>Verified</dd></dl>"
            # Q1j: declared columns. The climb used to reach the row and then quote
            # it through innerText with every boundary collapsed, so label, value and
            # rank arrived as `المساحة 1862 كم² (178)` -- one string a reader can take
            # for a single quantity.
            "<table><tr><td>Area</td><td>1862</td><td>(178)</td></tr></table>"
            # Q1k: two matches inside ONE element, with a context window bigger than
            # the element, so both windows cover all of it.
            "<pre>SIGQUIT      3           3\nSIGUSR1     10          30\n</pre>"
            # Q1n: THE OVER-CLIMB SHAPE. A short <a> inside a list item that carries
            # its own distinguishing metadata, inside a LONG list. The record is the
            # <li>; the <ul> is the collection. Measured live on two sites: the climb
            # walked to the collection and every hit quoted the same run of siblings,
            # costing 1-2 calls each. The list must be long enough that quoting it
            # would be obviously wrong.
            "<ul>"
            "<li><a href=/a>Alpha Report</a> <span>(edition 11, id 431)</span></li>"
            "<li><a href=/b>Beta Report</a> <span>(edition 22, id 432)</span></li>"
            "<li><a href=/c>Gamma Report</a> <span>(edition 33, id 433)</span></li>"
            "<li><a href=/d>Delta Report</a> <span>(edition 44, id 434)</span></li>"
            "</ul>"
            # Q1o-Q1q: THE UNDER-CLIMB, four live sightings in one eval. #43 set the
            # climb to one hop arguing "from a cell you reach the ROW" -- true only
            # when the match is a DIRECT text child of the cell, which real pages
            # almost never do. Wrap it in ANYTHING and one hop reaches the CELL, a
            # FIELD of the record. Each of these three is a verbatim live shape, and
            # each returned the label alone with the answer in the next cell.
            # Q1o: postgresql.org error-code table.
            "<table>"
            "<tr><td><code>serialization_failure</code></td><td>40001</td></tr>"
            "<tr><td><code>deadlock_detected</code></td><td>40P01</td></tr>"
            "</table>"
            # Q1p: httpd.apache.org module metadata -- the label is itself a LINK
            # inside a <th>, so the <th>'s whole text IS the match.
            "<table><tr><th><a href=/m>Module Identifier:</a></th>"
            "<td>info_module</td></tr></table>"
            # Q1q: html.spec.whatwg.org element metadata -- a <dl> whose <dt> wraps
            # a link. Two hops: the <dt> is a field, the <dl> is the record.
            "<dl><dt><a href=/cm>Content model</a></dt>"
            "<dd>Phrasing content, but there must be no meter element descendants.</dd>"
            "</dl>"
            "</body>")
        await meta.wait_for_timeout(150)

        async def msearch(pat, **kw):
            return await meta.evaluate(
                "(function(){ " + SEARCH + "; return _searchTextPage("
                + json.dumps(pat) + ", " + json.dumps(kw) + "); })()")

        r = await msearch("Published", contextChars=300)
        ctx = (r["hits"][0]["context"] if r.get("hits") else "")
        check("Q1i a label that NEARLY fills its element still reaches its value",
              "2026-10-02" in ctx, f"context={ctx!r}")

        r = await msearch("1543", contextChars=300)
        ctx = (r["hits"][0]["context"] if r.get("hits") else "")
        check("Q1i2 ...and so does a value sharing its element with a label",
              "Verified" in ctx, f"context={ctx!r}")

        r = await msearch("Area", contextChars=300)
        ctx = (r["hits"][0]["context"] if r.get("hits") else "")
        check("Q1j a row's declared columns are separated, not fused into one string",
              "Area | 1862 | (178)" in ctx, f"context={ctx!r}")

        # TWO MATCHES IN ONE ELEMENT MUST BE TELLABLE APART. Reported live as a
        # counting bug ("4 matches are 2 positions reported twice") and re-derived
        # offline as not one: the total was right every time and the two hits were
        # distinct. What was missing is that nothing said WHERE in the quoted window
        # each match sat, so two correct hits came back byte-identical and the agent
        # concluded the rows it wanted were absent -- when they were inside both
        # windows, unmarked.
        r = await msearch("SIGQUIT|SIGUSR1", regex=True, contextChars=120)
        hs = r.get("hits") or []
        check("Q1k two matches inside one element are distinguishable",
              r.get("total") == 2 and len(hs) == 2
              and hs[0].get("at") != hs[1].get("at")
              and all(h.get("at") is not None for h in hs),
              f"total={r.get('total')} ats={[h.get('at') for h in hs]}")
        check("Q1k2 ...and `at` really points at the match inside the quoted context",
              all(h["context"][h["at"]:h["at"] + len(h["match"])] == h["match"] for h in hs),
              "; ".join(f"at={h.get('at')} slice="
                        f"{h['context'][h.get('at', 0):h.get('at', 0) + len(h['match'])]!r}"
                        for h in hs))

        # THE INVARIANT THE COLUMN SEPARATOR MUST NOT BREAK: whatever is rendered
        # into the context, the match is still in there verbatim. A caller that
        # cannot find the match inside the text quoted back at it has to doubt both.
        bad = []
        for pat, kw in (("Published", {"contextChars": 300}), ("Area", {"contextChars": 300}),
                        ("1862", {"contextChars": 40}), ("Verified", {"contextChars": 200})):
            rr = await msearch(pat, **kw)
            for h in (rr.get("hits") or []):
                if h["match"] not in h["context"]:
                    bad.append(f"{pat}: {h['context']!r}")
        # Q1n/Q1n2: the climb stops at the RECORD, not the COLLECTION. One hop from
        # the <a> is the <li>, which carries the metadata that distinguishes this
        # entry from its siblings; two hops is the <ul>, which is every entry and
        # therefore identifies none of them.
        r = await msearch("Gamma Report", contextChars=300)
        ctx = (r["hits"][0]["context"] if r.get("hits") else "")
        check("Q1n a link in a list reaches its own record's metadata",
              "edition 33" in ctx and "id 433" in ctx, f"context={ctx!r}")
        check("Q1n2 ...and NOT the sibling records, which would identify nothing",
              "Alpha Report" not in ctx and "Delta Report" not in ctx, f"context={ctx!r}")

        # Q1o-Q1q: the climb reaches the RECORD even when the match is wrapped. All
        # three FAIL against the one-hop rule, which is what makes them worth having.
        r = await msearch("serialization_failure", contextChars=120)
        ctx = (r["hits"][0]["context"] if r.get("hits") else "")
        check("Q1o a match WRAPPED in a cell still reaches its row's other cells",
              "40001" in ctx, f"context={ctx!r}")
        # THE CONTROL that the record rule did not simply become the old 4-hop leak:
        # <tr> is the record, <table> is the collection, and the sibling ROW must not
        # appear -- otherwise a two-row lookup quotes an answer belonging to neither.
        check("Q1o2 CONTROL: ...and NOT the sibling row, which is a different record",
              "deadlock_detected" not in ctx and "40P01" not in ctx, f"context={ctx!r}")

        r = await msearch("Module Identifier", contextChars=300)
        ctx = (r["hits"][0]["context"] if r.get("hits") else "")
        check("Q1p a label that is a LINK inside a <th> reaches its value cell",
              "info_module" in ctx, f"context={ctx!r}")

        r = await msearch("Content model", contextChars=200)
        ctx = (r["hits"][0]["context"] if r.get("hits") else "")
        check("Q1q a <dt> wrapping a link reaches the <dd> beside it",
              "Phrasing content" in ctx, f"context={ctx!r}")

        check("Q1m CONTROL: context always contains the match verbatim",
              not bad, "; ".join(bad))
        await meta.close()

        # THE CONTROL THAT MAKES IT TRUSTWORTHY. A grep that reads hidden templates
        # answers "does this page say X" with text no user can see.
        r = await search("SECRET hidden marker")
        check("Q2 ...and does NOT match text the page is not rendering",
              r.get("total") == 0, f"total={r.get('total')}")

        r = await search("PHANTOM marker")
        check("Q2b ...including text hidden by visibility, not just display",
              r.get("total") == 0, f"total={r.get('total')}")

        # The sharper half: an invisible span INSIDE a visible sentence must not
        # reach that sentence's context either. A bare visibility test lets the
        # ancestor inherit text no one can see.
        r = await search("visible sibling", contextChars=60)
        _c = (r["hits"][0]["context"] if r.get("hits") else "")
        check("Q2c ...and an invisible child does not leak into a visible parent",
              "GHOSTWORD" not in _c, f"context={_c!r}")

        r = await search("token ZX9")
        check("Q3 ...and reaches inside a CLOSED shadow root",
              r.get("total") == 1, f"total={r.get('total')}")

        r = await search("[0-9]+\\.[0-9]{2}", regex=True, cssScope="table")
        check("Q4 regex + css_scope confine the search to one region",
              r.get("total") == 3, f"total={r.get('total')} (19.99, 230.00, 0.00)")

        r = await search("249.99", contextChars=5)
        check("Q5 context is bounded and marked when it is cut",
              bool(r["hits"]) and "…" in r["hits"][0]["context"]
              and len(r["hits"][0]["context"]) < 40,
              f"context={r['hits'][0]['context']!r}" if r.get("hits") else "no hits")

        r = await query("table tr")
        check("Q6 query_elements counts what the listing cannot — table rows",
              r.get("total") == 3, f"total={r.get('total')}")

        # COUNTING MUST SURVIVE THE CAP, or the one question this tool exists for
        # is the one it cannot answer on a big page.
        r = await query("td", maxResults=2)
        check("Q6b ...and the total is the TRUE count even when rows are capped",
              r.get("total") == 6 and r.get("shown") == 2,
              f"total={r.get('total')} shown={r.get('shown')}")

        r = await query("a", attributes=["href"])
        hrefs = [(x.get("attrs") or {}).get("href", "") for x in r["rows"]]
        # The count is coupled to the fixture (3 links: receipt, reorder, and the
        # one inside Q1c's prose sentence). The INVARIANT is the `startswith` —
        # every href resolved through the property, so a relative attribute like
        # '/m' comes back absolute rather than raw.
        check("Q7 attributes are read off the property, so href comes back absolute",
              len(hrefs) == 3 and all(h.startswith("http") for h in hrefs),
              f"hrefs={hrefs}")

        r = await query("th|||bad")
        check("Q7b an invalid selector is reported, not silently answered as 'none found'",
              bool(r.get("error")), f"error={r.get('error')!r}")

        # ---- Q9: include_text CROSSES A SHADOW BOUNDARY, like read_page does.
        # `innerText`/`textContent` both stop at the boundary, so a custom element
        # rendering its content inside its own shadow root came back as just its
        # light-DOM heading. read_page names the same element from the same content
        # (#29/SH1, extended in #37), so the two tools disagreed about one subtree
        # and the one that answers "what does this hold" was the wrong one. Found
        # live on caniuse -- the site #37 used to justify SH1 -- where a browser
        # support column read as "Safari" while it renders six version verdicts.
        shq = await browser.new_page(viewport={"width": 1000, "height": 700})
        await shq.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await shq.goto("about:blank")
        await shq.set_content(
            "<!doctype html><meta charset=utf-8><body>"
            "<div id=col><span>Safari</span></div>"
            "<script>"
            "const h=document.getElementById('col');"
            "const r=h.attachShadow({mode:'open'});"
            "r.innerHTML='<i>3.1 - 13.1 : Not supported</i><i>16.0 : Supported</i>';"
            "</script></body>")
        await shq.wait_for_timeout(120)
        rq = await shq.evaluate(
            "(function(){ " + QUERY + "; return _queryElementsPage('#col', "
            + json.dumps({"includeText": True}) + "); })()")
        txt = (rq["rows"][0].get("text") or "") if rq.get("rows") else ""
        check("Q9 include_text reads a host's SHADOW content, not just its light DOM",
              "16.0" in txt and "Supported" in txt, f"text={txt!r}")
        # THE CONTROL: an ordinary element is still read by innerText, which is what
        # keeps CSS-aware line breaking for the 99% case. The deep walk is a
        # fallback for what innerText cannot see, never a replacement (#29).
        rq = await shq.evaluate(
            "(function(){ " + QUERY + "; return _queryElementsPage('span', "
            + json.dumps({"includeText": True}) + "); })()")
        t2 = (rq["rows"][0].get("text") or "") if rq.get("rows") else ""
        check("Q9b CONTROL: a plain element's text is unchanged",
              t2 == "Safari", f"text={t2!r}")
        await shq.close()

        # ---- QB1-QB1d: PRESENT-AND-EMPTY IS NOT ABSENT.
        # `getAttribute` returns null for a missing attribute and "" for one present
        # with no value, and the attribute reader collapsed both into silence — so
        # asking for an attribute an element HAS printed nothing, which reads as a
        # negative. That is every HTML boolean (disabled/checked/selected/readonly/
        # required/multiple/hidden/open/...), because HTML serialises them as the bare
        # name. Measured live on Bootstrap's Disabled-forms example: `disabled` on the
        # checkbox that provably carries it returned nothing while `type` and `id`
        # printed normally, and a live agent read that as "no control carries its own
        # disabled attribute". QB1c is the other direction — an element WITHOUT the
        # attribute must still print nothing, or the fix has just inverted the lie.
        # A SEPARATE PAGE, not the shared fixture above: #14's lesson that adding to a
        # global fixture silently captures unrelated checks.
        qb = await browser.new_page(viewport={"width": 1280, "height": 900})
        await qb.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await qb.goto("about:blank")
        await qb.set_content(
            "<main>"
            "<input id=a type=text disabled>"
            "<input id=b type=checkbox checked>"
            "<input id=c type=text>"
            "<img id=d src='data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==' alt=''>"
            "<img id=e src='data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==' alt='A chart'>"
            "</main>")
        await qb.wait_for_timeout(150)

        async def qbq(sel, **kw):
            return await qb.evaluate(
                "(function(){ " + QUERY + "; return _queryElementsPage("
                + json.dumps(sel) + ", " + json.dumps(kw) + "); })()")

        r = await qbq("#a", attributes=["disabled", "type"], include_text=False)
        _at = (r["rows"][0].get("attrs") or {}) if r.get("rows") else {}
        check("QB1 a boolean attribute the element HAS is reported, not silently dropped",
              "disabled" in _at and _at.get("type") == "text", f"attrs={_at}")

        r = await qbq("#b", attributes=["checked"], include_text=False)
        _at = (r["rows"][0].get("attrs") or {}) if r.get("rows") else {}
        check("QB1b ...and the same for `checked`, the other most-asked boolean",
              "checked" in _at, f"attrs={_at}")

        r = await qbq("#c", attributes=["disabled"], include_text=False)
        _at = (r["rows"][0].get("attrs") or {}) if r.get("rows") else {}
        check("QB1c CONTROL: an element WITHOUT the attribute still reports nothing",
              "disabled" not in _at, f"attrs={_at}")

        # alt="" is the page DECLARING an image decorative. Collapsing it into "no alt"
        # erases the distinction the caller asked about, and it is not a boolean.
        r = await qbq("#d", attributes=["alt"], include_text=False)
        _d = (r["rows"][0].get("attrs") or {}) if r.get("rows") else {}
        r = await qbq("#e", attributes=["alt"], include_text=False)
        _e = (r["rows"][0].get("attrs") or {}) if r.get("rows") else {}
        check("QB1d an explicitly EMPTY alt (declared decorative) is distinguishable "
              "from a described image",
              "alt" in _d and _d.get("alt") == "" and _e.get("alt") == "A chart",
              f"decorative={_d} described={_e}")
        await qb.close()

        # Q8/Q8b: A RENDERED COUNT IS THE WRONG ANSWER when the page declares more.
        # Live defect: a record created seconds earlier was reported as absent because
        # the table showed "1 to 25 of 39" and the row was on page 2. ARIA declares this
        # (aria-rowcount / aria-setsize) and nothing else is read — no pagination control
        # is detected and no "Showing N of M" text is parsed, because those are a guess
        # and a wordlist. Q8b is the control: a table declaring nothing must NOT acquire
        # a warning, or every ordinary count grows a caveat that means nothing.
        await qp.goto("about:blank")
        await qp.set_content(
            "<table role='grid' aria-rowcount='39'><tbody>"
            + "".join(f"<tr role='row'><td>Row {i}</td></tr>" for i in range(4))
            + "</tbody></table>")
        await qp.wait_for_timeout(120)
        r = await query("tr[role=row]")
        check("Q8 a grid declaring aria-rowcount reports the declared total, not just "
              "what is rendered",
              r.get("total") == 4 and r.get("declaredTotal") == 39
              and r.get("declaredVia") == "aria-rowcount",
              f"total={r.get('total')} declared={r.get('declaredTotal')}")

        await qp.set_content(
            "<table><tbody>" + "".join(f"<tr><td>Row {i}</td></tr>" for i in range(4))
            + "</tbody></table>")
        await qp.wait_for_timeout(120)
        r = await query("tr")
        check("Q8b ...and a table that declares nothing gets no warning",
              r.get("total") == 4 and not r.get("declaredTotal"),
              f"total={r.get('total')} declared={r.get('declaredTotal')}")
        await qp.close()

        # ---- W27-W27c: <fieldset disabled> disables its DESCENDANTS.
        # `el.disabled` is the IDL reflection of the element's OWN attribute; HTML's
        # "actually disabled" state also covers every descendant of a disabled fieldset,
        # and `:disabled` is the selector implementing it. Found on Bootstrap's own
        # Disabled-forms example: of four controls inside one, `el.disabled` was true for
        # ONE — the checkbox with its own attribute — while the text input, the select
        # and THE SUBMIT BUTTON were all presented as live. The legend makes absence
        # load-bearing ("(disabled) — inert; clicking does nothing right now"), so an
        # agent had every reason to fill and submit a form where nothing lands.
        # W27c is the control: enabling the fieldset must clear every flag, or the rule
        # is just "always disabled" and means nothing.
        dp2 = await browser.new_page(viewport={"width": 1280, "height": 900})
        await dp2.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await dp2.goto("about:blank")
        FS = ("<form><fieldset {D}><legend>Group</legend>"
              "<label for=t>Text</label><input id=t>"
              "<label for=s>Pick</label><select id=s><option>One</option></select>"
              "<button type=submit>Send</button></fieldset></form>"
              "<label for=free>Outside</label><input id=free>")
        await dp2.set_content(FS.replace("{D}", "disabled"))
        await dp2.wait_for_timeout(140)
        off = str(await dp2.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false,null,'compact',false,false,'flat'); })()"))
        rows = {ln.split('|')[1].strip().split(' ')[0]: ln
                for ln in off.splitlines() if ln.startswith("ref_")}
        _txt = next((l for l in off.splitlines() if 'name="Text"' in l), "")
        _sub = next((l for l in off.splitlines() if '"Send"' in l), "")
        _out = next((l for l in off.splitlines() if 'name="Outside"' in l), "")
        check("W27 a control inside <fieldset disabled> is flagged (disabled), not "
              "presented as live",
              "(disabled)" in _txt, f"row={_txt.strip()[:80]}")
        check("W27b ...including the SUBMIT button, which is the one that costs most",
              "(disabled)" in _sub, f"row={_sub.strip()[:80]}")
        check("W27c ...while a control OUTSIDE the fieldset is not flagged",
              bool(_out) and "(disabled)" not in _out, f"row={_out.strip()[:80]}")

        # THE OTHER DIRECTION. A rule that flags everything is indistinguishable from
        # one that works, so the same markup with the fieldset ENABLED must be clean.
        await dp2.set_content(FS.replace(" {D}", ""))
        await dp2.wait_for_timeout(140)
        on = str(await dp2.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false,null,'compact',false,false,'flat'); })()"))
        check("W27d ...and with the fieldset enabled, nothing is flagged at all",
              "(disabled)" not in on, f"flags={on.count('(disabled)')}")
        await dp2.close()

        # ---- W28-W28d: READ-ONLY IS THE THIRD DECLARED WRITABILITY STATE, and it
        # was the one the listing never printed. It is NOT the same as disabled: a
        # readonly field still submits, still focuses, and its contents are real
        # contents — so an agent told only "(disabled) or nothing" cannot tell a
        # field it may read from one it may not. Found in the 10-task eval, where
        # the question "disabled or read-only?" could be half-answered from the
        # listing and needed query_elements for the rest.
        dp3 = await browser.new_page(viewport={"width": 1280, "height": 900})
        await dp3.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await dp3.goto("about:blank")
        await dp3.set_content(
            "<form>"
            "<label for=r>Locked</label><input id=r readonly value='kept text'>"
            "<label for=d>Off</label><input id=d disabled>"
            "<label for=n>Open</label><input id=n>"
            "<label for=a>Widget</label><div id=a role='textbox' aria-readonly='true'>x</div>"
            "</form>")
        await dp3.wait_for_timeout(140)
        ro = str(await dp3.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false,null,'compact',false,false,'flat'); })()"))
        _lock = next((l for l in ro.splitlines() if 'name="Locked"' in l), "")
        _off = next((l for l in ro.splitlines() if 'name="Off"' in l), "")
        _open = next((l for l in ro.splitlines() if 'name="Open"' in l), "")
        _wid = next((l for l in ro.splitlines() if 'name="Widget"' in l), "")
        check("W28 a readonly input is flagged (read-only)",
              "(read-only)" in _lock, f"row={_lock.strip()[:90]}")
        check("W28b ...and keeps its value, because readonly contents are real contents",
              "kept text" in _lock, f"row={_lock.strip()[:90]}")
        # A disabled field cannot be written EITHER, so printing both would read as
        # two separate obstacles when there is one.
        check("W28c a DISABLED field says (disabled) and not also (read-only)",
              "(disabled)" in _off and "(read-only)" not in _off, f"row={_off.strip()[:90]}")
        check("W28d a writable field is flagged neither (the negative control)",
              bool(_open) and "(read-only)" not in _open and "(disabled)" not in _open,
              f"row={_open.strip()[:90]}")
        check("W28e aria-readonly on a custom widget counts too",
              "(read-only)" in _wid, f"row={_wid.strip()[:90]}")
        check("W28f the legend names the notation, since it appears",
              "(read-only) —" in ro, "legend line absent")
        await dp3.close()

        # W28g: FOLDING MUST NOT DELETE THE STATE EITHER. Found live, immediately
        # after shipping the marker: identical sibling inputs fold, and the member
        # format carried (disabled) but not (read-only), so the listing read
        # `19:"Disabled input"(disabled) 21:"Readonly input"` and the second field
        # was indistinguishable from a writable one — while the legend, gated on the
        # flag being SET rather than PRINTED, still documented the notation.
        dp4 = await browser.new_page(viewport={"width": 1280, "height": 900})
        await dp4.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await dp4.goto("about:blank")
        await dp4.set_content(
            "<form>"
            "<label for=f1>A</label><input id=f1>"
            "<label for=f2>B</label><input id=f2 readonly value='v'>"
            "<label for=f3>C</label><input id=f3>"
            "<label for=f4>D</label><input id=f4>"
            "</form>")
        await dp4.wait_for_timeout(140)
        fold = str(await dp4.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false,null,'compact',false,false,'flat'); })()"))
        _line = next((l for l in fold.splitlines() if '"B"' in l), "")
        check("W28g a folded readonly member keeps its (read-only) flag",
              "(read-only)" in _line, f"line={_line.strip()[:140]}")
        await dp4.close()

        # ---- NP1-NP4: `name=` HAS THREE PROVENANCES AND THE ROW NAMED NONE.
        # It can be a real accessible name (title/alt, or a submit/reset input's
        # VALUE per HTML-AAM), or the HTML `name` attribute, which is not an
        # AccName source at all (#37) — it is the key the form posts under.
        # Measured live: <input type=reset name=submitbutton value=cancel> listed
        # as name="cancel" (correct — the value IS the name), indistinguishable
        # from the name-attribute fallback one row above, which cost an agent
        # three calls to disambiguate.
        np = await browser.new_page(viewport={"width": 1280, "height": 900})
        await np.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await np.goto("about:blank")
        await np.set_content(
            "<form>"
            "<input type=reset name=submitbutton value=cancel>"      # value IS the name
            "<input type=text name=username>"                        # name ATTRIBUTE fallback
            "<label for=lbl>Real Label</label><input id=lbl name=ignored>"  # a real label wins
            "</form>")
        await np.wait_for_timeout(140)
        npo = str(await np.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false,null,'compact',false,false,'flat'); })()"))
        _rst = next((l for l in npo.splitlines() if '"cancel"' in l), "")
        _usr = next((l for l in npo.splitlines() if '"username"' in l), "")
        _lbl = next((l for l in npo.splitlines() if '"Real Label"' in l), "")
        check("NP1 a name from the HTML name attribute is ATTRIBUTED as such",
              "(post-key)" in _usr, f"row={_usr.strip()[:120]}")
        # THE CONTROL THAT MAKES IT MEAN SOMETHING. A reset input's value IS its
        # accessible name per HTML-AAM, so it must NOT carry the marker — otherwise
        # the marker says nothing and every form row wears it.
        check("NP2 a reset input's VALUE is a real accessible name, so it is NOT marked",
              bool(_rst) and "(post-key)" not in _rst, f"row={_rst.strip()[:120]}")
        check("NP3 a properly labelled field is not marked either",
              bool(_lbl) and "(post-key)" not in _lbl, f"row={_lbl.strip()[:120]}")
        check("NP4 ...and the real label still wins over the name attribute",
              'name="Real Label"' in _lbl, f"row={_lbl.strip()[:120]}")
        check("NP4b the legend names the notation, since it appears",
              "(post-key) —" in npo, "legend line absent")
        await np.close()

        # NP5: FOLDING MUST NOT DELETE IT — third notation to need this rule, after
        # (read-only) and the state flags before it. Found live on eviltester, where
        # `10x input ... 1794:"username" 1798:"password"` carried POST keys as labels
        # with nothing saying so, while the loose rows above them were marked.
        np2 = await browser.new_page(viewport={"width": 1280, "height": 900})
        await np2.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await np2.goto("about:blank")
        await np2.set_content(
            "<form>" + "".join(f"<input type=text name=f{i}>" for i in range(6))
            + "<input type=reset name=submitbutton value=cancel>"
            + "<label for=L2>Proper Label</label><input id=L2 name=ignored></form>")
        await np2.wait_for_timeout(140)
        npf = str(await np2.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false,null,'compact',false,false,'flat'); })()"))
        _fold = next((l for l in npf.splitlines() if "\u00d7 input" in l), "")
        check("NP5 a folded POST-key member keeps its (post-key) marker",
              '"f0"(post-key)' in _fold, f"fold={_fold.strip()[:160]}")
        # The two controls that make the marker mean something, INSIDE the fold.
        check("NP5b ...while a folded reset keeps its VALUE-derived name unmarked",
              '"cancel"(post-key)' not in _fold, f"fold={_fold.strip()[:160]}")
        check("NP5c ...and a folded labelled field is unmarked too",
              '"Proper Label"(post-key)' not in _fold, f"fold={_fold.strip()[:160]}")
        await np2.close()

        # ---- LG1/LG1b: a legend line must describe the listing it is attached to.
        # `activeHint` returns pressed/active/open/on as well as the four the line used
        # to enumerate, so on habr the ONLY state token in the body was `(active)` while
        # the legend documented four notations that appeared nowhere. #13's `section=`
        # defect in a second place. LG1b is the control: the line must still name the
        # ordinary tokens when those are what is present.
        lgp = await browser.new_page(viewport={"width": 1280, "height": 900})
        await lgp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await lgp.goto("about:blank")
        await lgp.set_content("<main><button data-state='active'>Filter</button>"
                              "<button>Other</button></main>")
        await lgp.wait_for_timeout(120)
        _lg = str(await lgp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        _line = next((l for l in _lg.splitlines() if "already active" in l), "")
        check("LG1 the state legend names the token actually present, not a fixed four",
              "(active)" in _line and "(checked)" not in _line, f"legend={_line.strip()[:80]}")

        await lgp.set_content("<main><a href=/a aria-current='page'>Home</a>"
                              "<input type=checkbox checked><a href=/b>Other</a></main>")
        await lgp.wait_for_timeout(120)
        _lg2 = str(await lgp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        _line2 = next((l for l in _lg2.splitlines() if "already active" in l), "")
        check("LG1b ...and still names the ordinary tokens when those are the ones there",
              "(current)" in _line2 and "(checked)" in _line2 and "(active)" not in _line2,
              f"legend={_line2.strip()[:80]}")
        await lgp.close()

        # ---- AH1-AH3: the aria-hidden note must not PICK a cause.
        # Live on a real app it fired at 257 elements and concluded "Nothing here
        # indicates an open dialog, so this is most likely a CLOSED menu/panel" while
        # its own output listed an OPEN role=menu two rows below. Two bugs: dialogOpen
        # does not cover a menu, so the branch condition was wrong; and the note then
        # guessed. Same shape as #14's stale-ref message and #23's cross-extension one.
        # Pinned in BOTH directions, because a note that always claims an open popup
        # is as wrong as one that never does.
        AH_HIDDEN = ("<div aria-hidden='true'>"
                     "<button>Hidden alpha</button><button>Hidden beta</button>"
                     "<button>Hidden gamma</button><button>Hidden delta</button></div>")
        ahp = await browser.new_page(viewport={"width": 1280, "height": 900})
        await ahp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await ahp.goto("about:blank")
        await ahp.set_content(
            "<main><button>Real one</button><button>Real two</button>"
            "<div role='menu'><div role='menuitem'>Add investor</div>"
            "<div role='menuitem'>Add via CSV</div></div></main>" + AH_HIDDEN)
        await ahp.wait_for_timeout(150)
        with_menu = str(await ahp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        check("AH1 the note enumerates causes instead of selecting one",
              "most likely" not in with_menu and "(a)" in with_menu and "(b)" in with_menu,
              f"has_note={'aria-hidden' in with_menu} picks_one={'most likely' in with_menu}")
        check("AH2 ...and when an open menu IS listed, it says so",
              "open role=menu IS listed below" in with_menu,
              with_menu[with_menu.find("consistent with"):][:60] if "consistent with" in with_menu else "NOT NAMED")

        # THE CONTROL. Same drops, no popup on the page: the note must still appear
        # and must NOT claim something is open.
        await ahp.set_content(
            "<main><button>Real one</button><button>Real two</button>"
            "<button>Real three</button></main>" + AH_HIDDEN)
        await ahp.wait_for_timeout(150)
        no_menu = str(await ahp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        check("AH3 ...and with no popup on the page it claims none, while still noting the drop",
              "aria-hidden" in no_menu and "IS listed below" not in no_menu
              and "most likely" not in no_menu,
              f"claims_open={'IS listed below' in no_menu} has_note={'aria-hidden' in no_menu}")

        # AH4: A MENUBAR IS NOT AN OPEN MENU. Its items are permanently in the tree, so
        # they are not evidence that anything is open. Measured on vscode.dev, where this
        # clause — added by the AH1/AH2 fix — read the title-bar menubar as an open menu
        # and told the agent to dismiss something on a page with nothing open. The note
        # exists to stop exactly that, so the regression was in its own fix.
        await ahp.set_content(
            "<main><div role='menubar'><div role='menuitem'>Application Menu</div></div>"
            "<button>Real one</button><button>Real two</button></main>" + AH_HIDDEN)
        await ahp.wait_for_timeout(150)
        menubar = str(await ahp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        check("AH4 a role=menubar's item is NOT reported as an open popup",
              "aria-hidden" in menubar and "IS listed below" not in menubar,
              f"claimed_open={'IS listed below' in menubar}")
        await ahp.close()

        # ---- NR1-NR1d: A NON-RENDERED NODE CONTRIBUTES NOTHING TO A NAME.
        # `innerText` is documented as "what is rendered" and everything here believed
        # it — but HTML defines the getter to fall back to textContent when the element
        # is NOT being rendered, so `_contentName` read a display:none child and got its
        # whole subtree. Measured on eBay: a nav <li> with a closed mega-menu panel
        # listed as `404:"Motors Expand: Motors Parts and accessoriesAll parts and
        # accessories…"` — 3,392 characters in one fold line, 26.3% of the listing,
        # describing a menu nobody can see. NR1c/NR1d are the controls in the other
        # direction (#15): a rule that drops all descendant text is indistinguishable
        # from one that works, and the sr-only pattern the collector depends on is
        # CLIPPED, not hidden, so it must survive.
        nrp = await browser.new_page(viewport={"width": 1280, "height": 900})
        await nrp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await nrp.goto("about:blank")
        await nrp.set_content(
            "<main><ul>"
            "<li id=a onclick='void 0'><span>Motors</span>"
            "  <div style='display:none'><a href=/p>Car and truck parts</a>"
            "  <a href=/q>Wheels tires and parts</a></div></li>"
            "<li id=b onclick='void 0'><span>Fashion</span>"
            "  <div style='visibility:hidden'><a href=/r>Handbags</a></div></li>"
            "<li id=c onclick='void 0'><span>Deals</span> <span>today only</span></li>"
            "<li id=d onclick='void 0'><span>Help</span>"
            "  <span style='position:absolute;width:1px;height:1px;overflow:hidden;"
            "clip:rect(0 0 0 0)'>and contact</span></li>"
            "</ul></main>")
        await nrp.wait_for_timeout(150)
        nr = str(await nrp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        check("NR1 a display:none panel's text is not part of its container's name",
              "Car and truck parts" not in nr and "Motors" in nr,
              f"leaked={'Car and truck parts' in nr}")
        check("NR1b ...nor is a visibility:hidden one's",
              "Handbags" not in nr and "Fashion" in nr,
              f"leaked={'Handbags' in nr}")
        check("NR1c CONTROL: text from a RENDERED child is still part of the name",
              "today only" in nr, "the rendered sibling's text was dropped too")
        check("NR1d CONTROL: clipped sr-only text is rendered, so it still names",
              "and contact" in nr, "sr-only label lost")

        # NR2: STYLE AND SCRIPT TEXT IS NOT CONTENT. An SVG element has no innerText at
        # all, so the name path fell through to textContent and swallowed the inline
        # stylesheet. Measured on Grafana: `109:".cls-1{fill: currentColor;} AI &
        # machine learning"` in the slot the legend calls the element's IDENTITY.
        await nrp.set_content(
            "<main><a href=/ai id=z><svg width=16 height=16>"
            "<style>.cls-1{fill: currentColor;}</style><path d='M0 0h4v4H0z'/></svg>"
            "<span>AI and machine learning</span></a>"
            "<button>Run<script>var x=1;</script></button></main>")
        await nrp.wait_for_timeout(150)
        nr2 = str(await nrp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        check("NR2 an inline <svg><style>'s CSS never lands in an accessible name",
              "cls-1" not in nr2 and "currentColor" not in nr2
              and "AI and machine learning" in nr2, f"leaked={'cls-1' in nr2}")
        check("NR2b ...and neither does <script> text",
              "var x=1" not in nr2 and "Run" in nr2, f"leaked={'var x=1' in nr2}")

        # NR2c IS THE ONLY REASON `_NAME_SKIP` EXISTS, and it was measured before it
        # was kept: ablating the tag list changes the corpus listing by ZERO bytes
        # (grafana byte-identical, 6771 both ways), because `<style>` and `<script>`
        # carry `display:none` from the UA stylesheet and the visibility test already
        # rejects them. What it covers is the case the corpus does not contain — a page
        # that RENDERS its own stylesheet, which CSS-teaching and live-editor pages do
        # with `style { display: block }`. There the visibility test says "rendered" and
        # is right, and the text still is not a name: per AccName, style and script
        # content is never a text alternative however it is painted. So the list stays
        # as a SPEC rule with a fixture, not as a list someone thought of — and #25's
        # warning applies in the usual direction: an ablation measures the code against
        # the sample, and this sample has no such page.
        await nrp.set_content(
            "<style>#vis style{display:block}</style>"
            "<main><a href=/x id=vis><style>.cls-1{fill:currentColor}</style>"
            "<span>Themes</span></a></main>")
        await nrp.wait_for_timeout(150)
        nr3 = str(await nrp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        check("NR2c a RENDERED <style> is still not a name (the spec rule, not the "
              "visibility test)",
              "cls-1" not in nr3 and "Themes" in nr3, f"leaked={'cls-1' in nr3}")
        await nrp.close()

        # ---- SH1/SH1b: A HOST'S CONTENT IS ITS SHADOW CONTENT. #29 taught the child
        # loop to cross a shadow boundary; the node being NAMED was never asked the same
        # question, so a host whose entire content lives in its shadow root came back
        # with no name at all. Measured on caniuse: every <ciu-version-support> cell
        # rendered "4 - 28 : Not supported" and listed as a bare
        # `ref_149 | ciu-version-support`, making the support matrix unreadable.
        # SH1b pins the other half: the name came from descendants, so it must be
        # flagged as such, or the tree prints it twice once the child row is kept.
        shp = await browser.new_page(viewport={"width": 1280, "height": 900})
        await shp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await shp.goto("about:blank")
        await shp.set_content("<main><div id=host tabindex=0></div></main>")
        await shp.evaluate(
            "(function(){ const h = document.getElementById('host');"
            " const r = h.attachShadow({mode:'open'});"
            " r.innerHTML = '<div>4 - 28 : Not supported</div>'; })()")
        await shp.wait_for_timeout(150)
        sh = str(await shp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        check("SH1 a shadow host is named by the content it renders",
              "4 - 28 : Not supported" in sh, f"listing={sh[-200:]}")
        # ...and it is not then printed TWICE. When the shadow child is interactive in
        # its own right both are entries naming the same thing; whether the collapse
        # merges them or only one is collected, the reader must see the identity once.
        await shp.set_content("<main><div id=host2 tabindex=0></div></main>")
        await shp.evaluate(
            "(function(){ const h = document.getElementById('host2');"
            " const r = h.attachShadow({mode:'open'});"
            " r.innerHTML = '<div tabindex=0>4 - 28 : Not supported</div>'; })()")
        await shp.wait_for_timeout(150)
        sh2 = str(await shp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        _n = sum(1 for l in sh2.splitlines()
                 if "|" in l and "4 - 28 : Not supported" in l)
        check("SH1b ...and the host and its shadow child do not print it twice",
              _n == 1, f"rows_naming_it={_n}")
        await shp.close()

        # ---- TA1/TA1b: `title` IS AN ACCNAME SOURCE; THE HTML `name` ATTRIBUTE IS NOT.
        # `name` is the key the form posts under, and ordering it first meant a field
        # that DECLARES its label lost it to an ASCII identifier. Measured on Naver:
        # `<input name="query" title="검색어…">` listed as name="query", so the only
        # label a Korean reader sees was replaced by a developer token. TA1b is the
        # control — with no title the wire key is still better than nothing.
        tap = await browser.new_page(viewport={"width": 1280, "height": 900})
        await tap.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await tap.goto("about:blank")
        await tap.set_content(
            "<main><form><input name='query' title='검색어'>"
            "<input name='user-name'>"
            "<select name='ver' title='Python version'>"
            "<option>3.14</option><option>3.13</option></select></form></main>")
        await tap.wait_for_timeout(150)
        ta = str(await tap.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        check("TA1 a declared title outranks the HTML name attribute",
              '"검색어"' in ta and 'name="query"' not in ta,
              f"row={next((l for l in ta.splitlines() if 'input' in l), '')[:90]}")
        check("TA1b CONTROL: with no title the name attribute is still used",
              "user-name" in ta, "the wire-key fallback was lost")
        check("TA1c a <select>'s own option text never suppresses its title",
              "Python version" in ta,
              f"row={next((l for l in ta.splitlines() if 'select' in l), '')[:90]}")
        await tap.close()

        # ---- UI1-UI1c: "ICON" IS A CLAIM, AND NOTHING TESTED IT. The one row that
        # prints no identity said `(unlabeled-icon)`, asserting a shape that was never
        # checked — and three reviewers found it wrong on three pages (a decorative
        # logo, an EMPTY 1280x1600 toast container, 4px splitter hairlines). Whether an
        # element renders graphics IS checkable, so the marker now states only what is
        # known. UI1c pins the legend to the token actually emitted (#13).
        uip = await browser.new_page(viewport={"width": 1280, "height": 900})
        await uip.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await uip.goto("about:blank")
        await uip.set_content(
            "<main><button id=g style='width:32px;height:32px'>"
            "<svg width=16 height=16><path d='M0 0h4v4H0z'/></svg></button>"
            "<button id=e style='width:300px;height:60px'></button></main>")
        await uip.wait_for_timeout(150)
        ui = str(await uip.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        _rows = [l for l in ui.splitlines() if "(unlabeled" in l and "|" in l]
        check("UI1 a control that really renders a glyph is called an icon",
              any("(unlabeled-icon)" in l for l in _rows), f"rows={_rows}")
        check("UI1b ...and one that renders nothing is not",
              any(l.strip().endswith("(unlabeled)") or "(unlabeled)" in l for l in _rows)
              and sum("(unlabeled-icon)" in l for l in _rows) == 1, f"rows={_rows}")
        check("UI1c the legend names both tokens, because both appear",
              "- (unlabeled-icon)" in ui and "- (unlabeled) " in ui,
              f"icon_line={'- (unlabeled-icon)' in ui} plain_line={'- (unlabeled) ' in ui}")
        await uip.close()

        # ---- NB1-NB1c: `near=` FIRES WHERE IT IS NEEDED, NOT WHERE IT IS NOT.
        # The hint was computed for form fields only, so it reached rows that already
        # had a name and never the rows printed with no identity at all. And three
        # separate passes could hand the SAME string to several rows: on DataTables six
        # column headers each carried `near="Name Position Office Age Start date
        # Salary"` and six pager buttons each carried `near="<<<123456>>>"` — a roster
        # quoted next to labels that were already "1".."6".
        nbp = await browser.new_page(viewport={"width": 1280, "height": 900})
        await nbp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await nbp.goto("about:blank")
        await nbp.set_content(
            "<main><h3>Billing</h3><button id=ic style='width:28px;height:28px'></button>"
            "<table><tr><th>Name</th><th>Office</th><th>Age</th></tr></table></main>")
        await nbp.wait_for_timeout(150)
        nb = str(await nbp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        _icrow = next((l for l in nb.splitlines() if "(unlabeled" in l and "|" in l), "")
        check("NB1 an unnamed control gets the nearby-text hint",
              "near=" in _icrow, f"row={_icrow.strip()[:100]}")
        check("NB1b a hint shared by two or more NAMED rows is dropped from all of them",
              sum(1 for l in nb.splitlines() if 'near=' in l and '| th' in l) == 0,
              f"th_rows_with_near={[l.strip()[:70] for l in nb.splitlines() if 'near=' in l and '| th' in l]}")
        await nbp.close()

        # ---- HD1-HD1d: THE PAGE'S OWN DESCRIPTION OF A FIELD. The collector already
        # RESOLVED aria-describedby / aria-errormessage (#29 used them to keep help
        # text out of `value=`) and then discarded the text, so a form could state the
        # rule a field enforces, or why the last submit was rejected, and the listing
        # showed a field with no explanation. HD1c/HD1d are the controls: a field that
        # declares nothing pays nothing, and a STALE error node — present in the DOM at
        # all times — is only reported while the field is marked invalid, which is what
        # ARIA says aria-errormessage means.
        hdp = await browser.new_page(viewport={"width": 1280, "height": 900})
        await hdp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await hdp.goto("about:blank")
        await hdp.set_content(
            "<main><form>"
            "<label for=p>Password</label><input id=p type=password aria-describedby=ph>"
            "<div id=ph>Must be at least 8 characters</div>"
            "<label for=c>Card</label>"
            "<input id=c aria-invalid=true aria-errormessage=ce aria-describedby=ch>"
            "<div id=ch>16 digits, no spaces</div><div id=ce>That card number is invalid</div>"
            "<label for=q>Quiet</label><input id=q>"
            "<label for=s>Stale</label><input id=s aria-errormessage=se>"
            "<div id=se>Old error</div>"
            "</form></main>")
        await hdp.wait_for_timeout(150)
        hd = str(await hdp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        _row = lambda nm: next((l for l in hd.splitlines() if f'name="{nm}"' in l), "")
        check("HD1 a field's aria-describedby text is surfaced as help=",
              'help="Must be at least 8 characters"' in _row("Password"),
              f"row={_row('Password').strip()[:110]}")
        check("HD1b an INVALID field also reports its declared error message",
              'error="That card number is invalid"' in _row("Card")
              and 'help="16 digits, no spaces"' in _row("Card"),
              f"row={_row('Card').strip()[:130]}")
        check("HD1c CONTROL: a field that declares neither pays nothing",
              bool(_row("Quiet")) and "help=" not in _row("Quiet")
              and "error=" not in _row("Quiet"), f"row={_row('Quiet').strip()[:90]}")
        check("HD1d CONTROL: an error node is not reported unless aria-invalid is true",
              bool(_row("Stale")) and "Old error" not in _row("Stale"),
              f"row={_row('Stale').strip()[:90]}")
        await hdp.close()

        # ---- DR1: A ROW MUST NOT LIST THE SAME REF TWICE. The collapse loop walked a
        # snapshot of `keep` that its own body mutates, so an element already folded
        # away was still processed and deposited its ref onto a third node's list, which
        # the survivor then absorbed. Traced on nytimes (8 rows) and Yahoo Japan (3):
        # `ref_3146 ref_3147 ref_3147 ref_3148`. Nothing was lost, but the row claims
        # more distinct targets than exist.
        drp = await browser.new_page(viewport={"width": 1280, "height": 900})
        await drp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await drp.goto("about:blank")
        await drp.set_content(
            "<main><a href=/x style='display:block'><div style='display:block'>"
            "<span style='display:block'>Inside the War on Hezbollah</span>"
            "</div></a></main>")
        await drp.wait_for_timeout(150)
        dr = str(await drp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        _bad = [l for l in dr.splitlines()
                if len(re.findall(r"ref_(\d+)", l)) > 1
                and len(set(re.findall(r"ref_(\d+)", l))) != len(re.findall(r"ref_(\d+)", l))]
        check("DR1 no row repeats a ref", not _bad, f"rows={_bad[:2]}")
        await drp.close()

        # ---- OV1/OV1b: COUNT WHAT THE DROP REMOVES, AND ONLY ADVISE A SCROLL THE PAGE
        # CAN PERFORM. The off-viewport tally re-asked "is this a control" with a TAG
        # LIST while the drop above it used the collector's own rule — #18's asymmetry,
        # third instance. Measured on Syncfusion: 544 dropped, 449 of them
        # td[role=gridcell]/th[role=columnheader] off the right edge, and the page's
        # only spatial note read "4 ... outside the viewport HORIZONTALLY".
        ovp = await browser.new_page(viewport={"width": 1280, "height": 900})
        await ovp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await ovp.goto("about:blank")
        await ovp.set_content(
            "<main><button>Anchor</button>"
            "<table style='position:absolute;left:2200px;top:20px'><tr>"
            "<td role=gridcell tabindex=0>Trustworthiness</td>"
            "<td role=gridcell tabindex=0>Perfect</td></tr></table></main>")
        await ovp.wait_for_timeout(150)
        ov = str(await ovp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        check("OV1 off-viewport gridcells are counted, not filtered out by a tag list",
              "outside the viewport HORIZONTALLY" in ov
              and "2 interactive element(s) are outside" in ov,
              f"note={next((l for l in ov.splitlines() if 'HORIZONTALLY' in l), 'NONE')[:120]}")
        check("OV1b ...and the page does scroll sideways here, so that is the advice",
              "scroll sideways and re-observe" in ov, "wrong recovery for a scrolling page")

        # The same cells clipped inside a region that scrolls on its own: the WINDOW has
        # nowhere to go, so "scroll sideways" is a false trail of the #23/#33 kind.
        await ovp.set_content(
            "<main><button>Anchor</button>"
            "<div style='width:300px;overflow-x:auto'>"
            "<div style='width:2600px;position:relative;height:40px'>"
            "<table style='position:absolute;left:2200px;top:0'><tr>"
            "<td role=gridcell tabindex=0>Trustworthiness</td>"
            "<td role=gridcell tabindex=0>Perfect</td></tr></table>"
            "</div></div></main>")
        await ovp.wait_for_timeout(150)
        ov2 = str(await ovp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        check("OV1c a page that cannot scroll sideways is not told to",
              "HORIZONTALLY" in ov2 and "scroll sideways and re-observe" not in ov2
              and "does not scroll sideways" in ov2,
              f"note={next((l for l in ov2.splitlines() if 'HORIZONTALLY' in l), 'NONE')[:140]}")
        await ovp.close()

        # ---- CT1/CT1b: THE OVERFLOW LIST IS IN THE ORDER IT CLAIMS, AND EVERY REF IS
        # TYPED. It said "same order as the page" while being sorted by y then x, so a
        # two-column layout came out zipped: on the Java API docs
        # `555:"AbstractTypeVisitor6" 163:"javax.imageio" 557:"AbstractTypeVisitor7"`.
        # And an entry with no resolvable name emitted a BARE integer, so half the list
        # was numbers addressing nothing the reader could identify.
        ctp = await browser.new_page(viewport={"width": 1280, "height": 900})
        await ctp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await ctp.goto("about:blank")
        # Small type so both columns FIT the viewport: the listing is viewport-scoped,
        # so links pushed below the fold are dropped before the cap and there is no
        # overflow list to inspect at all (the first version of this fixture measured
        # nothing for exactly that reason).
        _sty = "display:block;font-size:7px;line-height:8px;margin:0"
        _colA = "".join(f"<a href=/a{i} style='{_sty}'>alpha{i}</a>" for i in range(100))
        _colB = "".join(f"<a href=/b{i} style='{_sty}'>bravo{i}</a>" for i in range(100))
        await ctp.set_content(
            "<main style='display:flex;margin:0'>"
            f"<div style='width:300px'>{_colA}</div>"
            f"<div style='width:300px'>{_colB}</div>"
            "<div><button style='width:30px;height:30px'></button></div></main>")
        await ctp.wait_for_timeout(200)
        ct = str(await ctp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"))
        _tail = next((l for l in ct.splitlines() if "OMITTED BUT ACTIONABLE" in l), "")
        _ids = [int(m) for m in re.findall(r"(?:^|\s)(\d+):", _tail)]
        check("CT1 the overflow list is emitted in document order, as it says",
              "document order" in _tail and len(_ids) > 5
              and _ids == sorted(_ids), f"first={_ids[:8]} sorted={_ids == sorted(_ids)}")
        _body = _tail.split("): ", 1)[-1]
        _bare_refs = re.findall(r"(?:^|\s)(\d+)(?=\s|$)", _body)
        check("CT1b every overflow ref carries a label or at least its tag",
              bool(_tail) and not _bare_refs, "bare_refs=" + str(_bare_refs[:5]))
        await ctp.close()

        await browser.close()

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} widget-zoo checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

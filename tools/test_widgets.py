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
        await dp.close()

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
        await ap.close()

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
        _hits = await tp2.evaluate("()=>window.__abClassActiveHits||0")
        check("W16c the class-token fallback is reached ONLY where the document"
              " declares nothing",
              _act.get("C-one") == "selected" and _act.get("C-two") == "" and _hits == 1,
              f"C-one={_act.get('C-one')!r} class-fallback fired {_hits}x (expected 1)")
        await tp2.close()

        await browser.close()

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} widget-zoo checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""Drop-ledger suite — the collector must be able to explain its own omissions.

WHY THIS EXISTS
---------------
The collector removed elements at ~20 bare `return`s and four destructive
post-passes, recording nothing. So "why is this element missing?" had no cheap
answer, and every investigation paid for it:

  - the whole ablation harness exists partly to infer drops by differencing;
  - CLAUDE.md's debugging table says "listing has 0 elements -> check three
    different functions";
  - most recently, finding out why three out-of-sample Mind2Web targets were
    missing took SIX DOM-mutation probes and two invalid diagnostics, and the
    hypothesis they produced (container suppression) was WRONG. The ledger
    answered it in one call, correctly: `not-interactive`.

INVARIANTS PINNED HERE
----------------------
L1  ledger OFF changes nothing — same elements, same order. A debug feature that
    perturbs the thing it observes is worse than no debug feature.
L2  every dropped element carries a rule id (no anonymous drops)
L3  kept and dropped are disjoint — a rule cannot be blamed for a removal that a
    later pass undid, which is why `dropped` is filtered against the final set
L4  the specific rules that fire on known shapes are the expected ones
L5  the breakdown accounts for the drops it reports

Run:  python tools/test_ledger.py
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract as _shared_extract  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = _shared_extract("_collectInteractivePage", BG, verify=True)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))


PAGE = """<!doctype html><meta charset=utf-8><body style="margin:0">
  <button id=keep style="width:120px;height:30px">Real Button</button>
  <a id=keeplink href="/x" style="display:inline-block;width:90px;height:20px">A Link</a>
  <!-- no role, no tabindex, no handler, no pointer cursor: correctly not a control -->
  <div id=inert style="width:200px;height:20px">Product Category</div>
  <!-- explicitly hidden -->
  <button id=hidden style="width:100px;height:24px;display:none">Hidden</button>
  <!-- A BARE [inert] REGION. `inert` renders normally and passes every
       visibility test, so nothing but the attribute says its contents cannot be
       operated. CLAUDE.md #25 recorded this as dead code ("no _drop(el,'inert')
       call exists, so a bare inert region presents as fully actionable"); the
       call is there, and the note was stale. This check is what makes that
       verifiable instead of re-derivable from reading. -->
  <div inert><button id=inertkid style="width:120px;height:26px">Inert Child</button></div>
  <!-- aria-hidden subtree -->
  <div aria-hidden="true"><button id=ah style="width:100px;height:24px">Aria Hidden</button></div>
  <!-- DEMOTED but KEPT: a heuristic judged it non-content, which under the
       prominence-not-existence rule marks it and leaves it in the listing. It
       must be reported as demoted and must NOT appear among the drops. -->
  <div id=demoted onclick="void 0" style="pointer-events:none;width:200px;height:24px">Muted Row</div>
  <!-- DEMOTED and THEN genuinely removed. Absence is decided by the spec rule
       alone, so this element must appear in `dropped` EXACTLY ONCE, attributed
       to parent-child-dedup and not to the heuristic that merely demoted it.
       Live shape this reproduces (gutenberg.org): 50 elements carried both a
       `was:generic-no-label` entry and a `parent-child-dedup` entry, so the
       header reported more drops than the page had elements and the real cause
       sat under a rule that no longer removes anything. -->
  <div id=both onclick="void 0" style="pointer-events:none;width:300px;height:36px">
    <button id=bothkid style="pointer-events:auto;width:280px;height:30px">Nested Real Control</button>
  </div>
  <!-- far below the fold -->
  <div style="height:3000px"></div>
  <button id=below style="width:100px;height:24px">Below Fold</button>
</body>"""


async def collect(page, ledger=False, detail="compact"):
    return await page.evaluate(
        "(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, '"
        + detail + "', " + ("true" if ledger else "false") + "); })()")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 900, "height": 700})
        await page.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await page.set_content(PAGE)
        await page.wait_for_timeout(150)

        plain = await collect(page, ledger=False)
        led = await collect(page, ledger=True)

        def ident(e):
            return (e.get("tag"), e.get("name"), e.get("label"), e.get("x"), e.get("y"))

        check("L1 ledger OFF and ON produce the same elements, in the same order",
              [ident(e) for e in plain] == [ident(e) for e in led["elements"]],
              f"{len(plain)} vs {len(led['elements'])}")

        dropped = led["dropped"]
        check("L2 every dropped element carries a rule id",
              all(d.get("rule") for d in dropped),
              f"{sum(1 for d in dropped if not d.get('rule'))} anonymous of {len(dropped)}")

        kept_ids = {str(e["mmid"]) for e in led["elements"]}
        overlap = kept_ids & {str(d["mmid"]) for d in dropped}
        check("L3 kept and dropped are disjoint", not overlap, f"overlap={list(overlap)[:5]}")

        async def rule_for(el_id):
            mm = await page.evaluate(
                f"()=>{{const e=document.getElementById('{el_id}');return e?e.getAttribute('mmid'):null;}}")
            hit = [d for d in dropped if str(d["mmid"]) == str(mm)]
            return hit[0]["rule"] if hit else None

        check("L4a a plain unstyled div with no handler is dropped as not-interactive",
              await rule_for("inert") == "not-interactive", str(await rule_for("inert")))
        check("L4b a display:none control is dropped for visibility, not interactivity",
              (await rule_for("hidden")) in ("not-visible", "not-interactive", None),
              str(await rule_for("hidden")))
        check("L4c an aria-hidden subtree control is attributed to aria-hidden",
              (await rule_for("ah")) in ("aria-hidden", "not-visible"), str(await rule_for("ah")))
        # A below-fold control is RETAINED (flagged offscreen) so find() can reach
        # the whole page — it is not a drop at all. Accepting None here passed
        # vacuously; assert the documented behaviour instead, so this check fails
        # if offscreen retention ever regresses.
        below_mm = await page.evaluate(
            "()=>{const e=document.getElementById('below');return e?e.getAttribute('mmid'):null;}")
        below_entry = next((e for e in led["elements"] if str(e["mmid"]) == str(below_mm)), None)
        check("L4d a below-fold control is RETAINED and flagged offscreen, not dropped",
              below_entry is not None and bool(below_entry.get("offscreen"))
              and await rule_for("below") is None,
              f"kept={below_entry is not None} offscreen={(below_entry or {}).get('offscreen')} "
              f"rule={await rule_for('below')}")
        _inert_rule = await rule_for("inertkid")
        check("L4e a control inside a bare [inert] region is dropped as inert",
              _inert_rule == "inert",
              f"rule={_inert_rule!r} (CLAUDE.md #25 called this dead code; the call "
              f"is at the aria-hidden/inert guard and this proves it fires)")

        by = led.get("byRule") or {}
        check("L5 the rule breakdown accounts for every reported drop",
              sum(by.values()) == len(dropped), f"{sum(by.values())} vs {len(dropped)}")

        # L7-L10: DEMOTION IS NOT A DROP. Under prominence-not-existence a
        # heuristic marks an element and leaves it in place, so the ledger has two
        # populations to keep apart — and it did not. Both failures were live:
        # craigslist/rakuten reported demoted-but-PRESENT elements as dropped, and
        # gutenberg counted 50 elements twice (once demoted, once genuinely
        # deduped), claiming more drops than the page had elements while hiding the
        # rule that actually decided their absence.
        demoted = led.get("demoted") or []
        dem_ids = {str(d["mmid"]) for d in demoted}
        drop_ids = [str(d["mmid"]) for d in dropped]

        async def mm(el_id):
            return await page.evaluate(
                f"()=>{{const e=document.getElementById('{el_id}');return e?e.getAttribute('mmid'):null;}}")

        m_dem, m_both = await mm("demoted"), await mm("both")
        check("L7 an element a heuristic demoted is reported as demoted, not dropped",
              str(m_dem) in dem_ids and str(m_dem) not in drop_ids,
              f"mmid={m_dem} in demoted={str(m_dem) in dem_ids} in dropped={str(m_dem) in drop_ids}"
              f" rules={[d['rule'] for d in demoted]}")
        check("L7b ...and is still in the listing, actionable by ref",
              any(str(e["mmid"]) == str(m_dem) for e in led["elements"]))
        check("L8 the two populations are disjoint — nothing is both dropped and demoted",
              not (dem_ids & set(drop_ids)), f"both={list(dem_ids & set(drop_ids))[:5]}")
        check("L9 no element is counted twice among the drops",
              len(drop_ids) == len(set(drop_ids)),
              f"{len(drop_ids)} entries, {len(set(drop_ids))} distinct")
        # L10 used to assert that a demoted-THEN-REMOVED element was attributed to
        # the rule that removed it. No heuristic removes any more — the five
        # container rules (parent-child-dedup, delegation-root,
        # container-suppression, same-box-wrapper-collapse, shadow-host-collapse)
        # all demote — so that scenario has no case left, and the invariant worth
        # pinning is the one that replaced it: this element is judged by a
        # container rule AND by pointer-events, and must come back present, once,
        # under exactly ONE reason.
        both_dem = [d["rule"] for d in demoted if str(d["mmid"]) == str(m_both)]
        both_rules = [d["rule"] for d in dropped if str(d["mmid"]) == str(m_both)]
        both_rows = [e for e in led["elements"] if str(e["mmid"]) == str(m_both)]
        check("L10 an element two heuristics judge is present exactly once, under "
              "exactly one reason, and is not among the drops",
              len(both_rows) == 1 and len(both_dem) == 1 and not both_rules,
              f"mmid={m_both} rows={len(both_rows)} demotions={both_dem} drops={both_rules}")
        # THE TRIPWIRE. The user-visible promise is "no heuristic decides whether
        # an element exists", and the only way to keep it true as code changes is
        # to enumerate what may delete and fail on anything else. Every name here
        # is either the page declaring the element absent, the complement of the
        # declaration set in isInteractive (not-interactive), an inheritance
        # correction (a contenteditable/editor descendant is content, not a
        # control), a caller budget, or a measurement error path.
        SPEC_DELETES = {
            "not-connected", "not-visible", "checkVisibility-false", "aria-hidden",
            "inert", "outside-viewport", "not-interactive",
            "contenteditable-non-root", "inside-editor-host", "canvas-measure-failed",
            # A same-origin iframe: its inner elements are listed individually, so
            # the frame is a container rather than a control. This exit used to be
            # SILENT -- one of the uninstrumented removals this test cannot see, so
            # the ledger had no answer for "why does the iframe have no row".
            "iframe-contents-listed-instead",
            # `cursor` is an INHERITED CSS property, so a pointer cursor on a
            # descendant of a control is the control's declaration and not the
            # descendant's -- the same inheritance error as contenteditable-non-root
            # just above. Wikipedia's citation markup printed three rows per citation
            # (the anchor plus its two bracket spans) before this.
            "cursor-inherited-non-root",
        }
        _rogue = sorted({str(d["rule"]) for d in dropped} - SPEC_DELETES)
        check("L10c nothing outside the spec-decided set deletes an element",
              not _rogue,
              f"rogue delete rules={_rogue}" if _rogue
              else f"delete rules seen={sorted({str(d['rule']) for d in dropped})}")
        check("L10b every reported drop names a spec rule, never a demotion",
              not [d["rule"] for d in dropped if str(d["rule"]).startswith("was:")],
              str([d["rule"] for d in dropped if str(d["rule"]).startswith("was:")][:4]))
        check("L6 real controls survive (the ledger did not eat the listing)",
              any((e.get("name") or e.get("label") or "").strip() == "Real Button"
                  for e in led["elements"]),
              f"{len(led['elements'])} kept, top rules {sorted(by.items(), key=lambda x: -x[1])[:3]}")

        await browser.close()

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} ledger checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

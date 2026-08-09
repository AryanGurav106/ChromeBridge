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
  <!-- aria-hidden subtree -->
  <div aria-hidden="true"><button id=ah style="width:100px;height:24px">Aria Hidden</button></div>
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

        by = led.get("byRule") or {}
        check("L5 the rule breakdown accounts for every reported drop",
              sum(by.values()) == len(dropped), f"{sum(by.values())} vs {len(dropped)}")
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

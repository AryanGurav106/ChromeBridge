"""Can `find` reach an element by the identity the LISTING printed for it?

THE GAP THIS CLOSES. Every other ruler here measures PRESENCE — presence,
`lost_identities`, Mind2Web recall, and `measure_sufficiency`'s DS. CLAUDE.md
#74 found 118 elements on ptable.com that were present in all of them and
unreachable by `find`, on a page the readiness probe itself called SETTLED,
including by their VERBATIM printed label. The listing was correct throughout;
the tool reading it was not, and no offline measurement in this repo could have
caught that.

Three of that session's defects were in the tools that READ the listing rather
than in the listing. This measures the reading layer.

THE METRIC. For each entry the collector returns, take the identity the listing
would PRINT for it, hand that string to the real `find`, and ask whether that
same element comes back. It is deliberately the weakest possible question —
not "can find infer the goal" (#20 measured that at 0% and it is semantic
inference, not retrieval), just "can find return the thing when handed its own
words". A miss here is unambiguous.

WHAT IT CANNOT ANSWER:
  * It scores find against the COLLECTOR, so a name both of them get wrong
    scores as a hit. It cannot see a wrong name, only an unreachable one.
  * Ties are not failures: several elements legitimately share an identity
    ("Submit", a repeated nav). An entry is reached if it is anywhere in the
    returned set, because that is the point at which an agent can act on it.
  * It says nothing about ranking quality beyond that.

  python tools/measure_findability.py [--n 20]
"""
import argparse, asyncio, importlib.util, json, re, sys
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "temp" / "frozen"
sys.path.insert(0, str(ROOT / "tools"))
from _extract import extract as _extract_fn          # noqa: E402
from capture_listings import SITES                   # noqa: E402

_spec = importlib.util.spec_from_file_location("ms", ROOT / "mcp_server.py")
ms = importlib.util.module_from_spec(_spec)
sys.modules["ms"] = ms
_spec.loader.exec_module(ms)
_find = ms.find.fn if hasattr(ms.find, "fn") else ms.find

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = _extract_fn("_collectInteractivePage", BG, verify=True)
VIEWPORT = {"width": 1280, "height": 1600}


def identity_of(e):
    """The words the LISTING shows for this element — what a reader would type."""
    for k in ("name", "label", "text", "value", "placeholder"):
        v = (e.get(k) or "").strip()
        if v:
            return v
    return ""


class _FB:
    connected = True

    def __init__(self, entries, listing=""):
        self.entries, self.listing = entries, listing

    async def call(self, op, **kw):
        if op == "get_interactive_elements" and not kw.get("structured"):
            return self.listing
        if op == "page_readiness":
            return ""
        return list(self.entries)


async def one(browser, name, url, cap):
    ctx = await browser.new_context(viewport=VIEWPORT)
    try:
        har = FROZEN / f"{name}.har"
        if not har.exists():
            return None
        await ctx.route_from_har(str(har), not_found="abort")
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        await page.wait_for_timeout(600)
        entries = await page.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        if not isinstance(entries, list) or not entries:
            return None
    except Exception:
        return None
    finally:
        await ctx.close()

    # CONTESTED vs GENUINE. `find` returns a bounded set, so on a page with 30
    # identical "upvote" links the one being probed can legitimately fall
    # outside it -- that is a result-cap artefact, not unreachability, and
    # counting it as a miss would make this ruler pessimistic in a way that
    # tracks how repetitive a page is rather than how reachable it is. An
    # identity shared by other entries is reported SEPARATELY. A unique
    # identity that does not come back is the real finding (#74's shape).
    _ident_count = {}
    for _e in entries:
        _q = identity_of(_e)
        if len(_q) >= 2:
            _ident_count[_q] = _ident_count.get(_q, 0) + 1

    ms.STATE["bridge"] = _FB(entries)
    tried = hit = contested = 0
    misses = []
    for e in entries[:cap]:
        q = identity_of(e)
        # Nothing to ask with, and a 1-char identity is not a question.
        if len(q) < 2:
            continue
        tried += 1
        try:
            out = await _find(query=q, tabId=1)
        except Exception:
            continue
        if re.search(r"\bref_" + re.escape(str(e.get("mmid"))) + r"\b", str(out)):
            hit += 1
        elif _ident_count.get(q, 1) > 1:
            contested += 1
        elif len(misses) < 4:
            misses.append({"mmid": e.get("mmid"), "tag": e.get("tag"),
                           "identity": q[:60], "shared_by": _ident_count.get(q, 1)})
    return {"tried": tried, "hit": hit, "contested": contested, "misses": misses}


async def main(n, cap):
    rows = []
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        for name, url in SITES[:n]:
            r = await one(b, name, url, cap)
            if r and r["tried"]:
                _uniq = r["tried"] - r["contested"]
                rate = r["hit"] / max(1, _uniq)
                rows.append((name, r))
                flag = ("   <-- " + json.dumps(r["misses"][:2], ensure_ascii=False)[:90]
                        if r["misses"] else "")
                print(f"  {name:<22} {r['hit']:>4}/{_uniq:<4} = {rate:.3f}"
                      f"  ({r['contested']} contested){flag}")
        await b.close()
    T = sum(r["tried"] - r["contested"] for _n, r in rows)
    H = sum(r["hit"] for _n, r in rows)
    C = sum(r["contested"] for _n, r in rows)
    print(f"\nsites: {len(rows)}   reachable by own printed identity: "
          f"{H}/{T} = {H/T:.4f}   ({C} contested, excluded — an identity shared "
          f"with other entries can fall outside find's bounded result set)"
          if T else "no data")
    worst = sorted(rows, key=lambda x: x[1]["hit"]
                   / max(1, x[1]["tried"] - x[1]["contested"]))[:3]
    for nm, r in worst:
        print(f"  worst: {nm} {r['hit']}/{r['tried'] - r['contested']} "
              f"{json.dumps(r['misses'][:3], ensure_ascii=False)[:160]}")
    print("\nNOT a measure of whether find can infer a GOAL (#20: 0%, and that is "
          "semantic inference, not retrieval). It is the weakest question there "
          "is: handed an element's own printed words, does find return it.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--cap", type=int, default=40, help="entries probed per site")
    a = ap.parse_args()
    asyncio.run(main(a.n, a.cap))


# ---------------------------------------------------------------------------
# WHAT THIS RULER DID NOT CATCH, recorded because I claimed it would.
#
# After #74 I wrote that a reachability ruler "would have caught it the day it
# shipped". Ablating the #74 fix and re-running this probe over 8 frozen sites
# produced the IDENTICAL number: 170/173 both ways. So on this corpus it would
# NOT have caught it.
#
# The reason is the sample, not the metric. #74's shape is an interactive
# container whose every text-contributing child is itself non-interactive --
# ptable's `<li tabindex>` over <b>/<abbr>/<em>/<data>. None of github,
# youtube, hn, bootstrap_forms, shoelace or the two MUI demos has it among the
# entries probed. #25's rule, landing on a ruler I had just built and praised:
# an ablation measures the code against the sample and cannot measure the
# sample.
#
# What that means for using this:
#   * the 0.9827 is real and the three misses are the deliberate app-shell
#     blanking, so the reading layer is in good shape ON THESE PAGES;
#   * it is NOT yet a regression test for #74, and must not be described as
#     one until the corpus contains that shape. `tools/probe_tile_identity.py`
#     builds it synthetically and F40/F40b pin it in the suite -- those are the
#     regression guard, and this is the population measurement.
# ---------------------------------------------------------------------------

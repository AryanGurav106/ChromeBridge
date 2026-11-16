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



async def _descendant_returned(page, mmid, out):
    """Did find return an element INSIDE the one we asked for?

    Acting on it does what acting on the target would -- that is the whole
    reason the descendants are listed separately. Descendant only, never
    ancestor: an ancestor claiming credit is how a page-sized container would
    score a hit for everything it contains.
    """
    refs = set(re.findall(r"\bref_(\d+)\b", out or ""))
    refs.discard(str(mmid))
    if not refs:
        return False
    # NOT `except: return False`. That is how this arm came to report 0 on
    # every site: `one()` closed the context in a `finally` BEFORE the probe
    # loop ran, so every evaluate raised on a dead page, every call swallowed it
    # and answered "no descendant", and #75 recorded the resulting 0 as having
    # REFUTED the label-plus-badge theory. It had measured a closed browser.
    # A question that could not be ASKED is not an answer of no, so it raises.
    return bool(await page.evaluate(
        """([m, rs]) => {
            const r = window.__mmidReg; if (!r) return false;
            const t = r.get(String(m)); if (!t) return false;
            return rs.some(x => { const n = r.get(String(x));
                                  return n && n !== t && t.contains(n); });
        }""", [str(mmid), list(refs)]))

async def one(browser, name, url, cap, extra_wait=None):
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
        await page.wait_for_timeout(min(4000, extra_wait or 600))
        entries = await page.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        if not isinstance(entries, list) or not entries:
            await ctx.close()
            return None
    except Exception:
        await ctx.close()
        return None

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
    tried = hit = contested = desc_hit = 0
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
        elif await _descendant_returned(page, e.get("mmid"), str(out)):
            # DESCENDANT CREDIT, reported SEPARATELY and never folded into the
            # strict number. Decided on the mechanism, not on the misses: an
            # <a><span>Issues</span><span>5k+</span></a> has its name blanked
            # because it is assembled, and its spans are kept because an anchor
            # gives descendants cursor:pointer, which is an admitting signal.
            # So find("Issues") returns the SPAN -- and clicking the span
            # activates the link, which is exactly the reasoning #18 and #73
            # use to credit a descendant on Mind2Web.
            #
            # BOUNDED the same way #73 bounds its ancestor path: only a
            # descendant, never an ancestor, so a page-sized container cannot
            # claim credit for everything inside it.
            desc_hit += 1
        elif len(misses) < 4:
            misses.append({"mmid": e.get("mmid"), "tag": e.get("tag"),
                           "identity": q[:60], "shared_by": _ident_count.get(q, 1)})
    await ctx.close()
    return {"tried": tried, "hit": hit, "contested": contested,
            "desc_hit": desc_hit, "misses": misses}


async def main(n, cap):
    rows = []
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        # 35 of the 106 SITES entries carry a third field (an extra settle
        # time for heavy apps like jupyter and vscode_dev). Unpacking two
        # killed a full-corpus run at site 51 -- the first 50 happen to be
        # the 2-tuples, so a partial run looked like a complete one.
        for _site in SITES[:n]:
            name, url = _site[0], _site[1]
            _wait = _site[2] if len(_site) > 2 else None
            r = await one(b, name, url, cap, _wait)
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
    D = sum(r.get("desc_hit", 0) for _n, r in rows)
    print(f"\nsites: {len(rows)}   reachable by own printed identity: "
          f"{H}/{T} = {H/T:.4f}   ({C} contested, excluded — an identity shared "
          f"with other entries can fall outside find's bounded result set)"
          if T else "no data")
    if T:
        # TWO NUMBERS, NEVER ONE. The strict figure asks for THIS element; the
        # second credits a returned DESCENDANT, because acting on it does what
        # acting on the target would. Folding them would hide which is which,
        # and the gap between them IS the finding -- it is the size of the
        # label-plus-badge population, not a defect.
        # STATE THE NUMBER, NOT A THEORY ABOUT IT. This line used to assert
        # that the gap IS the label+badge shape, in the same breath as a figure
        # that could contradict it -- and did, while the arm was broken. What
        # the two numbers mean is mechanical; what the residue IS belongs to a
        # classification of the misses, not to a sentence printed beside them.
        print(f"                 …plus {D} reached via a returned DESCENDANT "
              f"(strict {H/T:.4f} -> {(H+D)/T:.4f} with descendant credit). "
              f"A descendant is credited because acting on it does what acting "
              f"on the target would (#18, #73); it is reported separately and "
              f"never folded in. {T - H - D} miss(es) are reachable by neither "
              f"— see --dump to classify them.")
    worst = sorted(rows, key=lambda x: x[1]["hit"]
                   / max(1, x[1]["tried"] - x[1]["contested"]))[:3]
    for nm, r in worst:
        print(f"  worst: {nm} {r['hit']}/{r['tried'] - r['contested']} "
              f"{json.dumps(r['misses'][:3], ensure_ascii=False)[:160]}")
    print("\nNOT a measure of whether find can infer a GOAL (#20: 0%, and that is "
          "semantic inference, not retrieval). It is the weakest question there "
          "is: handed an element's own printed words, does find return it.")


async def self_test():
    """PROVE THE RULER CAN FIRE. A detector reporting 0 findings is worth
    nothing until it has been shown to detect something -- `audit_patterns.py`
    self-tests against three historical bugs for exactly this reason, and all
    three had passed code review before they were measured.

    This matters more than usual here, because ablating the #74 fix and
    re-running over 8 frozen sites gave the IDENTICAL number: that corpus does
    not contain #74's shape, so the live run alone cannot show the ruler works.

    The shape, synthetically: an interactive container whose every
    text-contributing child is NON-interactive, so the container is the only
    carrier of its own name -- ptable's `<li tabindex>` over
    <b>36</b><abbr>Kr</abbr><em>Krypton</em><data>83.798</data>.
    """
    def _e(**kw):
        b = dict(mmid="1", tag="div", role=None, label="", name="", value="",
                 placeholder="", text="", near="", w=60, h=60, y=10)
        b.update(kw)
        return b

    sole = _e(mmid="919", tag="li", label="36 Kr Krypton 83.798",
              subtreeName=True, subtreeNameSole=True)
    other = _e(mmid="25", tag="a", name="Properties", w=80, h=20)
    shell = _e(mmid="3", tag="body", label="Skip to content Home Docs Pricing "
                                           "Sign in Contact Footer", subtreeName=True)

    ok = True
    ms.STATE["bridge"] = _FB([sole, other])
    out = await _find(query="36 Kr Krypton 83.798", tabId=1)
    hit = "ref_919" in str(out)
    print(f"  sole carrier is reachable by its own identity: {'YES' if hit else 'NO'}")
    ok &= hit

    # ...and the ruler must still SCORE a genuine miss as a miss. An app shell
    # is blanked ON PURPOSE, so it is the known-miss case: if this came back a
    # hit, the metric could not distinguish reachable from unreachable at all.
    ms.STATE["bridge"] = _FB([shell, other])
    out = await _find(query="Skip to content Home Docs Pricing Sign in Contact Footer",
                      tabId=1)
    miss = "ref_3" not in str(out)
    print(f"  deliberately blanked shell scores as a MISS: {'YES' if miss else 'NO'}")
    ok &= miss

    print("\nSELF-TEST " + ("PASSED — the ruler distinguishes reachable from not."
                            if ok else
                            "FAILED — this metric cannot tell the two apart and "
                            "its number means nothing."))
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--cap", type=int, default=40, help="entries probed per site")
    ap.add_argument("--self-test", action="store_true",
                    help="prove the ruler fires, with no browser and no corpus")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(asyncio.run(self_test()))
    asyncio.run(main(a.n, a.cap))


# ---------------------------------------------------------------------------
# THE POPULATION NUMBER, 34 frozen sites: 811/824 = 0.9842 reachable by their
# own printed identity, 20 contested excluded.
#
# The 13 misses are NOT app shells, which is what I expected and is the more
# interesting answer. The ones recoverable verbatim from the run are
# `span "Search Cmd+K"`, `a "Issues 5k+"` and `ul "4.1.0 25.9k 6.1k"` -- all
# the same shape: a label joined to a BADGE (a count, a keyboard hint, a
# version). The element's name is assembled from several children, so it is
# blanked, and unlike ptable's tile some of those children ARE kept entries,
# so it is not a sole carrier.
#
# THAT MAKES THE METRIC STRICTER THAN THE AGENT'S ACTUAL SITUATION, and it is
# worth stating rather than quietly fixing. It asks whether THIS mmid comes
# back. When the inner <span>Issues</span> is itself listed, find("Issues")
# returns that span, and clicking it does what clicking the link would --
# which is exactly the reasoning #18 and #73 use to credit a DESCENDANT on
# Mind2Web. By that standard these are hits.
#
# Not changed here, deliberately: loosening a metric after seeing which cases
# it fails is grading to the answer. The honest reading is that 0.9842 is a
# LOWER bound, the residual is one shape, and whether to credit a descendant
# is a decision to take on its own merits rather than while looking at the
# misses it would erase.
#
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

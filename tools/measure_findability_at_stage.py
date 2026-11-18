"""Can `find` reach a control by the identity the LISTING printed for it, AFTER the page
has been interacted with? Live, out-of-sample, multi-stage.

WHY THIS EXISTS. Every ruler in this repo measures PRESENCE -- presence, `lost_identities`,
Mind2Web recall, `measure_sufficiency`'s DS. CLAUDE.md #74 found 118 ptable.com tiles that
were present in all of them and UNREACHABLE by their own verbatim printed label, on a page
the readiness probe itself called SETTLED. No presence metric can see that class: the row is
there, the name is on it, and the tool that reads the listing cannot return it.

`measure_findability.py` closed that gap on the FROZEN corpus AT FIRST PAINT (0.9774 strict /
0.9996 with descendant credit, 95 sites). #89 then measured identity LOSS after up to four
compounding interactions on 255 live out-of-sample sites and found 0 -- and closed by naming
this as the most valuable unmeasured thing: *"every number here says the control is PRESENT,
and none says it is present under its own name."*

So: **does reachability-by-name survive an interaction?** A control revealed by opening a
menu, switching a tab or rendering a listbox is PRESENT (#89 measured 2,106 such controls,
0 lost). Present is not reachable.

WHAT IS REUSED, NOT REWRITTEN.
  * the DRIVER -- `audit_stage_generality` (#89): STAGE_PICK / _act / STAGE_VERIFY, the
    declaration-only tier list, the flip rule, the excluded-host set, the sample pool.
  * the METRIC -- `measure_findability` (#74): `identity_of`, the `_FB` fake bridge, the real
    `find` bound out of `mcp_server.py`, and `_relation_returned`.
Forking either would let two definitions drift (PRINCIPLES 17), which #36 recorded happening
to the permitted-drop-reason set.

TWO ARMS, BOTH FROM THE SAME PAGE LOAD AND THE SAME STAGE (PRINCIPLES 10 / R3 -- interleaved,
so run-order drift cannot align with an arm):
  full     the entries `find` REALLY receives. The shipped tool calls
           get_interactive_elements(structured=True, detail="full") so images are in its
           search space. THIS IS THE HEADLINE ARM.
  compact  the entries `measure_findability.py` feeds it. Reported so the frozen-corpus
           number stays comparable, and because the difference between the two is a
           measurement of that ruler's fidelity rather than a matter of taste.

POPULATIONS, which is how the sharp question gets answered:
  s0        probed at first paint
  new       probed at stage >= 1, identity string NEVER seen at an earlier stage -- i.e.
            the control exists BECAUSE of the interaction
  carried   probed at stage >= 1, identity already seen -- the control that was always there,
            now living on a page that has been interacted with
`carried` is the control arm. If `new` and `carried` fall together, the cause is the page
after interaction; if only `new` falls, it is the revealed control itself.
NEW is keyed on the IDENTITY STRING, not the mmid: mmids are additive, so one re-render
mints hundreds of fresh ones for elements that did not change (#9), and #89's
`new_named_controls` uses the same name-set definition.

WHAT THIS CANNOT ANSWER, each with its own tool:
  * whether the name is RIGHT. This scores `find` against the COLLECTOR, so a name both get
    wrong scores as a hit. It sees an unreachable name, never a wrong one.
  * whether a model then PICKS the row (#75 -- that work found the benchmark substrate
    cannot carry the question).
  * hover-only menus, logins, paywalls, cross-origin frames (inherited from #89).

Run:  python tools/measure_findability_at_stage.py --selftest       # the fixture proof
      python tools/measure_findability_at_stage.py --fire --only A  # the LIVE firing proof
      python tools/measure_findability_at_stage.py --pool usable85 --conc 6
      python tools/measure_findability_at_stage.py --compare --only ...   # drift floor
      python tools/measure_findability_at_stage.py --report temp/findability_stage/main/pass0.json

Findings: docs/research/FINDABILITY-AT-STAGE-2026-11.md
"""
import argparse
import asyncio
import collections
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from playwright.async_api import async_playwright  # noqa: E402
import audit_stage_generality as ASG  # noqa: E402  (the interaction driver, verbatim)
import measure_findability as MF  # noqa: E402  (the metric, verbatim)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VIEWPORT = ASG.VIEWPORT
OUT = ROOT / "temp" / "findability_stage"
CAP = 24            # PRINTED-identity rows probed per stage per arm
NEW_CAP = 16        # of those, reserved for identities the interaction revealed
BLANKED_CAP = 6     # rows the listing blanks, probed with the separate question below
MAX_QUERY_CHARS = 300
BLANKED_QUERY_CHARS = 100
ARMS = ("full", "compact")
_SCORE_LOCK = asyncio.Lock()


# --------------------------------------------------------------------------------------
# COLLECTION. One evaluate per stage: the string listing (what a reader sees), the compact
# structured array, and the FULL structured array (what `find` is really handed).
# --------------------------------------------------------------------------------------
def _collect_js():
    return ("(function(){ " + MF.COLLECT + ";"
            " const listing = _collectInteractivePage(false, null, 'compact', false, false, 'tree');"
            " const compact = _collectInteractivePage(true,  null, 'compact', false, false, 'tree');"
            " const full    = _collectInteractivePage(true,  null, 'full',    false, false, 'tree');"
            " return { listing: String(listing), compact: compact, full: full,"
            "          url: location.href, title: document.title }; })()")


def _ents(v):
    """Structured mode may answer with a JSON STRING; AGL's _summ carries the same guard."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return []
    return v or []


_NORM_RE = re.compile(r"\s+")


def _norm(s):
    return _NORM_RE.sub(" ", unicodedata.normalize("NFC", s or "")).strip().casefold()


def listing_index(listing):
    """mmid -> the listing LINE that carries it.

    Two ref shapes, because a listing prints both: an ordinary row (`ref_12 | ...`) and a
    FOLD member or overflow entry (`12:"Add to cart"`). A bare number is deliberately NOT
    matched -- a price or a rank would make every row look like a ref.
    """
    idx = {}
    for line in (listing or "").split("\n"):
        for m in re.findall(r"\bref_(\d+)\b", line):
            idx.setdefault(m, line)
        for m in re.findall(r'(?<![0-9])(\d+):"', line):
            idx.setdefault(m, line)
    return idx


def _identity_printed(idx, mmid, q):
    """Did the LISTING actually print this identity on this element's own row?

    This is not pedantry. When `subtreeName && !subtreeNameSole` the collector prints the row
    with name/label/text BLANKED on purpose (#74's rule: an app shell must not match every
    query), so asking `find` for that name asks for a string the listing never showed. Those
    rows are counted and NAMED rather than silently inflating the miss column.
    A 20-char prefix, because a bounded field may carry a `…(+N)` marker (#22).
    """
    line = idx.get(str(mmid))
    if line is None:
        return None
    nq = _norm(q)[:20]
    return bool(nq) and nq in _norm(line)


# --------------------------------------------------------------------------------------
# PROBE SELECTION. New identities first, then a STRIDE sample of the rest.
# A head-slice (what the frozen-corpus tool does) is fine on a static page and wrong here:
# the first 30 entries of a live page are its header, and the whole point of a staged read is
# that the interesting controls appeared further down. Stride-sampling spans the document.
# --------------------------------------------------------------------------------------
def _stride(xs, k):
    """Spread k picks across the whole list. A head-slice would sample the header."""
    if k <= 0 or not xs:
        return []
    if len(xs) <= k:
        return list(xs)
    step = len(xs) / k
    return [xs[int(i * step)] for i in range(k)]


def is_blanked(e):
    """Does the LISTING print this row with its identity removed?

    `subtreeName && !subtreeNameSole` is the collector's own flag for "this name is a
    concatenation of descendants' text AND some of those descendants are themselves kept
    entries", and `e.line` is then built with name/label/text emptied, plus
    `(container -- the text here belongs to the elements inside it)`. So the listing printed
    NO identity for this element, and "can find reach it by the identity the listing printed"
    has no question to ask. Measured on ynet: 864 of 3,214 entries (26.9%).
    """
    return bool(e.get("subtreeName")) and not bool(e.get("subtreeNameSole"))


def choose(compact, seen_idents, cap=CAP, new_cap=NEW_CAP, blanked_cap=BLANKED_CAP):
    """Split the entries into the two questions that can honestly be asked of them.

    WHY A LENGTH BOUND EXISTS AND WHY IT IS A SKIP RATHER THAN A TRUNCATION. ynet's
    `<body>` carries an assembled name of 29,422 characters, and `find` takes **144
    seconds** on it -- one probe eating a whole site's budget, which is how the first smoke
    run lost its three largest sites to a timeout and would have left a sample of easy
    pages reporting a flattering number. Among rows the listing actually PRINTS, the
    longest identity on that page is 503 characters and the median is 21. Truncating would
    ask a different question and could manufacture a false miss (PRINCIPLES 5's rule, one
    level up: a silent cut is a lie the reader cannot detect), so an over-long printed
    identity is SKIPPED and counted instead.
    """
    new, carried, blanked, too_long = [], [], [], 0
    for e in compact:
        q = MF.identity_of(e)
        if len(q) < 2:                       # nothing to ask with; a 1-char id is not a query
            continue
        if is_blanked(e):
            blanked.append(e)
            continue
        if len(q) > MAX_QUERY_CHARS:
            too_long += 1
            continue
        (new if _norm(q) not in seen_idents else carried).append(e)
    # At first paint every identity is new, so the reservation would only shrink the sample.
    pick_new = _stride(new, new_cap if carried else cap)
    pick_carried = _stride(carried, max(0, cap - len(pick_new)))
    return pick_new, pick_carried, _stride(blanked, blanked_cap), too_long, len(blanked)


async def score_arm(page, arm, entries, listing, idx, probes, stage, site,
                    miss_sink, cap_misses=200):
    """Hand each probed element its OWN printed identity and ask `find` for it back.

    THE SHARED-GLOBAL RACE, AND WHY THIS IS A LOCK AND NOT A COMMENT.
    `find` takes (query, tabId) and reads its bridge from `mcp_server.STATE`, a MODULE
    GLOBAL. This probe runs several sites concurrently in ONE process, and the scoring loop
    yields (page.evaluate for the relation check). So between one site setting STATE and its
    next `find`, another site's coroutine can install ITS entries -- and `find` then scores
    the query against a different page, returning "No elements matched" for an element that
    is plainly present.

    IT IS NOT HYPOTHETICAL: it produced a clean, plausible, WRONG result. The `full` arm read
    0.5806 against `compact`'s 1.0000 on the tab rows, which reads as "the extra media rows
    in detail=full crowd real controls out of find's bounded result set" and would have been
    published as a finding about the product. Re-deriving it on a single page (PRINCIPLES 8)
    showed both arms matching, every time.

    The lock serialises SCORING only; page loads and interactions still overlap, and `find`
    is CPU-bound so the GIL was serialising it anyway. The `bridge_race` counter is the
    detector, because a correctness argument about yield points is a claim and PRINCIPLES 18
    says a claim in a comment needs the same evidence as a claim in a message.
    """
    async with _SCORE_LOCK:
        return await _score_arm(page, arm, entries, listing, idx, probes, stage, site,
                                miss_sink, cap_misses)


async def _score_arm(page, arm, entries, listing, idx, probes, stage, site,
                     miss_sink, cap_misses=200):
    counts = collections.Counter()
    for e in entries:
        q = MF.identity_of(e)
        if len(q) >= 2:
            counts[_norm(q)] += 1
    fb = MF._FB(entries, listing)
    agg = collections.Counter()
    for e, pop, kind in probes:
        await asyncio.sleep(0)   # `find` is synchronous CPU; without a yield one heavy site
        mm = str(e.get("mmid"))  # starves every concurrent one AND its own asyncio timeout
        q = MF.identity_of(e)
        if MF.ms.STATE.get("bridge") is not fb:
            # Under the lock this can only be the FIRST probe of this call. Anywhere else it
            # means something reinstalled the global mid-loop and the lock is not holding.
            if agg["tried"] or agg["b_tried"]:
                agg["bridge_race"] += 1
            MF.ms.STATE["bridge"] = fb
        if kind == "blanked":
            # A DIFFERENT QUESTION, ASKED OF A ROW THE LISTING DELIBERATELY BLANKS.
            # The blanking rule's own justification is that the text stays findable through
            # the contributors, which ARE kept entries -- so the agent-relevant outcome is
            # whether asking for those words returns this element OR anything inside it,
            # which is the descendant reasoning #18/#73 use on Mind2Web. The query is bounded
            # because the full string is not something the listing ever showed anyone.
            # BOUND ONLY WHEN IT IS TOO LONG. The first version applied `rsplit` to the
            # slice unconditionally, so a 12-character identity lost its last token:
            # `정상가 16,900원` was asked as `정상가`, which matches nothing, and 6 of the
            # first smoke's 14 "unreachable" blanked rows were that cut rather than the page.
            qb = q if len(q) <= BLANKED_QUERY_CHARS else (
                q[:BLANKED_QUERY_CHARS].rsplit(" ", 1)[0] or q[:BLANKED_QUERY_CHARS])
            agg["b_tried"] += 1
            try:
                out = str(await MF._find(query=qb, tabId=1))
            except Exception:
                agg["b_error"] += 1
                continue
            if re.search(r"\bref_" + re.escape(mm) + r"\b", out):
                agg["b_hit"] += 1
                continue
            rel = await MF._relation_returned(page, mm, out)
            if rel["descendant"]:
                agg["b_desc"] += 1
            else:
                agg["b_miss"] += 1
                # SPLIT BY WHETHER ANYTHING CAME BACK AT ALL, because the two have different
                # causes and only one of them is about reachability. `find` shows at most 20
                # rows, so on a page where 49 elements match the words, a real contributor
                # can sit in the 29 that were not listed -- that is the result cap, not an
                # unreachable identity.
                nrefs = len(set(re.findall(r"\bref_(\d+)\b", out)) - {mm})
                agg["b_miss_nomatch" if nrefs == 0 else "b_miss_outranked"] += 1
                if len(miss_sink) < cap_misses * 3:
                    miss_sink.append({
                        "site": site, "stage": stage, "arm": arm, "population": pop,
                        "mmid": mm, "tag": e.get("tag"),
                        "cls": ("blanked-text-no-match" if nrefs == 0
                                else "blanked-text-outranked"),
                        "identity": q[:140], "query": qb[:140],
                        "query_bounded": len(q) > BLANKED_QUERY_CHARS,
                        "refs_returned": nrefs, "search_space": len(entries),
                        "find_head": out.split("\n")[0][:140]})
            continue
        agg["tried"] += 1
        agg["tried_" + pop] += 1
        try:
            out = str(await MF._find(query=q, tabId=1))
        except Exception as ex:
            agg["error"] += 1
            if len(miss_sink) < cap_misses * 3:
                miss_sink.append({"site": site, "stage": stage, "arm": arm, "mmid": mm,
                                  "cls": "probe-error", "detail": str(ex)[:120]})
            continue
        shared = counts.get(_norm(q), 1) > 1
        if re.search(r"\bref_" + re.escape(mm) + r"\b", out):
            agg["hit"] += 1
            agg["hit_" + pop] += 1
            # THE INHERITED CONVENTION IS BIASED UPWARD AND THIS IS WHAT PRICES IT.
            # `measure_findability.py` tests for a hit BEFORE it tests for a shared
            # identity, so a contested probe that comes back counts in the numerator AND
            # the denominator while a contested probe that does not is excluded from
            # both. On the frozen corpus that is a rounding error; on a live page where
            # "Home", "Search" and "More" repeat it is not. Counted here so a
            # UNIQUE-IDENTITIES-ONLY rate can be reported beside the inherited one
            # rather than quietly replacing it (PRINCIPLES 8 -- a number that flatters
            # the system gets re-derived, including when the flattery is in the ruler).
            if shared:
                agg["hit_contested"] += 1
                agg["hit_contested_" + pop] += 1
            # Reached, but in which tier? `find` separates confident matches from a capped
            # weak list headed NO STRONG MATCH (#11d). Being in the weak tier is still
            # reachable -- the ref is there and an agent can act on it -- but it is a
            # materially different answer and folding the two would hide it.
            if "NO STRONG MATCH" in out:
                agg["hit_weak_tier"] += 1
            continue
        if shared:
            # CONTESTED. `find` returns a bounded set, so on a page with 30 identical
            # "upvote" links the probed one can legitimately fall outside it. That tracks how
            # repetitive a page is, not how reachable it is. Excluded from the denominator --
            # the frozen-corpus tool's convention, kept so the two numbers mean one thing.
            agg["contested"] += 1
            agg["contested_" + pop] += 1
            continue
        rel = await MF._relation_returned(page, mm, out)
        refs = set(re.findall(r"\bref_(\d+)\b", out)) - {mm}
        if rel["descendant"]:
            agg["desc"] += 1
            agg["desc_" + pop] += 1
            cls = "descendant-returned"
        elif rel["ancestor"]:
            agg["anc"] += 1
            agg["anc_" + pop] += 1
            cls = "ancestor-returned"
        else:
            agg["miss"] += 1
            agg["miss_" + pop] += 1
            cls = None
        printed = _identity_printed(idx, mm, q)
        if cls is None:
            if printed is None:
                cls = "row-not-printed(viewport-scoped)"
            elif printed is False:
                cls = "identity-absent-from-its-own-row"
            elif not refs:
                cls = "zero-match"
            else:
                cls = "outranked"
        if len(miss_sink) < cap_misses * 3:
            miss_sink.append({
                "site": site, "stage": stage, "arm": arm, "population": pop,
                "mmid": mm, "tag": e.get("tag"), "role": e.get("role"),
                "identity": q[:140], "cls": cls,
                "in_listing": printed is not None, "identity_printed": printed,
                "subtreeName": bool(e.get("subtreeName")),
                "subtreeNameSole": bool(e.get("subtreeNameSole")),
                "search_space": len(entries), "refs_returned": len(refs),
                "find_head": out.split("\n")[0][:140],
            })
    return dict(agg)


# --------------------------------------------------------------------------------------
async def one(browser, name, url, arch, lang, nstages, arms=ARMS):
    t0 = time.time()
    ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True,
                                    user_agent=None, locale="en-US")
    base = {"site": name, "url": url, "archetype": arch, "lang": lang}
    try:
        await ctx.add_init_script(path=ASG.TAG_JS)
        page = await ctx.new_page()
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=ASG.GOTO_MS)
            status = resp.status if resp else None
        except Exception as e:
            return dict(base, error="goto: " + str(e)[:120])
        try:
            await page.wait_for_load_state("networkidle", timeout=7000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)

        seen = set()
        misses = []
        stages = []

        async def measure(label):
            res = await page.evaluate(_collect_js())
            compact, full = _ents(res["compact"]), _ents(res["full"])
            idx = listing_index(res["listing"])
            pick_new, pick_carried, pick_blank, too_long, n_blank = choose(compact, seen)
            pop = "s0" if label == "s0" else "new"
            carried_pop = "s0" if label == "s0" else "carried"
            probes = ([(e, pop, "printed") for e in pick_new]
                      + [(e, carried_pop, "printed") for e in pick_carried]
                      + [(e, pop, "blanked") for e in pick_blank])
            row = {"stage": label, "entries_compact": len(compact), "entries_full": len(full),
                   "listing_chars": len(res["listing"]), "listing_rows": len(idx),
                   "probed": len(pick_new) + len(pick_carried), "probed_new": len(pick_new),
                   "probed_blanked": len(pick_blank), "entries_blanked": n_blank,
                   "skipped_identity_too_long": too_long,
                   "arms": {}}
            # The PROBE is always the COMPACT entry -- its mmid identifies the element and its
            # identity is the one the listing printed. Only the SEARCH SPACE changes between
            # arms, which is exactly the production situation: the listing a reader sees is
            # compact, and the array `find` scores over is full.
            for arm in arms:
                row["arms"][arm] = await score_arm(
                    page, arm, full if arm == "full" else compact,
                    res["listing"], idx, probes, label, name, misses)
            for e in compact:
                q = MF.identity_of(e)
                if len(q) >= 2:
                    seen.add(_norm(q))
            await asyncio.sleep(0)   # give the loop (and every other site's timeout) a turn
            return row, res

        try:
            row0, res0 = await measure("s0")
        except Exception as e:
            return dict(base, error="evaluate: " + str(e)[:160], status=status)
        stages.append(row0)
        out = dict(base, status=status, final_url=res0["url"],
                   title=(res0["title"] or "")[:80], stages=stages, misses=misses)

        used_kinds = collections.Counter()
        picks = []
        i, attempts = 0, 0
        while len(stages) <= nstages and attempts < nstages + 3:
            attempts += 1
            i = len(stages)
            step = {"n": i, "attempt": attempts}
            try:
                pick = await page.evaluate(
                    "(" + ASG.STAGE_PICK.strip() + ")(" + json.dumps(
                        {"usedKinds": dict(used_kinds),
                         "maxPerKind": ASG.MAX_PER_KIND}) + ")")
            except Exception as e:
                step["error"] = "pick: " + str(e)[:120]
                picks.append(step)
                break
            if not pick:
                step["none_left"] = True
                picks.append(step)
                break
            step.update({k: pick[k] for k in ("kind", "tag", "nested", "name") if k in pick})
            url_before = page.url
            try:
                step["mechanism"] = await ASG._act(page, pick)
            except Exception as e:
                step["act_error"] = str(e).split("\n")[0][:110]
            await page.wait_for_timeout(ASG.SETTLE_MS)
            if page.url.split("#")[0] != url_before.split("#")[0]:
                step["navigated"] = True
                picks.append(step)
                break
            try:
                v = await page.evaluate(ASG.STAGE_VERIFY)
            except Exception as e:
                step["error"] = "verify: " + str(e)[:120]
                picks.append(step)
                break
            used_kinds[pick["kind"]] += 1
            step["flipped"] = bool(v.get("flipped"))
            if not step["flipped"]:
                picks.append(step)
                continue
            try:
                row, _res = await measure("s%d" % i)
            except Exception as e:
                step["error"] = "measure: " + str(e)[:120]
                picks.append(step)
                break
            row["kind"] = pick["kind"]
            row["nested"] = pick.get("nested")
            stages.append(row)
            picks.append(step)
        out["picks"] = picks
        out["seconds"] = round(time.time() - t0, 1)
        return out
    finally:
        try:
            await ctx.close()
        except Exception:
            pass


def usable(r):
    """A read with nothing to probe cannot support a claim either way. ASG's bar, applied to
    the probe rather than to the DOM: a site is usable when stage 0 actually asked `find`
    something."""
    return ("error" not in r and r.get("stages")
            and r["stages"][0]["arms"].get("full", {}).get("tried", 0) >= 5)


# --------------------------------------------------------------------------------------
def _rate(c, pop=None):
    """strict = the element ITSELF came back, under the INHERITED convention."""
    sfx = ("_" + pop) if pop else ""
    tried = c.get("tried" + sfx, 0)
    cont = c.get("contested" + sfx, 0)
    den = tried - cont
    if den <= 0:
        return None, 0, 0, 0
    return (c.get("hit" + sfx, 0) / den, den, c.get("hit" + sfx, 0),
            c.get("desc" + sfx, 0) + c.get("anc" + sfx, 0))


def _rate_unique(c, pop=None):
    """The UNBIASED rate: every probe whose identity is shared is excluded from BOTH
    sides, so a contested element that happens to come back no longer counts as a hit
    while its unlucky twin is quietly dropped from the denominator."""
    sfx = ("_" + pop) if pop else ""
    den = (c.get("tried" + sfx, 0) - c.get("contested" + sfx, 0)
           - c.get("hit_contested" + sfx, 0))
    if den <= 0:
        return None, 0, 0
    hit = c.get("hit" + sfx, 0) - c.get("hit_contested" + sfx, 0)
    return hit / den, den, hit


def aggregate(rs):
    ok = [r for r in rs if usable(r)]
    per_stage = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    per_pop = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    per_kind = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    per_script = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    cls = collections.Counter()
    cls_by_pop = collections.defaultdict(collections.Counter)
    for r in ok:
        script = ASG.AGL.SCRIPT_OF.get(r["lang"], r["lang"])
        for st in r["stages"]:
            for arm, c in st["arms"].items():
                per_stage[st["stage"]][arm].update(c)
                per_kind[st.get("kind") or "(s0 first paint)"][arm].update(c)
                per_script[script][arm].update(c)
                for pop in ("s0", "new", "carried"):
                    if c.get("tried_" + pop):
                        per_pop[pop][arm].update(
                            {k.rsplit("_", 1)[0]: v for k, v in c.items()
                             if k.endswith("_" + pop)})
        for m in r.get("misses") or []:
            if m["arm"] == "full" and m.get("cls"):
                cls[m["cls"]] += 1
                cls_by_pop[m.get("population") or "?"][m["cls"]] += 1
    def _pack(d):
        return {k: {a: dict(c) for a, c in v.items()} for k, v in sorted(d.items())}
    races = sum(c.get("bridge_race", 0) for r in ok for st in r["stages"]
                for c in st["arms"].values())
    return {
        "sites_attempted": len(rs), "sites_usable": len(ok),
        # MUST BE ZERO. Non-zero means the scoring lock did not hold and every number in
        # this run was taken against some other site's entries part of the time.
        "bridge_races": races,
        "reads": sum(len(r["stages"]) for r in ok),
        "post_interaction_reads": sum(len(r["stages"]) - 1 for r in ok),
        "per_stage": _pack(per_stage), "per_population": _pack(per_pop),
        "per_kind": _pack(per_kind), "per_script": _pack(per_script),
        "printed_arm_totals": {
            k: sum(c.get(k, 0) for r in ok for st in r["stages"]
                   for a, c in st["arms"].items() if a == "full")
            for k in ("tried", "hit", "contested", "hit_contested", "desc", "anc", "miss",
                      "hit_weak_tier")},
        "blanked_arm_totals": {
            k: sum(c.get(k, 0) for r in ok for st in r["stages"]
                   for a, c in st["arms"].items() if a == "full")
            for k in ("b_tried", "b_hit", "b_desc", "b_miss", "b_miss_nomatch",
                      "b_miss_outranked")},
        "entries_blanked": sum(st.get("entries_blanked", 0) for r in ok
                               for st in r["stages"]),
        "entries_compact": sum(st.get("entries_compact", 0) for r in ok
                               for st in r["stages"]),
        "skipped_identity_too_long": sum(st.get("skipped_identity_too_long", 0) for r in ok
                                         for st in r["stages"]),
        "miss_classes_full_arm": dict(cls.most_common()),
        "miss_classes_by_population": {k: dict(v.most_common())
                                       for k, v in cls_by_pop.items()},
        "unusable": [{"site": r["site"],
                      "why": r.get("error") or "fewer than 5 probes at s0"}
                     for r in rs if not usable(r)],
    }


def report(paths):
    rs = []
    for p in paths:
        rs += json.loads(Path(p).read_text(encoding="utf-8"))["sites"]
    ok = [r for r in rs if usable(r)]
    agg = aggregate(rs)
    L = ["usable %d of %d attempted; %d reads (%d post-interaction); "
         "bridge_races=%d" % (len(ok), len(rs), agg["reads"],
                              agg["post_interaction_reads"], agg["bridge_races"]),
         "",
         "entries seen %d, of which the listing BLANKS %d (%.1f%%); printed identities "
         "skipped for length %d" % (
             agg["entries_compact"], agg["entries_blanked"],
             100.0 * agg["entries_blanked"] / max(1, agg["entries_compact"]),
             agg["skipped_identity_too_long"]),
         "printed arm %s" % json.dumps(agg["printed_arm_totals"]),
         "blanked arm %s" % json.dumps(agg["blanked_arm_totals"])]

    def table(title, groups):
        L.append("\n### " + title + "\n")
        L.append("| group | arm | probed | shared-identity | **strict (inherited)** | "
                 "+desc | +anc | **strict (unique only)** | weak tier | miss | "
                 "blanked rows probed | blanked text unreachable |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for k in sorted(groups):
            for arm in ARMS:
                c = groups[k].get(arm)
                if not c:
                    continue
                rate, den, hit, _x = _rate(c)
                if den <= 0:
                    continue
                ur, uden, uhit = _rate_unique(c)
                d, a = c.get("desc", 0), c.get("anc", 0)
                L.append("| %s | %s | %d | %d | **%.4f** (%d/%d) | %.4f | %.4f | "
                         "%s | %d | %d | %d | **%d** |"
                         % (k, arm, c.get("tried", 0),
                            c.get("contested", 0) + c.get("hit_contested", 0),
                            rate, hit, den, (hit + d) / den, (hit + d + a) / den,
                            ("**%.4f** (%d/%d)" % (ur, uhit, uden)) if ur is not None
                            else "n/a",
                            c.get("hit_weak_tier", 0), c.get("miss", 0),
                            c.get("b_tried", 0), c.get("b_miss", 0)))

    table("by stage", agg["per_stage"])
    table("by population (the question: is a REVEALED control harder to reach?)",
          agg["per_population"])
    table("by interaction kind", agg["per_kind"])
    table("by script family", agg["per_script"])
    L.append("\n### miss classes (full arm)\n")
    L.append("| class | n |")
    L.append("|---|---|")
    for k, v in agg["miss_classes_full_arm"].items():
        L.append("| %s | %d |" % (k, v))
    L.append("\n### miss classes by population (full arm)\n")
    for pop, d in sorted(agg["miss_classes_by_population"].items()):
        L.append("- **%s**: %s" % (pop, ", ".join("%s=%d" % kv for kv in d.items())))
    L.append("\nnot measured:")
    for u in agg["unusable"]:
        L.append("- %s: %s" % (u["site"], u["why"]))
    return "\n".join(L)


def drift(a_rs, b_rs):
    A = {r["site"]: r for r in a_rs if usable(r)}
    B = {r["site"]: r for r in b_rs if usable(r)}
    both = sorted(set(A) & set(B))
    out = {"sites_compared": len(both), "per_site": {}}
    deltas, same_stages = [], 0
    tot = {"a": collections.Counter(), "b": collections.Counter()}
    for n in both:
        x, y = A[n], B[n]
        if len(x["stages"]) == len(y["stages"]):
            same_stages += 1
        for who, r in (("a", x), ("b", y)):
            for st in r["stages"]:
                tot[who].update(st["arms"]["full"])
        rx, _d1, _h1, _o1 = _rate(
            sum((collections.Counter(s["arms"]["full"]) for s in x["stages"]),
                collections.Counter()))
        ry, _d2, _h2, _o2 = _rate(
            sum((collections.Counter(s["arms"]["full"]) for s in y["stages"]),
                collections.Counter()))
        if rx is not None and ry is not None:
            deltas.append(abs(rx - ry))
            out["per_site"][n] = {"strict": [round(rx, 4), round(ry, 4)],
                                  "stages": [len(x["stages"]), len(y["stages"])]}
    deltas.sort()
    ra, _da, _ha, _oa = _rate(tot["a"])
    rb, _db, _hb, _ob = _rate(tot["b"])
    out["pooled_strict"] = [round(ra, 4) if ra else None, round(rb, 4) if rb else None]
    out["pooled_abs_delta"] = round(abs((ra or 0) - (rb or 0)), 4)
    out["per_site_abs_delta_median"] = round(deltas[len(deltas) // 2], 4) if deltas else None
    out["per_site_abs_delta_p90"] = (round(deltas[int(len(deltas) * 0.9)], 4)
                                     if deltas else None)
    out["same_stage_count"] = same_stages
    return out


# --------------------------------------------------------------------------------------
# PROVING THE RULER FIRES. A run of high scores is worth nothing until the metric has been
# shown to report a miss for a control whose printed name does not match its element
# (PRINCIPLES 11, 15; #16's rule about a result that flatters the system).
# --------------------------------------------------------------------------------------
FIRE_HTML = r"""
<!doctype html><meta charset=utf-8><title>findability fixture</title>
<style>.pop{display:none} .pop.on{display:block}</style>
<button id=m aria-expanded="false" aria-haspopup="menu" aria-controls="menu">Open Menu</button>
<div id=menu role=menu class=pop>
  <button role=menuitem>Revealed Item Zeta</button>
  <!-- SOLE CARRIER (#74's ptable shape): an interactive container whose every
       text-contributing child declares nothing clickable, so the container is the only
       carrier of its own name and the listing PRINTS that name. Must be a HIT. -->
  <li tabindex="0" id=sole><b>36</b><abbr>Kr</abbr><em>Krypton</em><data>83.798</data></li>
  <!-- BORROWED-AND-BLANKED: the same assembled-name shape, but the contributors are
       themselves kept entries, so the listing prints the row with its name BLANKED. The
       metric must classify this rather than counting it as a plain unreachable row. -->
  <div id=borrowed tabindex="0"><a href="#x">Alpha Link</a><a href="#y">Beta Link</a></div>
</div>
<script>
 m.onclick = () => { const on = m.getAttribute('aria-expanded') === 'true';
   m.setAttribute('aria-expanded', String(!on)); menu.classList.toggle('on', !on); };
</script>
"""


async def _selftest():
    fails = []
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        ctx = await b.new_context(viewport=VIEWPORT)
        await ctx.add_init_script(path=ASG.TAG_JS)
        pg = await ctx.new_page()
        await pg.set_content(FIRE_HTML)
        await pg.wait_for_timeout(200)

        # Drive ONE declared interaction, exactly as the live run does.
        pick = await pg.evaluate("(" + ASG.STAGE_PICK.strip() + ")({})")
        if not pick or pick["kind"] != "menu-popup":
            fails.append("picker did not reach the menu: %r" % (pick,))
        await ASG._act(pg, pick)
        await pg.wait_for_timeout(200)
        v = await pg.evaluate(ASG.STAGE_VERIFY)
        if not v.get("flipped"):
            fails.append("fixture menu did not flip, so everything below is vacuous")

        res = await pg.evaluate(_collect_js())
        compact, full = _ents(res["compact"]), _ents(res["full"])
        idx = listing_index(res["listing"])
        if "Revealed Item Zeta" not in res["listing"]:
            fails.append("the interaction revealed nothing, so this proves nothing")

        def by_text(s):
            for e in compact:
                if s in (MF.identity_of(e) or ""):
                    return e
            return None

        # 1. A control REVEALED by the interaction is reachable by its printed identity.
        tgt = by_text("Revealed Item Zeta")
        sink = []
        if tgt is None:
            fails.append("revealed control absent from the structured array")
        else:
            c = await score_arm(pg, "full", full, res["listing"], idx, [(tgt, "new", "printed")],
                                "s1", "fixture", sink)
            if c.get("hit") != 1:
                fails.append("a revealed control was NOT reachable by its printed identity: %s"
                             % sink[:1])

        # 2. #74's SOLE-CARRIER shape, revealed by the interaction, must also be a hit.
        sole = by_text("Krypton")
        sink2 = []
        if sole is None:
            fails.append("sole-carrier tile absent from the structured array")
        else:
            c = await score_arm(pg, "full", full, res["listing"], idx, [(sole, "new", "printed")],
                                "s1", "fixture", sink2)
            if c.get("hit") != 1:
                fails.append("#74's sole-carrier shape unreachable post-interaction: %s"
                             % sink2[:1])

        # 3. THE PLANT. Take that same reachable control and make the printed name no longer
        #    match the element -- blank its identity in the array `find` searches, keep the
        #    query the listing printed. If the metric cannot see THAT, a run of zeros means
        #    nothing. This is the mutilation `--lossy` performs for the loss metric (#89).
        sink3 = []
        if tgt is not None:
            mutil = [dict(e, **({"name": "", "label": "", "text": "", "value": "",
                                 "placeholder": ""}
                                if str(e.get("mmid")) == str(tgt.get("mmid")) else {}))
                     for e in full]
            c = await score_arm(pg, "full", mutil, res["listing"], idx, [(tgt, "new", "printed")],
                                "s1", "fixture", sink3)
            if c.get("hit"):
                fails.append("PLANT DID NOT FIRE: the name was moved off the element and the "
                             "metric still scored a hit")

        # 3b. #74'S ACTUAL DEFECT, REPRODUCED AT A POST-INTERACTION STAGE. Check 3 plants a
        #     generic mismatch; this plants the specific one. Before #74, `subtreeNameSole`
        #     did not exist, so a sole-carrier tile was treated as a borrowed name and
        #     `find` blanked it -- 118 ptable.com tiles present in every presence metric and
        #     unreachable by their verbatim label. Stripping the flag from the entry puts
        #     `find` back in exactly that state without touching the extension, and the
        #     staged metric must score it a MISS. If it does not, this probe could not have
        #     caught the defect it exists for.
        sink3b = []
        if sole is not None:
            pre74 = [dict(e, subtreeNameSole=False) if str(e.get("mmid")) == str(sole.get("mmid"))
                     else e for e in full]
            c = await score_arm(pg, "full", pre74, res["listing"], idx,
                                [(sole, "new", "printed")], "s1", "fixture", sink3b)
            if c.get("hit"):
                fails.append("THE #74 SHAPE WAS NOT CAUGHT: with subtreeNameSole stripped "
                             "(the pre-#74 state) the sole carrier still scored a hit, so "
                             "this probe could not have caught the defect it exists for")

        # 4. A row the listing BLANKS must be routed to its own question and must not be
        #    asked for a string the listing never printed. The fixture's `#borrowed` div
        #    takes its name from two anchors that are themselves kept entries, which is
        #    exactly the condition the blanking rule exists for.
        bor = next((e for e in compact if is_blanked(e)), None)
        sink4 = []
        c4 = {}
        if bor is None:
            fails.append("fixture produced no blanked-container row; class 4 is vacuous")
        else:
            if _identity_printed(idx, bor.get("mmid"), MF.identity_of(bor)):
                fails.append("a row flagged blanked still printed its identity: the flag and "
                             "the listing disagree, so the split is not what it claims")
            c4 = await score_arm(pg, "full", full, res["listing"], idx,
                                 [(bor, "new", "blanked")], "s1", "fixture", sink4)
            if not (c4.get("b_hit") or c4.get("b_desc")):
                fails.append("the blanking rule's own promise failed: asking for the text "
                             "returned neither the container nor anything inside it: %s"
                             % (sink4[:1],))
            if c4.get("tried"):
                fails.append("a blanked row was scored in the PRINTED denominator")

        await b.close()
    print("selftest", "PASS" if not fails else "FAIL")
    print(json.dumps({"failures": fails, "plant_record": sink3[:1],
                      "pre74_record": sink3b[:1],
                      "blanked_arm": c4, "blanked_record": sink4[:1]},
                     indent=1, ensure_ascii=False))
    return 0 if not fails else 1


async def fire_one(browser, name, url, arch, lang, nstages, k=8):
    """THE LIVE FIRING PROOF. Drive the stages on a real site, then at the deepest stage move
    K controls' identities off their elements (blank them in the array `find` searches, keep
    the query the listing printed) and require every one to stop being a hit, while the
    untouched controls keep theirs. A fixture is what you thought of; this is not."""
    ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True,
                                    locale="en-US")
    try:
        await ctx.add_init_script(path=ASG.TAG_JS)
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=ASG.GOTO_MS)
        try:
            await page.wait_for_load_state("networkidle", timeout=7000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)
        used, depth = collections.Counter(), 0
        for _ in range(nstages):
            pick = await page.evaluate("(" + ASG.STAGE_PICK.strip() + ")(" + json.dumps(
                {"usedKinds": dict(used), "maxPerKind": ASG.MAX_PER_KIND}) + ")")
            if not pick:
                break
            before = page.url
            try:
                await ASG._act(page, pick)
            except Exception:
                pass
            await page.wait_for_timeout(ASG.SETTLE_MS)
            if page.url.split("#")[0] != before.split("#")[0]:
                break
            v = await page.evaluate(ASG.STAGE_VERIFY)
            used[pick["kind"]] += 1
            if v.get("flipped"):
                depth += 1
        res = await page.evaluate(_collect_js())
        compact, full = _ents(res["compact"]), _ents(res["full"])
        idx = listing_index(res["listing"])
        # Probe only UNIQUE identities: a contested one is excluded from the denominator on
        # both sides and would make the check look like it fired when it did not.
        cnt = collections.Counter(_norm(MF.identity_of(e)) for e in full
                                  if len(MF.identity_of(e)) >= 2)
        cands = [e for e in compact
                 if 2 <= len(MF.identity_of(e)) <= MAX_QUERY_CHARS and not is_blanked(e)
                 and cnt.get(_norm(MF.identity_of(e)), 0) == 1]
        step = max(1, len(cands) // max(1, k))
        chosen = cands[::step][:k]
        sink = []
        clean = await score_arm(page, "full", full, res["listing"], idx,
                                [(e, "new", "printed") for e in chosen], "fire", name, sink)
        tgt = {str(e.get("mmid")) for e in chosen}
        mutil = [dict(e, **({"name": "", "label": "", "text": "", "value": "",
                             "placeholder": ""} if str(e.get("mmid")) in tgt else {}))
                 for e in full]
        sink2 = []
        after = await score_arm(page, "full", mutil, res["listing"], idx,
                                [(e, "new", "printed") for e in chosen], "fire", name, sink2)
        return {"site": name, "stages_reached": depth, "probed": len(chosen),
                "entries": len(full),
                "clean_hits": clean.get("hit", 0), "mutilated_hits": after.get("hit", 0),
                "mutilated_misses": after.get("miss", 0) + after.get("desc", 0)
                + after.get("anc", 0),
                "fired": clean.get("hit", 0) > 0 and after.get("hit", 0) == 0}
    finally:
        await ctx.close()


async def run_fire(sites, nstages, k):
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        out = []
        for s in sites:
            try:
                out.append(await asyncio.wait_for(fire_one(b, *s, nstages, k), 200))
            except Exception as e:
                out.append({"site": s[0], "error": str(e)[:140]})
        await b.close()
    return out


async def run_pass(sites, conc, nstages, arms):
    sem = asyncio.Semaphore(conc)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        async def go(s):
            async with sem:
                try:
                    return await asyncio.wait_for(one(browser, *s, nstages, arms), 300)
                except Exception as e:
                    return {"site": s[0], "url": s[1], "archetype": s[2], "lang": s[3],
                            "error": "timeout/" + str(e)[:80]}
        res = await asyncio.gather(*(go(s) for s in sites))
        await browser.close()
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--fire", action="store_true",
                    help="live firing proof: move identities off their elements and "
                         "require the metric to report it")
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--pool", default="usable85", choices=("usable85", "all"))
    ap.add_argument("--stages", type=int, default=4)
    ap.add_argument("--conc", type=int, default=6)
    ap.add_argument("--arms", nargs="*", default=list(ARMS))
    ap.add_argument("--every", type=int, default=0,
                    help="take every Nth site of the pool (drift subset, chosen by position)")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--report", nargs="+")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    if a.selftest:
        return asyncio.run(_selftest())
    if a.report:
        print(report(a.report))
        return 0
    sites = ASG._pool(a.pool, a.only)
    if a.every:
        sites = sites[::a.every]
    bad = ASG._check_sample(sites)
    if bad:
        print("SAMPLE CONTAINS EXCLUDED HOSTS (frozen corpus / bench_turns / bench_flows):",
              bad)
        return 2
    if a.list:
        for s in sites:
            print(*s, sep="\t")
        print(len(sites), "sites;", len(ASG.AGL.EXCLUDED), "excluded hosts checked")
        return 0
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.fire:
        res = asyncio.run(run_fire(sites, a.stages, a.k))
        (out / "fire.json").write_text(json.dumps(res, indent=1, ensure_ascii=False),
                                       encoding="utf-8")
        for r in res:
            print(json.dumps(r, ensure_ascii=False))
        bad = [r["site"] for r in res if "error" not in r and not r.get("fired")]
        print("FIRE:", "PASS" if res and not bad else "FAIL",
              "- sites where moving the identity did NOT turn hits into misses:", bad)
        return 0 if (res and not bad) else 1
    runs = [asyncio.run(run_pass(sites, a.conc, a.stages, tuple(a.arms)))]
    if a.compare:
        runs.append(asyncio.run(run_pass(sites, a.conc, a.stages, tuple(a.arms))))
    for i, rs in enumerate(runs):
        agg = aggregate(rs)
        (out / f"pass{i}.json").write_text(
            json.dumps({"aggregate": agg, "sites": rs}, indent=1, ensure_ascii=False),
            encoding="utf-8")
        print(f"pass {i}: usable {agg['sites_usable']}/{agg['sites_attempted']} "
              f"reads={agg['reads']} post={agg['post_interaction_reads']} "
              f"bridge_races={agg['bridge_races']}"
              + ("  *** NON-ZERO: the scoring lock did not hold, discard this run ***"
                 if agg["bridge_races"] else ""))
        for pop, arms in agg["per_population"].items():
            c = arms.get("full")
            if c:
                r, den, hit, other = _rate(c)
                ur, uden, uhit = _rate_unique(c)
                print(f"   {pop:<8} full strict {hit}/{den} = "
                      f"{(r if r is not None else float('nan')):.4f}  "
                      f"(+{other} desc/anc)  unique-only "
                      f"{uhit}/{uden} = {(ur if ur is not None else float('nan')):.4f}")
    if a.compare:
        d = drift(runs[0], runs[1])
        (out / "drift.json").write_text(json.dumps(d, indent=1), encoding="utf-8")
        print("DRIFT:", json.dumps({k: v for k, v in d.items() if k != "per_site"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

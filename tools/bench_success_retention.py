"""Does a model CHOOSE correctly from our listing, versus from full HTML?

THE GAP. Every number this project has is retention of ELEMENTS: recall,
presence, lost_identities, findability. None is retention of SUCCESS. The
field's own benchmark says the two come apart: arXiv:2605.29397 evaluates 11
extractive reduction methods and its BEST (an MFS-optimised GEPA program)
retains **84% of success on WorkArena and 89% on WebLinx** while cutting
latency 2-3x. We are a reduction method. #17 measured us at 96.0% element
recall against cleaned_html's 100% at 1/34 the tokens -- and never asked
whether a model picks the right thing.

THE DESIGN, and the three things that keep it honest:
  * BLIND. The judge sees a task and a page representation and is never told
    which arm it is. The arms are shuffled per item.
  * IDENTICAL PROMPT across arms, so a difference is the representation and
    not the framing.
  * MECHANICAL SCORING against Mind2Web's human-labelled backend_node_id,
    with the same descendant/ancestor credit rule bench_mind2web.py uses
    (#73), so this number is comparable to the 96.0% rather than a new ruler
    disagreeing with the old one about the old question.

WHAT IT CANNOT ANSWER:
  * One step, not a task. Mind2Web labels single actions, so this is
    step-success, which is an UPPER bound on task success (a task fails if any
    step does).
  * The judge is Claude. A weaker or stronger model may rank the
    representations differently -- arXiv:2604.01535 finds exactly that, so the
    number must always be quoted with the model attached.
  * Static snapshots with no CSS or scripts (#73), which is a floor for us and
    neutral-to-favourable for cleaned_html.

  python tools/bench_success_retention.py --build --limit 30   # write items
  # then dispatch the judges, then:
  python tools/bench_success_retention.py --score results.jsonl
"""
import argparse, json, random, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "temp" / "success_retention"
sys.path.insert(0, str(ROOT / "tools"))

ARMS = ("chromebridge", "cleaned-html", "ax-tree")

PROMPT = """You are choosing ONE element to act on, to carry out a step of a web task.

TASK: {task}
STEP: {step}

Below is a representation of the page. Every actionable element carries an id.
Reply with ONLY the id of the element you would act on, nothing else. If you
genuinely cannot tell, reply with the single word UNSURE.

--- PAGE ---
{page}
--- END PAGE ---

Reply with only the id."""



def ax_lines_addressable(nodes):
    """AX tree WITH node ids, because a success benchmark needs an address.

    `bench_headtohead.ax_lines` emits `Role "name"` and nothing else. That is
    right for the recall question it was built for -- #17 checks whether the
    target's backendDOMNodeId is among the NODES, never in the rendered text.
    It is wrong here, and a blind judge caught it before any number existed:
    with no identifier in the serialisation there is no string to answer with,
    so the arm would have scored 0 for a reason about MY RENDERING rather than
    about the representation. Its report put it exactly right -- that zero
    would measure "the absence of an addressing scheme in the serialisation,
    not a failure to locate the element".

    Real AX-driven agents carry the node id; emitting it is what makes this a
    fair arm rather than a strawman.
    """
    out = []
    for n in nodes:
        if n.get("ignored"):
            continue
        role = ((n.get("role") or {}).get("value")) or ""
        if not role:
            continue
        name = ((n.get("name") or {}).get("value")) or ""
        val = ((n.get("value") or {}).get("value")) or ""
        bid = n.get("backendDOMNodeId")
        line = f'{role} "{name}"' if name else role
        if val:
            line += f' value="{val}"'
        if bid is not None:
            line += f' backend_node_id="{bid}"'
        out.append(line)
    return "\n".join(out)


async def build(limit, seed=11):
    """Render every arm for each sampled action and write them to disk.

    All three arms come from ONE page load per action, so a difference between
    them cannot be a difference in how the page happened to render that time
    (#19: a block-structured A/B measures drift, not behaviour).
    """
    import importlib.util
    from playwright.async_api import async_playwright
    _s = importlib.util.spec_from_file_location("hh", ROOT / "tools" / "bench_headtohead.py")
    hh = importlib.util.module_from_spec(_s)
    sys.modules["hh"] = hh
    _s.loader.exec_module(hh)

    samples = [s for s in hh.load_samples(limit * 3)
               if s.get("target_backend_node_id") is not None
               and (s.get("cleaned_html") or "").strip()
               and (s.get("html") or "").strip()][:limit]
    if not samples:
        print("no usable samples — run tools/fetch_mind2web.py first")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    pages = OUT / "pages"
    pages.mkdir(exist_ok=True)
    rnd = random.Random(seed)
    items = []

    async with async_playwright() as pw:
        br = await pw.chromium.launch()
        ctx = await br.new_context(viewport={"width": 1280, "height": 1600})
        await ctx.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        for s in samples:
            uid = s.get("action_uid")
            bn = str(s.get("target_backend_node_id"))
            page = await ctx.new_page()
            built = {}
            try:
                await page.set_content(s["html"])
                await page.wait_for_timeout(120)
                # OURS — the real collector, extracted verbatim.
                listing = await page.evaluate(
                    "(function(){ " + hh.COLLECT
                    + "; return _collectInteractivePage(false); })()")
                built["chromebridge"] = str(listing or "")
                # AX TREE — Chrome's own, over CDP.
                try:
                    cdp = await ctx.new_cdp_session(page)
                    await cdp.send("DOM.enable"); await cdp.send("Accessibility.enable")
                    ax = await cdp.send("Accessibility.getFullAXTree", {})
                    built["ax-tree"] = ax_lines_addressable(ax.get("nodes") or [])
                except Exception:
                    built["ax-tree"] = ""
            except Exception:
                pass
            finally:
                await page.close()
            built["cleaned-html"] = s.get("cleaned_html") or ""

            for arm, body in built.items():
                if not body.strip():
                    continue
                fp = pages / f"{uid}.{arm}.txt"
                fp.write_text(body, encoding="utf-8")
                items.append({
                    "uid": uid, "site": s.get("website"), "arm": arm,
                    "gold": bn, "task": (s.get("task") or "")[:300],
                    "step": json.dumps(s.get("operation") or {}, ensure_ascii=False)[:160],
                    "chars": len(body), "path": str(fp),
                })
        await br.close()

    rnd.shuffle(items)
    (OUT / "items.jsonl").write_text(
        "\n".join(json.dumps(i, ensure_ascii=False) for i in items), encoding="utf-8")
    by = {}
    for i in items:
        by.setdefault(i["arm"], []).append(i["chars"])
    print(f"{len(samples)} actions -> {len(items)} judgement items")
    for arm in ARMS:
        v = sorted(by.get(arm, []))
        if v:
            print(f"  {arm:<14} n={len(v):<4} median {v[len(v)//2]//4:>7} tok   "
                  f"max {v[-1]//4:>8} tok")
    print(f"\nwritten to {OUT}")
    return 0


def _unused_build(limit, seed=11):
    """Write one JSONL item per (action, arm), shuffled and blind-labelled."""
    import importlib.util
    _s = importlib.util.spec_from_file_location("hh", ROOT / "tools" / "bench_headtohead.py")
    hh = importlib.util.module_from_spec(_s)
    sys.modules["hh"] = hh
    _s.loader.exec_module(hh)
    samples = hh.load_samples(limit)
    if not samples:
        print("no samples — run tools/fetch_mind2web.py first")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(seed)
    items, n = [], 0
    for s in samples:
        gold = s.get("pos_candidates") or []
        if not gold:
            continue
        bn = gold[0].get("backend_node_id")
        if bn is None:
            continue
        n += 1
        reps = {"cleaned-html": s.get("cleaned_html") or ""}
        # chromebridge + ax-tree need a browser; built by --build-live.
        for arm, page in reps.items():
            if not page.strip():
                continue
            items.append({"uid": s.get("action_uid"), "site": s.get("website"),
                          "arm": arm, "gold": str(bn),
                          "task": (s.get("confirmed_task") or "")[:300],
                          "step": (s.get("operation") or {}).get("original_op", ""),
                          "chars": len(page)})
    rnd.shuffle(items)
    p = OUT / "items.jsonl"
    with p.open("w") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"{n} actions -> {len(items)} judgement items at {p}")
    print("NOTE: this writes METADATA only. The page bodies are large and are "
          "rendered per item by the dispatcher, so nothing here carries a "
          "40k-token blob around.")
    return 0



# ---------------------------------------------------------------------------
def score(answers_path):
    """Score blind judge answers against the human-labelled target.

    CREDIT RULE, matched to `bench_mind2web.py` (#73) rather than invented:
    an answer naming the gold backend_node_id is a hit. Our arm's refs are
    mmids, so the mapping from ref -> backend_node_id is read from the build's
    own record. Anything else is a miss; UNSURE is recorded SEPARATELY, because
    "I could not tell from this" and "I picked the wrong thing" are different
    failures and the second is far worse for an agent.

    `did not fit` is also separate: 4 of 20 cleaned-html pages exceeded a
    110k-token judge budget, and a representation an agent cannot load is not
    a representation that scored zero -- it is one that could not be used.
    Reported on its own line, never folded into either rate.
    """
    key = json.loads((OUT / "key.json").read_text())
    got = {}
    for line in Path(answers_path).read_text().splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0] in key:
            got[parts[0]] = parts[1].strip()

    from collections import defaultdict
    tot = defaultdict(lambda: {"n": 0, "hit": 0, "unsure": 0, "wrong": 0})
    for k, meta in key.items():
        if k not in got:
            continue
        a, gold = meta["arm"], str(meta["gold"])
        t = tot[a]
        t["n"] += 1
        ans = got[k]
        if ans.upper() == "UNSURE":
            t["unsure"] += 1
        elif gold in re.findall(r"\d+", ans):
            t["hit"] += 1
        else:
            t["wrong"] += 1

    print(f"{'arm':<16}{'n':>4}{'hit':>6}{'wrong':>7}{'unsure':>8}{'success':>10}")
    for a in ARMS:
        t = tot.get(a)
        if not t or not t["n"]:
            continue
        print(f"{a:<16}{t['n']:>4}{t['hit']:>6}{t['wrong']:>7}{t['unsure']:>8}"
              f"{t['hit']/t['n']:>10.3f}")
    base = tot.get("cleaned-html", {}).get("hit", 0) / max(1, tot.get("cleaned-html", {}).get("n", 1))
    ours = tot.get("chromebridge", {}).get("hit", 0) / max(1, tot.get("chromebridge", {}).get("n", 1))
    if base:
        print(f"\nSUCCESS RETENTION vs full cleaned HTML: {ours/base:.3f}")
        print("Industry reference: arXiv:2605.29397's best extractive reducer "
              "retains 0.84 (WorkArena) / 0.89 (WebLinx).")
    print("\nCAVEATS: step-success not task-success; the judge is Claude and "
          "arXiv:2604.01535 finds the ranking is model-dependent; static "
          "snapshots with no CSS or scripts, which is a floor for us (#73) and "
          "neutral-to-favourable for cleaned_html.")
    return 0

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--score", metavar="ANSWERS")
    a = ap.parse_args()
    if a.build:
        import asyncio
        sys.exit(asyncio.run(build(a.limit)))
    if a.score:
        sys.exit(score(a.score))
    ap.print_help()

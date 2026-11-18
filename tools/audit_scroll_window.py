"""Of the ordinal-bearing descriptors that NOTHING can witness, how many sit in a
scrolling WINDOW?

#90 measured the one record/replay case still able to act wrongly without
refusing: a VIRTUALISED list. 200 records, a rendered window of ten, recorded
REC-1003, replayed REC-1053, no refusal. The composition check that catches a
row being added or removed (`len(hits) != of`) CANNOT FIRE there, because the
crowd is the window and a window's size does not change when it scrolls.

The recorder already WARNS at record time -- `positional:` names the scrolling
window as one of three mechanisms -- so this is not silent in the artefact. What
it cannot do is REFUSE at replay.

THE CANDIDATE, and the only reason it is worth asking about: a crowd that lives
inside an ancestor whose content is taller than its box is, by the page's own
geometry, a WINDOW onto something larger. That is the exact condition under
which an ordinal means a screen position rather than a record. #72 rejected
refusing ALL unwitnessed ordinals because it would pause ~14% of descriptors on
an UNCHANGED page -- losing the feature rather than paying a safety cost. This
would be a SUBSET of those.

SO THE QUESTION IS PARETO, NOT CORRECTNESS, and it is the question #41 and #44
exist to force: what does the refusal COST on pages that are behaving, and what
share of the unwitnessed population does it even reach? If the subset is tiny
the fix is unreachable in practice and should be recorded DON'T BUILD with the
number; if it is large the refusal is worth three halves of plumbing (a
collector field, a descriptor field, a runner branch).

NOTHING IS BUILT FROM THIS PROBE. It reports and exits.

WHAT IS MEASURED, per frozen site:
  crowds            tied groups of >=2 entries identical in tag/role/type/name
  unwitnessed       ...with no distinguishing text atom and no distinguishing
                    attribute atom, i.e. the population #72/#83 leave on position
  in a scroller     ...whose members' common ancestor chain contains an element
                    with scrollHeight > clientHeight + 4 and a computed
                    overflow of auto/scroll (a DECLARED overflow plus a measured
                    overflow, which is what "window" means)
  windowed          ...and where the scroller is taller than its box by MORE
                    THAN ONE MEMBER's height, i.e. content is genuinely out of
                    view rather than a 2px rounding

Run:  .venv/bin/python tools/audit_scroll_window.py [--sites N]
"""
import argparse, asyncio, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
FROZEN = ROOT / "temp" / "frozen"

from _extract import extract                      # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = extract("_collectInteractivePage", BG, verify=True)

PROBE = r"""
(ents) => {
  const reg = window.__mmidReg || new Map();
  const el = (m) => reg.get(String(m)) || document.querySelector(`[mmid='${m}']`);
  const key = (e) => [e.tag, e.role || '', e.type || '', e.name || ''].join('\u0001');
  // tied crowds: >=2 entries identical in every declared identity field
  const by = new Map();
  for (const e of ents) {
    if (!e || !e.mmid) continue;
    const k = key(e);
    if (!by.has(k)) by.set(k, []);
    by.get(k).push(e);
  }
  const txt = (n) => (n && n.textContent || '').replace(/\s+/g, ' ').trim();
  const atomsOf = (m) => {
    const e = el(m); if (!e) return null;
    const out = new Set();
    // record = the child of the crowd's LCA containing this member; approximated
    // here by the nearest ancestor holding text the member itself does not.
    let p = e, hops = 0;
    while (p && hops++ < 6) {
      const t = txt(p);
      if (t && t !== txt(e)) { for (const w of t.split(' ')) if (w) out.add(w); break; }
      p = p.parentElement;
    }
    for (const a of (e.attributes || [])) {
      if (a.name === 'class' || a.name === 'style' || a.name === 'mmid') continue;
      out.add(a.name + '=' + a.value);
    }
    return out;
  };
  const scrollerOf = (m) => {
    let p = el(m); let hops = 0;
    while (p && p !== document.body && hops++ < 12) {
      try {
        const cs = getComputedStyle(p);
        const ov = (cs.overflowY || '') + ' ' + (cs.overflow || '');
        if (/auto|scroll/.test(ov) && p.scrollHeight > p.clientHeight + 4) return p;
      } catch (e) {}
      p = p.parentElement;
    }
    return null;
  };
  let crowds = 0, unwit = 0, inScroll = 0, windowed = 0;
  const examples = [];
  for (const [, members] of by) {
    if (members.length < 2) continue;
    crowds++;
    // unwitnessed: no member has an atom no other member has
    const sets = members.map(m => atomsOf(m.mmid));
    if (sets.some(s => s === null)) continue;
    let anyUnique = false;
    for (let i = 0; i < sets.length && !anyUnique; i++) {
      for (const a of sets[i]) {
        if (!sets.some((s, j) => j !== i && s.has(a))) { anyUnique = true; break; }
      }
    }
    if (anyUnique) continue;
    unwit++;
    const sc = scrollerOf(members[0].mmid);
    if (!sc) continue;
    inScroll++;
    let mh = 0;
    try { mh = el(members[0].mmid).getBoundingClientRect().height || 0; } catch (e) {}
    if (sc.scrollHeight > sc.clientHeight + Math.max(mh, 8)) {
      windowed++;
      if (examples.length < 3) examples.push({
        name: (members[0].name || '').slice(0, 30), n: members.length,
        sh: sc.scrollHeight, ch: sc.clientHeight, tag: sc.tagName.toLowerCase() });
    }
  }
  return { crowds, unwit, inScroll, windowed, examples };
}
"""


async def one(browser, har):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
    await ctx.route_from_har(har, not_found="abort", update=False)
    pg = await ctx.new_page()
    try:
        start = json.loads(har.read_text(encoding="utf-8"))["log"]["entries"][0]["request"]["url"]
        await pg.goto(start, wait_until="domcontentloaded", timeout=25000)
        await pg.wait_for_timeout(1200)
        ents = await pg.evaluate("(function(){ " + COLLECT
                                 + "; return _collectInteractivePage(true); })()")
        if not isinstance(ents, list) or not ents:
            return None
        return await pg.evaluate(PROBE, ents)
    except Exception:
        return None
    finally:
        await ctx.close()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", type=int, default=30)
    a = ap.parse_args()
    hars = sorted(FROZEN.glob("*.har"))[: a.sites]
    if not hars:
        print("no frozen corpus — python tools/freeze_corpus.py"); return 2
    tot = {"crowds": 0, "unwit": 0, "inScroll": 0, "windowed": 0}
    ok = 0
    ex = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for i, h in enumerate(hars, 1):
            r = await one(b, h)
            if not r:
                print(f"  [{i:>3}] {h.stem:<22} skipped"); continue
            ok += 1
            for k in tot: tot[k] += r.get(k, 0)
            ex += r.get("examples", [])
            print(f"  [{i:>3}] {h.stem:<22} crowds={r['crowds']:<4} unwitnessed={r['unwit']:<4} "
                  f"in-scroller={r['inScroll']:<3} WINDOWED={r['windowed']}")
        await b.close()
    u = tot["unwit"] or 1
    print(f"\n{'=' * 74}\nSCROLL-WINDOW REACH — {ok} sites\n{'=' * 74}")
    print(f"  tied crowds            {tot['crowds']}")
    print(f"  unwitnessed            {tot['unwit']}")
    print(f"  ...inside a scroller   {tot['inScroll']}  ({100*tot['inScroll']/u:.1f}% of unwitnessed)")
    print(f"  ...genuinely WINDOWED  {tot['windowed']}  ({100*tot['windowed']/u:.1f}% of unwitnessed)")
    print(f"\n  A refusal keyed on 'windowed' would reach {100*tot['windowed']/u:.1f}% of the")
    print(f"  population #72 left on position, and cost a pause on exactly those.")
    for e in ex[:6]:
        print(f"    e.g. {e['n']}x {e['name']!r} in <{e['tag']}> {e['ch']}px box / {e['sh']}px content")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

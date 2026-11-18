"""Does a childList record that only moves TEXT NODES belong in the structural tier?

THE QUESTION. `READINESS.md` 5(b) states the gap in its own words: *"a ticker
that updates via `textContent` arrives as `childList` -- Chrome records it as
remove+add of a text node -- so it trips the STRONG banner."* The adversarial
audit then measured the consequence: 6 steady-state false-busy reads, all of
them a `textContent` ticker or a live-value grid reported as *"Elements were
added, removed or re-texted ... do NOT conclude something is absent"* on content
that never changes again. An always-on warning is #15's noise, which #43 deleted
`readyState` for.

THE CANDIDATE is not a new heuristic. The ring's own vocabulary already has a
`text` kind (`characterData`), and the banner's own words define `structural` as
*elements* being added or removed. A `textContent =` assignment removes one Text
node and inserts another, so it is a RE-TEXT that the ring is filing as
structural. `Node.nodeType` decides it -- a declaration, no threshold, no class
name, no wordlist.

HOW IT IS MEASURED, and why there is no drift to subtract. The reclassification
happens at RECORD time, so the naive A/B would be two page loads. Instead ONE
patched ring stores a `retext` bit beside each record and the query reports it,
so **both arms are computed from the same records at the same instant** -- the
shipped reading is `structural`, the candidate reading is
`structural - retext` / `text + retext`. Run-order drift cannot align with an
arm that does not have its own run (PRINCIPLES 10).

The 18 shapes, their routing and their objective ground-truth signatures are
IMPORTED from `audit_readiness_adversarial.py` rather than copied, so the two
probes answer different questions about the same pages (PRINCIPLES 17).

COST is a separate claim and gets a separate experiment: the real file against
the patched file, interleaved on the same page load, order rotated, with an A/A
drift floor taken first (the shape #70 priced the observer with).

Run:  .venv/bin/python tools/audit_retext_tier.py [--json out.json]
"""
import asyncio, json, sys, time
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_readiness_adversarial as AD   # import-safe since its main() is guarded

ROOT = Path(__file__).resolve().parent.parent
TAG = (ROOT / "extension" / "listener_tag.js").read_text(encoding="utf-8")
READY = AD.READY
OFFSETS = AD.OFFSETS
FINAL = AD.FINAL

# ---- the instrumented ring: one extra bit per record, reported by query() ----
# Anchored on exact text from the shipped file and asserted to be a controlled
# two-site patch, so a verdict below cannot come from a ring that drifted from
# the one that ships.
REC_OLD = "        kd[s] = r.type === 'childList' ? 1 : (r.type === 'characterData' ? 2 : 3);"
REC_NEW = (REC_OLD + "\n"
           "        rt[s] = (kd[s] === 1 && _allText(r)) ? 1 : 0;")
DECL_OLD = "    const kd = new Uint8Array(CAP);       // 1 childList, 2 characterData, 3 attributes"
DECL_NEW = (DECL_OLD + "\n"
            "    const rt = new Uint8Array(CAP);\n"
            "    const _allText = (r) => {\n"
            "      try {\n"
            "        const a = r.addedNodes, b = r.removedNodes;\n"
            "        if (!a.length && !b.length) return false;\n"
            "        for (let i = 0; i < a.length; i++) if (a[i].nodeType !== 3) return false;\n"
            "        for (let i = 0; i < b.length; i++) if (b[i].nodeType !== 3) return false;\n"
            "        return true;\n"
            "      } catch (e) { return false; }\n"
            "    };")
Q_OLD = "          if (kd[i] === 1) out.structural++;"
Q_NEW = ("          if (kd[i] === 1) { out.structural++; if (rt[i]) out.retext++; }")
Q_INIT_OLD = "                      structural: 0, text: 0, attrs: {}, win: winMs || 1000 };"
Q_INIT_NEW = "                      structural: 0, text: 0, retext: 0, attrs: {}, win: winMs || 1000 };"
for a in (REC_OLD, DECL_OLD, Q_OLD, Q_INIT_OLD):
    assert TAG.count(a) == 1, f"anchor drifted: {a[:48]!r}"
TAG_RT = (TAG.replace(DECL_OLD, DECL_NEW).replace(REC_OLD, REC_NEW)
             .replace(Q_INIT_OLD, Q_INIT_NEW).replace(Q_OLD, Q_NEW))
assert TAG_RT != TAG


async def run_one(browser, name, f, sem):
    async with sem:
        ctx = await browser.new_context(viewport={"width": 900, "height": 700})
        await ctx.add_init_script(TAG_RT)
        await AD.route_all(ctx, name, f["html"])
        pg = await ctx.new_page()
        await pg.goto("http://app.test/", wait_until="domcontentloaded")
        for key, sel in (("main", "main"), ("host", "x-feed")):
            await pg.evaluate(
                "([s,k])=>{const e=document.querySelector(s);if(e)e.setAttribute('mmid',k)}",
                [sel, "9" + key])
        t0 = time.monotonic()

        async def sig():
            s = f["sig"]
            try:
                if s.startswith("@frame:"):
                    host, expr = s[7:].split("|", 1)
                    for fr in pg.frames:
                        if host in fr.url:
                            return await fr.evaluate(expr)
                    return None
                return await pg.evaluate(s)
            except Exception as e:
                return f"ERR {e}"

        rows = []
        for off in OFFSETS:
            await pg.wait_for_timeout(max(0, off - (time.monotonic() - t0) * 1000))
            sg = await sig()
            # The TOP ring only; the probe's frame merge is orthogonal to the
            # question and would mix two rings' retext bits into one number.
            q = await pg.evaluate("() => window.__abMut.query(null, 3000)")
            rows.append(dict(off=off, sig=sg, q=q))
        await pg.wait_for_timeout(max(0, FINAL - (time.monotonic() - t0) * 1000))
        final = await sig()
        await ctx.close()
        return dict(name=name, truth=f["truth"], rows=rows, final=final)


# ---- cost: the real file against the patched one, interleaved, A/A floor first
COST_PAGE = ("<!doctype html><meta charset=utf-8><body><div id=h></div>"
             "<div id=t>x</div></body>")


async def cost_arm(browser, tag, churn):
    """One timed run. `churn` picks which shape of mutation is generated, because
    the patch's cost is a per-record nodeType scan and an element append exits it
    on the FIRST node while a text swap scans two."""
    ctx = await browser.new_context()
    await ctx.add_init_script(tag)
    await ctx.route("**/*", lambda r: r.fulfill(
        status=200, content_type="text/html", body=COST_PAGE))
    pg = await ctx.new_page()
    await pg.goto("http://cost.test/")
    # THE FIRST VERSION OF THIS TIMED THE WRONG THING and reported 0.0% overhead
    # against a 16.67% A/A floor, i.e. nothing. A MutationObserver callback is a
    # MICROTASK: it is queued while the loop runs and executes at the microtask
    # checkpoint AFTER it, so a timer closed at the end of the synchronous loop
    # measures the page's own DOM writes and none of the work under test. The
    # `await Promise.resolve()` yields to the microtask queue, where the observer
    # callback is already ahead of this continuation, so the clock closes with the
    # callback included.
    ms = await pg.evaluate("""async ([n, mode]) => {
      const h = document.getElementById('h'), t = document.getElementById('t');
      const t0 = performance.now();
      if (mode === 'append') { for (let i = 0; i < n; i++) h.appendChild(document.createElement('p')); }
      else if (mode === 'retext') { for (let i = 0; i < n; i++) t.textContent = 'v' + i; }
      else { for (let i = 0; i < n; i++) h.setAttribute('data-k', String(i)); }
      await Promise.resolve();
      return performance.now() - t0;
    }""", [churn[1], churn[0]])
    await ctx.close()
    return ms


async def cost(browser, reps=7):
    out = {}
    # Sizes chosen to clear Chrome's 0.1ms timer quantisation, and to include the
    # 40,000-in-one-batch point an independent audit used to re-derive #70's
    # observer cost -- a 2,000-row grid render lands there, so it is the regime
    # the claim has to survive rather than a synthetic extreme.
    for mode, n in (("append", 10000), ("retext", 10000), ("attr", 10000),
                    ("append", 40000), ("retext", 40000), ("attr", 40000)):
        key = f"{mode}@{n}"
        a, b, aa = [], [], []
        for k in range(reps):
            # ORDER ROTATED per replicate, and an A/A pair measured in the same
            # sequence so the floor is produced by the same machinery as the
            # comparison rather than asserted (PRINCIPLES 10).
            seq = [("base", TAG), ("patched", TAG_RT), ("base2", TAG)]
            if k % 2:
                seq = [("patched", TAG_RT), ("base", TAG), ("base2", TAG)]
            got = {}
            for label, tag in seq:
                got[label] = await cost_arm(browser, tag, (mode, n))
            a.append(got["base"]); b.append(got["patched"]); aa.append(got["base2"])
        med = lambda xs: sorted(xs)[len(xs) // 2]
        out[key] = dict(base_ms=round(med(a), 3), patched_ms=round(med(b), 3),
                        base2_ms=round(med(aa), 3),
                        overhead_pct=round((med(b) / med(a) - 1) * 100, 2),
                        aa_floor_pct=round(abs(med(aa) / med(a) - 1) * 100, 2))
    return out


def tier(structural, text, attrs):
    if structural or text: return "STRONG"
    if attrs: return "MINOR"
    return "QUIET"


async def main():
    out_json = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        sem = asyncio.Semaphore(5)
        res = await asyncio.gather(*[run_one(browser, n, f, sem)
                                     for n, f in AD.FIX.items()])
        cst = await cost(browser)
        await browser.close()

    print(f"{'shape':34} {'off':>5} {'struct':>7} {'retext':>7} {'text':>5} {'attr':>5} "
          f"{'shipped':>8} {'candidate':>10}  later?")
    flips = []
    for r in res:
        for row in r["rows"]:
            q = row["q"]
            na = sum(q["attrs"].values())
            ship = tier(q["structural"], q["text"], na)
            # candidate: a childList that only moved text nodes is a re-text
            cs = q["structural"] - q["retext"]
            ct = q["text"] + q["retext"]
            cand = ("STRONG" if cs else ("TEXT" if ct else ("MINOR" if na else "QUIET")))
            later = row["sig"] != r["final"]
            if ship != cand:
                flips.append((r["name"], row["off"], ship, cand, later,
                              q["structural"], q["retext"]))
            print(f"{r['name']:34} {row['off']:>5} {q['structural']:>7} {q['retext']:>7} "
                  f"{q['text']:>5} {na:>5} {ship:>8} {cand:>10}  {later}")

    print("\nFLIPS (shipped tier -> candidate tier):")
    bad = 0
    for name, off, s, c, later, st, rt in flips:
        # A flip is WRONG only if it moves a read that is genuinely still
        # building into a tier claiming the set of elements is stable.
        verdict = "LOSS" if (later and c in ("MINOR", "QUIET")) else "ok"
        if verdict == "LOSS": bad += 1
        print(f"  {name:34} {off:>5}  {s} -> {c}  changes_later={later}  "
              f"(structural {st}, of which retext {rt})  {verdict}")
    print(f"\nflips={len(flips)}  losses={bad}")

    print("\nCOST (median of 7 interleaved replicates, order rotated; "
          "aa_floor is base vs base in the same sequence):")
    for k, v in cst.items():
        print(f"  {k:16} base {v['base_ms']:>8}ms  patched {v['patched_ms']:>8}ms  "
              f"overhead {v['overhead_pct']:>7}%   A/A floor {v['aa_floor_pct']:>6}%")
    if out_json:
        Path(out_json).write_text(json.dumps(dict(rows=res, cost=cst), indent=1))


if __name__ == "__main__":
    asyncio.run(main())

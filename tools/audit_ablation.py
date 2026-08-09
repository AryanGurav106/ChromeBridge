"""Signature-ablation test: how much weight is the site-specific code carrying?

The collector contains a handful of hard-coded LIBRARY SIGNATURES — CodeMirror/
Monaco/Ace class names, FontAwesome/Bootstrap icon-font prefixes, a `canvas`
class regex, Radix's data-state/data-placeholder, and an English
select|choose|pick wordlist. Each is documented as "a booster beside a general
path, never a sole gate". This test checks that claim empirically instead of by
assertion:

  For every site in the corpus, run the REAL collector, then run it again with
  ONE signature neutered to a never-matching token, and diff the structured
  output entry-by-entry.

  - A signature that is genuinely a booster produces small, cosmetic diffs.
  - A signature that is load-bearing produces entries appearing/disappearing —
    which means any site using a DIFFERENT library of the same kind is getting
    the ablated behaviour today.

Every variant is evaluated against the SAME loaded page, so the diff is caused
by the ablation and nothing else.

Run:  python tools/audit_ablation.py [-n N] [-c CONCURRENCY]
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from audit_dom_quality import extract, load_sites  # noqa: E402

OUT = ROOT / "temp" / "dom_quality"
NEVER = ".__ablated_never_matches__"

# (name, literal-to-replace, replacement). Each must appear in the collector or
# the test fails loudly rather than silently measuring nothing.
ABLATIONS = [
    # --- signatures naming a specific LIBRARY. Each should be a fast path with a
    #     general fallback behind it; if ablating one changes the listing, every
    #     site using a DIFFERENT library of that kind is getting the ablated
    #     behaviour today.
    ("code-editor-host",
     "'.CodeMirror, .cm-editor, .monaco-editor, .ace_editor, [class*=\"mq-editable-field\"]'",
     f"'{NEVER}'"),
    ("code-editor-content",
     "'.cm-content, .CodeMirror-code, .view-lines, .ace_text-layer, [class*=\"mq-root-block\"]'",
     f"'{NEVER}'"),
    ("cm-placeholder",
     "'.cm-placeholder, [class*=\"placeholder\"]'",
     f"'{NEVER}'"),
    ("icon-library-prefixes",
     r"/(?:^|\s)(?:fa|far|fas|fab|fal|bi|icon|lucide|ph|ri|ti|mdi|bx|bxs|gg|la|las|octicon|tabler)-([a-z][a-z0-9-]{2,})/",
     "/(?!)/"),
    ("canvas-class-regex",
     r"/(^|[\s-])canvas($|[\s_-])/i",
     "/(?!)/"),
    ("radix-data-state",
     "if (ds === 'active' || ds === 'open' || ds === 'on' || ds === 'checked') return ds;",
     "if (false) return ds;"),
    # --- signatures relying on ENGLISH or on one naming convention. The
    #     placeholder story has two independent structural signals (attribute
    #     name vs class token) plus the wordlist; ablating each in turn shows
    #     whether any single one is carrying the answer alone.
    ("english-select-wordlist",
     r"/^(select|choose|pick)\b/i",
     "/(?!)/"),
    ("placeholder-attr-name",
     "if (a.name.indexOf('placeholder') !== -1) {",
     "if (false) {"),
    ("placeholder-class-token",
     r"return /(^|[\s_-])placeholder([\s_-]|$)/.test(cn);",
     "return false;"),
    ("active-selected-class",
     r"/(^|\s)(active|selected|current)($|\s)/",
     "/(?!)/"),
]

# Fields whose change means the agent is told something different about a control.
WATCH = ["label", "name", "value", "placeholder", "role", "iconOnly", "canvasLike",
         "codeEditor", "editable", "unselected", "active", "orphanWidget", "near"]


def build_variants(src_path=None):
    src = Path(src_path or (ROOT / "extension" / "background.js")).read_text(encoding="utf-8")
    base = extract("_collectInteractivePage", src)
    variants = {"__base__": base}
    for name, needle, repl in ABLATIONS:
        n = base.count(needle)
        if n == 0:
            raise SystemExit(f"ablation '{name}' pattern not found in collector — update the literal:\n  {needle}")
        variants[name] = base.replace(needle, repl)
        print(f"  ablation {name:<24} {n} site(s) in source")
    return variants


def _ident(e):
    """What a human would call 'the same control': same kind, same text, same box.

    mmid injection is ADDITIVE, so a live SPA that re-renders between two
    evaluations hands the second one a brand-new mmid for a control that never
    visually changed. Diffing on mmid alone scores that as one removal plus one
    addition, and on animated pages (MUI docs, Spotify, Grafana) it buries the
    ablation signal completely — the first version of this test reported 250
    "changes" for signatures those pages do not even use.
    """
    return (e.get("tag"), e.get("role"), (e.get("label") or "")[:40],
            e.get("x"), e.get("y"), e.get("w"), e.get("h"))


def diff(base, other):
    """Entry-level diff, with re-render churn cancelled out."""
    a = {e["mmid"]: e for e in base}
    b = {e["mmid"]: e for e in other}
    added = [b[k] for k in b if k not in a]
    removed = [a[k] for k in a if k not in b]
    # Cancel add/remove pairs that describe the same control under a new mmid.
    pool = {}
    for e in added:
        pool.setdefault(_ident(e), []).append(e)
    real_removed, rematched = [], set()
    for e in removed:
        bucket = pool.get(_ident(e))
        if bucket:
            m = bucket.pop()
            rematched.add(id(m))
        else:
            real_removed.append(e)
    real_added = [e for e in added if id(e) not in rematched]
    changed = []
    for k in a:
        if k not in b:
            continue
        d = {f: (a[k].get(f), b[k].get(f)) for f in WATCH if a[k].get(f) != b[k].get(f)}
        if d:
            changed.append({"mmid": k, "tag": a[k]["tag"], "label": (a[k].get("label") or "")[:30], "d": d})
    return real_added, real_removed, changed


async def one(ctx, name, url, extra, wraps):
    page = await ctx.new_page()
    rec = {"name": name}
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        # Lazy shelves keep mounting for a while after networkidle; anything that
        # arrives mid-sweep looks like an ablation effect. Settle first.
        await page.wait_for_timeout(3000 + extra)
        rec["n"] = len(await page.evaluate(wraps["__base__"]))
        rec["ablations"] = {}
        rec["drift"] = {"added": 0, "removed": 0, "changed": 0}
        for k, w in wraps.items():
            if k == "__base__":
                continue
            try:
                # PER-ABLATION DRIFT CONTROL: base -> ablated -> base. The
                # base-to-base pair brackets the variant in time, so it measures
                # the page's own churn over exactly the window the comparison
                # spans. A single up-front control is not enough — the first
                # ablation in the list absorbs all remaining hydration and gets
                # blamed for it (Spotify's home shelves scored 28 phantom
                # additions for a selector the page does not contain).
                base = await page.evaluate(wraps["__base__"])
                other = await page.evaluate(w)
                base2 = await page.evaluate(wraps["__base__"])
            except Exception as e:
                rec["ablations"][k] = {"error": str(e)[:80]}
                continue
            add, rem, chg = diff(base, other)
            fa, fr, fc = diff(base, base2)
            floor = len(fa) + len(fr) + len(fc)
            for f in ("added", "removed", "changed"):
                rec["drift"][f] = max(rec["drift"][f], {"added": len(fa), "removed": len(fr), "changed": len(fc)}[f])
            if len(add) + len(rem) + len(chg) > floor:
                rec["ablations"][k] = {
                    "added": len(add), "removed": len(rem), "changed": len(chg), "floor": floor,
                    "sample": ([{"kind": "removed", **{f: r.get(f) for f in ("tag", "role", "label")}} for r in rem[:3]] +
                               [{"kind": "added", **{f: r.get(f) for f in ("tag", "role", "label")}} for r in add[:3]] +
                               [{"kind": "changed", "tag": c["tag"], "label": c["label"], "d": c["d"]} for c in chg[:4]]),
                }
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:80]}"
    finally:
        try:
            await page.close()
        except Exception:
            pass
    return rec


async def main(limit, concurrency, only, src_path=None, tag='ablation'):
    variants = build_variants(src_path)
    wraps = {k: "(function(){ " + v + "\n; return _collectInteractivePage(true); })()" for k, v in variants.items()}
    sites = load_sites()
    if only:
        want = set(only.split(","))
        sites = [s for s in sites if s[0] in want]
    if limit:
        sites = sites[:limit]
    print(f"\n{len(sites)} sites x {len(ABLATIONS)} ablations\n", flush=True)

    sem = asyncio.Semaphore(concurrency)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1366, "height": 900})
        await ctx.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))

        async def guarded(s):
            async with sem:
                r = await one(ctx, s[0], s[1], s[2], wraps)
                if "error" in r:
                    print(f"  {r['name']:<18} SKIP {r['error'][:50]}", flush=True)
                else:
                    churn = max(r.get("drift", {}).values() or [0])
                    hits = ", ".join(f"{k}({v.get('added',0)}+/{v.get('removed',0)}-/{v.get('changed',0)}~"
                                     f" vs floor {v.get('floor',0)})"
                                     for k, v in r["ablations"].items())
                    print(f"  {r['name']:<18} n={r['n']:<4} churn={churn:<4} {hits or 'no effect above drift'}", flush=True)
                return r

        rows = await asyncio.gather(*[guarded(s) for s in sites])
        await browser.close()

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{tag}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")

    print("\n=== ABLATION IMPACT (how load-bearing is each signature?) ===")
    ok = [r for r in rows if "error" not in r]
    print(f"  {len(ok)} pages measured, {len(rows)-len(ok)} unreachable\n")
    # Entries are only recorded when they already beat their own local
    # base->base control, so presence IS the signal.
    def above_floor(r, name):
        v = r["ablations"].get(name)
        return bool(v) and "error" not in v

    dr_tot = sum(max(r.get("drift", {}).values() or [0]) for r in ok)
    print(f"  (worst per-page re-render churn, summed: {dr_tot} entry diffs between two IDENTICAL runs)\n")
    print(f"  {'signature':<24} {'pages':>6} {'added':>7} {'removed':>8} {'changed':>8}   verdict")
    for name, _, _ in ABLATIONS:
        pages = [r for r in ok if above_floor(r, name)]
        add = sum(r["ablations"][name]["added"] for r in pages)
        rem = sum(r["ablations"][name]["removed"] for r in pages)
        chg = sum(r["ablations"][name]["changed"] for r in pages)
        if not pages:
            verdict = "inert on this corpus"
        elif rem or add:
            verdict = f"LOAD-BEARING on {len(pages)} page(s): " + ",".join(r["name"] for r in pages[:5])
        else:
            verdict = f"cosmetic on {len(pages)} page(s): " + ",".join(r["name"] for r in pages[:5])
        print(f"  {name:<24} {len(pages):>6} {add:>7} {rem:>8} {chg:>8}   {verdict}")

    print("\n=== DETAIL (pages where a signature changed the listing) ===")
    for name, _, _ in ABLATIONS:
        pages = [r for r in ok if name in r["ablations"] and "error" not in r["ablations"][name]]
        if not pages:
            continue
        print(f"\n  --- {name} ---")
        for r in sorted(pages, key=lambda r: -(r["ablations"][name]["added"] + r["ablations"][name]["removed"]))[:6]:
            a = r["ablations"][name]
            print(f"    {r['name']:<18} +{a['added']} -{a['removed']} ~{a['changed']}")
            for s in a["sample"][:5]:
                if s["kind"] == "changed":
                    dd = "; ".join(f"{f}: {v[0]!r}->{v[1]!r}" for f, v in list(s["d"].items())[:3])
                    print(f"        ~ {s['tag']:<8} {s['label'][:24]!r}  {dd[:110]}")
                else:
                    print(f"        {'-' if s['kind']=='removed' else '+'} {s['tag']:<8} "
                          f"role={s.get('role')} {(s.get('label') or '')[:40]!r}")
    print(f"\nFull JSON: {OUT/'ablation.json'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--limit", type=int, default=0)
    ap.add_argument("-c", "--concurrency", type=int, default=4)
    ap.add_argument("--only", default="")
    ap.add_argument("--src", default="")
    ap.add_argument("--tag", default="ablation")
    a = ap.parse_args()
    asyncio.run(main(a.limit, a.concurrency, a.only, a.src or None, a.tag))

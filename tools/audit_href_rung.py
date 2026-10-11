"""Should a link's DESTINATION be a descriptor rung, and ahead of its name?

#59 recorded the failure this probe exists to answer. On a real app a nav
tab's accessible name is "Investors 38" -- AccName 2F concatenates descendant
text and the badge is a descendant -- so the identity rung is DATA-DEPENDENT.
Adding a record made the name "Investors 43" and a flow that had passed minutes
earlier stopped resolving. The rebind can only ever propose another
count-bearing name, which breaks again at 44.

A nav link's `href` is DECLARED and does not move, so it is the obvious key.
#41/#44 are explicit that a ladder change is measured before it ships, and #44
is the entry where the obvious reading of a half-measurement was REFUTED by the
other half, so this measures all three halves:

  COVERAGE     a rung that reaches 3% of controls is not worth a field.
  UNIQUENESS   is href a BETTER key than name, or just a different one? If it
               ties more often it is worse, whatever its stability.
  STABILITY    the floor under everything. A descriptor that regenerates
               differently across two loads of the SAME source fails a frontend
               that did not change -- and an href is exactly where a session id
               or a cache-buster would live.

And the one that decides it, because the first three can all look good while
the change buys nothing REAL:

  DISAGREEMENT  among controls that have both, how often do href and name
                disagree about WHICH ELEMENT they name? Where they agree the
                rung is inert and the whole question is moot; the rung is worth
                a field only where href resolves something name cannot.

COST IS ZERO TOKENS, which is why this is a smaller decision than #41's.
`_flow_entries` fetches the STRUCTURED array and never prints it, so moving it
from `compact` to `brief` costs the collector a URL resolve per link and the
agent nothing at all. The #10 measurement (full costs x1.39 median tokens) is
about the STRING listing and does not apply here.

Usage:
    python tools/audit_href_rung.py --sites 30
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "temp" / "frozen"
OUT = ROOT / "temp" / "descriptors"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))
from _extract import extract  # noqa: E402
from capture_listings import SITES  # noqa: E402
from core.flows import descriptor as D  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = extract("_collectInteractivePage", BG, verify=True)
TAG_JS = str(ROOT / "extension" / "listener_tag.js")
VIEWPORT = {"width": 1280, "height": 1600}


def base(e: dict) -> tuple:
    f = D.fields(e)
    return (f["tag"], f["role"], f["type"])


def by_name(e: dict) -> tuple:
    return base(e) + (D.fields(e)["name"],)


def by_href(e: dict) -> tuple:
    return base(e) + ((e.get("href") or "").strip(),)


def by_full(e: dict) -> tuple:
    f = D.fields(e)
    return base(e) + (f["name"], f["section"], f["under"])


# What ELSE a page might declare about a control that is not a link. The href
# alternate reaches <a>/<area> and nothing else, which leaves a BUTTON carrying
# a badge with no second key at all -- and `counter-in-name` measures that
# population at 84.2% still refusing. These are the only two candidates that
# are declared rather than derived: `id` (HTML's own unique handle) and
# `data-testid` (an attribute whose entire purpose is to be a stable test
# hook). Measured on the same three axes as href, and for the same reason --
# a key that is rarer, less unique or less stable than the name is not a key.
ATTR_PROBE = """(function () {
  const out = {};
  for (const el of document.querySelectorAll('[mmid]')) {
    out[el.getAttribute('mmid')] = {
      id: el.id || '',
      testid: el.getAttribute('data-testid') || el.getAttribute('data-test-id')
              || el.getAttribute('data-test') || '',
    };
  }
  return out;
})()"""


async def collect(page, detail: str) -> list[dict]:
    return await page.evaluate(
        "(function(){ " + COLLECT + f"; return _collectInteractivePage(true, null, '{detail}'); }})()"
    ) or []


async def two_passes(browser, name, url):
    passes = []
    for _ in range(2):
        ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True)
        await ctx.add_init_script(path=TAG_JS)
        try:
            har = FROZEN / f"{name}.har"
            if not har.exists():
                return None
            await ctx.route_from_har(str(har), not_found="abort")
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            except Exception:
                return None
            await page.wait_for_timeout(1200)
            ents = await collect(page, "brief")
            # mmids are injected BY the collect above, so this must follow it.
            attrs = await page.evaluate(ATTR_PROBE)
            for e in ents:
                a = attrs.get(str(e.get("mmid"))) or {}
                e["_id"] = a.get("id", "")
                e["_testid"] = a.get("testid", "")
            passes.append(ents)
        finally:
            await ctx.close()
    return passes


async def run_site(browser, name, url) -> dict | None:
    got = await two_passes(browser, name, url)
    if not got:
        return None
    a, b = got
    if len(a) < 5 or len(b) < 5:
        return None
    targets = [e for e in a if D._targetable(e)]
    if not targets:
        return None
    linked = [e for e in targets if (e.get("href") or "").strip()]

    row = {"name": name, "targets": len(targets), "linked": len(linked),
           "coverage": round(len(linked) / len(targets), 4)}
    if not linked:
        row.update(uniq_href=None, uniq_name=None, uniq_full=None,
                   stable_href=None, stable_name=None, disagree=None,
                   href_only=0, name_only=0)
        return row

    # --- uniqueness, over the LINKED population only ----------------------
    # Measured against the whole listing, as the resolver does: a descriptor is
    # ambiguous if ANY targetable entry matches it, not just another link.
    ch = Counter(by_href(e) for e in targets)
    cn = Counter(by_name(e) for e in targets)
    cf = Counter(by_full(e) for e in targets)
    row["uniq_href"] = round(sum(1 for e in linked if ch[by_href(e)] == 1) / len(linked), 4)
    row["uniq_name"] = round(sum(1 for e in linked if cn[by_name(e)] == 1) / len(linked), 4)
    row["uniq_full"] = round(sum(1 for e in linked if cf[by_full(e)] == 1) / len(linked), 4)

    # Where does each key work ALONE? This is the field's real argument: a rung
    # that is only ever unique where name already was adds a field for nothing.
    row["href_only"] = sum(1 for e in linked if ch[by_href(e)] == 1 and cn[by_name(e)] != 1)
    row["name_only"] = sum(1 for e in linked if cn[by_name(e)] == 1 and ch[by_href(e)] != 1)

    # --- stability, same source twice, matched by mmid --------------------
    # mmid is the ruler for the same reason audit_flow_resolve uses it: it is
    # assigned by the collection walk, so it is independent of every field
    # being measured. Where the two passes do not stamp the same elements the
    # page differed between loads (#16 names 18 of 108 sites) and the site is
    # reported rather than scored.
    bm = {str(e.get("mmid")): e for e in b if D._targetable(e)}
    both = [(e, bm[str(e.get("mmid"))]) for e in linked if str(e.get("mmid")) in bm]
    row["ruler_valid"] = len(both) == len(linked)
    if both:
        row["stable_href"] = round(
            sum(1 for x, y in both if (x.get("href") or "") == (y.get("href") or "")) / len(both), 4)
        row["stable_name"] = round(
            sum(1 for x, y in both if D.fields(x)["name"] == D.fields(y)["name"]) / len(both), 4)
    else:
        row["stable_href"] = row["stable_name"] = None

    # --- disagreement: the number that decides whether this is inert ------
    # For every linked control, which element does each key land on? Where both
    # are unique and both land on the same element the rung changes nothing.
    dis = 0
    for e in linked:
        hh = [x for x in targets if by_href(x) == by_href(e)]
        nn = [x for x in targets if by_name(x) == by_name(e)]
        if len(hh) == 1 and len(nn) == 1 and str(hh[0].get("mmid")) != str(nn[0].get("mmid")):
            dis += 1
    row["disagree"] = dis

    # --- the NON-LINK population, which href cannot reach -----------------
    plain = [e for e in targets if not (e.get("href") or "").strip()]
    row["plain"] = len(plain)
    if plain:
        for key, label in (("_id", "id"), ("_testid", "testid")):
            have = [e for e in plain if (e.get(key) or "").strip()]
            row[f"cov_{label}"] = round(len(have) / len(plain), 4)
            if have:
                c = Counter(base(e) + ((e.get(key) or "").strip(),) for e in targets)
                row[f"uniq_{label}"] = round(
                    sum(1 for e in have if c[base(e) + ((e.get(key) or "").strip(),)] == 1)
                    / len(have), 4)
                pair = [(e, bm[str(e.get("mmid"))]) for e in have
                        if str(e.get("mmid")) in bm]
                row[f"stable_{label}"] = round(
                    sum(1 for x, y in pair
                        if (x.get(key) or "") == (y.get(key) or "")) / len(pair), 4
                ) if pair else None
            else:
                row[f"uniq_{label}"] = row[f"stable_{label}"] = None
    return row


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", type=int, default=30)
    args = ap.parse_args()

    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for i, (name, url) in enumerate(list(SITES)[: args.sites], 1):
            try:
                r = await run_site(browser, name, url)
            except Exception as exc:
                print(f"  [{i:>3}] {name:<22} ERROR {type(exc).__name__}: {exc}")
                continue
            if not r:
                print(f"  [{i:>3}] {name:<22} skipped")
                continue
            rows.append(r)
            if r["linked"]:
                print(f"  [{i:>3}] {name:<22} links={r['linked']:<4}/{r['targets']:<4} "
                      f"uniq href={r['uniq_href']:.2f} name={r['uniq_name']:.2f}  "
                      f"stable href={r['stable_href']:.2f} name={r['stable_name']:.2f}  "
                      f"href-only={r['href_only']} name-only={r['name_only']}")
            else:
                print(f"  [{i:>3}] {name:<22} no linked controls")
        await browser.close()

    live = [r for r in rows if r["linked"] and r.get("ruler_valid")]
    if not live:
        print("no sites measured")
        return 1

    def med(k):
        vals = [r[k] for r in live if r.get(k) is not None]
        return statistics.median(vals) if vals else 0.0

    nl = sum(r["linked"] for r in live)
    nt = sum(r["targets"] for r in live)
    print(f"\n{'=' * 78}\nHREF AS A DESCRIPTOR RUNG — {len(live)} sites, "
          f"{nl} linked controls of {nt} targetable\n{'=' * 78}")
    print(f"  coverage (targetable controls declaring an href)  median {med('coverage'):>7.1%}"
          f"   overall {nl / nt:.1%}")
    print(f"\n  {'key':<34}{'median uniq':>14}{'worst':>10}")
    for k, label in (("uniq_href", "tag+role+type+href"),
                     ("uniq_name", "tag+role+type+name"),
                     ("uniq_full", "+section+under (the name rung)")):
        worst = min(r[k] for r in live)
        print(f"  {label:<34}{med(k):>13.1%}{worst:>10.1%}")
    print(f"\n  {'key':<34}{'median stable':>16}{'worst':>10}")
    for k, label in (("stable_href", "href, same source twice"),
                     ("stable_name", "name, same source twice")):
        worst = min(r[k] for r in live if r[k] is not None)
        bad = min((r for r in live if r[k] is not None), key=lambda r: r[k])
        print(f"  {label:<34}{med(k):>15.1%}{worst:>10.1%}  ({bad['name']})")

    ho = sum(r["href_only"] for r in live)
    no = sum(r["name_only"] for r in live)
    dg = sum(r["disagree"] for r in live)
    print(f"\n  linked controls href resolves and name CANNOT : {ho:>6}  {ho / nl:>7.2%}")
    print(f"  linked controls name resolves and href CANNOT : {no:>6}  {no / nl:>7.2%}")
    print(f"  the two keys land on DIFFERENT elements       : {dg:>6}  {dg / nl:>7.2%}")

    npl = sum(r.get("plain", 0) for r in live)
    print(f"\n  THE NON-LINK POPULATION the href alternate cannot reach: {npl} controls")
    print(f"  {'candidate key':<34}{'coverage':>12}{'median uniq':>14}{'median stable':>16}")
    for label in ("id", "testid"):
        cov = [r[f"cov_{label}"] for r in live if r.get(f"cov_{label}") is not None]
        unq = [r[f"uniq_{label}"] for r in live if r.get(f"uniq_{label}") is not None]
        stb = [r[f"stable_{label}"] for r in live if r.get(f"stable_{label}") is not None]
        print(f"  {label:<34}{(statistics.median(cov) if cov else 0):>11.1%}"
              f"{(statistics.median(unq) if unq else 0):>13.1%}"
              f"{(statistics.median(stb) if stb else 0):>15.1%}"
              f"   (n={len(unq)} sites)")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "href_rung.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT / 'href_rung.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

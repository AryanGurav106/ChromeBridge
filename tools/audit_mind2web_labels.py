"""Audit the Mind2Web LABEL SET and the crediting rule `bench_mind2web.py` uses.

`bench_mind2web.py` produces the only out-of-sample number in this project
(96.0% target recall, quoted in README.md and in public posts). It cannot audit
its own inputs or its own ruler, and PRINCIPLES SS8 says a result that flatters
the system is re-derived before it is believed. This asks the four questions it
cannot ask of itself.

  LABELS  Is each labelled target sound? Present in the PARSED DOM -- not merely
          in the HTML string, which is a different claim -- uniquely identified,
          plausible for its recorded operation, and not degenerate.

  CREDIT  Of the hits, how many are the target ITSELF and how many are an
          ancestor or a descendant standing in for it? A DESCENDANT credit is
          sound by EVENT BUBBLING: a click inside the target passes through it.
          An ANCESTOR credit is sound only if ACTIVATING the ancestor does the
          one thing the target did, which HTML settles -- `<a>`, `<button>`,
          `<summary>`, a form control and the single-activation ARIA roles
          promise it, a bare container does not (#30's rule for inherited
          cursor, applied to a ruler instead of to the collector).

  CAP     #18 widened descendant credit from "the first descendant carrying an
          mmid" to "any descendant", capped by area so a page-sized container
          cannot claim credit for its contents. Ablate the cap: is it load
          bearing, or a guard that has never had to fire?

  REPAIR  Mind2Web serializes the DOM XML-style, so EMPTY elements come back as
          `<a/>`, `<iframe/>`, `<textarea/>`. HTML has no self-closing syntax for
          non-void elements: the slash is ignored and the tag OPENS. One
          self-closed `<iframe/>` or `<textarea/>` is RAWTEXT/RCDATA and swallows
          the entire rest of the document as text. This arm repairs the
          serialization and re-measures, because the distortion moves the number
          in BOTH directions and the shipped figure cannot see either.

Nothing here re-implements the collector: it extracts `_collectInteractivePage`
from `extension/background.js` verbatim, exactly as the benchmark does, so a
disagreement between the two is a disagreement about the RULER, not the system.
All arms run against the SAME page content in one process, so run-order drift
cannot align with the arm (#19).

Run:
    python tools/audit_mind2web_labels.py                 # labels + credit + cap
    python tools/audit_mind2web_labels.py --repair        # + the serialization arms
    python tools/audit_mind2web_labels.py --limit 40
    python tools/audit_mind2web_labels.py --json out.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "temp" / "mind2web"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = extract("_collectInteractivePage", BG, verify=True)
TAG_JS = str(ROOT / "extension" / "listener_tag.js")

# The repair and the credit cap come from the RULER, not from a second copy
# here -- this file exists to vary them, and a variant has to vary the thing the
# benchmark actually ships. `repair_serialization(html, only)` with `only=None`
# is what `bench_mind2web.py` now applies to every snapshot before rendering it.
from _m2w_ruler import (CREDIT_AREA_CAP, RAWTEXT, SELF_CLOSED,  # noqa: E402,F401
                        VOID, repair_serialization)

# What the recorded operation can land on. A TYPE on a <div> or a SELECT on
# something with no <select> in its chain is a label worth looking at -- though
# a <label> fronting its own control is legitimate, which is #18's case.
TYPEABLE_INPUT = {"", "text", "search", "email", "url", "tel", "password",
                  "number", "date", "time", "datetime-local", "month", "week"}
TYPEABLE_ROLE = {"textbox", "searchbox", "combobox", "spinbutton"}
# Activating one of these does ONE thing, so an agent acting on it instead of
# the labelled descendant does what the human did.
SINGLE_ACTIVATION_TAG = {"a", "button", "summary", "input", "select", "textarea",
                         "option", "label", "area", "details"}
SINGLE_ACTIVATION_ROLE = {"button", "link", "menuitem", "menuitemcheckbox",
                          "menuitemradio", "option", "tab", "checkbox", "radio",
                          "switch", "treeitem", "combobox"}


# One probe, asked of the labelled node: everything the four questions need, so
# a judgement comes from recorded facts rather than from a re-run per hypothesis.
PROBE = r"""
(bnid) => {
  const esc = String(bnid).replace(/"/g, '');
  const all = document.querySelectorAll('[backend_node_id]');
  const hits = document.querySelectorAll(`[backend_node_id="${esc}"]`);
  const out = { dom_ids: all.length, dom_hits: hits.length,
                vw: innerWidth, vh: innerHeight };
  const el = hits[0];
  if (!el) { out.found = false; return out; }
  out.found = true;

  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  out.tag = el.tagName.toLowerCase();
  out.type = (el.getAttribute('type') || '').toLowerCase();
  out.role = el.getAttribute('role') || '';
  out.w = Math.round(r.width); out.h = Math.round(r.height);
  out.area_frac = (r.width * r.height) / (innerWidth * innerHeight);
  out.rendered = r.width > 0 && r.height > 0 &&
                 cs.visibility !== 'hidden' && cs.display !== 'none';
  out.text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 70);

  // EVERY reason the collector may admit an element (PRINCIPLES SS1), asked one
  // at a time. Two of them -- a registered listener and `cursor:pointer` -- are
  // structurally unavailable on serialized HTML, and the point of recording
  // them separately is to show that rather than assert it.
  const ITAG = ['a','button','input','select','textarea','summary','label',
                'option','area','details'];
  out.sig = {
    interactive_tag: ITAG.includes(out.tag),
    svg_or_canvas: ['svg','canvas'].includes(out.tag),
    aria_role: !!out.role,
    onclick: el.hasAttribute('onclick'),
    tabindex: el.hasAttribute('tabindex'),
    contenteditable: !!el.isContentEditable,
    listener_tagged: !!el.__abClickBound,
    cursor_pointer: cs.cursor === 'pointer',
  };
  out.href = el.hasAttribute('href');

  const own = el.getAttribute('mmid');
  // `rank` is the position among mmid-BEARING ancestors (what the benchmark
  // walks); `dom_hops` is the real distance. They are wildly different on a
  // page whose markup nests, and conflating them hides how far a credit reached.
  const ancs = []; let dom_hops = 0;
  for (let n = el.parentElement; n; n = n.parentElement) {
    dom_hops++;
    const m = n.getAttribute && n.getAttribute('mmid');
    if (m) ancs.push({ mmid: m, tag: n.tagName.toLowerCase(),
                       role: n.getAttribute('role') || '',
                       rank: ancs.length + 1, dom_hops,
                       text: (n.innerText || n.textContent || '').replace(/\s+/g,' ').trim().slice(0,60),
                       area_frac: (() => { const b = n.getBoundingClientRect();
                                           return (b.width*b.height)/(innerWidth*innerHeight); })(),
                       kids: n.querySelectorAll('[mmid]').length });
  }
  // Uncapped, so the cap can be applied in Python and both arms come from one
  // page load.
  out.own = own; out.ancs = ancs;
  out.descs = Array.from(el.querySelectorAll('[mmid]')).map(n => ({
    mmid: n.getAttribute('mmid'), tag: n.tagName.toLowerCase(),
    text: (n.innerText || n.textContent || '').replace(/\s+/g,' ').trim().slice(0,60) }));
  return out;
}
"""


def load_samples(limit: int) -> list[dict]:
    """The benchmark's own round-robin-by-site loader, so the two see one set."""
    rows: list[dict] = []
    for f in sorted(DATA.glob("samples_shard*.jsonl")):
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    by_site: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_site[r.get("website") or "?"].append(r)
    out, i = [], 0
    while limit <= 0 or len(out) < limit:
        added = False
        for site in sorted(by_site):
            if i < len(by_site[site]):
                out.append(by_site[site][i])
                added = True
                if limit and len(out) >= limit:
                    break
        if not added:
            break
        i += 1
    return out


def op_plausible(op: str, p: dict) -> tuple[bool, str]:
    tag, typ, role = p.get("tag"), p.get("type"), p.get("role")
    if op == "TYPE":
        if tag == "textarea" or p.get("contenteditable") or role in TYPEABLE_ROLE:
            return True, ""
        if tag == "input" and typ in TYPEABLE_INPUT:
            return True, ""
        return False, f"TYPE on <{tag}{'/' + typ if typ else ''}>"
    if op == "SELECT":
        if tag == "select" or role in ("combobox", "listbox"):
            return True, ""
        # A <label> fronting its own <select> is #18's case and is legitimate.
        if any(d["tag"] == "select" for d in p.get("descs") or []):
            return True, ""
        if any(a["tag"] == "select" for a in p.get("ancs") or []):
            return True, ""
        return False, f"SELECT on <{tag}> with no <select> in its chain"
    return True, ""


async def score_arm(page, samples, only_tags, repair_on):
    rows = []
    for s in samples:
        html = repair_serialization(s["html"], only_tags) if repair_on else s["html"]
        rec = {k: s.get(k) for k in ("website", "action_uid", "annotation_id",
                                     "operation", "target_backend_node_id")}
        bid = str(s.get("target_backend_node_id"))
        # String presence and DOM presence are DIFFERENT claims. The benchmark's
        # `target_not_in_html` conflated them for a year -- that is the whole of
        # the REPAIR finding, and it is why the benchmark now repairs the
        # snapshot and calls the residual case `target_not_in_dom`.
        rec["in_string"] = len(re.findall(
            r'backend_node_id="%s"' % re.escape(bid), s["html"]))
        try:
            await page.set_content(html, wait_until="domcontentloaded")
            await page.wait_for_timeout(120)
            structured = await page.evaluate(
                "(function(){ " + COLLECT +
                "; return _collectInteractivePage(true, null, 'full'); })()")
            p = await page.evaluate(PROBE, s.get("target_backend_node_id"))
        except Exception as e:
            rec["status"] = "error"
            rec["err"] = str(e)[:120]
            rows.append(rec)
            continue

        listed = {str(e.get("mmid")) for e in structured}
        rec["entries"] = len(structured)
        rec.update({k: p.get(k) for k in
                    ("dom_ids", "dom_hits", "found", "rendered", "tag", "type",
                     "role", "w", "h", "area_frac", "text", "href")})
        rec["sig"] = p.get("sig") or {}
        if not p.get("found"):
            rec["status"] = "not_in_dom"
            rows.append(rec)
            continue

        own = p.get("own") if p.get("own") in listed else None
        anc = next((a for a in (p.get("ancs") or []) if a["mmid"] in listed), None)
        all_desc = [d for d in (p.get("descs") or []) if d["mmid"] in listed]
        cap_ok = p.get("area_frac", 1.0) < CREDIT_AREA_CAP   # the shipped cap
        desc = all_desc[0] if (cap_ok and all_desc) else None
        rec["n_desc_listed"] = len(all_desc)
        rec["cap_allows_desc"] = cap_ok
        rec["exact"] = bool(own)
        rec["recalled"] = bool(own or anc or desc)
        rec["recalled_uncapped"] = bool(own or anc or all_desc)
        rec["via"] = "own" if own else ("ancestor" if anc else
                                        ("descendant" if desc else "none"))
        if anc:
            rec["anc"] = anc
            rec["anc_single_activation"] = (anc["tag"] in SINGLE_ACTIVATION_TAG or
                                            anc["role"] in SINGLE_ACTIVATION_ROLE)
        if desc:
            rec["desc"] = desc
        rec["op_ok"], rec["op_why"] = op_plausible(s.get("operation") or "", p)
        rec["degenerate"] = p.get("tag") in ("body", "html") or p.get("area_frac", 0) >= 0.9
        rec["status"] = "ok" if rec["recalled"] else (
            "missed_present" if p.get("rendered") else "missed_invisible")
        rows.append(rec)
    return rows


def summarise(rows, label):
    scored = [r for r in rows if r.get("status") in
              ("ok", "missed_present", "missed_invisible")]
    rec = sum(1 for r in scored if r.get("recalled"))
    nd = sum(1 for r in rows if r.get("status") == "not_in_dom")
    via = Counter(r.get("via") for r in scored)
    print(f"  {label:<30} recall {rec}/{len(scored)} = {rec/max(1,len(scored)):>6.1%}"
          f"   all-in {rec}/{len(rows)} = {rec/max(1,len(rows)):>6.1%}"
          f"   not_in_dom {nd:<3} via {dict(via)}")
    return scored, rec


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--repair", action="store_true",
                    help="also measure the serialization-repaired arms")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    samples = load_samples(args.limit)
    if not samples:
        print("no samples -- run tools/fetch_mind2web.py first")
        return 1
    print(f"{len(samples)} labelled actions, "
          f"{len({s['website'] for s in samples})} sites, "
          f"{len({s['annotation_id'] for s in samples})} trajectories\n")

    arms = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 1600})
        await ctx.add_init_script(path=TAG_JS)
        page = await ctx.new_page()
        plan = [("A unrepaired (pre-#73)", None, False)]
        if args.repair:
            plan += [("B rawtext repaired", RAWTEXT, True),
                     ("C faithful repair = SHIPPED", None, True)]
        for label, tags, on in plan:
            arms[label] = await score_arm(page, samples, tags, on)
            print(f"  {label} done")
        await browser.close()

    rows = arms["A unrepaired (pre-#73)"]
    scored = [r for r in rows if r.get("status") in
              ("ok", "missed_present", "missed_invisible")]
    notdom = [r for r in rows if r.get("status") == "not_in_dom"]
    clicks = [r for r in scored if r.get("operation") == "CLICK"]

    print(f"\n=== LABEL SOUNDNESS ({len(rows)} labelled actions) ===")
    print(f"  id occurs exactly once in its own HTML string : "
          f"{sum(1 for r in rows if r.get('in_string') == 1)}/{len(rows)}")
    print(f"  id resolves to exactly one node in the DOM    : "
          f"{sum(1 for r in rows if r.get('dom_hits') == 1)}/{len(rows)}")
    print(f"  in the STRING but absent from the parsed DOM  : {len(notdom)}")
    print(f"  duplicated action_uid                         : "
          f"{len(rows) - len({r['action_uid'] for r in rows})}")
    print(f"  degenerate target (body/html or >=90% of viewport): "
          f"{sum(1 for r in scored if r.get('degenerate'))}")
    print(f"  implausible for its recorded operation        : "
          f"{sum(1 for r in scored if not r.get('op_ok'))}")
    bad = [r for r in scored if not r.get("op_ok") or r.get("degenerate")]
    for r in bad:
        print(f"      {r['website']:<13} {r['action_uid'][:8]} {r.get('operation'):<6} "
              f"<{r.get('tag')}> {r.get('op_why') or 'degenerate'}")

    # The two admitting signals serialized HTML cannot carry. Printed as a
    # measurement because the benchmark asserts it in prose and a probe that
    # never fires looks identical to one that does (#15).
    print(f"\n  admitting signals available on this corpus (of {len(scored)} targets):")
    for k in ("interactive_tag", "svg_or_canvas", "aria_role", "onclick",
              "tabindex", "contenteditable", "listener_tagged", "cursor_pointer"):
        n = sum(1 for r in scored if (r.get("sig") or {}).get(k))
        note = "   <- structurally unavailable on serialized HTML" if n == 0 and k in (
            "listener_tagged", "cursor_pointer") else ""
        print(f"    {k:<18} {n:>4}{note}")
    nodecl = [r for r in clicks if not any(
        (r.get("sig") or {}).get(k) for k in
        ("interactive_tag", "svg_or_canvas", "aria_role", "onclick", "tabindex",
         "contenteditable", "listener_tagged", "cursor_pointer"))]
    print(f"  CLICK targets declaring NOTHING the collector may admit: "
          f"{len(nodecl)}/{len(clicks)}")

    if notdom:
        print(f"\n  absent from the parsed DOM ({len(notdom)}) -- every one of them IS "
              f"in the snapshot\n  (id found in the string); run --repair for the cause:")
        for r in notdom:
            print(f"    {r['website']:<13} {r['action_uid'][:8]} {r.get('operation'):<6} "
                  f"id in string x{r.get('in_string')}, "
                  f"parsed DOM carries {r.get('dom_ids')} ids")

    rec = sum(1 for r in scored if r.get("recalled"))
    print(f"\n=== CREDIT PATH ({rec}/{len(scored)} = {rec/max(1,len(scored)):.1%}) ===")
    via = Counter(r.get("via") for r in scored)
    for k in ("own", "ancestor", "descendant"):
        print(f"  {k:<11} {via.get(k,0):>4}   {via.get(k,0)/max(1,rec):.1%} of hits")
    print(f"  {'none':<11} {via.get('none',0):>4}")

    anc_rows = [r for r in scored if r.get("via") == "ancestor"]
    if anc_rows:
        print(f"\n  ANCESTOR credits ({len(anc_rows)}) -- sound only if activating the "
              f"ancestor does what the target did:")
        for r in anc_rows:
            a = r["anc"]
            print(f"    {r['website']:<12} <{r.get('tag')}> {r.get('text','')[:22]!r}"
                  f" -> <{a['tag']}{'/' + a['role'] if a['role'] else ''}>"
                  f" {a['dom_hops']} DOM level(s) up, {a['kids']} listed inside,"
                  f" {a['area_frac']:.0%} of viewport")
    desc_rows = [r for r in scored if r.get("via") == "descendant"]
    if desc_rows:
        print(f"\n  DESCENDANT credits ({len(desc_rows)}) -- sound by event bubbling:")
        for r in desc_rows:
            print(f"    {r['website']:<12} <{r.get('tag')}> {r.get('text','')[:22]!r}"
                  f" -> <{r['desc']['tag']}> {r['desc']['text'][:22]!r}")

    print("\n  recall under stricter ancestor rules (each removes only credits it "
          "cannot justify):")
    own_n = via.get("own", 0); desc_n = via.get("descendant", 0); n = len(scored)
    print(f"    own only                              {own_n}/{n} = {own_n/max(1,n):.1%}")
    print(f"    own + descendant                      {own_n+desc_n}/{n} = "
          f"{(own_n+desc_n)/max(1,n):.1%}")
    # REFUSING AN ANCESTOR CREDIT IS NOT THE SAME AS LOSING THE ROW. `via` names
    # the FIRST path that worked, and ancestor outranks descendant -- so a row
    # shown here as `ancestor` may also have a perfectly good descendant credit
    # underneath it, and the first version of this table assumed it did not.
    # Measured: it reported "mirror the cap -> 165/173 = 95.4%" where running the
    # rule gives 166/173, because the one credit it withdraws (ikea, a <label>
    # credited to a 90%-of-viewport <a>) falls through to that label's own
    # <input>, which is sound by bubbling. The cap costs ZERO recall.
    for name, f in (
            (f"ancestor < {CREDIT_AREA_CAP:.0%} of viewport  <- SHIPPED",
             lambda a: a["anc"]["area_frac"] < CREDIT_AREA_CAP),
            ("ancestor is single-activation",               lambda a: a.get("anc_single_activation")),
            ("ancestor holds < 20 listed elements",         lambda a: a["anc"]["kids"] < 20)):
        kept = [a for a in anc_rows if f(a)]
        fell = [a for a in anc_rows if not f(a)
                and a.get("n_desc_listed") and a.get("cap_allows_desc")]
        k = len(kept) + len(fell)
        print(f"    own + desc + {name:<41} {own_n+desc_n+k}/{n} = "
              f"{(own_n+desc_n+k)/max(1,n):.1%}  ({len(kept)}/{len(anc_rows)} kept"
              + (f", {len(fell)} fall through to a descendant)" if fell else ")"))

    print("\n=== AREA CAP ABLATION (descendant credit) ===")
    blocked = [r for r in scored if not r.get("cap_allows_desc")]
    rec_un = sum(1 for r in scored if r.get("recalled_uncapped"))
    print(f"  targets >= {CREDIT_AREA_CAP:.0%} of the viewport (the cap engages) : {len(blocked)}")
    print(f"  recall capped {rec}/{len(scored)} = {rec/max(1,len(scored)):.1%}   "
          f"uncapped {rec_un}/{len(scored)} = {rec_un/max(1,len(scored)):.1%}")
    if rec_un == rec:
        print("  -> the cap changes NO verdict on the DESCENDANT side: a guard that "
              "has never had to fire. The ancestor side, where a\n"
              "     false credit is structurally possible, now carries the same "
              "bound -- see the stricter-rules table above for what it costs.")

    misses = [r for r in scored if r.get("status") == "missed_present"]
    if misses:
        print(f"\n=== MISSES ({len(misses)}) ===")
        for r in misses:
            on = [k for k, v in (r.get("sig") or {}).items() if v]
            print(f"  {r['website']:<13} {r['action_uid'][:8]} <{r.get('tag')}> "
                  f"{r.get('text','')[:30]!r} {r.get('w')}x{r.get('h')}  "
                  f"declares: {', '.join(on) if on else 'NOTHING'}")

    # CONCENTRATION. 186 actions is not 186 independent observations: they come
    # from a handful of trajectories, and several sites contribute exactly one.
    # A macro average and a leave-one-site-out range say how much one widget can
    # move the headline.
    print("\n=== SAMPLE CONCENTRATION ===")
    bysite = defaultdict(lambda: [0, 0])
    bytraj = defaultdict(lambda: [0, 0])
    for r in scored:
        bysite[r["website"]][1] += 1
        bytraj[r["annotation_id"]][1] += 1
        if r.get("recalled"):
            bysite[r["website"]][0] += 1
            bytraj[r["annotation_id"]][0] += 1
    traj_per_site = defaultdict(set)
    for r in scored:
        traj_per_site[r["website"]].add(r["annotation_id"])
    print(f"  {len(scored)} actions from {len(bytraj)} trajectories across "
          f"{len(bysite)} sites")
    print(f"  sites contributing a single trajectory: "
          f"{sum(1 for v in traj_per_site.values() if len(v) == 1)}/{len(traj_per_site)}")
    print(f"  largest site: {max(bysite.items(), key=lambda x: x[1][1])[0]} "
          f"({max(v[1] for v in bysite.values())} actions, "
          f"{max(v[1] for v in bysite.values())/len(scored):.0%} of the sample)")
    print(f"  micro recall {rec/len(scored):.1%} | "
          f"macro by site {statistics.fmean(v[0]/v[1] for v in bysite.values()):.1%} | "
          f"macro by trajectory "
          f"{statistics.fmean(v[0]/v[1] for v in bytraj.values()):.1%}")
    loo = sorted(((rec - v[0]) / (len(scored) - v[1]), k) for k, v in bysite.items())
    print(f"  leave-one-site-out: {loo[0][0]:.1%} (without {loo[0][1]}) .. "
          f"{loo[-1][0]:.1%} (without {loo[-1][1]})")
    print("  per-site: " + "  ".join(f"{k}={v[0]}/{v[1]}"
                                     for k, v in sorted(bysite.items())))

    if args.repair:
        print("\n=== SERIALIZATION REPAIR ===")
        print("  Mind2Web serializes empty elements XML-style. HTML ignores the "
              "slash, so\n  `<iframe/>` and `<textarea/>` OPEN and swallow the "
              "rest of the document as text.")
        for label in arms:
            summarise(arms[label], label)
        base = {r["action_uid"]: r for r in rows}
        for label in list(arms)[1:]:
            flips = [(r["website"], r["action_uid"][:8],
                      base[r["action_uid"]].get("status"), r.get("status"))
                     for r in arms[label]
                     if base[r["action_uid"]].get("status") != r.get("status")]
            gained = [f for f in flips if f[2] == "not_in_dom"]
            lost = [f for f in flips if f[3] in ("missed_present", "missed_invisible")]
            print(f"  {label}: {len(gained)} recovered from not_in_dom, "
                  f"{len(lost)} credit(s) withdrawn")
            for f in lost:
                print(f"      withdrawn: {f[0]} {f[1]} ({f[2]} -> {f[3]})")

    if args.json:
        Path(args.json).write_text(json.dumps(arms, indent=1), encoding="utf-8")
        print(f"\n-> {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

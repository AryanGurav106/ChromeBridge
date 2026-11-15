#!/usr/bin/env python3
"""Characterise WebPageBench (arXiv:2609.35026) from its RELEASED DATA.

Why this exists
---------------
`docs/SUCCESS-RETENTION.md` is a worked negative result: the attempt to measure
whether our DOM reduction preserves task SUCCESS died on the substrate, in four
named ways. WebPageBench was proposed as the fix. A survey's description of it
was wrong in two places already, so every load-bearing claim is re-derived here
from the repository rather than quoted from the paper (MEASUREMENT.md R1).

This probe is the verification record. It does not run the benchmark, does not
need a browser, does not need a network, and does not need an API key -- it
reads the 152 task JSONs and the frontend's variant registry.

It also emits the SAMPLING FRAME a pre-registration needs: 152 tasks are not 152
independent observations (65 donors + 87 controlled re-renders, and one site is
30% of the set). Deriving the frame mechanically rather than by hand is the #45
lesson -- that entry's headline had to be withdrawn when the author's own prompt
turned out to mandate the behaviour being measured.

Usage
-----
    git lfs install
    GIT_LFS_SKIP_SMUDGE=1 git clone --depth=1 \
        https://github.com/ai-forever/WebPageBench.git <somewhere>

    .venv/bin/python tools/audit_webpagebench.py <path-to-WebPageBench>
    .venv/bin/python tools/audit_webpagebench.py <path> --frame   # sampling frame
    .venv/bin/python tools/audit_webpagebench.py --self-test      # no repo needed

Exit code is 1 if any verified claim FAILS, so this can gate a design decision.
It is also 1 if the path is missing: a probe that cannot reach its subject must
not exit 0, because a silent skip reads exactly like a clean pass (PRINCIPLES
#15 -- a `--check-only` flag that validated zero files and exited 0 is the same
shape, #67).

The repository is UNTRUSTED DATA. Nothing here imports from it or executes it;
the path is an argument and every file is parsed as JSON or read as text.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# What the paper claims, so a failure names the paper's number and ours.
# Source: arXiv:2609.35026v1, 28 Sep 2026, 5 authors, no venue, unreviewed.
PAPER = {
    "tasks": 152,
    "canonical": 65,
    "variants": 87,
    "sites": 6,
    "event_types": 19,
    "conditions": 521,
    "control_keys": 9,
    "implementations": 33,
}

CYRILLIC = re.compile(r"[Ѐ-ӿ]")


# ---------------------------------------------------------------- loading
def load_tasks(root: Path) -> dict[str, dict]:
    tdir = root / "tests" / "bench" / "tasks"
    if not tdir.is_dir():
        die(f"no task directory at {tdir}\n"
            f"    Is {root} really a WebPageBench checkout?")
    out = {}
    for f in sorted(tdir.glob("*.json")):
        try:
            out[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            die(f"could not parse {f.name}: {e}")
    if not out:
        die(f"{tdir} contains no .json tasks")
    return out


def die(msg: str) -> None:
    print(f"FATAL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def registry(root: Path) -> dict[str, list[str]]:
    """Parse UI_VARIANT_IDS out of the frontend's constants.js.

    Read as TEXT with a regex rather than evaluated: it is JS, and it is
    untrusted. A parse failure returns {} and the caller reports the claim as
    UNVERIFIED rather than as passing.
    """
    p = root / "site" / "frontend" / "src" / "bench" / "ui" / "constants.js"
    if not p.is_file():
        return {}
    src = p.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"UI_VARIANT_IDS\s*=\s*\{(.*?)\n\};", src, re.S)
    if not m:
        return {}
    out: dict[str, list[str]] = {}
    for key, body in re.findall(r"(\w+)\s*:\s*\[([^\]]*)\]", m.group(1)):
        out[key] = re.findall(r"'([^']+)'", body)
    return out


# ---------------------------------------------------------------- checks
class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool | None, str]] = []

    def claim(self, name: str, ok: bool | None, detail: str) -> None:
        self.rows.append((name, ok, detail))

    def render(self) -> bool:
        print("\n=== CLAIMS, re-derived from the released data ===")
        w = max(len(n) for n, _, _ in self.rows)
        failed = False
        for name, ok, detail in self.rows:
            tag = "PASS" if ok else ("UNVERIFIED" if ok is None else "FAIL")
            if ok is False:
                failed = True
            print(f"  [{tag:10s}] {name:<{w}s}  {detail}")
        return failed


def audit(root: Path, show_frame: bool) -> int:
    raw = load_tasks(root)
    rep = Report()

    donors = [n for n in raw if "__" not in n]
    variants = [n for n in raw if "__" in n]

    rep.claim("152 tasks", len(raw) == PAPER["tasks"],
              f"{len(raw)} task files (paper: {PAPER['tasks']})")
    rep.claim("65 canonical + 87 variants",
              len(donors) == PAPER["canonical"] and len(variants) == PAPER["variants"],
              f"{len(donors)} canonical + {len(variants)} variants")

    sites = Counter(d["test_data"]["bench_first_domain"] for d in raw.values())
    rep.claim("6 sites", len(sites) == PAPER["sites"],
              f"{len(sites)}: " + ", ".join(f"{k}={v}" for k, v in sites.most_common()))

    # --- the control-swap invariance: THE load-bearing claim ---------------
    # A variant must keep the donor's PROMPT and SUCCESS CONDITIONS identical,
    # changing only which implementation of a control is rendered. If this does
    # not hold exactly, the variant axis is not a controlled experiment and the
    # generality measurement built on it would be comparing two different tasks.
    DEFINING = {"ui_variants", "ui_variant_profile"}
    paired = same_prompt = same_cond = 0
    orphan, leaked = [], []
    for v in variants:
        d = v.split("__")[0]
        if d not in raw:
            orphan.append(v)
            continue
        paired += 1
        A, B = raw[d]["test_data"], raw[v]["test_data"]
        same_prompt += A.get("task") == B.get("task")
        same_cond += A.get("conditions") == B.get("conditions")
        for k in (set(A) | set(B)) - DEFINING:
            if A.get(k) != B.get(k):
                leaked.append((v, k))

    rep.claim("every variant has its donor", not orphan,
              f"{paired}/{len(variants)} paired" + (f", ORPHANS: {orphan[:3]}" if orphan else ""))
    rep.claim("variant keeps donor's PROMPT", same_prompt == paired,
              f"{same_prompt}/{paired} byte-identical")
    rep.claim("variant keeps donor's CONDITIONS", same_cond == paired,
              f"{same_cond}/{paired} byte-identical")
    rep.claim("variant changes ONLY the UI config", not leaked,
              "no other test_data field differs" if not leaked
              else f"{len(leaked)} leaks e.g. {leaked[:3]}")

    # --- the oracle's input ------------------------------------------------
    ev: Counter = Counter()
    ncond = []
    for d in raw.values():
        cs = d["test_data"].get("conditions") or []
        ncond.append(len(cs))
        for c in cs:
            ev[c["event_name"]] += 1
    rep.claim("19 event types", len(ev) == PAPER["event_types"],
              f"{len(ev)} distinct event_name values")
    rep.claim("521 conditions", sum(ncond) == PAPER["conditions"],
              f"{sum(ncond)} conditions; per task min {min(ncond)} "
              f"median {sorted(ncond)[len(ncond) // 2]} max {max(ncond)}")

    # --- no per-step element ground truth ---------------------------------
    # This is NOT a defect for a success measurement -- it is the point. But it
    # means WebPageBench cannot replace bench_mind2web.py, which scores element
    # recall. The two answer different questions and neither substitutes.
    SUSPECT = ("selector", "xpath", "css", "element", "golden", "backend_node",
               "locator", "testid", "click_target")

    def leaves(obj, path=()):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield from leaves(v, path + (k,))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                yield from leaves(v, path + (f"[{i}]",))
        else:
            yield ".".join(path), obj

    gt = {p for d in raw.values() for p, _ in leaves(d)
          if any(s in p.lower() for s in SUSPECT)}
    rep.claim("no per-step ELEMENT ground truth", not gt,
              "success is end-of-task from the event log"
              if not gt else f"found: {sorted(gt)[:4]}")

    # --- the URL loophole -------------------------------------------------
    # Routes are /:track_id/:state_id/<name>, so a `state_changed` condition can
    # be reached by typing a URL. A task whose conditions are ALL navigational
    # could be passed without touching a single control, which would silently
    # void any measurement built on the control-swap axis -- the agent would
    # never exercise the control under test. Quantified rather than assumed.
    nav_only = []
    for n, d in raw.items():
        cs = d["test_data"].get("conditions") or []
        if cs and {c["event_name"] for c in cs} <= {"state_changed"}:
            nav_only.append(n)
    rep.claim("no task is URL-satisfiable alone", not nav_only,
              f"{len(nav_only)}/{len(raw)} tasks have ONLY navigational conditions"
              + (f" -- EXCLUDE: {nav_only[:4]}" if nav_only else
                 "; every task needs a real state mutation"))

    # --- language ---------------------------------------------------------
    cyr = sum(1 for d in raw.values() if CYRILLIC.search(d["test_data"]["task"]))
    rep.claim("task language", None,
              f"{cyr}/{len(raw)} prompts contain Cyrillic "
              f"-- the benchmark is RUSSIAN-language (the paper's abstract "
              f"does not say so, and no survey of it did either)")

    # --- the variant registry --------------------------------------------
    reg = registry(root)
    if reg:
        n_impl = sum(len(v) for v in reg.values())
        rep.claim("9 control keys", len(reg) == PAPER["control_keys"],
                  f"{len(reg)}: {', '.join(sorted(reg))}")
        rep.claim("33 implementations REGISTERED", n_impl == PAPER["implementations"],
                  f"{n_impl} ids in UI_VARIANT_IDS")
        used: dict[str, set] = defaultdict(set)
        for n, d in raw.items():
            for k, val in (d["test_data"].get("ui_variants") or {}).items():
                used[k].add(val)
        n_used = sum(len(v) for v in used.values())
        rep.claim("implementations EXERCISED by tasks", None,
                  f"{n_used} of {n_impl} registered are used by the 152 tasks "
                  f"-- quote 33 as the registry, not as the tested surface")
    else:
        rep.claim("variant registry", None,
                  "constants.js not parsed; registry claims UNVERIFIED")

    failed = rep.render()

    # ---------------------------------------------------------------- frame
    print("\n=== SAMPLING FRAME ===")
    print("152 tasks are NOT 152 independent observations. #73 made this exact")
    print("correction to our own Mind2Web headline: 173 actions came from 22")
    print("trajectories with one widget at 17% of the sample.\n")
    print(f"  independent donor tasks            {len(donors)}")
    print(f"  controlled re-renders of those     {len(variants)}")
    dv = Counter(d["test_data"]["bench_first_domain"]
                 for n, d in raw.items() if "__" in n)
    print("\n  per site (total / variants / share of all tasks):")
    for k, n in sites.most_common():
        print(f"    {k:10s} {n:4d}  {dv[k]:4d}   {n / len(raw):6.1%}")
    top = sites.most_common(1)[0]
    print(f"\n  CONCENTRATION: {top[0]} is {top[1] / len(raw):.0%} of the task set "
          f"({dv[top[0]]} of its {top[1]} are variants).")
    print("  Report leave-one-site-out, as bench_mind2web does.")

    fam = defaultdict(list)
    for v in variants:
        fam[v.split("__")[0]].append(v.split("__", 1)[1])
    print(f"\n  donors carrying variants: {len(fam)} "
          f"(these are the units of the GENERALITY arm, not the 87)")

    prof = Counter(p for ps in fam.values() for p in ps)
    print(f"  distinct variant profiles: {len(prof)}")

    # Which control each family exercises. The generality arm needs the control
    # keys spread across families, or a per-key result is one task's accident.
    keyfam: Counter = Counter()
    for d, ps in fam.items():
        ks = set()
        for p in ps:
            ks |= set((raw[f"{d}__{p}"]["test_data"].get("ui_variants") or {}).keys())
        keyfam.update(ks)
    print("  families exercising each control key:")
    for k, n in keyfam.most_common():
        print(f"    {k:16s} {n} families")

    # The built-in negative control. Our representation is structural, so a
    # pure colour-theme change must move success by ~0. A benchmark that ships
    # its own negative control is rare and it is free (MEASUREMENT.md R3).
    dark = [v for v in variants if "theme_dark" in v]
    print(f"\n  NEGATIVE CONTROL built into the task set: {len(dark)} "
          f"`theme_dark` variants")
    print("    change colour only. A structural representation must score the")
    print("    same on these as on their donors; a gap indicts the instrument")
    print("    (or us) before any other variant result is believed.")

    if show_frame:
        print("\n=== DONOR FAMILIES (the generality arm, in full) ===")
        for d in sorted(fam):
            site = raw[d]["test_data"]["bench_first_domain"]
            print(f"\n  {d}  [{site}]")
            for p in sorted(fam[d]):
                print(f"      __{p}")

    print("\n=== WHAT THIS PROBE DOES NOT ESTABLISH ===")
    print("  * that the site runs. It reads task JSON and one JS file; standing")
    print("    the six sites up needs Docker or an npm build, and nothing here")
    print("    has done that.")
    print("  * that the oracle fires end to end. check() was read and imports")
    print("    only requests/json/re/datetime -- no judge model -- but a live")
    print("    create_track -> events -> check loop has not been run.")
    print("  * anything about ChromeBridge. No arm was run.")
    return 1 if failed else 0


# ---------------------------------------------------------------- self-test
def self_test() -> int:
    """Prove the invariance check can FAIL.

    A detector reporting 'all claims pass' is worth nothing until it has been
    shown to fire (#21 built audit_patterns.py's self-test for exactly this,
    and all three historical bugs it catches had passed code review first).
    The invariance check is the one this design rests on, so it is the one
    that gets a planted violation.
    """
    import tempfile

    ok = True

    def mk(tmp: Path, name: str, prompt: str, conds: list, variants: dict) -> None:
        (tmp / "tests" / "bench" / "tasks").mkdir(parents=True, exist_ok=True)
        (tmp / "tests" / "bench" / "tasks" / f"{name}.json").write_text(
            json.dumps({"test_data": {
                "task": prompt, "conditions": conds,
                "bench_first_domain": "shop", "bench_first_state": "s",
                "ui_variants": variants,
            }}), encoding="utf-8")

    # Clean pair: prompt and conditions identical, only ui_variants differ.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        mk(tmp, "t", "do a thing", [{"event_name": "basket_add"}], {})
        mk(tmp, "t__text_search_pill", "do a thing",
           [{"event_name": "basket_add"}], {"text_search": "pill"})
        raw = load_tasks(tmp)
        A = raw["t"]["test_data"]
        B = raw["t__text_search_pill"]["test_data"]
        clean = A["task"] == B["task"] and A["conditions"] == B["conditions"]
        print(f"  [{'PASS' if clean else 'FAIL'}] clean pair is accepted")
        ok &= clean

    # Planted violation: the variant's CONDITIONS differ. If the check cannot
    # see this, it cannot see a variant that is secretly a different task.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        mk(tmp, "t", "do a thing", [{"event_name": "basket_add"}], {})
        mk(tmp, "t__text_search_pill", "do a thing",
           [{"event_name": "submit_payment"}], {"text_search": "pill"})
        raw = load_tasks(tmp)
        A = raw["t"]["test_data"]
        B = raw["t__text_search_pill"]["test_data"]
        caught = A["conditions"] != B["conditions"]
        print(f"  [{'PASS' if caught else 'FAIL'}] planted condition drift is CAUGHT")
        ok &= caught

    # Planted violation: the variant's PROMPT differs.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        mk(tmp, "t", "do a thing", [{"event_name": "basket_add"}], {})
        mk(tmp, "t__theme_dark", "do a DIFFERENT thing",
           [{"event_name": "basket_add"}], {"theme": "dark"})
        raw = load_tasks(tmp)
        A = raw["t"]["test_data"]
        B = raw["t__theme_dark"]["test_data"]
        caught = A["task"] != B["task"]
        print(f"  [{'PASS' if caught else 'FAIL'}] planted prompt drift is CAUGHT")
        ok &= caught

    # A missing checkout must NOT exit 0.
    with tempfile.TemporaryDirectory() as td:
        try:
            load_tasks(Path(td) / "nope")
            fired = False
        except SystemExit:
            fired = True
        print(f"  [{'PASS' if fired else 'FAIL'}] missing checkout exits nonzero")
        ok &= fired

    return 0 if ok else 1


def main() -> int:
    args = [a for a in sys.argv[1:]]
    if "--self-test" in args:
        print("=== self-test: can the invariance check FAIL? ===")
        return self_test()
    paths = [a for a in args if not a.startswith("-")]
    if not paths:
        print(__doc__)
        die("no path given. Pass a WebPageBench checkout, or --self-test.")
    root = Path(paths[0]).expanduser()
    if not root.is_dir():
        die(f"{root} is not a directory.\n"
            f"    GIT_LFS_SKIP_SMUDGE=1 git clone --depth=1 "
            f"https://github.com/ai-forever/WebPageBench.git")
    print(f"WebPageBench checkout: {root}")
    return audit(root, show_frame="--frame" in args)


if __name__ == "__main__":
    raise SystemExit(main())

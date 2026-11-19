#!/usr/bin/env python3
"""Characterise ComponentBench (arXiv:2608.18307, COLM 2026) from its RELEASED DATA.

Why this exists
---------------
`docs/OPEN.md` item 11 names ComponentBench as the route to the one measurement
this project does not have: whether our DOM reduction preserves task SUCCESS.
`docs/SUCCESS-RETENTION.md` records why the last attempt died -- Mind2Web's
snapshots leaked the gold target through id ordering, stripped every href, and
dropped the step VALUE. ComponentBench is claimed to fix all three.

A paper is not an artefact. `tools/audit_webpagebench.py` is the precedent: it
re-derives every load-bearing claim from the released repository, exits nonzero
when one fails, and self-tests against planted violations so a clean pass means
something (PRINCIPLES 5, 11; MEASUREMENT.md R1). This is its sibling.

It reads the checkout. It does not run the benchmark, does not need a browser,
a network or an API key, and -- deliberately -- does not execute the project's
own build or run scripts.

The question the survey could NOT answer
----------------------------------------
Whether ComponentBench carries per-step ELEMENT ground truth. If it does it is
also a candidate successor to `bench_mind2web.py`, which matters because #79
measured Mind2Web's scripts-and-CSS-free snapshots switching OFF two of the
collector's eight admitting signals -- so our only out-of-sample recall number
is taken with most of the collector's reach disabled.

`--episodes` points at the extracted human episode pack, which is where the
answer lives. Without it that claim reports UNVERIFIED, never PASS: a probe
that cannot reach its subject must not look like a clean pass (PRINCIPLES 15).

Usage
-----
    git clone --depth=1 https://github.com/TianchenGuan/ComponentBench.git <gh>

    # optional, 14.7 MB, for the element-ground-truth claim:
    curl -L -o episodes.tar \\
      https://huggingface.co/datasets/TianchenGuan/ComponentBench/resolve/main/runs_lite/human0_20260312_clean/episodes.tar
    mkdir eps && tar -C eps -xf episodes.tar

    .venv/bin/python tools/audit_componentbench.py <gh>
    .venv/bin/python tools/audit_componentbench.py <gh> --episodes eps/human0_20260312_clean
    .venv/bin/python tools/audit_componentbench.py <gh> --frame
    .venv/bin/python tools/audit_componentbench.py --self-test     # no checkout needed

Exit code is 1 if any verified claim FAILS, so this can gate a design decision.
It is also 1 if the path is missing.

The checkout is UNTRUSTED DATA. Nothing here imports from it or executes it;
every path is an argument and every file is read as text. The task YAMLs are
parsed by an explicit line reader rather than a YAML library, so this probe has
no dependency outside the standard library and nothing in the tree can reach a
loader. The parse is cross-checked against an INDEPENDENT count (the human
reference JSONL) so a silently wrong parser cannot pass.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# What the paper, the README and -- separately -- this project's own OPEN.md
# item 11 claim. A failure names their number and ours.
# Source: arXiv:2608.18307v1, 18 Aug 2026, 5 authors, COLM 2026.
PAPER = {
    "tasks_v1": 2910,
    "tasks_v2": 912,
    "canonical_types": 97,
    "families": 14,
    "templates": 24,
    "libraries": 3,
    "max_steps": 20,
}

# OPEN.md item 11 and SURVEY-2026-11 say ComponentBench is "centred on exactly
# the Radix / shadcn / HeadlessUI / MUI families this project was built
# around". That sentence is the reason the route was ranked where it was, so it
# is checked rather than repeated.
CLAIMED_FAMILIES = {"radix", "shadcn", "headlessui", "mui"}

MODES = ("ax_tree", "som", "pixel", "pixel_grid", "ui_tars_native")


def die(msg: str) -> None:
    print("FATAL: " + msg, file=sys.stderr)
    raise SystemExit(1)


# ------------------------------------------------------------------ loading
_ID = re.compile(r"^- id:\s*(\S+)\s*$")
_KV = re.compile(r"^  ([a-z_]+):\s*(.*?)\s*$")


def parse_tasks(path: Path) -> list[dict]:
    """Read the top-level scalar fields of one task YAML.

    Deliberately NOT a YAML parse. The files are machine generated and the
    fields this probe needs are scalars at a known indentation; a line reader
    removes a dependency the repo does not declare and cannot be reached by
    anything in the untrusted tree. Nested blocks (scene_context, difficulty,
    success_trigger) are detected by their key and recorded as present, which
    is all any claim here needs.
    """
    out: list[dict] = []
    cur: dict | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _ID.match(line)
        if m:
            cur = {"id": m.group(1), "_blocks": set()}
            out.append(cur)
            continue
        if cur is None:
            continue
        k = _KV.match(line)
        if not k:
            continue
        key, val = k.group(1), k.group(2)
        if val == "":
            cur["_blocks"].add(key)
        else:
            cur[key] = val
    return out


def load_all(root: Path) -> tuple[list[dict], list[dict]]:
    v1dir, v2dir = root / "data" / "tasks_v1", root / "data" / "tasks_v2"
    if not v1dir.is_dir():
        die("no task directory at " + str(v1dir) + "\n"
            "    Is " + str(root) + " really a ComponentBench checkout?")
    v1 = [t for f in sorted(v1dir.glob("*.yaml")) for t in parse_tasks(f)]
    v2 = [t for f in sorted(v2dir.glob("*.yaml")) for t in parse_tasks(f)] if v2dir.is_dir() else []
    if not v1:
        die(str(v1dir) + " yielded no tasks; the line parser may have drifted")
    return v1, v2


def jsonl_count(p: Path) -> int:
    if not p.is_file():
        return -1
    return sum(1 for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip())


def read(root: Path, *parts: str) -> str:
    p = root.joinpath(*parts)
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""


# ------------------------------------------------------------------- report
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
            print("  [" + tag.ljust(10) + "] " + name.ljust(w) + "  " + detail)
        return failed


# ------------------------------------------------------- element ground truth
def scan_episodes(epdir: Path) -> dict:
    """Count per-step element identity in the raw human episode pack.

    This is the claim OPEN.md item 11 says is unestablished. The released
    `data/human_traces/v{1,2}_reference.jsonl` carries only step COUNTS and
    KINDS, so reading those alone answers "no". The raw pack is a different
    artefact and answers differently, which is exactly why absence had to be
    checked rather than assumed.
    """
    eroot = epdir / "episodes"
    if not eroot.is_dir():
        eroot = epdir
    if not eroot.is_dir():
        return {}
    react_id = re.compile(r"^:r[0-9a-z]+:$")
    st = {
        "episodes": 0, "empty": 0, "steps": 0, "react_ids": 0,
        "with_identifiable_act": 0,
    }
    per: dict[str, Counter] = defaultdict(Counter)
    urlmode: Counter = Counter()
    viewports: Counter = Counter()
    for e in sorted(eroot.iterdir()):
        if not e.is_dir():
            continue
        st["episodes"] += 1
        tf = e / "trace.jsonl"
        lines = [l for l in tf.read_text(encoding="utf-8", errors="replace").splitlines()
                 if l.strip()] if tf.is_file() else []
        if not lines:
            st["empty"] += 1
            continue
        identifiable = False
        for ln in lines:
            try:
                s = json.loads(ln)
            except json.JSONDecodeError:
                continue
            st["steps"] += 1
            a = str(s.get("type"))
            t = s.get("target") or {}
            per[a]["n"] += 1
            if t:
                per[a]["target"] += 1
            for key in ("testid", "name", "id", "role", "bbox"):
                if t.get(key):
                    per[a][key] += 1
            if t.get("id") and react_id.match(str(t["id"])):
                st["react_ids"] += 1
            if t.get("testid") or t.get("name"):
                per[a]["testid_or_name"] += 1
                if a in ("click", "drag"):
                    identifiable = True
            if s.get("text") is not None:
                per[a]["step_value"] += 1
            u = str(s.get("url", ""))
            urlmode["benchmark" if "mode=benchmark" in u
                    else ("presentation" if "mode=presentation" in u else "unknown")] += 1
            vp = s.get("viewport") or {}
            if vp:
                viewports[(vp.get("w"), vp.get("h"))] += 1
        if identifiable:
            st["with_identifiable_act"] += 1
    st["per"] = per
    st["urlmode"] = urlmode
    st["viewports"] = viewports
    return st


_TASKID = re.compile(r"^(?P<ct>[a-z0-9_]+)-(?P<lib>antd|mui|mantine|external)"
                     r"-(?P<v2>v2-)?T(?P<n>\d+)$")


def resolvable(root: Path, epdir: Path) -> dict:
    """How many recorded targets can be re-found in the component source.

    Task ids are `<canonical_type>-<library>-T<NN>`, and the component that
    renders that task is at site/src/runners/<type>/<library>/T<NN>.tsx -- the
    SAME component benchmark mode renders. So a testid or a visible name
    occurring in that file is evidence the recorded target is addressable on
    the page an agent is scored on, where the recorded bbox is not.
    """
    eroot = epdir / "episodes"
    if not eroot.is_dir():
        eroot = epdir
    runners = root / "site" / "src" / "runners"
    if not (eroot.is_dir() and runners.is_dir()):
        return {}
    out = Counter()
    for e in sorted(eroot.iterdir()):
        m = _TASKID.match(e.name) if e.is_dir() else None
        if not m:
            continue
        sub = [m.group("ct"), m.group("lib")]
        if m.group("v2"):
            sub.append("v2")
        p = runners.joinpath(*sub, "T" + m.group("n") + ".tsx")
        if not p.is_file():
            out["no_component"] += 1
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        tf = e / "trace.jsonl"
        if not tf.is_file():
            continue
        for ln in tf.read_text(encoding="utf-8", errors="replace").splitlines():
            if not ln.strip():
                continue
            try:
                s = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if s.get("type") not in ("click", "drag"):
                continue
            t = s.get("target") or {}
            tid, name = t.get("testid"), t.get("name")
            if tid:
                out["with_testid"] += 1
                out["testid_found" if tid in src else "testid_missing"] += 1
            elif name:
                out["with_name"] += 1
                first = str(name).splitlines()[0].strip()
                out["name_found" if first and first in src else "name_missing"] += 1
            else:
                out["no_identity"] += 1
            # Production strips data-testid (next.config.js reactRemoveProperties),
            # and site/README.md's documented evaluation path is a production
            # build. So the key that survives on the page an agent is scored on
            # is the NAME -- aria-label or innerText -- counted here regardless
            # of whether a testid was also recorded.
            out["prod_named" if name else "prod_unnamed"] += 1
    return dict(out)


# -------------------------------------------------------------------- audit
def audit(root: Path, epdir: Path | None, show_frame: bool) -> int:
    v1, v2 = load_all(root)
    rep = Report()

    # --- counts, cross-checked against an INDEPENDENT source ---------------
    # The human reference JSONL is written by a different pipeline from the
    # task YAMLs, so agreement is evidence the line parser is reading what it
    # thinks it is. A ruler that agrees with nothing is not a ruler (#16).
    ref1 = jsonl_count(root / "data" / "human_traces" / "v1_reference.jsonl")
    ref2 = jsonl_count(root / "data" / "human_traces" / "v2_reference.jsonl")
    rep.claim("parser cross-check", len(v1) == ref1 and len(v2) == ref2,
              "YAML " + str(len(v1)) + "/" + str(len(v2)) + " vs human-trace JSONL "
              + str(ref1) + "/" + str(ref2) + " (independent pipeline)")
    rep.claim("2,910 tasks (v1 Full)", len(v1) == PAPER["tasks_v1"],
              str(len(v1)) + " tasks (paper: " + str(PAPER["tasks_v1"]) + ")")
    rep.claim("912 tasks (v2 Core)", len(v2) == PAPER["tasks_v2"],
              str(len(v2)) + " tasks (paper: " + str(PAPER["tasks_v2"]) + ")")

    types = {t.get("canonical_type") for t in v1} - {None}
    csv_rows = [r for r in read(root, "data", "metadata", "canonical_components.csv").splitlines()[1:] if r.strip()]
    rep.claim("97 canonical component types",
              len(types) == PAPER["canonical_types"] == len(csv_rows),
              str(len(types)) + " distinct in tasks, " + str(len(csv_rows))
              + " rows in canonical_components.csv")

    ont = read(root, "site", "src", "ontology", "ontology.ts")
    fams = re.findall(r"\{\s*id:\s*'([a-z_]+)',\s*name:", ont)
    rep.claim("14 interaction families", len(fams) == PAPER["families"],
              str(len(fams)) + " in the ontology")

    tmpl_csv = {r.split(",")[0] for r in
                read(root, "data", "metadata", "task_templates.csv").splitlines()[1:] if r.strip()}
    tmpl_used = {t.get("task_template") for t in v1} - {None}
    extra = sorted(tmpl_used - tmpl_csv)
    rep.claim("24 task templates", not extra and len(tmpl_csv) == PAPER["templates"],
              str(len(tmpl_csv)) + " declared, " + str(len(tmpl_used)) + " used"
              + ("; UNDECLARED IN USE: " + ", ".join(extra) if extra else ""))

    # --- WHICH component libraries, which is a claim of OURS ---------------
    libs = Counter(t.get("implementation_source") for t in v1)
    real = {k for k in libs if k and k != "external"}
    rep.claim("3 React libraries", len(real) == PAPER["libraries"],
              ", ".join(k + "=" + str(v) for k, v in libs.most_common()))
    rep.claim("OPEN.md 11: 'Radix / shadcn / HeadlessUI / MUI'",
              real <= CLAIMED_FAMILIES,
              "artefact ships " + "/".join(sorted(real)) + "; only MUI overlaps -- "
              "Radix, shadcn and HeadlessUI are ABSENT from site/package.json")

    # --- the oracle --------------------------------------------------------
    # The claim is "programmatic verifier, not an LLM judge". Checked two ways:
    # what the validating module imports, and what the success path actually
    # tests. A judge needs a model client; an import scan finds one.
    taskpy = read(root, "benchmark", "core", "task.py")
    imports = sorted(set(re.findall(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", taskpy, re.M)))
    MODEL_HINTS = ("openai", "anthropic", "google", "genai", "litellm", "transformers",
                   "requests", "httpx", "urllib")
    judgey = [i for i in imports if any(h in i.lower() for h in MODEL_HINTS)]
    rep.claim("oracle imports no model client", not judgey,
              "benchmark/core/task.py imports " + ", ".join(imports)
              + ("" if not judgey else " -- SUSPECT: " + ", ".join(judgey)))

    banner = "cb-success-banner" in taskpy
    selfreport = re.search(r"chat_messages[^\n]*\b(if|in|==)\b", taskpy) is not None
    rep.claim("success is a DOM banner, not self-report", banner and not selfreport,
              "validate() tests #cb-success-banner"
              + (", dataset.taskDone and window.__COMPONENT_BENCH_TASK_DONE__"
                 if "taskDone" in taskpy else "")
              + "; chat_messages is accepted and unused"
              if banner and not selfreport else "banner=" + str(banner))

    # --- does the target VALUE reach the agent's DOM? ----------------------
    # Three independent gates, each read from source:
    #  1. benchmark mode renders ONLY the runner -- no goal, no name, no setup
    #  2. the public task API strips the answer-key fields by default
    #  3. the success predicate is a literal inside the React component
    page = read(root, "site", "app", "task", "[taskId]", "page.tsx")
    bench_block = page.split("if (isBenchmarkMode)")[-1].split("// Presentation mode")[0]
    leaked = [f for f in ("browsergym_goal", "setup_description", "task.name", "ui_copy")
              if f in bench_block]
    rep.claim("benchmark mode renders no goal/answer text", not leaked,
              "the isBenchmarkMode branch renders only the success banner and "
              "<TaskRunner>" if not leaked else "LEAKS: " + ", ".join(leaked))

    api = read(root, "site", "app", "api", "tasks", "[canonicalType]", "route.ts")
    strips = all(f in api for f in ("success_trigger", "negative_cases",
                                    "expected_interaction_path", "notes"))
    default_public = "COMPONENTBENCH_FULL_SPECS" in api and "toPublicTaskSpec" in api
    rep.claim("task API strips the answer key by default", strips and default_public,
              "toPublicTaskSpec() removes success_trigger, negative_cases, "
              "expected_interaction_path and notes; full specs need "
              "COMPONENTBENCH_FULL_SPECS=1" if strips and default_public
              else "strips=" + str(strips) + " gated=" + str(default_public))

    # The authors' own anti-cheat, and the single most consequential detail in
    # the artefact for THIS project: our listing presents data-testid as an
    # attributed name (#23), so on a dev build our arm would read
    # `antd-btn-generate-report` where the AX-tree arm reads nothing. The
    # benchmark strips exactly that in production, and names production as the
    # evaluation path -- so an arm run against `npm run dev` is not comparable
    # with the published numbers.
    ncfg = read(root, "site", "next.config.js")
    stripped = re.findall(r"'\^(data-[a-z-]+)\$'", ncfg)
    prod_only = "NODE_ENV === 'production'" in ncfg
    siteread = read(root, "site", "README.md")
    rep.claim("production strips the semantic data-* attributes",
              bool(stripped) and prod_only,
              str(len(stripped)) + " attributes removed by reactRemoveProperties "
              "ONLY when NODE_ENV=production: " + ", ".join(stripped)
              + ". id and aria-* are preserved")
    rep.claim("...and production is the documented evaluation path",
              "npm run build" in siteread and "npm run start" in siteread,
              "site/README.md gives BENCHMARK_BUILD=1 + npm run build + npm run "
              "start, and notes dev mode pays a 1-2 MINUTE first-request compile "
              "per task page -- unusable at 278 tasks. A dev-build arm sees "
              "data-testid and is NOT comparable with the published numbers")

    runners = root / "site" / "src" / "runners"
    tsx = sorted(runners.rglob("*.ts*")) if runners.is_dir() else []
    srcs = {p: p.read_text(encoding="utf-8", errors="replace") for p in tsx}
    closure = [p for p, s in srcs.items() if "onSuccess()" in s]
    rep.claim("success predicate lives in component code", bool(closure),
              str(len(closure)) + " of " + str(len(tsx))
              + " runner files call onSuccess() from their own state, e.g. "
              "slider_single/antd/T01 fires on `value === 60` -- a literal in the "
              "closure, absent from the DOM")

    # --- observation arms --------------------------------------------------
    missing = [m for m in MODES if ('"' + m + '"') not in taskpy]
    bu = (root / "scripts" / "browser_use" / "run_and_pack.py").is_file()
    rep.claim("observation/action arms implemented", not missing and bu,
              "BrowserGym modes " + ", ".join(MODES)
              + " in OBS_MODES; browser-use is a separate "
              + str(len(read(root, "scripts", "browser_use", "run_and_pack.py").splitlines()))
              + "-line pipeline" if not missing and bu
              else "missing " + ", ".join(missing) + " browser_use=" + str(bu))

    # A reproducible subset is what a pre-registration needs, and deriving our
    # own would be a worse one: theirs is seeded, stratified and committed.
    sub = read(root, "site", "src", "recording-subset-278.json")
    nsub = 0
    if sub:
        try:
            sj = json.loads(sub)
            nsub = len(sj.get("tasks") or [])
        except json.JSONDecodeError:
            nsub = 0
    rep.claim("a stratified subset is DEFINED in the repo", nsub == 278,
              "site/src/recording-subset-278.json holds " + str(nsub)
              + " task ids with a selection_rule, a seed and a stated "
              "difficulty deviation -- 1 task per (canonical_type x library). "
              "Use it; do not derive one")

    proto = read(root, "docs", "evaluation-protocol.md")
    rep.claim("max_steps 20, seed 42, viewport 1280x720",
              "max_steps:** 20" in proto and "42" in proto and "1280" in proto,
              "fixed in docs/evaluation-protocol.md; per-step timeout 300s, "
              "per-task cap 600s")

    # --- determinism, measured rather than quoted --------------------------
    rnd = [p for p, s in srcs.items()
           if re.search(r"Math\.random|Date\.now\(\)|new Date\(\)", s)]
    rep.claim("determinism", None,
              str(len(rnd)) + " of " + str(len(tsx)) + " runner files ("
              + ("{:.1%}".format(len(rnd) / len(tsx)) if tsx else "n/a")
              + ") regenerate content per mount. Inspected cases are filler and "
              "distractor state (prices, file sizes, timestamps, a distractor "
              "switch's defaultChecked); the ORACLE is deterministic, the DOM "
              "text is NOT byte-stable")

    # --- the open question -------------------------------------------------
    ref_fields: set[str] = set()
    rp = root / "data" / "human_traces" / "v1_reference.jsonl"
    if rp.is_file():
        for ln in rp.read_text(encoding="utf-8", errors="replace").splitlines()[:50]:
            if ln.strip():
                try:
                    ref_fields |= set(json.loads(ln))
                except json.JSONDecodeError:
                    pass
    rep.claim("released reference traces: NO element labels",
              bool(ref_fields) and not (ref_fields & {"steps", "target", "target_bid"}),
              "v1_reference.jsonl carries " + ", ".join(sorted(ref_fields))
              + " -- step COUNTS and KINDS only")

    schema = read(root, "schema", "trace.schema.json")
    rep.claim("trace schema DECLARES a per-step target", "target_bid" in schema,
              "trace.schema.json declares target_bid, x, y, text and key per "
              "step -- the shape exists even where the released JSONL does not "
              "populate it")

    st = scan_episodes(epdir) if epdir else {}
    if st:
        per = st["per"]
        acts = sum(per[a]["n"] for a in ("click", "drag"))
        ident = sum(per[a]["testid_or_name"] for a in ("click", "drag"))
        rep.claim("raw human episodes: per-step ELEMENT ground truth", ident > 0,
                  str(st["steps"]) + " steps over " + str(st["episodes"])
                  + " episodes; every step carries tag/id/classes/testid/role/"
                  "name/bbox. " + str(ident) + " of " + str(acts)
                  + " click+drag steps carry a testid or a name ("
                  + "{:.1%}".format(ident / acts if acts else 0) + "), on "
                  + str(st["with_identifiable_act"]) + " of " + str(st["episodes"])
                  + " tasks")
        rep.claim("...usable AS-IS: recorded in the EVALUATED mode",
                  st["urlmode"].get("benchmark", 0) > 0,
                  "all " + str(st["urlmode"].get("presentation", 0))
                  + " steps carry mode=presentation, which renders the goal, the "
                  "task name and setup_description around the component -- a "
                  "DIFFERENT DOM from the benchmark page")
        rep.claim("...usable AS-IS: transferable geometry",
                  len(st["viewports"]) == 1 and (1280, 720) in st["viewports"],
                  str(len(st["viewports"])) + " distinct recording viewports "
                  + str([list(k) for k, _ in st["viewports"].most_common(4)])
                  + ", none of them the harness's 1280x720 -- bboxes do NOT "
                  "transfer, identity must be re-resolved")
        rep.claim("...by a STABLE identifier", None,
                  str(st["react_ids"]) + " of the id values are React auto-ids "
                  "(:rNN:), which change between renders; testid and name are "
                  "the usable keys")
        # Is the label RE-RESOLVABLE against the page an agent is scored on?
        # The two FAILs above say the recorded geometry and surrounding DOM do
        # not transfer, so a ruler must re-find the element by identity. That
        # is only worth building if the identity is actually there. Measured
        # statically against the component that renders the benchmark page.
        rr = resolvable(root, epdir)
        if rr:
            hit = rr["testid_found"] + rr["name_found"]
            tot = rr["with_testid"] + rr["with_name"]
            rep.claim("...and the identity IS in the rendering component",
                      tot > 0 and hit / tot > 0.5,
                      str(hit) + " of " + str(tot) + " identifiable click+drag "
                      "targets (" + "{:.1%}".format(hit / tot if tot else 0)
                      + ") have their testid or name verbatim in the component "
                      "source. A LOWER BOUND: the residue is dominated by "
                      "data-derived testids (mui-btn-view-invoice-0931) that "
                      "exist in the DOM and not in the source. "
                      + str(rr["no_identity"]) + " click+drag steps carry no "
                      "identity at all; " + str(rr["no_component"])
                      + " episodes have no component at the derived path")
            pn, pu = rr.get("prod_named", 0), rr.get("prod_unnamed", 0)
            rep.claim("...SURVIVING the production build", pn > 0,
                      str(pn) + " of " + str(pn + pu) + " click+drag targets ("
                      + "{:.1%}".format(pn / (pn + pu) if pn + pu else 0)
                      + ") carry a NAME (aria-label or innerText). next.config.js "
                      "strips data-testid, data-task-id and five more data-* in "
                      "production -- the authors' own anti-cheat -- and "
                      "site/README.md's documented evaluation path IS a "
                      "production build, so testid is NOT a usable re-resolution "
                      "key on the page agents are scored on")
    else:
        rep.claim("raw human episodes: per-step ELEMENT ground truth", None,
                  "pass --episodes <extracted runs_lite/human0_20260312_clean> "
                  "to settle this. 14.7 MB on HuggingFace")

    # --- the figure that must not travel -----------------------------------
    hay = " ".join(read(root, p) for p in ("README.md",)) + " " + proto \
        + " " + read(root, "docs", "methodology.md") + " " + read(root, "docs", "overview.md")
    rep.claim("'17.3% of tasks flip between runs'", "17.3" not in hay,
              "the string 17.3 appears nowhere in README, protocol, methodology "
              "or overview. A search summary attributed it to this paper; it is "
              "not in the artefact either. Do NOT place it beside "
              "arXiv:2608.06171's measured 12-14% rerun floor")

    failed = rep.render()

    # ---------------------------------------------------------------- frame
    print("\n=== SAMPLING FRAME ===")
    print("2,910 tasks are NOT 2,910 independent observations. #73 made this")
    print("correction to our own Mind2Web headline, where one widget was 17% of")
    print("the sample and leave-one-site-out spanned 95.1-98.1%.\n")
    print("  canonical types                " + str(len(types)))
    print("  families                       " + str(len(fams)))
    print("  tasks per (type, library)      "
          + str(round(len(v1) / max(len(types) * len(libs), 1), 1)) + " on average")
    print("\n  per library:")
    for k, n in libs.most_common():
        print("    " + str(k).ljust(10) + str(n).rjust(5) + "   "
              + "{:6.1%}".format(n / len(v1)))
    diff = Counter(t.get("difficulty_bucket") for t in v1)
    if len(diff) <= 1:
        diff = Counter()
        for f in sorted((root / "data" / "tasks_v1").glob("*.yaml")):
            for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
                m = re.match(r"^      difficulty_bucket:\s*(\S+)", ln)
                if m:
                    diff[m.group(1)] += 1
    if diff:
        print("\n  per difficulty bucket:")
        for k, n in diff.most_common():
            print("    " + str(k).ljust(10) + str(n).rjust(5) + "   "
                  + "{:6.1%}".format(n / len(v1)))
    bytype = Counter(t.get("canonical_type") for t in v1)
    if bytype:
        hi, lo = max(bytype.values()), min(bytype.values())
        print("\n  CONCENTRATION: tasks per canonical type run " + str(lo) + "-"
              + str(hi) + ", i.e. at most " + "{:.1%}".format(hi / len(v1))
              + " of the set -- flat by construction, unlike Mind2Web, where")
        print("  one widget was 17% of the sample.")
        print("  Report leave-one-FAMILY-out; types within a family are not")
        print("  independent (three libraries render the same ontology slot).")

    if show_frame:
        print("\n=== TASKS PER CANONICAL TYPE ===")
        for k, n in Counter(t.get("canonical_type") for t in v1).most_common():
            print("    " + str(k).ljust(30) + str(n).rjust(4))

    print("\n=== WHAT THIS PROBE DOES NOT ESTABLISH ===")
    print("  * that the site builds or runs. It reads task YAML, TypeScript and")
    print("    Python as TEXT. Standing the site up needs `npm install` (518")
    print("    lockfile packages) and nothing here has done that.")
    print("  * that the oracle fires end to end. task.py was read and imports no")
    print("    model client, but a live navigate -> act -> banner loop has not")
    print("    been run.")
    print("  * that an agent cannot reach the answer by another channel. The")
    print("    page fetches /api/tasks/<type>, which returns name, ui_copy and")
    print("    setup_description -- a full natural-language description of the")
    print("    scene. It is NOT the success predicate, and it is strictly more")
    print("    than the goal string. Any arm able to issue a fetch has a")
    print("    channel the four published arms do not.")
    print("  * anything about ChromeBridge. No arm was run.")
    return 1 if failed else 0


# ---------------------------------------------------------------- self-test
def self_test() -> int:
    """Prove the load-bearing checks can FAIL.

    A detector reporting 'all claims pass' is worth nothing until it has been
    shown to fire (PRINCIPLES 11; #21 built audit_patterns.py's self-test for
    exactly this, and all three historical bugs it catches had passed code
    review first). The three planted here are the three this design rests on:
    the answer key being stripped, the oracle not being a model, and the
    per-step element labels being present.
    """
    import tempfile

    ok = True

    def check(label: str, caught: bool) -> None:
        nonlocal ok
        print("  [" + ("PASS" if caught else "FAIL") + "] " + label)
        ok = ok and caught

    # 1. The answer-key strip, removed.
    clean_api = ("const { success_trigger, negative_cases, "
                 "expected_interaction_path, notes, ...rest } = task;\n"
                 "process.env.COMPONENTBENCH_FULL_SPECS === '1' ? tasks : "
                 "tasks.map(toPublicTaskSpec)")
    leaky_api = "return NextResponse.json(tasks);"

    def api_ok(src: str) -> bool:
        return (all(f in src for f in ("success_trigger", "negative_cases",
                                       "expected_interaction_path", "notes"))
                and "COMPONENTBENCH_FULL_SPECS" in src and "toPublicTaskSpec" in src)

    check("clean task API is accepted", api_ok(clean_api))
    check("planted answer-key leak is CAUGHT", not api_ok(leaky_api))

    # 2. A model client planted in the oracle.
    MODEL_HINTS = ("openai", "anthropic", "google", "genai", "litellm",
                   "transformers", "requests", "httpx", "urllib")

    def judge_free(src: str) -> bool:
        imps = re.findall(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", src, re.M)
        return not [i for i in imps if any(h in i.lower() for h in MODEL_HINTS)]

    check("clean oracle is accepted",
          judge_free("import logging\nimport playwright.sync_api\n"))
    check("planted LLM judge is CAUGHT",
          not judge_free("import logging\nfrom openai import OpenAI\n"))

    # 3. Element ground truth, stripped from the traces. This is the claim the
    #    whole exercise turns on, so it gets a real directory rather than a
    #    string test.
    def mk(tmp: Path, with_target: bool) -> Path:
        e = tmp / "episodes" / "demo-antd-T01"
        e.mkdir(parents=True, exist_ok=True)
        step = {"i": 0, "type": "click", "url": "http://x/task/d?mode=presentation",
                "viewport": {"w": 2844, "h": 1412}}
        if with_target:
            step["target"] = {"tag": "SPAN", "id": "", "classes": "c",
                              "testid": "go", "role": "", "name": "Go",
                              "bbox": {"x": 1, "y": 2, "w": 3, "h": 4}}
        (e / "trace.jsonl").write_text(json.dumps(step) + "\n", encoding="utf-8")
        return tmp

    with tempfile.TemporaryDirectory() as td:
        st = scan_episodes(mk(Path(td), True))
        got = st.get("per", {}).get("click", Counter()).get("testid_or_name", 0)
        check("a trace WITH targets reports element ground truth", got == 1)

    with tempfile.TemporaryDirectory() as td:
        st = scan_episodes(mk(Path(td), False))
        got = st.get("per", {}).get("click", Counter()).get("testid_or_name", 0)
        check("a trace WITHOUT targets is CAUGHT as having none", got == 0)

    # 4. The YAML line parser, against a planted shape.
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.yaml"
        p.write_text(
            "- id: button-antd-T01\n"
            "  canonical_type: button\n"
            "  implementation_source: antd\n"
            "  task_template: activate\n"
            "  success_trigger:\n"
            "    human_readable:\n"
            "    - thing\n"
            "- id: button-mui-T02\n"
            "  canonical_type: button\n"
            "  implementation_source: mui\n"
            "  task_template: activate\n", encoding="utf-8")
        ts = parse_tasks(p)
        check("line parser reads two tasks with their fields",
              len(ts) == 2 and ts[0]["implementation_source"] == "antd"
              and ts[1]["id"] == "button-mui-T02"
              and "success_trigger" in ts[0]["_blocks"])

    # 5. A missing checkout must NOT exit 0.
    with tempfile.TemporaryDirectory() as td:
        try:
            load_all(Path(td) / "nope")
            fired = False
        except SystemExit:
            fired = True
        check("missing checkout exits nonzero", fired)

    return 0 if ok else 1


def main() -> int:
    args = sys.argv[1:]
    if "--self-test" in args:
        print("=== self-test: can the load-bearing checks FAIL? ===")
        return self_test()
    epdir = None
    if "--episodes" in args:
        i = args.index("--episodes")
        if i + 1 >= len(args):
            die("--episodes needs a path")
        epdir = Path(args[i + 1]).expanduser()
        if not epdir.is_dir():
            die(str(epdir) + " is not a directory")
        args = args[:i] + args[i + 2:]
    paths = [a for a in args if not a.startswith("-")]
    if not paths:
        print(__doc__)
        die("no path given. Pass a ComponentBench checkout, or --self-test.")
    root = Path(paths[0]).expanduser()
    if not root.is_dir():
        die(str(root) + " is not a directory.\n"
            "    git clone --depth=1 "
            "https://github.com/TianchenGuan/ComponentBench.git")
    print("ComponentBench checkout: " + str(root))
    if epdir:
        print("human episode pack:      " + str(epdir))
    return audit(root, epdir, show_frame="--frame" in sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())

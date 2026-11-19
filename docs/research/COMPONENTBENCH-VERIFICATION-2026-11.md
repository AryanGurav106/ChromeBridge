# ComponentBench, verified at source: the element ground truth EXISTS, and two of our own claims about it do not

**Probe:** `tools/audit_componentbench.py` (sibling of `tools/audit_webpagebench.py`)
**Under test:** ComponentBench @ GitHub `TianchenGuan/ComponentBench`, default
branch `main`, pushed 2026-07-29, MIT — plus the HuggingFace dataset
`TianchenGuan/ComponentBench` @ `b0187fd`, last modified 2026-07-24
**Paper:** arXiv:2608.18307v1, 18 Aug 2026, Guan, Lin, Cheng-Yue, Wang, Zhou. COLM 2026
**Date:** 2026-11-19

> **RESULT IN ONE LINE:** the benchmark is real, released, complete and better
> constructed than its description — and **it DOES carry per-step element
> ground truth**, which `docs/OPEN.md` item 11 and `SURVEY-2026-11.md` both
> record as unestablished. Two claims in our own documents are refuted by the
> artefact. Nothing was run; this is a reading.

---

## The question

`docs/OPEN.md` item 11 is the only measurement debt in this project that has no
instrument at all. Every ruler here scores PRESENCE — `lost_identities` (0
across 258 live sites, #105), findability (0.98 strict, #106), name correctness
against Chrome's AX tree (0.9766 per-site median, #108), Mind2Web element
recall (~95%, #73/#78). **None asks whether a model SUCCEEDS at a task using
our representation.**

`docs/SUCCESS-RETENTION.md` is the worked negative result from the last
attempt. It died on the substrate in four named ways, three of which
ComponentBench is claimed to fix by construction: the gold target leaked
through `backend_node_id` ordering, the step VALUE was stripped, and with no
CSS the responsive duplicates were indistinguishable.

Item 11 says the route is not actionable until the claims are checked against
the artefact, because **a paper is not an artefact** — the precedent being #78,
where WebPageBench's description was wrong in two places before anyone looked.
It also names one thing the survey could not establish:

> The survey also flags one thing it could NOT establish: whether
> ComponentBench has per-step ELEMENT ground truth, which is what would also
> make it a successor to the Mind2Web recall ruler. **Absence not confirmed —
> check, do not assume.**

That instruction is why this paper exists, and it is the instruction that paid.

---

## Method

**Read, never run.** The checkout is untrusted data. It lives in its own empty
directory under the gitignored `temp/`; the probe is in `tools/` and takes the
path as an argument; every file is read as text. Nothing imports from the tree,
nothing executes it, and the benchmark's own build and run scripts were
deliberately not invoked.

**No YAML dependency.** The 116 task files are parsed by an explicit line
reader rather than a YAML library — PyYAML is not in `requirements.txt`, and a
probe that silently skips on a fresh clone is PRINCIPLES 15. The parser is
**cross-checked against an independent source**: the human reference JSONL is
written by a different pipeline, and both report 2,910 / 912. A parser that
agrees with nothing is not a parser.

**Shown to fire before it was believed.** `--self-test` plants five violations
— the answer-key strip removed, an LLM judge imported into the oracle, element
targets stripped from a trace, a malformed task file, a missing checkout — and
all five are caught. 8/8. A detector reporting "all claims pass" is worth
nothing until it has been seen to fail (PRINCIPLES 11).

**Size checked before download.** The HuggingFace dataset reports
`usedStorage: 86,337,359,015` — **86.3 GB**, of which `runs/` is 30.6 GB and
`runs_lite/` 10.2 GB. None of that was pulled. What carries the claims is
`tasks/` 12.0 MB + `results/` 75.3 MB + `difficulty/` 20.1 MB + `human_traces/`
0.7 MB, and the GitHub repo (8.3 MB of files, 45 MB with history) is
self-sufficient for everything except the raw episodes. **14.7 MB** was pulled
for the one claim that needed it.

---

## The numbers

`python tools/audit_componentbench.py <gh> --episodes <eps>`, exit 1.

| claim | verdict | measured |
|---|---|---|
| parser cross-check | PASS | YAML 2910/912 vs human-trace JSONL 2910/912 |
| 2,910 tasks (v1 Full) | **PASS** | 2910 |
| 912 tasks (v2 Core) | **PASS** | 912 |
| 97 canonical component types | **PASS** | 97 distinct in tasks, 97 CSV rows |
| 14 interaction families | PASS | 14 |
| 24 task templates | **FAIL** | 24 declared, **25 used** — `replace_code` is undeclared |
| 3 React libraries | PASS | antd 1000, mantine 970, mui 910, external 30 |
| *OPEN.md 11: "Radix / shadcn / HeadlessUI / MUI"* | **FAIL** | **antd/mantine/mui — only MUI overlaps** |
| oracle imports no model client | **PASS** | `logging`, `typing`, `playwright.sync_api`, `browsergym.core.task` |
| success is a DOM banner, not self-report | **PASS** | `#cb-success-banner`, `dataset.taskDone`, `window.__COMPONENT_BENCH_TASK_DONE__`; `chat_messages` accepted and unused |
| benchmark mode renders no goal/answer text | **PASS** | the `isBenchmarkMode` branch renders only the banner and `<TaskRunner>` |
| task API strips the answer key by default | **PASS** | `toPublicTaskSpec()`; full specs need `COMPONENTBENCH_FULL_SPECS=1` |
| production strips the semantic `data-*` | **PASS** | 8 attributes, `NODE_ENV=production` only; `id` and `aria-*` preserved |
| production is the documented evaluation path | **PASS** | `BENCHMARK_BUILD=1` + `npm run build` + `npm run start` |
| success predicate lives in component code | **PASS** | 3,816 of 4,022 runner files call `onSuccess()` from their own state |
| observation/action arms implemented | **PASS** | 5 BrowserGym modes + an 827-line browser-use pipeline |
| max_steps 20, seed 42, viewport 1280×720 | PASS | plus 300s/step, 600s/task |
| determinism | UNVERIFIED | 67 of 4,022 runner files (1.7%) regenerate content per mount |
| released reference traces: no element labels | PASS | counts and kinds only |
| trace schema DECLARES a per-step target | PASS | `target_bid`, `x`, `y`, `text`, `key` |
| **raw human episodes: per-step ELEMENT ground truth** | **PASS** | **7,773 steps over 2,910 episodes** |
| …usable as-is: recorded in the EVALUATED mode | **FAIL** | all 7,773 steps are `mode=presentation` |
| …usable as-is: transferable geometry | **FAIL** | 4 recording viewports, none 1280×720 |
| …by a STABLE identifier | UNVERIFIED | 551 id values are React auto-ids (`:rNN:`) |
| …and the identity IS in the rendering component | **PASS** | 3,183 of 3,833 (**83.0%**), a lower bound |
| …SURVIVING the production build | **PASS** | 3,350 of 5,615 (**59.7%**) carry a name |
| "17.3% of tasks flip between runs" | **PASS** | the string `17.3` appears nowhere in the artefact |

---

## 1. The open question is answered: YES, with a condition

**`docs/OPEN.md` item 11 and `SURVEY-2026-11.md` §3.3 both record per-step
element ground truth as "not described". The artefact has it.** It is not in
the paper, not in the README, and not in the file the README points at — which
is exactly why "absence not confirmed" was the right instruction.

The released `data/human_traces/v1_reference.jsonl` carries only this:

```json
{"task_id": "accordion-antd-T04", "status": "SUCCESS", "normalized_steps": 2,
 "raw_steps": 2, "duration_ms": 2209, "hover_only": false,
 "chosen_pass": 2, "step_types": ["click", "click"]}
```

Step counts and step kinds. Reading that alone answers "no", and it is what any
survey of the repo would have found.

The RAW episode pack — `runs_lite/human0_20260312_clean/episodes.tar`, 14.7 MB
on HuggingFace, not mentioned in the paper — carries this:

```json
{"i": 0, "t_ms": 2209, "type": "click",
 "url": "http://localhost:3002/task/accordion-antd-T04?mode=presentation&...",
 "viewport": {"w": 2844, "h": 1412},
 "pointer": {"x": 1281, "y": 941, "button": 0, "mod": {...}},
 "target": {"tag": "SPAN", "id": "", "classes": "ant-collapse-header-text",
            "testid": "", "role": "", "name": "API reference",
            "bbox": {"x": 1205, "y": 926, "w": 442, "h": 22}}}
```

Per step: the action, the coordinate, and the target's **tag, id, classes,
data-testid, role, name and bounding box**. For a `type` step it also carries
the VALUE — `"text": "Orion"` — which is the exact field
`SUCCESS-RETENTION.md` records Mind2Web's loader having discarded.

**Measured across the whole pack:**

| | |
|---|---|
| episodes | 2,910 (one per v1 task) |
| episodes with an EMPTY trace | **139**, every one flagged `hover_only: true` in its own meta |
| steps | **7,773** |
| by kind | click 5,481 · type 764 · scroll 744 · key 448 · drag 336 |
| steps carrying a target | 6,187 (79.6%; the residue is `scroll`, which has none) |
| click+drag carrying a testid or a name | **3,976 of 5,817 = 68.4%** |
| tasks with ≥1 identifiable click/drag target | **2,191 of 2,910 = 75.3%** |
| `type` steps carrying their VALUE | **764 of 764 = 100%** |

That is **23× the 173 actions** our Mind2Web ruler scores, on pages that are
live, styled, scripted and deterministic.

### Why that matters more than the raw multiple

#79 measured what Mind2Web's substrate costs us: its snapshots carry no scripts
and no CSS, so `__abClickBound` is 0/173 and `cursor:pointer` is 0/173 —
**two of the collector's eight admitting signals are structurally switched
off**, and the ablation that isolates them removes 59.7% of a live listing's
rows. Our only out-of-sample element-recall number is therefore taken with most
of the collector's reach disabled, and #110 showed the residue is exactly the
elements that declare nothing in static markup.

ComponentBench pages are React apps with real handlers and real CSS. All eight
signals can fire. That is a different question being asked of the same rule.

### The condition, and it is not small

Three facts, each measured, stand between the pack and a working ruler:

1. **All 7,773 steps were recorded in `mode=presentation`**, which renders the
   goal, the task name and `setup_description` in a header around the
   component. The page agents are scored on is `mode=benchmark`, which renders
   only the success banner and `<TaskRunner>`. Same component, different
   document.
2. **Four recording viewports** — 2844×1412, 2560×1271, 1420×1411, 1278×1270 —
   and none of them is the harness's 1280×720. **The bboxes do not transfer.**
3. **551 of the 1,804 recorded `id` values are React auto-ids** (`:rNN:`),
   which change between renders.

So a ruler cannot replay the trace; it must **re-find the element by identity**
on a fresh benchmark render. Is the identity there? Measured statically against
the component that renders the benchmark page (task ids map to
`site/src/runners/<type>/<library>/T<NN>.tsx`):

- **3,183 of 3,833 identifiable click+drag targets (83.0%)** have their testid
  or their first line of name verbatim in that component's source.
- That is a **LOWER BOUND**. The residue is dominated by data-derived testids
  (`mui-btn-view-invoice-0931`, `menu-item-API-PROD-9X2K`) that exist in the
  rendered DOM and not in the source literal.
- 1,782 click+drag steps carry no identity at all, and 120 episodes have no
  component at the derived path.

**And the usable key is the NAME, not the testid** — see §3.

---

## 2. Two of OUR claims are refuted by the artefact

### 2a. It is not the Radix/shadcn/HeadlessUI family

`docs/OPEN.md` item 11 and `SURVEY-2026-11.md` §1.2 both say ComponentBench is
*"centred on exactly the Radix / shadcn / HeadlessUI / MUI families this
project was built around"*, and item 11 adds *"fix #1 in CLAUDE.md exists
because Radix gates on `pointerdown`"*. That sentence is part of why the route
was ranked where it was.

`site/package.json` and 2,910 task records say otherwise:

| library | v1 tasks |
|---|---|
| Ant Design | 1,000 |
| Mantine | 970 |
| MUI | 910 |
| external (markdown/code editors) | 30 |

**Radix, shadcn and HeadlessUI are absent.** Only MUI overlaps. Mantine appears
nowhere in this project's fixture corpus or in any CLAUDE.md entry.

**The artefact wins and the sentence should be corrected — but the conclusion
survives, for a different and arguably better reason.** Ant Design is the
family that has produced this project's *worst* dropdown failures: #25 recorded
Ant Design v6 defeating the option picker entirely and presenting the site's own
nav bar as a field's options; #29 fixed the rc-select decoy listbox; #97 and
#98 — shipped this week — fixed a role-less popup trigger that made `fill_form`
type into a button and report `ok:true`, and a harvest that offered a modal's
Cancel and Create buttons as a combobox's options. antd is 34% of this
benchmark. So the relevance is real and it is **adversarial** rather than
familiar, which is the more useful kind. Mantine is a family we have never
measured at all.

### 2b. 25 task templates, not 24

`data/metadata/task_templates.csv` declares 24; the v1 tasks use 25.
`replace_code` is used and undeclared. A trivial defect in their metadata, and
the kind of thing a count-not-an-inventory check exists to catch (PRINCIPLES
16). Reported because a probe that silently rounds its subject's numbers to its
subject's prose is not a probe.

---

## 3. The anti-cheat, and the one detail that decides arm fairness for us

This is the most consequential thing in the artefact for **this** project, and
no description of ComponentBench mentions it.

`site/next.config.js`:

```js
// Strip semantic data-* attributes in production to prevent DOM-based agent cheating.
// Preserved: id, data-cb, aria-* attributes.
reactRemoveProperties: process.env.NODE_ENV === 'production'
  ? { properties: ['^data-testid$', '^data-task-id$', '^data-canonical-type$',
                   '^data-library$', '^data-view-mode$', '^data-reference-id$',
                   '^data-icon-key$', '^data-reference-icon-key$'] }
  : false,
```

**In a dev server, `data-testid` is in the DOM. In a production build it is
not.** 3,371 of the runner files set one, and they are semantically rich —
`antd-btn-generate-report`, `project-name-input`, `slider-volume`.

#23 recorded that our listing presents `data-testid` as an accessible name,
attributed on the row, on the stated argument that it beats nothing on an icon
control. On a **dev** build of ComponentBench our arm would read
`antd-btn-generate-report` on the button whose goal is "Click the Generate
report button", while the AX-tree arm reads nothing of the kind. That is a
semantic channel the four published arms do not have, and the benchmark's
authors name it as cheating in their own comment.

`site/README.md` settles which build to use: the documented evaluation path is
`BENCHMARK_BUILD=1; npm run build; PORT=3002 npm run start`, and it notes dev
mode pays a **1–2 minute first-request compile per task page** — unusable at
278 tasks regardless.

**Consequences, both of which must travel with any plan:**

- **Any ChromeBridge arm must run against a production build.** A dev-build
  number is not comparable with the published 83.1%/48.9%, and would flatter us
  for a reason unrelated to the representation.
- **The re-resolution key for the element ground truth is the NAME, not the
  testid.** Measured: **3,350 of 5,615 click+drag targets (59.7%)** carry a
  name — `aria-label` or `innerText`, which is how the recorder derives it
  (`(el.getAttribute('aria-label') || el.innerText || '').slice(0, 120)`).
  The other 40% are targets a human clicked that carry no accessible name at
  all, and those are not scoreable.

A smaller asymmetry, recorded so it is not rediscovered: the page itself
fetches `/api/tasks/<canonical_type>`, which returns `PublicTaskSpec` — the
answer key is stripped, but `name`, `ui_copy` and `setup_description` survive,
and `setup_description` is a full natural-language description of the scene and
its behaviour. It is strictly more than the goal string. Any arm that can issue
a fetch — ours can, through `javascript_tool` — has a channel the BrowserGym
arms do not. **Pin the toolset and report the fallback rate**, which is the
confound item 11 already names.

---

## 4. The oracle, and what "hidden in React closures" actually means

The claim verifies, and the mechanism is simpler than the phrase suggests.

`benchmark/core/task.py::validate()` is called after every agent action and
does three DOM tests in order: `page.locator("#cb-success-banner").count() > 0`,
then `document.documentElement.dataset.taskDone === 'true'`, then
`window.__COMPONENT_BENCH_TASK_DONE__ === true`. The module imports `logging`,
`typing`, `playwright.sync_api` and `browsergym.core.task` — **no model client,
no HTTP client of any kind**. `chat_messages` is in the signature and is never
read, which is the structural form of "do not trust the agent's own done
signal"; `docs/evaluation-protocol.md` says so in words as well, with a
specific caveat for browser-use's built-in `done(success=True)`.

The predicate is a literal in the component. `slider_single/antd/T01.tsx`:

```tsx
export default function T01({ onSuccess }: TaskComponentProps) {
  const [value, setValue] = useState(20);
  useEffect(() => { if (value === 60) { onSuccess(); } }, [value, onSuccess]);
```

`60` is in the compiled JS bundle and in no DOM node. The page shows marks
0..100 and `Current: 20`. 3,816 of 4,022 runner files follow that shape.

**Honest residue:** "not in the DOM" is not "unreachable". The predicate is in
a JS chunk, and an agent that can fetch and read its own page's bundle could in
principle find it. No published arm can do that; ours could. Same pin, same
fallback rate.

---

## 5. Determinism: the oracle is, the DOM is not

`docs/evaluation-protocol.md` says "Random seed: 42 (`task_seed`); tasks are
otherwise deterministic". Measured: **67 of 4,022 runner files (1.7%)** call
`Math.random()`, `Date.now()` or `new Date()` at mount.

Inspected, every case found is filler or distractor state — pagination row
prices (`$${(Math.random() * 100).toFixed(2)}`), file sizes, feed timestamps,
`isStarred` on decorative rows, and `defaultChecked={Math.random() > 0.5}` on
**distractor** switches in `button/antd/T05` and `button/mantine/T05`, whose
success is a separate "Save changes" click. I found no case where the random
value determines success, and the inspection was a sample rather than a sweep —
hence UNVERIFIED rather than PASS.

**The distinction that matters: the ORACLE is deterministic; the DOM TEXT is
not byte-stable.** A success measurement is unaffected. A token measurement, or
any exact-match invariance check of the kind `audit_generality_live.py` runs,
would see drift on those tasks and must exclude them or report a floor.

---

## 6. Feasibility

**Verdict in one line: feasible, one arm, and the binding cost is model time
rather than disk — budget a day for the harness and roughly 2–3 hours of serial
agent time per arm over a 278-task subset, against ~1.5–2.5 GB of
`node_modules` and a Next.js production build of unmeasured duration.**

| | |
|---|---|
| GitHub checkout | 8.3 MB of files, 45 MB with history, MIT |
| HuggingFace, total | **86.3 GB** — `runs/` 30.6 GB, `runs_lite/` 10.2 GB; **do not clone it** |
| HuggingFace, what is needed | tasks 12.0 + results 75.3 + difficulty 20.1 + human_traces 0.7 MB; **14.7 MB** for the episode pack |
| `node_modules` | **estimate 1.5–2.5 GB**, NOT measured. 518 lockfile packages; `next` 192 MB, `monaco-editor` 101 MB, `antd` 49 MB, `@mantine/core` 10.7 MB, `@mui/material` 8.5 MB unpacked at latest |
| Node | 20+ |
| Python | 3.11–3.13 — our `.venv` is 3.12.15, compatible, **and not needed for a ChromeBridge arm** |
| network at runtime | **none.** No CDN, no Google Fonts, no external asset reference in `site/app` or `site/src`; the API reads YAML off disk |
| build | `BENCHMARK_BUILD=1 npm run build` then `PORT=3002 npm run start`. **Duration unmeasured** — 4,022 runner files plus antd + MUI + Mantine + Monaco + TipTap + CodeMirror is a large Next.js build |

**The arm interface is the browser-use pipeline, not BrowserGym.** Four arms
are BrowserGym observation modes defined in a dict in `benchmark/core/task.py`;
the fifth, browser-use, is a **standalone 827-line script**
(`scripts/browser_use/run_and_pack.py`) that takes `--server-url
http://127.0.0.1:3002`, reads the same task YAMLs for `browsergym_goal`, drives
its own browser, polls `#cb-success-banner`, and writes `episode.json`. That is
the template, and it is the right one: ChromeBridge is not a BrowserGym agent,
it is an MCP server driven by Claude Code, so the arm is a Claude Code subagent
with the ChromeBridge toolset — the shape `tools/bench_turns/` already uses.

**Three things make this cheaper for us than for the published arms:**

- **The oracle needs no key.** Success is
  `query_elements("#cb-success-banner")` with `total >= 1`. Every published arm
  needs an API key for its agent; ours bills the user's Claude subscription,
  which is the zero-key architecture paying off on a benchmark for once.
- **Self-hosted on `localhost:3002`**, so the per-origin gate is granted once
  in a throwaway profile — `tools/run_flows.py` has done exactly this in CI
  since #50, on port 8901 outside the default span. `ALLOW_ALL_ORIGINS` is not
  touched.
- **The task set is flat.** Tasks per canonical type run 30–30, i.e. at most
  1.0% of the set, against Mind2Web where one widget is 17% (#73). Report
  leave-one-FAMILY-out, not leave-one-type-out: three libraries render the same
  ontology slot, so types within a family are not independent.

**Time.** Human reference is 2.7 normalized steps on v1; the published cap is
20 steps and 600s/task. A ChromeBridge episode is plausibly 4–6 model turns
(one `browser_batch` to create-navigate-read, 2–4 action turns, one verify) at
~3.6s each (#38), so ~30s/task plus page load. #39 established that parallel
agents corrupt each other's tab groups, so runs are serial. **278 tasks ≈
2.5 hours per arm; a stratified 97 (one per canonical type) ≈ 1 hour.** The
benchmark ships the subset as a committed, seeded, stratified list —
`site/src/recording-subset-278.json`, 278 task ids, one per
(canonical_type × library), with a `selection_rule`, a `seed` and a stated
`difficulty_deviation` against the global distribution. **Use it rather than
deriving one**; it is also the set the human reference traces were recorded
against.

> **This paragraph said the opposite in its first draft**, on the strength of a
> `grep` whose `--include` flags zsh had rejected — so a failed command was
> read as a negative result. PRINCIPLES 15 in miniature, caught by re-deriving
> the claim before reporting it rather than by anything in the probe. The probe
> now carries it as a claim so the next reader gets it from the tool.

---

## 7. What a number from this would, and would not, license

PRINCIPLES 9 — an ablation measures the code against the sample, and cannot
measure the sample. This sample is **generated React component demos**, and
that cuts both ways.

**It would license:** "on isolated interactions with Ant Design, MUI and
Mantine components, swapping the observation space from X to ChromeBridge moves
end-to-end task success by N points, oracle-scored, with the model held fixed."
That is the first success-axis number this project has ever had, and the first
on a substrate where all eight admitting signals can fire.

**It would NOT license** any claim about the open web. Every page is one
component in a card, authored by one team to one convention, in English, with
no ads, no consent walls, no cross-origin frames, no login, no legacy markup
and no framework this project has not already seen. `lost_identities = 0` across
260 live sites (#85) is a claim about the web; a ComponentBench number is a
claim about component libraries. They are not substitutes and neither
generalises to the other.

**Two specific confounds to pre-register:**

- `javascript_tool`, `search_page` and `read_network_requests` can reach the
  `/api/tasks/<type>` description and the JS bundle. Pin the toolset and report
  the fallback rate, or the number measures Claude's ingenuity.
- The tasks are single-component, so `browser_batch` (#38's whole lever) and
  scoped reads have almost nothing to do. This benchmark is close to a
  worst-case for our turn-efficiency argument and a best case for our
  per-observation argument. Say which is being measured.

---

## 8. What this probe does NOT establish

- **That the site builds or runs.** Task YAML, TypeScript and Python were read
  as text. `npm install` was not run; the 1.5–2.5 GB and the build duration are
  estimates and are labelled as such.
- **That the oracle fires end to end.** `validate()` was read and imports no
  model client, but no live navigate → act → banner loop was run.
- **That the element ground truth re-resolves on a live benchmark render.**
  83.0% is a STATIC source match, and 59.7% is the production-surviving name
  rate. The real figure needs the site standing up and a re-resolution pass,
  and it could go either way: data-derived testids push it up, duplicate names
  within a component push it down.
- **Whether the published 83.1% / 48.9% numbers were obtained against a
  production build.** The authors document production as the evaluation path
  and strip `data-testid` there, but no run manifest in the released results
  records `NODE_ENV`. If any published arm ran against a dev server, its
  serialized-DOM arm saw testids. This should be asked before any comparison.
- **Anything about ChromeBridge.** No arm was run.

---

## 9. One figure that must not travel, confirmed a second way

A search summary attributed *"17.3% of tasks flipping between identical runs"*
to ComponentBench. `SURVEY-2026-11.md` §4 records that the surveying agent
checked the **paper** and it is not there. This probe checked the **artefact**:
the string `17.3` appears nowhere in the README, the evaluation protocol, the
methodology or the overview. There is a `shard7_rerun` directory in the raw
runs, so reruns happened; no flip-rate figure is published from them.

Do not place it beside arXiv:2608.06171's measured 12–14% rerun noise floor as
if it were a second data point. That floor still has one source.

---

## 10. What it would take to decide what is left open

| open | what decides it | cost |
|---|---|---|
| does the element GT re-resolve live? | stand up a production build, render 278 benchmark pages, re-find each recorded target by name/role/text, report CORRECT/AMBIGUOUS/MISSING | ~1 day, after the build |
| `node_modules` size and build duration | `npm install && npm run build`, measured | ~1 hour |
| were the published numbers taken on a production build? | ask the authors, or find `NODE_ENV` in a run manifest inside a `runs/` tar | one email, or 30 GB |
| is the 1.7% randomness ever load-bearing? | sweep the 67 files for a random value reaching a success predicate | ~1 hour |
| ~~which 278 tasks are the subset?~~ | **CLOSED** — `site/src/recording-subset-278.json`, seeded and stratified | done |
| does ComponentBench beat Mind2Web as a recall ruler? | **not decidable from here.** It is a different population: live styled React components vs stripped static snapshots of real commercial sites. It would be a SECOND out-of-sample ruler, not a successor | — |

**`MEASUREMENT.md` §6 should be amended, not rewritten.** It says "there is no
successor dataset" and "the 2023 release is the only family member with a
per-step element label". The first clause is about the *Mind2Web family* and
stands. The second is now too strong as a general statement: ComponentBench has
per-step element labels, on a different population, undocumented, in the raw
episode pack. And §3.3's conjunction row for ComponentBench —
"per-step element labels: **not described**" — should read "**present but
undocumented; recorded in presentation mode at four non-harness viewports, so
usable only by re-resolution**".

---

## Artefacts

- `tools/audit_componentbench.py` — exits 1 on any failed claim; `--self-test`
  plants five violations and catches all five; `--frame` prints the full
  per-type sampling frame.
- Checkout and episode pack under `temp/componentbench/` (gitignored). Rebuild:

```bash
git clone --depth=1 https://github.com/TianchenGuan/ComponentBench.git temp/componentbench/gh
curl -L -o /tmp/eps.tar \
  https://huggingface.co/datasets/TianchenGuan/ComponentBench/resolve/main/runs_lite/human0_20260312_clean/episodes.tar
mkdir -p temp/componentbench/hf/human_eps && tar -C temp/componentbench/hf/human_eps -xf /tmp/eps.tar
.venv/bin/python tools/audit_componentbench.py temp/componentbench/gh \
  --episodes temp/componentbench/hf/human_eps/human0_20260312_clean
```

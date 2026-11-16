# EVAL 5 — REFEREE KEY

Independently re-derived from the live sites on **2026-11-16** by walking each
scenario's steps. Input was `referee_input.md` only; `tasks.md` was not opened
and no answer was seen from any other source. **No contamination to disclose.**

Method note: BLS, ETH, USGS, Bank of Canada, PyTorch and USNO were driven in a
real browser (the sites either block non-browser clients or need dependent form
state). Olympedia, IETF Datatracker, NCES and Japan Post were read from their
live HTML directly. Where a scenario had an underlying API (Bank of Canada
Valet, USGS FDSNWS) the figure was cross-checked against it.

Summary: **10/10 completed.** **3 recommended DROP / REWORD** (T1, T4, T5).
**3 time-sensitive** (T4 severely; T1 and T7 moderately; T5 mildly).

---

## T1 — BLS Occupation Finder

**Count of occupations matching both filters:** `96`

Verified from the page's own status line, produced by its own two dropdowns:
`Showing 1 to 25 of 96 entries (filtered from 831 total entries)`.
The `831` in the scenario's step 6 is correct.

**First row of page 3 (entries 51–75), sorted A→Z:** `Law teachers, postsecondary`

**Confidence:** High on `96`. **Low on the occupation name — see the flag.**

### FLAG — RECOMMEND DROP (or reword step 7). Two defensible answers.

Step 7 says *"Click the OCCUPATION column header once to sort the table
alphabetically A→Z."* **The table is already sorted A→Z on a pristine load.**
Measured on a clean reload: `<th>OCCUPATION</th>` carries `class="sorting_asc"`
and `aria-sort="ascending"`, `DataTable.order()` is `[[0,"asc"]]`, and the
unfiltered first rows are Accountants and auditors / Actors / Actuaries.
The column's `asSorting` is `["asc","desc"]`, so **one real click toggles it to
DESCENDING.** Confirmed by clicking it for real:

| sort state | page 3, first row |
|---|---|
| ascending (A→Z — the step's stated *intent*) | `Law teachers, postsecondary` |
| descending (what one click *actually* produces) | `Healthcare diagnosing or treating practitioners, all other` |

An agent following the step's stated goal lands on the first; an agent following
the instruction literally lands on the second. Both are defensible, so the
question does not have exactly one answer as written.

Cheapest fix: replace step 7 with *"Confirm the table is already sorted
alphabetically A→Z by OCCUPATION (no click needed)"*, or *"click the OCCUPATION
header twice"*. With that, the answer is `96` and `Law teachers, postsecondary`.

### FLAG — time-sensitive (moderate)
The pay column is literally headed **2025 MEDIAN PAY**. When BLS publishes the
next OOH edition the column becomes 2026 and the 96 will move.

### Incidental
The `2025 MEDIAN PAY` column holds **banded** values (`$100,000 or more`,
`$75,000 to $99,999`, …), not dollar figures. The filter options are exactly
`$100,000 or more` / `$75,000 to $99,999` / `$50,000 to $74,999` /
`$37,500 to $49,999` / `Less than $37,500` / `The annual wage is not available.`

---

## T2 — ETH Zürich course catalogue

**Course number:** `401-1151-00L`
**ECTS credits:** `7`
(Title `Linear Algebra I`, type O, 4V + 2U, lecturer S. Zerbes.)

**Confidence:** High. Walked the full dependent-dropdown chain in the browser.
Block 2 contains exactly one course unit, as the scenario states. Block 1 has
three (401-1261-07L Analysis I, 402-1701-00L Physics I, 252-0847-00L Computer
Science), so there is no confusion about which block is which.

**Time-sensitive:** No. Autumn Semester 2024 is an archived past semester.

**Steps verified:** Semester → Autumn Semester 2024 reloads the form; Level →
Bachelor's Degree Programme drops Programme to `31` and Department to `15`
(both as stated); a **Section** dropdown then appears that did not exist before,
containing `First Year Compulsory Courses`; results group under *First Year
Examination Block 1* and *First Year Examination Block 2*.

**Incidental (not load-bearing):** step 3 says Programme drops "from 184
options"; at Autumn Semester 2024 the pre-filter count is **186**, not 184. The
"to 31" and "17 to 15" figures are exactly right. Worth correcting the 184 so a
careful agent is not tripped by a number that does not match what it sees.

---

## T3 — Olympedia, 2008 men's 800 m

**Competitor in 4th position, Semi-Finals Heat #3:** `Manuel Olmedo`
**NOC:** `ESP`
**Time (Automatic):** `1:45.91`

**Confidence:** High. Read from `olympedia.org/results/257197`, reached by the
stated path (Games → Overview → XXIX / 2008 / Beijing = edition 53 → Athletics →
800 metres, Men). Heat #3 full order: 1 Nabil Madi 1:45.63 Q, 2 Gary Reed
1:45.85 Q, 3 Boaz Lalang 1:45.87, **4 Manuel Olmedo 1:45.91**, 5 Belal Mansoor
Ali 1:46.37, 6 Michael Rimmer 1:48.07, 7 Abraham Chepkirwok 1:49.16,
8 Abubaker Kaki Khamis 1:49.19. There is only one time column, so "Time
(Automatic)" is unambiguous.

**Time-sensitive:** No (historical result). Olympedia is volunteer-maintained,
so the usual low-grade risk of an edit applies, but nothing here is derived or
disputed.

---

## T4 — PyTorch LibTorch configurator

**Contents of the "Run this Command:" box** (verified by clicking the real
matrix: Stable → Linux → LibTorch → C++ / Java → CUDA 13.2):

```
Download here (cxx11 ABI):
https://download.pytorch.org/libtorch/cu132/libtorch-shared-with-deps-2.15.0%2Bcu132.zip
```

**The single verifiable end-state value:** `https://download.pytorch.org/libtorch/cu132/libtorch-shared-with-deps-2.15.0%2Bcu132.zip`

If a shorter atom is wanted, the filename `libtorch-shared-with-deps-2.15.0+cu132.zip`,
whose only live-derived component is the stable version number `2.15.0`.

**Confidence:** High on the value. Confirmed `cuda.x` is labelled **CUDA 13.2**
(the row also offers CUDA 13.4 and CUDA 12.8 today). The box renders a single
link; there is no longer a second "Pre-cxx11 ABI" line.

### FLAG — CONFIRMED UNGRADEABLE AS WRITTEN. The mechanical check is right.

Every token in that box is already determined by the selections the instructions
*state*:

| token in the box | where it comes from |
|---|---|
| `libtorch` | step 5 says LibTorch |
| `cu132` | step 7 says CUDA 13.2 |
| `shared-with-deps` (vs `win-`/`macos-arm64-`) | step 4 says Linux |
| `cxx11 ABI` | the only ABI offered |
| `Download here` | fixed boilerplate |

The **only** fact that must be read off the live page is the stable version
`2.15.0`. So the question must ask for the full URL, the filename, or the
version number. As written it can be answered without visiting the page.

### FLAG — time-sensitive (SEVERE)
PyTorch ships a minor release roughly quarterly, so `2.15.0` has a short shelf
life, and the Compute Platform labels churn with it (CUDA 13.2 / 13.4 / 12.8
today). This task needs re-verification immediately before any run, and a graded
answer keyed on `2.15.0` will go stale faster than anything else in this set.

---

## T5 — NCES College Navigator, two Vermont universities

From each institution's **Estimated expenses for academic year** table,
**In-state** row, **2024-2025** column (i.e. tuition and fees):

**University of Vermont (id 231174):** `$19,058`
**Vermont State University (id 231165):** `$11,952`
**Higher:** `University of Vermont`
**Difference:** `$7,106`

**Confidence:** High on the two figures.

### FLAG — CONFIRMED ECHOABLE. The mechanical check is right.

Both institution names are supplied verbatim by the instructions (step 4
"University of Vermont", step 8 "Vermont State University"). A question of the
form *"which had the higher/lower …"* can be answered by naming one of the two
strings it was just handed — a 50/50 guess that a grader cannot distinguish from
a real walk.

**The values only obtainable from the live pages are the dollar figures
`$19,058` and `$11,952`** (or their difference, `$7,106`). The question should
require at least one of those.

### FLAG — second ambiguity, smaller
The expenses block renders as one table with two header bands, and the string
"In-state" appears **twice**: once under *Tuition and fees* (a single value) and
once under *Total Expenses* (a band heading over three sub-rows: On Campus /
Off Campus / Off Campus with Family). Only the first is a single number, so
"the In-state row" resolves — but a grader should state which, because the
Total Expenses In-state On-Campus figures ($36,802 UVM / $33,274 VTSU) are a
plausible wrong-but-careful answer. **Recommend rewording to "In-state tuition
and fees".** With that + a dollar figure requested, T5 is gradeable; without
either change I would drop it.

### FLAG — time-sensitive (mild)
The table's rightmost column advances with each IPEDS release; a `2024-2025`
column will eventually be joined or replaced by `2025-2026`.

---

## T6 — IETF Datatracker

**RFC number:** `RFC 8556`
**Title:** `Multicast VPN Using Bit Index Explicit Replication (BIER)`
**Publication date:** `2019-04` (April 2019)

Also shown on the row: Proposed Standard RFC, 17 pages, AD Alvaro Retana.

**Confidence:** High. The narrowing chain reproduces exactly:
`multicast` + WG `bier` + RFCs only → **three** RFCs (8279, 8556, 9624), matching
step 7; changing the term to `multicast vpn` → **exactly one hit**, RFC 8556,
matching step 9.

**Time-sensitive:** No. Published RFCs are immutable and the BIER WG's RFC set
grows slowly; a new BIER RFC titled with "multicast vpn" would be needed to
disturb it.

**Incidental (not load-bearing):** I could not reproduce step 3's banner text
*"Too many documents match your query! Returning only a partial result (200
matches)."* from a plain fetch of the broad search — it is likely rendered
client-side. It is narrative only; the graded value does not depend on it.

---

## T7 — USGS earthquake catalogue

**Number of earthquakes returned:** `17`
(The sidebar header reads `Showing 17 earthquakes`.)

**After switching Sort from Time to Magnitude, the top event:**
**Magnitude:** `8.2`
**Depth:** `600.0 km`
(Place "2018 Fiji Earthquake", 2018-08-19 00:19:40 UTC.)

**Confidence:** High. Verified in the live map/list viewer and independently
cross-checked against the FDSNWS API
(`/count` → `{"count":17}`; `orderby=magnitude` → 8.2 at depth 600 km).
The Sort control has exactly two options, `Time` and `Magnitude`, as stated.

### FLAG — time-sensitive (moderate)
USGS revises reviewed events. Two of the seventeen sit **exactly at M 7.0** (the
2018-12-29 Philippines and 2018-10-10 PNG events), so a routine downward
revision of either drops the count to 16. The API shows events in this set being
updated as recently as 2026. The top event (M 8.2) is far from the boundary and
is safe; **the count `17` is the fragile half.** Re-verify before a run.

---

## T8 — Bank of Canada currency converter

**Value of 250.00 CAD in JPY on 2024-09-03:** `26,910.65 JPY`
**CAD → JPY rate:** `107.6426`

(The results table also shows JPY → CAD `0.009290`.)

**Confidence:** Very high. Read from the converter's own Results table after
walking the steps, and independently confirmed against the Bank's Valet API
(`FXCADJPY` for 2024-09-03 = 107.6426; 250 × 107.6426 = 26,910.65 exactly).

**Time-sensitive:** **No.** This is the most stable task in the set — a
published historical daily rate. The Custom-dates flow behaved exactly as
described (the two fields "Start (or single date)" and "End date" appear only
after switching the range selector).

---

## T9 — USNO civil twilight table

**Sept., day 15, 2027, Juneau AK — Begin:** `0447` (04:47)
**End:** `1857` (18:57)

**Confidence:** Very high. Walked the real form and also reproduced the table
directly. Step 7 is exactly right: the US Location dialog fills Latitude `58.3`,
Longitude `-134.42`, Location Label `Juneau, AK`, time zone `9` **west**
(`tz_sign = -1`). The table header confirms `Location: W134 25, N58 18`,
`Civil Twilight for 2027`, `Zone: 9h West of Greenwich`.

Full day-15 row for column counting (Jan.→Dec.):
`15  0744 1631  0648 1736  0534 1840  0403 1955  0235 2115  0134 2223  0210 2156  0332 2030  0447 1857  0553 1732  0700 1624  0748 1558`
— the 9th Begin/End pair is Sept.

**Time-sensitive:** No. Deterministic astronomical computation for a future year.

---

## T10 — 日本郵便 postal-code lookup

**郵便番号 for 石川県珠洲市狼煙町 (ノロシマチ):** `927-1441`

**Confidence:** Very high. Walked the live path: 都道府県 石川 (`pref=17`) →
珠洲市 (`city=1172050`, listed under サ行 by its reading スズシ, immediately below
the 珠洲郡内浦町 entry annotated 「鳳珠郡能登町に住所変更」exactly as step 4
warns) → ナ行 tab → 狼煙町 ノロシマチ → `927-1441`.

**Time-sensitive:** No.

### FLAG — the question line is MISSING from the referee input
T10 is the only scenario with no `**Question:**` line at all in
`referee_input.md` (it ends at step 7). The redaction whitelist appears to have
removed the whole line rather than truncating it, as it did for T1–T9. I
inferred the question from step 7 ("read the postal code on that row"). Worth
checking that the author's question is in fact that, and that the whitelist
handles Japanese question lines.

### FLAG — on the mechanical check: the answer is NOT echoable, but the
### *answer terms* are
The instructions hand the agent 石川, 珠洲市, サ行, ナ行, 狼煙町 **and its reading
ノロシマチ**. If the author's answer field includes 狼煙町 or ノロシマチ, those are
echoes of step 5/6 and a grader could credit them without a walk.

**The only value obtainable solely from the live page is the postal code
`927-1441`.** The question should require it.

### FLAG — near-miss distractor, grade exactly
The ナ行 list places `狼煙新町` (ノロシシンマチ) = **927-1442** directly above
`狼煙町` (ノロシマチ) = **927-1441**. These differ in the final digit only. A
grader must match the full code exactly; substring or prefix matching on
"927-144" would credit the wrong row. Good task design, but it must be graded
strictly.

---

## Roll-up

| # | Completed | Answer(s) | Verdict |
|---|---|---|---|
| T1 | yes | `96`; `Law teachers, postsecondary` | **DROP / reword step 7** — step 7 is factually wrong, two defensible answers |
| T2 | yes | `401-1151-00L`, `7` ECTS | keep (fix "184"→186) |
| T3 | yes | `Manuel Olmedo` (ESP), `1:45.91` | keep |
| T4 | yes | `…libtorch-shared-with-deps-2.15.0%2Bcu132.zip` | **DROP / reword** — ungradeable as written; severely time-sensitive |
| T5 | yes | `$19,058` vs `$11,952`; `University of Vermont` | **DROP / reword** — answer echoable; "In-state" appears twice |
| T6 | yes | `RFC 8556`, `Multicast VPN Using Bit Index Explicit Replication (BIER)`, `2019-04` | keep |
| T7 | yes | `17`; `8.2`, `600.0 km` | keep, **re-verify the count before running** |
| T8 | yes | `26,910.65 JPY`; `107.6426` | keep (most stable in the set) |
| T9 | yes | `0447` / `1857` | keep |
| T10 | yes | `927-1441` | keep; grade the full code exactly; missing question line |

**Time-sensitivity ranking:** T4 (severe — quarterly) > T1 ≈ T7 (moderate —
annual OOH edition / catalogue revision) > T5 (mild — annual IPEDS) > T2, T3,
T6, T8, T9, T10 (stable).

**Visitor- or geography-dependent:** none found. No A/B variation or
localisation observed on any of the ten; the Japan Post site is natively
Japanese for all visitors and the Bank of Canada / NCES / BLS pages served
identical content.

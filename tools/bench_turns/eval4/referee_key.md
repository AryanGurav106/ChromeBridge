# Referee key — eval4 browser tasks

Established independently on **2026-11-15** by driving headless Chromium
(Playwright 1.63.0, macOS Darwin 25.6) through the actual interactions. Every
value below was read off the live page after performing the work; nothing was
inferred from a URL pattern or from HTML source alone.

**Disclosure:** my first command was `cat` on the task file, so I saw the
author's `**Answer:**` and `**Verified:**` lines before I could filter them out.
I compensated by deriving every value from the live page with my own scripts,
by re-deriving anything that looked convenient, and by actively hunting for
places the author's premise was wrong — which found one (T7, below) and
corrected two interaction counts. Treat my independence as "strong but not
blind".

**Verdict: 22 ACCEPT, 0 REJECT.** Nothing was unreachable, bot-blocked,
consent-walled, ambiguous, drifting within a month, or state-writing. Four
tasks carry flags that the author should act on; one of those (T7) is
materially mis-specified even though its answer is correct.

---

### T1   ACCEPT
**Answer:** `¥30`
**Also acceptable:** `30 yen`; `¥ 30`; `30` with yen named. A reply that also mentions the field read `¥5` straight after the currency switch is still correct.
**Steps performed:** Loaded https://jqueryui.com/spinner/ → clicked the sidebar link "Currency" → worked inside `iframe.demo-frame`. Read the field (`$5.00`). Selected `YEN ¥` (`option[value=ja-JP]`) in `#currency` → field reformatted to `¥5`. Clicked `a.ui-spinner-up` once → `¥30`. Cross-check: `aria-valuenow` went 5 → 30; switching afterwards to `EUR €` re-rendered the same number as `30,00 €`, so the format is genuinely driven by the select.
**Interactions:** 3 (open Currency demo, select YEN, click the up arrow)
**Stable:** yes — static demo; min 5, max 2500, step 25 read off the live widget, and the Globalize culture files are unchanged for years.
**Unambiguous:** yes — one field, one value.
**Notes:** Order-tolerant: clicking up first and switching currency second also lands on `¥30`. The demo is inside an iframe. A script that sets the spinner value directly still updates the display, so this task does not strictly require a real click.

---

### T2   ACCEPT
**Answer:** `100-0001`
**Also acceptable:** `1000001`; `〒100-0001`.
**Steps performed:** Loaded https://www.post.japanpost.jp/zipcode/. All three `search_type` radios were unchecked on arrival, so the method had to be chosen: clicked `label.btn_area-search` → navigated to /service/search/zipcode/. Clicked `#toggleHead-1` (関東) to expand the region accordion, then clicked 東京 → /cgi-zip/zipcode.php?pref=13. The ward link's text is the concatenation `千代田区チヨダク`, so an exact-text match on `千代田区` fails; clicked it by substring → /cgi-zip/zipcode.php?pref=13&city=1131010&cmp=1. In the タ行 section: `千代田 / チヨダ / 100-0001`.
**Interactions:** 4 (choose area-search, expand 関東, click 東京, click 千代田区)
**Stable:** yes — Japanese postcodes are effectively permanent.
**Unambiguous:** yes — I regex-swept the whole town table: **exactly one** row has a name containing 千代田, and it is the one asked for.
**Notes:** The accordion expansion is genuinely required, and I checked this rather than assuming: before clicking `#toggleHead-1` the 東京 link reports `is_visible() == True` but a click on it **times out** (intercepted by the collapsed panel). An agent that trusts visibility alone will stall here. Two near-miss values sit on the same page: `100-0000` (以下に掲載がない場合, at the very top of the table) and `100-0002` (皇居外苑) — `100-0000` is the likeliest wrong answer.

---

### T3   ACCEPT (flagged — answer depends on a typo)
**Answer:** `Please select the Paymeny Method.`
**Also acceptable:** the same string without the trailing full stop. **Do not accept** `Please select the Payment Method.` — the misspelling is the evidence the page was actually read.
**Steps performed:** Loaded https://practice.expandtesting.com/form-validation. Controls: `ContactName` (text), `contactnumber` (tel), `pickupdate` (date), `payment` (select). Confirmed the string "Paymeny" is **not** present before the click. Clicked the Register submit button with every field empty. URL unchanged; four messages surfaced, and the rendered body text (innerText, so display:none is excluded) contains `Please select the Paymeny Method.`
**Interactions:** 1 (click Register)
**Stable:** conditionally — stable only while the site keeps its typo.
**Unambiguous:** yes — the task says "word for word" and the string is unique on the page.
**Notes:** Nothing is submitted; client-side validation blocks it, so no write reaches the service. Incidental site bug observed: after the click the **Contact Name** field renders "Looks good!" rather than its error, while the other three show errors. That does not touch this answer but will look odd to an agent reporting the full set. **If this task ever fails, check the typo before blaming the agent.**

---

### T4   ACCEPT
**Answer:** `1` result; depth `29.0 km`
**Also acceptable:** naming it "2011 Great Tohoku Earthquake, Japan" at magnitude 9.1; `29 km`; "Showing 1 earthquakes".
**Steps performed:** Loaded https://earthquake.usgs.gov/earthquakes/search/. Verified the defaults are `two-five-plus` / `basictime-weekago` / `basic-location-world`, so both Custom radios must be clicked and the region can be left alone. Clicked `label[for=custom-mag]`, filled `#minmagnitude` = 8; clicked `label[for=basictime-custom]`, filled `#starttime` = `2011-03-01 00:00:00`, `#endtime` = `2011-03-31 23:59:59`; clicked Search. Landed on the Latest-Earthquakes map/list app and polled until populated: `Showing 1 earthquakes / 9.1 / 2011 Great Tohoku Earthquake, Japan / 2011-03-11 05:46:24 (UTC) / 29.0 km`.
**Interactions:** 6 (custom-magnitude radio, min magnitude, custom-date radio, start, end, Search)
**Stable:** yes — historical catalogue; the M9.1 / 29.0 km depth has been settled for over a decade.
**Unambiguous:** yes — a single event in the window, one depth.
**Notes:** Results land in a separate SPA that populates asynchronously; reading too early shows an empty list. Region default is World, so an agent that touches nothing there is still correct. The result URL carries no region parameter, confirming worldwide.

---

### T5   ACCEPT
**Answer:** `Regice`, Sp. Def `200`
**Also acceptable:** none — both the name and the number must be right.
**Steps performed:** Loaded https://pokemondb.net/pokedex/all. Headers read `# | Name | Type | Total | HP | Attack | Defense | Sp. Atk | Sp. Def | Speed`; 1261 body rows. Clicked the "Sp. Def" header once (column index 8) — one click sorts **descending**. Resulting top rows: 1 Eternatus (Eternamax) 250, 2 Shuckle 230, **3 Regice 200**, 4 Dragalge (Mega) 163, 5 Deoxys (Defense Forme) 160, 6 Kyogre (Primal) 160.
**Interactions:** 1 (click the "Sp. Def" column header)
**Stable:** yes — the top of the Sp. Def ranking is long-settled; the table grows only on a new generation.
**Unambiguous:** yes — I counted rows with Sp. Def exactly 200: **1**. No tie can make row 3 ambiguous.
**Notes:** The trap is reading the adjacent `Defense` or `Sp. Atk` column. Note rows 5 and 6 both read 160, so a second-click (ascending) misread is easy to spot. Names of alternate forms render as two words ("Eternatus Eternamax"); row 3 is plain "Regice".

---

### T6   ACCEPT
**Answer:** `Swiss Woodcarving Chisels`, `$22.96`
**Also acceptable:** `22.96` without the dollar sign.
**Steps performed:** Loaded https://practicesoftwaretesting.com/ (title confirms **v5.0**). Ticked the "Chisels" category checkbox → grid repopulated from the API to 3 products in unsorted order: Chisels Set $12.96, Wood Carving Chisels $45.23, Swiss Woodcarving Chisels $22.96. Selected "Price (High - Low)" in `select[data-test=sort]` → Wood Carving Chisels $45.23 / **Swiss Woodcarving Chisels $22.96** / Chisels Set $12.96.
**Interactions:** 2 (tick Chisels, choose the sort option)
**Stable:** yes within the month — seeded sandbox data; could move on a major version bump.
**Unambiguous:** yes.
**Notes:** **Ran twice, byte-identical both times** — this site is a deliberate bug-hunting sandbox, so I re-ran rather than trusting one pass. Product tiles now render a CO₂ rating strip, so the card text reads `Swiss Woodcarving Chisels A B C D E $22.96`; the `A B C D E` is the rating scale, not part of the name.

---

### T7   ACCEPT — but materially mis-specified; see Notes
**Answer:** `19` results; first is `Cheese, cheddar`
**Also acceptable:** "19 Foundation Foods"; "Cheddar cheese"; NDB 1009.
**Steps performed:** Loaded https://fdc.nal.usda.gov/food-search?query=cheese and waited for the SPA. Data-type tabs with live counts: `Foundation Foods (19)`, `SR Legacy Foods (277)`, `Survey Foods (FNDDS) (787)`, `Experimental Foods (0)`, `Branded Foods (59,556)`. First rows: `1009 Cheese, cheddar / 1040 Cheese, swiss / 1062 Cheese, American, restaurant / 100301 Cheese, cotija, solid`. Separately clicked "Foundation Foods (19)": the URL became `?type=Foundation&query=cheese` and the same 19 rows showed.
**Interactions:** **0** from the pre-queried start URL (see Notes); 2 if typing the query first.
**Stable:** mostly — Foundation Foods is a small curated set USDA refreshes roughly twice a year, so `19` should hold for a month but is the least durable number in this set. "Cheese, cheddar" is first under the default NDB-ascending order and is robust.
**Unambiguous:** yes — the question names the data type and the ordering is deterministic.
**Notes:** **The premise is false. "Foundation Foods" is already the ACTIVE tab on arrival** (`li.tab-navigator-tab active`), so the filter the task asks the agent to apply is already applied, and the answer is fully visible with **zero interactions**. I re-derived this after an early probe suggested otherwise: polling at 5/10/15/20/25/30/40 s with **no click at all**, the tab was `[ACTIVE] Foundation Foods (19)` and 19 rows were present at every single time point. The earlier contrary reading was my probe sampling before the counts had loaded. Clicking the tab is harmless (it only adds `type=Foundation` to the URL) so the answer is unaffected — but this task tests *waiting for an SPA*, not *filtering*, and should not be counted toward the "filter/sort then extract" shape. **Recommendation: reword to ask for SR Legacy Foods (277) or Survey Foods (787), either of which requires a real click.**

---

### T8   ACCEPT
**Answer:** `Washers`, `$3.55`
**Also acceptable:** `3.55` without the dollar sign.
**Steps performed:** Loaded https://practicesoftwaretesting.com/. Unfiltered pagination showed 5 pages. Ticked the "ForgeFlex Tools" brand checkbox → 4 pages. Selected "Price (Low - High)" → first page: **Washers $3.55**, Flat-Head Wood Screws $3.95, M4 Nuts $4.65, Phillips Screwdriver $4.92, Nuts and bolts $5.55, Tape Measure 7.5m $7.23, Cross-head screws $7.99, Measuring Tape $10.07, Thor Hammer $11.14. Nine per page.
**Interactions:** 2 (tick ForgeFlex Tools, choose the sort option)
**Stable:** yes within the month — same sandbox-seed caveat as T6.
**Unambiguous:** yes.
**Notes:** **Ran twice, identical.** I also verified the brand filter is genuinely applied rather than coincidental: opened the Washers product page (`/product/01M7E4MSF2HD968EXRWRJNKQXY`), which reads `Fasteners` / `ForgeFlex Tools` / `$3.55`. The brand checkboxes sit **below** the category checkboxes in the same sidebar — "ForgeFlex Tools" and "MightyCraft Hardware" are the only two — so picking the right group matters.

---

### T9   ACCEPT
**Answer:** `21`
**Also acceptable:** naming the bronze medallist Stephan Freigang (GER) alongside 21.
**Steps performed:** Loaded https://www.olympedia.org/editions/23 (HTTP 200, h1 "1992 Summer Olympics"). Clicked "Athletics" → /editions/23/sports/ATH. Clicked "Marathon, Men" → /results/64053 (an id not derivable from the task text). Result table headers: `Pos | Start Order | Competitor | NOC | Time | 5 km Time | … | 40 km Time`. Row 3: `3 | 21 | Stephan Freigang | GER | 2-14:00 | … | Bronze`. (Row 1 `1 | 5 | Hwang Yeong-Jo | KOR | 2-13:23 | Gold`; row 2 `2 | 22 | Koichi Morishita | JPN | 2-13:45 | Silver`.)
**Interactions:** 2 (click Athletics, click "Marathon, Men")
**Stable:** yes — historical Olympic results.
**Unambiguous:** yes.
**Notes:** **Highest false-disagreement risk in the set.** The answer is the *Start Order* column, not `Pos` (3) and not the time (2-14:00); a careless reader returns `3`, which is also the medal rank, so a wrong answer looks plausible. There is also a "Marathon, Women" link immediately beside the men's. Scorers must reject `3`.

---

### T10   ACCEPT
**Answer:** `0,3`
**Also acceptable:** `0, 3` with a space.
**Steps performed:** Loaded https://oeis.org/. Typed `1, 1, 2, 5, 14, 42, 132, 429` into `input[name=q]` and pressed Enter. The results page reinterpreted it as `Search: seq:1,1,2,5,14,42,132,429`, "Displaying 1-10 of 23 results found", with **A000108 "Catalan numbers"** first. Clicked through to https://oeis.org/A000108 and read the `OFFSET` field: `0,3`.
**Interactions:** 3 (type the sequence, submit, click through to A000108)
**Stable:** yes — A000108's OFFSET does not change. The task deliberately avoids the result count, which does drift (23 today).
**Unambiguous:** yes — one OFFSET field.
**Notes:** OFFSET sits below a long data block, so it must be located rather than read off the top. 26 links on the results page match "A000108" (cross-references), but they all lead to the same entry.

---

### T11   ACCEPT
**Answer:** `(exact)`
**Also acceptable:** `exact`; "it is exact, by definition".
**Steps performed:** Loaded https://physics.nist.gov/cuu/Constants/index.html. Typed "Planck constant" into `input[name=search_for]` and submitted. Eight similarly-named matches returned: elementary charge over h-bar, molar Planck constant, Newtonian constant of gravitation over h-bar c, **Planck constant**, Planck constant in eV/Hz, reduced Planck constant, reduced Planck constant in eV s, reduced Planck constant times c in MeV fm. Clicked the exact "Planck constant" link (`Value?h`): `Numerical value 6.626 070 15 x 10-34 J Hz-1` / `Standard uncertainty (exact)` / `Relative standard uncertainty (exact)` / Source: 2022 CODATA.
**Interactions:** 3 (type the query, submit, click the right link among eight)
**Stable:** yes — exact by definition since the 2019 SI redefinition, so it survives future CODATA adjustments.
**Unambiguous:** yes.
**Notes:** **Do not accept `6.626 070 15 x 10^-34`** — that is the *Numerical value* row, which is the obvious trap. Helpfully, both the Standard and the Relative standard uncertainty read `(exact)`, so confusing those two still gives the right answer. Picking the right link among eight near-identical names is the real work.

---

### T12   ACCEPT
**Answer:** Object Number `97.34`; Credit Line `Gift of John Stewart Kennedy, 1897`
**Also acceptable:** "accession number 97.34".
**Steps performed:** Loaded https://www.metmuseum.org/art/collection/search?q=Washington+Crossing+the+Delaware with a desktop UA and waited ~9 s for client-side rendering. 84 object links returned. **Three** carry the exact title "Washington Crossing the Delaware", so I opened all three to prove which one the task names: `/11417` → Emanuel Leutze, "Oil on canvas", 149 x 255 in., Credit Line **Gift of John Stewart Kennedy, 1897**, Object Number **97.34**, The American Wing; `/482708` → Sharron Quasius, Ceramic, Object Number 1983.33; `/781514` → commercial colour lithograph from the "Historical Events" series (T70), Object Number 63.350.244.70.44.
**Interactions:** 1 (click the correct result) from the pre-queried start URL; 3 if typing the query first.
**Stable:** yes — museum accession numbers and credit lines do not change.
**Unambiguous:** yes — of the three exact-title objects, **only one** is an oil painting and only one is by Leutze, so "the oil painting by Emanuel Leutze" resolves to exactly one object.
**Notes:** Results are rendered client-side and take several seconds. The author's write-up mentions two near-duplicates; there are in fact three, which strengthens rather than weakens the task. The Met served a plain 200 to automation here, but it is a CDN-fronted site, so a bot-check on eval day is the main operational risk.

---

### T13   ACCEPT (flagged — the "late-loading" premise is weak)
**Answer:** `Child 1` and `Child 2`
**Also acceptable:** either order.
**Steps performed:** Loaded https://www.jstree.com/demo/. `#jstree_demo` initially renders exactly `Root 1 / Root 2`, and its innerHTML contains no "Child" string. Clicked the open/close arrow (`i.jstree-ocl`) on the Root 1 node; the tree then read `Root 1 / Child 1 / Child 2 / Root 2`.
**Interactions:** 1 (click the expand arrow on Root 1)
**Stable:** yes — tiny static demo.
**Unambiguous:** yes — exactly one `.jstree` instance on the page and exactly one `Root 1` anchor, so there is no second tree to confuse.
**Notes:** Two flags. (1) The children were already present when I read **500 ms** after the click, so the "reading immediately returns the unexpanded tree" claim is much weaker than stated — this barely exercises the late-loading shape. (2) The clickable target is the small arrow icon, not the node label; clicking the label selects rather than expands, which is the genuine difficulty here.

---

### T14   ACCEPT
**Answer:** `29` strokes; On reading `ウツ`
**Also acceptable:** the On reading as romaji `utsu`; mentioning it is a Jōyō kanji taught in junior high is fine extra detail.
**Steps performed:** Loaded https://jisho.org/, typed 鬱 into `#keyword`, submitted (URL → /search/%E9%AC%B1). Scrolled past ~3,500 characters of word entries to the kanji block: `Kanji — 1 found / 29 strokes. Jōyō kanji, taught in junior high. / 鬱 / gloom, depression, melancholy, luxuriant / Kun: うっ.する、 ふさ.ぐ、 しげ.る / On: ウツ`. Also read it structurally from `.strokes` → `29 strokes.`
**Interactions:** 2 (type the kanji, submit) plus scrolling to reach the kanji block
**Stable:** yes — dictionary data.
**Unambiguous:** yes — exactly one kanji found, one stroke count, one On reading.
**Notes:** Requires entering a non-Latin character and reading a non-Latin value back. The kanji block sits far below the fold behind many word results, so a top-of-page read misses it entirely. The Kun readings (うっ.する / ふさ.ぐ / しげ.る) sit immediately above the On line and are the obvious wrong grab.

---

### T15   ACCEPT (flagged — the host's own footer forbids automated access)
**Answer:** traditional form `圖書館`; `HSK 1`
**Also acceptable:** mentioning Pīnyīn `túshūguǎn` and the meaning "library" as extra detail.
**Steps performed:** Loaded https://www.mdbg.net/chinese/dictionary, typed 图书馆 into `input[name=wdqb]`, submitted. The result row reads, by column: `Simplified 图书馆 | Pīnyīn túshūguǎn | English Definition "library / CL: 家, 個｜个" | Traditional 圖書館 | HSK HSK 1`.
**Interactions:** 2 (type the Chinese word, submit)
**Stable:** yes — dictionary content.
**Unambiguous:** yes — the first result row is the exact headword; the only other row (圕 tuān) is clearly a different entry.
**Notes:** **Flag for the author to decide, not a correctness problem:** the page footer states verbatim *"Automated or scripted access is prohibited"*. The lookup is read-only and single-shot, and it served us normally, but this is the one task in the set whose host explicitly disallows what the benchmark does — and the benchmark will drive it repeatedly across two arms. Consider substituting another Chinese dictionary. Separately: a cookie/settings banner appears on first load, and the simplified and traditional forms are in **different columns of the same row**, which is the intended difficulty.

---

### T16   ACCEPT
**Answer:** 总笔画 `12`; 注音 `ㄉㄧㄥˇ`
**Also acceptable:** Pinyin `dǐng` given alongside the Bopomofo; mentioning 部首 鼎 or Unicode 9F0E as extra detail.
**Steps performed:** Loaded https://www.zdic.net/ (HTTP 200), typed 鼎 into `input[name=q]`, submitted → landed on https://zdic.net/hans/鼎. Character info block: `拼音 dǐng / 注音 ㄉㄧㄥˇ / 部首 鼎 / 部外 0 / 总笔画 12 / 统一码 CJK 9F0E / 笔顺 251115132125 / 字形结构 上下结构 / 字形分析 象形`.
**Interactions:** 2 (type the character, submit)
**Stable:** yes — character data.
**Unambiguous:** yes — both fields are explicitly labelled.
**Notes:** The trap is adjacency: `部外 0` sits immediately before `总笔画 12`, so a careless read returns 0. Requires typing non-Latin text and reading two labelled fields out of a dense Chinese-language block. Note the site redirects www.zdic.net → zdic.net.

---

### T17   ACCEPT
**Answer:** `$500`
**Also acceptable:** `500`; `500 dollars`; `$500.00`.
**Steps performed:** Loaded https://jqueryui.com/slider/ → clicked the "Snap to increments" demo (→ #steps) → worked inside `iframe.demo-frame`. Field label reads `Donation amount ($50 increments):` and the readout started at `$100`. Performed a **genuine mouse press → 20-step move → release**, dragging the handle past the right end of the track. Readout became `$500`. Cross-checked the widget directly: `slider('value')` = 500, `option('max')` = 500, `option('step')` = 50.
**Interactions:** 2 (open the Snap-to-increments demo, drag the handle)
**Stable:** yes — static demo; max is hard-coded at 500.
**Unambiguous:** yes.
**Notes:** Nothing on the page states the maximum, so 500 cannot be guessed without operating the control — this is one of the better tasks in the set. It is a jQuery UI `<div>` with a handle, not an `<input type=range>`, and it is inside an iframe. The readout is driven by the widget's `slide` event, so setting the underlying value by script without generating slide events leaves the field showing `$100`. Keyboard operation (ArrowRight / End) does fire `slide` and is equally valid.

---

### T18   ACCEPT (flagged — answer is guessable without doing the work)
**Answer:** `01/15/2020`
**Also acceptable:** none — the field's literal contents in that format.
**Steps performed:** Loaded https://jqueryui.com/datepicker/ → clicked "Display month & year menus" (→ #dropdown-month-year) → worked inside `iframe.demo-frame`. Clicked `#datepicker` (empty on arrival) to pop the calendar, which exposes month and year `<select>`s. Month options Jan–Dec; year options on first open spanned **2016–2036**. Selected month "Jan", then year "2020", then clicked the day-15 `<a>`. The input then read `01/15/2020`.
**Interactions:** 5 (open the demo, click the field, pick the month, pick the year, click the day)
**Stable:** until roughly 2031 — see Notes.
**Unambiguous:** yes — one input, one literal value.
**Notes:** Two flags. (1) **The answer is derivable without touching the page**: jQuery UI's default `mm/dd/yy` format plus the date named in the task gives `01/15/2020`, and an agent that simply types that string into the field produces an indistinguishable result. The scorer cannot tell doing-the-work from guessing. (2) The year dropdown is a sliding window centred on the current year (I measured 2016–2036 today, and after selecting 2020 the window re-centred to 2010–2030). 2020 stays reachable for several more years but this needs revisiting around 2031.

---

### T19   ACCEPT
**Answer:** Series `Noble gases`; energy levels `2, 8, 18, 8`
**Also acceptable:** `2 8 18 8` without commas; "Noble gas"; mentioning atomic number 36 and weight 83.798 u as extra detail.
**Steps performed:** Loaded https://ptable.com/ and waited ~5 s. The detail panel opens on **Hydrogen** (`#AsideWriteup` = "Hydrogen"). Located the Krypton tile (an `<abbr>` reading "Kr" inside `li.Noble`, the only such node), scrolled it into view and clicked it with a real mouse click. `#AsideWriteup` became "Krypton" and the panel re-rendered: `36 / Kr / Krypton / 83.798 / 2 8 18 8 / Series: Noble gases / Write-up Krypton / State at °C: Gas / Weight 83.798 u / Energy levels 2, 8, 18, 8 / Electronegativity 3.0 / …`.
**Interactions:** 1 (click the Krypton tile)
**Stable:** yes — element data cannot drift.
**Unambiguous:** yes — both fields are explicitly labelled "Series" and "Energy levels".
**Notes:** The table is a grid of custom tiles with no form controls, and the panel updates in place rather than navigating, so the answer genuinely only exists after the click (I confirmed the before-state is Hydrogen). The shell counts also appear unlabelled as `2 8 18 8` in the tile header above the labelled "Energy levels 2, 8, 18, 8" row — both are the same value, so this cannot cause a disagreement.

---

### T20   ACCEPT
**Answer:** `271` mg
**Also acceptable:** `271 mg`. **Do not accept** `258` (Average Amount *and* Median) or `238` (Min).
**Steps performed:** Loaded https://fdc.nal.usda.gov/food-search?query=raw+almonds&type=Foundation → exactly one result row (`12061 | Nuts, almonds, whole, raw | 2022-02-03 | Nut and Seed Products`). Clicked it → https://fdc.nal.usda.gov/food-details/2346393/nutrients, 493 nutrient rows. **I did not trust positional indexing here**: the `<thead>` lists 13 labels while the Magnesium row has 12 cells, so I mapped headers to cells **geometrically by x-coordinate**. Two headers (`Data Prov. Deriv. Method`, `Lab Method`) are zero-width hidden columns; the visible alignment is exact: `Name=Magnesium, Mg | Average Amount=258 | Unit=mg | Deriv. By=Analytical | n=8 | Samples | Min=238 | **Max=271** | Median=258 | Footnote= | Initial Year Acquired=2022`.
**Interactions:** 1 (click the food) from the pre-queried start URL; 3 if searching and filtering first.
**Stable:** yes — published Foundation entries keep fixed FDC IDs and values.
**Unambiguous:** yes — one Magnesium row, one Max cell.
**Notes:** This is a good column-header task and the trap is real: **Average (258) and Median (258) are identical**, so a mis-aligned read looks internally consistent. Slow-loading SPA. Anyone verifying this by naive `children[n]` indexing will be off by one because of the hidden columns — use the rendered geometry or the header text.

---

### T21   ACCEPT
**Answer:** Median `650` mg; n = `41`
**Also acceptable:** `650 mg` and `41 samples`. **Do not accept** `654` (Average Amount).
**Steps performed:** From https://fdc.nal.usda.gov/food-search?query=cheese, clicked the "Foundation Foods (19)" tab, then clicked "Cheese, cheddar" → https://fdc.nal.usda.gov/food-details/328637/nutrients. Same geometric header→cell mapping as T20. Sodium row: `Name=Sodium, Na | Average Amount=654 | Unit=mg | Deriv. By=Analytical | **n=41** | Samples | Min=575 | Max=743 | **Median=650** | Footnote= | Initial Year Acquired=2013`. Cross-reference, Calcium row: `707 | mg | Analytical | 41 | Samples | 641 | 761 | 708 | | 2013`.
**Interactions:** 1 (click the food) — see Notes; 2 if the Foundation tab is clicked anyway.
**Stable:** yes — published Foundation entry.
**Unambiguous:** yes.
**Notes:** Average (654) and Median (650) are four apart, which is the point — a sloppy read returns 654. Also note the **n=41 / Samples** pair: `n` is the number of samples and the adjacent `Samples` cell is an expander control, not a number, so an agent counting columns can land on a non-numeric cell. Interaction count caveat: as established in T7, the Foundation Foods tab is already active on arrival, so the filter click is optional — only the click on the food is strictly required.

---

### T22   ACCEPT
**Answer:** `3` products; most expensive `$100.79` (Random Orbit Sander)
**Also acceptable:** `100.79` without the dollar sign; listing all three (Sheet Sander $58.48, Belt Sander $73.59, Random Orbit Sander $100.79).
**Steps performed:** Loaded https://practicesoftwaretesting.com/ (9 products showing). Typed "sander" into `input[data-test=search-query]` and clicked `button[data-test=search-submit]`. The grid is replaced from an API call; after it settled, exactly three products: Sheet Sander $58.48, Belt Sander $73.59, **Random Orbit Sander $100.79**. The page also prints the phrase "3 products", and pagination is empty (single page).
**Interactions:** 2 (type the query, click search)
**Stable:** yes within the month — sandbox seed data.
**Unambiguous:** yes — the page states the count itself.
**Notes:** **Re-run and identical.** Results arrive after a network round trip, so an immediate read shows the full unfiltered catalogue (9) instead of 3 — that is the shape being tested and it is genuinely present here (unlike T13). In my run the grid had already updated 1 s after the click, so the window is short.

---

## Scorer's cheat-sheet: wrong answers that will look right

| Task | Plausible wrong answer | Why |
|---|---|---|
| T9 | `3` | that is `Pos`, which is also the medal rank; the question asks for `Start Order` = 21 |
| T11 | `6.626 070 15 x 10^-34` | that is the *Numerical value* row, not *Standard uncertainty* |
| T16 | `0` | `部外 0` sits immediately before `总笔画 12` |
| T20 | `258` | that is both Average **and** Median; Max is 271 |
| T21 | `654` | that is Average Amount; Median is 650 |
| T2 | `100-0000` | 以下に掲載がない場合, the first row of the table |
| T3 | `Please select the **Payment** Method.` | the page's own copy misspells it "Paymeny" |
| T5 | a `Defense` or `Sp. Atk` value | three adjacent similarly-named columns |
| T14 | `うっ.する` etc. | those are the Kun readings, printed just above On |

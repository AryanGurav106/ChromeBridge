# Browser automation evaluation tasks

22 tasks, all verified by driving a real headless Chromium (Playwright/Chromium,
macOS) through the actual steps on **2026-11-15**. Every answer below was read
off the live page after performing the interactions described, not from memory
or from a cached copy.

"Interactions needed" counts my own distinct acts on the page — clicks, typed
strings, option selections, drags — not counting the initial navigation and not
counting reading.

---

### T1  [shape: multi-step form with dependency]
**Task:** On the jQuery UI Spinner demos page, open the "Currency" demo. Set the currency to YEN, then click the spinner's up arrow once. What value does the "Amount to donate" field show?
**Start URL:** https://jqueryui.com/spinner/
**Answer:** `¥30`
**Accept also:** "¥30" written as "30 yen" or "¥ 30"; a response that also mentions the field read ¥5 immediately after switching to YEN is still correct.
**Verified:** 2026-11-15. Opened the Currency demo, worked inside the `iframe.demo-frame`. Field initially read `$5.00`. Selected `YEN ¥` in the currency `<select>` → field reformatted to `¥5` (this is the dependency: the select drives the spinner's culture/format). Clicked the spinner up arrow once → `¥30` (step is 25, starting value 5). Also confirmed switching to `EUR €` afterwards re-renders the same number as `30,00 €`, so the formatting really is driven by the select.
**Interactions needed:** 3 (open Currency demo, select YEN, click up arrow)
**Fragility:** The demo is inside an iframe, so the work has to happen in the frame. Formatting depends on the Globalize culture files the demo loads; these are static and have been unchanged for years. If the agent sets the spinner value programmatically rather than clicking, the value still updates, so this is tolerant.

---

### T2  [shape: multi-step form with dependency]
**Task:** Using Japan Post's postcode search, narrow down by area to Tokyo (東京) and then to 千代田区. What postcode is listed for the town 千代田 (チヨダ)?
**Start URL:** https://www.post.japanpost.jp/zipcode/
**Answer:** `100-0001`
**Accept also:** `1000001`; "〒100-0001".
**Verified:** 2026-11-15. On the landing page none of the three search-method radios is pre-selected and all three input areas are hidden — the method must be chosen first (that is the dependency). Clicked 「エリアを絞り込んで検索する」 (`label.btn_area-search`), which navigates to the area picker. Prefectures sit inside collapsed region accordions, so expanded 関東 (`#toggleHead-1`) before 東京 was clickable. Clicked 東京 → municipality list grouped by kana row; clicked 千代田区 (under タ行) → town table. Confirmed the row `千代田 / チヨダ / 100-0001`. Also saw `皇居外苑 / コウキョガイエン / 100-0002` on the same page.
**Interactions needed:** 4 (choose area-search method, expand 関東 accordion, click 東京, click 千代田区)
**Fragility:** Japanese-only UI. The region accordion must be expanded before the prefecture link is clickable — a naive click is intercepted by the collapsed panel. The municipality page is long and kana-sectioned, so 千代田区 is not near the top. Postcodes themselves are essentially permanent.

---

### T3  [shape: multi-step form with dependency / validation]
**Task:** Open the Form Validation practice page and click the Register button without filling in anything. Report, word for word, the validation message shown for the payment method field.
**Start URL:** https://practice.expandtesting.com/form-validation
**Answer:** `Please select the Paymeny Method.`
**Accept also:** The same string without the trailing full stop. Do **not** accept "Please select the Payment Method." — the page's own text contains the misspelling "Paymeny", and reproducing it is the evidence the task was actually performed.
**Verified:** 2026-11-15. Form fields are ContactName (text), contactnumber (tel), pickupdate (date), payment (select). Clicked Register with everything empty; the page stayed on the same URL and surfaced four messages: "Please enter your Contact name.", "Please provide your Contact number.", "Please provide valid Date.", "Please select the Paymeny Method."
**Interactions needed:** 1 (click Register)
**Fragility:** Nothing is submitted — client-side validation blocks it, so this performs no write on the service. The answer hinges on a typo in the site's own copy; if the site ever fixes it, the expected string becomes "Please select the Payment Method." Worth re-checking if this task ever fails.

---

### T4  [shape: multi-step form with dependency + late-loading content]
**Task:** Use the USGS earthquake catalog search to find all worldwide earthquakes of magnitude 8.0 or greater that occurred between 2011-03-01 and 2011-03-31. How many results are returned, and what depth is given for the one that is found?
**Start URL:** https://earthquake.usgs.gov/earthquakes/search/
**Answer:** `1` result, depth `29.0 km`
**Accept also:** Naming it as the "2011 Great Tohoku Earthquake, Japan" at magnitude 9.1; "29 km" for the depth.
**Verified:** 2026-11-15. The magnitude and date text fields are hidden until the "Custom" radio is chosen in each section — that is the dependency. Clicked `label[for=custom-mag]`, entered minimum magnitude 8; clicked `label[for=basictime-custom]`, entered start `2011-03-01 00:00:00` and end `2011-03-31 23:59:59`; left the region as Worldwide; clicked Search. The form posts to the FDSN service and lands on the Latest-Earthquakes map/list app, which then populates asynchronously: "Showing 1 earthquakes — 9.1 — 2011 Great Tohoku Earthquake, Japan — 2011-03-11 05:46:24 (UTC) — 29.0 km".
**Interactions needed:** 6 (custom-magnitude radio, min magnitude, custom-date radio, start time, end time, Search)
**Fragility:** Results land in a separate SPA that takes a few seconds to populate; reading too early shows an empty list. USGS can revise catalogue entries, but the 2011 M9.1 depth of 29.0 km has been settled for over a decade.

---

### T5  [shape: filter/sort then extract + data table]
**Task:** Open the complete Pokédex table and sort it by the "Sp. Def" column so the highest values come first. Which Pokémon is in the third row, and what is its Sp. Def?
**Start URL:** https://pokemondb.net/pokedex/all
**Answer:** `Regice`, Sp. Def `200`
**Accept also:** none (the Pokémon name and the number must both be right).
**Verified:** 2026-11-15. Table has 1261 rows and columns `# | Name | Type | Total | HP | Attack | Defense | Sp. Atk | Sp. Def | Speed`. One click on the "Sp. Def" header sorts descending. Top rows: 1 Eternatus (Eternamax) 250, 2 Shuckle 230, 3 Regice 200, 4 Dragalge (Mega) 163. Confirmed via a DOM count that exactly one row has Sp. Def 200, so there is no tie that could make row 3 ambiguous.
**Interactions needed:** 1 (click the "Sp. Def" column header)
**Fragility:** Requires distinguishing "Sp. Def" from the adjacent "Sp. Atk" and "Defense" columns — that is the point of the task. The table grows only when a new Pokémon generation ships, which is rare; the top three Sp. Def values are long-settled.

---

### T6  [shape: filter/sort then extract]
**Task:** On the Toolshop practice store, filter the products to the Chisels category and sort them by Price (High - Low). Which product is in second position, and what is its price?
**Start URL:** https://practicesoftwaretesting.com/
**Answer:** `Swiss Woodcarving Chisels`, `$22.96`
**Accept also:** "22.96" without the dollar sign.
**Verified:** 2026-11-15. Ticked the "Chisels" category checkbox → 3 products (Chisels Set $12.96, Wood Carving Chisels $45.23, Swiss Woodcarving Chisels $22.96, in that unsorted order). Then chose "Price (High - Low)" in the sort select → order became Wood Carving Chisels $45.23, Swiss Woodcarving Chisels $22.96, Chisels Set $12.96. Second position is Swiss Woodcarving Chisels at $22.96. The product grid repopulates from an API after each change.
**Interactions needed:** 2 (tick Chisels, choose the sort option)
**Fragility:** This site advertises itself as a bug-hunting practice app, so some controls are deliberately unreliable (see the note on the price slider in the dropped list below). The category filter and the sort select both behaved correctly and repeatably here. The seeded catalogue could change on a major version bump (currently v5.0).

---

### T7  [shape: filter/sort then extract + late-loading content]
**Task:** Search USDA FoodData Central for "cheese", then restrict the results to the Foundation Foods data type. How many results does that leave, and what is the first one?
**Start URL:** https://fdc.nal.usda.gov/food-search?query=cheese
**Answer:** `19` results; first is `Cheese, cheddar`
**Accept also:** "19 Foundation Foods"; "Cheddar cheese" for the item name.
**Verified:** 2026-11-15. The results page loads asynchronously (several seconds of blank content first). The data-type filter is rendered with live counts: "Foundation Foods (19)", "SR Legacy Foods (277)", "Survey Foods (FNDDS) (787)", "Experimental Foods (0)", "Branded Foods (59,556)". Clicked "Foundation Foods (19)"; the URL became `?type=Foundation&query=cheese` and the list showed Cheese, cheddar / Cheese, swiss / Cheese, American, restaurant / Cheese, cotija, solid / ...
**Interactions needed:** 1 (click the Foundation Foods filter) from the pre-queried start URL; 3 if typing the query first
**Fragility:** The Branded Foods count drifts constantly, but Foundation Foods is a small curated set that USDA updates roughly twice a year (spring/autumn releases), so 19 should hold for the next month. The page needs a real wait before the counts exist.

---

### T8  [shape: filter/sort then extract]
**Task:** On the Toolshop practice store, show only products from the brand "ForgeFlex Tools" and sort by Price (Low - High). What is the first product and its price?
**Start URL:** https://practicesoftwaretesting.com/
**Answer:** `Washers`, `$3.55`
**Accept also:** "3.55" without the dollar sign.
**Verified:** 2026-11-15. Ticked the "ForgeFlex Tools" brand checkbox, then selected "Price (Low - High)". Resulting first page: Washers $3.55, Flat-Head Wood Screws $3.95, M4 Nuts $4.65, Phillips Screwdriver $4.92, ... Nine products per page.
**Interactions needed:** 2 (tick ForgeFlex Tools, choose the sort option)
**Fragility:** Same practice-site caveat as T6. The brand checkboxes sit below the category checkboxes in the same sidebar, so picking the right one matters.

---

### T9  [shape: drill down two levels + data table]
**Task:** Starting from Olympedia's page for the 1992 Summer Olympics, go to Athletics and then to the men's Marathon result. What Start Order number did the bronze medallist have?
**Start URL:** https://www.olympedia.org/editions/23
**Answer:** `21`
**Accept also:** Mentioning the bronze medallist as Stephan Freigang (GER) alongside the number 21.
**Verified:** 2026-11-15. /editions/23 → clicked "Athletics" (/editions/23/sports/ATH) → clicked "Marathon, Men" (/results/64053, an ID that cannot be guessed from the task text). Result table columns: `Pos | Start Order | Competitor | NOC | Time`. Row 3: `3 | 21 | Stephan Freigang | GER | 2-14:00 | Bronze`.
**Interactions needed:** 2 (click Athletics, click "Marathon, Men")
**Fragility:** The answer is the Start Order column, not Pos (3) and not the time — a careless reader will return 3. There is also a "Marathon, Women" link right beside the men's one. Historical Olympic results do not change.

---

### T10  [shape: drill down two levels]
**Task:** Search the On-Line Encyclopedia of Integer Sequences for the sequence that begins 1, 1, 2, 5, 14, 42, 132, 429. Open the entry for the Catalan numbers and report the value of its OFFSET field.
**Start URL:** https://oeis.org/
**Answer:** `0,3`
**Accept also:** "0, 3" with a space.
**Verified:** 2026-11-15. Typed `1, 1, 2, 5, 14, 42, 132, 429` into the search box and submitted; the results page interpreted it as `seq:1,1,2,5,14,42,132,429` and listed A000108 "Catalan numbers" first. Opened A000108 and read `OFFSET\n0,3`.
**Interactions needed:** 3 (type the sequence, submit, click through to A000108)
**Fragility:** Deliberately avoids the result count, which grows as OEIS adds sequences. The OFFSET field of A000108 is stable. The entry page is long, so OFFSET needs locating rather than just reading the top.

---

### T11  [shape: drill down two levels + data table]
**Task:** On NIST's Fundamental Physical Constants site, use the search box to look up the Planck constant, open its entry, and report the Standard uncertainty given for it.
**Start URL:** https://physics.nist.gov/cuu/Constants/index.html
**Answer:** `(exact)`
**Accept also:** "exact"; "it is exact, by definition". Do **not** accept the numerical value 6.626 070 15 x 10^-34 as the answer to this question — that is the Numerical value row, not the Standard uncertainty row.
**Verified:** 2026-11-15. Typed "Planck constant" into the `search_for` box and submitted → a list of eight matching constant names (elementary charge over h-bar, molar Planck constant, Planck constant, Planck constant in eV/Hz, reduced Planck constant, ...). Clicked the exact "Planck constant" entry → `Value?h` page showing `Numerical value  6.626 070 15 x 10-34 J Hz-1`, `Standard uncertainty  (exact)`, `Relative standard uncertainty  (exact)`.
**Interactions needed:** 3 (type the query, submit, click the exact "Planck constant" link among similarly named results)
**Fragility:** None seen. The Planck constant has been exact by definition since the 2019 SI redefinition, so this particular answer cannot drift even when CODATA publishes a new adjustment. Picking the right link from several similar names is part of the task.

---

### T12  [shape: drill down two levels]
**Task:** Search The Met's collection for "Washington Crossing the Delaware" and open the oil painting by Emanuel Leutze. What is its Object Number and its Credit Line?
**Start URL:** https://www.metmuseum.org/art/collection/search?q=Washington+Crossing+the+Delaware
**Answer:** Object Number `97.34`; Credit Line `Gift of John Stewart Kennedy, 1897`
**Accept also:** Accession number 97.34.
**Verified:** 2026-11-15. The search returns 84 object links, including at least two called "Washington Crossing the Delaware" — the Leutze painting (/art/collection/search/11417) and a print from the "Historical Events" series (/art/collection/search/781514), so the painting has to be picked deliberately. Object 11417 page gives: Medium "Oil on canvas", Dimensions "149 x 255 in. (378.5 x 647.7 cm)", Credit Line "Gift of John Stewart Kennedy, 1897", Object Number "97.34", Curatorial Department "The American Wing".
**Interactions needed:** 1 (click the correct result) from the pre-queried start URL; 3 if typing the query first
**Fragility:** Results are rendered client-side and take several seconds. The near-duplicate print result is the trap. Museum accession numbers do not change.

---

### T13  [shape: content that loads after the initial HTML]
**Task:** On the jsTree demo page, expand the "Root 1" node in the tree. What are the names of the child nodes that appear?
**Start URL:** https://www.jstree.com/demo/
**Answer:** `Child 1` and `Child 2`
**Accept also:** Either order.
**Verified:** 2026-11-15. The tree (`#jstree_demo`) initially renders only "Root 1" and "Root 2" — the children are not in the initial HTML. Clicking the open/close arrow (`i.jstree-ocl`) on Root 1 fires an AJAX request; after it returns the tree reads "Root 1 / Child 1 / Child 2 / Root 2".
**Interactions needed:** 1 (click the expand arrow on Root 1)
**Fragility:** The clickable target is the small arrow icon, not the node label — clicking the label selects rather than expands. The children arrive over the network, so reading immediately after the click returns the unexpanded tree. Small demo, so the answer is short; it is included because the late-arrival behaviour is exactly what the shape is testing.

---

### T14  [shape: non-Latin script with interaction]
**Task:** Go to Jisho and search for the Japanese character 鬱. Find the kanji entry in the results and report how many strokes it has and its On reading.
**Start URL:** https://jisho.org/
**Answer:** `29` strokes; On reading `ウツ`
**Accept also:** The On reading written as "utsu" in romaji; mentioning that it is a Jōyō kanji taught in junior high is fine extra detail.
**Verified:** 2026-11-15. Typed 鬱 into `#keyword` and submitted (URL became /search/%E9%AC%B1). The page leads with ~3,500 characters of word entries; the kanji block sits well below the fold and reads "Kanji — 1 found / 29 strokes. Jōyō kanji, taught in junior high. / 鬱 / gloom, depression, melancholy, luxuriant / Kun: うっ.する、 ふさ.ぐ、 しげ.る / On: ウツ".
**Interactions needed:** 2 (type the kanji, submit) plus scrolling to reach the kanji block
**Fragility:** Requires entering a non-Latin character and reading a non-Latin value back. The kanji section is far down the page past many word results, so a top-of-page read will miss it. Dictionary data is static.

---

### T15  [shape: non-Latin script with interaction]
**Task:** Look up 图书馆 in the MDBG Chinese-English dictionary. What is its traditional-character form, and what HSK level is it marked with?
**Start URL:** https://www.mdbg.net/chinese/dictionary
**Answer:** Traditional form `圖書館`; `HSK 1`
**Accept also:** Mentioning the Pinyin túshūguǎn and the meaning "library" as extra detail.
**Verified:** 2026-11-15. Typed 图书馆 into the `wdqb` search box and submitted. The result row reads: `图书馆 | túshūguǎn | library / CL: 家, 個｜个 | 圖書館 | HSK 1`.
**Interactions needed:** 2 (type the Chinese word, submit)
**Fragility:** Requires typing non-Latin text. The simplified and traditional forms sit in different columns of the same result row, so the answer depends on reading the right column. A cookie banner appears on first load. Dictionary content is static.

---

### T16  [shape: non-Latin script with interaction]
**Task:** Look up the character 鼎 on 汉典 (zdic.net). Report its 总笔画 (total stroke count) and its 注音 (Bopomofo reading).
**Start URL:** https://www.zdic.net/
**Answer:** 总笔画 `12`; 注音 `ㄉㄧㄥˇ`
**Accept also:** Pinyin "dǐng" given alongside the Bopomofo; mentioning 部首 鼎 or Unicode 9F0E as extra detail.
**Verified:** 2026-11-15. Typed 鼎 into the site search (`input[name=q]`) and submitted; landed on /hans/鼎. The character info block reads: `注音 ㄉㄧㄥˇ / 部首 鼎 / 部外 0 / 总笔画 12 / 统一码 CJK 9F0E / 笔顺 251115132125 / 字形结构 上下结构`.
**Interactions needed:** 2 (type the character, submit)
**Fragility:** Requires typing non-Latin text and reading two labelled fields out of a dense Chinese-language info block. Note 部外 is 0 and 总笔画 is 12 — a careless read could return the wrong one of the two adjacent numbers. Character data is static.

---

### T17  [shape: widget that is not a plain HTML control]
**Task:** Open the "Snap to increments" demo on the jQuery UI Slider page and drag the slider handle as far to the right as it will go. What does the "Donation amount" field then read?
**Start URL:** https://jqueryui.com/slider/
**Answer:** `$500`
**Accept also:** "500 dollars"; "$500.00".
**Verified:** 2026-11-15. Opened the Snap-to-increments demo inside `iframe.demo-frame`. The readout starts at `$100` and nothing on the page states the maximum, so 500 cannot be guessed without operating the control. Verified two independent ways: focusing the handle and pressing ArrowRight 12 times → `$500`; and a genuine mouse press-move-release drag past the right end of the track → `$500`.
**Interactions needed:** 2 (open the Snap-to-increments demo, drag the handle)
**Fragility:** It is a jQuery UI slider `<div>` with a handle, not an `<input type=range>`, and it lives in an iframe. The readout is driven by the widget's `slide` event, so setting the underlying value by script without generating slide events leaves the field showing $100 — the field only updates if the control is genuinely operated.

---

### T18  [shape: widget that is not a plain HTML control]
**Task:** On the jQuery UI Datepicker page, open the "Display month & year menus" demo. Using that calendar, select 15 January 2020. What value appears in the Date field?
**Start URL:** https://jqueryui.com/datepicker/
**Answer:** `01/15/2020`
**Accept also:** none — the field's literal contents are required, in that format.
**Verified:** 2026-11-15. Opened the demo in `iframe.demo-frame`, clicked `#datepicker` to pop the calendar, which exposes month and year dropdowns. Selected month "Jan", confirmed the year dropdown offers 2016–2036 (so 2020 is present), selected "2020", clicked day 15. The input then read `01/15/2020`.
**Interactions needed:** 5 (open the demo, click the field, pick the month, pick the year, click the day)
**Fragility:** Inside an iframe. The calendar is a popup built of `<a>` elements, not a native date input. The year dropdown is a sliding window around the current year (current−10 to current+10), so 2020 remains selectable for several more years but this would need revisiting around 2031.

---

### T19  [shape: widget that is not a plain HTML control]
**Task:** On the Ptable interactive periodic table, select the element Krypton. Which series does it belong to, and what is its listed electron energy-level configuration?
**Start URL:** https://ptable.com/
**Answer:** Series `Noble gases`; energy levels `2, 8, 18, 8`
**Accept also:** "2 8 18 8" without commas; mentioning atomic number 36 and weight 83.798 as extra detail.
**Verified:** 2026-11-15. The page opens showing Hydrogen in the detail panel. Clicked the Krypton tile; the panel re-rendered to `36 / Kr / Krypton / 83.798 / 2 8 18 8 / Series: Noble gases / State at …: Gas / Weight 83.798 u / Energy levels 2, 8, 18, 8`.
**Interactions needed:** 1 (click the Krypton tile)
**Fragility:** The table is a canvas-like grid of custom tiles with no form controls; the detail panel updates in place rather than navigating, so the answer only exists after the click. Element data cannot drift.

---

### T20  [shape: data table / grid, value related to its column header]
**Task:** On USDA FoodData Central, search for raw almonds among Foundation Foods and open "Nuts, almonds, whole, raw". In the nutrient table, what is the **Max** value recorded for Magnesium, Mg?
**Start URL:** https://fdc.nal.usda.gov/food-search?query=raw+almonds&type=Foundation
**Answer:** `271` mg
**Accept also:** "271 mg". Do **not** accept 258 — that is the Average Amount, and 238 is the Min.
**Verified:** 2026-11-15. Clicked through to /food-details/2346393/nutrients. The table header is `Name | Average Amount | Unit | Deriv. By | n | Samples | Min | Max | Median | Footnote | Initial Year Acquired`. The Magnesium row reads `Magnesium, Mg | 258 | mg | Analytical | 8 | Samples | 238 | 271 | 258 | | 2022`.
**Interactions needed:** 1 (click the food) from the pre-queried start URL; 3 if searching and filtering first
**Fragility:** The answer requires counting across to the Max column past Average, Unit, Deriv. By, n and Samples — Average (258) and Median (258) are identical here, which makes a mis-aligned read look plausible. The page is a slow-loading SPA with ~494 table rows. Published Foundation entries keep fixed FDC IDs and values.

---

### T21  [shape: data table / grid, value related to its column header]
**Task:** On USDA FoodData Central, find "Cheese, cheddar" in the Foundation Foods data and report the **Median** value for Sodium, Na and the number of samples (n) it is based on.
**Start URL:** https://fdc.nal.usda.gov/food-search?query=cheese
**Answer:** Median `650` mg; n = `41`
**Accept also:** "650 mg" and "41 samples". Do **not** accept 654 — that is the Average Amount.
**Verified:** 2026-11-15. From the plain "cheese" search, clicked the "Foundation Foods (19)" filter, then clicked "Cheese, cheddar" → /food-details/328637/nutrients. Sodium row: `Sodium, Na | 654 | mg | Analytical | 41 | Samples | 575 | 743 | 650 | | 2013`. For cross-reference the Calcium row is `707 | mg | Analytical | 41 | Samples | 641 | 761 | 708`.
**Interactions needed:** 2 (apply the Foundation Foods filter, click the food)
**Fragility:** Average (654) and Median (650) are close enough that a sloppy read returns the wrong one, which is the point. Same slow SPA caveat as T20.

---

### T22  [shape: content that loads after the initial HTML]
**Task:** On the Toolshop practice store, use the site's search box to search for "sander". How many products come back, and what is the price of the most expensive one?
**Start URL:** https://practicesoftwaretesting.com/
**Answer:** `3` products; most expensive is `$100.79` (Random Orbit Sander)
**Accept also:** "100.79" without the dollar sign; listing all three (Sheet Sander $58.48, Belt Sander $73.59, Random Orbit Sander $100.79).
**Verified:** 2026-11-15. Typed "sander" into `input[data-test=search-query]` and clicked `button[data-test=search-submit]`. The product grid is replaced asynchronously from an API call; after it settled it held exactly three products: Sheet Sander $58.48, Belt Sander $73.59, Random Orbit Sander $100.79.
**Interactions needed:** 2 (type the query, click search)
**Fragility:** Results arrive after a network round trip, so an immediate read shows the full unfiltered catalogue instead. Same practice-site/seed-data caveat as T6 and T8.

---

## Summary

**Written and verified: 22. Dropped: 7.**

All 22 above were performed end to end against the live sites on 2026-11-15 using
a real headless Chromium, and every answer string was read off the page after
doing the work.

### Dropped, and why

1. **NHTSA vehicle recalls** (`nhtsa.gov/recalls`) — intended as a cascading Year→Make→Model dependency task. The site returns **HTTP 403 "Access Denied"** from an automated browser (Akamai edge block). Unusable.
2. **timeanddate.com date-duration calculator** — intended as a multi-step form. Serves a **Cloudflare interstitial ("Just a moment…", HTTP 403)** instead of the page. Unusable.
3. **gramota.ru** (Russian spelling dictionary) — intended as a third non-Latin task in a third script. Loaded once during reconnaissance, then returned `ERR_CONNECTION_REFUSED` on every subsequent attempt including the homepage. Too unreliable to put in an eval; replaced by a second Chinese site (zdic).
4. **Toolshop price-range slider** — intended as a third custom-widget task. The `ngx-slider` itself drives fine by keyboard, but the **filter it feeds is wrong**: setting the range to 100–200 still returned products at $66.54, $73.59, $80.19, $86.71 and $89.55, and setting the minimum to 50 still returned a $48.41 item. The site is explicitly a bug-hunting practice app, so this may well be deliberate — either way there is no defensible single answer.
5. **MDN browser-compatibility table** — intended as an expandable-widget plus column-header task. `table.bc-table` exists in the DOM but its header and body cells came back empty under automation (the compat data is no longer rendered into a plain table), so there was nothing to read.
6. **Open Library faceted search** — intended as a filter-then-count task. Facets work, but the result totals ("1 - 20 of 48,286 results") drift continuously as records are added, which fails the stability rule.
7. **Swagger Petstore** — intended as an expandable-panel plus late-loading task. The operations are backed by a shared public demo API whose data is mutated by everyone using it, so no answer is stable; and exercising it properly would mean writing to someone else's service.

### Shape coverage

| Shape | Tasks | Count |
|---|---|---|
| 1. Multi-step form with dependency | T1, T2, T3, T4 | 4 |
| 2. Filter / sort / paginate then extract | T5, T6, T7, T8 | 4 |
| 3. Drill down two or more levels | T9, T10, T11, T12 | 4 |
| 4. Content that loads after initial HTML | T13, T22 (plus T4, T7, T20, T21) | 2 dedicated, 6 total |
| 5. Non-Latin script with interaction | T14, T15, T16 | 3 |
| 6. Widget that is not a plain HTML control | T17, T18, T19 | 3 |
| 7. Data table / grid, value related to header | T20, T21 (plus T5, T9, T11) | 2 dedicated, 5 total |

**Under-represented: shape 4 and shape 7**, each with only two tasks written
purely for that shape. In practice both are better covered than the table
suggests — four other tasks (T4, T7, T20, T21) require waiting on content that
arrives after the initial HTML, and three others (T5, T9, T11) require relating a
value to the right column or row label. The two shapes are thin only on
*dedicated* tasks, and that is a consequence of the drops: the Swagger Petstore
and the MDN compat table were the two candidates that would have added one each.

Shape 5 is the one I would strengthen next: all three tasks are dictionary
look-ups, and two of the three are Chinese, because the Russian site became
unreachable mid-exercise. A third script (Korean, Arabic or Hebrew) and a
non-dictionary interaction would make that group less repetitive.

### Notes on safety and statefulness

No task creates an account, posts, purchases or writes anything that persists.
T3 clicks a submit button but client-side validation blocks the submission, so
nothing reaches the server. T6, T8 and T22 type into a site explicitly published
as a testing sandbox, and only read. Everything else is read-only navigation,
searching and filtering.

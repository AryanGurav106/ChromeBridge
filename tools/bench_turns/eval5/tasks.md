# eval5 — browser scenarios

Ten multi-step scenarios on public websites. Every one was walked end to end in a
real browser on the date recorded against it; the answers below are what was
observed on screen, not inferred.

Conventions used throughout:
- Steps are written as a person would do them, not as URLs.
- **Answer:** gives the load-bearing values in backticks, one span per distinct value.
- Flags call out time-sensitivity, visitor-dependent rendering, and how confident
  I am that two careful people would write down the same answer.

---

## T1 — Filter, sort and paginate the BLS Occupation Finder

**Site:** U.S. Bureau of Labor Statistics, Occupational Outlook Handbook
(`bls.gov/ooh`)

1. Open the Occupational Outlook Handbook at `bls.gov/ooh`.
2. From the OOH navigation bar, open **Occupation Finder**.
3. Leave the **Show** control at its default of `25` entries.
4. In the filter row under the **ON-THE-JOB TRAINING** column header, choose
   `None` from the dropdown.
5. In the filter row under the **2025 MEDIAN PAY** column header, choose
   `$100,000 or more`.
6. Read the status line under the table ("Showing 1 to 25 of N entries (filtered
   from 831 total entries)") and note how many occupations survive both filters.
7. Click the **OCCUPATION** column header once to sort the table alphabetically
   A→Z.
8. Click **Next** above the table twice, to reach the third page (entries 51–75).
9. Read the occupation named in the first row of that page.

**Question:** How many occupations match both filters, and which occupation is
the first row on page 3 once the table is sorted by occupation A→Z?

**Answer:** `96` matching occupations; the first row of page 3 is
`Law teachers, postsecondary`.

**Verified:** 2026-11-16

**Flags:**
- *Time-sensitive.* BLS revises the Occupational Outlook Handbook roughly once a
  year (the pay column was labelled "2025 MEDIAN PAY" when observed, and the
  unfiltered total was 831). Both the count of 96 and which occupation lands
  first on page 3 will move at the next revision.
- *Visitor variation:* none expected; the table is server-rendered and the
  filters are plain `<select>` elements. But the page size is a user-set control,
  so the scenario must say to leave it at 25 or pagination differs.
- *Confidence the answer is unambiguous:* high on the day. The displayed pay
  column shows buckets ("$100,000 or more"), not dollar figures — the answer is
  deliberately the occupation name, not a number.

---

## T2 — Dependent dropdowns in the ETH Zürich course catalogue

**Site:** ETH Zürich Course Catalogue (`vvz.ethz.ch`)

1. Open the ETH Zürich Course Catalogue and go to **Search for Courses**. If the
   page is in German, click **en** in the header strip to switch to English.
2. Set **Semester** to `Autumn Semester 2024`. (Changing the semester reloads the
   form and clears the fields below it, so do this first.)
3. Set **Level** to `Bachelor's Degree Programme`. Watch the **Programme**
   dropdown: it drops from 184 options to 31, and **Department** drops from 17 to
   15 — the options below depend on this field.
4. Set **Programme** to `Physics Bachelor`. A new **Section** dropdown appears
   that did not exist before, listing that programme's own sections.
5. Set **Section** to `First Year Compulsory Courses`.
6. Click **Search**.
7. In the results, note that the courses are grouped under two headings: *First
   Year Examination Block 1* and *First Year Examination Block 2*.
8. Find the single course unit listed under **First Year Examination Block 2** and
   read its course number and ECTS credits from the table.

**Question:** What is the course number of the only course unit under "First Year
Examination Block 2", and how many ECTS credits does it carry?

**Answer:** `401-1151-00L` (Linear Algebra I), `7 credits`.

**Verified:** 2026-11-16

**Flags:**
- *Time-sensitive:* barely. Autumn Semester 2024 is a closed semester and ETH
  keeps historical catalogues, so the result set is frozen. The *current* semester
  offered in the dropdown moves, but the scenario names a past one.
- *Visitor variation:* the catalogue picks its language from the browser. A
  German-locale visitor lands on the German UI, where the labels are
  "Semester / Stufe / Studiengang / Bereich" — hence the explicit "click en" step.
- *Confidence:* high. Block 2 contained exactly one course when observed, and the
  course number is printed verbatim in the first column.

---

## T3 — Drill four levels into Olympedia to a single heat

**Site:** Olympedia (`olympedia.org`)

1. Open `olympedia.org`.
2. From the top navigation, open **Games → Overview**.
3. In the **Summer Olympic Games** table, find the row numbered **XXIX / 2008 /
   Beijing** and click it.
4. On the 2008 Summer Olympics edition page, scroll to the list of disciplines and
   click **Athletics**.
5. In the list of 2008 athletics events, click **800 metres, Men**.
6. Scroll past the final standings table to the section headed **Semi-Finals**.
7. Within Semi-Finals, find the sub-table headed **Heat #3**.
8. Read the row in 4th position: the competitor's name and the time in the
   "Time (Automatic)" column.

**Question:** In the Semi-Finals, Heat #3 of the men's 800 metres at the 2008
Summer Olympics, who finished 4th and what time is recorded against them?

**Answer:** `Manuel Olmedo` (ESP), `1:45.91`.

**Verified:** 2026-11-16

**Flags:**
- *Time-sensitive:* no. 2008 results are settled historical data.
- *Visitor variation:* none; Olympedia is plain server-rendered HTML with no
  consent wall and no personalisation. It is a volunteer-run site and is
  occasionally slow or briefly unavailable.
- *Confidence:* high. The page has one "Semi-Finals" heading with Heat #1/#2/#3
  beneath it, and the 4th row is unambiguous.

---

## T4 — Build a LibTorch download command in the PyTorch install configurator

**Site:** PyTorch (`pytorch.org`)

1. Open `pytorch.org`.
2. Go to **Get Started → Start Locally**, which shows the "Start Locally"
   selection matrix.
3. In the **PyTorch Build** row, leave **Stable** selected.
4. In the **Your OS** row, click **Linux**. (Note the Compute Platform row changes:
   on Mac the CUDA options are struck through and the last option reads "Default";
   on Linux they become selectable and the last option reads "CPU".)
5. In the **Package** row, click **LibTorch**.
6. In the **Language** row, click **C++ / Java**.
7. In the **Compute Platform** row, click **CUDA 13.2**.
8. Read the contents of the **Run this Command:** box.

**Question:** With Stable / Linux / LibTorch / C++ / Java / CUDA 13.2 selected,
what download URL does the "Run this Command" box give for the cxx11 ABI build?

**Answer:**
`https://download.pytorch.org/libtorch/cu132/libtorch-shared-with-deps-2.15.0%2Bcu132.zip`
(shown under the label `Download here (cxx11 ABI):`)

**Verified:** 2026-11-16

**Flags:**
- *Time-sensitive: significantly.* The stable build was labelled **Stable
  (2.15.0)** and the CUDA choices were 13.2 / 13.4 / ROCm 10.0 when observed. The
  URL embeds both the version (`2.15.0`) and the CUDA build (`cu132`), so a
  PyTorch release changes the answer. The *mechanism* (selections accumulating
  into one command) is durable; the exact string is not.
- *Visitor variation:* the matrix pre-selects **Your OS** from the visitor's
  platform (it opened on Mac here). Step 4 overrides that, so the end state is the
  same for everyone — but a reader must actually click Linux rather than assume.
- *Confidence:* high. The command box holds exactly one URL for this combination.

---

## T5 — Compare two Vermont universities in NCES College Navigator

**Site:** NCES College Navigator (`nces.ed.gov/collegenavigator`)

1. Open NCES College Navigator.
2. In the search form, set **State** to `Vermont`.
3. Click **Show Results**.
4. In the results list, click **University of Vermont**.
5. On its page, click the collapsed section **Tuition, Fees, and Estimated Student
   Expenses** to expand it.
6. In the "Estimated expenses for academic year" table, read the **In-state** row
   under the **2024-2025** column.
7. Go back to the Vermont results list.
8. Click **Vermont State University**.
9. Expand the same **Tuition, Fees, and Estimated Student Expenses** section.
10. Read its **In-state / 2024-2025** figure and compare the two.

**Question:** Of the University of Vermont and Vermont State University, which had
the higher published in-state tuition and fees for 2024-2025, and what was that
figure?

**Answer:** `University of Vermont`, at `$19,058` (Vermont State University shows
`$11,952`).

**Verified:** 2026-11-16

**Flags:**
- *Time-sensitive: mildly.* The figure for the named column (2024-2025) is a
  published IPEDS value and does not change. But NCES adds a new academic-year
  column each release, so "the last column" is not a safe way to phrase it — the
  scenario names the column explicitly for that reason.
- *Visitor variation:* none. It is a server-rendered ASP.NET page; the expand/
  collapse sections are the only client-side behaviour.
- *Confidence:* high. Both figures are printed in a labelled row/column cell.
  Vermont State University's figures drop sharply between 2022-23 and 2023-24
  because of its 2023 merger — that is real, not a reading error.

---

## T6 — Refine an IETF document search down to one RFC

**Site:** IETF Datatracker (`datatracker.ietf.org`)

1. Open the IETF Datatracker and go to **Documents → Search**.
2. Type `multicast` into the "Document name/title/RFC number" box and search.
3. Note the banner: *"Too many documents match your query! Returning only a partial
   result (200 matches)."* — this is too broad to use.
4. Expand **Additional search criteria**.
5. Under **Document Type**, leave **RFC** ticked and untick **Internet-Draft
   (active)**, so only published RFCs are searched.
6. Still in the additional criteria, with the **WG** radio selected, type `bier`
   into the WG box.
7. Search again. The result is now down to three RFCs.
8. Narrow once more: change the search term in the main box from `multicast` to
   `multicast vpn`.
9. Search again — exactly one RFC remains.
10. Read its RFC number, title and publication date from the results row.

**Question:** After narrowing to RFCs only, to the BIER working group, and to the
term "multicast vpn", which single RFC is left and when was it published?

**Answer:** `RFC 8556` — "Multicast VPN Using Bit Index Explicit Replication
(BIER)" — published `2019-04`.

**Verified:** 2026-11-16

**Flags:**
- *Time-sensitive:* very little. RFCs are immutable and BIER is a closed-ish
  working group; a new RFC would have to match both "multicast vpn" and WG=bier to
  disturb the count of one.
- *Visitor variation:* none, though the Datatracker has a dark/light theme that
  changes only appearance. No login is needed for search.
- *Confidence:* high. The results page states "RFC (1 hit)" explicitly.
- *Note for whoever runs this:* the Author / WG / Area / Responsible-AD criteria
  are **radio buttons**, i.e. mutually exclusive — you cannot stack WG and AD. The
  third refinement therefore has to tighten the free-text term, which is what step
  8 does.

---

## T7 — Query the USGS earthquake catalogue, then re-sort the loaded results

**Site:** USGS Earthquake Hazards Program (`earthquake.usgs.gov`)

1. Open `earthquake.usgs.gov` and go to **Search Earthquake Catalog**.
2. Under **Magnitude**, select **Custom** and set the **Minimum** to `7.0`, leaving
   the maximum blank.
3. Under **Date & Time**, select **Custom** and set **Start (UTC)** to
   `2018-01-01 00:00:00` and **End (UTC)** to `2018-12-31 23:59:59`.
4. Leave **Geographic Region** on **World**.
5. Click **Search**.
6. Wait — the page hands off to the map/list viewer and the results arrive after
   the page has already rendered; the list is empty for a moment first.
7. Read the header in the results sidebar: "Showing N earthquakes".
8. In that sidebar, change the **Sort** control from `Time` to `Magnitude`.
9. Read the magnitude and depth of the event now at the top of the list.

**Question:** How many earthquakes does the search return, and what are the
magnitude and depth of the largest one?

**Answer:** `17` earthquakes; the largest is magnitude `8.2` ("2018 Fiji
Earthquake", 2018-08-19) at a depth of `600.0 km`.

**Verified:** 2026-11-16

**Flags:**
- *Time-sensitive: mildly.* The catalogue is historical, but USGS does
  occasionally revise magnitudes, which could move an event across the 7.0
  threshold and change the count of 17. The 8.2 / 600.0 km values for the deep
  Fiji event are long settled.
- *Visitor variation:* the viewer has a **Settings** panel with a time-zone
  choice; it defaulted to UTC here. A visitor set to local time sees different
  date strings (the magnitude and depth are unaffected) — which is why the answer
  is keyed on magnitude and depth rather than on a timestamp.
- *Confidence:* high for the magnitude and depth; medium for the count, for the
  revision reason above.
- This is the scenario where later steps genuinely depend on late-arriving
  content: the Sort control in step 8 does not exist until the results have
  loaded, and it re-orders data already in the browser rather than re-querying.

---

## T8 — Convert a currency on a specific past date at the Bank of Canada

**Site:** Bank of Canada (`bankofcanada.ca`)

1. Open `bankofcanada.ca`.
2. Go to **Statistics → Exchange rates → Currency Converter**.
3. Set **Amount** to `250.00`.
4. Leave **From** as `Canadian dollar`.
5. Set **To** to `Japanese yen`.
6. In the **Dates** section, change **Select date range** from `1 week` to
   `Custom dates`. Two new fields appear — "Start (or single date)" and "End date"
   — which were not on the page before.
7. Enter `2024-09-03` in **Start (or single date)** and leave **End date** blank.
8. Click **Convert**.
9. In the Results table, read the row for 2024-09-03: the "Value of 250.00 CAD in
   JPY" column and the "CAD → JPY" rate column.

**Question:** What were 250.00 Canadian dollars worth in Japanese yen on
3 September 2024, and what CAD → JPY rate was used?

**Answer:** `26,910.65 JPY`, at a rate of `107.6426`.

**Verified:** 2026-11-16

**Flags:**
- *Time-sensitive:* no. Bank of Canada daily rates for past dates are final, so a
  historical conversion is reproducible indefinitely.
- *Visitor variation:* the site has a light/dark theme toggle and an **FR**
  language switch in the header; neither changes the numbers. There is a standing
  notice that the Bank added MYR/PLN/THB and stopped publishing RUB and SAR in May
  2026 — the available currency list can change, but JPY is unaffected.
- *Confidence:* high. The result is a single labelled table row, and the column
  heading restates the amount ("Value of 250.00 CAD in JPY") so a misread amount is
  self-evident.

---

## T9 — Read one cell out of a USNO twilight table

**Site:** U.S. Naval Observatory, Astronomical Applications Department
(`aa.usno.navy.mil`)

1. Open `aa.usno.navy.mil` and go to **Data Services**.
2. In the Rise/Set/Transit/Twilight Data list, open **Table of Sunrise/Sunset,
   Moonrise/Moonset, or Twilight Times for an Entire Year**.
3. Set **Year** to `2027`.
4. Set **Type of Table** to `civil twilight`.
5. Under **Location**, click **Need USA Location?** — a "US Location" dialog opens.
6. In that dialog, type `Juneau` in **City**, set **State or Territory** to
   `Alaska`, and click **Import Data**.
7. Confirm the dialog has filled the form for you: **Latitude** `58.3`,
   **Longitude** `-134.42`, **Location Label** `Juneau, AK`, time zone 9h west.
8. Click **Get Data**.
9. In the resulting table — one column pair (Begin / End) per month, one row per
   day of the month — find the row for day **15**.
10. Read the two values in the **Sept.** column of that row.

**Question:** In the 2027 civil twilight table for Juneau, Alaska, what Begin and
End times are shown for 15 September?

**Answer:** Begin `0447`, End `1857`. (The table is 24-hour local standard time,
so these are 04:47 and 18:57.)

**Verified:** 2026-11-16

**Flags:**
- *Time-sensitive:* no. These are computed astronomical quantities for a fixed
  place and date; the table is reproducible for any year 1700–2100.
- *Visitor variation:* none — the output is a fixed-width `<pre>` table and the
  location comes entirely from the form. Note the table uses **local standard
  time** year-round with no daylight-saving adjustment, which the page states in
  its instructions.
- *Confidence:* high. This is the cleanest row-and-column read in the set: the
  row is labelled "15" and the column group is headed "Sept." with Begin/End
  sub-columns.
- The USNO site has had extended outages in the past; if it is down the scenario
  cannot be run at all (it will not fail subtly).

---

## T10 — 日本郵便で郵便番号を調べる (Japan Post postal-code lookup)

**Site:** 日本郵便 郵便番号検索 (`post.japanpost.jp/zipcode/`) — natively Japanese

1. `post.japanpost.jp/zipcode/` を開く（日本郵便の「郵便番号検索」）。
2. 「国内の郵便番号」の都道府県一覧から **石川** を選ぶ。
3. 石川県の市区町村一覧が表示される。先頭のかな行タブから **サ行** を選ぶ。
4. サ行の一覧の中から **珠洲市** を選ぶ。（同じ欄にある「珠洲郡内浦町」は
   「鳳珠郡能登町に住所変更」と注記されている旧自治体なので選ばない。）
5. 珠洲市の町域一覧が表示される。かな行タブから **ナ行** を選ぶ。
   （「狼煙町」は読みが「ノロシマチ」なので、漢字ではなく読みでナ行に入る。）
6. ナ行の一覧の中から **狼煙町** を探す。
7. その行に表示されている郵便番号を読む。

**Question (English):** Starting from Japan Post's postal-code search, drilling
Ishikawa Prefecture → Suzu City → the ナ行 group of town names, what postal code is
listed for 狼煙町 (ノロシマチ)?

**Answer:** `927-1441` (for `狼煙町`; the neighbouring 狼煙新町 is `927-1442`).

**Verified:** 2026-11-16

**Flags:**
- *Time-sensitive:* no. The Ishikawa page carried a "(2025.3.28掲載)" publication
  note when observed; postal codes for existing towns change very rarely.
- *Visitor variation:* the site has an **English** link in the header, but the
  postal-code search itself is Japanese-only — the town-name lists, the kana-row
  tabs and the change notices are all in Japanese. No consent wall, no login.
- *Confidence:* high. One town name, one code, printed side by side.
- Worth knowing for anyone running it: the kana tabs file towns by **reading**,
  not by kanji, so 狼煙町 sits under ナ行 and not under any row a non-reader would
  guess from the characters. That is the step that makes this more than a lookup.
  Note also that elsewhere in the same list 宝立町黒峰 and 宝立町柏原 share the code
  927-1228 — codes are not unique per town, so the scenario asks for the code of a
  named town and not the reverse.

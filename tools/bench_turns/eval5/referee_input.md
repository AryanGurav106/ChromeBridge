# EVAL 5 — REFEREE INPUT

The author's answers, verification dates and caveats are MECHANICALLY REMOVED by
a whitelist: only the title, site, numbered steps and the end-state question
survive. `tasks.md` is deliberately NOT your input and you must not open it.

Walk each scenario on the live site and re-derive the end-state value yourself.
Where your answer and the author's disagree, the task is DROPPED rather than
adjudicated -- so a disagreement you report is a success, not a failure.

## T1 — Filter, sort and paginate the BLS Occupation Finder
**Site:** U.S. Bureau of Labor Statistics, Occupational Outlook Handbook

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


## T9 — Read one cell out of a USNO twilight table
**Site:** U.S. Naval Observatory, Astronomical Applications Department

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


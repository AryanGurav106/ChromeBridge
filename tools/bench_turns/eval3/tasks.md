# EVAL 3 TASKS — written blind by an authoring agent (no knowledge of any toolset
# under test), given only a deny-list of domains used in evals 1-2 and #39-#43.
# EXPECTED values are the AUTHOR'S and are NOT ground truth; the referee
# establishes that independently.
# Author dropped: CIA World Factbook (sunset 4 Feb 2026), geonames.org,
# timeanddate.com, Met Office climate averages — could not confirm.

T1  | A doc-lookup | https://man7.org/linux/man-pages/dir_section_2.html
Open the manual page for open(2). In its ERRORS section, report the errno NAME returned when pathname refers to a directory and the access requested involved writing. Report only the errno name (e.g. EFOO).
author: EISDIR | distractors: EACCES, EROFS, ENOTDIR; EISDIR appears TWICE (2nd is O_TMPFILE)

T2  | A doc-lookup | https://git-scm.com/docs
Open the git-config reference page and find the variable core.bigFileThreshold. Report its default value exactly as the page states it (a number plus a unit).
author: 512 MiB | distractors: core.deltaBaseCacheLimit 96m; hundreds of "The default is ..." on a ~450KB page

T3  | A doc-lookup | https://www.kernel.org/doc/html/latest/admin-guide/index.html
Navigate to "Documentation for /proc/sys/vm/" and report the default value of swappiness as a bare number.
author: 60 | distractors: vfs_cache_pressure 100, page-cluster 3, range 0..200 and the value 100

T4  | B search-flow | https://www.gov.uk
Use the site's own search box to find the UK bank holidays page, then report the date of the Summer bank holiday in SCOTLAND in 2027, formatted "D Month YYYY".
author: 2 August 2027 | distractors: England/Wales + NI = 30 August 2027 (the default tab)

T5  | B search-flow | https://find-and-update.company-information.service.gov.uk/
Search for "TESCO PLC", open the company record whose company number is 00445790, and report the "Incorporated on" date as shown.
author: 27 November 1947 | distractors: other Tesco entities; "Next/Last accounts made up to"

T6  | B search-flow | https://www.rijksmuseum.nl/en
Use the site's search to find Johannes Vermeer's painting "The Milkmaid", open its object page, and report the object number.
author: SK-A-2344 | distractors: many RP-/SK- copies titled Milkmaid; SK-C-5 is The Night Watch

T7  | C form-lookup | https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany
In the EDGAR company search form, search by company name for "NIKE" and report the CIK number shown for NIKE, Inc., including its leading zeros.
author: 0000320187 | distractors: SEC file no 001-10635, SIC 3021; dropping leading zeros

T8  | C form-lookup | https://www.fueleconomy.gov/
Use the "Find a Car" form to select model year 2012, make Toyota, model Prius. Report the Combined MPG for the 2012 Toyota Prius — the standard hybrid, not the Plug-in Hybrid.
author: 48 | distractors: City 49, Highway 46; Plug-in "Gas Only 50" and "Electricity 95"

T9  | C form-lookup | https://util.unicode.org/UnicodeJsps/character.jsp
Use the character lookup form to look up the code point U+20AC, then report the value of its Age property exactly as the page prints it.
author: V2_1 | distractors: blk/gc/sc rows; "2.1" mis-transcription

T10 | D data-table | https://nssdc.gsfc.nasa.gov/planetary/
Open the Planetary Fact Sheet and report the value in the row "Mean Temperature (C)" in the column for Uranus.
author: -195 | distractors: Neptune -200, Saturn -140; US-units and Ratio-to-Earth versions exist

T11 | D data-table | https://www.hko.gov.hk/en/cis/climat.htm
Under Normals, select the 1991-2020 period and open "Monthly/Yearly Normals". In the monthly mean temperature table, report the value in the "Mean (deg. C)" column for the row "July".
author: 28.9 | distractors: Mean Daily Max/Min columns for July; other normals periods

T12 | E drill-down | https://www.law.cornell.edu/uscode/text
Drill from the U.S. Code table of contents into Title 17 -> Chapter 3 -> section 302, and report the number of years after the author's death for which copyright endures under subsection (a). Report just the number.
author: 70 | distractors: (c) 95 and 120; (b) joint works; sections 303/304 carry 28 and 67

T13 | E drill-down | https://www.legislation.gov.uk/ukpga
Browse UK Public General Acts to 2015, open the Consumer Rights Act 2015, go to section 22, and report the number of days given as the time limit in subsection (3). Report just the number.
author: 30 (UNCERTAIN — author could not render the site; path unverified)
distractors: 7-day extension in (6)-(8); 6-month rule in s.19

T14 | E drill-down | https://www.itis.gov/servlet/SingleRpt/SingleRpt?search_topic=TSN&search_value=180580
From this ITIS record for the family Felidae, drill down to the genus Felis and then to the species Felis nigripes, and report its Taxonomic Serial Number (TSN).
author: 183800 | distractors: start TSN 180580, genus Felis 180586, subspecies 726323/726324

T15 | F non-Latin (ja) | https://www.data.jma.go.jp/stats/etrn/index.php
This is the Japan Meteorological Agency's past-weather search, entirely in Japanese. Navigate 東京都 -> 東京 -> 年ごとの値 and report the 降水量の合計 (annual total precipitation, in mm) for 2020年.
author: 1590.0 | distractors: 平均気温 16.5 in the adjacent column; other 東京都 stations

T16 | F non-Latin (zh-Hant) | https://dict.revised.moe.edu.tw/
Taiwan's MOE Revised Mandarin Dictionary, in Chinese. Search for 颱風, open the entry for 颱風 itself, and report its 注音.
author: ㄊㄞˊ ㄈㄥ | distractors: 漢語拼音 "tái fēng" beside it; 8 compound entries; dropped tone mark

T17 | F non-Latin (ko) | https://stdict.korean.go.kr/main/main.do
The National Institute of Korean Language's Standard Korean Dictionary, in Korean. Search for 학교, open the entry, and report the 원어 (the Hanja origin) shown for it.
author: 學校 | distractors: 품사 「명사」; reporting the Hangul 학교 instead of Hanja

T18 | G spa | https://caniuse.com
Use the site's search to open the "WebP image format" feature, then report the first Safari (desktop) version listed as having FULL support. Report just the version number.
author: 16.0 | distractors: Safari 14 is PARTIAL (the trap); Safari on iOS is a separate column

T19 | G spa | https://pubchem.ncbi.nlm.nih.gov
Search for aspirin, open the compound summary page for CID 2244, and report the Molecular Formula exactly as shown.
author: C9H8O4 | distractors: Molecular Weight 180.16; salicylic acid CID 338 C7H6O3

T20 | G spa | https://periodic-table.rsc.org/
In the interactive periodic table, open the element Xenon and report its Melting point in degrees Celsius, exactly as the page prints that value.
author: -111.75 C | distractors: Boiling point -108.099 C on the line below; F and K on the same line

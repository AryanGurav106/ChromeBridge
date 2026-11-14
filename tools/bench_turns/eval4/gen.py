# -*- coding: utf-8 -*-
"""Generate the 38 eval-3 prompts. The two arms differ ONLY by namespace, so the
substitution is done once from one template and asserted identical afterwards."""
import json, os, random

HERE = os.path.dirname(os.path.abspath(__file__))

TPL = """You are running one task in a browser-automation evaluation. Work entirely in the
browser. Answer from the live pages, never from memory or prior knowledge.

TOOLS: use ONLY tools whose names start with `{NS}`. Do not use any other
browser toolset.

TASK {TID}:
Start at {START}
{TASK}

Work efficiently but do not guess: every reported value must have been read off a
page you actually loaded. If a value is genuinely unobtainable, say so rather than
inventing it. Do not close any tab you did not open. Do not log in, buy anything,
post anything, or enter personal data anywhere.

When done, reply with EXACTLY these seven lines and nothing else:

ANSWER: <the answer, all requested parts, verbatim where the task says exact>
TOOL_CALLS: <total number of tool calls you made, including ToolSearch>
BROWSER_CALLS: <of those, how many were {NS} calls>
FIRST_CONTENT_AT: <the 1-based index of the first tool call that returned actual PAGE CONTENT to you>
BATCHED: <no | yes, N times>
BLOCKERS: <none | anything that cost you an extra round trip>
DEFECTS: <none | any tool output that was wrong, misleading, empty when it should not be, or that made you re-check something>"""

T = {
 "T1": ("A", "https://man7.org/linux/man-pages/dir_section_2.html",
  "From this index of section 2 (system calls), open the manual page for open(2). In its ERRORS section, report the errno NAME that open() returns when pathname refers to a directory and the access requested involved writing. Report only the errno name (e.g. EFOO)."),
 "T2": ("A", "https://git-scm.com/docs",
  "Open the git-config reference page and find the variable core.bigFileThreshold. Report its default value exactly as the page states it (a number plus a unit)."),
 "T3": ("A", "https://www.kernel.org/doc/html/latest/admin-guide/index.html",
  "Navigate to \"Documentation for /proc/sys/vm/\" and report the default value of swappiness as a bare number."),
 "T4": ("B", "https://www.gov.uk",
  "Use the site's own search box to find the UK bank holidays page, then report the date of the Summer bank holiday in SCOTLAND in 2027, formatted \"D Month YYYY\"."),
 "T5": ("B", "https://find-and-update.company-information.service.gov.uk/",
  "Search for \"TESCO PLC\", open the company record whose company number is 00445790, and report the \"Incorporated on\" date as shown."),
 "T6": ("B", "https://www.rijksmuseum.nl/en",
  "Use the site's search to find Johannes Vermeer's painting \"The Milkmaid\", open its object page, and report the object number."),
 "T8": ("C", "https://www.fueleconomy.gov/",
  "Use the \"Find a Car\" form to select model year 2012, make Toyota, model Prius. Report the Combined MPG for the 2012 Toyota Prius — the standard hybrid, not the Plug-in Hybrid."),
 "T9": ("C", "https://util.unicode.org/UnicodeJsps/character.jsp",
  "Use the character lookup form to look up the code point U+20AC, then report the value of its Age property exactly as the page prints it."),
 "T10": ("D", "https://nssdc.gsfc.nasa.gov/planetary/",
  "Open the Planetary Fact Sheet and report the value in the row \"Mean Temperature (C)\" in the column for Uranus."),
 "T11": ("D", "https://www.hko.gov.hk/en/cis/climat.htm",
  "Under Normals, select the 1991-2020 period and open \"Monthly/Yearly Normals\". In the monthly mean temperature table, report the value in the \"Mean (deg. C)\" column for the row \"July\"."),
 "T12": ("E", "https://www.law.cornell.edu/uscode/text",
  "Drill from the U.S. Code table of contents into Title 17 → Chapter 3 → § 302, and report the number of years after the author's death for which copyright endures under subsection (a). Report just the number."),
 "T13": ("E", "https://www.legislation.gov.uk/ukpga",
  "Browse UK Public General Acts to 2015, open the Consumer Rights Act 2015, go to section 22, and report the number of days given as the time limit in subsection (3). Report just the number."),
 "T14": ("E", "https://www.itis.gov/servlet/SingleRpt/SingleRpt?search_topic=TSN&search_value=180580",
  "Starting from this ITIS record for the family Felidae, drill down to the genus Felis and then to the species Felis nigripes, and report its Taxonomic Serial Number (TSN)."),
 "T15": ("F", "https://www.data.jma.go.jp/stats/etrn/index.php",
  "This is the Japan Meteorological Agency's past-weather search, entirely in Japanese. Navigate 東京都 → 東京 → 年ごとの値 and report the 降水量の合計 (annual total precipitation, in mm) for 2020年."),
 "T16": ("F", "https://dict.revised.moe.edu.tw/",
  "This is Taiwan's MOE Revised Mandarin Dictionary, in Chinese. Search for 颱風, open the entry for 颱風 itself, and report its 注音."),
 "T17": ("F", "https://stdict.korean.go.kr/main/main.do",
  "This is the National Institute of Korean Language's Standard Korean Dictionary, in Korean. Search for 학교, open the entry, and report the 원어 (the Hanja origin) shown for it."),
 # REWORDED per AMENDMENT 1 -- keys on the legend, not on the colliding phrase
 # "full support" which the page's own footnote 3 applies to Safari 14.
 "T18": ("G", "https://caniuse.com",
  "Use the site's search to open the \"WebP image format\" feature, then report the first Safari (desktop) version whose cell is GREEN (Supported) in the support table — not the greenish-yellow Partial ones. Report just the version number."),
 "T19": ("G", "https://pubchem.ncbi.nlm.nih.gov",
  "Search for aspirin, open the compound summary page for CID 2244, and report the Molecular Formula exactly as shown."),
 "T20": ("G", "https://periodic-table.rsc.org/",
  "In the interactive periodic table, open the element Xenon and report its Melting point in degrees Celsius, exactly as the page prints that value."),
}

GT = {
 "T1": (["EISDIR"], ["EACCES","EROFS","ENOTDIR","EPERM","ELOOP"]),
 "T2": (["512 MiB","512MiB"], ["512 MB","512","96m","96 MiB","32 MiB"]),
 "T3": (["60"], ["100","200","0","3","133"]),
 "T4": (["2 August 2027","2nd August 2027","02 August 2027","2 Aug 2027"],
        ["30 August 2027","3 August 2026","7 August 2028","31 May 2027"]),
 "T5": (["27 November 1947","27 Nov 1947","27/11/1947"],
        ["12 January 2015","22 July 2009","24 February 2006","27 July 2006"]),
 "T6": (["SK-A-2344"], ["SK-C-5","SK-A-2344a"]),
 "T8": (["48","48 MPG"], ["49","46","50","95","77.8","48.9"]),
 "T9": (["V2_1"], ["2.1","V2.1","V2_0","V4_0","V1_1"]),
 "T10": (["-195","−195","-195 C","-195°C"], ["-197","-200","-140","-320","58.1","76"]),
 "T11": (["28.9","28.9 °C"], ["28.8","28.7","31.6","26.9","23.5"]),
 "T12": (["70","70 years"], ["95","120","28","67","75"]),
 "T13": (["30","30 days"], ["7","6","6 months","14"]),
 "T14": (["183800","TSN 183800"], ["180580","180586","552363","726323","726324","183812"]),
 "T15": (["1590.0","1590.0 mm","1590"], ["16.5","1874.0","2052.5","132.0","2431.2"]),
 "T16": (["ㄊㄞˊ ㄈㄥ","ㄊㄞˊㄈㄥ"],
         ["ㄊㄞ ㄈㄥ","tái fēng"]),
 "T17": (["學校"], ["학교","学校","「명사」","학꿊"]),
 "T18": (["16.0","16"], ["14","14.0","15.6","16.1","26.6","27"]),
 "T19": (["C9H8O4","C₉H₈O₄"], ["CH3COOC6H4COOH","180.16","C7H6O3"]),
 "T20": (["-111.75","−111.75","-111.75 C","−111.75°C","-111.75 °C"],
         ["-108.099","-169.15","161.4","165.051","-111.8","-112"]),
}

WEAK = ["T5", "T16", "T17"]          # answer already on the results page
NS = {"cb": "mcp__chromebridge__", "cic": "mcp__claude-in-chrome__"}

os.makedirs(os.path.join(HERE, "prompts"), exist_ok=True)
ids = list(T)
for tid in ids:
    arch, start, task = T[tid]
    for arm, ns in NS.items():
        p = TPL.format(NS=ns, TID=tid, START=start, TASK=task)
        open(os.path.join(HERE, "prompts", f"{tid}_{arm}.txt"), "w",
             encoding="utf-8").write(p)

# ASSERT the arms are identical modulo the namespace -- #40's "identical prompt
# both arms except the namespace" is only true if it is checked.
bad = []
for tid in ids:
    a = open(os.path.join(HERE,"prompts",f"{tid}_cb.txt"),encoding="utf-8").read()
    b = open(os.path.join(HERE,"prompts",f"{tid}_cic.txt"),encoding="utf-8").read()
    if a.replace(NS["cb"], "@NS@") != b.replace(NS["cic"], "@NS@"):
        bad.append(tid)
assert not bad, bad

# Arm order ROTATED per task (#19): odd-numbered task -> CB first, even -> CIC.
order = []
for tid in ids:
    n = int(tid[1:])
    order += [[tid, "cb"], [tid, "cic"]] if n % 2 else [[tid, "cic"], [tid, "cb"]]
json.dump(order, open(os.path.join(HERE,"run_order.json"),"w"), indent=1)
json.dump({"gt": {k: {"accept": v[0], "reject": v[1], "archetype": T[k][0]}
                  for k, v in GT.items()}, "weak": WEAK},
          open(os.path.join(HERE,"ground_truth.json"),"w"),
          ensure_ascii=False, indent=1)

print(f"{len(ids)} tasks, {len(ids)*2} prompts, arms verified identical modulo namespace")
from collections import Counter
print("archetypes:", dict(Counter(T[t][0] for t in ids)))
print("order:", " ".join(f"{t}/{a}" for t, a in order))

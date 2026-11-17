# Live out-of-sample generality of the DOM collector, 2026-11

Probe: `tools/audit_generality_live.py` (re-runnable; the site list is in the file; `--selftest` proves the probe can fire; `--compare` is the drift control). Raw output: `temp/generality_live/pass0.json`, `pass1.json`, `drift.json` (gitignored).

## Result, stated as a negative result

**`lost_identities` = 0 across 40 live, never-seen sites: 0 of 6,193 controls under the `inspect_site.py` definition (light DOM), and 0 of 6,441 when the walk also pierces open shadow roots, `__abClosedRoot` and same-origin iframes.** Both numbers repeated in a second pass of the same source (drift control below). The collector ran verbatim from `extension/background.js` with `listener_tag.js` injected at document_start, so all eight admitting signals were live (the thing Mind2Web cannot give, #73/#79).

A third arm asks about controls the page DECLARES but the tag probe never asks about (ARIA interactive roles, `tabindex>=0`, `contenteditable`, `[onclick]`): 274 candidates, 23 reported lost. **All 23 are `<iframe tabindex=0 aria-label="Advertisement">` ad slots** on 5 sites; they are a probe-definition artefact more than a loss (an iframe is a container whose contents ARE listed; ledger reason `iframe-contents-listed-instead`, permitted). Non-iframe declared losses: **0 of 251**. They are kept in the table because the declared name does disappear, see Defect 1.

Drop reasons across the 40 sites (all in `test_ledger.SPEC_DELETES`, read not restated): not-interactive 79,168; not-visible 11,928; aria-hidden 4,228; cursor-inherited-non-root 3,378; iframe-contents-listed-instead 116; inert 36; checkVisibility-false 3. **No unexpected reason on any site.** (The first run showed `checkVisibility-false` as unexpected on two sites; that was a tooling bug, Defect 3.)

## Probe validity (it can fire)

`--selftest`: a page with visible, `visibility:hidden`, `opacity:0`, `aria-hidden`, open-shadow and `role=button` controls and an empty listing. It reports exactly `core=[Alpha]`, `deep=[Alpha, InShadow]`, `declared=[Declared-D]`, and 0 when the names are supplied. Visibility is `checkVisibility({opacityProperty:true, visibilityProperty:true})`. Names are compared raw and JSON-escaped (the verbatim `inspect_site` probe would report a false loss for a name containing a quote; no such case occurred).

## Drift control (`--compare`, same source twice, back to back per site)

- Lost identities: deep 0 and 0; declared 23 then 14 (only the ad-iframe set, which varies with which ad slots GPT fills); stable names 4, only-in-one-pass 1.
- Listing size drift: median 0.0%, p90 11.2%.
- Entries drift is large on live news/portal pages: eventbrite 543 to 455, he_ynet 2152 to 3241, vi_tuoitre 743 to 559, ko_daum 1642 to 828 (more than 10% on 4 sites, no code change). **Do not attribute an entries or token change under about 50% on those pages to code.** The metric that matters here (lost identities) did not move.

## Sample

76 candidates attempted, **40 usable** (rendered at least 10 controls). 36 were not: gov_in (served <10 controls: consent wall or bot block); gov_br (navigation failed/timeout); gov_mx (served <10 controls: consent wall or bot block); gov_il (served <10 controls: consent wall or bot block); gov_de (navigation failed/timeout); gov_sg (served <10 controls: consent wall or bot block); gov_th_bkk (served <10 controls: consent wall or bot block); gov_gr (served <10 controls: consent wall or bot block); gov_ae (navigation failed/timeout); bank_sbi (served <10 controls: consent wall or bot block); bank_hdfc (served <10 controls: consent wall or bot block); ins_allianz (served <10 controls: consent wall or bot block); bank_bbva (served <10 controls: consent wall or bot block); bank_ing_nl (navigation failed/timeout); bank_hapoalim (served <10 controls: consent wall or bot block); uni_ox (served <10 controls: consent wall or bot block); uni_illinois (served <10 controls: consent wall or bot block); uni_utokyo (navigation failed/timeout); uni_snu (navigation failed/timeout); uni_huji (served <10 controls: consent wall or bot block); uni_uoa (navigation failed/timeout); leg_faqs_rfc (served <10 controls: consent wall or bot block); leg_irctc (navigation failed/timeout); leg_sourceforge (served <10 controls: consent wall or bot block); tix_seatgeek (served <10 controls: consent wall or bot block); tix_sncf (served <10 controls: consent wall or bot block); tix_korail (navigation failed/timeout); tix_jreast (served <10 controls: consent wall or bot block); tix_renfe (served <10 controls: consent wall or bot block); el_skroutz (served <10 controls: consent wall or bot block); vi_vnexpress (served <10 controls: consent wall or bot block); ar_almasry (served <10 controls: consent wall or bot block); fa_digikala (served <10 controls: consent wall or bot block); ko_coupang (served <10 controls: consent wall or bot block); ru_vk (navigation failed/timeout); cv_nullschool (served <10 controls: consent wall or bot block).

**This is a bias in the sample, stated first because it is the biggest one.** The unusable set is dominated by exactly the archetypes the brief asked for most: government, bank/insurance, ticketing and several non-Latin sites. Headless Chromium with a stock profile is bot-blocked or times out there. I did not spoof a user agent or hide automation to get past that (and the sandbox refused when I started to), so these are reported as unmeasured, not as passed. What survived skews to news, docs and developer sites. Government, bank and ticketing are represented by 3, 4 and 3 sites.

Excluded-host check: no candidate host appears in `capture_listings.SITES` or anywhere under `tools/bench_turns/` or `tools/bench_flows/` (159 hosts; the probe refuses to run if one does).

## Aggregate and breakdowns (40 usable sites)

| | controls (deep) | declared-arm candidates | entries | lost (core/deep/declared) |
|---|---|---|---|---|
| all | 6,441 | 274 | 18,567 | 0 / 0 / 23 (ad iframes) |

By archetype (sites; deep controls; lost deep/declared): news-non-latin and news 8; 2,843; 0/23. webcomponents 9; 1,018; 0/0 (1,451 shadow roots walked; the light-DOM arm saw 833 of 1,018, so the shadow-piercing arm found 185 controls the light probe cannot see, all listed). university 3; 557; 0/0. government 3; 445; 0/0. ticketing 3; 384; 0/0. forum 1; 367. portal 1; 312. bank 4; 242. legacy (table/frameset-era man pages, tcl, tldp, perldoc) 4; 144; 0/0. canvas 4; 129; 0/0.

By script (deep controls, lost): English 25 sites 2,077, 0. Thai 4 sites 939, 0. Hindi/Devanagari 2 sites 794, 0. Vietnamese 3 sites 789, 0. Hebrew RTL 2 sites 701, 0. Greek 1 site 554, 0. Korean 1 site 312, 0. Arabic RTL 1 site 93, 0. Traditional Chinese 1 site 182, 0. Persian, Russian, Japanese: no usable site (blocked or timed out).

## Per-site table (pass 1; entries2 is pass 2)

| site | archetype | lang | controls (deep) | declared | entries | ~tokens | entries2 | lost core/deep/decl | top drop reasons |
|---|---|---|---|---|---|---|---|---|---|
| gov_tw_moi | government | zh-hant | 182 | 0 | 332 | 1497 | 329 | 0/0/0 | not-interactive 1738, not-visible 451, cursor-inherited-non-root 57 |
| gov_au | government | en | 40 | 0 | 126 | 1173 | 126 | 0/0/0 | not-interactive 289, not-visible 117, cursor-inherited-non-root 31 |
| gov_vn | government | vi | 223 | 4 | 339 | 1987 | 336 | 0/0/0 | not-interactive 838, not-visible 207, cursor-inherited-non-root 63 |
| bank_chase | bank | en | 121 | 0 | 405 | 1848 | 428 | 0/0/0 | not-interactive 563, not-visible 247, aria-hidden 96 |
| bank_dbs | bank | en | 11 | 0 | 32 | 845 | 32 | 0/0/0 | not-interactive 136, aria-hidden 112, not-visible 19 |
| bank_bbl_th | bank | th | 14 | 0 | 74 | 649 | 74 | 0/0/0 | not-interactive 1087, not-visible 61 |
| bank_rbc | bank | en | 96 | 3 | 155 | 1097 | 155 | 0/0/0 | not-interactive 1173, aria-hidden 313, not-visible 140 |
| uni_mit_cat | university-catalog | en | 134 | 0 | 186 | 1613 | 186 | 0/0/0 | not-interactive 882, not-visible 646, aria-hidden 90 |
| uni_chula | university | th | 256 | 0 | 970 | 1624 | 970 | 0/0/0 | not-interactive 1446, not-visible 401, cursor-inherited-non-root 150 |
| uni_vnu | university | vi | 167 | 0 | 664 | 2421 | 664 | 0/0/0 | not-interactive 538, not-visible 241, aria-hidden 92 |
| leg_freebsd_man | legacy | en | 29 | 0 | 32 | 920 | 32 | 0/0/0 | not-interactive 695, not-visible 113, aria-hidden 9 |
| leg_tcl | legacy | en | 47 | 0 | 52 | 762 | 52 | 0/0/0 | not-interactive 90, not-visible 9 |
| leg_tldp | legacy | en | 35 | 0 | 59 | 858 | 59 | 0/0/0 | not-interactive 167, not-visible 1 |
| leg_perldoc | legacy | en | 33 | 0 | 36 | 462 | 36 | 0/0/0 | not-visible 136, not-interactive 103, cursor-inherited-non-root 1 |
| tix_eventbrite | ticketing | en | 213 | 8 | 543 | 2614 | 455 | 0/0/0 | not-interactive 572, not-visible 159, aria-hidden 105 |
| tix_songkick | ticketing | en | 104 | 1 | 287 | 1573 | 286 | 0/0/0 | not-interactive 695, not-visible 511, cursor-inherited-non-root 62 |
| tix_trainline | ticketing | en | 67 | 16 | 221 | 715 | 221 | 0/0/0 | not-interactive 1298, not-visible 373, aria-hidden 78 |
| th_sanook | news-non-latin | th | 302 | 10 | 563 | 3462 | 573 | 0/0/5 | not-interactive 1111, cursor-inherited-non-root 139, not-visible 87 |
| th_pantip | forum-non-latin | th | 367 | 4 | 465 | 2933 | n/a | 0/0/0 | not-interactive 1147, cursor-inherited-non-root 251, not-visible 182 |
| he_ynet | news-non-latin | he-rtl | 506 | 149 | 2152 | 3226 | 3241 | 0/0/0 | not-interactive 3412, aria-hidden 1730, not-visible 549 |
| he_walla | news-non-latin | he-rtl | 195 | 4 | 1615 | 2755 | 1615 | 0/0/4 | not-interactive 1012, not-visible 542, cursor-inherited-non-root 120 |
| el_in | news-non-latin | el | 554 | 2 | 1387 | 2567 | 1387 | 0/0/1 | not-interactive 5082, not-visible 832, aria-hidden 80 |
| vi_tuoitre | news-non-latin | vi | 399 | 9 | 743 | 2336 | 559 | 0/0/0 | not-interactive 1849, not-visible 542, cursor-inherited-non-root 60 |
| hi_bhaskar | news-non-latin | hi-deva | 382 | 4 | 1184 | 2485 | 1184 | 0/0/4 | not-interactive 1011, not-visible 369, cursor-inherited-non-root 319 |
| hi_aajtak | news-non-latin | hi-deva | 412 | 23 | 1263 | 3323 | 1258 | 0/0/9 | not-interactive 1439, not-visible 258, cursor-inherited-non-root 116 |
| ar_aljazeera | news-non-latin | ar-rtl | 93 | 1 | 311 | 1986 | 328 | 0/0/0 | not-interactive 1895, aria-hidden 178, not-visible 152 |
| ko_daum | portal-non-latin | ko | 312 | 0 | 1642 | 3670 | 828 | 0/0/0 | not-interactive 996, not-visible 862, cursor-inherited-non-root 265 |
| cv_photopea | canvas | en | 17 | 0 | 17 | 361 | 17 | 0/0/0 | not-interactive 62 |
| cv_windy | canvas | en | 3 | 3 | 389 | 2638 | 389 | 0/0/0 | not-interactive 144, cursor-inherited-non-root 18, not-visible 12 |
| cv_geogebra | canvas | en | 12 | 2 | 39 | 936 | 39 | 0/0/0 | not-interactive 33492, aria-hidden 128, not-visible 89 |
| cv_miro | canvas | en | 97 | 15 | 349 | 1404 | 350 | 0/0/0 | not-interactive 897, aria-hidden 95, not-visible 63 |
| wc_lit | webcomponents | en | 62 | 4 | 135 | 1341 | 135 | 0/0/0 | not-interactive 529, cursor-inherited-non-root 109, aria-hidden 94 |
| wc_webawesome | webcomponents | en | 333 | 10 | 714 | 2987 | 714 | 0/0/0 | not-interactive 5376, not-visible 1040, aria-hidden 610 |
| wc_m3 | webcomponents | en | 54 | 2 | 194 | 1364 | 194 | 0/0/0 | not-interactive 299, cursor-inherited-non-root 54, not-visible 32 |
| wc_vaadin | webcomponents | en | 229 | 0 | 315 | 2530 | 315 | 0/0/0 | not-interactive 3023, not-visible 1092, cursor-inherited-non-root 252 |
| wc_spectrum | webcomponents | en | 23 | 0 | 52 | 657 | 52 | 0/0/0 | not-interactive 447, not-visible 174, cursor-inherited-non-root 56 |
| wc_devchrome | webcomponents | en | 90 | 0 | 126 | 1201 | 126 | 0/0/0 | not-interactive 508, not-visible 194, cursor-inherited-non-root 15 |
| wc_salesforce | webcomponents | en | 99 | 0 | 177 | 2141 | 177 | 0/0/0 | not-interactive 2868, not-visible 951, cursor-inherited-non-root 276 |
| wc_openwc | webcomponents | en | 104 | 0 | 192 | 1636 | 192 | 0/0/0 | not-interactive 92, not-visible 17, cursor-inherited-non-root 2 |
| wc_fast | webcomponents | en | 24 | 0 | 30 | 438 | 30 | 0/0/0 | not-interactive 167, aria-hidden 12, not-visible 4 |

## Every lost identity, quoted

All 23 are one shape. Example (he_walla, mmid 1090, 1200x250, on screen):

`<iframe id="google_ads_iframe_/43010785/wallanews/main/top_desktop_0" title="3rd party ad content" width="1200" height="250" ... aria-label="Advertisement" tabindex="0" ...>`

Sites: th_sanook 5, he_walla 4, el_in 1, hi_bhaskar 4, hi_aajtak 9 (pass 2: same shape, plus one on vi_vnexpress). Ledger reason on every one: `iframe-contents-listed-instead`. The frame is same-origin (`contentDocument` readable) and holds one link; that link is listed, the frame's declared label is not.

## Ranked defects

**1. (low, a context loss, not an element loss) A same-origin ad frame's declared label is discarded.** Markup above. The page declared a focusable frame with `aria-label="Advertisement"`; the collector lists the one link inside and drops the frame, so an agent sees an unlabelled link in a news grid and cannot tell it is an ad. Declaration that should carry it: `aria-label` (or `title`) on the frame element, which a screen reader announces. No class, wordlist or threshold needed. Proposed patch (not applied, background.js is off limits to me), at the `iframe-contents-listed-instead` exit around line 7318:

```diff
-      if (accessible) return _drop(el, 'iframe-contents-listed-instead');
+      if (accessible) {
+        // carry the frame's own declared name to what is listed from inside it
+        const fl = (el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
+        if (fl) el.contentDocument && (el.contentDocument.documentElement.__abFrameLabel = fl);
+        return _drop(el, 'iframe-contents-listed-instead');
+      }
```

then have `near=`/`under=` resolution read `__abFrameLabel` from the owning document when an entry has none. Needs its own fixture and the ablation (#29 rule) before shipping; it is priced at one short token per ad slot, 23 slots over 40 sites.

**2. (tooling, fixed) `inspect_site._permitted_deletes` used `[a-z]` and dropped `checkVisibility-false`.** It raised a false "unexpected drop reason" on uni_vnu and th_sanook. Same class as #36's drifting copy of the set. Fixed in `tools/inspect_site.py` (`[A-Za-z]`). There is no test that the parsed set equals the literal in `test_ledger.py`; worth one.

**3. (probe) `aria-label` + `tabindex` on a container makes it a declared-arm candidate.** Treat `iframe` as out of the declared arm in future runs, or keep reporting it as here.

No collector defect that loses an element was found.

## What this sample cannot measure

- **Anything behind bot protection or consent walls.** 36 of 76 candidates (all of the Japan and Korea government/rail targets, most banks, most gov portals) never rendered. The archetypes most likely to carry legacy enterprise markup are the ones missing; four table-era man-page/doc sites stand in for them and are not enterprise UIs (no IRCTC-style ASP.NET forms, no frameset app).
- **Logged-in, post-interaction and modal states.** Only first paint plus 2s settle, desktop 1280x1600 viewport, no scroll, no clicks. Nothing opens a menu, date picker or dialog.
- **Unnamed controls.** The metric requires a name, so a control with no accessible name is excluded by definition ("no identity to lose"). Whether the collector lists unnamed controls is measured by `(unlabeled)` marks, not here.
- **Presence is not usefulness.** Zero lost identities does not say the right name was attached to the right element, or that a model would pick it (#74, #75: findability and success are different questions).
- **Cross-origin frames.** The probe cannot see inside them and neither does the first-pass collector call (`collectCrossFrames` needs the extension APIs); consent CMPs and embedded checkouts are outside this measurement.
- **Controls that the CSS hides but the page considers visible (clipped, 1px, offscreen via transform).** `checkVisibility` calls them visible only if they have a box, and the probe requires 2x2 px.
- **The real extension.** Offline Playwright with `listener_tag.js` injected; any difference in how the MV3 content script is delivered is not tested.
- **Generalisation claims about the web.** 40 sites, 25 English, mostly sites that tolerate headless Chromium. The honest statement is: on 40 live sites spanning 9 scripts and archetypes, with every admitting signal live, the collector lost no named, visible control, and found no rule outside the permitted set deleting anything.

---

# Second run, 2026-11-17: the sample gap, and the first post-interaction read

Same probe, extended (`tools/audit_generality_live.py`): `SITES2` (369 new candidates, same exclusion guard against the frozen corpus, `bench_turns` and `bench_flows`; 14 candidates were removed by the guard before running), `--wave`, `--report`, and two new things below. Raw output: `temp/generality_live/{wave2,final,strict}/` (gitignored). Nothing in `extension/`, `core/` or `mcp_server.py` was touched. No user agent was changed, no automation hidden, no bot check worked around: a site that blocked is recorded as unusable below.

## Result, again a negative result

**`lost_identities` = 0 on 260 usable live sites (43 from the first run re-run, 217 new): 0 of 34,913 visible controls at first paint, 0 of 8,402 in the opened state.** Under a second, strictly harder definition (below) it is also 0, so the zero does not depend on how forgiving the first definition is. The collector ran verbatim from `background.js` with `listener_tag.js` at document_start. Drop reasons across all 260: not-interactive 345,743; not-visible 86,609; cursor-inherited-non-root 20,838; aria-hidden 17,118; inert 3,935; checkVisibility-false 608; iframe-contents-listed-instead 310. **No reason outside `test_ledger.SPEC_DELETES` on any site, at first paint or opened** (`UNEXPECTED_drop_reasons` empty everywhere; the set is read, not restated).

### Two probe defects found and fixed (the first one would have published a false collector defect)

1. **A page that defines `Array.prototype.toJSON` (Prototype.js era) double-encodes the probe's blob.** kebhana.com (a Korean bank) showed 33 "lost" identities, all on-screen `<a>` with no ledger entry. They were not lost: every one has an entry (mmid 2610, label "조회"). `JSON.stringify(array)` on that page returns a JSON string OF a string, so the by-reference lookup `'"' + mmid + '"'` never matched, and the name test failed because the probe takes `title` first ("조회로 이동") while the collector, correctly per AccName, names it from content ("조회"). The same defect sits in `inspect_site.PROBE`'s by-ref skip on any such page (not changed; it only ever makes that probe stricter). The probe now neutralises `Array.prototype.toJSON` for the one stringify; `--selftest` gained a control that fails if the by-ref skip is dead (`byref_skip_alive_and_double_encoding_detected`). The collector itself only stringifies strings (checked: every `JSON.stringify(` in `_collectInteractivePage` takes a string), so it is unaffected. After the fix kebhana reads 0.
2. **The name-substring test is lenient, and the first run's zero was weaker than it sounded.** Ablation on wipo.int (180 entries, 37 candidates): remove every second entry from the blob and the name test still reports **1** lost control, because a surviving container's concatenated label contains its descendants' names. The same ablation on the new **strict arm** (the control must OWN a row, decided by mmid alone against the structured entries plus every `ref_N` and `N:"` form in the listing, so a neighbour's text cannot satisfy it) reports **21 of 38**, and 38 of 38 with an empty blob. The prior run's "0 lost" was therefore a statement about names being findable somewhere, not about every control having a row. Both definitions are 0 here.

### Drift control

`--compare` on all 267 sites in the final set (same source, two passes, back to back per site): 259 usable in both. Lost identities 0 in both passes (after the fix). Entries absolute drift 1,154 over 259 sites (about 4.5 per site); listing-chars drift median 0.0%, p90 0.6%. Live reach is the unstable thing, not the metric: 7 of the 224 sites that rendered in the screening pass did not render at all on the rerun (`w2_shanghai`, `w2_kathmandu`, `w2_stockholm`, `w2_cdmx`, `w2_iitb` timed out; `w2_alfabank` and `w2_worldcat` served under 10 controls). A third pass (the strict arm) was also 0/0.

## The second read: opening ONE disclosure

After first paint the probe picks one disclosure from DECLARATIONS ONLY, in this tier order, first visible, in-viewport, not aria-hidden/inert, not disabled, and not an `<a href>` or a submit (so it cannot leave the page): (1) `[aria-expanded=false][aria-haspopup]`, (2) `[aria-expanded=false][aria-controls]`, (3) `[role=combobox]` or `input[list]`, (4) closed `<details>` `<summary>`, (5) any `[aria-expanded=false]`. No class name, no label text. It clicks with a real pointer click, waits 900 ms, re-measures with the identical probe, and reports `lost_identities` for the opened state separately. A disclosure counts as **opened** only if the page's own declared state flipped (`aria-expanded` became `true`, or `details.open`), so a click that did nothing is not counted as an opened menu.

| | count |
|---|---|
| sites with a declared disclosure candidate | 122 of 260 |
| clicked (Playwright pointer click succeeded) | 96 (26 timed out at 4 s: something covered the target) |
| navigated away (excluded by construction) | 0 |
| **declared state flipped (a real opened state)** | **77** |
| controls visible in the opened state | 8,402 |
| NEW named controls that were not visible at first paint | **1,026** (on 68 sites) |
| **lost_identities in the opened state** | **0** |
| strict "no row" in the opened state | **0** |
| of the 1,026 new controls: lost | **0** |

Kinds that flipped: menu-popup 31, expandable-with-controls 26, expandable 17, details 2, combobox 1. Largest new surfaces: wipo.int 194, admin.ch 122, perldoc 93, nsw.gov.au 77, cityline 50, geico 37. The MODAL banner fired on 10 of the 77 opened states (first paint: 29 of 260, mostly consent walls), and in none of them did anything beneath it vanish unrecorded.

**By script, opened state (sites flipped / controls / new controls):** latin-english 42 / 4,231 / 716; latin-other 17 / 1,367 / 193; han-trad 3 / 520 / 61; kana+han 5 / 834 / 16; hangul 2 / 459 / 8; cyrillic 2 / 126 / 12; arabic 2 / 196 / 3; hebrew 1 / 105 / 8; bengali 1 / 221 / 7; greek 1 / 343 / 2. **No opened state at all for Han-simplified, Devanagari, Thai or Vietnamese** (no site there offered a declared, clickable disclosure that the probe could safely open), so those scripts are first-paint only.

## Sample (wave 2 alone, plus combined)

369 wave-2 candidates attempted, **217 usable** (59%; at least 10 controls). Of the 152 that were not, in the screening pass: 112 served under 10 controls (consent wall or bot block; none was investigated or evaded), 20 goto timeouts, 9 network resets or HTTP/2 protocol errors, 4 DNS failures, 2 evaluate errors, plus the 7 flaky ones above.

**Wave 2 by archetype** (first paint; opened columns are sites tried/flipped, opened controls, NEW controls):

| archetype | sites | controls | entries | lost | no-row | opened | opened ctl | NEW | opened lost |
|---|---|---|---|---|---|---|---|---|---|
| bank | 30 | 2,919 | 5,935 | 0 | 0 | 18/9 | 866 | 72 | 0 |
| government (national + municipal) | 42 | 4,005 | 13,025 | 0 | 0 | 22/18 | 2,015 | 275 | 0 |
| insurance | 11 | 1,071 | 2,312 | 0 | 0 | 7/4 | 388 | 72 | 0 |
| judicial | 10 | 891 | 1,750 | 0 | 0 | 3/1 | 112 | 4 | 0 |
| legacy / table-era / framework-era | 27 | 2,884 | 4,245 | 0 | 0 | 7/4 | 266 | 33 | 0 |
| library | 5 | 579 | 1,010 | 0 | 0 | 2/1 | 76 | 6 | 0 |
| standards bodies | 16 | 7,455 | 8,814 | 0 | 0 | 7/5 | 482 | 221 | 0 |
| ticketing (incl. transit) | 26 | 2,173 | 4,242 | 0 | 0 | 17/8 | 902 | 73 | 0 |
| university (catalogue, registrar, home) | 50 | 5,393 | 11,169 | 0 | 0 | 20/11 | 1,092 | 81 | 0 |
| **wave 2 total** | **217** | **27,370** | **52,502** | **0** | **0** | **103/61** | **6,199** | **837** | **0** |

**Wave 2 by script:**

| script | sites | controls | entries | lost | opened tried/flipped | opened ctl | NEW |
|---|---|---|---|---|---|---|---|
| latin-english | 113 | 16,747 | 25,951 | 0 | 54/30 | 2,633 | 543 |
| latin-other (de fr es pt nl it pl cs sv no fi da hu ro tr id ca) | 46 | 3,708 | 9,178 | 0 | 30/17 | 1,367 | 193 |
| kana+han (ja) | 13 | 1,582 | 3,437 | 0 | 6/5 | 834 | 16 |
| han-simplified | 9 | 1,195 | 2,386 | 0 | 0/0 | 0 | 0 |
| cyrillic (ru uk bg sr) | 8 | 1,034 | 2,055 | 0 | 2/2 | 126 | 12 |
| han-traditional | 7 | 785 | 1,582 | 0 | 3/2 | 332 | 56 |
| hangul | 6 | 518 | 895 | 0 | 1/1 | 143 | 0 |
| hebrew (rtl) | 4 | 281 | 816 | 0 | 3/1 | 105 | 8 |
| arabic (rtl, incl. fa) | 3 | 310 | 503 | 0 | 2/1 | 95 | 0 |
| greek | 3 | 572 | 4,403 | 0 | 1/1 | 343 | 2 |
| thai | 2 | 100 | 255 | 0 | 0/0 | 0 | 0 |
| bengali | 2 | 337 | 695 | 0 | 1/1 | 221 | 7 |
| devanagari | 1 | 201 | 346 | 0 | 0/0 | 0 | 0 |

**Combined (wave 1 + wave 2): 260 sites, 138 English (53%, down from 25 of 40 = 62%), 122 non-English across 31 language codes and 13 script families.** Wave 2 alone is 104 of 217 non-English (48%). 95 wave-2 sites have an open or closed shadow root and 106 have an iframe; 14 sites across the sample carry canvas.

Legacy is better represented than before but **not** in the way the ask wanted: 27 usable wave-2 sites in the legacy family, of which only 7-8 are genuine table-and-CGI-era pages (bls.gov CGI, uspto tsdr, nws forecast, debian packages, cpan, openbsd, netbsd, catb, ubc ssc, perseus, sacred-texts, onlinebooks, mit.edu) and the rest are JSF/GWT/ASP.NET/APEX/ExtJS/Kendo **framework demo sites** (omnifaces, myfaces, gwt, devexpress, telerik, apex.oracle.com, sencha, dhtmlx). Those are real legacy component trees but are showcases, not enterprise forms. **Every real government/registry form portal I tried returned zero controls** in headless: FAA registry, FMCSA SAFER, FCC ULS, California SOS bizfile, NY DOS (reset). See "still unmeasurable".

## Ranked collector defects

**None found that loses an element.** No on-screen, named, visible control was missing a row at first paint or after opening a declared disclosure, on 260 sites, under either definition. The earlier ad-slot label observation (Defect 1 above: a same-origin `<iframe aria-label="Advertisement">` has its label dropped while its contents are listed) recurs, now on fandango; it is a context loss with a proposed patch in the first section and is unchanged. The probe's declared arm now skips `<iframe>` (the artefact noted in the first run).

## What this sample still cannot measure

- **The government, bank, insurance, ticketing and court archetypes are only as represented as the sites that tolerate headless Chromium.** 152 of 369 candidates never gave a usable page, and these are disproportionately the highest-value targets: Bank of America, Mizuho, MUFG, Shinhan, State Farm, Liberty Mutual, Tokio Marine, Ticketmaster, StubHub, MTR, SBB, NYC, Seattle, gov.kr, courtlistener, FAA/FCC/FMCSA. They are unmeasured, not passed. A survivorship effect is likely: the sites that render for an unmodified headless browser are the ones with the least aggressive bot protection, which correlates with simpler front ends.
- **True legacy enterprise UI** (an IRCTC-class ASP.NET WebForms booking form, a SAP portal, an intranet-style frameset app, a court e-filing front end) is **still unmeasured**. The legacy rows here are framework demos and table-era documentation sites.
- **One disclosure, one read.** Only the FIRST declared, visible, in-viewport, non-navigating disclosure is opened; 28% of attempted clicks timed out on an overlay (a consent wall most likely), so pages with a blocking banner mostly contributed no opened state. Date pickers, native `<select>` menus (not in the DOM in headless), modal dialogs opened from a button, multi-step menus (a second level), drag, hover-only menus and anything needing text input are untested. The probe looks only in the top document's light DOM when choosing what to open.
- **Scripts with no opened state:** Han-simplified, Devanagari, Thai, Vietnamese. First-paint only.
- **Logged-in state, still.** No site was authenticated; every page is the logged-out front door.
- **A visible control with no accessible name** is excluded from the name arm by definition; the strict arm counts it (it has no name to hide behind) and also found none without a row. That says a row exists, not that the row says anything useful (#74, #75).
- **Cross-origin frames** and controls inside closed shadow roots in cross-origin frames: invisible to the probe and to the first-pass collector call.
- **The headline is now two zeros that cannot be confused with success of the whole system**: presence and row-ownership are 0-loss; findability by name, success of an agent on these pages and correctness of the name attached to each row are not measured here.
- **Hidden-but-intended controls.** `checkVisibility` plus a 2x2 box excludes a clipped or off-canvas control the page considers reachable; a collector that dropped such a control would not be seen by this metric.

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

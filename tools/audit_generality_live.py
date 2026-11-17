"""Live, out-of-sample identity-loss probe for the DOM collector.

WHY THIS EXISTS. Every corpus number in this project comes from temp/frozen/, whose 106
sites ALL informed development (CLAUDE.md #16, #25: such a corpus shows absence of
regression, never generalisation). The one out-of-sample number, Mind2Web, is stripped
HTML with no scripts and no CSS, so two of the collector's eight admitting signals
(__abClickBound, cursor:pointer) cannot fire there (#73, #79: 59.7% of a live listing's
rows depend on them). This probe runs the REAL collector, extracted verbatim from
extension/background.js, over LIVE sites that are neither in SITES (capture_listings.py)
nor named in tools/bench_turns/ or tools/bench_flows/. listener_tag.js is injected at
document_start exactly as the extension does, so every signal is live.

METRIC. `lost_identities`: a RENDERED, genuinely-visible, not-declared-hidden control whose
name appears nowhere in the listing or the structured array. Visibility is
checkVisibility({opacityProperty:true, visibilityProperty:true}) -- a bare call reported
3.81% phantom loss in #36. Three arms, all from ONE page evaluation so run order cannot
align with the arm:
  core      inspect_site.PROBE, VERBATIM (light DOM; a[href],button,input,select,textarea,
            summary). Reused rather than re-written so the definition cannot fork.
  deep      the same tags, but walking open shadow roots, __abClosedRoot (#31) and
            same-origin iframes -- the light-DOM probe cannot see a Lit/Shoelace control.
  declared  controls the PAGE DECLARES but core never asks about: ARIA interactive roles,
            tabindex>=0, contenteditable, [onclick]. A loss here is a collector defect by
            construction, because the declaration was available.
The deep/declared arms also quote the name robustly (a name containing `"` is JSON-escaped
inside the blob, which makes the verbatim probe report a false loss).

PERMITTED DROP REASONS are READ from tools/test_ledger.py's SPEC_DELETES via
inspect_site._permitted_deletes -- never restated (#36 recorded a copy drifting).

DRIFT CONTROL. `--compare` runs the SAME source twice, back to back per site, and reports
how much of every number moves with the code held constant. Attribute nothing to a code
change until that floor is known (#16, #25).

Run:  python tools/audit_generality_live.py                  # one pass, writes JSON
      python tools/audit_generality_live.py --compare        # two passes + drift
      python tools/audit_generality_live.py --only NAME ...  # subset
      python tools/audit_generality_live.py --list
"""
import argparse
import asyncio
import collections
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from playwright.async_api import async_playwright  # noqa: E402
from _extract import extract as _extract_fn  # noqa: E402
import inspect_site as IS  # noqa: E402  (reuse PROBE + permitted set verbatim)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = _extract_fn("_collectInteractivePage", BG, verify=True)
TAG_JS = str(ROOT / "extension" / "listener_tag.js")
VIEWPORT = {"width": 1280, "height": 1600}
GOTO_MS = 45000
WAVE = 0   # 1 = wave-1 list, 2 = wave-2 list, 0 = both; set by --wave
PERMITTED = IS.PERMITTED
OUT = ROOT / "temp" / "generality_live"

# (name, url, archetype, language/script). THE SINGLE SOURCE OF TRUTH for the sample.
# A candidate is KEPT in the aggregate only if it rendered (>=3 DOM controls or entries);
# blocked/empty pages are listed separately, never silently dropped.
SITES = [
    # ---- government portals
    ("gov_in",      "https://www.india.gov.in/",                      "government", "en/hi"),
    ("gov_br",      "https://www.gov.br/pt-br",                       "government", "pt"),
    ("gov_mx",      "https://www.gob.mx/",                            "government", "es"),
    ("gov_il",      "https://www.gov.il/he/",                         "government", "he-rtl"),
    ("gov_de",      "https://www.bundesregierung.de/breg-de",         "government", "de"),
    ("gov_sg",      "https://www.gov.sg/",                            "government", "en"),
    ("gov_th_bkk",  "https://www.bangkok.go.th/",                     "government", "th"),
    ("gov_tw_moi",  "https://www.moi.gov.tw/",                        "government", "zh-hant"),
    ("gov_au",      "https://www.australia.gov.au/",                  "government", "en"),
    ("gov_gr",      "https://www.gov.gr/",                            "government", "el"),
    ("gov_vn",      "https://chinhphu.vn/",                           "government", "vi"),
    ("gov_ae",      "https://u.ae/ar-ae",                             "government", "ar-rtl"),
    # ---- bank / insurance, logged out
    ("bank_chase",  "https://www.chase.com/",                         "bank", "en"),
    ("bank_sbi",    "https://sbi.co.in/",                             "bank-legacy", "en"),
    ("bank_hdfc",   "https://www.hdfcbank.com/",                      "bank", "en"),
    ("bank_dbs",    "https://www.dbs.com.sg/index/default.page",      "bank", "en"),
    ("ins_allianz", "https://www.allianz.de/",                        "insurance", "de"),
    ("bank_bbva",   "https://www.bbva.es/",                           "bank", "es"),
    ("bank_ing_nl", "https://www.ing.nl/particulier/index.html",      "bank", "nl"),
    ("bank_bbl_th", "https://www.bangkokbank.com/th-TH/Personal",     "bank", "th"),
    ("bank_hapoalim","https://www.bankhapoalim.co.il/",               "bank", "he-rtl"),
    ("bank_rbc",    "https://www.rbcroyalbank.com/personal.html",     "bank", "en"),
    # ---- university catalogues / portals
    ("uni_mit_cat", "https://catalog.mit.edu/subjects/",              "university-catalog", "en"),
    ("uni_ox",      "https://www.ox.ac.uk/admissions/undergraduate/courses/course-listing", "university-catalog", "en"),
    ("uni_illinois","https://courses.illinois.edu/schedule/2026/fall","university-catalog", "en"),
    ("uni_utokyo",  "https://www.u-tokyo.ac.jp/ja/index.html",        "university", "ja"),
    ("uni_snu",     "https://www.snu.ac.kr/",                         "university", "ko"),
    ("uni_chula",   "https://www.chula.ac.th/",                       "university", "th"),
    ("uni_huji",    "https://www.huji.ac.il/",                        "university", "he-rtl"),
    ("uni_uoa",     "https://www.uoa.gr/",                            "university", "el"),
    ("uni_vnu",     "https://vnu.edu.vn/",                            "university", "vi"),
    # ---- legacy enterprise / table-and-frameset era
    ("leg_freebsd_man","https://man.freebsd.org/cgi/man.cgi",         "legacy", "en"),
    ("leg_tcl",     "https://www.tcl-lang.org/",                      "legacy", "en"),
    ("leg_tldp",    "https://tldp.org/",                              "legacy", "en"),
    ("leg_perldoc", "https://perldoc.perl.org/",                      "legacy", "en"),
    ("leg_faqs_rfc","http://www.faqs.org/rfcs/",                      "legacy-frameset", "en"),
    ("leg_irctc",   "https://www.irctc.co.in/nget/train-search",      "legacy-enterprise", "en"),
    ("leg_sourceforge","https://sourceforge.net/",                    "legacy", "en"),
    # ---- ticketing / travel
    ("tix_eventbrite","https://www.eventbrite.com/",                  "ticketing", "en"),
    ("tix_seatgeek","https://seatgeek.com/",                          "ticketing", "en"),
    ("tix_songkick","https://www.songkick.com/",                      "ticketing", "en"),
    ("tix_trainline","https://www.thetrainline.com/",                 "ticketing", "en"),
    ("tix_sncf",    "https://www.sncf-connect.com/en-en/",            "ticketing", "en"),
    ("tix_korail",  "https://www.letskorail.com/",                    "ticketing", "ko"),
    ("tix_jreast",  "https://www.jreast.co.jp/",                      "ticketing", "ja"),
    ("tix_renfe",   "https://www.renfe.com/es/es",                    "ticketing", "es"),
    # ---- non-English, non-major-brand consumer/news
    ("th_sanook",   "https://www.sanook.com/",                        "news-non-latin", "th"),
    ("th_pantip",   "https://pantip.com/",                            "forum-non-latin", "th"),
    ("he_ynet",     "https://www.ynet.co.il/",                        "news-non-latin", "he-rtl"),
    ("he_walla",    "https://www.walla.co.il/",                       "news-non-latin", "he-rtl"),
    ("el_skroutz",  "https://www.skroutz.gr/",                        "shop-non-latin", "el"),
    ("el_in",       "https://www.in.gr/",                             "news-non-latin", "el"),
    ("vi_vnexpress","https://vnexpress.net/",                         "news-non-latin", "vi"),
    ("vi_tuoitre",  "https://tuoitre.vn/",                            "news-non-latin", "vi"),
    ("hi_bhaskar",  "https://www.bhaskar.com/",                       "news-non-latin", "hi-deva"),
    ("hi_aajtak",   "https://www.aajtak.in/",                         "news-non-latin", "hi-deva"),
    ("ar_aljazeera","https://www.aljazeera.net/",                     "news-non-latin", "ar-rtl"),
    ("ar_almasry",  "https://www.almasryalyoum.com/",                 "news-non-latin", "ar-rtl"),
    ("fa_digikala", "https://www.digikala.com/",                      "shop-non-latin", "fa-rtl"),
    ("ko_daum",     "https://www.daum.net/",                          "portal-non-latin", "ko"),
    ("ko_coupang",  "https://www.coupang.com/",                       "shop-non-latin", "ko"),
    ("ru_vk",       "https://vk.com/",                                "social-non-latin", "ru"),
    # ---- heavy canvas
    ("cv_photopea", "https://www.photopea.com/",                      "canvas", "en"),
    ("cv_windy",    "https://www.windy.com/",                         "canvas", "en"),
    ("cv_geogebra", "https://www.geogebra.org/graphing",              "canvas", "en"),
    ("cv_nullschool","https://earth.nullschool.net/",                 "canvas", "en"),
    ("cv_miro",     "https://miro.com/",                              "canvas", "en"),
    # ---- Web Components / Lit / Shoelace / Polymer
    ("wc_lit",      "https://lit.dev/",                               "webcomponents", "en"),
    ("wc_webawesome","https://webawesome.com/docs/components/select/","webcomponents", "en"),
    ("wc_m3",       "https://m3.material.io/",                        "webcomponents", "en"),
    ("wc_vaadin",   "https://vaadin.com/docs/latest/components",      "webcomponents", "en"),
    ("wc_spectrum", "https://spectrum.adobe.com/",                    "webcomponents", "en"),
    ("wc_devchrome","https://developer.chrome.com/",                  "webcomponents", "en"),
    ("wc_salesforce","https://developer.salesforce.com/docs/component-library/overview/components", "webcomponents", "en"),
    ("wc_openwc",   "https://open-wc.org/",                           "webcomponents", "en"),
    ("wc_fast",     "https://www.fast.design/",                       "webcomponents", "en"),
]

# ---- WAVE 2 (2026-11-17): replacements for the 36 that never rendered + legacy enterprise,
# non-English and post-interaction coverage. Same exclusion guard as wave 1. A candidate that
# blocks or times out is RECORDED as unusable, never worked around (no UA spoofing, no
# automation hiding).
SITES2 = [
    # ---- legacy enterprise: JSF / GWT / ASP.NET WebForms / APEX / ExtJS / CGI-era government
    ('w2_primefaces', 'https://www.primefaces.org/showcase/', 'legacy-jsf', 'en'),
    ('w2_omnifaces', 'https://showcase.omnifaces.org/', 'legacy-jsf', 'en'),
    ('w2_myfaces', 'https://myfaces.apache.org/', 'legacy-jsf', 'en'),
    ('w2_gwt_showcase', 'http://samples.gwtproject.org/samples/Showcase/Showcase.html', 'legacy-gwt', 'en'),
    ('w2_gwt', 'https://www.gwtproject.org/', 'legacy-gwt', 'en'),
    ('w2_zk', 'https://www.zkoss.org/zkdemo/', 'legacy-zk', 'en'),
    ('w2_wicket', 'https://examples9x.wicket.apache.org/', 'legacy-wicket', 'en'),
    ('w2_dx_aspx', 'https://demos.devexpress.com/aspxperiment/', 'legacy-aspnet', 'en'),
    ('w2_telerik_aspnet', 'https://demos.telerik.com/aspnet-ajax', 'legacy-aspnet', 'en'),
    ('w2_aspnet', 'https://dotnet.microsoft.com/en-us/apps/aspnet', 'legacy-aspnet', 'en'),
    ('w2_apex', 'https://apex.oracle.com/en/', 'legacy-apex', 'en'),
    ('w2_extjs_ks', 'https://examples.sencha.com/extjs/7.0.0/examples/kitchensink/', 'legacy-extjs', 'en'),
    ('w2_kendo', 'https://demos.telerik.com/kendo-ui/', 'legacy-kendo', 'en'),
    ('w2_dhtmlx', 'https://dhtmlx.com/docs/products/demoApps/', 'legacy-kendo', 'en'),
    ('w2_faa_nnumber', 'https://registry.faa.gov/aircraftinquiry/Search/NNumberInquiry', 'legacy-gov-form', 'en'),
    ('w2_fmcsa_safer', 'https://safer.fmcsa.dot.gov/CompanySnapshot.aspx', 'legacy-gov-form', 'en'),
    ('w2_fcc_uls', 'https://wireless2.fcc.gov/UlsApp/UlsSearch/searchLicense.jsp', 'legacy-gov-form', 'en'),
    ('w2_bls_cgi', 'https://data.bls.gov/cgi-bin/surveymost', 'legacy-gov-form', 'en'),
    ('w2_ca_bizsearch', 'https://bizfileonline.sos.ca.gov/search/business', 'legacy-gov-form', 'en'),
    ('w2_ny_dos', 'https://apps.dos.ny.gov/publicInquiry/', 'legacy-gov-form', 'en'),
    ('w2_uspto_tsdr', 'https://tsdr.uspto.gov/', 'legacy-gov-form', 'en'),
    ('w2_ncbi_tax', 'https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi', 'legacy-gov-form', 'en'),
    ('w2_nws_forecast', 'https://forecast.weather.gov/', 'legacy-gov-form', 'en'),
    ('w2_deb_packages', 'https://packages.debian.org/', 'legacy-standards', 'en'),
    ('w2_cpan', 'https://www.cpan.org/', 'legacy', 'en'),
    ('w2_gnu', 'https://www.gnu.org/', 'legacy', 'en'),
    ('w2_openbsd', 'https://www.openbsd.org/', 'legacy', 'en'),
    ('w2_netbsd', 'https://www.netbsd.org/', 'legacy', 'en'),
    ('w2_austlii', 'http://www.austlii.edu.au/', 'legacy-judicial', 'en'),
    ('w2_bailii', 'https://www.bailii.org/', 'legacy-judicial', 'en'),
    ('w2_canlii', 'https://www.canlii.org/en/', 'judicial', 'en'),
    ('w2_onlinebooks', 'https://onlinebooks.library.upenn.edu/', 'legacy-library', 'en'),
    ('w2_catb', 'http://www.catb.org/~esr/faqs/smart-questions.html', 'legacy', 'en'),
    ('w2_mit_edu', 'https://www.mit.edu/', 'legacy', 'en'),
    ('w2_phpbb', 'https://www.phpbb.com/community/', 'legacy-forum', 'en'),
    ('w2_slashdot', 'https://slashdot.org/', 'legacy-forum', 'en'),
    ('w2_metafilter', 'https://www.metafilter.com/', 'legacy-forum', 'en'),
    ('w2_msu_sched', 'https://schedule.msu.edu/', 'legacy-registrar', 'en'),
    ('w2_ubc_ssc', 'https://courses.students.ubc.ca/cs/courseschedule?pname=subjarea', 'legacy-registrar', 'en'),
    ('w2_wustl_ugrad', 'https://courses.wustl.edu/', 'legacy-registrar', 'en'),
    # ---- government (municipal / national), many languages
    ('w2_nyc', 'https://www.nyc.gov/', 'government-municipal', 'en'),
    ('w2_sfgov', 'https://www.sf.gov/', 'government-municipal', 'en'),
    ('w2_chicago', 'https://www.chicago.gov/city/en.html', 'government-municipal', 'en'),
    ('w2_boston', 'https://www.boston.gov/', 'government-municipal', 'en'),
    ('w2_seattle', 'https://www.seattle.gov/', 'government-municipal', 'en'),
    ('w2_toronto', 'https://www.toronto.ca/', 'government-municipal', 'en'),
    ('w2_london', 'https://www.london.gov.uk/', 'government-municipal', 'en'),
    ('w2_berlin', 'https://www.berlin.de/', 'government-municipal', 'de'),
    ('w2_paris', 'https://www.paris.fr/', 'government-municipal', 'fr'),
    ('w2_amsterdam', 'https://www.amsterdam.nl/', 'government-municipal', 'nl'),
    ('w2_madrid', 'https://www.madrid.es/', 'government-municipal', 'es'),
    ('w2_milano', 'https://www.comune.milano.it/', 'government-municipal', 'it'),
    ('w2_tokyo_metro', 'https://www.metro.tokyo.lg.jp/', 'government-municipal', 'ja'),
    ('w2_yokohama', 'https://www.city.yokohama.lg.jp/', 'government-municipal', 'ja'),
    ('w2_osaka', 'https://www.city.osaka.lg.jp/', 'government-municipal', 'ja'),
    ('w2_seoul', 'https://www.seoul.go.kr/', 'government-municipal', 'ko'),
    ('w2_busan', 'https://www.busan.go.kr/', 'government-municipal', 'ko'),
    ('w2_hk_gov', 'https://www.gov.hk/tc/', 'government', 'zh-hant'),
    ('w2_taipei', 'https://www.gov.taipei/', 'government-municipal', 'zh-hant'),
    ('w2_shanghai', 'https://www.shanghai.gov.cn/', 'government-municipal', 'zh-hans'),
    ('w2_beijing', 'https://www.beijing.gov.cn/', 'government-municipal', 'zh-hans'),
    ('w2_moscow', 'https://www.mos.ru/', 'government-municipal', 'ru'),
    ('w2_spb', 'https://www.gov.spb.ru/', 'government-municipal', 'ru'),
    ('w2_istanbul', 'https://www.ibb.istanbul/', 'government-municipal', 'tr'),
    ('w2_turkiye', 'https://www.turkiye.gov.tr/', 'government', 'tr'),
    ('w2_cairo', 'https://www.egypt.gov.eg/', 'government', 'ar-rtl'),
    ('w2_dubai', 'https://www.dubai.ae/ar', 'government-municipal', 'ar-rtl'),
    ('w2_riyadh', 'https://www.my.gov.sa/', 'government', 'ar-rtl'),
    ('w2_tehran', 'https://www.tehran.ir/', 'government-municipal', 'fa-rtl'),
    ('w2_telaviv', 'https://www.tel-aviv.gov.il/', 'government-municipal', 'he-rtl'),
    ('w2_jerusalem', 'https://www.jerusalem.muni.il/', 'government-municipal', 'he-rtl'),
    ('w2_bangkok_gov', 'https://www.thaigov.go.th/', 'government', 'th'),
    ('w2_hanoi', 'https://hanoi.gov.vn/', 'government-municipal', 'vi'),
    ('w2_jakarta', 'https://www.jakarta.go.id/', 'government-municipal', 'id'),
    ('w2_manila', 'https://manila.gov.ph/', 'government-municipal', 'en'),
    ('w2_delhi', 'https://delhi.gov.in/', 'government-municipal', 'en'),
    ('w2_mumbai', 'https://portal.mcgm.gov.in/', 'government-municipal', 'en'),
    ('w2_kolkata', 'https://www.kmcgov.in/', 'government-municipal', 'en'),
    ('w2_chennai', 'https://chennaicorporation.gov.in/', 'government-municipal', 'en'),
    ('w2_kathmandu', 'https://kathmandu.gov.np/', 'government-municipal', 'ne-deva'),
    ('w2_dhaka', 'https://dscc.gov.bd/', 'government-municipal', 'bn'),
    ('w2_colombo', 'https://www.colombo.mc.gov.lk/', 'government-municipal', 'en'),
    ('w2_kyiv', 'https://kyivcity.gov.ua/', 'government-municipal', 'uk'),
    ('w2_warsaw', 'https://um.warszawa.pl/', 'government-municipal', 'pl'),
    ('w2_prague', 'https://www.praha.eu/', 'government-municipal', 'cs'),
    ('w2_budapest', 'https://www.budapest.hu/', 'government-municipal', 'hu'),
    ('w2_athens', 'https://www.cityofathens.gr/', 'government-municipal', 'el'),
    ('w2_sofia', 'https://www.sofia.bg/', 'government-municipal', 'bg'),
    ('w2_belgrade', 'https://www.beograd.rs/', 'government-municipal', 'sr'),
    ('w2_bucharest', 'https://www.pmb.ro/', 'government-municipal', 'ro'),
    ('w2_stockholm', 'https://start.stockholm/', 'government-municipal', 'sv'),
    ('w2_oslo', 'https://www.oslo.kommune.no/', 'government-municipal', 'no'),
    ('w2_helsinki', 'https://www.hel.fi/en', 'government-municipal', 'fi'),
    ('w2_copenhagen', 'https://www.kk.dk/', 'government-municipal', 'da'),
    ('w2_lisbon', 'https://www.lisboa.pt/', 'government-municipal', 'pt'),
    ('w2_saopaulo', 'https://www.capital.sp.gov.br/', 'government-municipal', 'pt'),
    ('w2_buenosaires', 'https://buenosaires.gob.ar/', 'government-municipal', 'es'),
    ('w2_bogota', 'https://bogota.gov.co/', 'government-municipal', 'es'),
    ('w2_lima', 'https://www.munlima.gob.pe/', 'government-municipal', 'es'),
    ('w2_santiago', 'https://www.munistgo.cl/', 'government-municipal', 'es'),
    ('w2_cdmx', 'https://www.cdmx.gob.mx/', 'government-municipal', 'es'),
    ('w2_nairobi', 'https://nairobi.go.ke/', 'government-municipal', 'en'),
    ('w2_lagos', 'https://lagosstate.gov.ng/', 'government-municipal', 'en'),
    ('w2_capetown', 'https://www.capetown.gov.za/', 'government-municipal', 'en'),
    ('w2_admin_ch', 'https://www.admin.ch/gov/de/start.html', 'government', 'de'),
    ('w2_oesterreich', 'https://www.oesterreich.gv.at/', 'government', 'de'),
    ('w2_gov_pl', 'https://www.gov.pl/', 'government', 'pl'),
    ('w2_gov_cz', 'https://www.gov.cz/', 'government', 'cs'),
    ('w2_japan_go', 'https://www.japan.go.jp/', 'government', 'ja'),
    ('w2_egov_jp', 'https://www.e-gov.go.jp/', 'government', 'ja'),
    ('w2_gov_kr', 'https://www.gov.kr/portal/main', 'government', 'ko'),
    ('w2_gov_cn', 'https://www.gov.cn/', 'government', 'zh-hans'),
    ('w2_indonesia', 'https://indonesia.go.id/', 'government', 'id'),
    ('w2_nsw', 'https://www.nsw.gov.au/', 'government', 'en'),
    ('w2_govt_nz', 'https://www.govt.nz/', 'government', 'en'),
    ('w2_argentina', 'https://www.argentina.gob.ar/', 'government', 'es'),
    ('w2_gob_cl', 'https://www.gob.cl/', 'government', 'es'),
    ('w2_gov_ro', 'https://www.gov.ro/', 'government', 'ro'),
    ('w2_gov_hu', 'https://magyarorszag.hu/', 'government', 'hu'),
    ('w2_gov_pt', 'https://www.portugal.gov.pt/', 'government', 'pt'),
    ('w2_gov_ua', 'https://www.kmu.gov.ua/', 'government', 'uk'),
    ('w2_gov_kz', 'https://www.gov.kz/', 'government', 'ru'),
    # ---- courts / judicial
    ('w2_supremecourt', 'https://www.supremecourt.gov/', 'judicial', 'en'),
    ('w2_uscourts', 'https://www.uscourts.gov/', 'judicial', 'en'),
    ('w2_courts_ca', 'https://www.courts.ca.gov/', 'judicial', 'en'),
    ('w2_courtlistener', 'https://www.courtlistener.com/', 'judicial', 'en'),
    ('w2_hudoc', 'https://hudoc.echr.coe.int/', 'judicial', 'en'),
    ('w2_curia', 'https://curia.europa.eu/jcms/jcms/j_6/en/', 'judicial', 'en'),
    ('w2_courts_jp', 'https://www.courts.go.jp/', 'judicial', 'ja'),
    ('w2_ukscourt', 'https://www.supremecourt.uk/', 'judicial', 'en'),
    ('w2_courts_il', 'https://www.court.gov.il/', 'judicial', 'he-rtl'),
    ('w2_courts_kr', 'https://www.scourt.go.kr/', 'judicial', 'ko'),
    ('w2_courts_tw', 'https://www.judicial.gov.tw/tw/mp-1.html', 'judicial', 'zh-hant'),
    ('w2_bgh', 'https://www.bundesgerichtshof.de/', 'judicial', 'de'),
    ('w2_cour_cass', 'https://www.courdecassation.fr/', 'judicial', 'fr'),
    ('w2_stf', 'https://portal.stf.jus.br/', 'judicial', 'pt'),
    ('w2_scjn', 'https://www.scjn.gob.mx/', 'judicial', 'es'),
    ('w2_hcourt_au', 'https://www.hcourt.gov.au/', 'judicial', 'en'),
    ('w2_scc', 'https://www.scc-csc.ca/', 'judicial', 'en'),
    # ---- transit / rail / ticketing
    ('w2_mta', 'https://new.mta.info/', 'ticketing-transit', 'en'),
    ('w2_bart', 'https://www.bart.gov/', 'ticketing-transit', 'en'),
    ('w2_wmata', 'https://www.wmata.com/', 'ticketing-transit', 'en'),
    ('w2_mbta', 'https://www.mbta.com/', 'ticketing-transit', 'en'),
    ('w2_tfl', 'https://tfl.gov.uk/', 'ticketing-transit', 'en'),
    ('w2_ratp', 'https://www.ratp.fr/', 'ticketing-transit', 'fr'),
    ('w2_sbb', 'https://www.sbb.ch/en', 'ticketing-transit', 'en'),
    ('w2_ns', 'https://www.ns.nl/en', 'ticketing-transit', 'en'),
    ('w2_oebb', 'https://www.oebb.at/en/', 'ticketing-transit', 'en'),
    ('w2_sj', 'https://www.sj.se/en', 'ticketing-transit', 'en'),
    ('w2_vr', 'https://www.vr.fi/en', 'ticketing-transit', 'en'),
    ('w2_trenitalia', 'https://www.trenitalia.com/en.html', 'ticketing-transit', 'en'),
    ('w2_cp', 'https://www.cp.pt/passageiros/en', 'ticketing-transit', 'en'),
    ('w2_mtr', 'https://www.mtr.com.hk/en/customer/main/index.html', 'ticketing-transit', 'en'),
    ('w2_taipei_metro', 'https://web.metro.taipei/e/', 'ticketing-transit', 'en'),
    ('w2_thsrc', 'https://www.thsrc.com.tw/en', 'ticketing-transit', 'en'),
    ('w2_tra_tw', 'https://www.railway.gov.tw/tra-tip-web/tip', 'ticketing-transit', 'zh-hant'),
    ('w2_srt_th', 'https://www.railway.co.th/', 'ticketing-transit', 'th'),
    ('w2_nationalrail', 'https://www.nationalrail.co.uk/', 'ticketing-transit', 'en'),
    ('w2_jr_west', 'https://www.westjr.co.jp/global/en/', 'ticketing-transit', 'en'),
    ('w2_jr_central', 'https://global.jr-central.co.jp/en/', 'ticketing-transit', 'en'),
    ('w2_tokyo_metro_line', 'https://www.tokyometro.jp/en/', 'ticketing-transit', 'en'),
    ('w2_seoul_metro', 'https://www.seoulmetro.co.kr/en/', 'ticketing-transit', 'en'),
    ('w2_ktx_en', 'https://www.letskorail.com/ebizbf/EbizbfForeign_pr16100.do', 'ticketing-transit', 'en'),
    ('w2_dsb', 'https://www.dsb.dk/en/', 'ticketing-transit', 'en'),
    ('w2_renfe_en', 'https://www.renfe.com/en/en', 'ticketing-transit', 'en'),
    ('w2_cfr', 'https://www.cfrcalatori.ro/en/', 'ticketing-transit', 'en'),
    ('w2_rzd', 'https://www.rzd.ru/', 'ticketing-transit', 'ru'),
    ('w2_ukrzaliz', 'https://www.uz.gov.ua/', 'ticketing-transit', 'uk'),
    ('w2_pkp', 'https://www.intercity.pl/en/', 'ticketing-transit', 'en'),
    ('w2_cd', 'https://www.cd.cz/en/', 'ticketing-transit', 'en'),
    ('w2_mav', 'https://www.mavcsoport.hu/en', 'ticketing-transit', 'en'),
    ('w2_egypt_rail', 'https://enr.gov.eg/', 'ticketing-transit', 'ar-rtl'),
    ('w2_tcdd', 'https://www.tcddtasimacilik.gov.tr/', 'ticketing-transit', 'tr'),
    ('w2_israel_rail', 'https://www.rail.co.il/', 'ticketing-transit', 'he-rtl'),
    ('w2_ticketmaster', 'https://www.ticketmaster.com/', 'ticketing', 'en'),
    ('w2_stubhub', 'https://www.stubhub.com/', 'ticketing', 'en'),
    ('w2_axs', 'https://www.axs.com/', 'ticketing', 'en'),
    ('w2_fandango', 'https://www.fandango.com/', 'ticketing', 'en'),
    ('w2_viagogo', 'https://www.viagogo.com/', 'ticketing', 'en'),
    ('w2_dice', 'https://dice.fm/', 'ticketing', 'en'),
    ('w2_eventim', 'https://www.eventim.de/', 'ticketing', 'de'),
    ('w2_ticketswap', 'https://www.ticketswap.com/', 'ticketing', 'en'),
    ('w2_bookmyshow', 'https://in.bookmyshow.com/', 'ticketing', 'en'),
    ('w2_tpia', 'https://t.pia.jp/', 'ticketing', 'ja'),
    ('w2_ltike', 'https://l-tike.com/', 'ticketing', 'ja'),
    ('w2_eplus', 'https://eplus.jp/', 'ticketing', 'ja'),
    ('w2_interpark', 'https://tickets.interpark.com/', 'ticketing', 'ko'),
    ('w2_ticketlink', 'https://www.ticketlink.co.kr/', 'ticketing', 'ko'),
    ('w2_kktix', 'https://kktix.com/', 'ticketing', 'zh-hant'),
    ('w2_cityline', 'https://www.cityline.com/', 'ticketing', 'zh-hant'),
    ('w2_biletix', 'https://www.biletix.com/', 'ticketing', 'tr'),
    ('w2_kassir', 'https://msk.kassir.ru/', 'ticketing', 'ru'),
    ('w2_ticketpro', 'https://www.ticketportal.cz/', 'ticketing', 'cs'),
    # ---- bank / insurance, logged out
    ('w2_geico', 'https://www.geico.com/', 'insurance', 'en'),
    ('w2_progressive', 'https://www.progressive.com/', 'insurance', 'en'),
    ('w2_statefarm', 'https://www.statefarm.com/', 'insurance', 'en'),
    ('w2_allstate', 'https://www.allstate.com/', 'insurance', 'en'),
    ('w2_libertymutual', 'https://www.libertymutual.com/', 'insurance', 'en'),
    ('w2_nationwide', 'https://www.nationwide.com/', 'insurance', 'en'),
    ('w2_axa_fr', 'https://www.axa.fr/', 'insurance', 'fr'),
    ('w2_generali', 'https://www.generali.com/', 'insurance', 'en'),
    ('w2_aviva', 'https://www.aviva.co.uk/', 'insurance', 'en'),
    ('w2_directline', 'https://www.directline.com/', 'insurance', 'en'),
    ('w2_zurich', 'https://www.zurich.com/', 'insurance', 'en'),
    ('w2_tokiomarine', 'https://www.tokiomarine-nichido.co.jp/', 'insurance', 'ja'),
    ('w2_samsung_fire', 'https://www.samsungfire.com/', 'insurance', 'ko'),
    ('w2_pingan', 'https://www.pingan.com/', 'insurance', 'zh-hans'),
    ('w2_cathay_life', 'https://www.cathaylife.com.tw/', 'insurance', 'zh-hant'),
    ('w2_ingosstrakh', 'https://www.ingos.ru/', 'insurance', 'ru'),
    ('w2_wells', 'https://www.wellsfargo.com/', 'bank', 'en'),
    ('w2_boa', 'https://www.bankofamerica.com/', 'bank', 'en'),
    ('w2_citi', 'https://www.citi.com/', 'bank', 'en'),
    ('w2_usbank', 'https://www.usbank.com/', 'bank', 'en'),
    ('w2_capone', 'https://www.capitalone.com/', 'bank', 'en'),
    ('w2_barclays', 'https://www.barclays.co.uk/', 'bank', 'en'),
    ('w2_hsbc_uk', 'https://www.hsbc.co.uk/', 'bank', 'en'),
    ('w2_lloyds', 'https://www.lloydsbank.com/', 'bank', 'en'),
    ('w2_natwest', 'https://www.natwest.com/', 'bank', 'en'),
    ('w2_commbank', 'https://www.commbank.com.au/', 'bank', 'en'),
    ('w2_anz', 'https://www.anz.com.au/', 'bank', 'en'),
    ('w2_td', 'https://www.td.com/ca/en/personal-banking', 'bank', 'en'),
    ('w2_bmo', 'https://www.bmo.com/main/personal/', 'bank', 'en'),
    ('w2_mufg', 'https://www.bk.mufg.jp/', 'bank', 'ja'),
    ('w2_smbc', 'https://www.smbc.co.jp/', 'bank', 'ja'),
    ('w2_mizuho', 'https://www.mizuhobank.co.jp/', 'bank', 'ja'),
    ('w2_kbstar', 'https://www.kbstar.com/', 'bank', 'ko'),
    ('w2_shinhan', 'https://www.shinhan.com/', 'bank', 'ko'),
    ('w2_hana', 'https://www.kebhana.com/', 'bank', 'ko'),
    ('w2_icbc', 'https://www.icbc.com.cn/', 'bank', 'zh-hans'),
    ('w2_ccb', 'https://www.ccb.com/', 'bank', 'zh-hans'),
    ('w2_cathaybk', 'https://www.cathaybk.com.tw/', 'bank', 'zh-hant'),
    ('w2_sberbank', 'https://www.sberbank.ru/', 'bank', 'ru'),
    ('w2_tinkoff', 'https://www.tbank.ru/', 'bank', 'ru'),
    ('w2_alfabank', 'https://alfabank.ru/', 'bank', 'ru'),
    ('w2_isbank', 'https://www.isbank.com.tr/', 'bank', 'tr'),
    ('w2_garanti', 'https://www.garantibbva.com.tr/', 'bank', 'tr'),
    ('w2_alrajhi', 'https://www.alrajhibank.com.sa/', 'bank', 'ar-rtl'),
    ('w2_nbe', 'https://www.nbe.com.eg/', 'bank', 'ar-rtl'),
    ('w2_leumi', 'https://www.leumi.co.il/', 'bank', 'he-rtl'),
    ('w2_discount', 'https://www.discountbank.co.il/', 'bank', 'he-rtl'),
    ('w2_mellat', 'https://www.bankmellat.ir/', 'bank', 'fa-rtl'),
    ('w2_kasikorn', 'https://www.kasikornbank.com/th/', 'bank', 'th'),
    ('w2_scb_th', 'https://www.scb.co.th/th/personal-banking.html', 'bank', 'th'),
    ('w2_vietcombank', 'https://vietcombank.com.vn/', 'bank', 'vi'),
    ('w2_bca', 'https://www.bca.co.id/', 'bank', 'id'),
    ('w2_hdfc_life', 'https://www.hdfclife.com/', 'insurance', 'en'),
    ('w2_icici', 'https://www.icicibank.com/', 'bank', 'en'),
    ('w2_pko', 'https://www.pkobp.pl/', 'bank', 'pl'),
    ('w2_csob', 'https://www.csob.cz/', 'bank', 'cs'),
    ('w2_otp', 'https://www.otpbank.hu/', 'bank', 'hu'),
    ('w2_alpha_gr', 'https://www.alpha.gr/', 'bank', 'el'),
    ('w2_nbg', 'https://www.nbg.gr/el', 'bank', 'el'),
    ('w2_privatbank', 'https://privatbank.ua/', 'bank', 'uk'),
    ('w2_raiffeisen_at', 'https://www.raiffeisen.at/', 'bank', 'de'),
    ('w2_ubs', 'https://www.ubs.com/ch/de.html', 'bank', 'de'),
    ('w2_sparkasse', 'https://www.sparkasse.de/', 'bank', 'de'),
    ('w2_ing_de', 'https://www.ing.de/', 'bank', 'de'),
    ('w2_caixa', 'https://www.caixabank.es/', 'bank', 'es'),
    ('w2_bradesco', 'https://banco.bradesco/', 'bank', 'pt'),
    ('w2_itau', 'https://www.itau.com.br/', 'bank', 'pt'),
    ('w2_bancolombia', 'https://www.bancolombia.com/', 'bank', 'es'),
    ('w2_banorte', 'https://www.banorte.com/', 'bank', 'es'),
    # ---- university course catalogues / registrar / non-English universities
    ('w2_stanford_ec', 'https://explorecourses.stanford.edu/', 'university-catalog', 'en'),
    ('w2_berkeley_cls', 'https://classes.berkeley.edu/', 'university-catalog', 'en'),
    ('w2_cornell_cls', 'https://classes.cornell.edu/', 'university-catalog', 'en'),
    ('w2_upenn_cat', 'https://catalog.upenn.edu/', 'university-catalog', 'en'),
    ('w2_brown_bul', 'https://bulletin.brown.edu/', 'university-catalog', 'en'),
    ('w2_princeton_reg', 'https://registrar.princeton.edu/', 'university-registrar', 'en'),
    ('w2_ucla_reg', 'https://registrar.ucla.edu/', 'university-registrar', 'en'),
    ('w2_mit_reg', 'https://registrar.mit.edu/', 'university-registrar', 'en'),
    ('w2_osu_courses', 'https://courses.osu.edu/', 'university-catalog', 'en'),
    ('w2_unimelb_hb', 'https://handbook.unimelb.edu.au/', 'university-catalog', 'en'),
    ('w2_unsw_hb', 'https://www.handbook.unsw.edu.au/', 'university-catalog', 'en'),
    ('w2_toronto_acorn', 'https://www.utoronto.ca/', 'university', 'en'),
    ('w2_ntu_tw', 'https://www.ntu.edu.tw/', 'university', 'zh-hant'),
    ('w2_kyoto', 'https://www.kyoto-u.ac.jp/ja', 'university', 'ja'),
    ('w2_titech', 'https://www.titech.ac.jp/', 'university', 'ja'),
    ('w2_waseda', 'https://www.waseda.jp/top/', 'university', 'ja'),
    ('w2_keio', 'https://www.keio.ac.jp/ja/', 'university', 'ja'),
    ('w2_kaist', 'https://www.kaist.ac.kr/kr/', 'university', 'ko'),
    ('w2_yonsei', 'https://www.yonsei.ac.kr/sc/', 'university', 'ko'),
    ('w2_korea_u', 'https://www.korea.ac.kr/mbshome/mbs/university/index.do', 'university', 'ko'),
    ('w2_tsinghua', 'https://www.tsinghua.edu.cn/', 'university', 'zh-hans'),
    ('w2_pku', 'https://www.pku.edu.cn/', 'university', 'zh-hans'),
    ('w2_hku', 'https://www.hku.hk/', 'university', 'en'),
    ('w2_cuhk', 'https://www.cuhk.edu.hk/', 'university', 'en'),
    ('w2_msu_ru', 'https://www.msu.ru/', 'university', 'ru'),
    ('w2_spbu', 'https://spbu.ru/', 'university', 'ru'),
    ('w2_heidelberg', 'https://www.uni-heidelberg.de/de', 'university', 'de'),
    ('w2_tum', 'https://www.tum.de/', 'university', 'de'),
    ('w2_sorbonne', 'https://www.sorbonne-universite.fr/', 'university', 'fr'),
    ('w2_unibo', 'https://www.unibo.it/it', 'university', 'it'),
    ('w2_ub', 'https://www.ub.edu/web/ub/ca/', 'university', 'ca'),
    ('w2_ucm', 'https://www.ucm.es/', 'university', 'es'),
    ('w2_usp', 'https://www5.usp.br/', 'university', 'pt'),
    ('w2_unam', 'https://www.unam.mx/', 'university', 'es'),
    ('w2_uba', 'https://www.uba.ar/', 'university', 'es'),
    ('w2_uct', 'https://www.uct.ac.za/', 'university', 'en'),
    ('w2_cu_eg', 'https://cu.edu.eg/', 'university', 'ar-rtl'),
    ('w2_ut_ir', 'https://ut.ac.ir/', 'university', 'fa-rtl'),
    ('w2_metu', 'https://www.metu.edu.tr/', 'university', 'tr'),
    ('w2_itu_tr', 'https://www.itu.edu.tr/', 'university', 'tr'),
    ('w2_tau', 'https://www.tau.ac.il/', 'university', 'he-rtl'),
    ('w2_technion', 'https://www.technion.ac.il/', 'university', 'he-rtl'),
    ('w2_ku_th', 'https://www.ku.ac.th/', 'university', 'th'),
    ('w2_mahidol', 'https://mahidol.ac.th/', 'university', 'th'),
    ('w2_ui_id', 'https://www.ui.ac.id/', 'university', 'id'),
    ('w2_iitb', 'https://www.iitb.ac.in/', 'university', 'en'),
    ('w2_du_in', 'https://www.du.ac.in/', 'university', 'en'),
    ('w2_bhu', 'https://www.bhu.ac.in/', 'university', 'hi-deva'),
    ('w2_du_bd', 'https://www.du.ac.bd/', 'university', 'bn'),
    ('w2_kneu', 'https://www.knu.ua/', 'university', 'uk'),
    ('w2_uw_pl', 'https://www.uw.edu.pl/', 'university', 'pl'),
    ('w2_cuni', 'https://www.cuni.cz/', 'university', 'cs'),
    ('w2_elte', 'https://www.elte.hu/', 'university', 'hu'),
    ('w2_uoa_gr', 'https://en.uoa.gr/', 'university', 'el'),
    ('w2_uni_bg', 'https://www.uni-sofia.bg/', 'university', 'bg'),
    ('w2_ubb', 'https://www.ubbcluj.ro/', 'university', 'ro'),
    ('w2_su_se', 'https://www.su.se/', 'university', 'sv'),
    ('w2_uio', 'https://www.uio.no/', 'university', 'no'),
    ('w2_helsinki_u', 'https://www.helsinki.fi/', 'university', 'fi'),
    ('w2_ku_dk', 'https://www.ku.dk/', 'university', 'da'),
    ('w2_usyd', 'https://www.sydney.edu.au/', 'university', 'en'),
    ('w2_uonair', 'https://www.ac.ke/', 'university', 'en'),
    ('w2_ug_lib', 'https://www.ug.edu.gh/', 'university', 'en'),
    # ---- libraries / archives
    ('w2_loc_cat', 'https://catalog.loc.gov/', 'library', 'en'),
    ('w2_worldcat', 'https://search.worldcat.org/', 'library', 'en'),
    ('w2_hathitrust', 'https://catalog.hathitrust.org/', 'library', 'en'),
    ('w2_trove', 'https://trove.nla.gov.au/', 'library', 'en'),
    ('w2_bl', 'https://www.bl.uk/', 'library', 'en'),
    ('w2_gallica', 'https://gallica.bnf.fr/', 'library', 'fr'),
    ('w2_ndl_jp', 'https://www.ndl.go.jp/en/', 'library', 'en'),
    ('w2_nl_kr', 'https://www.nl.go.kr/', 'library', 'ko'),
    ('w2_nlb_sg', 'https://www.nlb.gov.sg/', 'library', 'en'),
    ('w2_dnb', 'https://www.dnb.de/', 'library', 'de'),
    ('w2_bne', 'https://www.bne.es/es', 'library', 'es'),
    ('w2_nlr_ru', 'https://www.nlr.ru/', 'library', 'ru'),
    ('w2_nli_il', 'https://www.nli.org.il/he', 'library', 'he-rtl'),
    ('w2_nlc_cn', 'https://www.nlc.cn/', 'library', 'zh-hans'),
    ('w2_europeana', 'https://www.europeana.eu/en', 'library', 'en'),
    ('w2_perseus', 'https://www.perseus.tufts.edu/hopper/', 'legacy-library', 'en'),
    ('w2_sacredtexts', 'https://sacred-texts.com/', 'legacy-library', 'en'),
    ('w2_ctext', 'https://ctext.org/', 'legacy-library', 'zh-hans'),
    ('w2_aozora', 'https://www.aozora.gr.jp/', 'legacy-library', 'ja'),
    ('w2_wikisource_ar', 'https://ar.wikisource.org/', 'library', 'ar-rtl'),
    ('w2_ccel', 'https://www.ccel.org/', 'legacy-library', 'en'),
    # ---- standards bodies / registries
    ('w2_ietf_dt', 'https://datatracker.ietf.org/', 'standards', 'en'),
    ('w2_iso', 'https://www.iso.org/home.html', 'standards', 'en'),
    ('w2_ecma', 'https://ecma-international.org/', 'standards', 'en'),
    ('w2_oasis', 'https://www.oasis-open.org/', 'standards', 'en'),
    ('w2_etsi', 'https://www.etsi.org/', 'standards', 'en'),
    ('w2_ieee_std', 'https://standards.ieee.org/', 'standards', 'en'),
    ('w2_itu', 'https://www.itu.int/en/Pages/default.aspx', 'standards', 'en'),
    ('w2_unicode', 'https://home.unicode.org/', 'standards', 'en'),
    ('w2_iana_proto', 'https://www.iana.org/protocols', 'standards', 'en'),
    ('w2_wipo', 'https://www.wipo.int/portal/en/index.html', 'standards', 'en'),
    ('w2_eurlex', 'https://eur-lex.europa.eu/homepage.html', 'standards', 'en'),
    ('w2_ecfr', 'https://www.ecfr.gov/', 'standards', 'en'),
    ('w2_codex', 'https://www.fao.org/fao-who-codexalimentarius/en/', 'standards', 'en'),
    ('w2_ansi', 'https://www.ansi.org/', 'standards', 'en'),
    ('w2_din', 'https://www.din.de/de', 'standards', 'de'),
    ('w2_afnor', 'https://www.afnor.org/', 'standards', 'fr'),
    ('w2_jisc', 'https://www.jisc.go.jp/', 'standards', 'ja'),
    ('w2_ksa_kats', 'https://www.kats.go.kr/', 'standards', 'ko'),
    ('w2_sac_cn', 'https://www.sac.gov.cn/', 'standards', 'zh-hans'),
    ('w2_gost', 'https://www.rst.gov.ru/', 'standards', 'ru'),
    ('w2_ssaa', 'https://www.standards.org.au/', 'standards', 'en'),
    ('w2_bsi', 'https://www.bsigroup.com/en-GB/', 'standards', 'en'),
    ('w2_ccsds', 'https://public.ccsds.org/', 'standards', 'en'),
]

# Hosts the sample must NOT contain: the frozen corpus, bench_turns, bench_flows.
def _excluded_hosts():
    def norm(h): return re.sub(r"^www\.", "", h.lower())
    hosts = set()
    src = (ROOT / "tools" / "capture_listings.py").read_text(encoding="utf-8")
    body = src[src.index("SITES = ["):src.index("\nOUT = ")]
    for u in re.findall(r'"(https?://[^"]+)"', body):
        hosts.add(norm(urlparse(u).netloc))
    for d in ("bench_turns", "bench_flows"):
        for f in (ROOT / "tools" / d).rglob("*"):
            if f.is_file() and f.suffix in (".md", ".json", ".py", ".tsv", ".txt", ".jsonl"):
                try:
                    t = f.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                for h in re.findall(r"https?://([a-zA-Z0-9.-]+)", t):
                    hosts.add(norm(h))
    return hosts


EXCLUDED = _excluded_hosts()


def _check_sample():
    bad = []
    for n, u, *_ in SITES + SITES2:
        h = re.sub(r"^www\.", "", urlparse(u).netloc.lower())
        if h in EXCLUDED:
            bad.append((n, h))
    names = [s[0] for s in SITES + SITES2]
    assert len(names) == len(set(names)), "duplicate site name"
    return bad


# Arms deep + declared. Composed walk: open shadow roots, __abClosedRoot (#31),
# same-origin iframes. Names are compared against BOTH the raw string and its JSON-escaped
# form, since the blob is JSON.stringify output.
PROBE2 = r"""
(function (LISTING, BLOB) {
  const CORE = 'a[href],button,input,select,textarea,summary';
  const DECL = '[role=button],[role=link],[role=menuitem],[role=menuitemcheckbox],[role=menuitemradio],'
    + '[role=tab],[role=checkbox],[role=radio],[role=switch],[role=option],[role=combobox],[role=textbox],'
    + '[role=searchbox],[role=slider],[role=spinbutton],[role=treeitem],[role=gridcell],'
    + '[tabindex]:not([tabindex^="-"]),[contenteditable=""],[contenteditable="true"],[onclick]';
  const res = { deep: {candidates: 0, lost: [], names: []}, declared: {candidates: 0, lost: []},
                strict: {candidates: 0, norow: [], norow_named: 0} };
  // STRICT arm (wave 2): does the control own a ROW, decided by mmid alone. The name-substring
  // test is LENIENT -- a container's concatenated label contains its descendants' names, so
  // halving a real blob moved lost from ~18 expected to 1 (see doc). This arm cannot be
  // satisfied by a neighbour's text.
  const rowIds = new Set();
  for (const m of BLOB.matchAll(/"mmid":\s*"([^"]+)"/g)) rowIds.add(m[1]);
  for (const m of LISTING.matchAll(/\bref_(\w+:?\w*)/g)) rowIds.add(m[1]);
  for (const m of LISTING.matchAll(/(?:^|[\s,(])(\d+):"/g)) rowIds.add(m[1]);
  const seen = new Set();
  let budget = 12000;
  function roots(root, acc, depth) {
    acc.push(root);
    if (depth > 6) return;
    let all; try { all = root.querySelectorAll('*'); } catch (e) { return; }
    for (const e of all) {
      const sr = e.shadowRoot || e.__abClosedRoot;
      if (sr) roots(sr, acc, depth + 1);
      if (e.tagName === 'IFRAME') { try { const d = e.contentDocument; if (d) roots(d, acc, depth + 1); } catch (x) {} }
    }
  }
  const R = []; roots(document, R, 0);
  function vis(el) {
    try {
      return el.checkVisibility
        ? el.checkVisibility({ visibilityProperty: true, opacityProperty: true, contentVisibilityAuto: true })
        : true;
    } catch (e) { return true; }
  }
  function hidden(el) {
    // aria-hidden / inert, crossing shadow hosts and same-origin frame elements
    let n = el;
    for (let i = 0; n && i < 200; i++) {
      if (n.nodeType === 1 && (n.getAttribute('aria-hidden') === 'true' || n.hasAttribute('inert'))) return true;
      if (n.nodeType === 9) { let f = null; try { f = n.defaultView && n.defaultView.frameElement; } catch (x) {} n = f; continue; }
      n = n.parentNode || n.host;
    }
    return false;
  }
  function nameOf(el) {
    let t = '';
    try { t = (el.innerText || el.textContent || '').trim(); } catch (e) {}
    return ((el.getAttribute('aria-label') || el.getAttribute('title') || t
      || el.getAttribute('placeholder') || el.getAttribute('value') || '') + '').replace(/\s+/g, ' ').trim();
  }
  function arm(key, sel, skipCore) {
    for (const root of R) {
      let list; try { list = root.querySelectorAll(sel); } catch (e) { continue; }
      for (const el of list) {
        if (--budget < 0) return;
        if (key === 'declared' && el.matches(CORE)) continue;   // core already asked
        if (key === 'declared' && el.tagName === 'IFRAME') continue;   // ad-slot artefact, #82 defect 3
        const id = key + (el.__abSeen = el.__abSeen || ++window.__abSeenN);
        let r; try { r = el.getBoundingClientRect(); } catch (e) { continue; }
        if (r.width < 2 || r.height < 2) continue;
        if (!vis(el)) continue;
        if (hidden(el)) continue;
        res[key].candidates++;
        const nm = nameOf(el);
        if (key === 'deep') {
          res.strict.candidates++;
          const mm0 = el.getAttribute('mmid');
          if (!(mm0 && rowIds.has(mm0))) {
            if (nm) res.strict.norow_named++;
            if (res.strict.norow.length < 40) res.strict.norow.push({ tag: el.tagName.toLowerCase(), name: nm.slice(0, 60), mmid: mm0,
              box: [Math.round(r.width), Math.round(r.height)], html: el.outerHTML.slice(0, 220) });
          }
        }
        if (!nm) continue;
        if (key === 'deep' && res.deep.names.length < 4000) res.deep.names.push(nm.slice(0, 60));
        const m = el.getAttribute('mmid');
        if (m && BLOB.indexOf('"' + m + '"') >= 0) continue;
        const esc = JSON.stringify(nm).slice(1, -1);
        if (BLOB.indexOf(nm) >= 0 || BLOB.indexOf(esc) >= 0 || LISTING.indexOf(nm) >= 0 || LISTING.indexOf(esc) >= 0) continue;
        res[key].lost.push({
          tag: el.tagName.toLowerCase(), role: el.getAttribute('role'), name: nm.slice(0, 80), mmid: m,
          box: [Math.round(r.width), Math.round(r.height)],
          offscreen: (r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth),
          inShadow: !!(el.getRootNode && el.getRootNode() !== document && el.getRootNode().host),
          inFrame: el.ownerDocument !== document,
          html: el.outerHTML.slice(0, 280),
        });
      }
    }
  }
  window.__abSeenN = 0;
  arm('deep', CORE);
  arm('declared', DECL);
  res.shadowRoots = R.length - 1;
  return res;
})
"""


OPEN_PICK = r"""
(function () {
  // Chooses ONE disclosure from what the page DECLARES (PRINCIPLES 1 and 4): ARIA
  // aria-expanded / aria-haspopup / aria-controls, role=combobox, <details>. No class
  // name, no label wordlist. Tags the element so Playwright can click it as a user would.
  function vis(el) { try { return el.checkVisibility({ visibilityProperty: true, opacityProperty: true }); } catch (e) { return false; } }
  function ok(el) {
    let r; try { r = el.getBoundingClientRect(); } catch (e) { return false; }
    if (r.width < 4 || r.height < 4 || !vis(el)) return false;
    if (r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) return false;
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
    for (let n = el, i = 0; n && i < 80; i++, n = n.parentElement)
      if (n.getAttribute('aria-hidden') === 'true' || n.hasAttribute('inert')) return false;
    return true;
  }
  function leaves(el) {   // would activating it navigate or submit? then it is not a disclosure
    if (el.tagName === 'A') { const h = (el.getAttribute('href') || '').trim(); if (h && !/^#|^javascript:/i.test(h)) return true; }
    if ((el.tagName === 'BUTTON' || el.tagName === 'INPUT') && el.type === 'submit' && el.form) return true;
    return false;
  }
  const tiers = [
    ['menu-popup', '[aria-expanded="false"][aria-haspopup]:not([aria-haspopup="false"])'],
    ['expandable-controls', '[aria-expanded="false"][aria-controls]'],
    ['combobox', '[role=combobox]:not([aria-expanded="true"]),input[list]'],
    ['details', 'details:not([open]) > summary'],
    ['expandable', '[aria-expanded="false"]'],
  ];
  for (const [kind, sel] of tiers) {
    let list; try { list = document.querySelectorAll(sel); } catch (e) { continue; }
    for (const el of list) {
      if (!ok(el) || leaves(el)) continue;
      el.setAttribute('data-ab-open-target', '1');
      return { kind: kind, tag: el.tagName.toLowerCase(), role: el.getAttribute('role'),
               name: ((el.getAttribute('aria-label') || el.innerText || '') + '').replace(/\s+/g, ' ').trim().slice(0, 60),
               candidates: list.length };
    }
  }
  return null;
})()
"""

OPEN_STATE = r"""
(function () {
  const el = document.querySelector('[data-ab-open-target]');
  if (!el) return { gone: true };
  const det = el.tagName === 'SUMMARY' ? el.parentElement : null;
  return { gone: false, expanded: el.getAttribute('aria-expanded'),
           detailsOpen: det ? det.open : null, url: location.href };
})()
"""


def _measure_js():
    # NOTE (wave 2): a page that defines Array.prototype.toJSON (Prototype.js era; kebhana.com)
    # makes JSON.stringify(array) return a JSON STRING OF A STRING, so every `"<mmid>"` lookup in
    # the blob silently misses. The probe neutralises it for the one stringify and restores it.
    # The collector itself only stringifies strings, so it is unaffected (checked).
    return ("(function(){ " + COLLECT + ";"
            " const listing = _collectInteractivePage(false, null, 'compact', false, false, 'tree');"
            " const ents = _collectInteractivePage(true, null, 'compact', false, false, 'tree');"
            " const led = _collectInteractivePage(true, null, 'compact', true);"
            " const _tj = Array.prototype.toJSON; try { delete Array.prototype.toJSON; } catch (e) {}"
            " const blob = (typeof ents === 'string') ? ents : JSON.stringify(ents);"
            " if (_tj) Array.prototype.toJSON = _tj;"
            " const core = (" + IS.PROBE.strip() + ")(String(listing), blob);"
            " const more = (" + PROBE2.strip() + ")(String(listing), blob);"
            " return {listing: String(listing), ents: ents, dropped: (led && led.dropped) || [],"
            "  core: core, more: more, title: document.title, url: location.href,"
            "  nframes: document.querySelectorAll('iframe,frame').length,"
            "  ncanvas: document.querySelectorAll('canvas').length}; })()")


def _summ(res):
    """Reduce one raw measurement to the numbers the report uses."""
    listing = res["listing"]
    ents = res["ents"] or []
    if isinstance(ents, str):          # structured mode returns a JSON STRING
        ents = json.loads(ents)
    drops = res["dropped"] or []
    reasons = collections.Counter((d.get("rule") or d.get("why") or "?") for d in drops)
    unexpected = {k: v for k, v in reasons.items() if k not in PERMITTED}
    why_by_mmid = {str(d.get("mmid")): (d.get("rule") or d.get("why")) for d in drops}
    lost = []
    for arm, items in (("core", res["core"]["lost"]), ("deep", res["more"]["deep"]["lost"]),
                       ("declared", res["more"]["declared"]["lost"])):
        for it in items:
            it = dict(it); it["arm"] = arm
            it["ledger"] = why_by_mmid.get(str(it.get("mmid")))
            lost.append(it)
    return {
        "listing_chars": len(listing), "listing_tokens_est": len(listing) // 4,
        "entries": len(ents), "ledger_drops": len(drops),
        "dom_core": res["core"]["candidates"],
        "dom_deep": res["more"]["deep"]["candidates"],
        "dom_declared": res["more"]["declared"]["candidates"],
        "shadow_roots": res["more"]["shadowRoots"],
        "frames": res["nframes"], "canvases": res["ncanvas"],
        "lost_core": len(res["core"]["lost"]),
        "strict_candidates": res["more"]["strict"]["candidates"],
        "strict_norow": len(res["more"]["strict"]["norow"]),
        "strict_norow_named": res["more"]["strict"]["norow_named"],
        "strict_examples": res["more"]["strict"]["norow"][:8],
        "lost_deep": len(res["more"]["deep"]["lost"]),
        "lost_declared": len(res["more"]["declared"]["lost"]),
        "modal_banner": "MODAL/DIALOG IS CURRENTLY OPEN" in listing,
        "lost": lost, "drop_reasons": dict(reasons.most_common()),
        "UNEXPECTED_drop_reasons": unexpected,
    }


async def one(browser, name, url, arch, lang, shot_dir):
    t0 = time.time()
    ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True,
                                    user_agent=None, locale="en-US")
    try:
        await ctx.add_init_script(path=TAG_JS)
        page = await ctx.new_page()
        status = None
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=GOTO_MS)
            status = resp.status if resp else None
        except Exception as e:
            return {"site": name, "url": url, "archetype": arch, "lang": lang,
                    "error": "goto: " + str(e)[:120]}
        try:
            await page.wait_for_load_state("networkidle", timeout=7000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)
        try:
            res = await page.evaluate(_measure_js())
        except Exception as e:
            return {"site": name, "url": url, "archetype": arch, "lang": lang,
                    "error": "evaluate: " + str(e)[:160], "status": status}
        shot = None
        if shot_dir:
            try:
                shot = str(Path(shot_dir) / f"{name}.png")
                await page.screenshot(path=shot, full_page=False)
            except Exception:
                shot = None
        out = {"site": name, "url": url, "final_url": res["url"], "title": res["title"][:80],
               "archetype": arch, "lang": lang, "status": status,
               "seconds": round(time.time() - t0, 1), "screenshot": shot}
        out.update(_summ(res))
        names1 = set(res["more"]["deep"].get("names") or [])

        # ---- second read: open ONE declared disclosure, then measure again ----
        op = {"attempted": False}
        try:
            pick = await page.evaluate(OPEN_PICK)
            if pick:
                op.update(attempted=True, **pick)
                url_before = page.url
                try:
                    await page.click("[data-ab-open-target]", timeout=4000)
                    op["clicked"] = True
                except Exception as e:
                    op["clicked"] = False; op["click_error"] = str(e).split("\n")[0][:100]
                if op.get("clicked"):
                    await page.wait_for_timeout(900)
                    if page.url.split("#")[0] != url_before.split("#")[0]:
                        op["navigated"] = True
                    else:
                        st = await page.evaluate(OPEN_STATE)
                        op["state"] = st
                        flipped = (not st.get("gone")) and (st.get("expanded") == "true" or st.get("detailsOpen") is True)
                        op["flipped"] = bool(flipped)
                        r2 = await page.evaluate(_measure_js())
                        s2 = _summ(r2)
                        names2 = set(r2["more"]["deep"].get("names") or [])
                        new = names2 - names1
                        lostnames = {l["name"] for l in s2["lost"] if l["arm"] == "deep"}
                        s2["new_named_controls"] = len(new)
                        s2["new_named_lost"] = len(new & lostnames)
                        s2["entries_delta"] = s2["entries"] - out["entries"]
                        op["measure"] = s2
                        if shot_dir:
                            try: await page.screenshot(path=str(Path(shot_dir) / f"{name}.open.png"), full_page=False)
                            except Exception: pass
        except Exception as e:
            op["error"] = str(e)[:160]
        out["open"] = op
        return out
    finally:
        await ctx.close()


def usable(r):
    # >=10: a 2-control page is a consent wall or bot block, not the site (gov_th_bkk,
    # uni_ox, ar_almasry each "loaded" with 2 controls on the first pass).
    # Bot-blocked sites are REPORTED as unusable; this probe deliberately does not spoof a
    # user agent or hide automation to get past them.
    return "error" not in r and (r["dom_core"] >= 10 or r["entries"] >= 10)


async def run_pass(only, conc, shot_dir):
    sem = asyncio.Semaphore(conc)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        async def go(s):
            async with sem:
                try:
                    return await asyncio.wait_for(one(browser, *s, shot_dir), 120)
                except Exception as e:
                    return {"site": s[0], "url": s[1], "archetype": s[2], "lang": s[3],
                            "error": "timeout/" + str(e)[:80]}
        pool = {1: SITES, 2: SITES2}.get(WAVE, SITES + SITES2)
        todo = [s for s in pool if not only or s[0] in only]
        out = await asyncio.gather(*(go(s) for s in todo))
        await browser.close()
    return out


def aggregate(rs):
    ok = [r for r in rs if usable(r)]
    a = {"sites_attempted": len(rs), "sites_usable": len(ok),
         "unusable": [{"site": r["site"], "why": r.get("error") or "empty/blocked (dom_core=%s entries=%s)" % (r.get("dom_core"), r.get("entries"))}
                      for r in rs if not usable(r)]}
    for k in ("dom_core", "dom_deep", "dom_declared", "entries", "lost_core", "lost_deep", "lost_declared"):
        a[k] = sum(r[k] for r in ok)
    a["sites_with_any_loss_deep_or_declared"] = sum(1 for r in ok if r["lost_deep"] or r["lost_declared"])
    a["sites_with_core_loss"] = sum(1 for r in ok if r["lost_core"])
    a["sites_with_unexpected_reason"] = [r["site"] for r in ok if r["UNEXPECTED_drop_reasons"]]
    a["identity_loss_rate_deep"] = round(a["lost_deep"] / max(1, a["dom_deep"]), 5)
    a["identity_loss_rate_declared"] = round(a["lost_declared"] / max(1, a["dom_declared"]), 5)
    by = collections.defaultdict(lambda: collections.Counter())
    for r in ok:
        k = r["archetype"].split("-")[0]
        c = by[k]
        c["sites"] += 1; c["dom_deep"] += r["dom_deep"]; c["dom_declared"] += r["dom_declared"]
        c["lost_deep"] += r["lost_deep"]; c["lost_declared"] += r["lost_declared"]; c["entries"] += r["entries"]
    a["by_archetype"] = {k: dict(v) for k, v in sorted(by.items())}
    return a


SCRIPT_OF = {
    "en": "latin-english", "de": "latin-other", "fr": "latin-other", "es": "latin-other", "pt": "latin-other",
    "nl": "latin-other", "it": "latin-other", "pl": "latin-other", "cs": "latin-other", "sv": "latin-other",
    "no": "latin-other", "fi": "latin-other", "da": "latin-other", "hu": "latin-other", "ro": "latin-other",
    "tr": "latin-other", "id": "latin-other", "ca": "latin-other", "vi": "vietnamese",
    "he-rtl": "hebrew", "ar-rtl": "arabic", "fa-rtl": "arabic(persian)", "th": "thai",
    "zh-hant": "han-trad", "zh-hans": "han-simp", "ja": "kana+han", "ko": "hangul",
    "ru": "cyrillic", "uk": "cyrillic", "bg": "cyrillic", "sr": "cyrillic", "el": "greek",
    "hi-deva": "devanagari", "ne-deva": "devanagari", "bn": "bengali", "en/hi": "latin-english",
}


def report(paths, nonenglish_only=False):
    """Markdown tables from one or more pass JSON files (wave 2 by default)."""
    rs = []
    for p in paths:
        rs += json.loads(Path(p).read_text(encoding="utf-8"))["sites"]
    ok = [r for r in rs if usable(r)]
    def fam(a):
        x = a.split("-")
        return x[0] if len(x) == 1 or x[0] not in ("legacy", "government", "ticketing", "university") else x[0] + "-" + x[1]
    def split_loss(r, key):
        # declared losses that are <iframe> are the known ad-slot artefact (#82 defect 1)
        return sum(1 for l in r["lost"] if l["arm"] == key and not (key == "declared" and l["tag"] == "iframe"))
    out = []
    out.append("usable %d of %d attempted" % (len(ok), len(rs)))
    def table(keyf, title):
        g = collections.defaultdict(lambda: collections.Counter())
        for r in ok:
            c = g[keyf(r)]
            c["sites"] += 1; c["controls"] += r["dom_deep"]; c["declared"] += r["dom_declared"]
            c["entries"] += r["entries"]
            c["lost_deep"] += r["lost_deep"]; c["lost_decl_noniframe"] += split_loss(r, "declared")
            c["lost_core"] += r["lost_core"]
            o = (r.get("open") or {}).get("measure")
            if (r.get("open") or {}).get("attempted"): c["open_attempted"] += 1
            if o and (r["open"].get("flipped")):
                c["open_flipped"] += 1; c["open_controls"] += o["dom_deep"]
                c["open_new_controls"] += o["new_named_controls"]; c["open_new_lost"] += o["new_named_lost"]
                c["open_lost_deep"] += o["lost_deep"]; c["open_lost_decl"] += sum(1 for l in o["lost"] if l["arm"] == "declared" and l["tag"] != "iframe")
        out.append("\n### " + title + "\n")
        out.append("| group | sites | controls | declared | entries | lost core/deep/decl(non-iframe) | opened: tried/flipped | opened-state controls | NEW named controls | NEW lost | lost deep/decl (opened) |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for k, c in sorted(g.items()):
            out.append("| %s | %d | %d | %d | %d | %d/%d/%d | %d/%d | %d | %d | %d | %d/%d |" % (
                k, c["sites"], c["controls"], c["declared"], c["entries"], c["lost_core"], c["lost_deep"],
                c["lost_decl_noniframe"], c["open_attempted"], c["open_flipped"], c["open_controls"],
                c["open_new_controls"], c["open_new_lost"], c["open_lost_deep"], c["open_lost_decl"]))
        t = sum(c["sites"] for c in g.values())
        out.append("| **total** | %d | %d | %d | %d | %d/%d/%d | %d/%d | %d | %d | %d | %d/%d |" % (
            t, *[sum(c[x] for c in g.values()) for x in ("controls", "declared", "entries", "lost_core", "lost_deep", "lost_decl_noniframe", "open_attempted", "open_flipped", "open_controls", "open_new_controls", "open_new_lost", "open_lost_deep", "open_lost_decl")]))
    table(lambda r: fam(r["archetype"]), "by archetype")
    table(lambda r: SCRIPT_OF.get(r["lang"], r["lang"]), "by script")
    out.append("\nunusable:")
    for r in rs:
        if not usable(r):
            out.append("- %s (%s, %s): %s" % (r["site"], r["archetype"], r["lang"], r.get("error") or "served <10 controls (dom_core=%s entries=%s)" % (r.get("dom_core"), r.get("entries"))))
    return "\n".join(out)


async def _selftest():
    """A probe that cannot fire is worth nothing (#21, #30). Feed it a page whose controls
    are visible, hidden by visibility/opacity/aria-hidden, in an open shadow root, and a
    role=button div -- with an EMPTY listing/blob. It must report exactly the visible ones
    and none of the hidden ones, in the right arms; then with the names supplied, zero."""
    html = ("<button>Alpha</button><button style='visibility:hidden'>Hidden-v</button>"
            "<button style='opacity:0'>Hidden-o</button><div aria-hidden='true'><button>Hidden-a</button></div>"
            "<div id=h></div><div role=button tabindex=0>Declared-D</div>"
            "<script>const r=document.getElementById('h').attachShadow({mode:'open'});"
            "r.innerHTML='<button>InShadow</button>';</script>")
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page()
        await pg.set_content(html)
        js = "(" + PROBE2.strip() + ")('', '[]')"
        r = await pg.evaluate(js)
        core = await pg.evaluate("(" + IS.PROBE.strip() + ")('', '[]')")
        r2 = await pg.evaluate("(" + PROBE2.strip() + ")('Alpha InShadow Declared-D', '[]')")
        # by-reference skip (wave 2 found it dead): a control whose mmid appears in the blob
        # as an entry is NOT lost even if its probe-name (title-first) matches nothing.
        await pg.set_content("<a href='#' mmid='7' title='go to Zed'>Zed</a>")
        byref_ok = await pg.evaluate("(" + PROBE2.strip() + ")('', '[{\"mmid\": \"7\", \"label\": \"Zed\"}]')")
        byref_dead = await pg.evaluate("(" + PROBE2.strip() + ")('', JSON.stringify(JSON.stringify([{mmid: '7'}])))")
        await b.close()
    byref_pass = (not byref_ok["deep"]["lost"]) and bool(byref_dead["deep"]["lost"])
    deep = sorted(x["name"] for x in r["deep"]["lost"])
    decl = sorted(x["name"] for x in r["declared"]["lost"])
    cor = sorted(x["name"] for x in core["lost"])
    ok = (deep == ["Alpha", "InShadow"] and decl == ["Declared-D"] and cor == ["Alpha"]
          and not r2["deep"]["lost"] and not r2["declared"]["lost"] and byref_pass)
    print("selftest", "PASS" if ok else "FAIL", {"core": cor, "deep": deep, "declared": decl,
          "with_names_supplied": [len(r2["deep"]["lost"]), len(r2["declared"]["lost"])],
          "byref_skip_alive_and_double_encoding_detected": byref_pass})
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--conc", type=int, default=4)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--report", nargs="+", help="print markdown tables from pass JSON file(s)")
    ap.add_argument("--wave", type=int, default=0, choices=(0, 1, 2))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    if a.selftest:
        return asyncio.run(_selftest())
    if a.report:
        print(report(a.report)); return 0
    global WAVE
    WAVE = a.wave
    bad = _check_sample()
    if bad:
        print("SAMPLE CONTAINS EXCLUDED HOSTS:", bad); return 2
    if a.list:
        for s in SITES + SITES2: print(*s, sep="\t")
        print(len(SITES) + len(SITES2), "candidates;", len(EXCLUDED), "excluded hosts checked"); return 0
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "shots").mkdir(exist_ok=True)
    runs = [asyncio.run(run_pass(a.only, a.conc, str(out / "shots")))]
    if a.compare:
        runs.append(asyncio.run(run_pass(a.only, a.conc, None)))
    for i, rs in enumerate(runs):
        (out / f"pass{i}.json").write_text(json.dumps(
            {"aggregate": aggregate(rs), "sites": rs}, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"pass {i}:", json.dumps(aggregate(rs), ensure_ascii=False)[:1500])
    if a.compare:
        A = {r["site"]: r for r in runs[0]}; B = {r["site"]: r for r in runs[1]}
        both = [n for n in A if n in B and usable(A[n]) and usable(B[n])]
        d = {"sites_compared": len(both), "entries_abs_diff": 0, "chars_rel_diff": [],
             "lost_names_stable": 0, "lost_names_only_one_pass": 0, "per_site": {}}
        for n in both:
            x, y = A[n], B[n]
            d["entries_abs_diff"] += abs(x["entries"] - y["entries"])
            d["chars_rel_diff"].append(abs(x["listing_chars"] - y["listing_chars"]) / max(1, x["listing_chars"]))
            nx = {(l["arm"] != "core", l["name"]) for l in x["lost"]}
            ny = {(l["arm"] != "core", l["name"]) for l in y["lost"]}
            d["lost_names_stable"] += len(nx & ny); d["lost_names_only_one_pass"] += len(nx ^ ny)
            d["per_site"][n] = {"entries": [x["entries"], y["entries"]],
                                "lost": [len(x["lost"]), len(y["lost"])]}
        rel = sorted(d.pop("chars_rel_diff"))
        d["listing_chars_rel_drift_median"] = round(rel[len(rel)//2], 4) if rel else None
        d["listing_chars_rel_drift_p90"] = round(rel[int(len(rel)*0.9)], 4) if rel else None
        (out / "drift.json").write_text(json.dumps(d, indent=1), encoding="utf-8")
        print("DRIFT:", json.dumps({k: v for k, v in d.items() if k != "per_site"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

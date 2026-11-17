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
    for n, u, *_ in SITES:
        h = re.sub(r"^www\.", "", urlparse(u).netloc.lower())
        if h in EXCLUDED:
            bad.append((n, h))
    names = [s[0] for s in SITES]
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
  const res = { deep: {candidates: 0, lost: []}, declared: {candidates: 0, lost: []} };
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
        const id = key + (el.__abSeen = el.__abSeen || ++window.__abSeenN);
        let r; try { r = el.getBoundingClientRect(); } catch (e) { continue; }
        if (r.width < 2 || r.height < 2) continue;
        if (!vis(el)) continue;
        if (hidden(el)) continue;
        res[key].candidates++;
        const nm = nameOf(el);
        if (!nm) continue;
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


async def one(browser, name, url, arch, lang, shot_dir):
    t0 = time.time()
    ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True,
                                    user_agent=None, locale="en-US")
    try:
        await ctx.add_init_script(path=TAG_JS)
        page = await ctx.new_page()
        status = None
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
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
            res = await page.evaluate(
                "(function(){ " + COLLECT + ";"
                " const listing = _collectInteractivePage(false, null, 'compact', false, false, 'tree');"
                " const ents = _collectInteractivePage(true, null, 'compact', false, false, 'tree');"
                " const led = _collectInteractivePage(true, null, 'compact', true);"
                " const blob = JSON.stringify(ents);"
                " const core = (" + IS.PROBE.strip() + ")(String(listing), blob);"
                " const more = (" + PROBE2.strip() + ")(String(listing), blob);"
                " return {listing: String(listing), ents: ents, dropped: (led && led.dropped) || [],"
                "  core: core, more: more, title: document.title, url: location.href,"
                "  nframes: document.querySelectorAll('iframe,frame').length,"
                "  ncanvas: document.querySelectorAll('canvas').length}; })()")
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
        listing = res["listing"]
        ents = res["ents"] or []
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
            "site": name, "url": url, "final_url": res["url"], "title": res["title"][:80],
            "archetype": arch, "lang": lang, "status": status,
            "seconds": round(time.time() - t0, 1),
            "listing_chars": len(listing), "listing_tokens_est": len(listing) // 4,
            "entries": len(ents), "ledger_drops": len(drops),
            "dom_core": res["core"]["candidates"],
            "dom_deep": res["more"]["deep"]["candidates"],
            "dom_declared": res["more"]["declared"]["candidates"],
            "shadow_roots": res["more"]["shadowRoots"],
            "frames": res["nframes"], "canvases": res["ncanvas"],
            "lost_core": len(res["core"]["lost"]),
            "lost_deep": len(res["more"]["deep"]["lost"]),
            "lost_declared": len(res["more"]["declared"]["lost"]),
            "lost": lost, "drop_reasons": dict(reasons.most_common()),
            "UNEXPECTED_drop_reasons": unexpected, "screenshot": shot,
        }
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
        todo = [s for s in SITES if not only or s[0] in only]
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
        await b.close()
    deep = sorted(x["name"] for x in r["deep"]["lost"])
    decl = sorted(x["name"] for x in r["declared"]["lost"])
    cor = sorted(x["name"] for x in core["lost"])
    ok = (deep == ["Alpha", "InShadow"] and decl == ["Declared-D"] and cor == ["Alpha"]
          and not r2["deep"]["lost"] and not r2["declared"]["lost"])
    print("selftest", "PASS" if ok else "FAIL", {"core": cor, "deep": deep, "declared": decl,
          "with_names_supplied": [len(r2["deep"]["lost"]), len(r2["declared"]["lost"])]})
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--conc", type=int, default=4)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    if a.selftest:
        return asyncio.run(_selftest())
    bad = _check_sample()
    if bad:
        print("SAMPLE CONTAINS EXCLUDED HOSTS:", bad); return 2
    if a.list:
        for s in SITES: print(*s, sep="\t")
        print(len(SITES), "candidates;", len(EXCLUDED), "excluded hosts checked"); return 0
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

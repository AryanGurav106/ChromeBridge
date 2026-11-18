# -*- coding: utf-8 -*-
"""HOW OFTEN does a cross-origin frame hold something the page-level scans
   cannot see? Measured on LIVE sites in a FRESH profile, where consent exists.

THE OPEN ITEM. `docs/OPEN.md` item 7: the MODAL banner, the dialog-text pass and
`section=dialog` all run before `collectCrossFrames`, which merely APPENDS rows.
So a consent sheet served from a CMP vendor's origin in an iframe raises no
banner, while the identical sheet served same-origin does. Nine constructed
fixtures already prove the CORRECTNESS gap. What is unknown is FREQUENCY, and
item 7 says exactly why the frozen corpus cannot answer it: **its HARs were
captured AFTER consent was given**, so 0 of 128 frames declare a page-level
trigger and that zero is verified real for that corpus and says nothing about
the web.

THE ONLY WAY TO ANSWER IT is a fresh profile on live sites, which is what this
is. `user_data_dir=""` makes Playwright mint a throwaway profile per launch, the
probe NEVER clicks accept, and the cookie jar is counted at startup and asserted
empty -- so every CMP that is going to appear, appears.

WHAT IS MEASURED, and the last one is the one the recommendation turns on:
  A  sites loaded (vs UNMEASURED -- blocked, timed out, refused by the gate)
  B  sites with >= 1 cross-origin frame
  C  sites where a cross-origin frame WOULD raise a page-level trigger if the
     scan could see it -- `dialogOpen`'s own rules, evaluated in the frame's own
     view (which is #78/MV4's correction: measure the rect in the view it came
     from)
  D  of C, how many are BLOCKING -- the frame's shell dominates the TOP viewport,
     covers its centre, is overlay-positioned, and wins the hit-test at the
     centre -- versus INCIDENTAL (a chat launcher or an ad slot that happens to
     carry role=dialog)
  E  the CONTROL: on the SAME loads, how many raise the banner TODAY

D IS NOT A GARNISH. If most would-be triggers are incidental, building the fix
makes the product WORSE -- the banner suppresses the rest of the page (#80
measured a drawer taking all 150 entry slots), so a spurious banner costs more
than a missing one. The split decides the direction, not just the size.

GEO IS THE THREAT TO THIS SAMPLE AND IT IS MEASURED, NOT ASSUMED. Consent sheets
are mostly geo-gated to the EEA/UK (and CPRA to California); this machine is
elsewhere. Spoofing geolocation would be exactly the bot-check evasion this
project refuses, so instead the probe reports the CONDITIONAL rate --
`cross-origin / (any consent sheet at all)` -- which is far less geo-dependent
than the absolute rate, because an IP decides WHETHER a CMP fires and the site's
VENDOR CHOICE decides whether it is an iframe. `--geo` prints the absolute
consent rate beside it so the reader can see how much the vantage point bounded
the run.

NO SPOOFING, NO EVASION: no user-agent override, no proxy, no `navigator`
patching, no cookie-banner clicking. A site that blocks the probe is UNMEASURED
and is counted and named as such -- never as a zero. Roughly 180 candidates are
already unreachable this way across this project's probes (#85); expect it.

THE GATE IS GRANTED, NOT BYPASSED, exactly as `run_flows` and
`audit_frames_live` do it: grants are written into the THROWAWAY profile's own
storage, on a bridge port outside the default 8765-8774 span, so the user's own
Chrome never sees this. `ALLOW_ALL_ORIGINS` is not touched.

COMPOSED, NOT FORKED (PRINCIPLES 17). The browser/bridge/extension/MCP rig is
`audit_frames_live.Rig` -- #94's harness, unmodified -- and the out-of-sample
guard is `audit_generality_live.EXCLUDED`, imported rather than restated.

    python tools/audit_cmp_frames.py --selftest   # prove the detector fires, both ways
    python tools/audit_cmp_frames.py --list       # the sample, and the guard firing
    python tools/audit_cmp_frames.py              # the measurement
    python tools/audit_cmp_frames.py --report     # re-aggregate what is on disk
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import audit_frames_live as AFL                        # noqa: E402  the rig
from audit_generality_live import EXCLUDED             # noqa: E402  the guard

# Outside the default span, outside run_flows' 8901 and outside
# audit_frames_live's 8913, so none of the three can be mistaken for another.
AFL.BRIDGE_PORT = 8915
AFL.RF.PORT = 8915

OUT = ROOT / "temp" / "cmp_frames"
JSONL = OUT / "sites.jsonl"

# How long a page gets to put its consent sheet up. FIXED for every site,
# including the ones that will show nothing, so a negative and a positive are
# given the same chance -- a per-site "wait until something appears" budget
# would hand every positive more time than every negative and manufacture the
# result (#19's interleaving rule, in the time dimension).
SETTLE_MS = 6000


# --------------------------------------------------------------------------
# The sample.
#
# Chosen for the SHAPE, not for the answer: heavy on EU/UK publishers because
# that is where iframe CMPs live, with e-commerce, travel, SaaS (chat-widget
# iframes -- the incidental-trigger risk), non-Latin and government/reference
# as the denominator. A list biased only toward sites that WOULD fire measures
# nothing; a list with no such sites measures nothing either.
# --------------------------------------------------------------------------
SITES = [
    # --- EU/UK news: where iframe CMPs (Sourcepoint, TrustArc, Funding Choices) live
    ("spiegel", "https://www.spiegel.de/", "eu_news"),
    ("welt", "https://www.welt.de/", "eu_news"),
    ("zeit", "https://www.zeit.de/", "eu_news"),
    ("faz", "https://www.faz.net/", "eu_news"),
    ("sueddeutsche", "https://www.sueddeutsche.de/", "eu_news"),
    ("handelsblatt", "https://www.handelsblatt.com/", "eu_news"),
    ("stern", "https://www.stern.de/", "eu_news"),
    ("focus_de", "https://www.focus.de/", "eu_news"),
    ("tagesschau", "https://www.tagesschau.de/", "eu_news"),
    ("derstandard", "https://www.derstandard.at/", "eu_news"),
    ("nzz", "https://www.nzz.ch/", "eu_news"),
    ("20min_ch", "https://www.20min.ch/", "eu_news"),
    ("lemonde", "https://www.lemonde.fr/", "eu_news"),
    ("lefigaro", "https://www.lefigaro.fr/", "eu_news"),
    ("liberation", "https://www.liberation.fr/", "eu_news"),
    ("lesechos", "https://www.lesechos.fr/", "eu_news"),
    ("ouestfrance", "https://www.ouest-france.fr/", "eu_news"),
    ("elpais", "https://elpais.com/", "eu_news"),
    ("elmundo", "https://www.elmundo.es/", "eu_news"),
    ("lavanguardia", "https://www.lavanguardia.com/", "eu_news"),
    ("corriere", "https://www.corriere.it/", "eu_news"),
    ("repubblica", "https://www.repubblica.it/", "eu_news"),
    ("ilsole24ore", "https://www.ilsole24ore.com/", "eu_news"),
    ("telegraaf", "https://www.telegraaf.nl/", "eu_news"),
    ("nu_nl", "https://www.nu.nl/", "eu_news"),
    ("nrc", "https://www.nrc.nl/", "eu_news"),
    ("vg_no", "https://www.vg.no/", "eu_news"),
    ("aftenposten", "https://www.aftenposten.no/", "eu_news"),
    ("dn_se", "https://www.dn.se/", "eu_news"),
    ("aftonbladet", "https://www.aftonbladet.se/", "eu_news"),
    ("hs_fi", "https://www.hs.fi/", "eu_news"),
    ("yle", "https://yle.fi/", "eu_news"),
    ("dr_dk", "https://www.dr.dk/", "eu_news"),
    ("politiken", "https://politiken.dk/", "eu_news"),
    ("irishtimes", "https://www.irishtimes.com/", "eu_news"),
    ("rte", "https://www.rte.ie/", "eu_news"),
    ("telegraph", "https://www.telegraph.co.uk/", "eu_news"),
    ("independent_uk", "https://www.independent.co.uk/", "eu_news"),
    ("standard_uk", "https://www.standard.co.uk/", "eu_news"),
    ("mirror_uk", "https://www.mirror.co.uk/", "eu_news"),
    ("dailymail", "https://www.dailymail.co.uk/", "eu_news"),
    ("skynews", "https://news.sky.com/", "eu_news"),
    ("metro_uk", "https://metro.co.uk/", "eu_news"),
    ("express_uk", "https://www.express.co.uk/", "eu_news"),
    ("ft", "https://www.ft.com/", "eu_news"),
    ("economist", "https://www.economist.com/", "eu_news"),
    ("euronews", "https://www.euronews.com/", "eu_news"),
    ("politico_eu", "https://www.politico.eu/", "eu_news"),

    # --- US news/media
    ("washingtonpost", "https://www.washingtonpost.com/", "us_news"),
    ("cnn", "https://www.cnn.com/", "us_news"),
    ("foxnews", "https://www.foxnews.com/", "us_news"),
    ("nbcnews", "https://www.nbcnews.com/", "us_news"),
    ("cbsnews", "https://www.cbsnews.com/", "us_news"),
    ("usatoday", "https://www.usatoday.com/", "us_news"),
    ("latimes", "https://www.latimes.com/", "us_news"),
    ("npr", "https://www.npr.org/", "us_news"),
    ("politico", "https://www.politico.com/", "us_news"),
    ("axios", "https://www.axios.com/", "us_news"),
    ("bloomberg", "https://www.bloomberg.com/", "us_news"),
    ("reuters", "https://www.reuters.com/", "us_news"),
    ("apnews", "https://apnews.com/", "us_news"),
    ("forbes", "https://www.forbes.com/", "us_news"),
    ("businessinsider", "https://www.businessinsider.com/", "us_news"),
    ("wired", "https://www.wired.com/", "us_news"),
    ("theverge", "https://www.theverge.com/", "us_news"),
    ("techcrunch", "https://techcrunch.com/", "us_news"),
    ("arstechnica", "https://arstechnica.com/", "us_news"),
    ("engadget", "https://www.engadget.com/", "us_news"),
    ("cnet", "https://www.cnet.com/", "us_news"),
    ("vox", "https://www.vox.com/", "us_news"),
    ("theatlantic", "https://www.theatlantic.com/", "us_news"),
    ("time", "https://time.com/", "us_news"),
    ("newsweek", "https://www.newsweek.com/", "us_news"),

    # --- e-commerce
    ("walmart", "https://www.walmart.com/", "shop"),
    ("target", "https://www.target.com/", "shop"),
    ("bestbuy", "https://www.bestbuy.com/", "shop"),
    ("etsy", "https://www.etsy.com/", "shop"),
    ("zalando", "https://www.zalando.de/", "shop"),
    ("asos", "https://www.asos.com/", "shop"),
    ("hm", "https://www2.hm.com/en_gb/index.html", "shop"),
    ("ikea", "https://www.ikea.com/gb/en/", "shop"),
    ("zara", "https://www.zara.com/uk/", "shop"),
    ("otto", "https://www.otto.de/", "shop"),
    ("mediamarkt", "https://www.mediamarkt.de/", "shop"),
    ("fnac", "https://www.fnac.com/", "shop"),
    ("bol", "https://www.bol.com/nl/nl/", "shop"),
    ("allegro", "https://allegro.pl/", "shop"),
    ("argos", "https://www.argos.co.uk/", "shop"),
    ("johnlewis", "https://www.johnlewis.com/", "shop"),

    # --- travel/booking
    ("expedia", "https://www.expedia.com/", "travel"),
    ("trivago", "https://www.trivago.com/", "travel"),
    ("skyscanner", "https://www.skyscanner.net/", "travel"),
    ("tripadvisor", "https://www.tripadvisor.com/", "travel"),
    ("lufthansa", "https://www.lufthansa.com/", "travel"),
    ("britishairways", "https://www.britishairways.com/", "travel"),
    ("easyjet", "https://www.easyjet.com/", "travel"),
    ("bahn", "https://www.bahn.de/", "travel"),
    ("nationalrail", "https://www.nationalrail.co.uk/", "travel"),
    ("trainline", "https://www.thetrainline.com/", "travel"),
    ("airbnb", "https://www.airbnb.com/", "travel"),

    # --- SaaS / marketing: the chat-widget iframe lives here (incidental risk)
    ("hubspot", "https://www.hubspot.com/", "saas"),
    ("salesforce", "https://www.salesforce.com/", "saas"),
    ("zendesk", "https://www.zendesk.com/", "saas"),
    ("intercom", "https://www.intercom.com/", "saas"),
    ("shopify", "https://www.shopify.com/", "saas"),
    ("atlassian", "https://www.atlassian.com/", "saas"),
    ("slack", "https://slack.com/", "saas"),
    ("zoom", "https://www.zoom.com/", "saas"),
    ("dropbox", "https://www.dropbox.com/", "saas"),
    ("asana", "https://asana.com/", "saas"),
    ("airtable", "https://www.airtable.com/", "saas"),
    ("figma", "https://www.figma.com/", "saas"),
    ("canva", "https://www.canva.com/", "saas"),
    ("drift", "https://www.salesloft.com/", "saas"),
    ("twilio", "https://www.twilio.com/", "saas"),

    # --- non-Latin
    ("nikkei", "https://www.nikkei.com/", "nonlatin"),
    ("asahi", "https://www.asahi.com/", "nonlatin"),
    ("yomiuri", "https://www.yomiuri.co.jp/", "nonlatin"),
    ("mainichi", "https://mainichi.jp/", "nonlatin"),
    ("chosun", "https://www.chosun.com/", "nonlatin"),
    ("joongang", "https://www.joongang.co.kr/", "nonlatin"),
    ("sina", "https://www.sina.com.cn/", "nonlatin"),
    ("qq", "https://www.qq.com/", "nonlatin"),
    ("lenta", "https://lenta.ru/", "nonlatin"),
    ("rbc_ru", "https://www.rbc.ru/", "nonlatin"),
    ("aljazeera_ar", "https://www.aljazeera.net/", "nonlatin"),
    ("alarabiya", "https://www.alarabiya.net/", "nonlatin"),
    ("ndtv", "https://www.ndtv.com/", "nonlatin"),
    ("thehindu", "https://www.thehindu.com/", "nonlatin"),

    # --- government / reference: the denominator, where CMPs should be rare
    ("nasa", "https://www.nasa.gov/", "gov_ref"),
    ("noaa", "https://www.noaa.gov/", "gov_ref"),
    ("cdc", "https://www.cdc.gov/", "gov_ref"),
    ("nih", "https://www.nih.gov/", "gov_ref"),
    ("europa", "https://european-union.europa.eu/index_en", "gov_ref"),
    ("who", "https://www.who.int/", "gov_ref"),
    ("un", "https://www.un.org/en/", "gov_ref"),
    ("oecd", "https://www.oecd.org/", "gov_ref"),
    ("imf", "https://www.imf.org/en/Home", "gov_ref"),
    ("worldbank", "https://www.worldbank.org/en/home", "gov_ref"),
    ("ecb", "https://www.ecb.europa.eu/home/html/index.en.html", "gov_ref"),
    ("eur_lex", "https://eur-lex.europa.eu/homepage.html", "gov_ref"),
]

# WAVE 2, and the reason it exists is PRINCIPLES 9: an ablation measures the
# code against the sample and cannot measure the sample. Wave 1 is publisher-
# heavy, and publishers are Sourcepoint/Didomi country. If wave 1 returns zero,
# the honest next question is whether the shape is absent from the WEB or
# absent from THIS LIST -- so wave 2 is picked for the two vendor families whose
# architecture is most likely to put the whole sheet behind the boundary:
#   * enterprise/corporate sites, where TrustArc's `consent-pref.trustarc.com`
#     iframe is common;
#   * ad-supported content sites, where Google's Funding Choices serves its
#     message from `fundingchoicesmessages.google.com` in an iframe.
# Plus EU tabloids and sports, which run the heaviest consent stacks on the web.
SITES2 = [
    # enterprise / corporate -- TrustArc country
    ("cisco", "https://www.cisco.com/", "enterprise"),
    ("oracle", "https://www.oracle.com/", "enterprise"),
    ("ibm", "https://www.ibm.com/", "enterprise"),
    ("intel", "https://www.intel.com/", "enterprise"),
    ("hp", "https://www.hp.com/", "enterprise"),
    ("dell", "https://www.dell.com/", "enterprise"),
    ("sap", "https://www.sap.com/", "enterprise"),
    ("siemens", "https://www.siemens.com/", "enterprise"),
    ("philips", "https://www.philips.com/", "enterprise"),
    ("nestle", "https://www.nestle.com/", "enterprise"),
    ("pg", "https://us.pg.com/", "enterprise"),
    ("unilever", "https://www.unilever.com/", "enterprise"),
    ("pfizer", "https://www.pfizer.com/", "enterprise"),
    ("gsk", "https://www.gsk.com/en-gb/", "enterprise"),
    ("astrazeneca", "https://www.astrazeneca.com/", "enterprise"),
    ("nike", "https://www.nike.com/", "enterprise"),
    ("adidas", "https://www.adidas.co.uk/", "enterprise"),
    ("mcdonalds", "https://www.mcdonalds.com/", "enterprise"),
    ("pepsico", "https://www.pepsico.com/", "enterprise"),
    ("ups", "https://www.ups.com/", "enterprise"),
    ("fedex", "https://www.fedex.com/", "enterprise"),
    ("accenture", "https://www.accenture.com/", "enterprise"),
    ("deloitte", "https://www.deloitte.com/", "enterprise"),
    ("pwc", "https://www.pwc.com/", "enterprise"),
    ("kpmg", "https://kpmg.com/", "enterprise"),
    ("mckinsey", "https://www.mckinsey.com/", "enterprise"),
    ("bosch", "https://www.bosch.com/", "enterprise"),
    ("bayer", "https://www.bayer.com/", "enterprise"),
    ("novartis", "https://www.novartis.com/", "enterprise"),
    ("abb", "https://global.abb/", "enterprise"),

    # ad-supported content -- Google Funding Choices / Quantcast country
    ("howstuffworks", "https://www.howstuffworks.com/", "adsupported"),
    ("gizmodo", "https://gizmodo.com/", "adsupported"),
    ("androidauthority", "https://www.androidauthority.com/", "adsupported"),
    ("xda", "https://www.xda-developers.com/", "adsupported"),
    ("macrumors", "https://www.macrumors.com/", "adsupported"),
    ("gsmarena", "https://www.gsmarena.com/", "adsupported"),
    ("tomshardware", "https://www.tomshardware.com/", "adsupported"),
    ("pcgamer", "https://www.pcgamer.com/", "adsupported"),
    ("eurogamer", "https://www.eurogamer.net/", "adsupported"),
    ("ign", "https://www.ign.com/", "adsupported"),
    ("gamespot", "https://www.gamespot.com/", "adsupported"),
    ("polygon", "https://www.polygon.com/", "adsupported"),
    ("allrecipes", "https://www.allrecipes.com/", "adsupported"),
    ("healthline", "https://www.healthline.com/", "adsupported"),
    ("webmd", "https://www.webmd.com/", "adsupported"),
    ("investopedia", "https://www.investopedia.com/", "adsupported"),
    ("nerdwallet", "https://www.nerdwallet.com/", "adsupported"),
    ("bankrate", "https://www.bankrate.com/", "adsupported"),
    ("sciencealert", "https://www.sciencealert.com/", "adsupported"),
    ("phys_org", "https://phys.org/", "adsupported"),

    # EU tabloids / sports -- the heaviest consent stacks on the web
    ("bild", "https://www.bild.de/", "eu_tabloid"),
    ("kicker", "https://www.kicker.de/", "eu_tabloid"),
    ("sport1", "https://www.sport1.de/", "eu_tabloid"),
    ("marca", "https://www.marca.com/", "eu_tabloid"),
    ("as_com", "https://as.com/", "eu_tabloid"),
    ("lequipe", "https://www.lequipe.fr/", "eu_tabloid"),
    ("tuttosport", "https://www.tuttosport.com/", "eu_tabloid"),
    ("blick", "https://www.blick.ch/", "eu_tabloid"),
    ("heute_at", "https://www.heute.at/", "eu_tabloid"),
    ("rtl_de", "https://www.rtl.de/", "eu_tabloid"),
    ("ouest_sport", "https://www.sudouest.fr/", "eu_tabloid"),
    ("thesun", "https://www.thesun.co.uk/", "eu_tabloid"),
]


def _host(u: str) -> str:
    return re.sub(r"^www\d*\.", "", urlparse(u).netloc.lower())


def _origin(u: str) -> str:
    """scheme://host:port, spelled the way the DOM's `URL.origin` spells it.

    The first version of this was `"{0}//{1}".format(scheme, netloc)`, which
    drops the colon -- `urlparse` returns `https`, not `https:`. Cross-origin
    DETECTION survived it (both sides were malformed the same way), but the
    comparison against the JS-side `new URL(src).origin` could never match, so
    the "the top document wraps this frame" count was structurally pinned at
    zero while the wrapper origins were plainly in the same record. Found by a
    count contradicting data already on screen, not by reading (PRINCIPLES 8).
    """
    p = urlparse(u)
    return "{0}://{1}".format(p.scheme, p.netloc) if p.scheme and p.netloc else ""


def _oeq(a: str, b: str) -> bool:
    """Origin equality that tolerates the malformed spelling above, so rows
    written by the earlier run are repriced rather than silently miscounted."""
    n = lambda s: str(s or "").replace("://", "//").lower()   # noqa: E731
    return bool(n(a)) and n(a) == n(b)


def check_sample() -> list:
    """The out-of-sample guard, firing. Returns the collisions, which must be [].

    PRINCIPLES 15: a guard nobody has watched fire is worth nothing, so `--list`
    prints how many hosts were checked against and plants one known-excluded
    host to show the comparison really happens.
    """
    pool = SITES + SITES2
    bad = [(n, _host(u)) for n, u, _ in pool if _host(u) in EXCLUDED]
    names = [s[0] for s in pool]
    assert len(names) == len(set(names)), "duplicate site name in SITES"
    hosts = [_host(u) for _, u, _ in pool]
    assert len(hosts) == len(set(hosts)), "duplicate host in SITES"
    return bad


# --------------------------------------------------------------------------
# THE DETECTOR.
#
# A faithful port of `dialogOpen` (extension/background.js), evaluated INSIDE
# one frame against that frame's OWN window -- which is #78/MV4's correction:
# a rect is in the coordinate space of the view it came from, and comparing a
# frame-relative rect against the top window's innerWidth is not a threshold
# choice, it is two different spaces.
#
# FIVE OF THE SEVEN RULES ARE PORTED. The two that are not -- "verify the
# aria-modal claim against how many page controls are blocked" and "behavioural
# modality: a supermajority of controls occluded" -- both read the COLLECTOR's
# `out` array, which does not exist here. Both can only turn a false into a
# true, so leaving them out makes this a LOWER BOUND on C. Stated rather than
# buried, because a probe that silently drops two of seven rules is reporting a
# number about itself.
#
# ONE RULE IS WIDER HERE THAN IN THE PRODUCT, in the other direction: the real
# `_allComposed` iterates `mmidReg`, so `dialogOpen` only ever sees dialog nodes
# the COLLECTOR STAMPED, while this walks the composed tree directly. So C is an
# upper bound on that sub-rule and a lower bound overall. The BLOCKING split (D)
# is what the recommendation turns on and it does not depend on either.
# --------------------------------------------------------------------------
FRAME_DIALOG_PROBE = r"""
(function () {
  const SEL = '[role="dialog"],[role="alertdialog"],[aria-modal="true"],dialog';
  const vw = window.innerWidth, vh = window.innerHeight;
  const out = {
    url: location.href, vw: vw, vh: vh,
    nodes: 0, visible_nodes: 0, aria_modal_claim: false,
    trigger: false, rule: null, biggest_frac: 0,
    dialog_text: '', roots: 0, err: null,
    // MAKES THE ZERO AUDITABLE. A frame reporting nodes=0 is either a frame
    // with no dialog in it or a frame that had not loaded yet, and those are
    // the same number. The body text and the control count separate them, and
    // without them "0 of N frames declare a trigger" is a claim about the
    // probe's timing rather than about the web.
    body_len: 0, body_snippet: '', controls: 0,
    any_aria_modal_attr: 0, any_role_dialog_attr: 0,
  };
  try {
    // Composed-tree collection: open shadow roots and the closed ones
    // listener_tag.js captured via its attachShadow wrap (#31). Depth-bounded,
    // the same way the product's own deep walks are.
    const nodes = [];
    const seen = new Set();
    function walk(root, depth) {
      if (!root || depth > 6 || seen.has(root)) return;
      seen.add(root); out.roots++;
      let found = [];
      try { found = root.querySelectorAll(SEL); } catch (e) { return; }
      for (const n of found) if (nodes.indexOf(n) < 0) nodes.push(n);
      let all = [];
      try { all = root.querySelectorAll('*'); } catch (e) { return; }
      let budget = 4000;
      for (const e of all) {
        if (budget-- < 0) break;
        const sr = e.shadowRoot || e.__abClosedRoot;
        if (sr) walk(sr, depth + 1);
      }
    }
    walk(document, 0);
    out.nodes = nodes.length;
    try {
      const bt = (document.body && document.body.innerText) || '';
      out.body_len = bt.length;
      out.body_snippet = bt.replace(/\s+/g, ' ').trim().slice(0, 200);
      out.controls = document.querySelectorAll('a[href],button,input,select,textarea').length;
      out.any_aria_modal_attr = document.querySelectorAll('[aria-modal]').length;
      out.any_role_dialog_attr =
        document.querySelectorAll('[role="dialog"],[role="alertdialog"],dialog').length;
    } catch (e) {}

    // Rule 2 -- the visibility question the collector asks. #36: a bare
    // checkVisibility() checks LAYOUT only and reported 3.81% identity loss
    // that was not there.
    const vis = (d) => {
      try {
        const r = d.getBoundingClientRect();
        if (!(r.width > 0 && r.height > 0)) return false;
        if (d.checkVisibility &&
            !d.checkVisibility({ opacityProperty: true, visibilityProperty: true })) return false;
        return true;
      } catch (e) { return false; }
    };

    let anyVisible = false;
    for (const d of nodes) {
      if (!vis(d)) continue;
      anyVisible = true; out.visible_nodes++;
      const r = d.getBoundingClientRect();
      const frac = (r.width * r.height) / (vw * vh);
      if (frac > out.biggest_frac) {
        out.biggest_frac = frac;
        try { out.dialog_text = (d.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 220); }
        catch (e) {}
      }
      if (d.getAttribute('aria-modal') === 'true') out.aria_modal_claim = true;
      // Rule 3 -- native showModal(). Browser-enforced inertness.
      try { if (d.matches(':modal')) { out.trigger = true; out.rule = 'native-modal'; return out; } }
      catch (e) {}
      // Rule 4 -- dominates the viewport. <dialog> is excluded exactly as the
      // product excludes it: :modal already answered, and overruling a
      // declaration with a measurement is the direction PRINCIPLES 1 forbids.
      let cs; try { cs = getComputedStyle(d); } catch (e) { continue; }
      if (d.tagName !== 'DIALOG' && frac >= 0.5 &&
          r.left <= vw / 2 && r.right >= vw / 2 &&
          r.top <= vh / 2 && r.bottom >= vh / 2 &&
          /^(fixed|absolute|sticky)$/.test(cs.position)) {
        out.trigger = true; out.rule = 'dominates-viewport'; return out;
      }
    }
    // Rule 5 -- aria-hidden siblings. How Radix and every focus-trap library
    // actually implements modality (#25).
    if (anyVisible) {
      for (const d of nodes) {
        if (!vis(d)) continue;
        let n = d;
        for (let up = 0; up < 4 && n && n.parentElement; up++, n = n.parentElement) {
          let hidden = 0, sibs = 0;
          for (const sib of n.parentElement.children) {
            if (sib === n) continue;
            sibs++;
            if (sib.getAttribute && (sib.getAttribute('aria-hidden') === 'true'
                || sib.hasAttribute('inert'))) hidden++;
          }
          if (sibs > 0 && hidden === sibs) {
            out.trigger = true; out.rule = 'aria-hidden-siblings'; return out;
          }
        }
      }
    }
    // Rule 6 -- an inert background. The W3C signal (NHK's consent sheet).
    if (anyVisible) {
      let inerts = [];
      try { inerts = document.querySelectorAll('[inert]'); } catch (e) {}
      for (const h of inerts) {
        const ir = h.getBoundingClientRect();
        if (ir.width * ir.height >= 0.3 * vw * vh) {
          out.trigger = true; out.rule = 'inert-background'; return out;
        }
      }
    }
  } catch (e) { out.err = String(e).slice(0, 160); }
  return out;
})()
"""

# Is the frame's SHELL blocking the user's view of the top document? Four facts,
# no vocabulary: area fraction of the TOP viewport, overlay positioning, covers
# the centre, and -- the one that is not a threshold at all -- does the browser's
# own hit-test at the viewport centre land on this frame or inside it.
SHELL_PROBE = r"""
(el) => {
  const vw = window.innerWidth, vh = window.innerHeight;
  const r = el.getBoundingClientRect();
  let cs = null; try { cs = getComputedStyle(el); } catch (e) {}
  let hit = null, hit_is_frame = false;
  try {
    const top = document.elementFromPoint(Math.floor(vw / 2), Math.floor(vh / 2));
    if (top) {
      hit = top.tagName.toLowerCase();
      hit_is_frame = (top === el) || (top.contains && top.contains(el));
    }
  } catch (e) {}
  return {
    w: Math.round(r.width), h: Math.round(r.height),
    frac: (r.width * r.height) / (vw * vh),
    position: cs ? cs.position : null,
    zindex: cs ? cs.zIndex : null,
    covers_centre: (r.left <= vw / 2 && r.right >= vw / 2 &&
                    r.top <= vh / 2 && r.bottom >= vh / 2),
    hit_at_centre: hit, hit_is_this_frame: hit_is_frame,
    top_vw: vw, top_vh: vh,
  };
}
"""

# Does the TOP document hold a consent sheet of its own? This is the geo sanity
# check and the denominator of the conditional rate: it answers "did a CMP fire
# here AT ALL", so a near-zero absolute rate can be read as the vantage point
# rather than as the web. It deliberately uses the SAME structural rules as the
# frame detector -- a visible dialog node -- and NOT a cookie-word list, because
# PRINCIPLES 4 forbids a natural-language wordlist reading page text and a
# German/Japanese/Arabic consent sheet is exactly what such a list would miss.
#
# PLUS THE ONE FACT THAT EXPLAINS A ZERO RATHER THAN JUST REPORTING IT:
# does the top document's own dialog node WRAP a cross-origin iframe? That is
# Sourcepoint's architecture -- a `role=dialog aria-modal` container in the TOP
# document whose only child is the vendor's iframe -- and if it is the norm,
# then the page-level scan already sees every CMP it needs to, and the boundary
# is not where the sheets live. Item 7 saw one instance of this in the frozen
# corpus and could not tell whether it was the exception or the rule.
TOP_DIALOG_PROBE = (
    "(function () {\n"
    "  const base = " + FRAME_DIALOG_PROBE + ";\n"
    "  base.wrapped_xorigin_iframes = 0;\n"
    "  base.wrapper_frame_origins = [];\n"
    "  try {\n"
    "    const SEL = '[role=\"dialog\"],[role=\"alertdialog\"],[aria-modal=\"true\"],dialog';\n"
    "    for (const d of document.querySelectorAll(SEL)) {\n"
    "      let r; try { r = d.getBoundingClientRect(); } catch (e) { continue; }\n"
    "      if (!(r.width > 0 && r.height > 0)) continue;\n"
    "      if (d.checkVisibility &&\n"
    "          !d.checkVisibility({opacityProperty: true, visibilityProperty: true})) continue;\n"
    "      for (const fr of d.querySelectorAll('iframe')) {\n"
    "        let o = '';\n"
    "        try { o = new URL(fr.src, location.href).origin; } catch (e) { continue; }\n"
    "        if (o && o !== location.origin) {\n"
    "          base.wrapped_xorigin_iframes++;\n"
    "          if (base.wrapper_frame_origins.indexOf(o) < 0) base.wrapper_frame_origins.push(o);\n"
    "        }\n"
    "      }\n"
    "    }\n"
    "  } catch (e) { base.wrap_err = String(e).slice(0, 120); }\n"
    "  return base;\n"
    "})()"
)


BANNER = "MODAL/DIALOG IS CURRENTLY OPEN"


# --------------------------------------------------------------------------
# Per-site measurement.
# --------------------------------------------------------------------------

async def measure_site(rig, tab, page, name, url, bucket) -> dict:
    row = {"name": name, "url": url, "bucket": bucket, "ok": False}
    t0 = time.time()
    try:
        nav = str(await asyncio.wait_for(rig.goto(tab, url), timeout=60))
    except asyncio.TimeoutError:
        row["unmeasured"] = "navigate timed out (60s)"
        return row
    except Exception as e:
        row["unmeasured"] = "navigate error: " + str(e).split("\n")[0][:140]
        return row
    row["nav_excerpt"] = nav[:160].replace("\n", " ")
    if "DID NOT COMMIT" in nav:
        row["unmeasured"] = "navigation did not commit"
        return row
    if "Permission required" in nav or "cannot act on" in nav:
        # A redirect off the granted origin. The gate working, not a failure.
        row["unmeasured"] = "gate refused after redirect: " + nav[:110].replace("\n", " ")
        return row
    # THE HANDLE IS RESOLVED HERE, NOT ONCE PER RUN -- see `_page_for_tab`.
    # `navigate` already told us where the tab landed, so the host is known.
    m = re.search(r"https?://[^\s,\]]+", nav)
    want = _host(m.group(0)) if m else _host(url)
    page = await _page_for_tab(rig, want) or page
    if page is None:
        row["unmeasured"] = "probe found no Playwright page for this tab"
        return row
    try:
        await page.wait_for_timeout(SETTLE_MS)
    except Exception:
        pass
    row["final_url"] = page.url
    row["landed_host"] = _host(page.url)
    # A HANDLE THAT IS NOT THIS PAGE CANNOT ANSWER THE QUESTION, so the row is
    # UNMEASURED rather than "no cross-origin frames". This is the guard the
    # 56-row incident existed for: every MCP-side field below would still have
    # looked perfectly healthy.
    if page.url in ("about:blank", "") or (want and _host(page.url) != want):
        row["unmeasured"] = ("probe could not resolve the Playwright handle for this tab "
                             "(got {0!r}, wanted host {1!r})".format(page.url[:60], want))
        return row

    # THE CONTROL ARM: what does the product say today, on this load?
    try:
        listing = str(await asyncio.wait_for(rig.tool("read_page")(tabId=tab), timeout=90))
    except Exception as e:
        row["unmeasured"] = "read_page failed: " + str(e).split("\n")[0][:140]
        return row
    row["listing_chars"] = len(listing)
    row["banner_today"] = BANNER in listing
    row["xorigin_blocks_today"] = len(re.findall(r"\[CROSS-ORIGIN IFRAME f(\d+)", listing))
    row["section_dialog_rows"] = len(re.findall(r"section=dialog", listing))
    # An almost-empty listing on a real page is the bot-block signature: Chrome
    # rendered an interstitial. Counted as UNMEASURED, never as "no frames".
    rows = len(re.findall(r"\bref_f?\d+", listing))
    row["rows"] = rows

    # THE TOP DOCUMENT's own sheet -- the geo denominator.
    try:
        row["top"] = await page.evaluate(TOP_DIALOG_PROBE)
    except Exception as e:
        row["top"] = {"err": str(e)[:120]}

    # Every frame, with its depth and origin, straight from Playwright --
    # the ground truth the extension is scored against, and the only place
    # depth and cross-origin-ness are knowable at once.
    top_origin = _origin(page.url)
    frames = []
    for f in page.frames:
        if f == page.main_frame:
            continue
        depth, p = 0, f.parent_frame
        while p is not None:
            depth += 1
            p = p.parent_frame
        try:
            forigin = _origin(f.url)
        except Exception:
            forigin = ""
        cross = bool(forigin) and forigin != top_origin and f.url.startswith("http")
        frames.append((f, depth, cross, forigin))
    row["frames_total"] = len(frames)
    row["frames_cross"] = sum(1 for _, _, c, _ in frames if c)

    per = []
    shelled = 0
    for f, depth, cross, forigin in frames:
        info = {"url": f.url[:160], "origin": forigin, "depth": depth, "cross": cross}
        try:
            info["probe"] = await asyncio.wait_for(f.evaluate(FRAME_DIALOG_PROBE), timeout=20)
        except Exception as e:
            info["probe_err"] = str(e).split("\n")[0][:120]
            per.append(info)
            continue
        # SHELL GEOMETRY FOR EVERY CROSS-ORIGIN FRAME, not only the triggering
        # ones. Item 7 asks which triggers are CMP-shaped, and answering only
        # that would miss the category next door: a cross-origin frame that
        # BLOCKS THE WHOLE PAGE while declaring no dialog node anywhere. That
        # one is invisible to `dialogOpen` on either side of the boundary, so
        # it is NOT what item 7 proposes to fix -- which is exactly why it has
        # to be counted separately rather than folded in or left out.
        if cross and shelled < 12:
            shelled += 1
            info["shell"] = await _shell_of(page, f)
        per.append(info)
    row["frames"] = per
    row["shell_capped"] = row["frames_cross"] > 12

    trig = [p for p in per if p.get("cross") and (p.get("probe") or {}).get("trigger")]
    row["cross_trigger_frames"] = len(trig)
    row["would_trigger"] = bool(trig)
    row["blocking"] = sum(1 for p in trig if _is_blocking(p.get("shell")))
    row["is_blocking_site"] = row["blocking"] > 0
    # The category next door, counted and kept apart.
    row["blocking_undeclared"] = sum(
        1 for p in per
        if p.get("cross") and not (p.get("probe") or {}).get("trigger")
        and _is_blocking(p.get("shell")))

    # THE ORDERING HAZARD, CLOSED. `read_page` is taken BEFORE the frame probes,
    # so a sheet that appears in the gap between them would be scored as a
    # trigger with no banner -- a defect that is really a race in the probe.
    # It biases toward FINDING a gap, which is the safe direction for a
    # "don't build" verdict and the dangerous one for a "build" verdict, so it
    # is re-asked rather than reasoned about (PRINCIPLES 8). Only on the sites
    # that claim a gap, so it costs nothing on the rest.
    if row["would_trigger"] and not row["banner_today"]:
        try:
            again = str(await asyncio.wait_for(rig.tool("read_page")(tabId=tab), timeout=90))
            row["banner_recheck"] = BANNER in again
            row["gap_confirmed"] = not row["banner_recheck"]
        except Exception as e:
            row["banner_recheck"] = None
            row["gap_confirmed"] = None
            row["recheck_err"] = str(e).split("\n")[0][:120]
    row["top_has_visible_dialog"] = bool((row.get("top") or {}).get("visible_nodes"))
    row["top_would_trigger"] = bool((row.get("top") or {}).get("trigger"))
    row["secs"] = round(time.time() - t0, 1)
    row["ok"] = True
    return row


async def _shell_of(page, frame) -> dict:
    """Geometry of the OUTERMOST ancestor frame's <iframe> element, in the TOP view.

    For a depth-1 frame that is its own shell. For a nested one it is the
    ancestor whose parent is the main frame -- because a nested CMP blocks the
    user's view only as much as its outermost shell does, and a nested rect is
    in its parent's coordinate space, not the top window's (#78/MV4).
    """
    f = frame
    while f.parent_frame is not None and f.parent_frame != page.main_frame:
        f = f.parent_frame
    try:
        el = await f.frame_element()
        return await page.evaluate(SHELL_PROBE, el)
    except Exception as e:
        return {"err": str(e).split("\n")[0][:120]}


def _is_blocking(shell) -> bool:
    """CMP-shaped versus incidental: does this frame BLOCK the user's view?

    Three facts, and the third is not a threshold at all -- `elementFromPoint`
    at the viewport centre is the browser's own hit-test, so "is this frame on
    top where the user is looking" is answered by Chrome rather than by us.

    DELIBERATELY NOT `dialogOpen`'s `position: fixed|absolute|sticky` term, and
    the reason is the difference between the two questions. That term asks "is
    this ELEMENT an overlay", which is the right question for a bare <div>. Here
    we already know it is a frame, and a very common CMP layout is a `static`
    iframe sized 100% inside a `fixed` WRAPPER -- the page is fully blocked and
    the iframe's own computed position is `static`. Keeping the term would have
    under-counted exactly the class this probe exists to find, which is the
    direction that makes a "don't build" verdict unsafe. The hit-test makes it
    unnecessary: an iframe that wins at the centre is on top however it got
    there. Verified both ways by the selftest -- the 422x202 embed (frac 0.07)
    and the 360x520 chat widget (frac 0.15) are still incidental.
    """
    if not isinstance(shell, dict) or shell.get("err"):
        return False
    return bool(shell.get("frac", 0) >= 0.5
                and shell.get("covers_centre")
                and shell.get("hit_is_this_frame"))


# --------------------------------------------------------------------------
# FIRING PROOF (PRINCIPLES 5/11/15). Local fixtures on two ports, so
# cross-origin is real: Chrome's same-origin policy keys on scheme+host+PORT.
# --------------------------------------------------------------------------

def _selftest_pages(pA: int, pB: int):
    B = "http://127.0.0.1:{0}".format(pB)
    sheet = """<!DOCTYPE html><meta charset="utf-8"><title>sheet</title>
<body style="margin:0">
<div role="dialog" aria-modal="true" id="d"
     style="position:fixed;inset:0;background:#fff;display:flex;align-items:center;
            justify-content:center;font:16px system-ui">
  <div><p>We value your privacy</p>
  <button id="acc">Accept all</button> <button>Reject all</button></div>
</div></body>"""
    plain = """<!DOCTYPE html><meta charset="utf-8"><title>plain</title>
<body style="margin:0;font:14px system-ui"><h3>An ordinary embed</h3>
<button>PLAINFRAME button</button><a href="/x">PLAINFRAME link</a></body>"""
    overlay = ('style="position:fixed;inset:0;width:100%;height:100%;border:0;z-index:2147483647"')
    a = {
        # P -- POSITIVE: a cross-origin frame holding a blocking consent sheet.
        #      The detector MUST fire and the product MUST NOT raise the banner.
        "/p.html": """<!DOCTYPE html><meta charset="utf-8"><title>P xorigin cmp</title>
<body style="margin:0;font:14px system-ui"><h1>P</h1>
<button>PAGE button one</button><a href="/a">PAGE link</a>
<iframe title="consent" src="{0}/sheet.html" {1}></iframe>
</body>""".format(B, overlay),
        # N -- NEGATIVE: the same cross-origin frame, ordinary content.
        #      The detector MUST NOT fire. Without this it could report
        #      everything and distinguish nothing.
        "/n.html": """<!DOCTYPE html><meta charset="utf-8"><title>N xorigin plain</title>
<body style="margin:0;font:14px system-ui"><h1>N</h1>
<button>PAGE button one</button><a href="/a">PAGE link</a>
<iframe title="embed" src="{0}/plain.html"
        style="width:420px;height:200px;border:1px solid #999"></iframe>
</body>""".format(B),
        # C -- CONTROL: the identical sheet served SAME-ORIGIN as an overlay.
        #      The product MUST raise the banner, which is what proves the
        #      control arm works and the gap is specifically the boundary.
        "/c.html": """<!DOCTYPE html><meta charset="utf-8"><title>C same-origin cmp</title>
<body style="margin:0;font:14px system-ui"><h1>C</h1>
<button>PAGE button one</button><a href="/a">PAGE link</a>
<div role="dialog" aria-modal="true"
     style="position:fixed;inset:0;background:#fff;display:flex;align-items:center;
            justify-content:center;font:16px system-ui">
  <div><p>We value your privacy</p>
  <button>Accept all</button> <button>Reject all</button></div>
</div></body>""",
        # I -- INCIDENTAL: a cross-origin frame that WOULD trigger (it holds a
        #      visible full-frame role=dialog) but whose shell is a 360x520
        #      chat panel in the corner. The detector must fire and the
        #      BLOCKING split must call it incidental -- the distinction the
        #      recommendation turns on.
        "/i.html": """<!DOCTYPE html><meta charset="utf-8"><title>I chat widget</title>
<body style="margin:0;font:14px system-ui"><h1>I</h1>
<button>PAGE button one</button><a href="/a">PAGE link</a>
<iframe title="chat" src="{0}/sheet.html"
        style="position:fixed;right:16px;bottom:16px;width:360px;height:520px;border:0"></iframe>
</body>""".format(B),
    }
    b = {"/sheet.html": sheet, "/plain.html": plain}
    return a, b


async def selftest() -> dict:
    pA, pB = AFL.free_port(), AFL.free_port()
    a, b = _selftest_pages(pA, pB)
    sA, sB = AFL.serve(pA, a), AFL.serve(pB, b)
    base = "http://127.0.0.1:{0}".format(pA)
    origins = [base, "http://127.0.0.1:{0}".format(pB)]
    res = {}
    try:
        async with AFL.Rig(origins) as rig:
            tab = await rig.new_tab()
            page = await _page_for_tab(rig)  # may be None; measure_site re-resolves
            for key, path in (("P_positive", "/p.html"), ("N_negative", "/n.html"),
                              ("C_same_origin_control", "/c.html"),
                              ("I_incidental", "/i.html")):
                res[key] = await measure_site(rig, tab, page, key, base + path, "fixture")
            await rig.tool("tabs_close_mcp")(tabId=tab)
    finally:
        for s in (sA, sB):
            s.shutdown()
    P, N, C, I = (res["P_positive"], res["N_negative"],
                  res["C_same_origin_control"], res["I_incidental"])
    verdict = {
        "P detector fires on a cross-origin blocking sheet": P.get("would_trigger") is True,
        "P is classified BLOCKING": P.get("blocking", 0) > 0,
        "P gets NO banner today (the gap)": P.get("banner_today") is False,
        "N detector silent on an ordinary cross-origin frame": N.get("would_trigger") is False,
        "N gets no banner either": N.get("banner_today") is False,
        "C same-origin sheet DOES raise the banner (control arm works)":
            C.get("banner_today") is True,
        "I detector fires on the chat widget": I.get("would_trigger") is True,
        "I is classified INCIDENTAL, not blocking": I.get("blocking", 0) == 0,
    }
    return {"cases": res, "verdict": verdict, "PASSED": all(verdict.values())}


# --------------------------------------------------------------------------

async def dump(names: list):
    """Load named sites and SAVE THE WHOLE LISTING, so a claim about what the
    agent is told can be quoted verbatim instead of summarised.

    The counts above can say `section_dialog_rows == 0`; only the listing can
    show the banner telling the agent to focus on exactly those rows while the
    consent controls sit in a `[CROSS-ORIGIN IFRAME f...]` block addressed by
    `ref_f<id>:<n>`. PRINCIPLES 6 is about what the system SAYS, so the
    evidence has to be the string it said.
    """
    pool = {n: (n, u, b) for n, u, b in (SITES + SITES2)}
    want = [pool[n] for n in names if n in pool]
    if not want:
        raise SystemExit("no such site(s); try --list")
    allsites = SITES + SITES2
    origins = sorted({_origin(u) for _, u, _ in allsites}
                     | {"https://{0}".format(_host(u)) for _, u, _ in allsites}
                     | {"https://www.{0}".format(_host(u)) for _, u, _ in allsites})
    OUT.mkdir(parents=True, exist_ok=True)
    async with AFL.Rig(origins) as rig:
        tab = await rig.new_tab()
        page = await _page_for_tab(rig)      # may be None; re-resolved below
        for name, url, _b in want:
            try:
                await asyncio.wait_for(rig.goto(tab, url), timeout=60)
                page = await _page_for_tab(rig, _host(url)) or page
                if page is not None:
                    await page.wait_for_timeout(SETTLE_MS)
                listing = str(await asyncio.wait_for(
                    rig.tool("read_page")(tabId=tab), timeout=90))
            except Exception as e:
                print("{0}: FAILED {1}".format(name, str(e)[:120]))
                continue
            p = OUT / "listing_{0}.txt".format(name)
            p.write_text(listing, encoding="utf-8")
            banner = BANNER in listing
            sect = len(re.findall(r"section=dialog", listing))
            blocks = len(re.findall(r"\[CROSS-ORIGIN IFRAME f(\d+)", listing))
            print("{0:<16} banner={1!s:<6} section=dialog rows={2:<4} "
                  "cross-frame blocks={3}   -> {4}".format(name, banner, sect, blocks, p))
        await rig.tool("tabs_close_mcp")(tabId=tab)


async def _page_for_tab(rig, want_host=None):
    """The Playwright handle for the tab the MCP tools are driving.

    RESOLVED PER SITE, AND THE FIRST VERSION WAS RESOLVED ONCE PER RUN, WHICH
    SILENTLY MEASURED THE WRONG PAGE FOR A WHOLE WAVE. A persistent context
    opens with its own `about:blank`, and `tabs_create_mcp` adds a second page
    that Playwright may not have registered yet -- so taking the last
    non-extension page is a race. Losing it does not look like a failure: the
    MCP tools keep working (they address the tab by id), the readiness banner
    and the listing are real, and only `page.frames` is empty -- which this
    probe reports as ZERO CROSS-ORIGIN FRAMES. That is a false zero in exactly
    the direction of the conclusion, and it poisoned 56 rows before the guard
    below existed (PRINCIPLES 15, and #77's rule that "I could not see" must
    never render as "there is nothing to see").

    Matched on the landing HOST, which is the fact that identifies the page,
    with the blank page explicitly excluded.
    """
    for _ in range(50):
        cands = [p for p in rig.ctx.pages
                 if not p.url.startswith("chrome-extension://")
                 and p.url not in ("about:blank", "")]
        if want_host:
            for p in cands:
                if _host(p.url) == want_host:
                    return p
        elif cands:
            return cands[-1]
        await asyncio.sleep(0.1)
    return None


async def run(limit=None, start=0, resume=False, wave=0, only=None, jsonl=None):
    bad = check_sample()
    if bad:
        raise SystemExit("OUT-OF-SAMPLE GUARD FAILED, these hosts are in the "
                         "frozen corpus or a bench: {0}".format(bad))
    OUT.mkdir(parents=True, exist_ok=True)
    sink = Path(jsonl) if jsonl else JSONL
    done = set()
    if resume and sink.exists():
        for ln in sink.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(ln)["name"])
            except Exception:
                pass
    pool = {1: SITES, 2: SITES2}.get(wave, SITES + SITES2)
    plan = pool[start:]
    if only:
        want = set(only)
        plan = [s for s in plan if s[0] in want]
        done = set()          # a drift re-run deliberately re-measures
    if limit:
        plan = plan[:limit]
    plan = [s for s in plan if s[0] not in done]
    allsites = SITES + SITES2
    origins = sorted({_origin(u) for _, u, _ in allsites}
                     | {"https://{0}".format(_host(u)) for _, u, _ in allsites}
                     | {"https://www.{0}".format(_host(u)) for _, u, _ in allsites})
    print("{0} sites to load; {1} origins granted into the throwaway profile"
          .format(len(plan), len(origins)))
    async with AFL.Rig(origins) as rig:
        # THE FRESH-PROFILE CLAIM, VERIFIED RATHER THAN ASSERTED. `user_data_dir=""`
        # makes Playwright mint a new temp profile per launch; this counts the jar.
        try:
            jar = await rig.ctx.cookies()
        except Exception:
            jar = None
        print("cookie jar at startup: {0} cookie(s)  <- the fresh-profile check"
              .format(len(jar) if jar is not None else "unreadable"))
        tab = await rig.new_tab()
        page = await _page_for_tab(rig)      # may be None; measure_site re-resolves
        with sink.open("a", encoding="utf-8") as fh:
            for i, (name, url, bucket) in enumerate(plan, 1):
                try:
                    row = await asyncio.wait_for(
                        measure_site(rig, tab, page, name, url, bucket), timeout=200)
                except asyncio.TimeoutError:
                    row = {"name": name, "url": url, "bucket": bucket, "ok": False,
                           "unmeasured": "site budget exceeded (200s)"}
                except Exception as e:
                    row = {"name": name, "url": url, "bucket": bucket, "ok": False,
                           "unmeasured": "harness error: " + str(e).split("\n")[0][:140]}
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                flag = ("UNMEASURED " + str(row.get("unmeasured"))[:60]) if not row.get("ok") else (
                    "frames={0}/{1}x  trig={2}  block={3}  banner_today={4}".format(
                        row.get("frames_total"), row.get("frames_cross"),
                        row.get("cross_trigger_frames"), row.get("blocking"),
                        row.get("banner_today")))
                print("[{0:>3}/{1}] {2:<18} {3}".format(i, len(plan), name, flag), flush=True)
        try:
            await rig.tool("tabs_close_mcp")(tabId=tab)
        except Exception:
            pass
    return sink


# --------------------------------------------------------------------------

def report(path=None):
    src = Path(path) if path else JSONL
    if not src.exists():
        print("nothing on disk at {0}".format(src))
        return
    rows = []
    for ln in src.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(ln))
        except Exception:
            pass
    # Last write wins, so a re-run of one site replaces it.
    byname = {}
    for r in rows:
        byname[r["name"]] = r
    rows = list(byname.values())
    allok = [r for r in rows if r.get("ok")]
    un = [r for r in rows if not r.get("ok")]

    # A BOT WALL RETURNS HTTP 200. `navigate` succeeds, `read_page` succeeds,
    # and the probe would score a challenge interstitial as a site with no
    # cross-origin consent sheet -- i.e. as a ZERO, which is the one thing the
    # non-negotiables forbid. So a loaded page is called THIN when the TOP
    # document holds <= 3 controls AND under 400 characters of text, which no
    # news homepage, shop or government portal does. Both numbers are stated
    # because they are a reporting convenience, not a product rule; the
    # write-up dispositions every thin site by name. Checked against the data
    # it has to separate: npr (522 controls, 8,766 chars, a consent modal
    # suppressing the listing) is NOT thin, while telegraph / dailymail /
    # latimes (0 controls, ~200 chars) are.
    def _thin(r):
        t = r.get("top") or {}
        return (t.get("controls", 0) <= 3) and (t.get("body_len", 0) <= 400)

    thin = [r for r in allok if _thin(r)]
    ok = [r for r in allok if not _thin(r)]
    print("\n" + "=" * 78)
    print("CROSS-ORIGIN CMP FRAMES -- live, fresh profile, no consent ever given")
    print("=" * 78)
    print("candidates attempted              {0}".format(len(rows)))
    print("UNMEASURED - navigate/read/gate   {0}".format(len(un)))
    print("UNMEASURED - loaded a THIN page   {0}   (<=3 controls AND <400 chars in the"
          .format(len(thin)))
    print("                                      top document: a challenge wall, not the site)")
    print("A  sites actually measured        {0}".format(len(ok)))
    # D and U are RECOMPUTED from the stored shell facts rather than read off
    # the per-row field, so a change to `_is_blocking` reprices every row
    # already on disk instead of mixing two rules in one table. The raw facts
    # (frac, covers_centre, hit) are what was recorded; the classification is
    # not, on purpose.
    def _blocking_frames(r, want_trigger):
        n = 0
        for p in r.get("frames", []):
            if not (p.get("cross") and _is_blocking(p.get("shell"))):
                continue
            if bool((p.get("probe") or {}).get("trigger")) == want_trigger:
                n += 1
        return n

    B = [r for r in ok if r.get("frames_cross", 0) > 0]
    C = [r for r in ok if r.get("would_trigger")]
    D = [r for r in ok if _blocking_frames(r, True) > 0]
    E = [r for r in ok if r.get("banner_today")]
    anysheet = [r for r in ok if r.get("top_has_visible_dialog") or r.get("would_trigger")]
    pct = lambda n, d: ("{0:.1f}%".format(100.0 * n / d)) if d else "n/a"   # noqa: E731
    print("B  with >=1 cross-origin frame  {0}   ({1} of A)  [{2} frames]"
          .format(len(B), pct(len(B), len(ok)), sum(r.get("frames_cross", 0) for r in ok)))
    print("C  a cross-origin frame WOULD trigger a page-level scan   {0}   ({1} of A)"
          .format(len(C), pct(len(C), len(ok))))
    print("D    of C, BLOCKING (>=50% of the top viewport, covers its centre, and")
    print("     wins the browser's own hit-test there)                        {0}"
          .format(len(D)))
    print("     of C, INCIDENTAL (a chat launcher, an ad slot)                {0}"
          .format(len(C) - len(D)))
    print("E  CONTROL -- raises the banner TODAY                      {0}   ({1} of A)"
          .format(len(E), pct(len(E), len(ok))))
    gaps = [r for r in C if not r.get("banner_today")]
    conf = [r for r in gaps if r.get("gap_confirmed")]
    print("F  THE GAP ITSELF -- in C and NO banner today             {0}"
          .format(len(gaps)))
    print("     of which confirmed by a second read (not a probe race)       {0}"
          .format(len(conf)))
    print("\nGEO SANITY CHECK -- the vantage point bounds the absolute rate, not the ratio")
    print("  sites showing ANY visible dialog/sheet (top doc or frame)  {0}   ({1} of A)"
          .format(len(anysheet), pct(len(anysheet), len(ok))))
    print("  of those, served CROSS-ORIGIN                              {0}   ({1})"
          .format(len(C), pct(len(C), len(anysheet))))
    print("  of those, BLOCKING and cross-origin                        {0}   ({1})"
          .format(len(D), pct(len(D), len(anysheet))))
    print("  of those, ALREADY caught by the page-level scan today      {0}   ({1})"
          .format(sum(1 for r in anysheet if r.get("banner_today")),
                  pct(sum(1 for r in anysheet if r.get("banner_today")), len(anysheet))))

    # THE MECHANISM, not just the number. A zero is worth far less than a zero
    # with a reason, because a reason is what survives a change in the sample.
    W = [r for r in ok if (r.get("top") or {}).get("wrapped_xorigin_iframes", 0) > 0]
    print("\nWHY -- where the dialog SEMANTICS sit when the content is cross-origin")
    print("  sites whose TOP-document dialog node WRAPS a cross-origin iframe  {0}"
          .format(len(W)))
    print("    (the Sourcepoint shape: role=dialog aria-modal container in the TOP")
    print("     document, vendor iframe inside it -- the page-level scan already")
    print("     sees it, so the boundary is not where the sheet is declared)")
    print("  of those {0}, raise the banner today                              {1}"
          .format(len(W), sum(1 for r in W if r.get("banner_today"))))
    # EVERY BLOCKING CROSS-ORIGIN FRAME, split by what it declares. The fix in
    # item 7 only reaches (a). (b) and (c) are blocked pages a frame-aware
    # `dialogOpen` would STILL miss, because its rules need a declared dialog
    # node that dominates -- so they size a DIFFERENT change, and folding them
    # into the benefit would overstate it.
    ba = bb = bc1 = bc2 = 0
    c2_rows = []
    for r in ok:
        wrapped = set((r.get("top") or {}).get("wrapper_frame_origins") or [])
        for p in r.get("frames", []):
            if not (p.get("cross") and _is_blocking(p.get("shell"))):
                continue
            pr = p.get("probe") or {}
            if pr.get("trigger"):
                ba += 1
            elif pr.get("visible_nodes"):
                bb += 1
            elif any(_oeq(p.get("origin"), w) for w in wrapped):
                bc1 += 1
            else:
                bc2 += 1
                c2_rows.append((r, p))
    tot = ba + bb + bc1 + bc2
    print("\nEVERY BLOCKING CROSS-ORIGIN FRAME, by WHERE the dialog is DECLARED"
          "   (n={0})".format(tot))
    print("  (a) the FRAME declares a dialog and would trigger  <- item 7's gap  {0}"
          .format(ba))
    print("  (b) the frame declares a visible dialog that does NOT trigger       {0}"
          .format(bb))
    print("  (c1) the frame declares nothing, the TOP DOCUMENT wraps it in a")
    print("       role=dialog / aria-modal container  <- ALREADY SEEN TODAY      {0}"
          .format(bc1))
    print("  (c2) nothing declares a dialog anywhere                             {0}"
          .format(bc2))
    print("       (b) and (c2) are blocked pages a frame-aware dialogOpen would")
    print("       STILL miss -- its rules need a declared, dominating node -- so")
    print("       they size a different change, not this one.")

    U = [r for r, _ in c2_rows]
    print("\nTHE CATEGORY NEXT DOOR, counted apart because item 7 does not fix it")
    print("  blocking cross-origin frames with no dialog declared anywhere     {0}"
          .format(len(c2_rows)))
    for r, p in c2_rows[:20]:
        print("      {0:<18} {1:<42} banner_today={2}".format(
            r["name"], (p.get("origin") or "")[:42], r.get("banner_today")))
    print("\nBY BUCKET")
    buckets = {}
    for r in ok:
        b = buckets.setdefault(r.get("bucket", "?"), [0, 0, 0, 0, 0])
        b[0] += 1
        b[1] += 1 if r.get("frames_cross", 0) else 0
        b[2] += 1 if r.get("would_trigger") else 0
        b[3] += 1 if r.get("is_blocking_site") else 0
        b[4] += 1 if r.get("banner_today") else 0
    print("  {0:<12}{1:>7}{2:>8}{3:>7}{4:>8}{5:>9}".format(
        "bucket", "loaded", "xframe", "C", "BLOCK", "bannerE"))
    for k in sorted(buckets):
        v = buckets[k]
        print("  {0:<12}{1:>7}{2:>8}{3:>7}{4:>8}{5:>9}".format(k, *v))
    if C:
        print("\nEVERY SITE IN C, with the rule that fired and the shell geometry:")
        for r in sorted(C, key=lambda x: (not x.get("is_blocking_site"), x["name"])):
            for p in r.get("frames", []):
                pr = p.get("probe") or {}
                if not (p.get("cross") and pr.get("trigger")):
                    continue
                sh = p.get("shell") or {}
                kind = "BLOCKING  " if _is_blocking(sh) else "incidental"
                print("  {0} {1:<16} {2:<22} rule={3:<22} shell {4}x{5} "
                      "frac={6:.2f} pos={7} hit={8}".format(
                          kind, r["name"], (p.get("origin") or "")[:22], pr.get("rule"),
                          sh.get("w"), sh.get("h"), sh.get("frac", 0) or 0,
                          sh.get("position"), sh.get("hit_is_this_frame")))
                if pr.get("dialog_text"):
                    print("             text: {0}".format(pr["dialog_text"][:110]))
    # "LOADED" IS NOT "IS THE SITE". A bot wall, a consent wall on another
    # origin, or a geo redirect all return HTTP 200 and a document. The
    # non-negotiable here is that a site which blocked the probe is named, never
    # folded into a zero -- so these are printed as FACTS (row count, where it
    # landed) rather than classified by a vendor list, and the write-up
    # dispositions them by looking.
    odd = [r for r in ok
           if r.get("rows", 0) < 10 or _host(r.get("final_url") or "") != _host(r["url"])]
    if odd:
        print("\nLOADED BUT POSSIBLY NOT THE SITE -- dispositioned by looking, not by a rule")
        for r in sorted(odd, key=lambda x: x.get("rows", 0)):
            print("  {0:<18} rows={1:<5} landed={2:<28} banner={3}".format(
                r["name"], r.get("rows"), (r.get("landed_host") or "")[:28],
                r.get("banner_today")))

    if thin:
        print("\nTHIN / WALLED, named and EXCLUDED from every count above:")
        for r in sorted(thin, key=lambda x: x["name"]):
            t = r.get("top") or {}
            print("  {0:<18} top_controls={1:<4} top_chars={2:<6} frames={3:<3} landed={4}"
                  .format(r["name"], t.get("controls"), t.get("body_len"),
                          r.get("frames_total"), (r.get("landed_host") or "")[:26]))
    if un:
        print("\nUNMEASURED, named (never counted as a zero):")
        for r in sorted(un, key=lambda x: x["name"]):
            print("  {0:<18} {1}".format(r["name"], str(r.get("unmeasured"))[:98]))
    print("\nraw: {0}".format(src))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true",
                    help="prove the detector fires, and that it stays silent, before any count")
    ap.add_argument("--list", action="store_true", help="the sample and the guard firing")
    ap.add_argument("--report", action="store_true", help="re-aggregate what is on disk")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--resume", action="store_true", help="skip sites already on disk")
    ap.add_argument("--wave", type=int, default=0,
                    help="1 = publisher-heavy, 2 = TrustArc/FundingChoices-heavy, 0 = both")
    ap.add_argument("--only", default=None,
                    help="comma-separated site names: re-measure exactly these (drift control)")
    ap.add_argument("--jsonl", default=None,
                    help="write/read results elsewhere, so a drift arm cannot overwrite the main run")
    ap.add_argument("--dump", default=None,
                    help="comma-separated site names: save their full listings for quoting")
    args = ap.parse_args()

    if args.dump:
        asyncio.run(dump([s.strip() for s in args.dump.split(",") if s.strip()]))
        return 0

    if args.list:
        bad = check_sample()
        pool = SITES + SITES2
        for n, u, b in pool:
            print("{0}\t{1}\t{2}".format(n, b, u))
        print("\n{0} candidates ({1} wave 1 + {2} wave 2), {3} buckets".format(
            len(pool), len(SITES), len(SITES2), len({b for _, _, b in pool})))
        print("out-of-sample guard: checked against {0} excluded hosts "
              "(frozen corpus + bench_turns + bench_flows); collisions: {1}"
              .format(len(EXCLUDED), bad or "none"))
        # PRINCIPLES 15: show the comparison really happens rather than trusting
        # an empty list. A host known to be excluded must be reported.
        probe = "nytimes.com"
        print("guard firing check: is {0!r} seen as excluded? {1}".format(
            probe, probe in EXCLUDED))
        return 0
    if args.report:
        report(args.jsonl)
        return 0
    if args.selftest:
        r = asyncio.run(selftest())
        print("\nSELFTEST -- the detector, both directions")
        for k, v in r["verdict"].items():
            print("  {0:<62} {1}".format(k, "OK" if v else "FAILED"))
        print("  {0}".format("PASSED" if r["PASSED"] else "FAILED"))
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "selftest.json").write_text(json.dumps(r, indent=1, ensure_ascii=False),
                                           encoding="utf-8")
        return 0 if r["PASSED"] else 1

    only = [x.strip() for x in args.only.split(',')] if args.only else None
    asyncio.run(run(limit=args.limit, start=args.start, resume=args.resume,
                    wave=args.wave, only=only, jsonl=args.jsonl))
    report(args.jsonl)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Capture the REAL agent-facing interactive-element listing on a set of diverse,
challenging pages, using the same collection JS the Chrome extension runs.

Injects tools/dom_filter_probe.js (an instrumented twin of background.js's
`_collectInteractivePage`, kept in lock-step) via Playwright `page.evaluate`,
which returns the full listing string to Python with NO truncation. Writes one
<name>.txt (meta + agent-facing listing) and one <name>.png screenshot per page
under temp/dom_audit/, so reviewer agents can compare "what the agent sees" to
"what's actually on screen."

Run:  python tools/capture_listings.py
(uses the same Playwright install as tools/audit_sites.py)
"""

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


def _extract_collector() -> str:
    """Pull the REAL `_collectInteractivePage` source out of background.js (brace-
    balanced) so the capture reflects exactly what the extension ships — no
    probe-divergence risk. The function is self-contained (no outer refs)."""
    src = (Path(__file__).resolve().parent.parent / "extension" / "background.js").read_text(encoding="utf-8")
    marker = "function _collectInteractivePage(structured) {"
    i = src.index(marker)
    j = i + len(marker)
    depth = 1
    while depth and j < len(src):
        c = src[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        j += 1
    return src[i:j]


COLLECTOR = _extract_collector()
# Wrapper expression: define the real collector, return both the agent-facing
# listing (structured=false) and the full pre-cap element count (structured=true).
WRAP = "(function(){ " + COLLECTOR + "\n; var a=_collectInteractivePage(true); var s=_collectInteractivePage(false); return { count: a.length, listing: s }; })()"

# Diverse, deliberately hard targets. Public (Playwright runs a fresh, logged-out
# Chromium), each stressing a different code path.
SITES = [
    ("github",      "https://github.com/"),                                   # rich app UI, icon buttons, menus
    ("youtube",     "https://www.youtube.com/"),                              # heavy shadow DOM (piercing gap)
    ("mui_autocomplete", "https://mui.com/material-ui/react-autocomplete/"),  # MUI custom comboboxes
    ("hn",          "https://news.ycombinator.com/"),                         # layout tables, dense links
    ("bootstrap_forms", "https://getbootstrap.com/docs/5.3/forms/overview/"), # many native form controls
    ("amazon",      "https://www.amazon.com/"),                               # huge commercial page, noise
    ("shoelace",    "https://shoelace.style/components/select"),              # Lit web components, open shadow roots
    ("mui_datepicker", "https://mui.com/x/react-date-pickers/date-picker/"),  # ARIA grid calendars (compaction)
    ("lexical",     "https://playground.lexical.dev/"),                       # contenteditable rich-text editor
    ("w3s_tryit",   "https://www.w3schools.com/html/tryit.asp?filename=tryhtml_default"),  # iframe-heavy editor page
    # ---- Round-5 generality stress set ----
    ("wikipedia_ar", "https://ar.wikipedia.org/"),                            # RTL layout + Arabic text
    ("amazon_de",   "https://www.amazon.de/"),                                # German UI (locale heuristics)
    ("antd",        "https://ant.design/components/select"),                  # Ant Design (non-Radix comboboxes)
    ("vuetify",     "https://vuetifyjs.com/en/components/selects/"),          # Vuetify (Vue stack)
    ("webdev",      "https://web.dev/"),                                      # Lit web components, shadow DOM (reddit blocks headless)
    ("booking",     "https://www.booking.com/"),                              # datepickers, autocomplete, consent modal
    ("gh_issues",   "https://github.com/microsoft/vscode/issues"),            # dense app UI, filter dropdowns
    ("mdn_select",  "https://developer.mozilla.org/en-US/docs/Web/HTML/Element/select"),  # dense docs + interactive-example iframe (SO blocks headless)
    # ---- Round-6 stress set ----
    ("gov_uk",      "https://www.gov.uk/"),                                   # a11y gold standard (control group)
    ("guardian",    "https://www.theguardian.com/international"),             # consent modal + very dense news grid
    ("yahoo_jp",    "https://www.yahoo.co.jp/"),                              # CJK text, dense portal
    ("craigslist",  "https://www.craigslist.org/about/sites"),                # legacy table/list markup
    ("ng_material", "https://material.angular.dev/components/select/overview"),  # Angular Material (untested stack)
    ("svelte",      "https://svelte.dev/"),                                   # Svelte stack
    ("excalidraw",  "https://excalidraw.com/"),                               # canvas-drawn app (canvas fallback)
    ("aggrid",      "https://www.ag-grid.com/example/"),                      # virtualized data grid (aria-rowcount)
    # ---- Round-7 stress set ----
    ("gflights",    "https://www.google.com/travel/flights"),                 # Google stack (c-wiz!), heavy widgets
    ("headlessui",  "https://headlessui.com/react/menu"),                     # Headless UI (data-headlessui-state)
    ("react_aria",  "https://react-spectrum.adobe.com/react-aria/Select.html"),  # React Aria (a11y-maximal)
    ("openui5",     "https://sdk.openui5.org/"),                              # enterprise SAP OpenUI5
    ("stripe",      "https://stripe.com/"),                                   # marketing, heavy animation/gradients
    ("ebay",        "https://www.ebay.com/"),                                 # e-commerce home
    ("wordpress",   "https://wordpress.org/"),                                # classic CMS
    ("notion",      "https://www.notion.com/"),                               # React marketing SPA
    # ---- Round-8 stress set ----
    ("select2",     "https://select2.org/getting-started/basic-usage"),       # Select2 (jQuery select lib)
    ("jqueryui",    "https://jqueryui.com/datepicker/"),                      # jQuery UI demo in iframe
    ("flatpickr",   "https://flatpickr.js.org/examples/"),                    # live JS datepickers
    ("chakra",      "https://www.chakra-ui.com/docs/components/select"),      # Chakra UI v3
    ("mastodon",    "https://mastodon.social/explore"),                       # SPA social, public timeline
    ("solidjs",     "https://www.solidjs.com/"),                              # Solid stack
    ("saucedemo",   "https://www.saucedemo.com/"),                            # plain login form
    ("kayak",       "https://www.kayak.com/"),                                # travel widgets (may bot-wall)
    # ---- Round-9 stress set ----
    ("osm",         "https://www.openstreetmap.org/"),                        # full Leaflet map app
    ("discourse",   "https://meta.discourse.org/"),                           # Ember SPA, infinite topic list
    ("spotify",     "https://open.spotify.com/"),                             # media SPA (public, logged out)
    ("vimeo",       "https://vimeo.com/"),                                    # video platform
    ("gitlab",      "https://gitlab.com/explore/projects"),                   # app-like project lists
    ("yahoo_fin",   "https://finance.yahoo.com/"),                            # dense finance data + consent
    ("ryanair",     "https://www.ryanair.com/gb/en"),                         # aggressive widgets + consent
    ("khan",        "https://www.khanacademy.org/"),                          # edu SPA
    # ---- Round-10 stress set ----
    ("htmx",        "https://htmx.org/examples/"),                            # htmx server-rendered partials (w3.org/deque unavailable headless)
    ("arxiv",       "https://arxiv.org/abs/2410.13825"),                      # academic legacy markup
    ("jsfiddle",    "https://jsfiddle.net/"),                                 # editors + preview iframes (codepen CF-gates headless)
    ("coinmarketcap", "https://coinmarketcap.com/"),                          # dense sticky-col data table
    ("espn",        "https://www.espn.com/"),                                 # media-dense sports portal
    ("weather",     "https://weather.com/"),                                  # widget-heavy + consent
    ("ionic",       "https://ionicframework.com/docs/api/select"),            # ion-* shadow web components
    ("archive_org", "https://archive.org/"),                                  # legacy + media tiles
    # ---- Round-11 stress set ----
    ("grafana",     "https://play.grafana.org/"),                             # live dashboard app (panels, time pickers)
    ("jupyter",     "https://jupyter.org/try-jupyter", 12000),                # JupyterLite app-in-iframe (WASM boot needs time)
    ("adminlte",    "https://adminlte.io/themes/v3/index.html"),              # classic admin-panel demo
    ("datatables",  "https://datatables.net/examples/basic_init/zero_configuration.html"),  # canonical jQuery table
    ("primevue",    "https://primevue.org/select/"),                          # PrimeVue combobox stack
    ("wikihow",     "https://www.wikihow.com/Main-Page"),                     # ad/consent-heavy wiki (fandom CF-gates headless)
    ("service_public", "https://www.service-public.fr/"),                     # French government portal
    ("carbon",      "https://carbondesignsystem.com/components/dropdown/usage/"),  # IBM Carbon design system
    # ---- Round-12 stress set ----
    ("vscode_dev",  "https://vscode.dev/", 8000),                             # Monaco full IDE in browser
    ("tldraw",      "https://www.tldraw.com/", 6000),                         # canvas whiteboard app (photopea gates behind landing)
    ("bookstore",   "https://books.toscrape.com/"),                           # e-commerce store (opencart CF-gates headless)
    ("todomvc",     "https://todomvc.com/examples/react/dist/"),              # canonical TodoMVC widget app
    ("lobsters",    "https://lobste.rs/"),                                    # HN-like aggregator (old.reddit bot-walls)
    ("usa_gov",     "https://www.usa.gov/"),                                  # US government portal
    ("fullcalendar", "https://fullcalendar.io/demos", 3000),                  # live calendar widgets
    ("stackedit",   "https://stackedit.io/app", 5000),                        # in-browser markdown editor (hedgedoc CF-gates)
    # ---- Round-13 stress set ----
    ("grapesjs",    "https://grapesjs.com/demo.html", 5000),                  # drag-drop page builder
    ("videojs",     "https://videojs.com/", 3000),                            # video player controls
    ("maplibre",    "https://maplibre.org/maplibre-gl-js/docs/examples/display-a-map/", 4000),  # WebGL map canvas
    ("surveyjs",    "https://surveyjs.io/form-library/examples/nps-question/", 4000),  # live survey form
    ("python_docs", "https://docs.python.org/3/"),                            # Sphinx docs + version/lang selects
    ("bandcamp",    "https://bandcamp.com/", 3000),                           # music grid + player
    ("daterangepicker", "https://www.daterangepicker.com/", 3000),            # live date-range widget
    ("jspreadsheet", "https://bossanova.uk/jspreadsheet/v4/", 3000),          # web spreadsheet grid
    # ---- Round-14 stress set ----
    ("baidu",       "https://www.baidu.com/", 3000),                          # Chinese search portal
    ("naver",       "https://www.naver.com/", 3000),                          # Korean dense portal
    ("canada_ca",   "https://www.canada.ca/en.html"),                         # bilingual government
    ("premierleague", "https://www.premierleague.com/", 4000),                # consent + league tables
    ("regex101",    "https://regex101.com/", 4000),                           # live regex tool (editors + sidebar)
    ("caniuse",     "https://caniuse.com/?search=grid", 3000),                # feature-support tables
    ("lichess",     "https://lichess.org/", 4000),                            # real-time chess app (SVG board)
    ("habr",        "https://habr.com/ru/articles/", 3000),                   # Russian tech portal
    # ---- Round-16 stress set ----
    ("flutter_web", "https://wonderous.app/web/", 12000),                     # CanvasKit-rendered Flutter showcase (samples URL 404s)
    ("syncfusion_grid", "https://blazor.syncfusion.com/demos/datagrid/overview", 10000),  # Blazor/WASM grid (telerik nav-timeouts)
    ("java_api",    "https://docs.oracle.com/javase/8/docs/api/", 3000),      # legacy <frameset>
    ("moodle",      "https://sandbox.moodledemo.net/", 4000),                 # LMS app sandbox
    ("nytimes",     "https://www.nytimes.com/", 4000),                        # paywall/consent news
    ("irs_forms",   "https://www.irs.gov/forms-instructions", 3000),          # government forms directory
    ("wiki_edit",   "https://en.wikipedia.org/wiki/Wikipedia:Sandbox?action=edit", 4000),  # MediaWiki live editor
    ("godbolt",     "https://godbolt.org/", 6000),                            # Compiler Explorer: Monaco panes + pickers (roundcube DNS-dead)
    # ---- Round-17 stress set ----
    ("desmos",      "https://www.desmos.com/calculator", 6000),               # canvas graph + math-input sidebar
    ("swagger",     "https://petstore.swagger.io/", 5000),                    # Swagger UI: accordion try-it API forms
    ("graphiql",    "https://graphql.org/swapi-graphql/", 6000),              # GraphiQL editors + docs panel (countries endpoint aborts)
    ("drawio",      "https://app.diagrams.net/", 6000),                       # diagram app (storage-picker dialog on load)
    ("shadcn_select", "https://ui.shadcn.com/docs/components/select", 4000),  # the ORIGIN stack (Radix/shadcn) in the wild
    ("gmaps",       "https://www.google.com/maps", 6000),                     # Google Maps (canvas + consent variance)
    ("healthcare_gov", "https://www.healthcare.gov/", 3000),                  # US healthcare portal
    ("calcnet",     "https://www.calculator.net/mortgage-calculator.html", 3000),  # dense calculator form (bankrate bot-walls)
]

OUT = Path("temp/dom_audit")


async def capture(browser, name: str, url: str, extra_ms: int = 0) -> dict:
    ctx = await browser.new_context(viewport={"width": 1366, "height": 900})
    page = await ctx.new_page()
    # Mirror the extension's document_start listener-tagging content script.
    await page.add_init_script(path=str(Path(__file__).resolve().parent.parent / "extension" / "listener_tag.js"))
    page.set_default_navigation_timeout(30000)
    rec = {"name": name, "url": url}
    try:
        await page.goto(url, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        await page.wait_for_timeout(1200 + extra_ms)  # let SPAs paint (+ per-site boot time)
        result = await page.evaluate(WRAP)
        listing = result.get("listing", "")
        body = ("=== AGENT-FACING LISTING (verbatim from extension/background.js::_collectInteractivePage) ===\n"
                + listing + "\n")
        (OUT / f"{name}.txt").write_text(body, encoding="utf-8")
        try:
            await page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
        except Exception as e:
            rec["screenshot_error"] = str(e)
        rec.update({"elements_before_cap": result.get("count"),
                    "listing_lines": listing.count("\n") + 1,
                    "listing_chars": len(listing)})
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
    finally:
        await ctx.close()
    return rec


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        rows = []
        for site in SITES:
            name, url = site[0], site[1]
            extra = site[2] if len(site) > 2 else 0
            print(f"  • {name:18s} {url}", flush=True)
            rows.append(await capture(browser, name, url, extra))
        await browser.close()
    (OUT / "_summary.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print("\n=== CAPTURE SUMMARY ===")
    for r in rows:
        if "error" in r:
            print(f"  {r['name']:18s} ERROR {r['error'][:90]}")
        else:
            print(f"  {r['name']:18s} elements(pre-cap)={r['elements_before_cap']:<5} listing_lines={r['listing_lines']:<4} chars={r['listing_chars']}")
    print(f"\nArtifacts in {OUT.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())

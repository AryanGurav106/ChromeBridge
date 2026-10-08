"""Unit suite for the `find` tool — the one tool that had none.

find() ranks and formats in Python, so it needs no browser: feeding it synthetic
structured entries exercises the real scorer and the real formatter directly.
The absence of this file is why six of nine agents in the escalation study had to
discover find's problems on live pages instead.

Every check corresponds to something an agent hit:
  F1  images were outside the search space entirely — a perfect query for a
      photograph returned 17 nav anchors and no signal that images were excluded.
  F2  non-ASCII labels printed as \\uXXXX escapes (json.dumps defaults to
      ensure_ascii=True), undoing the collector's non-Latin work in the one tool
      that reports elements as text.
  F3  one unlabelled quoted string that could be the name, the value, the
      placeholder or the text. On Baidu an agent read a placeholder as contents.
  F4  a raw `q_full in label` bonus ranked "Duffield Memorial" above a real input
      for the query "field" — the exact failure the token scorer avoids.
  F5  weak keyword overlap was reported under a confident "Found N matching".
  F8  "search box" — find's own docstring example — scored zero against a search
      box whose only label was in another language.

Run:  python tools/test_find.py
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_spec = importlib.util.spec_from_file_location("ms", ROOT / "mcp_server.py")
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)
_find = ms.find.fn if hasattr(ms.find, "fn") else ms.find

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))


def page(*entries, listing=None):
    """Install a fake bridge returning these structured entries.

    `listing` models the OTHER half of the real op's contract: with
    structured=True the bridge hands back entries, otherwise a formatted listing
    STRING. The fake used to return entries whatever was asked, which is exactly
    the stub-shares-your-assumptions trap #19 records — find's miss path reads the
    string form, and against this fake it would have seen a Python list.
    """
    class FB:
        connected = True

        async def call(self, op, **kw):
            if op == "get_interactive_elements" and not kw.get("structured"):
                return listing if listing is not None else ""
            return list(entries)
    ms.STATE["bridge"] = FB()


def el(**kw):
    base = dict(mmid="1", tag="div", role=None, label="", name="", value="",
                placeholder="", text="", near="", w=100, h=20, y=0)
    base.update(kw)
    return base


async def run(q):
    return await _find(query=q, tabId=1)


async def main():
    IMG = el(mmid="13", tag="div", role="media", name="Italian Trulli", mediaOnly=True,
             src="https://example.com/pic_trulli.jpg", w=294, h=300, y=592)
    NAV = el(mmid="10", tag="a", label="Images", name="", text="Images", section="nav", y=20)
    CJK = el(mmid="12", tag="textarea", placeholder="2人冒充保安看演唱会被罚",
             underHeading="新闻", w=300, h=30, y=60)
    DUFF = el(mmid="20", tag="a", label="Duffield Memorial", name="Duffield Memorial", y=10)
    BTN = el(mmid="14", tag="input", type="submit", label="Login", name="Login", w=290, h=47, y=300)

    page(IMG, NAV, CJK, DUFF, BTN)
    out = await run("photograph")
    check("F1 an image is reachable by the words people use for one",
          "ref_13" in out and "pic_trulli.jpg" in out,
          out.splitlines()[1].strip()[:96] if len(out.splitlines()) > 1 else out[:96])
    check("F7 ...and is marked as media rather than something to click",
          "image/media — not a control" in out)

    out = await run("search box")
    check("F2 non-Latin labels print as text, not as escape sequences",
          "2人冒充保安看演唱会被罚" in out and "\\u" not in out,
          out.splitlines()[-1].strip()[:96])
    check("F8 a role word reaches a control whose own text is in another language",
          "ref_12" in out, "found" if "ref_12" in out else "MISSED the search box")

    out = await run("login")
    check("F3 identity is labelled, not a bare ambiguous string",
          'name="Login"' in out, out.splitlines()[-1].strip()[:96])

    page(CJK, DUFF)
    out = await run("field")
    order = [ln for ln in out.splitlines() if ln.strip().startswith("ref_")]
    check("F4 a buried substring does not outrank a real control",
          bool(order) and "ref_12" in order[0],
          " | ".join(o.strip()[:44] for o in order))

    # A genuine WEAK match: "field" is buried mid-word in "Duffield", scoring the
    # 0.1 substring weight and nothing else. A zero-overlap query takes the
    # no-match path instead, which is a different branch — so the fixture has to
    # contain the buried match and nothing better.
    page(DUFF)
    out = await run("field")
    check("F5 weak keyword overlap is reported as NOT a match",
          "NO CONFIDENT MATCH" in out, out.splitlines()[0][:110])
    check("F6 ...and weak results stay few",
          len([ln for ln in out.splitlines() if ln.strip().startswith("ref_")]) <= 5)

    # G-series: language handling the audit found still broken after the rewrite.
    page(el(mmid="40", tag="a", label="이검색어저장소", name="이검색어저장소", y=10),
         el(mmid="41", tag="button", label="상품 검색", name="상품 검색", y=20))
    out = await run("검색")
    first = next((l for l in out.splitlines() if l.strip().startswith("ref_")), "")
    check("F10 Korean: a buried compound match does not outrank the real control",
          "ref_41" in first, first.strip()[:70])

    page(el(mmid="50", tag="button", label="搜索", name="搜索", y=10))
    out = await run("搜索按钮")
    check("F11 a spaceless-script noun+role query reaches a shorter label",
          "ref_50" in out, out.splitlines()[0][:70])

    import unicodedata as _u
    page(el(mmid="60", tag="button", label=_u.normalize("NFD", "café menü"),
            name=_u.normalize("NFD", "café menü"), y=10))
    out = await run("café")
    check("F12 an NFC query matches an NFD label",
          "ref_60" in out, out.splitlines()[0][:70])

    page(*[el(mmid=str(200 + i), tag="button", label="Delete row", name="Delete row", y=i * 20)
           for i in range(31)])
    out = await run("delete")
    check("F13 a capped result list states the true total",
          "Found 31" in out and "11 more not listed" in out, out.splitlines()[0][:100])

    # Baidu's real shape: the submit button reads 百度一下, so a Chinese query for
    # "search button" has NO text overlap — the role word is the only signal, and
    # the hint table used to speak only English. Verified live before this fix:
    # find returned a confident "No elements matched" on a page with both.
    page(el(mmid="70", tag="textarea", placeholder="41岁女子为鼓励女儿考上985研究生", w=300, h=30, y=10),
         el(mmid="71", tag="input", type="submit", label="百度一下", name="百度一下", w=100, h=40, y=10))
    for q, want in (("搜索按钮", "ref_71"), ("検索ボタン", "ref_71"), ("поиск", "ref_70")):
        out = await run(q)
        check(f"F14 a non-English role word reaches the control ({q})",
              want in out, out.splitlines()[0][:64])

    # F15/F16: found by two independent live agents. A long natural-language query
    # let ONE common word carry footer boilerplate into the confident list — on BBC
    # "About the BBC" and "Read about our approach to external linking" were listed
    # under `Found 15 element(s) matching "lead photo image of the top story about
    # Thai PM gun laws"`. Score alone said 1.0; coverage says one word of ten.
    REAL = el(mmid="30", tag="img", role="media", name="Thai PM lead photo", mediaOnly=True,
              src="https://example.com/thai-pm.jpg", w=616, h=347, y=251)
    FOOT = el(mmid="31", tag="a", label="About the BBC", name="About the BBC", section="footer", y=4785)
    LINK = el(mmid="32", tag="a", label="Read about our approach to external linking.",
              name="Read about our approach to external linking.", section="footer", y=4846)
    page(REAL, FOOT, LINK)
    out = await run("lead photo image of the top story about Thai PM gun laws")
    confident = out.split("NO CONFIDENT MATCH")[0] if "NO CONFIDENT MATCH" in out else out
    strong_refs = [ln for ln in confident.splitlines() if ln.strip().startswith("ref_")]
    check("F15 a long query does not promote one-common-word footer noise",
          not any("ref_31" in l or "ref_32" in l for l in strong_refs),
          " | ".join(l.strip()[:46] for l in strong_refs) or "none")
    check("F16 ...while the element that answers the query still ranks",
          "ref_30" in out, out.splitlines()[0][:80])

    # href is the attribute a URL task needs, and was the only one never emitted.
    page(el(mmid="33", tag="a", label="Download the report", name="Download the report",
            href="/downloads/report.pdf?v=2", y=10))
    out = await run("download the report")
    check("F17 find reports a link's href, not just image src",
          "report.pdf" in out, out.splitlines()[-1].strip()[:90])

    # F18: adding href to the identity block made `ident` non-empty and silently
    # suppressed the text fallback, so a link with no accessible name printed its
    # URL and nothing else. A live agent had to infer which of 12 MDN results was
    # right by reading the API name out of the URL string. Attributes are not
    # identity; adding a field must never delete another.
    page(el(mmid="60", tag="a", label="Element.querySelector", name="",
            text="Element.querySelector", section="main",
            href="https://developer.mozilla.org/en-US/docs/Web/API/Element/querySelector", y=10))
    out = await run("querySelector")
    check("F18 a link with only text still shows its label alongside its href",
          '"Element.querySelector"' in out and "href=" in out,
          out.splitlines()[-1].strip()[:96])

    # F19/F20: the SHARED formatter path. The collector attaches `line` — the exact
    # row read_page would print — and find must render from it rather than
    # rebuilding the row in Python. Every other fixture here omits `line`, so
    # without these the new path was completely untested and only the legacy
    # fallback was being exercised.
    page(el(mmid="70", tag="a", label="Download report", text="Download report",
            href="/downloads/report.pdf",
            line='mmid=70 | a "Download report" href="/downloads/report.pdf" | box(8,8,200,20)',
            y=8))
    out = await run("download report")
    check("F19 find renders from the collector's line, not a parallel formatter",
          '"Download report"' in out and "report.pdf" in out and "box(" not in out,
          out.splitlines()[-1].strip()[:100])

    # A version-skew guard: an older extension returns no `line`, and find must
    # degrade rather than emit an empty identity.
    page(el(mmid="71", tag="a", label="Legacy link", text="Legacy link",
            href="/legacy", y=8))
    out = await run("legacy link")
    check("F20 an entry with no line still renders (older extension build)",
          "Legacy link" in out and "/legacy" in out,
          out.splitlines()[-1].strip()[:100])

    # F21-F24: the confidence heading, reported independently by SIX live agents.
    # Two separate causes, both letting junk through under `Found N element(s)`:
    #  - coverage was credited on ANY score increase, including the 0.1 weight for
    #    a fragment buried inside a longer word;
    #  - the >=2-covered-token rule only applied from FOUR tokens, so a 3-token
    #    query passed on one generic word.
    page(el(mmid="337", tag="button", name="Issue body actions"),
         el(mmid="109", tag="a", name="All issues"),
         el(mmid="266", tag="a", name="New issue"))
    out = await run("labels applied to this issue")
    check("F21 a 3-token query is not answered confidently by one generic word",
          "NO CONFIDENT MATCH" in out, out.splitlines()[0][:96])

    page(el(mmid="504", tag="a", name="Browser compatibility"),
         el(mmid="17110", tag="a", name="About", section="footer"),
         el(mmid="374", tag="a", name="Web APIs"))
    out = await run("the link about browser compatibility data for this API")
    confident = out.split("NO CONFIDENT MATCH")[0]
    strong = [l for l in confident.splitlines() if l.strip().startswith("ref_")]
    check("F22 ...and one-token footer noise stays out of the confident list",
          any("ref_504" in l for l in strong)
          and not any(("ref_17110" in l or "ref_374" in l) for l in strong),
          " | ".join(l.strip()[:40] for l in strong) or "none")

    # A whole form answered "date of birth field" — 15 elements, the real DOB
    # field ranked 8th, all under the confident header.
    page(el(mmid="263", tag="input", value="10 Aug 2026"),
         el(mmid="230", tag="input", placeholder="First Name"),
         el(mmid="240", tag="input", placeholder="Last Name"))
    out = await run("date of birth field")
    check("F23 a query no element explains is reported as no confident match",
          "NO CONFIDENT MATCH" in out or "No elements matched" in out,
          out.splitlines()[0][:96])

    # NEGATIVE CONTROL. The gate must stay off for short queries, where matching
    # one word IS the whole query — this is what F1/F8/F14 depend on, and a
    # coverage rule that ignores role words silently breaks non-Latin pages.
    page(el(mmid="12", tag="textarea", placeholder="2人冒充保安看演唱会被罚", w=300, h=30))
    out = await run("search box")
    check("F24 ...while a two-word query still reaches a control via a role word",
          "ref_12" in out and "Found" in out.splitlines()[0],
          out.splitlines()[0][:96])

    # F25/F26: near= is CONTENT coverage. Excluding it left pages whose only word
    # matches came from adjacent text with no text coverage at all, so they fell
    # through to the ROLE-word fallback that every combobox satisfies — and the
    # two failures point in OPPOSITE directions, which is why one rule fixes both.
    page(el(mmid="312", tag="input", role="combobox", near="Select State"),
         el(mmid="275", tag="input", role="combobox"))
    out = await run("Select City dropdown")
    # F29: the live case F25's fixture did not cover. "Select State" is TWO tokens,
    # one of which ("select") is a role word that also appears in the wrong element's
    # label -- so it covered the query on its own and a bare "Found 1 element(s)
    # matching" header returned near="Select City". An agent trusting that sets City
    # believing it set State. A role word names a TYPE and can never identify a
    # particular element, so it no longer counts as content coverage.
    page(el(mmid="325", tag="input", role="combobox", near="Select City"),
         el(mmid="400", tag="button", label="Submit", name="Submit"))
    out = await run("Select State")
    check("F29 a role word in the wrong element's label is not content coverage",
          "NO CONFIDENT MATCH" in out or "No elements matched" in out,
          out.splitlines()[0][:96])

    check("F25 a dropdown that is not the one asked for is not confident",
          "NO CONFIDENT MATCH" in out, out.splitlines()[0][:96])

    # F30/F31: A SUBTREE CONCATENATION IS NOT AN IDENTITY. AccName's
    # name-from-content fallback hands a generic container the text of everything
    # inside it, so demoqa's outermost div carried all 390 characters of the page.
    # That matches ANY query about ANYTHING on it, and it kept winning under a
    # confident header — verified live with two unrelated queries returning the same
    # ref_4. #29 removed it from the tree LISTING and recorded the defect as fixed,
    # but the tree is a serializer and this scorer reads the structured array, so the
    # blob was still the matchable identity. The collector marks it `subtreeName`.
    # F31 is the guard that this is a targeted exclusion, not a demotion of
    # containers: the same element remains reachable by every field that IS its own.
    _blob = ("Elements Forms Practice Form Student Registration Form Name Email Gender "
             "Male Female Other Mobile Date of Birth Subjects Hobbies Sports Reading "
             "Music Picture Current Address State and City Submit "
             "© 2013-2026 TOOLSQA.COM | ALL RIGHTS RESERVED.")
    page(el(mmid="4", tag="div", label=_blob, name=_blob, subtreeName=True, w=1900, h=1370),
         el(mmid="283", tag="input", type="checkbox", name="Sports", w=16, h=16, y=400))
    out = await run("Sports hobbies checkbox")
    check("F30 a container whose name is its whole subtree does not win the query",
          "ref_4" not in out, out.splitlines()[0][:100]
          + (" | " + next((l.strip()[:60] for l in out.splitlines() if "ref_" in l), "")))
    check("F30b ...and the real control is what comes back",
          "ref_283" in out, next((l.strip()[:70] for l in out.splitlines() if "ref_" in l), out[:70]))

    page(el(mmid="4", tag="div", role="navigation", label=_blob, name=_blob,
            subtreeName=True, near="Site navigation", w=1900, h=1370))
    out = await run("navigation")
    check("F31 ...while that element is still findable by what IS its own (role, near=)",
          "ref_4" in out, out.splitlines()[0][:100])

    # F32-F35: THE CONFIDENCE GATE HAD A CLIFF AT THREE TOKENS, so every TWO-word
    # query was effectively ungated — one covered word out of two earned a confident
    # header. Each of these came back under `Found N element(s) matching` in a live
    # audit, and the first is the one that does real damage: an agent told to enter a
    # passport number types it into the phone field.
    page(el(mmid="256", tag="input", placeholder="Mobile Number", near="Mobile(10 Digits)"),
         el(mmid="249", tag="input", type="radio", name="Other", value="Other"),
         el(mmid="286", tag="input", type="checkbox", name="Reading", value="2"))
    _pn = await run("Passport Number")
    check("F32 a 2-token query covering ONE word is not confident",
          "NO CONFIDENT MATCH" in _pn or "No elements matched" in _pn,
          _pn.splitlines()[0][:96])
    _oc = await run("Other Currency")
    check("F32b ...nor 'Other Currency' answered by a radio named Other",
          "NO CONFIDENT MATCH" in _oc or "No elements matched" in _oc,
          _oc.splitlines()[0][:96])

    # The positive control, and the reason the fix is a curve rather than a bar:
    # BOTH words match one element, so it must still be confident — and the
    # neighbours that cover only "name" must not be.
    page(el(mmid="230", tag="input", placeholder="First Name", near="Name"),
         el(mmid="233", tag="input", placeholder="Last Name", near="Name"),
         el(mmid="238", tag="input", placeholder="name@example.com", near="Email"))
    _fn = await run("First Name")
    _fn_rows = [l for l in _fn.split("NO CONFIDENT MATCH")[0].splitlines()
                if l.strip().startswith("ref_")]
    check("F33 a 2-token query where BOTH words match one element IS confident,"
          " and its one-word neighbours are not",
          "Found" in _fn.splitlines()[0] and any("ref_230" in l for l in _fn_rows)
          and not any(("ref_233" in l or "ref_238" in l) for l in _fn_rows),
          _fn.splitlines()[0][:70] + " | " + " ".join(l.strip()[:22] for l in _fn_rows))

    # And coverage now scales: 2 covered tokens no longer satisfy a long query.
    page(el(mmid="3553", tag="a", label="Support", name="Support"),
         el(mmid="3554", tag="a", label="Roadmap", name="Roadmap"))
    _long = await run("Introduction Why Vuetify Long-term support Roadmap Sponsors")
    check("F34 a 7-token query is not confident on 2 covered tokens",
          "NO CONFIDENT MATCH" in _long or "No elements matched" in _long,
          _long.splitlines()[0][:96])

    page(el(mmid="2229", tag="button", label="구독", name="구독",
            near="매일경제 08월 10일 05:52 구독"),
         el(mmid="528", tag="button", label="구독", name="구독"),
         el(mmid="549", tag="button", label="구독", name="구독"))
    out = await run("매일경제 구독 버튼")
    check("F26 ...while the one identified by its near= context IS confident",
          "Found" in out.splitlines()[0] and "ref_2229" in out.split("NO CONFIDENT MATCH")[0],
          out.splitlines()[0][:96])

    # F27: the Turkish dotted capital I. Unicode folds U+0130 to "i" + U+0307
    # COMBINING DOT ABOVE, so "İstanbul".casefold() != "istanbul". An agent types
    # lowercase ASCII, so EVERY correctly-spelled Turkish proper noun was
    # unreachable — measured live on ntv.com.tr, where the İstanbul weather link
    # was missed entirely (not even a weak match) while the İ-spelled query put it
    # first. The fix (fold, then drop combining marks) is accent-insensitive for
    # every script at once, which is what someone typing a query expects.
    page(el(mmid="29", tag="a", label="İstanbul 29°", name="İstanbul 29°"),
         el(mmid="30", tag="a", label="Hava durumu raporu", name="Hava durumu raporu"))
    out = await run("istanbul")
    check("F27 a lowercase-ASCII query reaches a Turkish İ-spelled label",
          "ref_29" in out and "Found" in out.splitlines()[0], out.splitlines()[0][:96])

    page(el(mmid="31", tag="input", placeholder="Αναζήτηση", w=300, h=30))
    out = await run("αναζητησης")
    check("F27b ...and an unaccented Greek query reaches an accented label",
          "ref_31" in out, out.splitlines()[0][:96])

    # F28: `under=` bypassed the marker — a 71-char Greek heading arrived as exactly
    # 40 chars with a trailing space and no signal, in find's own formatter.
    page(el(mmid="32", tag="a", label="Read more", name="Read more",
            underHeading="Γ. Γεραπετρίτης: Τηλεφωνική επικοινωνία με τον Ιρανό υπουργό Εξωτερικών"))
    out = await run("read more")
    _u = [l for l in out.splitlines() if "under=" in l]
    check("F28 a long under= heading is not cut in silence",
          bool(_u) and ("Εξωτερικών" in _u[0] or "…(+" in _u[0]),
          _u[0].strip()[-70:] if _u else "no under= emitted")

    page(NAV)
    out = await run("zzzq nonexistent widget")
    check("F9 a genuine miss says so and points at read_page",
          "No elements matched" in out and "read_page" in out, out[:96])

    # F32/F33: THE APP-SHELL CONTAINER. Its accessible name is the whole page
    # concatenated, so it matched any query and — because find prints the collector's
    # `line` — printed the whole blob. The scorer already refused to match on it
    # (`_borrowed`), and #29 already stopped the TREE printing it, so this was the two
    # halves of one tool disagreeing: ranked WITHOUT the label, rendered WITH it.
    # Measured live on a component-heavy app: find("Investor Relations Hub sidebar
    # link") returned the shell FIRST, ~2,500 chars of sidebar/dashboard/calendar,
    # pushing the real button to second place.
    _blob = "Toggle Sidebar Home Control Center Calendar Investor Relations Hub RevOps Hub"
    page(el(mmid="80", tag="div", label=_blob, text=_blob, subtreeName=True,
            line='ref_80 | div (container — the text here belongs to the elements inside it)', y=0),
         el(mmid="81", tag="button", label="Investor Relations Hub",
            text="Investor Relations Hub",
            line='ref_81 | button "Investor Relations Hub"', y=358))
    out = await run("Investor Relations Hub sidebar link")
    _first = next((l for l in out.splitlines() if "ref_8" in l), "")
    check("F32 the real control outranks the app-shell container whose name is the "
          "whole page",
          "ref_81" in _first, f"first result: {_first.strip()[:90]}")
    check("F33 ...and if the container appears at all, its borrowed text is not "
          "printed as its identity",
          _blob not in out, f"blob_printed={_blob in out}")

    # ---- F34-F37: DECLARED STATE IS QUERYABLE. The listing prints `(disabled)`
    # and the legend defines it, but find scored only page TEXT, so a query naming
    # a state could be answered only by reading a listing first — a whole model
    # turn to recover something the entry already carried. Measured in the live
    # head-to-head, where the other arm's model-backed find answered it in one
    # call and ours could not.
    SEL_OK = el(mmid="40", tag="select", name="Country", y=100)
    SEL_OFF = el(mmid="41", tag="select", name="Region", disabled=True, y=140)
    REQ = el(mmid="42", tag="input", name="Email", required=True, y=180)
    page(SEL_OK, SEL_OFF, REQ)

    out = await run("disabled select menu")
    _first = next((l for l in out.splitlines()[1:] if l.strip()), "")
    check("F34 a declared state in the query ranks the element that declares it",
          "ref_41" in _first, f"first result: {_first.strip()[:90]}")
    check("F34b ...confidently, not demoted to a weak match",
          "NO CONFIDENT MATCH" not in out, out.splitlines()[0][:90])

    # NEGATIVE CONTROL. Without it, "always boost" would pass F34 just as well.
    out = await run("required select menu")
    _first = next((l for l in out.splitlines()[1:] if l.strip()), "")
    check("F35 a state the element does not declare does not boost it",
          "ref_41" not in _first, f"first result: {_first.strip()[:90]}")

    # F29 GUARD, UNDER A NEW NAME. A state word is a type-level predicate — every
    # disabled control satisfies it and none is identified by it — so crediting it
    # as CONTENT coverage would re-open exactly what F29 closed: a confident answer
    # carried by a word that distinguishes nothing, while the tokens that actually
    # name the target match nothing at all.
    out = await run("disabled passport number field")
    check("F36 a state word does not buy confidence for an element nothing else "
          "in the query matches",
          "NO CONFIDENT MATCH" in out or "No elements matched" in out,
          out.splitlines()[0][:110])

    # ---- F37: A MISS ROUTES TO A TOOL THAT CAN ANSWER. Three shapes were tried
    # and the first two were wrong, each only visible live. "Call read_page" spends
    # a model turn (92-97% of a tool call, #38) to get something find is already
    # connected to. Fetching the listing instead returned a VIEWPORT-SCOPED page
    # (#6/#26) that did not contain the answer, under a footer naming `find` as the
    # cheapest recovery — the tool that had just failed. Dumping find's own
    # whole-page rows then spent 8,000 chars on 81 of 186 sidebar nav links and
    # still missed the target. Ordering a dump usefully requires KNOWING the
    # answer, which is what find just failed at.
    # The census is small, always fits, and is what lets the model write an exact
    # query: "6 select" + "pick more than one option" -> select[multiple].
    page(el(mmid="1", tag="select", name="Default select example"),
         el(mmid="2", tag="select", name="Multiple select example", y=50),
         el(mmid="3", tag="a", name="Docs", y=80))

    out = await run("zzqqx nothing like this at all")
    check("F37 a total miss reports what the page HOLDS, not just that it missed",
          "3 elements" in out and "2 select" in out, out.replace("\n", " ")[:150])
    check("F37b ...and names the tools that can answer exactly",
          "query_elements" in out and "search_page" in out, out.replace("\n", " ")[:150])
    check("F37c ...and explains that find ranks by WORDS, so the miss is informative",
          "WORDS" in out, out.replace("\n", " ")[:150])

    # THE WEAK PATH GETS IT TOO — this is where the turn is actually lost. A weak
    # match returns plausible-looking junk (live: four nav links for "the control I
    # would use to pick more than one option at once", while the correct
    # <select multiple> was listed with `multiple count=4`), which is worse than
    # nothing because it invites acting on it.
    # A genuinely WEAK match needs one shared content word out of many, so the
    # coverage gate demotes it rather than finding nothing at all. (Without this
    # page the query falls into the ZERO-match branch and the check passes for the
    # wrong reason — which is exactly what happened on the first run.)
    page(el(mmid="1", tag="button", name="Passport Office Directory"),
         el(mmid="2", tag="select", name="Country", y=50))
    out = await run("passport number entry for an international travel document")
    check("F37d a WEAK match is routed too, so the miss costs no extra turn",
          "NO CONFIDENT MATCH" in out and "query_elements" in out,
          out.splitlines()[0][:100])
    check("F37e ...and says WHY a lexical matcher missed, not just that it did",
          "LEXICAL" in out, out.splitlines()[0][:120])

    # DEGRADATION CONTROL: nothing collected at all -> no census to report, and the
    # tool must still return a sentence rather than a bare header.
    page()
    out = await run("anything")
    check("F37f an empty page still answers in words, not an empty string",
          out.strip() != "" and "No elements matched" in out, out[:110])

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} find checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

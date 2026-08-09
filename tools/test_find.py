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


def page(*entries):
    """Install a fake bridge returning these structured entries."""
    class FB:
        connected = True

        async def call(self, op, **kw):
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

    page(NAV)
    out = await run("zzzq nonexistent widget")
    check("F9 a genuine miss says so and points at read_page",
          "No elements matched" in out and "read_page" in out, out[:96])

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} find checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

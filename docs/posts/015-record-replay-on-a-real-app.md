# Record once, replay forever — and the bug that found

*Draft. Not posted.*

---

ChromeBridge can watch an agent drive a browser and compile what it did into a
replayable test. No DOM paths, no selectors you maintain, no model call per
step. Today I pointed it at a live e-commerce SPA for the first time and it
found a bug in itself within thirty seconds.

## What I recorded

A grocery catalogue. Russian labels, a Vue app that paints its products after
the document commits, forty product cards that each carry an identically-named
«Добавить» button. I searched for an olive, scoped a read to the card the
search named, clicked its add button, and checked that the remove button had
appeared.

Three steps. Here is what the recorder kept:

```json
"require": {
  "path": "/e7_cb_grocat/produkty_11/bench_grocery_category",
  "search": { "pattern": "Оливки", "min": 1, "observed": 1 },
  "query":  { "selector": "[aria-label=\"Убрать\"]", "count": 0 }
},
"targets": {
  "ref": {
    "level": 2,
    "desc": { "tag": "button", "type": "button", "name": "Добавить",
              "section": "main", "under": "Консервы" },
    "full": { "...": "...", "near": "229 ₽" }
  }
},
"expect": {
  "query": { "selector": "[aria-label=\"Убрать\"]", "count": 1 }
}
```

Three things in there are worth pointing at.

**The precondition.** `count: 0` on the remove button means the flow declares
that it starts from an empty cart. I never wrote that; it came from an
observation I made before I clicked anything.

**The target is a description, not a path.** `under: "Консервы"` is what
separates this «Добавить» from the other forty, and it is the page's own
section heading. If the app re-renders, re-sorts or re-mounts, a CSS path
breaks and this does not. `near: "229 ₽"` is the fallback, kept for when the
first description stops being unique.

**The postcondition is falsifiable.** `count: 1` is only in the file because
the same check read `0` before the click. If it had read `1` both times the
recorder would have told me the assertion was worthless — it has a warning for
exactly that, and it fired on my first attempt.

## It refused three of my assertions

On that first attempt I also queried for a class that does not exist on this
page, and searched for text that is an accessible name rather than rendered
text. Both came back empty. The recorder would not compile them:

> **NOT recorded:** step 2's search for 'Убрать' found NOTHING, and nothing
> earlier in this recording ever found it. An absence is only evidence if the
> thing was there first, so this one was dropped rather than compiled into a
> requirement that it stay missing — which is what a mistyped pattern would
> become.

That is the failure mode that matters. A test asserting "this string is
absent", written from a typo, passes forever and protects nothing.

## Then the replay died

```
FAILED: 0/3 step(s) run in 0.0s.
  step 0 (tabs_create_mcp) raised:
  tabs_create_mcp() got an unexpected keyword argument 'tabId'
```

The runner fills in a tab id for every step — it has to, because a flow can
open a tab partway through and everything after it belongs there. And the tool
that opens a tab takes no arguments at all.

So **no flow that started the way our own documentation teaches could ever
replay**, and nothing in 224 offline tests could have caught it, because every
one of them builds its steps by hand. It took pointing the thing at a real app.

The fix asks the function's signature instead of keeping a list of tool names.
Lists like that go stale; this project deleted one earlier for going unupdated
three times in a single day.

## Both directions

```
PASS  bench-grocery-add-to-cart    3/3 step(s) in 0.84s
```

0.84 seconds, zero model calls. The same work took an agent about a dozen
turns to do the first time.

A green test that has never been seen to fail is not evidence of anything, so
I ran it twice in one session, which leaves the cart full:

```
FAIL  bench-grocery-add-to-cart    2/3 step(s) in 6.26s
      the app is not in the state this flow starts from:
      query_elements('[aria-label="Убрать"]') counted 1, recorded exactly 0.
      The count GREW. Causes that need different answers: a previous run of
      this flow left its own rows behind; the data changed underneath; or the
      page really does render more now.
      Stopped before step 2 (computer). Only the 2 navigation step(s) in
      front of it ran.
```

It stopped *before* the step that changes anything, and it listed three causes
without picking one. That second part is deliberate. A message that guesses at
a cause sends you down the wrong path with confidence, and this project has
shipped that mistake three times and written a test to stop a fourth.

## The honest part

This is one flow on one app. The locator half is measured properly — 12,030
controls across 37 sites for uniqueness, 2,726 descriptors at 0% wrong under
seven DOM mutations including a re-sort — but the record-and-replay loop
itself has now been exercised on a handful of real apps, not hundreds.

And a known gap, stated rather than buried: 59.4% of descriptors that need an
ordinal to disambiguate have nothing available to witness that ordinal. Those
are unprotected against a re-sort, the file says so, and nothing about today
changed it.

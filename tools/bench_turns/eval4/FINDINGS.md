# Eval 4 — defects found BY the eval

Logged as they arrive. **Nothing here is fixed while the eval is running**: the
two arms must face the same code, so changing the thing under test mid-run
invalidates the comparison (#19's interleaving discipline, applied to a
head-to-head instead of a threshold sweep).

---

## E4-D1 — `NOT DELIVERED` is a FALSE NEGATIVE for an in-iframe click (T1/cb)

`computer` left_click inside a same-origin iframe reported:

> `*** NOT DELIVERED: Chrome accepted the input command and the page recorded
> no event, so nothing landed. This tab's trusted-input channel is dead …
> VERIFIED RECOVERY: open a new tab`

**The click landed.** In the same batch the field went ¥5 → ¥30 and
`aria-valuenow` 5 → 30 (exactly one step of 25), and the read's own readiness
banner reported `1 @aria-valuenow` change.

Cause: #56's delivery probe arms a capturing listener on the **top** document,
and an event dispatched into a nested browsing context is not observable there.
So the probe reports "no event" for every in-iframe coordinate click.

Severity is higher than a wrong label, because the message **asserts a recovery
it has not verified** — "open a new tab" — which is #33's class and precisely
what `C15` exists to catch, inside the check added to stop a different silent
failure. #56's own `ID3` control says an unknown answer must claim nothing; an
iframe click produces a *confident* wrong answer instead.

Fix shape: arm the probe in the frame the click is dispatched into (the
coordinate resolver already knows the frame via `_frameShells` /
`resolveFrameSelector`), or — if the frame cannot be reached — fall back to
UNKNOWN and say nothing, which is the behaviour `ID3` already pins for the
navigating case.

## E4-D2 — `query_elements` does not reach into iframes (T1/cb)

`.ui-spinner input` and `.ui-spinner a` matched **nothing**, while an
iframe-scoped `read_page(ref_id=…)` listed those same elements. Two tools
disagreeing about one page, with nothing saying which is blind — the same shape
as #30's `near=` and #48's `include_text`, both of which were un-migrated older
paths.

`_queryElementsPage` walks the composed tree for shadow roots (and #48 taught
`include_text` to do so), but does not cross a frame boundary the way the
collector's `collectCrossFrames` does.

---

## T1 result — cb 7 calls, cic 19. Both answered ¥30 (referee: ¥30).

This is a **custom-widget** task, i.e. H4's interaction subset — the band
pre-registered as the one where we might be level or behind.

**What the OTHER arm hit**, recorded because the eval is also a survey of the
field and because a turn count alone hides it: its `find` returned a ref
described confidently as *"the currency select element with id 'currency'"* and
`form_input` on that exact ref failed twice with `Element type "SPAN" is not a
supported form input` — the ref resolves to a different element than the
description. Its `read_page` returned **no iframe content at all**, with nothing
indicating anything had been skipped, while its own `find` could see it. Its
`computer(action="key")` reported `Pressed 3 keys: Down Down Return` while the
select stayed unchanged — a success report for input that did not land, which
is the #10/#11/#12 family. And its `read_page` never reports a spinbutton's
current value, so the answer had to come from a zoomed screenshot rather than
the structured listing.

Ours hit the same iframe and cost 1 extra round trip to it (plus 1 to a
still-loading demo frame); theirs cost roughly 8 and required navigating
directly to the embedded document to make the select operable at all.

# Eval 4 closeout checklist

Written mid-run so nothing is left to memory. Work top to bottom; nothing is
published until step 3 passes.

- [ ] **1. Last pair logged.** `python collect.py --write` then confirm
      `20 complete pair(s)` and no `REFUSED` / re-run warnings.

- [ ] **2. Restore the consent gate.** `sh tools/bench_turns/eval4/restore_gate.sh`
      — flips the flag, checks `git diff` is clean for `background.js`, and runs
      `test_permissions.js` refusing any "gate off" caveat.
      **Then reload the extension** at `chrome://extensions` and confirm an op
      on a known-ungranted origin is REFUSED. #47 measured a restore silently
      not taking for several minutes, because the flag is a module-scope const
      and the bridge keeps the worker alive. Disk is not browser.

- [ ] **3. Publish nothing before step 2 passes.** Amendment 5 says the eval
      says NOTHING about what the consent model costs, and that sentence is
      only honest if the gate is actually back on.

- [ ] **4. Run `analyse.py`** and quote the leave-one-host-out RANGE, not the
      point estimate. Report H4 with the same prominence as H1 whichever way it
      lands — it was pre-registered as a test we may fail.

- [ ] **5. Tabs.** This eval accumulates tabs in the user's REAL Chrome, because
      the prompt forbids closing tabs an agent did not open. Count them, close
      only what is in the agent's own group, and **report the rest to the user
      rather than closing it** — some may be theirs. One of ours was destroyed
      mid-eval by the other arm's tabId-less navigate (T12), which is exactly
      why this is not a unilateral cleanup.

- [ ] **6. Deferred defects.** E4-D1..D9 are logged in FINDINGS.md and were
      deliberately NOT fixed mid-run. Triage them after, not during.
      D7 (does the structural readiness banner fire usefully on
      post-navigation reads?) and D9 (how long after each kind of click does
      `onBeforeNavigate` land?) are MEASUREMENTS, and both need the browser.

- [ ] **7. CLAUDE.md entry** — numbers from `analyse.py`, not from memory, and
      the two harness defects (Amendment 6) stated as part of the result rather
      than as a footnote.

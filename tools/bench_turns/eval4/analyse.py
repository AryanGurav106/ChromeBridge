"""EVAL 4 analysis — the interaction eval.

Test, bars and task set were fixed in PREREG.md BEFORE any run. Amendment 1
(sample concentration) and Amendment 2 (independent referee) were written after
the tasks arrived and before any run existed. Nothing here is chosen after data.

Three things this prints that eval 3's did not, each required by the
pre-registration rather than added because a number looked good:

  * LEAVE-ONE-HOST-OUT. Three hosts supply three tasks each, so the top three
    are 41% of the sample. #73 measured exactly this failure on Mind2Web (one
    widget was 17% of 173 actions; leave-one-site-out spanned 95.1-98.1%), so
    the headline here must be quoted as a RANGE.
  * H4, the interaction-only subset. It is pre-registered as a test we may
    fail: eval 3 measured form-lookup at 0.88, essentially level. A null is
    publishable and is printed with the same prominence as a win.
  * ACHIEVABLE p beside every p. At small n a perfect sweep can be unable to
    clear p<0.05 (#47's six-task subset went 4/4 and the best reachable p at
    n=4 is 0.1250). A result that could not have cleared is not a failure to
    clear.
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import score                                        # noqa: E402

GT = json.load(open(os.path.join(HERE, "ground_truth.json")))
WEAK = set(GT.get("weak", []))
# Shapes, from PREREG. The three marked INTERACTION are H4's subset and were
# named before any task existed.
SHAPE = {"F": "multi-step form", "L": "filter/sort/page", "D": "drill-down",
         "A": "late-arriving", "N": "non-Latin+type", "W": "custom widget",
         "T": "data table"}
INTERACTION = {"F", "N", "W"}


def sign_p(k, n):
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n)


def graded(tid, ans):
    """Accept/reject from the REFEREE's key, never from the agent's confidence."""
    if not ans:
        return None
    a = ans.replace("−", "-").lower()
    g = GT["gt"][tid]
    for bad in g.get("reject", []):               # reject wins ties deliberately
        b = bad.replace("−", "-").lower()
        if b in a and not any(ok.replace("−", "-").lower() in a
                              for ok in g["accept"]):
            return False
    return any(ok.replace("−", "-").lower() in a for ok in g["accept"])


rows = [l.split("\t") for l in
        open(os.path.join(HERE, "runs.tsv")).read().strip().splitlines()[1:]]
res = {}
for _o, t, arm, ag in rows:
    res.setdefault(t, {})[arm] = score(ag.strip())

pairs, wrong = [], []
print(f"{'task':<5} {'shape':<18} {'host':<28} {'CB':>3} {'CIC':>4}  "
      f"{'win':<4} {'CBf':>4} {'CICf':>5}")
for t in sorted(res, key=lambda x: int(x[1:])):
    if t not in GT["gt"]:
        continue                                   # referee rejected it
    cb, cic = res[t]["cb"], res[t]["cic"]
    g = GT["gt"][t]
    sh, host = g["shape"], g.get("host", "?")
    win = ("CB" if cb["turns"] < cic["turns"] else
           "CIC" if cb["turns"] > cic["turns"] else "tie")
    for arm, r in (("cb", cb), ("cic", cic)):
        if graded(t, r["answer"]) is not True:
            wrong.append(f"{t}/{arm}: {str(r['answer'])[:60]!r}")
    pairs.append((t, sh, cb, cic, win, host))
    print(f"{t:<5} {sh} {SHAPE.get(sh, '?'):<16} {host:<28} {cb['turns']:>3} "
          f"{cic['turns']:>4}  {win:<4} {cb['first_content_turn']:>4} "
          f"{cic['first_content_turn']:>5}")


def h(label, sel, quiet=False):
    dec = [p for p in sel if p[4] != "tie"]
    k = sum(1 for p in dec if p[4] == "CB")
    n = len(dec)
    p = sign_p(max(k, n - k), n) if n else 1.0
    best = sign_p(n, n) if n else 1.0
    if not quiet:
        print(f"\n{label}: {k}/{n} to CB ({len(sel) - n} tie) p={p:.4f} "
              f"(best reachable at n={n}: {best:.4f}) -> "
              f"{'CLEARS p<0.05' if p < 0.05 else 'DOES NOT CLEAR'}"
              f"{'   [n too small to EVER clear — not a failure]' if best >= 0.05 else ''}")
    return k, n, p


h(f"H1 PRIMARY   (all {len(pairs)})      ", pairs)
if WEAK:
    h(f"H1 SECONDARY (strong only)", [p for p in pairs if p[0] not in WEAK])

# ---- H4: the test this eval exists for, and may fail -----------------------
sub = [p for p in pairs if p[1] in INTERACTION]
k4, n4, p4 = h(f"H4 INTERACTION-ONLY ({len(sub)})", sub)
print("    H4 was pre-registered as a test we may FAIL. Eval 3 measured "
      "form-lookup at 0.88 (level).")
print(f"    Result: {'CB ahead on a majority' if n4 and k4 * 2 > n4 else 'NOT ahead on a majority'}"
      " — report this with the same prominence as the headline either way.")

# ---- Amendment 1: leave-one-host-out --------------------------------------
hosts = sorted({p[5] for p in pairs})
print(f"\nLEAVE-ONE-HOST-OUT (Amendment 1 — top 3 hosts are 41% of the sample):")
span = []
for hh in hosts:
    sel = [p for p in pairs if p[5] != hh]
    k, n, p = h("", sel, quiet=True)
    span.append((k / n if n else 0.0, hh, k, n, p))
span.sort()
for frac, hh, k, n, p in (span[:1] + span[-1:]):
    print(f"  without {hh:<28} {k}/{n} to CB  p={p:.4f}")
if span:
    print(f"  => headline spans {span[0][0] * 100:.0f}%–{span[-1][0] * 100:.0f}% "
          f"of decided pairs. QUOTE THE RANGE, not the point.")

print("\nPER-SHAPE (descriptive, NO p-values — n~3 each, see PREREG):")
for s in "FLDANWT":
    sel = [p for p in pairs if p[1] == s]
    if not sel:
        continue
    w = sum(1 for p in sel if p[4] == "CB")
    l = sum(1 for p in sel if p[4] == "CIC")
    cbt = sum(p[2]["turns"] for p in sel)
    cict = sum(p[3]["turns"] for p in sel)
    star = "  <- H4 subset" if s in INTERACTION else ""
    print(f"  {s} {SHAPE[s]:<18} CB {w}  CIC {l}  tie {len(sel) - w - l}   "
          f"turns {cbt} v {cict}   ratio {cbt / cict if cict else 0:.2f}{star}")

med = lambda v: sorted(v)[len(v) // 2]
cbf = [p[2]["first_content_turn"] for p in pairs]
cicf = [p[3]["first_content_turn"] for p in pairs]
print(f"\nH2 first-content (REPLICATION): CB median {med(cbf)} | CIC median "
      f"{med(cicf)} -> {'MET' if med(cbf) <= 2 and med(cbf) < med(cicf) else 'NOT MET'}")
n1 = sum(1 for p in pairs if p[2]["one_turn_start"])
print(f"H3 one-turn start: {n1}/{len(pairs)} | ceremony CB "
      f"{sum(p[2]['ceremony_calls'] for p in pairs)} v CIC "
      f"{sum(p[3]['ceremony_calls'] for p in pairs)}")
print(f"\nTOTAL turns: CB {sum(p[2]['turns'] for p in pairs)} | "
      f"CIC {sum(p[3]['turns'] for p in pairs)}")
print(f"CORRECTNESS falsifier: {len(wrong)} graded-wrong of {2 * len(pairs)}"
      + ("" if not wrong else "  -> " + "; ".join(wrong)))
print("\nNOT A BAR: wall clock, unless the per-task median gap exceeds the "
      "~47s/task drift floor (#35, #41).")

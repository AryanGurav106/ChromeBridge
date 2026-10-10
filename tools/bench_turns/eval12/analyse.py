"""Compute the PRE-REGISTERED analysis. Nothing here chooses a test after seeing
data: the test, the bar and the two task sets were fixed in PREREG.md and
AMENDMENT 1 before any run existed."""
import json, math, subprocess, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import score                                   # noqa: E402

STRONG = {"T3", "T4", "T5", "T6", "T7", "T10"}             # AMENDMENT 1


def sign_p(k, n):
    """Two-tailed exact sign test: P(at least k of n, either direction)."""
    tail = sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n
    return min(1.0, 2 * tail)


rows = [l.split("\t") for l in
        open(os.path.join(HERE, (sys.argv[1] if len(sys.argv)>1 else "runs.tsv"))).read().strip().splitlines()[1:]]
res = {}
for ordn, task, arm, agent in rows:
    res.setdefault(task, {})[arm] = score(agent.strip())

print(f"{'task':<5} {'CB':>3} {'CIC':>4}  {'win':<4} "
      f"{'CBfirst':>7} {'CICfirst':>8}  {'1turn':>5} {'CBcer':>5} {'CICcer':>6}")
pairs = []
for t in sorted(res, key=lambda x: int(x[1:])):
    cb, cic = res[t]["cb"], res[t]["cic"]
    win = "CB" if cb["turns"] < cic["turns"] else ("CIC" if cb["turns"] > cic["turns"] else "tie")
    pairs.append((t, cb, cic, win))
    print(f"{t:<5} {cb['turns']:>3} {cic['turns']:>4}  {win:<4} "
          f"{str(cb['first_content_turn']):>7} {str(cic['first_content_turn']):>8}  "
          f"{str(cb['one_turn_start']):>5} {cb['ceremony_calls']:>5} {cic['ceremony_calls']:>6}")


def h1(label, subset):
    sel = [p for p in pairs if p[0] in subset]
    dec = [p for p in sel if p[3] != "tie"]
    k = sum(1 for p in dec if p[3] == "CB")
    n = len(dec)
    p = sign_p(max(k, n - k), n) if n else 1.0
    # The best p ACHIEVABLE at this n -- an n too small to ever reach 0.05 is
    # underpowered, which is a different statement from "disagrees".
    best = sign_p(n, n) if n else 1.0
    print(f"\n{label}: {k}/{n} decided to CB ({len(sel)-n} tie(s)), "
          f"p = {p:.4f} -> {'CLEARS p<0.05' if p < 0.05 else 'TIE (fails bar)'}")
    print(f"    best p reachable at n={n} is {best:.4f}"
          f"{'  <-- CANNOT reach 0.05 at this n' if best >= 0.05 else ''}")
    return k, n, p


h1("H1 PRIMARY   (all 9 tasks)", set(res))
h1("H1 SECONDARY (6 strong)   ", STRONG)

cbf = sorted(p[1]["first_content_turn"] for p in pairs)
cicf = sorted(p[2]["first_content_turn"] for p in pairs)
med = lambda v: (v[len(v)//2] if len(v) % 2 else (v[len(v)//2-1]+v[len(v)//2])/2)
print(f"\nH2 turns-to-first-content: CB median {med(cbf)} {cbf} | "
      f"CIC median {med(cicf)} {cicf}")
print(f"   BAR: CB median <= 2 AND < CIC median -> "
      f"{'MET' if med(cbf) <= 2 and med(cbf) < med(cicf) else 'NOT MET'}")

n1 = sum(1 for p in pairs if p[1]["one_turn_start"])
print(f"\nH3 (descriptive, no bar): CB runs opening with a batch containing "
      f"tabs_create_mcp: {n1}/{len(pairs)}")
print(f"   CB ceremony calls total {sum(p[1]['ceremony_calls'] for p in pairs)} | "
      f"CIC {sum(p[2]['ceremony_calls'] for p in pairs)}")
print(f"   CB ToolSearch calls  {sum(p[1]['toolsearch'] for p in pairs)} | "
      f"CIC {sum(p[2]['toolsearch'] for p in pairs)}")
print(f"\nTOTAL turns: CB {sum(p[1]['turns'] for p in pairs)} | "
      f"CIC {sum(p[2]['turns'] for p in pairs)}")

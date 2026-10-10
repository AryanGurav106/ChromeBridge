"""EVAL 3 analysis. Test, bar and task sets were fixed in PREREG.md before any
run; AMENDMENT 1 dropped T7 and reworded T18 before any run existed."""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import score                                        # noqa: E402

GT = json.load(open(os.path.join(HERE, "ground_truth.json")))
WEAK = set(GT["weak"])
ARCH = {"A": "doc-lookup", "B": "search-flow", "C": "form-lookup",
        "D": "data-table", "E": "drill-down", "F": "non-Latin", "G": "SPA"}


def sign_p(k, n):
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n)


def graded(tid, ans):
    """Accept/reject from the REFEREE's key, never from the agent's confidence."""
    if not ans:
        return None
    a = ans.replace("−", "-").lower()
    g = GT["gt"][tid]
    for bad in g["reject"]:                       # reject wins ties deliberately
        b = bad.replace("−", "-").lower()
        if b in a and not any(ok.replace("−","-").lower() in a
                              for ok in g["accept"]):
            return False
    return any(ok.replace("−", "-").lower() in a for ok in g["accept"])


rows = [l.split("\t") for l in
        open(os.path.join(HERE, "runs.tsv")).read().strip().splitlines()[1:]]
res = {}
for _o, t, arm, ag in rows:
    res.setdefault(t, {})[arm] = score(ag.strip())

pairs, wrong = [], []
print(f"{'task':<5} {'arch':<12} {'CB':>3} {'CIC':>4}  {'win':<4} {'CBf':>4} {'CICf':>5}")
for t in sorted(res, key=lambda x: int(x[1:])):
    cb, cic = res[t]["cb"], res[t]["cic"]
    arch = GT["gt"][t]["archetype"]
    win = ("CB" if cb["turns"] < cic["turns"] else
           "CIC" if cb["turns"] > cic["turns"] else "tie")
    for arm, r in (("cb", cb), ("cic", cic)):
        if graded(t, r["answer"]) is not True:
            wrong.append(f"{t}/{arm}: {str(r['answer'])[:60]!r}")
    pairs.append((t, arch, cb, cic, win))
    print(f"{t:<5} {arch} {ARCH[arch]:<10} {cb['turns']:>3} {cic['turns']:>4}  "
          f"{win:<4} {cb['first_content_turn']:>4} {cic['first_content_turn']:>5}")


def h1(label, sel):
    dec = [p for p in sel if p[4] != "tie"]
    k = sum(1 for p in dec if p[4] == "CB"); n = len(dec)
    p = sign_p(max(k, n - k), n) if n else 1.0
    best = sign_p(n, n) if n else 1.0
    print(f"\n{label}: {k}/{n} to CB ({len(sel)-n} tie) p={p:.4f} -> "
          f"{'CLEARS p<0.05' if p < 0.05 else 'TIE (fails)'}"
          f"{'   [n too small to ever clear]' if best >= 0.05 else ''}")


h1("H1 PRIMARY   (all 19)     ", pairs)
h1("H1 SECONDARY (16 strong)  ", [p for p in pairs if p[0] not in WEAK])

print("\nPER-ARCHETYPE (descriptive, NO p-values -- n~3 each, see PREREG):")
for a in "ABCDEFG":
    s = [p for p in pairs if p[1] == a]
    if not s:
        continue
    w = sum(1 for p in s if p[4] == "CB"); l = sum(1 for p in s if p[4] == "CIC")
    cbt = sum(p[2]["turns"] for p in s); cict = sum(p[3]["turns"] for p in s)
    print(f"  {a} {ARCH[a]:<12} CB {w}  CIC {l}  tie {len(s)-w-l}   "
          f"turns {cbt} v {cict}   ratio {cbt/cict:.2f}")

med = lambda v: sorted(v)[len(v)//2]
cbf = [p[2]["first_content_turn"] for p in pairs]
cicf = [p[3]["first_content_turn"] for p in pairs]
print(f"\nH2 first-content: CB median {med(cbf)} | CIC median {med(cicf)} -> "
      f"{'MET' if med(cbf) <= 2 and med(cbf) < med(cicf) else 'NOT MET'}")
n1 = sum(1 for p in pairs if p[2]["one_turn_start"])
print(f"H3 one-turn start: {n1}/{len(pairs)} | ceremony CB "
      f"{sum(p[2]['ceremony_calls'] for p in pairs)} v CIC "
      f"{sum(p[3]['ceremony_calls'] for p in pairs)}")
print(f"\nTOTAL turns: CB {sum(p[2]['turns'] for p in pairs)} | "
      f"CIC {sum(p[3]['turns'] for p in pairs)}")
print(f"CORRECTNESS falsifier: {len(wrong)} graded-wrong of {2*len(pairs)}"
      + ("" if not wrong else "  -> " + "; ".join(wrong)))

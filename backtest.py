import csv, io, sys
from datetime import timedelta
from data import recuperer
from model import parse_date, ajuster, predire

code = sys.argv[1] if len(sys.argv) > 1 else "SP1"
test_s = sys.argv[2] if len(sys.argv) > 2 else "2526"
train_s = sys.argv[3].split(",") if len(sys.argv) > 3 else ["2324", "2425"]

def lire(s):
    raw = recuperer(s, code)
    out = []
    for r in csv.DictReader(io.StringIO(raw)):
        d = parse_date(r.get("Date", ""))
        if not d or r.get("FTHG", "") == "" or r.get("FTAG", "") == "":
            continue
        try:
            cotes = (float(r["B365H"]), float(r["B365D"]), float(r["B365A"]))
        except (KeyError, ValueError):
            cotes = None
        out.append((d, r["HomeTeam"], r["AwayTeam"], int(r["FTHG"]), int(r["FTAG"]), cotes))
    print(f"saison {s}: {len(out)} matchs")
    return out

tout, test = [], []
for s in train_s + [test_s]:
    lot_s = lire(s)
    tout += lot_s
    if s == test_s:
        test = lot_s
tout.sort(key=lambda m: m[0])
test.sort(key=lambda m: m[0])
debut = test[0][0] + timedelta(days=21)   # 3 semaines d'avance

n = n_b = 0
brier_m = brier_b = 0.0
choix = []
w0, fin = debut, test[-1][0]
while w0 <= fin:
    w1 = w0 + timedelta(days=7)
    lot = [m for m in test if w0 <= m[0] < w1]
    if lot:
        mod = ajuster([m[:5] for m in tout if m[0] < w0], w0)
        for d, h, a, gh, ga, cotes in lot:
            if h not in mod["att"] or a not in mod["att"]:
                continue
            p = predire(mod, h, a)
            res = "H" if gh > ga else ("D" if gh == ga else "A")
            o = {"H": res == "H", "D": res == "D", "A": res == "A"}
            bm = sum((p[k] - o[k]) ** 2 for k in "HDA")
            if cotes:
                inv = [1 / c for c in cotes]; s_ = sum(inv)
                pb = dict(zip("HDA", [x / s_ for x in inv]))
                brier_b += sum((pb[k] - o[k]) ** 2 for k in "HDA")
                brier_m += bm
                n_b += 1
            n += 1
            gagne = {"1X": res in "HD", "X2": res in "DA", "12": res in "HA"}
            k = max(("1X", "X2", "12"), key=lambda x: p[x])
            choix.append((p[k], gagne[k]))
    w0 = w1

print(f"\n{n} matchs testes ({n_b} avec cotes Bet365)")
if n_b:
    print(f"Erreur (Brier) modele : {brier_m / n_b:.4f}")
    print(f"Erreur (Brier) Bet365 : {brier_b / n_b:.4f}   (plus bas = meilleur)")
print("\nFiabilite du meilleur choix (1X / X2 / 12):")
for lo, hi in [(0.0, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]:
    g = [c for c in choix if lo <= c[0] < hi]
    if g:
        print(f"  prevu {lo:.0%}-{min(hi, 1):.0%}: {len(g):3d} matchs | moyenne prevue {sum(c[0] for c in g)/len(g):.1%} | reel {sum(c[1] for c in g)/len(g):.1%}")

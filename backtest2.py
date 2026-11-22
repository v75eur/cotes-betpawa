import csv, io, sys
from datetime import timedelta
import model
from data import recuperer
from model import parse_date, ajuster, predire

LIGUES = ("SP1", "E0", "I1", "D1", "F1")
TEST = "2526"
TRAIN = ["2324", "2425"]

def cotes(r, cols):
    try:
        c = tuple(float(r[k]) for k in cols)
        return c if all(x > 1 for x in c) else None
    except (KeyError, ValueError):
        return None

def lire(s, code):
    out = []
    for r in csv.DictReader(io.StringIO(recuperer(s, code))):
        d = parse_date(r.get("Date", ""))
        if not d or r.get("FTHG", "") == "" or r.get("FTAG", "") == "":
            continue
        out.append((d, r["HomeTeam"], r["AwayTeam"], int(r["FTHG"]), int(r["FTAG"]),
                    cotes(r, ("B365H", "B365D", "B365A")),
                    cotes(r, ("PSH", "PSD", "PSA"))))
    return out

DONNEES = {}
for code in LIGUES:
    tout, test = [], []
    for s in TRAIN + [TEST]:
        l = lire(s, code)
        tout += l
        if s == TEST:
            test = l
    tout.sort(key=lambda m: m[0])
    test.sort(key=lambda m: m[0])
    DONNEES[code] = (tout, test)

def normaliser(c):
    inv = [1 / x for x in c]
    s = sum(inv)
    return [x / s for x in inv]

def brier(p, r):
    o = (r == "H", r == "D", r == "A")
    return sum((x - y) ** 2 for x, y in zip(p, o))

def predictions(demi, prior):
    model.DEMI_VIE = demi
    model.PRIOR = prior
    res = []
    for code in LIGUES:
        tout, test = DONNEES[code]
        w0, fin = test[0][0] + timedelta(days=21), test[-1][0]
        while w0 <= fin:
            w1 = w0 + timedelta(days=7)
            lot = [m for m in test if w0 <= m[0] < w1]
            if lot:
                mod = ajuster([m[:5] for m in tout if m[0] < w0], w0)
                for d, h, a, gh, ga, cb, cp in lot:
                    if h not in mod["att"] or a not in mod["att"]:
                        continue
                    p = predire(mod, h, a)
                    r = "H" if gh > ga else ("D" if gh == ga else "A")
                    res.append(((p["H"], p["D"], p["A"]), r, cb, cp))
            w0 = w1
        print("  ligue", code, "ok", flush=True)
    return res

print("Calcul de base (patiente, ca peut prendre 1 a 2 minutes)...", flush=True)
base = predictions(180, 2)
sub = [x for x in base if x[2] and x[3]]
n = len(sub)
print(f"\n{len(base)} matchs testes, {n} avec cotes Bet365 ET Pinnacle")
if n == 0:
    sys.exit("Pas de cotes Pinnacle (PSH/PSD/PSA) dans ces fichiers.")

bm = sum(brier(x[0], x[1]) for x in sub) / n
bb = sum(brier(normaliser(x[2]), x[1]) for x in sub) / n
bp = sum(brier(normaliser(x[3]), x[1]) for x in sub) / n
print("\nErreur Brier (plus bas = meilleur):")
print(f"  Modele seul : {bm:.4f}")
print(f"  Bet365      : {bb:.4f}")
print(f"  Pinnacle    : {bp:.4f}")

print("\nMelange modele + Pinnacle (poids du modele):")
meilleur = (9, 0)
for w in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
    tot = 0.0
    for p, r, cb, cp in sub:
        q = normaliser(cp)
        pf = [w * a + (1 - w) * b for a, b in zip(p, q)]
        tot += brier(pf, r)
    b = tot / n
    if b < meilleur[0]:
        meilleur = (b, w)
    print(f"  {w:.0%} modele : {b:.4f}")
print(f"=> meilleur melange: {meilleur[1]:.0%} modele ({meilleur[0]:.4f}) contre Pinnacle seul {bp:.4f}")

print("\nReglages du modele seul (tous les matchs):")
for demi, prior in ((90, 2), (180, 2), (365, 2), (180, 1), (180, 4)):
    pr = base if (demi, prior) == (180, 2) else predictions(demi, prior)
    b = sum(brier(x[0], x[1]) for x in pr) / len(pr)
    print(f"  demi-vie {demi:3d}j, prior {prior}: {b:.4f}", flush=True)

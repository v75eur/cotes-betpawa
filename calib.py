import csv, io, json
from datetime import timedelta
from data import recuperer
from model import parse_date, ajuster, predire

def lire(s, code):
    out = []
    for r in csv.DictReader(io.StringIO(recuperer(s, code))):
        d = parse_date(r.get("Date", ""))
        if not d or r.get("FTHG", "") == "" or r.get("FTAG", "") == "":
            continue
        out.append((d, r["HomeTeam"], r["AwayTeam"], int(r["FTHG"]), int(r["FTAG"])))
    return out

pts = []
for code in ("SP1", "E0", "I1", "D1", "F1"):
    tout, test = [], []
    for s in ("2324", "2425", "2526"):
        l = lire(s, code)
        tout += l
        if s == "2526":
            test = l
    tout.sort(key=lambda m: m[0])
    test.sort(key=lambda m: m[0])
    w0, fin = test[0][0] + timedelta(days=21), test[-1][0]
    while w0 <= fin:
        w1 = w0 + timedelta(days=7)
        lot = [m for m in test if w0 <= m[0] < w1]
        if lot:
            mod = ajuster([m for m in tout if m[0] < w0], w0)
            for d, h, a, gh, ga in lot:
                if h not in mod["att"] or a not in mod["att"]:
                    continue
                p = predire(mod, h, a)
                res = "H" if gh > ga else ("D" if gh == ga else "A")
                for k, ok in (("1X", res in "HD"), ("X2", res in "DA"), ("12", res in "HA")):
                    pts.append((p[k], 1.0 if ok else 0.0))
        w0 = w1
    print("ok", code)

pts.sort()
blocs = []
for p, y in pts:
    blocs.append([p, y, 1])
    while len(blocs) > 1 and blocs[-2][1] / blocs[-2][2] > blocs[-1][1] / blocs[-1][2]:
        b = blocs.pop()
        blocs[-1][0] += b[0]; blocs[-1][1] += b[1]; blocs[-1][2] += b[2]
courbe = [(b[0] / b[2], b[1] / b[2]) for b in blocs]
json.dump(courbe, open("calib.json", "w"))
print(len(pts), "points,", len(courbe), "paliers")

import valeur
brut = sum((p - y) ** 2 for p, y in pts) / len(pts)
cal = sum((valeur.calibrer(p) - y) ** 2 for p, y in pts) / len(pts)
print(f"Brier brut {brut:.4f} -> calibre {cal:.4f} (mesure sur les memes donnees, donc un peu flatteuse)")

import csv, io, math, sys, difflib
from datetime import datetime, date
from data import recuperer

SAISONS = ["2627", "2526"]   # saison en cours + precedente
DEMI_VIE = 180               # jours: un match perd la moitie de son poids
PRIOR = 2.0                  # lissage pour equipes avec peu de matchs
MAXG = 10

def parse_date(s):
    for f in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None

def charger(code):
    matchs = []
    for s in SAISONS:
        try:
            raw = recuperer(s, code)
        except Exception as e:
            print(f"! saison {s} indisponible: {e}")
            continue
        n = 0
        for r in csv.DictReader(io.StringIO(raw)):
            d = parse_date(r.get("Date", ""))
            if not d or r.get("FTHG", "") == "" or r.get("FTAG", "") == "":
                continue
            matchs.append((d, r["HomeTeam"], r["AwayTeam"], int(r["FTHG"]), int(r["FTAG"])))
            n += 1
        print(f"saison {s}: {n} matchs joues")
    return matchs

def ajuster(matchs, aujourdhui=None):
    aujourdhui = aujourdhui or date.today()
    poids = [0.5 ** (max((aujourdhui - m[0]).days, 0) / DEMI_VIE) for m in matchs]
    equipes = sorted({m[1] for m in matchs} | {m[2] for m in matchs})
    W = sum(poids)
    mu_h = sum(w * m[3] for w, m in zip(poids, matchs)) / W
    mu_a = sum(w * m[4] for w, m in zip(poids, matchs)) / W
    mu = (mu_h + mu_a) / 2
    att = {t: 1.0 for t in equipes}
    dfn = {t: 1.0 for t in equipes}
    for _ in range(100):
        an = {t: PRIOR * mu for t in equipes}; ad = {t: PRIOR * mu for t in equipes}
        dn = {t: PRIOR * mu for t in equipes}; dd = {t: PRIOR * mu for t in equipes}
        for w, (d, h, a, gh, ga) in zip(poids, matchs):
            an[h] += w * gh;  ad[h] += w * mu_h * dfn[a]
            an[a] += w * ga;  ad[a] += w * mu_a * dfn[h]
            dn[h] += w * ga;  dd[h] += w * mu_a * att[a]
            dn[a] += w * gh;  dd[a] += w * mu_h * att[h]
        att = {t: an[t] / ad[t] for t in equipes}
        dfn = {t: dn[t] / dd[t] for t in equipes}
        ma = sum(att.values()) / len(att); md = sum(dfn.values()) / len(dfn)
        att = {t: v / ma for t, v in att.items()}
        dfn = {t: v / md for t, v in dfn.items()}
    return {"att": att, "dfn": dfn, "mu_h": mu_h, "mu_a": mu_a, "equipes": equipes}

def poisson(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)

def predire(mod, dom, ext):
    lh = mod["mu_h"] * mod["att"][dom] * mod["dfn"][ext]
    la = mod["mu_a"] * mod["att"][ext] * mod["dfn"][dom]
    ph = pd = pa = 0.0
    for i in range(MAXG + 1):
        for j in range(MAXG + 1):
            p = poisson(i, lh) * poisson(j, la)
            if i > j: ph += p
            elif i == j: pd += p
            else: pa += p
    t = ph + pd + pa
    ph, pd, pa = ph / t, pd / t, pa / t
    return {"lh": lh, "la": la, "H": ph, "D": pd, "A": pa,
            "1X": ph + pd, "X2": pd + pa, "12": ph + pa}

MOTS = {"fc", "cf", "ac", "as", "sc", "ud", "cd", "ca", "afc", "rc", "us", "ss", "calcio", "club"}
def nettoyer(nom):
    return " ".join(w for w in nom.lower().replace(".", "").split() if w not in MOTS)

def trouver(nom, equipes):
    cible = nettoyer(nom)
    propres = {nettoyer(e): e for e in equipes}
    if cible in propres:
        return propres[cible]
    for p, e in propres.items():
        if cible in p or p in cible:
            return e
    r = difflib.get_close_matches(cible, list(propres), n=1, cutoff=0.5)
    return propres[r[0]] if r else None

if __name__ == "__main__":
    code, nom_dom, nom_ext = sys.argv[1], sys.argv[2], sys.argv[3]
    matchs = charger(code)
    mod = ajuster(matchs)
    dom = trouver(nom_dom, mod["equipes"])
    ext = trouver(nom_ext, mod["equipes"])
    print(f"Equipes reconnues: {dom} vs {ext}")
    if not dom or not ext:
        sys.exit("Equipe introuvable. Equipes dispo: " + ", ".join(mod["equipes"]))
    p = predire(mod, dom, ext)
    print(f"Buts attendus: {p['lh']:.2f} - {p['la']:.2f}")
    print(f"Victoire dom {p['H']:.0%} | Nul {p['D']:.0%} | Victoire ext {p['A']:.0%}")
    for k in ("1X", "X2", "12"):
        print(f"{k}: {p[k]:.1%}  (cote juste {1 / p[k]:.2f})")

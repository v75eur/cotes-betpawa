import json, os

CAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calib.json")
POIDS_MODELE = 0.4      # 40% modele, 60% marche
SEUIL_EDGE = 0.03       # avantage minimum pour afficher une etoile
_courbe = None

def calibrer(p):
    global _courbe
    if _courbe is None:
        try:
            _courbe = json.load(open(CAL))
        except Exception:
            _courbe = []
    if not _courbe:
        return p
    if p <= _courbe[0][0]:
        return _courbe[0][1]
    if p >= _courbe[-1][0]:
        return _courbe[-1][1]
    for (x0, y0), (x1, y1) in zip(_courbe, _courbe[1:]):
        if x0 <= p <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (p - x0) / (x1 - x0)
    return p

def marche(cotes):
    inv = [1 / c for c in cotes]
    s = sum(inv)
    return [2 * x / s for x in inv]   # 1X+X2+12 vaut toujours 2

def resume(p, cotes):
    try:
        c = [float(x) for x in cotes]
        q = marche(c)
    except (ValueError, ZeroDivisionError):
        return ""
    parts = []
    for k, cote, qm in zip(("1X", "X2", "12"), c, q):
        pm = calibrer(p[k])
        pf = POIDS_MODELE * pm + (1 - POIDS_MODELE) * qm
        edge = pf * cote - 1
        etoile = "⭐" if edge >= SEUIL_EDGE else ""
        parts.append(f"{k} {pf:.0%} ({edge:+.0%}){etoile}")
    return " │ ".join(parts)

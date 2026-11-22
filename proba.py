from model import charger, ajuster, predire, trouver

CODES = {"Spain": "SP1", "England": "E0", "Italy": "I1",
         "France": "F1", "Germany": "D1"}
_cache = {}

def proba(ligue, e1, e2):
    code = CODES.get(ligue.split(" / ")[0])
    if not code:
        return None
    if code not in _cache:
        _cache[code] = ajuster(charger(code))
    mod = _cache[code]
    d = trouver(e1, mod["equipes"])
    e = trouver(e2, mod["equipes"])
    if not d or not e or d == e:
        return None
    return predire(mod, d, e)

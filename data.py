import os, time, urllib.request

DOSSIER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
BASE = "https://www.football-data.co.uk/mmz4281/{s}/{c}.csv"
SAISON_EN_COURS = "2627"
RAFRAICHIR_H = 6

def recuperer(saison, code):
    os.makedirs(DOSSIER, exist_ok=True)
    chemin = os.path.join(DOSSIER, f"{code}_{saison}.csv")
    existe = os.path.exists(chemin)
    if existe:
        age_h = (time.time() - os.path.getmtime(chemin)) / 3600
        if saison != SAISON_EN_COURS or age_h < RAFRAICHIR_H:
            return open(chemin, encoding="utf-8-sig", errors="ignore").read()
    try:
        raw = urllib.request.urlopen(BASE.format(s=saison, c=code), timeout=30).read()
        open(chemin, "wb").write(raw)
        return raw.decode("utf-8-sig", "ignore")
    except Exception:
        if existe:
            print(f"! reseau indisponible, copie locale utilisee ({saison})")
            return open(chemin, encoding="utf-8-sig", errors="ignore").read()
        raise

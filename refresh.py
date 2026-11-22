import os, urllib.request
from data import DOSSIER, BASE, SAISON_EN_COURS

os.makedirs(DOSSIER, exist_ok=True)
for code in ("SP1", "E0", "I1", "D1", "F1"):
    chemin = os.path.join(DOSSIER, f"{code}_{SAISON_EN_COURS}.csv")
    try:
        raw = urllib.request.urlopen(BASE.format(s=SAISON_EN_COURS, c=code), timeout=30).read()
        if b"HomeTeam" not in raw[:1000]:
            raise ValueError("fichier inattendu")
        open(chemin, "wb").write(raw)
        print("MAJ ok", code)
    except Exception as e:
        print("MAJ impossible", code, "- ancien fichier conserve:", e)

from data import recuperer
for code in ("SP1", "E0", "I1", "D1", "F1"):
    for saison in ("2324", "2425", "2526", "2627"):
        try:
            recuperer(saison, code)
            print("ok", code, saison)
        except Exception as e:
            print("ECHEC", code, saison, e)

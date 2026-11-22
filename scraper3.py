import asyncio, csv, io, os, time, urllib.request
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright
from data import recuperer
from model import parse_date, charger, ajuster, predire, trouver, poisson
from proba import CODES

URL = ("https://www.betpawa.bj/events?categoryId=2&marketId=1X2&day=all"
       "&competitions=11965,12097,12039,12127,12110")
NTFY_TOPIC = os.environ["NTFY_TOPIC_3"]
FUSEAU = ZoneInfo("Africa/Porto-Novo")
HEURES = None
SAISON_DEBUT = date(2026, 7, 1)
TAILLE_MAX = 3500
PAYS = {"Spain": "🇪🇸", "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Italy": "🇮🇹", "France": "🇫🇷", "Germany": "🇩🇪"}

JS = r"""() => {
  const results = [];
  const seen = new Set();
  document.querySelectorAll('div').forEach(div => {
    const text = div.innerText || '';
    if ((text.match(/Football \//g) || []).length !== 1) return;
    const lines = text.split('\n').map(l => l.replace('🔥','').trim()).filter(Boolean);
    if (lines.length < 6 || lines.length > 25) return;
    if (!/^\d{2}:\d{2}/.test(lines[0])) return;
    const d = text.match(/(\d{2}\/\d{2})/);
    const m = {heure: lines[0].split(' ')[0], date: d ? d[1] : '',
      equipe1: lines[1], equipe2: lines[2], ligue: lines[3].replace('Football / ', '')};
    const key = m.date + m.heure + m.equipe1 + m.equipe2;
    if (!seen.has(key)) { seen.add(key); results.push(m); }
  });
  return results;
}"""

_mod, _rows = {}, {}

def modele(code):
    if code not in _mod:
        _mod[code] = ajuster(charger(code))
    return _mod[code]

def lignes(code):
    if code not in _rows:
        out = []
        for s in ("2324", "2425", "2526", "2627"):
            try:
                raw = recuperer(s, code)
            except Exception:
                continue
            for r in csv.DictReader(io.StringIO(raw)):
                d = parse_date(r.get("Date", ""))
                if d and r.get("FTHG", "") != "" and r.get("FTAG", "") != "":
                    out.append((d, r))
        out.sort(key=lambda x: x[0])
        _rows[code] = out
    return _rows[code]

def v(r, k):
    try:
        return float(r[k])
    except (KeyError, ValueError, TypeError):
        return 0.0

def matchs_equipe(rows, t, n=None, lieu=None):
    ms = [(d, r) for d, r in rows
          if (r["HomeTeam"] == t and lieu in (None, "H"))
          or (r["AwayTeam"] == t and lieu in (None, "A"))]
    return ms[-n:] if n else ms

def vue(r, t):
    dom = r["HomeTeam"] == t
    gf = int(r["FTHG"] if dom else r["FTAG"])
    gc = int(r["FTAG"] if dom else r["FTHG"])
    return dom, gf, gc, (r["AwayTeam"] if dom else r["HomeTeam"])

def lettre(gf, gc):
    return "V" if gf > gc else ("N" if gf == gc else "D")

def niveaux(mod):
    sc = {t: mod["att"][t] / mod["dfn"][t] for t in mod["equipes"]}
    ordre = sorted(sc, key=lambda t: -sc[t])
    n = len(ordre)
    return {t: ("fort" if i < n / 3 else "faible" if i >= 2 * n / 3 else "moyen")
            for i, t in enumerate(ordre)}

def classement(rows):
    T = {}
    for d, r in rows:
        if d < SAISON_DEBUT:
            continue
        gh, ga = int(r["FTHG"]), int(r["FTAG"])
        for t, gf, gc in ((r["HomeTeam"], gh, ga), (r["AwayTeam"], ga, gh)):
            x = T.setdefault(t, [0, 0, 0, 0])
            x[1] += 1; x[2] += gf; x[3] += gc
            x[0] += 3 if gf > gc else (1 if gf == gc else 0)
    ordre = sorted(T, key=lambda t: (-T[t][0], -(T[t][2] - T[t][3]), -T[t][2]))
    return {t: (i + 1, *T[t]) for i, t in enumerate(ordre)}, len(ordre)

def stats(rows, t, n, lieu=None):
    ms = matchs_equipe(rows, t, n, lieu)
    if not ms:
        return None
    S = {k: 0.0 for k in ("pts", "gf", "gc", "tir", "tirc", "cad", "cadc",
                          "cor", "corc", "fau", "jau", "rou", "cs")}
    for d, r in ms:
        dom, gf, gc, _ = vue(r, t)
        p, q = ("H", "A") if dom else ("A", "H")
        S["gf"] += gf; S["gc"] += gc
        S["tir"] += v(r, p + "S"); S["tirc"] += v(r, q + "S")
        S["cad"] += v(r, p + "ST"); S["cadc"] += v(r, q + "ST")
        S["cor"] += v(r, p + "C"); S["corc"] += v(r, q + "C")
        S["fau"] += v(r, p + "F"); S["jau"] += v(r, p + "Y"); S["rou"] += v(r, p + "R")
        S["cs"] += 1 if gc == 0 else 0
        S["pts"] += 3 if gf > gc else (1 if gf == gc else 0)
    k = len(ms)
    res = {x: S[x] / k for x in S}
    res["pts"], res["cs"], res["n"] = S["pts"], S["cs"], k
    return res

def controle(s):
    tot = s["tir"] + s["tirc"] + s["cor"] + s["corc"]
    return 100 * (s["tir"] + s["cor"]) / tot if tot else 50.0

def tendances(rows, t, n=8):
    ms = matchs_equipe(rows, t, n)
    if not ms:
        return None
    o25 = btts = cs = fts = h1 = h2 = nht = 0
    for d, r in ms:
        dom, gf, gc, _ = vue(r, t)
        o25 += gf + gc >= 3
        btts += gf > 0 and gc > 0
        cs += gc == 0
        fts += gf == 0
        try:
            hf = int(r["HTHG" if dom else "HTAG"])
            h1 += hf; h2 += gf - hf; nht += 1
        except (KeyError, ValueError):
            pass
    k = len(ms)
    return {"n": k, "o25": o25 / k, "btts": btts / k, "cs": cs / k, "fts": fts / k,
            "h1": h1 / nht if nht else None, "h2": h2 / nht if nht else None}

def forme_detail(rows, t, niv, n=6):
    out, par = [], {"fort": [0, 0], "moyen": [0, 0], "faible": [0, 0]}
    for d, r in matchs_equipe(rows, t, n):
        dom, gf, gc, o = vue(r, t)
        L = lettre(gf, gc)
        nv = niv.get(o, "?")
        out.append(f"   {L} {gf}-{gc} {'dom' if dom else 'ext'} vs {o} ({nv})")
        if nv in par:
            par[nv][0] += 3 if L == "V" else (1 if L == "N" else 0)
            par[nv][1] += 1
    res = " · ".join(f"{k}s: {p[0]} pts/{p[1]} m" for k, p in par.items() if p[1])
    return out, res

def communs(rows, a, b, auj):
    depuis = auj - timedelta(days=400)
    oa, ob = {}, {}
    for t, dic in ((a, oa), (b, ob)):
        for d, r in matchs_equipe(rows, t):
            if d >= depuis:
                dic.setdefault(vue(r, t)[3], []).append((d, r))
    com = [o for o in oa if o in ob and o not in (a, b)]
    com.sort(key=lambda o: -max(oa[o][-1][0], ob[o][-1][0]))
    return com, oa, ob

def diff_moy(dic, t, com):
    g = [vue(r, t)[1] - vue(r, t)[2] for o in com for d, r in dic[o]]
    return (sum(g) / len(g), len(g)) if g else (0.0, 0)

def res_txt(d, r, t):
    dom, gf, gc, _ = vue(r, t)
    return f"{lettre(gf, gc)} {gf}-{gc} {'dom' if dom else 'ext'}"

def grille(lh, la):
    g = {(i, j): poisson(i, lh) * poisson(j, la) for i in range(9) for j in range(9)}
    t = sum(g.values())
    return {k: x / t for k, x in g.items()}

def sections(m, auj):
    n1, n2 = m["equipe1"], m["equipe2"]
    code = CODES.get(m["ligue"].split(" / ")[0])
    if not code:
        return ["Ligue non couverte par le modele."]
    mod = modele(code)
    d, e = trouver(n1, mod["equipes"]), trouver(n2, mod["equipes"])
    if not d or not e or d == e:
        return ["Equipe non reconnue par le modele."]
    rows = lignes(code)
    niv = niveaux(mod)
    p = predire(mod, d, e)
    g = grille(p["lh"], p["la"])
    pr = lambda f: sum(q for (i, j), q in g.items() if f(i, j))
    o15, o25, o35 = pr(lambda i, j: i + j >= 2), pr(lambda i, j: i + j >= 3), pr(lambda i, j: i + j >= 4)
    btts = pr(lambda i, j: i > 0 and j > 0)
    top = sorted(g.items(), key=lambda kv: -kv[1])[:3]
    S = []

    cl, nb = classement(rows)
    def pos(t):
        x = cl.get(t)
        return f"{x[0]}e/{nb} · {x[1]} pts en {x[2]} m · diff {x[3] - x[4]:+d}" if x else "classement indisponible"
    def repos(t):
        ms = matchs_equipe(rows, t)
        return f"{(auj - ms[-1][0]).days} j" if ms else "?"
    S.append("📍 CONTEXTE\n"
             f"   {d}: {pos(d)} · repos {repos(d)}\n"
             f"   {e}: {pos(e)} · repos {repos(e)}")

    S.append("🎯 PREVISION DU MODELE\n"
             f"   Buts attendus: {p['lh']:.2f} - {p['la']:.2f}\n"
             f"   1 {p['H']:.0%} │ X {p['D']:.0%} │ 2 {p['A']:.0%}\n"
             f"   1X {p['1X']:.0%} │ X2 {p['X2']:.0%} │ 12 {p['12']:.0%}\n"
             f"   +1.5 buts {o15:.0%} │ +2.5 {o25:.0%} │ +3.5 {o35:.0%}\n"
             f"   Les 2 equipes marquent: {btts:.0%}\n"
             "   Scores probables: " + ", ".join(f"{i}-{j} ({q:.0%})" for (i, j), q in top))

    s1, s2 = stats(rows, d, 6), stats(rows, e, 6)
    v1, v2 = stats(rows, d, 5, "H"), stats(rows, e, 5, "A")
    eq = [(d, s1, v1, "dom"), (e, s2, v2, "ext")]
    a = "⚔️ ATTAQUE\n"
    for t, s, vv, lab in eq:
        a += f"   {t}: force x{mod['att'][t]:.2f}"
        if s: a += f" · {s['gf']:.1f} buts/m · {s['tir']:.1f} tirs ({s['cad']:.1f} cadres)"
        if vv: a += f" · {lab}: {vv['gf']:.1f} buts/m"
        a += "\n"
    S.append(a.rstrip())
    a = "🛡️ DEFENSE (sous x1.00 = solide)\n"
    for t, s, vv, lab in eq:
        a += f"   {t}: force x{mod['dfn'][t]:.2f}"
        if s: a += f" · {s['gc']:.1f} enc./m · {s['cadc']:.1f} cadres subis · {s['cs']:.0f} clean sheet(s)/6"
        if vv: a += f" · {lab}: {vv['gc']:.1f} enc./m"
        a += "\n"
    S.append(a.rstrip())
    a = "🎛️ MILIEU / CONTROLE (estime: tirs + corners)\n"
    for t, s, vv, lab in eq:
        if s: a += f"   {t}: {controle(s):.0f}% du jeu · {s['cor']:.1f} corners/m · {s['tir'] - s['tirc']:+.1f} tirs de plus que l'adversaire\n"
    S.append(a.rstrip())
    a = "⚠️ DISCIPLINE (par match)\n"
    for t, s, vv, lab in eq:
        if s: a += f"   {t}: {s['fau']:.1f} fautes · {s['jau']:.1f} jaunes · {s['rou']:.2f} rouges\n"
    S.append(a.rstrip())

    for t in (d, e):
        lg, res = forme_detail(rows, t, niv)
        if lg:
            S.append(f"📈 FORME {t} (6 derniers, niveau de l'adversaire)\n" + "\n".join(lg) + (f"\n   Bilan: {res}" if res else ""))

    com, oa, ob = communs(rows, d, e, auj)
    if com:
        t = "🔗 ADVERSAIRES COMMUNS (400 derniers jours)\n"
        for o in com[:5]:
            t += f"   vs {o}: {d} {res_txt(*oa[o][-1], d)} │ {e} {res_txt(*ob[o][-1], e)}\n"
        da, na = diff_moy(oa, d, com)
        db, nbm = diff_moy(ob, e, com)
        t += f"   Diff. de buts/match vs ces {len(com)} equipes: {d} {da:+.2f} ({na} m) │ {e} {db:+.2f} ({nbm} m)"
        S.append(t)
    else:
        da = db = 0.0
        S.append("🔗 ADVERSAIRES COMMUNS\n   Aucun adversaire commun recent dans les donnees")

    t1, t2 = tendances(rows, d), tendances(rows, e)
    if t1 and t2:
        def lig(t, x):
            s = f"   {t}: +2.5 buts {x['o25']:.0%} · 2 marquent {x['btts']:.0%} · clean sheet {x['cs']:.0%} · sans marquer {x['fts']:.0%}"
            if x["h1"] is not None:
                s += f" · buts 1re MT {x['h1']:.1f} / 2e MT {x['h2']:.1f}"
            return s
        S.append("📊 TENDANCES (8 derniers matchs)\n" + lig(d, t1) + "\n" + lig(e, t2))

    ms = [(dd, r) for dd, r in rows if {r["HomeTeam"], r["AwayTeam"]} == {d, e}][-5:]
    if ms:
        w1 = sum(1 for dd, r in ms if lettre(*vue(r, d)[1:3]) == "V")
        w2 = sum(1 for dd, r in ms if lettre(*vue(r, e)[1:3]) == "V")
        S.append("🤝 CONFRONTATIONS DIRECTES\n" + "\n".join(
            f"   {dd:%d/%m/%y} {r['HomeTeam']} {r['FTHG']}-{r['FTAG']} {r['AwayTeam']}" for dd, r in ms)
            + f"\n   Bilan: {d} {w1} V │ {len(ms) - w1 - w2} N │ {e} {w2} V")
    else:
        S.append("🤝 CONFRONTATIONS DIRECTES\n   Aucune rencontre recente dans les donnees")

    L = []
    if p["H"] >= 0.5: L.append(f"Le modele voit {d} favori")
    elif p["A"] >= 0.5: L.append(f"Le modele voit {e} favori")
    else: L.append("Pas de favori net")
    if mod["att"][d] > mod["att"][e] * 1.15: L.append(f"Meilleure attaque: {d}")
    elif mod["att"][e] > mod["att"][d] * 1.15: L.append(f"Meilleure attaque: {e}")
    if mod["dfn"][d] < mod["dfn"][e] * 0.87: L.append(f"Meilleure defense: {d}")
    elif mod["dfn"][e] < mod["dfn"][d] * 0.87: L.append(f"Meilleure defense: {e}")
    if s1 and s2 and abs(controle(s1) - controle(s2)) >= 6:
        L.append(f"{d if controle(s1) > controle(s2) else e} domine le jeu (tirs et corners)")
    if s1 and s2 and abs(s1["pts"] - s2["pts"]) >= 5:
        L.append(f"Meilleure forme: {d if s1['pts'] > s2['pts'] else e}")
    if com and abs(da - db) >= 0.5:
        L.append(f"Mieux contre les adversaires communs: {d if da > db else e}")
    r1, r2 = repos(d), repos(e)
    try:
        if abs(int(r1.split()[0]) - int(r2.split()[0])) >= 3:
            L.append(f"Moins repose: {d if int(r1.split()[0]) < int(r2.split()[0]) else e}")
    except ValueError:
        pass
    tot = p["lh"] + p["la"]
    L.append("Match ouvert (beaucoup de buts attendus)" if tot >= 3 else
             "Match ferme (peu de buts attendus)" if tot <= 2.3 else "Nombre de buts moyen attendu")
    L.append("Ignore blessures, compositions et enjeu du match")
    S.append("🧠 LECTURE\n" + "\n".join(f"   • {x}" for x in L))
    return S

def messages_match(m, S):
    pays, _, nom = m["ligue"].partition(" / ")
    tete = (f"{PAYS.get(pays, '🌍')} {(nom or m['ligue']).upper()}\n"
            f"🔎 {m['equipe1']} 🆚 {m['equipe2']} · 🕒 {m['heure']}\n━━━━━━━━━━━━━━━━━━\n\n")
    msgs, cur = [], tete
    for sec in S:
        if len((cur + sec).encode()) > TAILLE_MAX and cur != tete:
            msgs.append(cur)
            cur = tete.split("\n")[1] + " (suite)\n\n"
        cur += sec + "\n\n"
    msgs.append(cur)
    return msgs

def send_ntfy(message, titre):
    req = urllib.request.Request(f"https://ntfy.sh/{NTFY_TOPIC}",
                                 data=message.encode("utf-8"), method="POST")
    req.add_header("Title", titre)
    req.add_header("Tags", "mag")
    try:
        urllib.request.urlopen(req)
        print("Notification envoyee.")
    except Exception as ex:
        print(f"Erreur ntfy: {ex}")

async def main():
    maintenant = datetime.now(FUSEAU)
    if HEURES and maintenant.hour not in HEURES and not os.environ.get("FORCER"):
        print("Hors heure d'envoi, rien a faire.")
        return
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(5000)
        for _ in range(10):
            await page.mouse.wheel(0, 4000)
            await page.wait_for_timeout(1000)
        matches = await page.evaluate(JS)
        await browser.close()
    auj = maintenant.strftime("%d/%m")
    print("Matchs lus:", len(matches))
    matches = [m for m in matches if m["date"] in ("", auj)]
    print("Matchs gardes pour aujourd'hui:", len(matches))
    if not matches:
        send_ntfy("😕 Aucun match a analyser pour le moment.", "Analyse matchs")
        return
    matches.sort(key=lambda x: x["heure"])
    for i, m in enumerate(matches, 1):
        try:
            msgs = messages_match(m, sections(m, maintenant.date()))
        except Exception as ex:
            print("Erreur analyse:", m["equipe1"], m["equipe2"], ex)
            continue
        for k, msg in enumerate(msgs, 1):
            send_ntfy(msg, f"Analyse {m['heure']} ({i}/{len(matches)})" + (f" p{k}" if len(msgs) > 1 else ""))
            time.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())

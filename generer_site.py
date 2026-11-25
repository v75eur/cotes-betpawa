import asyncio, json, os
from datetime import datetime
from zoneinfo import ZoneInfo


from playwright.async_api import async_playwright
import scraper as S1      # double chance
import scraper2 as S2     # repartition des mises
import scraper3 as S3     # analyse detaillee
from proba import proba

FUSEAU = ZoneInfo("Africa/Porto-Novo")
SORTIE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "data.json")


def iso(jm, ref):
    j, mo = map(int, jm.split("/"))
    return (ref.year + (1 if mo < ref.month - 6 else 0), mo, j)


def cle(m):
    return (m["date"], m["heure"], m["equipe1"], m["equipe2"])


def paires(m, c, p):
    out = []
    for x, y, nom in S2.PAIRES:
        r = S2.repartir(c[x], c[y])
        if r is None:
            continue
        m1, m2, tot, g = r
        z = [k for k in "1X2" if k not in (x, y)][0]
        r1, r2 = m1 * c[x], m2 * c[y]
        out.append({
            "paire": nom, "total": tot, "gain_min": round(g, 1),
            "comptes": [
                {"compte": 1, "mise": m1, "sur": S2.nom_res(m, x), "cote": c[x],
                 "recu": round(r1, 1), "gain": round(r1 - tot, 1)},
                {"compte": 2, "mise": m2, "sur": S2.nom_res(m, y), "cote": c[y],
                 "recu": round(r2, 1), "gain": round(r2 - tot, 1)},
            ],
            "perte_si": S2.nom_res(m, z), "perte": tot,
            "proba": round(S2.calibrer(p[nom]) * 100) if p else None,
        })
    return out


def double_chance(dc, p):
    out = []
    for k, val in (("1X", dc["1X"]), ("X2", dc["X2"]), ("12", dc["12"])):
        try:
            feu = float(val) <= S1.SEUIL
        except ValueError:
            feu = False
        out.append({"pari": k, "cote": val, "feu": feu,
                    "modele": round(p[k] * 100) if p else None})
    return out


def analyse(m, jour):
    try:
        sections = S3.sections(m, jour)
    except Exception as ex:
        print("Erreur analyse:", m["equipe1"], m["equipe2"], ex)
        return []
    out = []
    for s in sections:
        lignes = [l.strip() for l in s.split("\n") if l.strip()]
        if len(lignes) > 1:
            out.append({"titre": lignes[0], "lignes": lignes[1:]})
        elif lignes:
            out.append({"titre": "Analyse", "lignes": lignes})
    return out


def construire(dc_list, x12_list, maintenant):
    auj = maintenant.strftime("%d/%m")
    for m in dc_list + x12_list:
        m["date"] = m["date"] or auj
    base = {}

    def noeud(m):
        return base.setdefault(cle(m), {"date": m["date"], "heure": m["heure"], "ligue": m["ligue"],
                                        "equipe1": m["equipe1"], "equipe2": m["equipe2"]})

    for m in x12_list:
        d = noeud(m)
        try:
            d["c"] = {"1": float(m["c1"]), "X": float(m["cX"]), "2": float(m["c2"])}
        except ValueError:
            pass
    for m in dc_list:
        noeud(m)["dc"] = {"1X": m["c1X"], "X2": m["cX2"], "12": m["c12"]}

    matchs = []
    for d in sorted(base.values(), key=lambda d: (iso(d["date"], maintenant), d["heure"], d["ligue"])):
        try:
            p = proba(d["ligue"], d["equipe1"], d["equipe2"])
        except Exception:
            p = None
        pays, _, nom = d["ligue"].partition(" / ")
        matchs.append({
            "date": d["date"], "heure": d["heure"], "pays": pays, "drapeau": S1.PAYS.get(pays, "🌍"),
            "ligue": nom or d["ligue"], "equipe1": d["equipe1"], "equipe2": d["equipe2"],
            "cotes_1x2": d.get("c"),
            "double_chance": double_chance(d["dc"], p) if "dc" in d else None,
            "paires": paires(d, d["c"], p) if "c" in d else [],
            "analyse": analyse(d, maintenant.date()),
        })
    return {
        "source": "betPawa Bénin",
        "jour": f"{S1.JOURS[maintenant.weekday()]} {maintenant:%d/%m/%Y}",
        "maj": maintenant.isoformat(timespec="minutes"),
        "mise": [S2.MISE_MIN, S2.MISE_MAX], "gain_min": S2.GAIN_MIN, "seuil_feu": S1.SEUIL,
        "matchs": matchs,
    }


async def lire(page, url, js, defilements):
    await page.goto(url, wait_until="networkidle", timeout=60000)
    await page.wait_for_timeout(5000)
    await page.mouse.move(400, 500)
    stable, dernier = 0, -1
    liens = page.locator('a[href*="/event/"]')
    for _ in range(defilements):
        if await liens.count():
            await liens.last.scroll_into_view_if_needed()
        await page.keyboard.press("End")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.mouse.wheel(0, 3000)
        plus = page.locator("button:has-text('Show more'), button:has-text('Load more'), button:has-text('Voir plus')")
        if await plus.count():
            try:
                await plus.first.click(timeout=3000)
            except Exception:
                pass
        await page.wait_for_timeout(1500)
        n = await liens.count()
        stable = stable + 1 if n == dernier else 0
        dernier = n
        if stable >= 6:
            break
    print("Cartes chargees:", dernier)
    print("Hauteur page:", await page.evaluate("document.body.scrollHeight"))
    print("Boutons:", await page.evaluate("[...document.querySelectorAll('button')].map(b => b.innerText.trim()).filter(Boolean).slice(0, 40)"))
    return await page.evaluate(js)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            dc = await lire(await browser.new_page(), S1.URL, S1.JS, 250)
            x12 = await lire(await browser.new_page(), S2.URL, S2.JS, 250)
        finally:
            await browser.close()
    print("Double chance lus:", len(dc), "| 1X2 lus:", len(x12))
    data = construire(dc, x12, datetime.now(FUSEAU))
    print("Matchs publies sur le site:", len(data["matchs"]))
    os.makedirs(os.path.dirname(SORTIE), exist_ok=True)
    with open(SORTIE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    asyncio.run(main())

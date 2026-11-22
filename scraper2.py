import asyncio
import os
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright
from proba import proba
from valeur import calibrer

URL = ("https://www.betpawa.bj/events?categoryId=2&marketId=1X2&day=all"
       "&competitions=11965,12097,12039,12127,12110")
NTFY_TOPIC = os.environ["NTFY_TOPIC_2"]
FUSEAU = ZoneInfo("Africa/Porto-Novo")
GAINS = (50, 100)
TAILLE_MAX = 3500
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
PAYS = {"Spain": "🇪🇸", "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Italy": "🇮🇹", "France": "🇫🇷", "Germany": "🇩🇪"}
PAIRES = [("1", "X", "1X"), ("X", "2", "X2"), ("1", "2", "12")]

JS = r"""() => {
  const results = [];
  const seen = new Set();
  document.querySelectorAll('div').forEach(div => {
    const text = div.innerText || '';
    if ((text.match(/Football \//g) || []).length !== 1) return;
    const lines = text.split('\n').map(l => l.replace('🔥','').trim()).filter(Boolean);
    if (lines.length < 6 || lines.length > 25) return;
    if (!/^\d{2}:\d{2}/.test(lines[0])) return;
    const rest = lines.slice(4);
    const val = (label) => {
      const i = rest.indexOf(label);
      return i >= 0 ? rest[i + 1] : '';
    };
    const d = text.match(/(\d{2}\/\d{2})/);
    const m = {
      heure: lines[0].split(' ')[0],
      date: d ? d[1] : '',
      equipe1: lines[1],
      equipe2: lines[2],
      ligue: lines[3].replace('Football / ', ''),
      c1: val('1'), cX: val('X'), c2: val('2')
    };
    const key = m.date + m.heure + m.equipe1 + m.equipe2;
    if (!seen.has(key) && m.c1 && m.cX && m.c2) { seen.add(key); results.push(m); }
  });
  return results;
}"""

def arrondi(x):
    return int(x + 0.5)

def mise_min(o1, o2, S):
    for T in range(1, 200001):
        R = T / S
        m1, m2 = arrondi(R / o1), arrondi(R / o2)
        if m1 < 1 or m2 < 1:
            continue
        tot = m1 + m2
        if min(m1 * o1 - tot, m2 * o2 - tot) >= 1:
            return tot
    return None

def calcul(o1, o2, gain):
    S = 1 / o1 + 1 / o2
    if S >= 1:
        return None
    mm = mise_min(o1, o2, S)
    if mm is None:
        return None
    T = gain / (1 / S - 1)
    faible = T < mm
    if faible:
        T = mm
    R = T / S
    m1, m2 = arrondi(R / o1), arrondi(R / o2)
    tot = m1 + m2
    g = min(m1 * o1 - tot, m2 * o2 - tot)
    return m1, m2, tot, g, faible

def bloc_match(m):
    try:
        c = {"1": float(m["c1"]), "X": float(m["cX"]), "2": float(m["c2"])}
    except ValueError:
        return ""
    txt = f"🕒 {m['heure']} · {m['equipe1']} 🆚 {m['equipe2']}\n"
    txt += f"   1 {c['1']} │ X {c['X']} │ 2 {c['2']}\n"
    try:
        p = proba(m["ligue"], m["equipe1"], m["equipe2"])
    except Exception:
        p = None
    for a, b, nom in PAIRES:
        parts = []
        for g in GAINS:
            r = calcul(c[a], c[b], g)
            if r is None:
                parts = None
                break
            m1, m2, tot, gr, faible = r
            if faible:
                parts.append(f"⚠️ mini {m1}+{m2} F → +{gr:.0f} F")
            else:
                parts.append(f"+{g} F → {m1}+{m2} F")
        if parts is None:
            txt += f"   ❌ {nom}: ne passe pas\n"
            continue
        ligne = f"   ✅ {nom}: " + " │ ".join(parts)
        if p:
            ligne += f" │ 🤖 {calibrer(p[nom]):.0%}"
        txt += ligne + "\n"
    return txt + "\n"

def construire(matches, maintenant):
    entete = (f"⚽ COTES 1X2\n📅 {JOURS[maintenant.weekday()]} {maintenant:%d/%m/%Y}"
              f" · 🏟️ {len(matches)} matchs · gains {GAINS[0]} / {GAINS[1]} F\n"
              f"━━━━━━━━━━━━━━━━━━\n\n")
    groupes = {}
    for m in sorted(matches, key=lambda x: x["heure"]):
        groupes.setdefault(m["ligue"], []).append(m)
    blocs = []
    for ligue, ms in groupes.items():
        pays, _, nom = ligue.partition(" / ")
        t = f"{PAYS.get(pays, '🌍')} {(nom or ligue).upper()}\n"
        t += "".join(bloc_match(m) for m in ms)
        blocs.append(t)
    messages, courant = [], entete
    for b in blocs:
        if len((courant + b).encode()) > TAILLE_MAX and courant.strip():
            messages.append(courant)
            courant = ""
        courant += b
    messages.append(courant)
    messages[-1] += "✅ gain garanti → mise compte 1 + compte 2\n🤖 = proba du modele pour la paire\n🔞 Jouez avec moderation"
    return messages

def send_ntfy(message, titre):
    req = urllib.request.Request(f"https://ntfy.sh/{NTFY_TOPIC}",
                                 data=message.encode("utf-8"), method="POST")
    req.add_header("Title", titre)
    req.add_header("Tags", "soccer")
    try:
        urllib.request.urlopen(req)
        print("Notification envoyee.")
    except Exception as e:
        print(f"Erreur ntfy: {e}")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(5000)
        for _ in range(10):
            await page.mouse.wheel(0, 4000)
            await page.wait_for_timeout(1000)
        matches = await page.evaluate(JS)
        brut = await page.evaluate("() => document.body.innerText")
        await browser.close()
    maintenant = datetime.now(FUSEAU)
    auj = maintenant.strftime("%d/%m")
    print("Matchs lus:", len(matches), "| Dates vues:", sorted({m["date"] for m in matches}))
    matches = [m for m in matches if m["date"] in ("", auj)]
    print("Matchs gardes pour aujourd'hui:", len(matches))
    if not matches:
        print("Extrait de la page:", brut[:600].replace("\n", " | "))
        send_ntfy("😕 Aucun match 1X2 trouve pour le moment.", "Cotes 1X2")
        return
    msgs = construire(matches, maintenant)
    for i, msg in enumerate(msgs, 1):
        send_ntfy(msg, "Cotes 1X2" + (f" ({i}/{len(msgs)})" if len(msgs) > 1 else ""))

if __name__ == "__main__":
    asyncio.run(main())

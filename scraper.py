import asyncio
import os
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright

URL = "https://www.betpawa.bj/events?categoryId=2&marketId=Double%20Chance&day=today&competitions=11965,12097,12039,12127,12110"
NTFY_TOPIC = os.environ["NTFY_TOPIC"]
FUSEAU = ZoneInfo("Africa/Porto-Novo")
SEUIL = 1.20          # cotes <= SEUIL marquees avec 🔥
TAILLE_MAX = 3500     # octets max par notification ntfy

PAYS = {"Spain": "🇪🇸", "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Italy": "🇮🇹",
        "France": "🇫🇷", "Germany": "🇩🇪"}
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

JS = """() => {
  const results = [];
  const seen = new Set();
  document.querySelectorAll('div').forEach(div => {
    const text = div.innerText || '';
    if ((text.match(/Football \\//g) || []).length !== 1) return;
    const lines = text.split('\\n').map(l => l.replace('🔥','').trim()).filter(Boolean);
    if (lines.length < 8 || lines.length > 25) return;
    if (!/^\\d{2}:\\d{2}/.test(lines[0])) return;
    const val = (label) => {
      const i = lines.indexOf(label);
      return i >= 0 ? lines[i + 1] : '';
    };
    const d = text.match(/(\\d{2}\\/\\d{2})/);
    const m = {
      heure: lines[0].split(' ')[0],
      date: d ? d[1] : '',
      equipe1: lines[1],
      equipe2: lines[2],
      ligue: lines[3].replace('Football / ', ''),
      c1X: val('1X'), cX2: val('X2'), c12: val('12')
    };
    const key = m.date + m.heure + m.equipe1 + m.equipe2;
    if (!seen.has(key) && m.c1X) { seen.add(key); results.push(m); }
  });
  return results;
}"""

def cote(label, valeur):
    try:
        flamme = "🔥" if float(valeur) <= SEUIL else ""
    except ValueError:
        flamme = ""
    return f"{label} {flamme}{valeur}"

def bloc_ligue(ligue, matchs):
    pays, _, nom = ligue.partition(" / ")
    drapeau = PAYS.get(pays, "🌍")
    txt = f"{drapeau} {(nom or ligue).upper()}\n"
    for m in matchs:
        txt += f"🕒 {m['heure']} · {m['equipe1']} 🆚 {m['equipe2']}\n"
        txt += f"   {cote('1X', m['c1X'])} │ {cote('X2', m['cX2'])} │ {cote('12', m['c12'])}\n\n"
    return txt

def construire_messages(matches, maintenant):
    entete = (f"⚽ COTES DOUBLE CHANCE\n"
              f"📅 {JOURS[maintenant.weekday()]} {maintenant:%d/%m/%Y} · 🏟️ {len(matches)} matchs\n"
              f"━━━━━━━━━━━━━━━━━━\n\n")
    groupes = {}
    for m in sorted(matches, key=lambda x: x['heure']):
        groupes.setdefault(m['ligue'], []).append(m)
    blocs = [bloc_ligue(l, ms) for l, ms in groupes.items()]

    messages, courant = [], entete
    for b in blocs:
        if len((courant + b).encode()) > TAILLE_MAX and courant.strip():
            messages.append(courant)
            courant = ""
        courant += b
    messages.append(courant)
    messages[-1] += f"🔥 = cote ≤ {SEUIL}\n🔞 Jouez avec moderation"
    return messages

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(5000)
        matches = await page.evaluate(JS)
        await browser.close()

    maintenant = datetime.now(FUSEAU)
    auj = maintenant.strftime("%d/%m")
    print("Dates vues:", sorted({m['date'] for m in matches}))
    matches = [m for m in matches if m['date'] in ("", auj)]

    if not matches:
        send_ntfy("😕 Aucun match trouve pour le moment.", "Cotes betPawa")
        return
    messages = construire_messages(matches, maintenant)
    for i, msg in enumerate(messages, 1):
        titre = "Cotes betPawa" + (f" ({i}/{len(messages)})" if len(messages) > 1 else "")
        send_ntfy(msg, titre)

def send_ntfy(message, titre):
    req = urllib.request.Request(f"https://ntfy.sh/{NTFY_TOPIC}",
                                 data=message.encode('utf-8'), method='POST')
    req.add_header('Title', titre)   # titre ASCII uniquement (limite des en-tetes HTTP)
    req.add_header('Tags', 'soccer')
    try:
        urllib.request.urlopen(req)
        print("Notification envoyee.")
    except Exception as e:
        print(f"Erreur ntfy: {e}")

if __name__ == "__main__":
    asyncio.run(main())

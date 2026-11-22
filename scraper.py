import asyncio
import os
import urllib.request
from playwright.async_api import async_playwright

URL = "https://www.betpawa.bj/events?categoryId=2&marketId=Double Chance&day=all&competitions=11965,12097,12039,12127,12110"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "rick-bet")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print(f"Ouverture de {URL}...")
        await page.goto(URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(5000)
        matches = await page.evaluate("""() => {
            const results = [];
            const allDivs = document.querySelectorAll('div');
            allDivs.forEach(div => {
                const text = div.innerText || '';
                if (text.includes('Football /') && text.includes('1X') && text.includes('X2') && text.includes('12')) {
                    const lines = text.split('\\n').map(l => l.trim()).filter(l => l !== '');
                    if (lines.length >= 6) {
                        const heure = lines[0].split(' ')[0];
                        const equipe1 = lines[1];
                        const equipe2 = lines[2];
                        const ligue = lines[3].replace('Football / ', '');
                        const cote1X = lines[4].replace('1X', '').replace('🔥', '').trim();
                        const coteX2 = lines[5].replace('X2', '').trim();
                        const cote12 = lines[6].replace('12', '').trim();
                        results.push({ heure, equipe1, equipe2, ligue, cote1X, coteX2, cote12 });
                    }
                }
            });
            const uniqueResults = [];
            const seen = new Set();
            results.forEach(m => {
                const key = m.heure + m.equipe1 + m.equipe2;
                if (!seen.has(key) && m.equipe1 && m.equipe2) {
                    seen.add(key);
                    uniqueResults.push(m);
                }
            });
            return uniqueResults;
        }""")
        await browser.close()
        matches.sort(key=lambda x: x['heure'])
        if not matches:
            send_ntfy("Aucun match trouve.")
            return
        message = "Cotes Double Chance\n\n"
        for m in matches:
            message += f"{m['heure']} | {m['ligue']}\n"
            message += f"  {m['equipe1']} vs {m['equipe2']}\n"
            message += f"  1X: {m['cote1X']} | X2: {m['coteX2']} | 12: {m['cote12']}\n\n"
        send_ntfy(message)

def send_ntfy(message):
    print(f"Envoi sur ntfy ({len(message)} caracteres)...")
    data = message.encode('utf-8')
    req = urllib.request.Request(f"https://ntfy.sh/{NTFY_TOPIC}", data=data, method='POST')
    req.add_header('Title', 'Cotes betPawa')
    req.add_header('Tags', 'soccer')
    try:
        urllib.request.urlopen(req)
        print("Notification envoyee.")
    except Exception as e:
        print(f"Erreur ntfy: {e}")

if __name__ == "__main__":
    asyncio.run(main())

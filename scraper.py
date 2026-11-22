import asyncio
import os
import urllib.request
from playwright.async_api import async_playwright

URL = "https://www.betpawa.bj/events?categoryId=2&marketId=Double%20Chance&day=all&competitions=11965,12097,12039,12127,12110"
NTFY_TOPIC = os.environ["NTFY_TOPIC"]

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
    const m = {
      heure: lines[0].split(' ')[0],
      equipe1: lines[1],
      equipe2: lines[2],
      ligue: lines[3].replace('Football / ', ''),
      c1X: val('1X'), cX2: val('X2'), c12: val('12')
    };
    const key = m.heure + m.equipe1 + m.equipe2;
    if (!seen.has(key) && m.c1X) { seen.add(key); results.push(m); }
  });
  return results;
}"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(5000)
        matches = await page.evaluate(JS)
        await browser.close()

    matches.sort(key=lambda x: x['heure'])
    if not matches:
        send_ntfy("Aucun match trouve.")
        return
    for i in range(0, len(matches), 15):
        msg = ""
        for m in matches[i:i+15]:
            msg += f"{m['heure']} | {m['ligue']}\n"
            msg += f"  {m['equipe1']} vs {m['equipe2']}\n"
            msg += f"  1X: {m['c1X']} | X2: {m['cX2']} | 12: {m['c12']}\n\n"
        send_ntfy(msg)

def send_ntfy(message):
    req = urllib.request.Request(f"https://ntfy.sh/{NTFY_TOPIC}",
                                 data=message.encode('utf-8'), method='POST')
    req.add_header('Title', 'Cotes betPawa')
    req.add_header('Tags', 'soccer')
    try:
        urllib.request.urlopen(req)
        print("Notification envoyee.")
    except Exception as e:
        print(f"Erreur ntfy: {e}")

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import os
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright
from proba import proba

URL = "https://www.betpawa.bj/events?categoryId=2&marketId=Double%20Chance&day=all"
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

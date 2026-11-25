import asyncio
import os
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright
from proba import proba
from valeur import calibrer

URL = "https://www.betpawa.bj/events?categoryId=2&marketId=1X2&day=all"
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

MISE_MIN = 150
MISE_MAX = 200
GAIN_MIN = 20

def repartir(o1, o2):
    S = 1 / o1 + 1 / o2
    if S >= 1:
        return None
    for T in range(MISE_MIN, MISE_MAX + 1):
        R = T / S
        m1, m2 = arrondi(R / o1), arrondi(R / o2)
        if m1 < 1 or m2 < 1:
            continue
        tot = m1 + m2
        if tot < MISE_MIN or tot > MISE_MAX:
            continue
        g = min(m1 * o1 - tot, m2 * o2 - tot)
        if g >= GAIN_MIN:
            return m1, m2, tot, g
    return None

def nom_res(m, k):
    return {"1": m['equipe1'], "X": "Nul", "2": m['equipe2']}[k]

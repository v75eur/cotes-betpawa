def rep(f, a, b):
    s = open(f, encoding="utf-8").read()
    assert a in s, "introuvable: " + a[:40]
    open(f, "w", encoding="utf-8").write(s.replace(a, b))

rep("generer_site.py",
'''    for _ in range(defilements):
        await page.mouse.wheel(0, 4000)
        await page.wait_for_timeout(1000)
    return await page.evaluate(js)''',
'''    stable, dernier = 0, -1
    for _ in range(defilements):
        await page.mouse.wheel(0, 6000)
        await page.wait_for_timeout(1000)
        n = await page.locator('a[href*="/event/"]').count()
        stable = stable + 1 if n == dernier else 0
        dernier = n
        if stable >= 5:
            break
    print("Cartes chargees:", dernier)
    return await page.evaluate(js)''')
rep("generer_site.py", "S1.URL, S1.JS, 40", "S1.URL, S1.JS, 250")
rep("generer_site.py", "S2.URL, S2.JS, 40", "S2.URL, S2.JS, 250")
rep("docs/index.html", 'if (jours.indexOf(jour) < 0) jour = "Tous";',
    'if (!window._j0 && jours.length) { jour = jours[0]; window._j0 = 1; }\n    if (jours.indexOf(jour) < 0) jour = "Tous";')
print("OK")

import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
     "Accept-Language": "ru-RU,ru;q=0.9"}
U = ["https://efremov.zarplata.ru/vacancy?text=&experience=noExperience",
     "https://efremov.superjob.ru/vacancy/search/?without_experience=1",
     "https://efremov.rabota.ru/vacancy/?experience=0",
     "https://www.avito.ru/efremov/vakansii"]
for u in U:
    try:
        r = requests.get(u, headers=H, timeout=25)
        t = r.text
        links = re.findall(r'href="([^"]*(?:vacanc|vakans)[^"]*)"', t)[:3]
        print(u.split("/")[2], r.status_code, len(t), "hh-cards=%d" % t.count('data-qa="vacancy-serp__vacancy"'),
              "captcha=%s" % ("captcha" in t.lower()), links)
    except Exception as e:
        print(u.split("/")[2], "ERR", str(e)[:90])

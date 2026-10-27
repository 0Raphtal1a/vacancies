import re, sys, requests
sys.path.insert(0, "/opt/vacancies")
import vacancies as v
from bs4 import BeautifulSoup
U = {"superjob": "https://efremov.superjob.ru/vakansii/bez-opyta.html",
     "rabota": "https://efremov.rabota.ru/vacancy/?experience=0",
     "zarplata": "https://efremov.zarplata.ru/vacancy?text=&experience=noExperience"}
out = []
for n, u in U.items():
    out.append("##### %s %s" % (n, u))
    try:
        r = requests.get(u, headers=v.UA, timeout=25)
        t = r.text
        out.append("status=%s len=%d captcha_in_first5k=%s" % (r.status_code, len(t), "captcha" in t[:5000].lower()))
        out.append("title=%s" % (re.search(r"<title>(.*?)</title>", t, re.S) or [0, ""])[1][:100])
        out.append("data-qa cards=%d next_data=%s ld_json=%d" % (t.count('data-qa="vacancy-serp__vacancy"'), "__NEXT_DATA__" in t, t.count("application/ld+json")))
        soup = BeautifulSoup(t, "html.parser")
        pat = re.compile(r"(vakansii/[^/]*\d{5,}|/vacancy/[^/?]*\d{5,}|/vacancy/\d{5,})")
        links = [a for a in soup.find_all("a", href=True) if pat.search(a["href"])]
        out.append("detail links=%d" % len(links))
        seen = 0
        for a in links[:3]:
            card = a
            for _ in range(5):
                if card.parent and len(str(card.parent)) < 6000: card = card.parent
            out.append("--- href=%s\n%s" % (a["href"], str(card)[:2500]))
    except Exception as e:
        out.append("ERR %s" % e)
v.publish(v.load_cfg(), "\n".join(out), "digest/dump.txt")
print("готово")

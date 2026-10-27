import re, sys
sys.path.insert(0, "/opt/vacancies")
import vacancies as v
from bs4 import BeautifulSoup
out = []
cfg = v.load_cfg()
def card_text(card):
    for s in card(["svg", "script", "style"]): s.decompose()
    return v._clean(card.get_text(" | ", strip=True))
r = v.get("https://efremov.rabota.ru/vacancy/", params={"experience": 0, "page": 1})
soup = BeautifulSoup(r.text, "html.parser")
cards = soup.select(".vacancy-preview-card")
out.append("rabota cards=%d" % len(cards))
for c in cards[:6]:
    out.append("R: " + card_text(c)[:600])
out.append("--- filter chips: " + " ".join(v._clean(x.get_text(" ", strip=True)) for x in soup.select("[class*=filter] [class*=chip], [class*=selected]")[:15]))
r = v.get("https://efremov.zarplata.ru/search/vacancy", params={"text": "", "experience": "noExperience", "search_period": 30, "page": 3})
soup = BeautifulSoup(r.text, "html.parser")
cards = soup.select('[data-qa="vacancy-serp__vacancy"]')
out.append("zarplata cards=%d" % len(cards))
for c in cards[:6]:
    out.append("Z: " + card_text(c)[:600])
v.publish(cfg, "\n".join(out), "digest/dump.txt")
print("готово")

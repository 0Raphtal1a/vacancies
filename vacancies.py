#!/usr/bin/env python3
# Сбор вакансий по Ефремову: hh.ru, Работа России, Avito. Фильтры и письмо на почту.
import os, re, sys, json, time, base64, datetime, logging
import requests
from bs4 import BeautifulSoup

BASE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "ru-RU,ru;q=0.9"}
logging.basicConfig(filename=os.path.join(BASE, "vacancies.log"), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("vac")

def load_cfg():
    cfg = {"CITY": "Ефремов", "AVITO_SLUG": "efremov", "HH_AREA_ID": "", "MAX_SALARY": "100000"}
    p = os.path.join(BASE, "config.env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg

class Blocked(Exception):
    pass

def get(url, **kw):
    r = requests.get(url, headers=UA, timeout=20, **kw)
    if r.status_code in (403, 429) or "captcha" in r.text[:5000].lower() or "Доступ ограничен" in r.text[:5000]:
        raise Blocked("%s: HTTP %s / защита от роботов" % (url.split("/")[2], r.status_code))
    r.raise_for_status()
    return r

# ---------- фильтры ----------
BAD_TITLE = re.compile(r"продав|курьер|вахт", re.I)
BAD_TEXT = re.compile(r"вахт|высше[еойм]|опыт\w*\s+(?:работы\s+)?(?:от|не менее|обязателен|\d)|стаж\s+(?:от|\d)", re.I)

def salary_numbers(s):
    s = (s or "").replace(" ", " ").replace("\xa0", " ")
    return [int(re.sub(r"\s", "", x)) for x in re.findall(r"\d[\d ]*\d|\d", s)]

def keep(item, cfg):
    title = item["title"]
    text = item.get("text", "")
    if BAD_TITLE.search(title) or BAD_TEXT.search(title + " " + text):
        return False
    nums = salary_numbers(item.get("salary", ""))
    if nums and max(nums) > int(cfg["MAX_SALARY"]):
        return False
    return True

# ---------- источники ----------
def src_trudvsem(cfg):
    out, page, limit, t0 = [], 0, 100, time.time()
    while page < 80 and time.time() - t0 < 120:
        try:
            r = get("http://opendata.trudvsem.ru/api/v1/vacancies/region/7100000000",
                    params={"offset": page, "limit": limit})
            vs = (r.json().get("results") or {}).get("vacancies") or []
        except Exception:
            if page == 0: raise
            log.warning("Работа России: остановился на странице %d", page)
            break
        for w in vs:
            v = w.get("vacancy") or {}
            addr = " ".join(a.get("location", "") for a in ((v.get("addresses") or {}).get("address") or []))
            if cfg["CITY"].lower() not in addr.lower():
                continue
            req = v.get("requirement") or {}
            exp = req.get("experience")
            edu = str(req.get("education") or "")
            if (isinstance(exp, (int, float)) and exp > 0) or "высш" in edu.lower():
                continue
            smin, smax = v.get("salary_min") or 0, v.get("salary_max") or 0
            sal = ""
            if smin and smax: sal = "от %d до %d руб." % (smin, smax)
            elif smin: sal = "от %d руб." % smin
            elif smax: sal = "до %d руб." % smax
            phones = [c.get("contact_value", "") for c in (v.get("contact_list") or [])
                      if "тел" in str(c.get("contact_type", "")).lower()]
            out.append({"title": v.get("job-name") or "Без названия", "salary": sal,
                        "phone": ", ".join(p for p in phones if p), "url": v.get("vac_url") or "",
                        "text": " ".join([str(v.get("schedule") or ""), str(v.get("duty") or "")]), "src": "Работа России"})
        if len(vs) < limit:
            break
        page += 1
        time.sleep(1)
    log.info("Работа России: страниц %d, за %d с", page + 1, time.time() - t0)
    return out

def hh_area(cfg):
    if cfg["HH_AREA_ID"]:
        return cfg["HH_AREA_ID"]
    r = get("https://api.hh.ru/suggests/areas", params={"text": cfg["CITY"]})
    items = r.json().get("items") or []
    if not items:
        raise RuntimeError("hh.ru: не нашёл код города, впишите HH_AREA_ID в config.env")
    return str(items[0]["id"])

def parse_hh(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for card in soup.select('[data-qa="vacancy-serp__vacancy"]'):
        a = card.select_one('a[data-qa="serp-item__title"]') or card.select_one('a[href*="/vacancy/"]')
        if not a: continue
        sal = card.select_one('[data-qa="vacancy-serp__vacancy-compensation"]')
        out.append({"title": a.get_text(" ", strip=True), "salary": sal.get_text(" ", strip=True) if sal else "",
                    "phone": "", "url": a.get("href", "").split("?")[0], "text": card.get_text(" ", strip=True), "src": "hh.ru"})
    return out

def src_hh(cfg):
    area, out = hh_area(cfg), []
    for page in range(5):
        r = get("https://hh.ru/search/vacancy", params={"area": area, "experience": "noExperience", "text": "",
                "order_by": "publication_time", "search_period": 3, "items_on_page": 50, "page": page})
        items = parse_hh(r.text)
        if not items:
            if page == 0: raise RuntimeError("hh.ru: страница без вакансий (изменилась разметка или нет вакансий)")
            break
        out += items
        time.sleep(2)
    return out

def src_avito(cfg):
    r = get("https://www.avito.ru/%s/vakansii" % cfg["AVITO_SLUG"], params={"s": 104})
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for card in soup.select('[data-marker="item"]'):
        a = card.select_one('a[data-marker="item-title"]') or card.select_one("a[href]")
        if not a: continue
        p = card.select_one('[data-marker="item-price"]')
        href = a.get("href", "")
        if href.startswith("/"): href = "https://www.avito.ru" + href
        out.append({"title": a.get_text(" ", strip=True), "salary": p.get_text(" ", strip=True) if p else "",
                    "phone": "", "url": href.split("?")[0], "text": card.get_text(" ", strip=True), "src": "Avito"})
    if not out: raise Blocked("Avito: пустая страница (скорее всего блок)")
    return out

# ---------- письмо ----------
def fmt(item):
    lines = [item["title"], "Зарплата: " + (item["salary"] or "не указана")]
    if item["phone"]: lines.append("Номер для связи: " + item["phone"])
    lines.append("Ссылка: " + item["url"])
    return "\n".join(lines)

def publish(cfg, text, path="digest/latest.txt"):
    tok, repo = cfg.get("GITHUB_TOKEN"), cfg.get("GH_REPO", "0Raphtal1a/vacancies")
    if not tok: raise RuntimeError("В config.env не заполнено GITHUB_TOKEN")
    h = {"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json", "User-Agent": "vacancies-digest"}
    url = "https://api.github.com/repos/%s/contents/%s" % (repo, path)
    g = requests.get(url, headers=h, params={"ref": "main"}, timeout=30)
    if g.status_code not in (200, 404):
        raise RuntimeError("GitHub HTTP %s: %s" % (g.status_code, g.text[:300]))
    body = {"message": "digest", "branch": "main",
            "content": base64.b64encode(text.encode("utf-8")).decode()}
    if g.status_code == 200: body["sha"] = g.json().get("sha")
    p = requests.put(url, headers=h, json=body, timeout=30)
    if p.status_code >= 300:
        raise RuntimeError("GitHub HTTP %s: %s" % (p.status_code, p.text[:300]))

def main():
    cfg = load_cfg()
    if "--test" in sys.argv:
        publish(cfg, "TEST OK\n", "digest/test.txt"); print("Тестовый файл отправлен в GitHub"); return
    state_p = os.path.join(BASE, "seen.json")
    seen = json.load(open(state_p)) if os.path.exists(state_p) else {}
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).date()
    seen = {k: d for k, d in seen.items() if (today - datetime.date.fromisoformat(d)).days < 90}
    status, items = [], []
    for name, fn in (("hh.ru", src_hh), ("Работа России", src_trudvsem), ("Avito", src_avito)):
        try:
            got = fn(cfg); items += got; status.append("%s: OK (%d)" % (name, len(got)))
        except Blocked as e:
            status.append("%s: заблокирован, пропущен" % name); log.warning("%s", e)
        except Exception as e:
            status.append("%s: ошибка, пропущен" % name); log.exception("%s", name)
    new, keys = [], set()
    for it in items:
        k = it["url"] or it["title"]
        if k in seen or k in keys or not keep(it, cfg): continue
        keys.add(k); new.append(it)
    ok = sum(1 for s in status if ": OK" in s)
    log.info("%s; новых: %d", "; ".join(status), len(new))
    count = len(new) if ok else -1
    head = "DATE: %s\nCOUNT: %d\nSTATUS: %s\n---\n" % (today.isoformat(), count, "; ".join(status))
    publish(cfg, head + "\n\n".join(fmt(i) for i in new) + "\n")
    for k in keys: seen[k] = today.isoformat()
    json.dump(seen, open(state_p, "w"), ensure_ascii=False)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.exception("fatal"); print("ОШИБКА:", e, file=sys.stderr); sys.exit(1)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Remaster.lt svetainės generatorius.

  python build.py          -> sugeneruoja svetainę į aplanką "svetaine"
  python build.py --new    -> sukuria naują straipsnio failą (klausia pavadinimo)

Turinys:
  straipsniai/*.md      straipsniai (valdomi per /admin/)
  puslapiai/*.md        papildomi puslapiai (Apie mus, D.U.K. ...)
  duomenys/*.json       nustatymai, paslaugos, kainos (valdomi per /admin/)
  nuotraukos/           paveikslėliai
Nereikia jokių papildomų bibliotekų.
"""
import datetime
import html
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "straipsniai"
PAGES = ROOT / "puslapiai"
DATA = ROOT / "duomenys"
IMG = ROOT / "nuotraukos"
OUT = ROOT / "svetaine"

# Numatytieji nustatymai (perrašomi iš duomenys/nustatymai.json, t. y. per /admin/)
SITE = {
    "name": "Remaster.lt",
    "slogan": "Patikima kompiuterių priežiūra ir supirkimas",
    "email": "info@remaster.lt",
    "phone": "",
    "city": "Vilnius, Lietuva",
    "url": "",
    "address": "",
    "hours": "",
    "whatsapp": "",
    "messenger": "",
    "forma_url": "",      # Google Apps Script adresas supirkimo užklausoms (nustatoma per /admin/)
}

DEFAULT_SERVICES = [
    {"ikona": "desktop", "pavadinimas": "OS perrašymas ir optimizavimas",
     "aprasymas": "Švari Windows/Linux instaliacija, tvarkyklių (drivers) diegimas, svarbiausių programų paruošimas darbui."},
    {"ikona": "temperature-arrow-down", "pavadinimas": "Profilaktika ir termo pasta",
     "aprasymas": "Dulkių valymas, aušinimo sistemos priežiūra ir aukštos kokybės termo pastos keitimas, kad kompiuteris nekaistų."},
    {"ikona": "stethoscope", "pavadinimas": "Kompiuterių diagnostika",
     "aprasymas": "Aparatūros ir programinės įrangos gedimų nustatymas, komponentų būklės įvertinimas."},
]

MONTHS = ["sausio", "vasario", "kovo", "balandžio", "gegužės", "birželio",
          "liepos", "rugpjūčio", "rugsėjo", "spalio", "lapkričio", "gruodžio"]

LT_MAP = str.maketrans({
    "ą": "a", "č": "c", "ę": "e", "ė": "e", "į": "i", "š": "s", "ų": "u", "ū": "u", "ž": "z",
    "Ą": "a", "Č": "c", "Ę": "e", "Ė": "e", "Į": "i", "Š": "s", "Ų": "u", "Ū": "u", "Ž": "z",
})

CTX = {"prices": [], "pages": [], "faq": []}   # užpildoma build() metu


def slugify(text):
    text = text.translate(LT_MAP).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "straipsnis"


def fmt_date(d):
    try:
        y, m, day = [int(x) for x in d.split("-")]
        return "%d m. %s %d d." % (y, MONTHS[m - 1], day)
    except Exception:
        return d


def load_json(name, default):
    path = DATA / name
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as e:
            print("Įspėjimas: nepavyko perskaityti %s (%s)" % (name, e))
    return default


# ---------------- Markdown (paprastas) ----------------
def img_tag(alt, src, prefix):
    if not re.match(r"^(https?:)?//", src):
        src = prefix + "nuotraukos/" + src.replace("\\", "/").split("nuotraukos/")[-1]
    return '<img src="%s" alt="%s" loading="lazy">' % (src, alt)


def inline(s, prefix):
    s = html.escape(s, quote=False)
    s = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", lambda m: img_tag(m.group(1), m.group(2), prefix), s)

    def link(m):
        url = m.group(2)
        ext = ' target="_blank" rel="noopener"' if url.startswith("http") else ""
        return '<a href="%s"%s>%s</a>' % (url, ext, m.group(1))

    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def markdown(text, prefix):
    lines = text.replace("\r\n", "\n").split("\n")
    out, para, i = [], [], 0

    def flush():
        if para:
            out.append("<p>%s</p>" % inline(" ".join(para), prefix))
            para.clear()

    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            flush(); i += 1; continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            flush()
            lvl = max(2, len(m.group(1)))      # h1 rezervuotas puslapio antraštei
            out.append("<h%d>%s</h%d>" % (lvl, inline(m.group(2), prefix), lvl))
            i += 1; continue
        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$", line)
        if m:
            flush()
            cap = "<figcaption>%s</figcaption>" % html.escape(m.group(1)) if m.group(1) else ""
            out.append("<figure>%s%s</figure>" % (img_tag(html.escape(m.group(1)), m.group(2), prefix), cap))
            i += 1; continue
        if re.match(r"^\s*[-*]\s+", line) or re.match(r"^\s*\d+[.)]\s+", line):
            flush()
            ordered = bool(re.match(r"^\s*\d+[.)]\s+", line))
            items = []
            while i < len(lines) and (re.match(r"^\s*[-*]\s+", lines[i]) or re.match(r"^\s*\d+[.)]\s+", lines[i])):
                items.append(re.sub(r"^\s*(?:[-*]|\d+[.)])\s+", "", lines[i].rstrip()))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % inline(x, prefix) for x in items), tag))
            continue
        if line.startswith(">"):
            flush()
            out.append("<blockquote>%s</blockquote>" % inline(line.lstrip("> "), prefix))
            i += 1; continue
        para.append(line.strip())
        i += 1
    flush()
    return "\n".join(out)


def parse_md(path):
    text = path.read_text(encoding="utf-8-sig")
    meta, body = {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if m:
        for ln in m.group(1).splitlines():
            if ":" in ln:
                k, v = ln.split(":", 1)
                meta[k.strip().lower()] = v.strip().strip('"')
        body = m.group(2)
    meta.setdefault("pavadinimas", path.stem.replace("-", " ").capitalize())
    meta.setdefault("data", datetime.date.fromtimestamp(path.stat().st_mtime).isoformat())
    meta.setdefault("aprasymas", "")
    meta.setdefault("kategorija", "")
    meta["nuotrauka"] = meta.get("nuotrauka", "").replace("\\", "/").split("nuotraukos/")[-1].strip()
    meta["juodrastis"] = meta.get("juodrastis", "").strip().lower() in ("taip", "true", "1", "yes")
    meta["slug"] = slugify(path.stem)
    meta["body"] = body
    return meta


# ---------------- Šablonai ----------------
def brand_html():
    """Logotipo tekstas: DIDŽIOSIOS raidės, dalis po paskutinio taško paryškinta mėlyna."""
    n = (SITE["name"] or "Remaster.lt").strip().upper()
    if "." in n:
        i = n.rfind(".")
        return "%s<b>%s</b>" % (html.escape(n[:i]), html.escape(n[i:]))
    return html.escape(n)


LOGO_MARK = '''<svg class="logo-mark" width="44" height="44" viewBox="0 0 56 56" aria-hidden="true"><circle cx="28" cy="28" r="26" fill="#2563eb"/><path d="M40 28a12 12 0 1 1-4.2-9.1" fill="none" stroke="#ffffff" stroke-width="4.5" stroke-linecap="round"/><path d="M33 14.5 43 15.5 38.5 24.5Z" fill="#fb923c"/></svg>'''


def logo_html():
    """Logotipas: ženklas + pavadinimas + (nebūtinas) užrašas po juo."""
    sl = SITE["slogan"].strip()
    small = "<small>%s</small>" % html.escape(sl) if sl else ""
    return LOGO_MARK + '<span class="logo-txt"><span class="logo-name">%s</span>%s</span>' % (brand_html(), small)


def site_base():
    """Svetainės bazinis adresas (nustatytas domenas arba GitHub Pages adresas)."""
    if SITE["url"]:
        return SITE["url"].rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        o, r = repo.split("/", 1)
        return "https://%s.github.io/%s" % (o.lower(), r)
    return ""


def ld_json(obj):
    return '<script type="application/ld+json">%s</script>' % json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def mobile_bar():
    btns = []
    if SITE["phone"]:
        btns.append('<a class="mb-call" href="tel:%s"><i class="fa-solid fa-phone"></i> Skambinti</a>' % re.sub(r"[^\d+]", "", SITE["phone"]))
    if SITE["whatsapp"]:
        digits = re.sub(r"\D", "", SITE["whatsapp"])
        if digits:
            btns.append('<a class="mb-wa" href="https://wa.me/%s" target="_blank" rel="noopener"><i class="fa-brands fa-whatsapp"></i> WhatsApp</a>' % digits)
    if SITE["messenger"]:
        m = SITE["messenger"].strip()
        link = m if m.startswith("http") else "https://m.me/" + m.lstrip("@/")
        btns.append('<a class="mb-ms" href="%s" target="_blank" rel="noopener"><i class="fa-brands fa-facebook-messenger"></i> Messenger</a>' % html.escape(link))
    btns.append('<a class="mb-mail" href="mailto:%s"><i class="fa-solid fa-envelope"></i> Rašyti</a>' % html.escape(SITE["email"]))
    return '<div class="mbar n%d">%s</div>' % (len(btns), "".join(btns))


def layout(title, desc, content, depth, active="", path=None, head_extra=""):
    p = "../" * depth
    home = p + "index.html"

    def a(href, label, key):
        cls = ' class="active"' if active == key else ""
        return '<a href="%s"%s>%s</a>' % (href, cls, label)

    menu = a(home + "#paslaugos", "Paslaugos", "paslaugos")
    if CTX["prices"]:
        menu += a(home + "#kainos", "Kainos", "kainos")
    menu += a(home + "#supirkimas", "Supirkimas", "supirkimas")
    menu += a(p + "straipsniai/index.html", "Straipsniai", "straipsniai")
    if CTX["faq"]:
        menu += a(home + "#duk", "D.U.K.", "duk")
    menu += a(home + "#kontaktai", "Kontaktai", "kontaktai")

    foot_links = "".join('<a href="%spuslapiai/%s.html">%s</a>' % (p, pg["slug"], html.escape(pg["pavadinimas"]))
                         for pg in CTX["pages"])
    foot_links = ('<div class="foot-links">%s</div>' % foot_links) if foot_links else ""

    full_title = title if title.startswith(SITE["name"]) else "%s | %s" % (title, SITE["name"])

    base = site_base()
    seo = ""
    if base and path is not None:
        url = base + "/" + path
        img = base + "/og.png"
        seo = ('<link rel="canonical" href="%s">\n<meta property="og:url" content="%s">\n'
               '<meta property="og:image" content="%s">\n<meta name="twitter:card" content="summary_large_image">\n'
               '<meta name="twitter:image" content="%s">\n') % (url, url, img, img)

    return """<!DOCTYPE html>
<html lang="lt">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="theme-color" content="#0f172a">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
<meta property="og:locale" content="lt_LT">
{seo}<link rel="icon" type="image/svg+xml" href="{p}favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<link rel="stylesheet" href="{p}stilius.css">
{head_extra}</head>
<body>
<nav class="nav">
  <div class="wrap nav-inner">
    <a class="logo" href="{home}">{logo}</a>
    <div class="menu" id="menu">
      {menu}
    </div>
    <a class="btn btn-primary nav-cta" href="{home}#kontaktai"><i class="fa-solid fa-headset"></i> Konsultacija</a>
    <button class="burger" id="burger" aria-label="Meniu"><i class="fa-solid fa-bars"></i></button>
  </div>
</nav>
<main>
{content}
</main>
<footer><div class="wrap">{foot_links}&copy; {year} {name} – Visos teisės saugomos.</div></footer>
{mbar}
<script src="{p}script.js"></script>
</body>
</html>""".format(
        title=html.escape(full_title), desc=html.escape(desc), p=p, home=home, content=content, seo=seo,
        head_extra=head_extra, mbar=mobile_bar(),
        menu=menu, foot_links=foot_links, year=datetime.date.today().year, name=html.escape(SITE["name"]), logo=logo_html())


def art_card(a, prefix):
    cover = ('<img src="%snuotraukos/%s" alt="" loading="lazy">' % (prefix, a["nuotrauka"])
             if a["nuotrauka"] else '<i class="fa-solid fa-screwdriver-wrench"></i>')
    cat = '<span class="tag">%s</span>' % html.escape(a["kategorija"]) if a["kategorija"] else ""
    return """<a class="art-card" href="{p}straipsniai/{slug}.html" data-cat="{catraw}">
  <div class="cover">{cover}</div>
  <div class="art-body"><div class="meta"><time>{date}</time>{cat}</div><h3>{title}</h3><p>{desc}</p></div>
</a>""".format(p=prefix, slug=a["slug"], cover=cover, date=fmt_date(a["data"]), cat=cat,
               catraw=html.escape(a["kategorija"]),
               title=html.escape(a["pavadinimas"]), desc=html.escape(a["aprasymas"]))


def contact_block():
    cards = []
    cards.append('<a class="contact" href="mailto:%s"><i class="fa-solid fa-envelope"></i><span>%s</span></a>' % (
        html.escape(SITE["email"]), html.escape(SITE["email"])))
    if SITE["phone"]:
        tel = re.sub(r"[^\d+]", "", SITE["phone"])
        cards.append('<a class="contact" href="tel:%s"><i class="fa-solid fa-phone"></i><span>%s</span></a>' % (tel, html.escape(SITE["phone"])))
    if SITE["whatsapp"] and re.sub(r"\D", "", SITE["whatsapp"]):
        cards.append('<a class="contact" href="https://wa.me/%s" target="_blank" rel="noopener"><i class="fa-brands fa-whatsapp"></i><span>WhatsApp</span></a>' % re.sub(r"\D", "", SITE["whatsapp"]))
    if SITE["messenger"]:
        m = SITE["messenger"].strip()
        link = m if m.startswith("http") else "https://m.me/" + m.lstrip("@/")
        cards.append('<a class="contact" href="%s" target="_blank" rel="noopener"><i class="fa-brands fa-facebook-messenger"></i><span>Messenger</span></a>' % html.escape(link))
    if SITE["address"]:
        q = urllib.parse.quote("%s, %s" % (SITE["address"], SITE["city"]))
        cards.append('<a class="contact" href="https://www.google.com/maps/search/?api=1&query=%s" target="_blank" rel="noopener"><i class="fa-solid fa-location-dot"></i><span>%s<small>Rodyti žemėlapyje</small></span></a>' % (
            q, html.escape(SITE["address"] + ", " + SITE["city"])))
    else:
        cards.append('<div class="contact"><i class="fa-solid fa-location-dot"></i><span>%s</span></div>' % html.escape(SITE["city"]))
    if SITE["hours"]:
        cards.append('<div class="contact"><i class="fa-regular fa-clock"></i><span>%s</span></div>' % html.escape(SITE["hours"]).replace("\n", "<br>"))
    return '<div class="contacts">%s</div>' % "".join(cards)


def services_block(services):
    cards = []
    for s in services:
        icon = re.sub(r"[^a-z0-9-]", "", str(s.get("ikona", "screwdriver-wrench")).lower()) or "screwdriver-wrench"
        price = '<div class="cprice">%s</div>' % html.escape(s["kaina"]) if s.get("kaina") else ""
        cards.append('<div class="card"><div class="ico"><i class="fa-solid fa-%s"></i></div><h3>%s</h3><p>%s</p>%s</div>' % (
            icon, html.escape(s.get("pavadinimas", "")), html.escape(s.get("aprasymas", "")), price))
    return "".join(cards)


def prices_section(prices, cls="s alt"):
    if not prices:
        return ""
    rows = []
    for r in prices:
        note = '<span class="pnote">%s</span>' % html.escape(r.get("pastaba", "")) if r.get("pastaba") else ""
        rows.append('<div class="price-row"><div class="pname">%s%s</div><div class="pval">%s</div></div>' % (
            html.escape(r.get("pavadinimas", "")), note, html.escape(r.get("kaina", ""))))
    return """<section class="%s" id="kainos"><div class="wrap">
  <div class="s-head"><span class="eyebrow">Skaidrios kainos</span><h2>Paslaugų kainos</h2><p>Galutinę kainą nustatome po diagnostikos, o apie ją pasakome iš anksto.</p></div>
  <div class="price-list">%s</div>
</div></section>""" % (cls, "".join(rows))


def faq_section(cls):
    if not CTX["faq"]:
        return ""
    items = "".join('<details><summary>%s</summary><p>%s</p></details>' % (
        html.escape(q["klausimas"]), html.escape(q["atsakymas"]).replace("\n", "<br>")) for q in CTX["faq"])
    return """<section class="%s" id="duk"><div class="wrap">
  <div class="s-head"><span class="eyebrow">Atsakymai</span><h2>Dažniausi klausimai</h2></div>
  <div class="faq">%s</div>
</div></section>""" % (cls, items)


def local_business_ld(services):
    d = {"@context": "https://schema.org", "@type": "LocalBusiness", "name": SITE["name"],
         "description": "Kompiuterių remontas, diagnostika, OS perrašymas ir kompiuterių supirkimas.",
         "email": SITE["email"], "areaServed": SITE["city"].split(",")[0].strip() or "Vilnius"}
    base = site_base()
    if base:
        d["url"] = base + "/"
        d["image"] = base + "/og.png"
    if SITE["phone"]:
        d["telephone"] = SITE["phone"]
    addr = {"@type": "PostalAddress", "addressLocality": SITE["city"].split(",")[0].strip() or "Vilnius", "addressCountry": "LT"}
    if SITE["address"]:
        addr["streetAddress"] = SITE["address"]
    d["address"] = addr
    if SITE["hours"]:
        d["openingHours"] = SITE["hours"].replace("\n", "; ")
    names = [s.get("pavadinimas") for s in services if s.get("pavadinimas")]
    if names:
        d["hasOfferCatalog"] = {"@type": "OfferCatalog", "name": "Paslaugos", "itemListElement": [
            {"@type": "Offer", "itemOffered": {"@type": "Service", "name": n}} for n in names]}
    return ld_json(d)


def faq_ld():
    if not CTX["faq"]:
        return ""
    return ld_json({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q["klausimas"], "acceptedAnswer": {"@type": "Answer", "text": q["atsakymas"]}}
        for q in CTX["faq"]]})


def index_page(articles, services):
    latest = articles[:3]
    if latest:
        grid = '<div class="art-grid">%s</div><div class="more"><a class="btn btn-ghost" href="straipsniai/index.html">Visi straipsniai <i class="fa-solid fa-arrow-right"></i></a></div>' % "".join(art_card(a, "") for a in latest)
    else:
        grid = '<p class="empty">Straipsniai netrukus.</p>'

    # sekcijų fonai kaitaliojasi automatiškai
    order = ["paslaugos"] + (["kainos"] if CTX["prices"] else []) + ["supirkimas", "straipsniai"] + \
            (["duk"] if CTX["faq"] else []) + ["kontaktai"]
    cls = dict((k, "s alt" if i % 2 else "s") for i, k in enumerate(order))

    prices_html = prices_section(CTX["prices"], cls.get("kainos", "s alt"))
    faq_html = faq_section(cls.get("duk", "s"))

    privacy = ""
    if any(pg["slug"] == "privatumo-politika" for pg in CTX["pages"]):
        privacy = ' Siųsdami sutinkate su <a href="puslapiai/privatumo-politika.html" style="text-decoration:underline">privatumo politika</a>.'
    note = ("Atsakysime kuo greičiau." if SITE["forma_url"] else "Paspaudus atsidarys jūsų el. pašto programa su paruoštu laišku.") + privacy

    content = """
<section class="hero"><div class="wrap hero-grid">
  <div>
    <div class="badge"><i class="fa-solid fa-shield-halved"></i><span>Saugumo ir skaidrių kainų garantija</span></div>
    <h1>Patikima kompiuterių priežiūra ir <span>supirkimas</span></h1>
    <p class="lead">Greitas OS perrašymas, nuodugni diagnostika, profilaktika bei sąžiningas kompiuterinės technikos supirkimas Vilniuje.</p>
    <div class="hero-btns">
      <a class="btn btn-primary" href="#kontaktai">Gauti nemokamą konsultaciją</a>
      <a class="btn btn-ghost" href="#supirkimas">Pasiūlyti savo įrangą</a>
    </div>
  </div>
  <div class="panel">
    <h3><i class="fa-solid fa-circle-check"></i> Kodėl renkasi {name}?</h3>
    <ul class="checks">
      <li><i class="fa-solid fa-check"></i><span><strong>Greita diagnostika:</strong> problemas nustatome per trumpiausią laiką.</span></li>
      <li><i class="fa-solid fa-check"></i><span><strong>Duomenų saugumas:</strong> garantuojame pilną asmeninių failų konfidencialumą.</span></li>
      <li><i class="fa-solid fa-check"></i><span><strong>Kokybiškos medžiagos:</strong> profilaktikai naudojame aukštos klasės termo pastą.</span></li>
    </ul>
  </div>
</div></section>

<section class="{c_pasl}" id="paslaugos"><div class="wrap">
  <div class="s-head"><h2>Mūsų paslaugos</h2><p>Profesionali pagalba jūsų staliniams ir nešiojamiesiems kompiuteriams.</p></div>
  <div class="grid3">{services}</div>
</div></section>

{prices}

<section class="{c_buy}" id="supirkimas"><div class="wrap two">
  <div>
    <span class="eyebrow">Greitas atsiskaitymas</span>
    <h2>Kompiuterių ir komponentų supirkimas</h2>
    <p>Norite atnaujinti įrangą arba turite nenaudojamą kompiuterį? Vertiname ir superkame tiek veikiančius, tiek su defektais kompiuterius bei jų dalis.</p>
    <ul class="checks">
      <li><i class="fa-solid fa-circle-check"></i><span>Sąžiningas įvertinimas pagal rinkos kainą</span></li>
      <li><i class="fa-solid fa-circle-check"></i><span>Atsiskaitymas iš karto vietoje</span></li>
    </ul>
  </div>
  <form class="form" id="supirkimo-forma" data-email="{email}" data-endpoint="{endpoint}">
    <h3>Pasiūlykite savo kompiuterį</h3>
    <div><label for="pc">Kompiuterio modelis / specifikacijos</label>
      <textarea id="pc" name="pc" rows="3" required placeholder="pvz. Ryzen 5 5600X, RTX 3060..."></textarea></div>
    <div><label for="kontaktas">Jūsų telefonas arba el. paštas</label>
      <input id="kontaktas" name="kontaktas" type="text" required placeholder="+370 600 00000"></div>
    <div class="hp" aria-hidden="true"><label>Neužpildykite</label><input type="text" name="website" tabindex="-1" autocomplete="off"></div>
    <button class="btn btn-primary" type="submit">Gauti kainos pasiūlymą</button>
    <small id="form-note">{note}</small>
  </form>
</div></section>

<section class="{c_art}" id="straipsniai"><div class="wrap">
  <div class="s-head"><span class="eyebrow">Naudinga žinoti</span><h2>Patarimai ir straipsniai</h2><p>Praktiniai patarimai apie kompiuterių priežiūrą, temperatūras ir greitį.</p></div>
  {grid}
</div></section>

{faq}

<section class="{c_cont}" id="kontaktai"><div class="wrap">
  <div class="s-head"><h2>Susisiekite su {name}</h2></div>
  {contacts}
</div></section>
""".format(email=html.escape(SITE["email"]), grid=grid, name=html.escape(SITE["name"]), contacts=contact_block(),
           services=services_block(services), prices=prices_html, faq=faq_html,
           endpoint=html.escape(SITE["forma_url"]), note=note,
           c_pasl=cls["paslaugos"], c_buy=cls["supirkimas"], c_art=cls["straipsniai"], c_cont=cls["kontaktai"])
    return layout("%s – Kompiuterių remontas, diagnostika ir supirkimas Vilniuje" % SITE["name"],
                  "Profesionalios kompiuterių remonto paslaugos: OS perrašymas, diagnostika, profilaktika ir termo pastos keitimas, kompiuterių supirkimas Vilniuje.",
                  content, 0, path="", head_extra=local_business_ld(services) + faq_ld() + "\n")


def list_page(articles):
    cats = []
    for a in articles:
        if a["kategorija"] and a["kategorija"] not in cats:
            cats.append(a["kategorija"])
    chips = ""
    if len(cats) > 0:
        chips = '<div class="chips" id="chips"><button class="chip on" data-cat="">Visi</button>%s</div>' % "".join(
            '<button class="chip" data-cat="%s">%s</button>' % (html.escape(c), html.escape(c)) for c in cats)
    grid = ('<div class="art-grid" id="art-grid">%s</div>' % "".join(art_card(a, "../") for a in articles)
            if articles else '<p class="empty">Straipsnių kol kas nėra.</p>')
    content = """<div class="wrap"><div class="page-head">
<div class="crumbs"><a href="../index.html">Pradžia</a> / Straipsniai</div>
<h1>Patarimai ir straipsniai</h1></div>
%s
<div style="padding-bottom:70px">%s</div></div>""" % (chips, grid)
    return layout("Straipsniai", "Naudingi patarimai apie kompiuterių priežiūrą, remontą ir optimizavimą.", content, 1, "straipsniai", path="straipsniai/index.html")


def article_page(a):
    hero = ('<img class="hero-img" src="../nuotraukos/%s" alt="">' % a["nuotrauka"]) if a["nuotrauka"] else ""
    cat = ' <span class="tag">%s</span>' % html.escape(a["kategorija"]) if a["kategorija"] else ""
    content = """<div class="wrap"><div class="page-head" style="max-width:760px;margin:0 auto;padding-left:0;padding-right:0">
<div class="crumbs"><a href="../index.html">Pradžia</a> / <a href="index.html">Straipsniai</a></div>
<h1>{title}</h1><div class="crumbs"><i class="fa-regular fa-calendar"></i> {date}{cat}</div></div></div>
<article class="article">
{hero}
<div class="prose">{body}</div>
<div class="cta"><h3>Reikia pagalbos su kompiuteriu?</h3><p>Parašykite – įvertinsime problemą ir pasiūlysime sprendimą.</p>
<a class="btn btn-ghost" href="../index.html#kontaktai">Susisiekti</a></div>
</article>""".format(title=html.escape(a["pavadinimas"]), date=fmt_date(a["data"]), hero=hero, cat=cat,
                     body=markdown(a["body"], "../"))
    base = site_base()
    ld = {"@context": "https://schema.org", "@type": "Article", "headline": a["pavadinimas"],
          "datePublished": a["data"], "description": a["aprasymas"], "inLanguage": "lt",
          "author": {"@type": "Organization", "name": SITE["name"]}}
    if base and a["nuotrauka"]:
        ld["image"] = "%s/nuotraukos/%s" % (base, a["nuotrauka"])
    return layout(a["pavadinimas"], a["aprasymas"], content, 1, "straipsniai",
                  path="straipsniai/%s.html" % a["slug"], head_extra=ld_json(ld) + "\n")


def static_page(pg):
    hero = ('<img class="hero-img" src="../nuotraukos/%s" alt="">' % pg["nuotrauka"]) if pg["nuotrauka"] else ""
    content = """<div class="wrap"><div class="page-head" style="max-width:760px;margin:0 auto;padding-left:0;padding-right:0">
<div class="crumbs"><a href="../index.html">Pradžia</a> / {title}</div>
<h1>{title}</h1></div></div>
<article class="article">
{hero}
<div class="prose">{body}</div>
<div class="cta"><h3>Turite klausimų?</h3><p>Parašykite – mielai padėsime.</p>
<a class="btn btn-ghost" href="../index.html#kontaktai">Susisiekti</a></div>
</article>""".format(title=html.escape(pg["pavadinimas"]), hero=hero, body=markdown(pg["body"], "../"))
    return layout(pg["pavadinimas"], pg["aprasymas"], content, 1, path="puslapiai/%s.html" % pg["slug"])


# ---------------- Generavimas ----------------
def version_string():
    """Trumpas versijos kodas (git commit) ir sugeneravimo laikas – rodomas admine."""
    sha = (os.environ.get("GITHUB_SHA") or "")[:7]
    if not sha:
        try:
            sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                                          stderr=subprocess.DEVNULL).decode().strip()
        except Exception:
            sha = "vietinė"
    try:
        from zoneinfo import ZoneInfo
        now = datetime.datetime.now(ZoneInfo("Europe/Vilnius"))
    except Exception:
        now = datetime.datetime.utcnow()
    return "%s · %s" % (sha, now.strftime("%Y-%m-%d %H:%M"))


def build():
    for d in (SRC, PAGES, DATA, IMG):
        d.mkdir(exist_ok=True)

    SITE.update({k: v for k, v in load_json("nustatymai.json", {}).items() if k in SITE and isinstance(v, str)})
    services = load_json("paslaugos.json", DEFAULT_SERVICES) or DEFAULT_SERVICES
    # kainų lentelė: paslaugos su kaina + papildomos kainos (be pasikartojimų)
    from_services = [{"pavadinimas": s.get("pavadinimas", ""), "kaina": s["kaina"], "pastaba": s.get("kainos_pastaba", "")}
                     for s in services if s.get("kaina") and s.get("pavadinimas")]
    extra = [r for r in load_json("kainos.json", []) if r.get("pavadinimas")]
    CTX["prices"] = from_services + extra
    CTX["faq"] = [q for q in load_json("duk.json", []) if q.get("klausimas") and q.get("atsakymas")]

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    (OUT / "straipsniai").mkdir()
    (OUT / "puslapiai").mkdir()

    articles = [a for a in (parse_md(p) for p in sorted(SRC.glob("*.md"))) if not a["juodrastis"]]
    articles.sort(key=lambda a: a["data"], reverse=True)
    pages = [pg for pg in (parse_md(p) for p in sorted(PAGES.glob("*.md"))) if not pg["juodrastis"]]
    CTX["pages"] = pages

    (OUT / "index.html").write_text(index_page(articles, services), encoding="utf-8")
    (OUT / "straipsniai" / "index.html").write_text(list_page(articles), encoding="utf-8")
    for a in articles:
        (OUT / "straipsniai" / (a["slug"] + ".html")).write_text(article_page(a), encoding="utf-8")
    for pg in pages:
        (OUT / "puslapiai" / (pg["slug"] + ".html")).write_text(static_page(pg), encoding="utf-8")

    for f in ("stilius.css", "script.js", "favicon.svg", "og.png"):
        if (ROOT / f).exists():
            shutil.copy(ROOT / f, OUT / f)
    shutil.copytree(IMG, OUT / "nuotraukos")
    if (ROOT / "admin").exists():
        shutil.copytree(ROOT / "admin", OUT / "admin")
        ver = version_string()
        (OUT / "admin" / "versija.js").write_text('window.RM_VERSION = "%s";\n' % ver, encoding="utf-8")
        # talpyklos apėjimas: failų adresams pridedame versiją, kad naršyklė visada paimtų naujausius
        tag = re.sub(r"[^a-zA-Z0-9]", "", ver)
        idx = OUT / "admin" / "index.html"
        page = idx.read_text(encoding="utf-8")
        for f in ("admin.css", "admin.js", "versija.js"):
            page = page.replace('"%s"' % f, '"%s?v=%s"' % (f, tag))
        idx.write_text(page, encoding="utf-8")

    (OUT / "404.html").write_text(layout("Puslapis nerastas", "Puslapis nerastas",
        '<div class="wrap" style="padding:90px 0;text-align:center"><h1>Puslapis nerastas</h1><p style="margin:16px 0 24px;color:#94a3b8">Tokio adreso nėra.</p><a class="btn btn-primary" href="index.html">Į pradžią</a></div>', 0), encoding="utf-8")
    robots = "User-agent: *\nAllow: /\nDisallow: /admin/\n"
    if SITE["url"]:
        base = SITE["url"].rstrip("/")
        urls = [base + "/", base + "/straipsniai/index.html"] + \
               ["%s/straipsniai/%s.html" % (base, a["slug"]) for a in articles] + \
               ["%s/puslapiai/%s.html" % (base, pg["slug"]) for pg in pages]
        sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s\n</urlset>\n' % \
             "\n".join("<url><loc>%s</loc></url>" % u for u in urls)
        (OUT / "sitemap.xml").write_text(sm, encoding="utf-8")
        robots += "Sitemap: %s/sitemap.xml\n" % base
    (OUT / "robots.txt").write_text(robots, encoding="utf-8")

    print("Sugeneruota. Straipsnių: %d, puslapių: %d" % (len(articles), len(pages)))
    print("Rezultatas aplanke: %s" % OUT)


def new_article():
    title = input("Straipsnio pavadinimas: ").strip()
    if not title:
        print("Pavadinimas tuščias."); return
    SRC.mkdir(exist_ok=True)
    today = datetime.date.today().isoformat()
    path = SRC / ("%s-%s.md" % (today, slugify(title)))
    path.write_text(
        "---\npavadinimas: %s\ndata: %s\nkategorija: Patarimai\naprasymas: Trumpas aprašymas (rodomas sąraše ir Google paieškoje)\nnuotrauka: \njuodrastis: ne\n---\n\n"
        "Pirmas pastraipos tekstas.\n\n## Poskyrio antraštė\n\nTekstas su **paryškinimu**.\n\n- sąrašo punktas\n- kitas punktas\n\n"
        "![Nuotraukos aprašymas](nuotrauka.jpg)\n" % (title, today), encoding="utf-8")
    print("Sukurta: %s" % path)
    print("Redaguok failą, nuotraukas dėk į aplanką 'nuotraukos', tada paleisk build.bat")


if __name__ == "__main__":
    if "--new" in sys.argv:
        new_article()
    else:
        build()

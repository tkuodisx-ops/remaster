#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Remaster.lt svetainės generatorius.

  python build.py          -> sugeneruoja svetainę į aplanką "svetaine"
  python build.py --new    -> sukuria naują straipsnio failą (klausia pavadinimo)

Straipsniai: aplankas "straipsniai" (.md failai), nuotraukos: aplankas "nuotraukos".
Nereikia jokių papildomų bibliotekų.
"""
import datetime
import html
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "straipsniai"
IMG = ROOT / "nuotraukos"
OUT = ROOT / "svetaine"

# ---------------- NUSTATYMAI (keisk čia) ----------------
SITE = {
    "name": "Remaster.lt",
    "email": "info@remaster.lt",
    "phone": "",          # kol kas tuščia – telefonas nerodomas. Vėliau įrašyk pvz. "+370 600 00000"
    "city": "Vilnius, Lietuva",
    "url": "",            # kai turėsi adresą, įrašyk pvz. "https://remaster.lt" (reikalinga sitemap.xml)
}
# --------------------------------------------------------

MONTHS = ["sausio", "vasario", "kovo", "balandžio", "gegužės", "birželio",
          "liepos", "rugpjūčio", "rugsėjo", "spalio", "lapkričio", "gruodžio"]

LT_MAP = str.maketrans({
    "ą": "a", "č": "c", "ę": "e", "ė": "e", "į": "i", "š": "s", "ų": "u", "ū": "u", "ž": "z",
    "Ą": "a", "Č": "c", "Ę": "e", "Ė": "e", "Į": "i", "Š": "s", "Ų": "u", "Ū": "u", "Ž": "z",
})


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


def parse_article(path):
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
    meta.setdefault("nuotrauka", "")
    meta["slug"] = slugify(path.stem)
    meta["body"] = body
    return meta


# ---------------- Šablonai ----------------
def layout(title, desc, content, depth, active=""):
    p = "../" * depth
    home = p + "index.html"

    def a(href, label, key):
        cls = ' class="active"' if active == key else ""
        return '<a href="%s"%s>%s</a>' % (href, cls, label)

    full_title = title if title.startswith(SITE["name"]) else "%s | %s" % (title, SITE["name"])
    canonical = ""
    return """<!DOCTYPE html>
<html lang="lt">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<link rel="stylesheet" href="{p}stilius.css">
</head>
<body>
<nav class="nav">
  <div class="wrap nav-inner">
    <a class="logo" href="{home}"><span class="logo-ico"><i class="fa-solid fa-microchip"></i></span><span>REMASTER<b>.LT</b></span></a>
    <div class="menu" id="menu">
      {m1}{m2}{m3}{m4}
    </div>
    <a class="btn btn-primary nav-cta" href="{home}#kontaktai"><i class="fa-solid fa-headset"></i> Konsultacija</a>
    <button class="burger" id="burger" aria-label="Meniu"><i class="fa-solid fa-bars"></i></button>
  </div>
</nav>
<main>
{content}
</main>
<footer><div class="wrap">&copy; {year} {name} – Visos teisės saugomos.</div></footer>
<script src="{p}script.js"></script>
</body>
</html>""".format(
        title=html.escape(full_title), desc=html.escape(desc), p=p, home=home, content=content,
        m1=a(home + "#paslaugos", "Paslaugos", "paslaugos"),
        m2=a(home + "#supirkimas", "Supirkimas", "supirkimas"),
        m3=a(p + "straipsniai/index.html", "Straipsniai", "straipsniai"),
        m4=a(home + "#kontaktai", "Kontaktai", "kontaktai"),
        year=datetime.date.today().year, name=SITE["name"])


def art_card(a, prefix):
    cover = ('<img src="%snuotraukos/%s" alt="" loading="lazy">' % (prefix, a["nuotrauka"])
             if a["nuotrauka"] else '<i class="fa-solid fa-screwdriver-wrench"></i>')
    return """<a class="art-card" href="{p}straipsniai/{slug}.html">
  <div class="cover">{cover}</div>
  <div class="art-body"><time>{date}</time><h3>{title}</h3><p>{desc}</p></div>
</a>""".format(p=prefix, slug=a["slug"], cover=cover, date=fmt_date(a["data"]),
               title=html.escape(a["pavadinimas"]), desc=html.escape(a["aprasymas"]))


def contact_block():
    phone = ""
    if SITE["phone"]:
        tel = re.sub(r"[^\d+]", "", SITE["phone"])
        phone = '<a class="contact" href="tel:%s"><i class="fa-solid fa-phone"></i><span>%s</span></a>' % (tel, html.escape(SITE["phone"]))
    return """<div class="contacts">
  <a class="contact" href="mailto:{email}"><i class="fa-solid fa-envelope"></i><span>{email}</span></a>
  {phone}
  <div class="contact"><i class="fa-solid fa-location-dot"></i><span>{city}</span></div>
</div>""".format(email=SITE["email"], phone=phone, city=SITE["city"])


def index_page(articles):
    latest = articles[:3]
    if latest:
        grid = '<div class="art-grid">%s</div><div class="more"><a class="btn btn-ghost" href="straipsniai/index.html">Visi straipsniai <i class="fa-solid fa-arrow-right"></i></a></div>' % "".join(art_card(a, "") for a in latest)
    else:
        grid = '<p class="empty">Straipsniai netrukus.</p>'

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
    <h3><i class="fa-solid fa-circle-check"></i> Kodėl renkasi Remaster.lt?</h3>
    <ul class="checks">
      <li><i class="fa-solid fa-check"></i><span><strong>Greita diagnostika:</strong> problemas nustatome per trumpiausią laiką.</span></li>
      <li><i class="fa-solid fa-check"></i><span><strong>Duomenų saugumas:</strong> garantuojame pilną asmeninių failų konfidencialumą.</span></li>
      <li><i class="fa-solid fa-check"></i><span><strong>Kokybiškos medžiagos:</strong> profilaktikai naudojame aukštos klasės termo pastą.</span></li>
    </ul>
  </div>
</div></section>

<section class="s" id="paslaugos"><div class="wrap">
  <div class="s-head"><h2>Mūsų paslaugos</h2><p>Profesionali pagalba jūsų staliniams ir nešiojamiesiems kompiuteriams.</p></div>
  <div class="grid3">
    <div class="card"><div class="ico"><i class="fa-solid fa-desktop"></i></div><h3>OS perrašymas ir optimizavimas</h3><p>Švari Windows/Linux instaliacija, tvarkyklių (drivers) diegimas, svarbiausių programų paruošimas darbui.</p></div>
    <div class="card"><div class="ico"><i class="fa-solid fa-temperature-arrow-down"></i></div><h3>Profilaktika ir termo pasta</h3><p>Dulkių valymas, aušinimo sistemos priežiūra ir aukštos kokybės termo pastos keitimas, kad kompiuteris nekaistų.</p></div>
    <div class="card"><div class="ico"><i class="fa-solid fa-stethoscope"></i></div><h3>Kompiuterių diagnostika</h3><p>Aparatūros ir programinės įrangos gedimų nustatymas, komponentų būklės įvertinimas.</p></div>
  </div>
</div></section>

<section class="s alt" id="supirkimas"><div class="wrap two">
  <div>
    <span class="eyebrow">Greitas atsiskaitymas</span>
    <h2>Kompiuterių ir komponentų supirkimas</h2>
    <p>Norite atnaujinti įrangą arba turite nenaudojamą kompiuterį? Vertiname ir superkame tiek veikiančius, tiek su defektais kompiuterius bei jų dalis.</p>
    <ul class="checks">
      <li><i class="fa-solid fa-circle-check"></i><span>Sąžiningas įvertinimas pagal rinkos kainą</span></li>
      <li><i class="fa-solid fa-circle-check"></i><span>Atsiskaitymas iš karto vietoje</span></li>
    </ul>
  </div>
  <form class="form" id="supirkimo-forma" data-email="{email}">
    <h3>Pasiūlykite savo kompiuterį</h3>
    <div><label for="pc">Kompiuterio modelis / specifikacijos</label>
      <textarea id="pc" name="pc" rows="3" required placeholder="pvz. Ryzen 5 5600X, RTX 3060..."></textarea></div>
    <div><label for="kontaktas">Jūsų telefonas arba el. paštas</label>
      <input id="kontaktas" name="kontaktas" type="text" required placeholder="+370 600 00000"></div>
    <button class="btn btn-primary" type="submit">Gauti kainos pasiūlymą</button>
    <small>Paspaudus atsidarys jūsų el. pašto programa su paruoštu laišku.</small>
  </form>
</div></section>

<section class="s" id="straipsniai"><div class="wrap">
  <div class="s-head"><span class="eyebrow">Naudinga žinoti</span><h2>Patarimai ir straipsniai</h2><p>Praktiniai patarimai apie kompiuterių priežiūrą, temperatūras ir greitį.</p></div>
  {grid}
</div></section>

<section class="s alt" id="kontaktai"><div class="wrap">
  <div class="s-head"><h2>Susisiekite su {name}</h2></div>
  {contacts}
</div></section>
""".format(email=SITE["email"], grid=grid, name=SITE["name"], contacts=contact_block())
    return layout("Remaster.lt – Kompiuterių remontas, diagnostika ir supirkimas Vilniuje",
                  "Profesionalios kompiuterių remonto paslaugos: OS perrašymas, diagnostika, profilaktika ir termo pastos keitimas, kompiuterių supirkimas Vilniuje.",
                  content, 0)


def list_page(articles):
    grid = ('<div class="art-grid">%s</div>' % "".join(art_card(a, "../") for a in articles)
            if articles else '<p class="empty">Straipsnių kol kas nėra.</p>')
    content = """<div class="wrap"><div class="page-head">
<div class="crumbs"><a href="../index.html">Pradžia</a> / Straipsniai</div>
<h1>Patarimai ir straipsniai</h1></div>
<div style="padding-bottom:70px">%s</div></div>""" % grid
    return layout("Straipsniai", "Naudingi patarimai apie kompiuterių priežiūrą, remontą ir optimizavimą.", content, 1, "straipsniai")


def article_page(a):
    hero = ('<img class="hero-img" src="../nuotraukos/%s" alt="">' % a["nuotrauka"]) if a["nuotrauka"] else ""
    content = """<div class="wrap"><div class="page-head" style="max-width:760px;margin:0 auto;padding-left:0;padding-right:0">
<div class="crumbs"><a href="../index.html">Pradžia</a> / <a href="index.html">Straipsniai</a></div>
<h1>{title}</h1><div class="crumbs"><i class="fa-regular fa-calendar"></i> {date}</div></div></div>
<article class="article">
{hero}
<div class="prose">{body}</div>
<div class="cta"><h3>Reikia pagalbos su kompiuteriu?</h3><p>Parašykite – įvertinsime problemą ir pasiūlysime sprendimą.</p>
<a class="btn btn-ghost" href="../index.html#kontaktai">Susisiekti</a></div>
</article>""".format(title=html.escape(a["pavadinimas"]), date=fmt_date(a["data"]), hero=hero,
                     body=markdown(a["body"], "../"))
    return layout(a["pavadinimas"], a["aprasymas"], content, 1, "straipsniai")


# ---------------- Generavimas ----------------
def build():
    SRC.mkdir(exist_ok=True)
    IMG.mkdir(exist_ok=True)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    (OUT / "straipsniai").mkdir()

    articles = [parse_article(p) for p in sorted(SRC.glob("*.md"))]
    articles.sort(key=lambda a: a["data"], reverse=True)

    (OUT / "index.html").write_text(index_page(articles), encoding="utf-8")
    (OUT / "straipsniai" / "index.html").write_text(list_page(articles), encoding="utf-8")
    for a in articles:
        (OUT / "straipsniai" / (a["slug"] + ".html")).write_text(article_page(a), encoding="utf-8")

    for f in ("stilius.css", "script.js"):
        shutil.copy(ROOT / f, OUT / f)
    shutil.copytree(IMG, OUT / "nuotraukos")

    # 404 ir robots
    (OUT / "404.html").write_text(layout("Puslapis nerastas", "Puslapis nerastas",
        '<div class="wrap" style="padding:90px 0;text-align:center"><h1>Puslapis nerastas</h1><p style="margin:16px 0 24px;color:#94a3b8">Tokio adreso nėra.</p><a class="btn btn-primary" href="index.html">Į pradžią</a></div>', 0), encoding="utf-8")
    robots = "User-agent: *\nAllow: /\n"
    if SITE["url"]:
        base = SITE["url"].rstrip("/")
        urls = [base + "/", base + "/straipsniai/index.html"] + ["%s/straipsniai/%s.html" % (base, a["slug"]) for a in articles]
        sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s\n</urlset>\n' % \
             "\n".join("<url><loc>%s</loc></url>" % u for u in urls)
        (OUT / "sitemap.xml").write_text(sm, encoding="utf-8")
        robots += "Sitemap: %s/sitemap.xml\n" % base
    (OUT / "robots.txt").write_text(robots, encoding="utf-8")

    print("Sugeneruota. Straipsnių: %d" % len(articles))
    print("Rezultatas aplanke: %s" % OUT)


def new_article():
    title = input("Straipsnio pavadinimas: ").strip()
    if not title:
        print("Pavadinimas tuščias."); return
    SRC.mkdir(exist_ok=True)
    today = datetime.date.today().isoformat()
    path = SRC / ("%s-%s.md" % (today, slugify(title)))
    path.write_text(
        "---\npavadinimas: %s\ndata: %s\naprasymas: Trumpas aprašymas (rodomas sąraše ir Google paieškoje)\nnuotrauka: \n---\n\n"
        "Pirmas pastraipos tekstas.\n\n## Poskyrio antraštė\n\nTekstas su **paryškinimu**.\n\n- sąrašo punktas\n- kitas punktas\n\n"
        "![Nuotraukos aprašymas](nuotrauka.jpg)\n" % (title, today), encoding="utf-8")
    print("Sukurta: %s" % path)
    print("Redaguok failą, nuotraukas dėk į aplanką 'nuotraukos', tada paleisk build.bat")


if __name__ == "__main__":
    if "--new" in sys.argv:
        new_article()
    else:
        build()

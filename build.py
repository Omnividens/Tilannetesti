"""Tilannekuva
Kerää turvallisuusuutisia eri lähteistä, luokittelee ne sääntöjen avulla
ja laskee jokaiselle teemalle värikoodatun mittarin. Tulos: site/index.html.
Ei vaadi maksullisia palveluita eikä asennettavia kirjastoja.
"""

import hashlib
import json
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    HELSINKI = ZoneInfo("Europe/Helsinki")
except Exception:
    HELSINKI = timezone.utc

from asetukset import (
    ALUEET, GDELT_HAKU, KATEGORIAT, LAHTEET, MAX_NAYTETTAVAT, MIN_POHJA, NAYTA_PAIVIA,
    PAIKAT, POHJA_PAIVIA, PYSAYTYSSANAT, RAJAT, SAILYTYS_PAIVIA, TEEMAT,
    TOIMIJAT, YLLATYS,
)

RIVINVAIHTO = chr(10)


def puhdista(teksti):
    teksti = re.sub("<[^>]+>", " ", unescape(teksti or ""))
    return " ".join(teksti.split())


def lataa(url):
    pyynto = urllib.request.Request(
        url, headers={"User-Agent": "tilannekuva-harrasteprojekti (GitHub Actions)"}
    )
    with urllib.request.urlopen(pyynto, timeout=60) as vastaus:
        return vastaus.read()


def parsi_aika(teksti):
    if not teksti:
        return None
    teksti = teksti.strip()
    try:
        aika = parsedate_to_datetime(teksti)
    except (TypeError, ValueError):
        try:
            aika = datetime.fromisoformat(teksti.replace("Z", "+00:00"))
        except ValueError:
            return None
    if aika is None:
        return None
    if aika.tzinfo is None:
        aika = aika.replace(tzinfo=timezone.utc)
    return aika.astimezone(timezone.utc)


def siisti_linkki(linkki):
    osat = urllib.parse.urlsplit(linkki.strip())
    kysely = [(k, v) for k, v in urllib.parse.parse_qsl(osat.query) if not k.startswith("utm_")]
    return urllib.parse.urlunsplit(
        (osat.scheme, osat.netloc, osat.path, urllib.parse.urlencode(kysely), "")
    )


def lue_rss(data, lahde):
    juuri = ET.fromstring(data)
    tulokset = []
    for elementti in juuri.iter():
        if elementti.tag.split("}")[-1] not in ("item", "entry"):
            continue
        kentat = {}
        for lapsi in elementti:
            nimi = lapsi.tag.split("}")[-1]
            if nimi == "link":
                kentat.setdefault("link", lapsi.get("href") or (lapsi.text or "").strip())
            elif nimi in ("title", "pubDate", "published", "updated", "date", "description", "summary"):
                kentat.setdefault(nimi, lapsi.text or "")
        otsikko = puhdista(kentat.get("title"))
        linkki = kentat.get("link")
        if not otsikko or not linkki:
            continue
        aika = None
        for avain in ("pubDate", "published", "date", "updated"):
            aika = aika or parsi_aika(kentat.get(avain))
        tulokset.append({
            "otsikko": otsikko,
            "linkki": siisti_linkki(linkki),
            "lahde": lahde["nimi"],
            "aika": aika,
            "yhteenveto": puhdista(kentat.get("description") or kentat.get("summary"))[:600],
        })
    return tulokset


def hae_gdelt(lahde):
    kysely = f"{GDELT_HAKU} domain:{lahde['domain']} sourcelang:english"
    osoite = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode({
        "query": kysely, "mode": "ArtList", "maxrecords": 75,
        "format": "json", "timespan": "24h", "sort": "DateDesc",
    })
    data = lataa(osoite)
    try:
        vastaus = json.loads(data)
    except ValueError:
        raise RuntimeError("GDELT ei palauttanut JSONia: " + data[:80].decode("utf-8", "replace"))
    tulokset = []
    for a in vastaus.get("articles", []):
        aika = None
        try:
            aika = datetime.strptime(a.get("seendate", ""), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
        if a.get("title") and a.get("url"):
            tulokset.append({
                "otsikko": puhdista(a["title"]),
                "linkki": siisti_linkki(a["url"]),
                "lahde": lahde["nimi"],
                "aika": aika,
                "yhteenveto": "",
            })
    return tulokset


def luokittele(otsikko, yhteenveto):
    """Palauttaa sanakirjan uutisen tiedoista tai None, jos uutinen ei ole relevantti."""
    teksti = otsikko + " " + yhteenveto
    teemat = [nimi for nimi, kuvio in TEEMAT.items() if kuvio.search(teksti)]
    kategoriat = {}
    for nimi, saannot in KATEGORIAT.items():
        paras = 0
        for paino, kuvio, lisa in saannot:
            if kuvio.search(teksti) and (lisa is None or lisa.search(teksti)):
                paras = max(paras, paino)
        if paras:
            kategoriat[nimi] = paras
    if not teemat and max(kategoriat.values(), default=0) < 2:
        return None
    if not teemat:
        teemat = ["Muu maailma"]
    paino = 1 + min(6, sum(kategoriat.values())) + (1 if YLLATYS.search(teksti) else 0)

    # Kuka, Mitä, Missä, Kenelle: lasketaan vain otsikosta
    osumat = sorted(
        (m.start(), nimi) for nimi, kuvio, _ in TOIMIJAT for m in [kuvio.search(otsikko)] if m
    )
    kuka = osumat[0][1] if osumat else "–"
    kenelle = osumat[1][1] if len(osumat) > 1 else "–"
    paikat = sorted(
        (m.start(), nimi) for nimi, kuvio in PAIKAT for m in [kuvio.search(otsikko)] if m
    )
    missa = paikat[0][1] if paikat else "–"
    if missa == "–":
        for ehdokas in (kenelle, kuka):
            if ehdokas in ALUEET:
                missa = ehdokas
                break
    mita = max(kategoriat, key=kategoriat.get) if kategoriat else "–"
    return {"teemat": teemat, "kategoriat": kategoriat, "paino": paino,
            "kuka": kuka, "mita": mita, "missa": missa, "kenelle": kenelle}


def sanat(otsikko):
    return {s for s in re.findall("[a-zäöå]{5,}", otsikko.lower()) if s not in PYSAYTYSSANAT}


def laske_mittari(kohteet, nyt, alku):
    """Palauttaa (väri, otsikko, perustelu) yhdelle teemalle."""
    ikkunat = {}
    for k in kohteet:
        i = int((nyt - k["aika_dt"]).total_seconds() // 86400)
        if 0 <= i <= POHJA_PAIVIA:
            ikkunat.setdefault(i, []).append(k)
    nykyiset = ikkunat.get(0, [])
    pohja_ikkunat = [i for i in range(1, POHJA_PAIVIA + 1) if nyt - timedelta(days=i + 1) >= alku]
    kuorma0 = sum(k["paino"] for k in nykyiset)
    if len(pohja_ikkunat) < MIN_POHJA:
        return ("harmaa", "Pohjatasoa kerätään",
                f"Dataa on kertynyt {len(pohja_ikkunat)} / {MIN_POHJA} vuorokautta. "
                f"Nyt: {kuorma0} pistettä.")
    kuormat = [sum(k["paino"] for k in ikkunat.get(i, [])) for i in pohja_ikkunat]
    mu = statistics.mean(kuormat)
    sigma = max(statistics.pstdev(kuormat), 1.0, 0.3 * mu)
    z = (kuorma0 - mu) / sigma
    suhde = (kuorma0 + 1) / (mu + 1)
    lahteet0 = len({k["lahde"] for k in nykyiset})

    pohja_kohteet = [k for i in pohja_ikkunat for k in ikkunat.get(i, [])]
    kat0, kat_pohja = {}, {}
    for k in nykyiset:
        for nimi, paino in k["kategoriat"].items():
            kat0.setdefault(nimi, [0, paino])[0] += 1
    for k in pohja_kohteet:
        for nimi in k["kategoriat"]:
            kat_pohja[nimi] = kat_pohja.get(nimi, 0) + 1
    uudet = [(nimi, p) for nimi, (n, p) in kat0.items() if n >= 2 and kat_pohja.get(nimi, 0) <= 1]
    uusi_vakava = any(p >= 3 for _, p in uudet)

    termit0, termit_pohja = {}, set()
    for k in nykyiset:
        for s in sanat(k["otsikko"]):
            termit0[s] = termit0.get(s, 0) + 1
    for k in pohja_kohteet:
        termit_pohja |= sanat(k["otsikko"])
    uudet_termit = [] if len(pohja_kohteet) < 30 else sorted(
        (s for s, n in termit0.items() if n >= 2 and s not in termit_pohja),
        key=lambda s: -termit0[s])[:6]

    punainen = (
        (z >= RAJAT["pun_z"] and suhde >= RAJAT["pun_suhde"] and lahteet0 >= RAJAT["pun_lahteet"]
         and kuorma0 >= RAJAT["pun_kuorma"])
        or (uusi_vakava and lahteet0 >= 3 and z >= RAJAT["kelt_z"])
    )
    keltainen = (
        (z >= RAJAT["kelt_z"] and suhde >= RAJAT["kelt_suhde"] and kuorma0 >= RAJAT["kelt_kuorma"])
        or bool(uudet)
        or (len(uudet_termit) >= RAJAT["uudet_termit"] and kuorma0 >= RAJAT["kelt_kuorma"])
    )
    osat = [f"Nyt {kuorma0} pistettä, normaali {mu:.0f} ({suhde:.1f} kertaa)", f"{lahteet0} lähdettä"]
    if uudet:
        osat.append("uusi aihe: " + ", ".join(n for n, _ in uudet))
    if uudet_termit:
        osat.append("uudet sanat: " + ", ".join(uudet_termit))
    perustelu = ". ".join(osat) + "."
    if punainen:
        return ("punainen", "Äkillinen ja yllättävä", perustelu)
    if keltainen:
        return ("keltainen", "Kehittyy uuteen suuntaan", perustelu)
    return ("vihrea", "Pysynyt samana", perustelu)


def lataa_kohteet():
    polku = Path("data/items.json")
    if not polku.exists():
        return []
    return json.loads(polku.read_text(encoding="utf-8"))


def tallenna_kohteet(kohteet):
    Path("data").mkdir(exist_ok=True)
    rivit = ("," + RIVINVAIHTO).join(json.dumps(k, ensure_ascii=False) for k in kohteet)
    Path("data/items.json").write_text(
        "[" + RIVINVAIHTO + rivit + RIVINVAIHTO + "]" + RIVINVAIHTO, encoding="utf-8")


def lataa_meta(nyt):
    polku = Path("data/meta.json")
    if polku.exists():
        meta = json.loads(polku.read_text(encoding="utf-8"))
    else:
        meta = {"ensimmainen_ajo": nyt.isoformat()}
    meta["viimeisin_ajo"] = nyt.isoformat()
    Path("data").mkdir(exist_ok=True)
    polku.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def hae_kaikki():
    haetut, tila, gdelt_kaytetty = [], [], False
    for lahde in LAHTEET:
        try:
            if lahde["tyyppi"] == "gdelt":
                if gdelt_kaytetty:
                    time.sleep(6)  # GDELT sallii vain yhden pyynnön viiden sekunnin välein
                gdelt_kaytetty = True
                rivit = hae_gdelt(lahde)
            else:
                rivit = lue_rss(lataa(lahde["url"]), lahde)
            tila.append((lahde["nimi"], len(rivit), ""))
            haetut.extend(rivit)
        except Exception as virhe:
            print(f"VIRHE {lahde['nimi']}: {virhe}")
            tila.append((lahde["nimi"], 0, str(virhe)[:80]))
    return haetut, tila


def paivita_kohteet(vanhat, haetut, nyt):
    raja = nyt - timedelta(days=SAILYTYS_PAIVIA)
    tunnetut = {k["id"] for k in vanhat}
    kohteet = [k for k in vanhat if datetime.fromisoformat(k["aika"]) >= raja]
    for rivi in haetut:
        tunnus = hashlib.sha1(rivi["linkki"].encode()).hexdigest()[:12]
        if tunnus in tunnetut:
            continue
        aika = min(rivi["aika"] or nyt, nyt)
        if aika < raja:
            continue
        tiedot = luokittele(rivi["otsikko"], rivi["yhteenveto"])
        if tiedot is None:
            continue
        tunnetut.add(tunnus)
        kohteet.append({"id": tunnus, "otsikko": rivi["otsikko"], "linkki": rivi["linkki"],
                        "lahde": rivi["lahde"], "aika": aika.isoformat(), **tiedot})
    kohteet.sort(key=lambda k: k["aika"], reverse=True)
    return kohteet


def mittarit_html(mittarit):
    osat = ["<div class='mittarit'>"]
    for teema, (vari, otsikko, perustelu) in mittarit.items():
        osat.append(
            f"<div class='kortti {vari}'><div class='teema'>{escape(teema)}</div>"
            f"<div class='tila'>{escape(otsikko)}</div>"
            f"<div class='perustelu'>{escape(perustelu)}</div></div>"
        )
    osat.append("</div>")
    return "".join(osat)


def uutiset_html(kohteet, nyt):
    osat = []
    for k in kohteet:
        aika = datetime.fromisoformat(k["aika"]).astimezone(HELSINKI)
        uusi = " <span class='uusi'>uusi</span>" if (nyt - k["aika_dt"]) < timedelta(hours=6) else ""
        palkki = "".join(
            f"<span class='solu'><b>{nimi}</b>{escape(k[avain])}</span>"
            for nimi, avain in (("Kuka", "kuka"), ("Mitä", "mita"), ("Missä", "missa"), ("Kenelle", "kenelle"))
        )
        osat.append(
            f"<article class='uutinen' data-teemat='{escape('|'.join(k['teemat']))}'>"
            f"<div class='palkki' title='Automaattinen arvio otsikosta'>{palkki}</div>"
            f"<div class='sisalto'><a href='{escape(k['linkki'])}' rel='noopener'>{escape(k['otsikko'])}</a>{uusi}"
            f"<div class='meta'>{escape(k['lahde'])} · {aika.strftime('%d.%m. %H:%M')}</div></div>"
            "</article>"
        )
    return "".join(osat) if osat else "<p>Ei uutisia vielä.</p>"


SIVUPOHJA = """<!doctype html>
<html lang="fi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tilannekuva</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 1100px; margin: 0 auto; padding: 1rem;
         line-height: 1.45; color: #1a1a1a; background: #fafafa; }
  h1 { margin-bottom: 0; }
  .paivitetty { color: #666; margin-top: 0.25rem; }
  .mittarit { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 0.75rem;
              margin: 1rem 0; }
  .kortti { background: #fff; border-left: 8px solid #777; padding: 0.6rem 0.8rem; border-radius: 4px;
            box-shadow: 0 1px 2px rgba(0,0,0,.12); }
  .kortti.vihrea { border-color: #1b873f; } .kortti.keltainen { border-color: #d9a400; }
  .kortti.punainen { border-color: #c62828; } .kortti.harmaa { border-color: #777; }
  .teema { font-weight: 600; } .tila { font-size: 0.95rem; margin: 0.15rem 0; }
  .vihrea .tila { color: #1b873f; } .keltainen .tila { color: #9a7400; }
  .punainen .tila { color: #c62828; font-weight: 600; } .harmaa .tila { color: #666; }
  .perustelu { font-size: 0.8rem; color: #555; }
  .suodattimet { margin: 1rem 0; display: flex; flex-wrap: wrap; gap: 0.4rem; }
  .suodattimet button { border: 1px solid #bbb; background: #fff; border-radius: 999px; padding: 0.25rem 0.7rem;
                        cursor: pointer; font-size: 0.85rem; }
  .suodattimet button.valittu { background: #1a1a1a; color: #fff; }
  .uutinen { display: flex; gap: 0.8rem; background: #fff; padding: 0.55rem 0.7rem; margin-bottom: 0.4rem;
             border-radius: 4px; box-shadow: 0 1px 2px rgba(0,0,0,.08); }
  .uutinen[hidden] { display: none; }
  .palkki { display: grid; grid-template-columns: repeat(2, minmax(70px, 1fr)); gap: 2px; width: 230px;
            flex: none; font-size: 0.72rem; }
  .solu { background: #f0f0f0; padding: 2px 5px; border-radius: 3px; overflow: hidden; }
  .solu b { display: block; color: #777; font-weight: 600; font-size: 0.65rem; }
  .sisalto a { color: #0b3d91; text-decoration: none; font-weight: 500; }
  .sisalto a:hover { text-decoration: underline; }
  .meta { color: #777; font-size: 0.8rem; }
  .uusi { background: #c62828; color: #fff; font-size: 0.65rem; padding: 1px 5px; border-radius: 3px; }
  @media (max-width: 700px) { .uutinen { flex-direction: column; } .palkki { width: 100%; } }
  footer { color: #666; font-size: 0.8rem; margin: 2rem 0; }
</style>
</head>
<body>
<h1>Tilannekuva</h1>
<p class="paivitetty">Päivitetty __PAIVITETTY__ (Suomen aika). Mittari vertaa viimeistä 24 tuntia teeman
omaan normaaliin: vihreä pysynyt samana, keltainen kehittyy uuteen suuntaan, punainen äkillinen ja yllättävä.
Mittari kertoo uutisvirran poikkeamasta, ei tilanteen todellisesta vaarallisuudesta.</p>
__MITTARIT__
<div class="suodattimet">__NAPIT__</div>
__UUTISET__
<footer>
Lähteiden tila tällä ajolla: __TILA__<br>
Näytetään vain otsikot ja linkit alkuperäisiin uutisiin. Kuka, Mitä, Missä ja Kenelle ovat automaattinen
arvio otsikosta, joten tarkista aina alkuperäinen uutinen. Harrasteprojekti.
</footer>
<script>
const napit = document.querySelectorAll('[data-suodata]');
napit.forEach(function (nappi) {
  nappi.addEventListener('click', function () {
    const teema = nappi.dataset.suodata;
    document.querySelectorAll('.uutinen').forEach(function (u) {
      u.hidden = !(teema === 'kaikki' || u.dataset.teemat.split('|').includes(teema));
    });
    napit.forEach(function (x) { x.classList.toggle('valittu', x === nappi); });
  });
});
</script>
</body>
</html>
"""


def main(nyt=None):
    nyt = nyt or datetime.now(timezone.utc)
    haetut, tila = hae_kaikki()
    if not any(n > 0 for _, n, _ in tila):
        print("Yksikään lähde ei vastannut. Ajo keskeytetään, vanha sivu säilyy.")
        sys.exit(1)

    meta = lataa_meta(nyt)
    alku = datetime.fromisoformat(meta["ensimmainen_ajo"])
    kohteet = paivita_kohteet(lataa_kohteet(), haetut, nyt)
    tallenna_kohteet(kohteet)

    for k in kohteet:
        k["aika_dt"] = datetime.fromisoformat(k["aika"])
    teemat = list(TEEMAT) + ["Muu maailma"]
    mittarit = {t: laske_mittari([k for k in kohteet if t in k["teemat"]], nyt, alku) for t in teemat}
    nayta = [k for k in kohteet if nyt - k["aika_dt"] <= timedelta(days=NAYTA_PAIVIA)][:MAX_NAYTETTAVAT]

    napit = "<button class='valittu' data-suodata='kaikki'>Kaikki</button>" + "".join(
        f"<button data-suodata='{escape(t)}'>{escape(t)}</button>" for t in teemat)
    tila_teksti = ", ".join(
        f"{escape(nimi)} ({n})" if not virhe else f"{escape(nimi)} (virhe: {escape(virhe)})"
        for nimi, n, virhe in tila)
    sivu = (SIVUPOHJA
            .replace("__PAIVITETTY__", nyt.astimezone(HELSINKI).strftime("%d.%m.%Y klo %H:%M"))
            .replace("__MITTARIT__", mittarit_html(mittarit))
            .replace("__NAPIT__", napit)
            .replace("__UUTISET__", uutiset_html(nayta, nyt))
            .replace("__TILA__", tila_teksti))
    Path("site").mkdir(exist_ok=True)
    Path("site/index.html").write_text(sivu, encoding="utf-8")
    print(f"Uutisia tallessa: {len(kohteet)}. Mittarit: " +
          ", ".join(f"{t}={v[0]}" for t, v in mittarit.items()))


if __name__ == "__main__":
    main()

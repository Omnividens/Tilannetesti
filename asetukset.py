"""Tilannekuva: asetukset.
Täällä ovat lähteet, avainsanat ja värien rajat. Muokkaa tätä tiedostoa, älä build.py:tä.
"""

import re

# ---------- ASETUKSET: muokkaa näitä ----------
LAHTEET = [
    {"nimi": "BBC", "tyyppi": "rss", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"nimi": "Yle", "tyyppi": "rss", "url": "https://feeds.yle.fi/uutiset/v1/majorHeadlines/YLE_UUTISET.rss"},
    {"nimi": "Yle ulkomaat", "tyyppi": "rss", "url": "https://feeds.yle.fi/uutiset/v1/recent.rss?publisherIds=YLE_UUTISET&concepts=18-34953"},
    {"nimi": "Yle News", "tyyppi": "rss", "url": "https://feeds.yle.fi/uutiset/v1/majorHeadlines/YLE_NEWS.rss"},
    {"nimi": "Al Jazeera", "tyyppi": "rss", "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"nimi": "DW", "tyyppi": "rss", "url": "https://rss.dw.com/xml/rss-en-world"},
    {"nimi": "Guardian", "tyyppi": "rss", "url": "https://www.theguardian.com/world/rss"},
    {"nimi": "Bellingcat", "tyyppi": "rss", "url": "https://www.bellingcat.com/feed/"},
    {"nimi": "FDD LWJ", "tyyppi": "rss", "url": "https://www.longwarjournal.org/feed"},
    {"nimi": "War on the Rocks", "tyyppi": "rss", "url": "https://warontherocks.com/feed/"},
    {"nimi": "The Record", "tyyppi": "rss", "url": "https://therecord.media/feed"},
    # Lähteet, joilla ei ole omaa syötettä, haetaan GDELT-hakupalvelun kautta
    {"nimi": "AP", "tyyppi": "gdelt", "domain": "apnews.com"},
    {"nimi": "Reuters", "tyyppi": "gdelt", "domain": "reuters.com"},
    {"nimi": "ISW", "tyyppi": "gdelt", "domain": "understandingwar.org"},
]
GDELT_HAKU = (
    "(war OR attack OR strike OR military OR missile OR drone OR sanctions "
    "OR ceasefire OR sabotage OR seized OR coup OR cyberattack OR nuclear)"
)
SAILYTYS_PAIVIA = 30      # kuinka kauan uutisia säilytetään
NAYTA_PAIVIA = 7          # kuinka vanhoja uutisia sivulla näytetään
MAX_NAYTETTAVAT = 200     # uutisten enimmäismäärä sivulla
POHJA_PAIVIA = 14         # kuinka monen vuorokauden jaksoon nykytilaa verrataan
MIN_POHJA = 5             # montako vuorokautta dataa tarvitaan ennen väriä
# Värien rajat: muuta näitä, jos mittari on liian herkkä tai liian hidas
RAJAT = {
    "pun_z": 3.0, "pun_suhde": 2.5, "pun_lahteet": 3, "pun_kuorma": 8,
    "kelt_z": 1.5, "kelt_suhde": 1.3, "kelt_kuorma": 5, "uudet_termit": 3,
}
# ----------------------------------------------


def rx(*osat):
    """Tekee sanalistasta hakukuvion. Sana alkaa sanan alusta, mutta loppu saa
    vaihdella, joten 'ukrain' löytää myös 'Ukrainaan'. Merkki $ lopussa vaatii,
    että sana loppuu siihen. Merkki ! alussa vaatii täsmälleen samat isot ja
    pienet kirjaimet (esimerkiksi !US ei osu sanaan 'us')."""
    kuviot = []
    for osa in osat:
        if osa.startswith("!"):
            kuviot.append("(?-i:(?<![A-Za-z])" + osa[1:] + "(?![A-Za-z]))")
        else:
            loppu = "(?![a-zäöå0-9])" if osa.endswith("$") else ""
            kuviot.append("(?<![a-zäöå0-9])" + osa.rstrip("$") + loppu)
    return re.compile("|".join(kuviot), re.IGNORECASE)


# Teemat: mihin tilanteeseen uutinen liittyy (englanti ja suomi)
TEEMAT = {
    "Ukraina ja Venäjä": rx("ukrain", "kyiv", "kiev", "kremlin", "russia", "putin",
                            "moscow", "zelensk", "donbas", "kharkiv", "crimea",
                            "venäj", "moskova", "kiova", "kreml"),
    "Lähi-itä": rx("gaza", "israel", "hamas", "hezbollah", "hizbollah", "lebanon",
                   "iran", "tehran", "houthi", "huthi", "yemen", "syria", "iraq",
                   "west bank", "libanon", "syyria", "irak", "jemen", "red sea",
                   "punaisen meren"),
    "Itämeri ja pohjoinen Eurooppa": rx("baltic", "estonia", "latvia", "lithuania", "finland",
                                        "finnish", "kaliningrad", "nordic", "sweden", "norway",
                                        "arctic", "shadow fleet", "poland", "itämer", "suomi",
                                        "suomen", "viro$", "virossa", "liettua", "pohjoism",
                                        "ruotsi", "norja", "varjolaivasto", "suomenlahti",
                                        "puola$", "gulf of finland"),
    "Indo-Pacific": rx("china", "chinese", "beijing", "taiwan", "south china sea",
                       "north korea", "pyongyang", "philippine", "japan", "kiina",
                       "peking", "pohjois-korea", "south korea", "indo-pacific", "myanmar"),
    "Afrikka ja Sahel": rx("sahel", "mali$", "niger$", "burkina", "sudan", "somalia",
                           "congo", "libya", "ethiopia", "nigeria", "mozambique",
                           "africa", "afrikka", "al-shabaab"),
    "Terrorismi ja jihadismi": rx("terror", "isis$", "islamic state", "al-qaeda", "al qaeda",
                                  "jihad", "extremis", "taliban", "ääriliik"),
    "Kyber ja vakoilu": rx("cyber", "hack", "ransomware", "data breach", "ddos", "malware",
                           "espionage", "spy$", "spies", "disinformation", "kyber",
                           "vakoil", "tietomurto", "kiristyshaitta"),
}

# Kategoriat: mitä tapahtui. Jokaisella säännöllä on paino (vakavuus).
# Sääntö = (paino, kuvio, lisäkuvio). Lisäkuvion pitää myös löytyä, jos se on annettu.
KATEGORIAT = {
    "Isku ja taistelut": [(2, rx("strikes?$", "airstrike", "missile", "drones?$", "shelling",
                                 "bombard", "offensive", "clashes", "attack", "killed",
                                 "isk[uie]", "ohju[sk]", "droon", "pommi", "taistel",
                                 "hyökkä", "kuoli", "kuole"), None)],
    "Haltuunotto": [(3, rx("seiz", "hijack", "detain", "boarded", "boarding", "intercepted",
                           "impound", "takavarikoi", "haltuun", "kaappas", "pysäytti"),
                     rx("tanker", "vessel", "ship$", "ships$", "cargo", "freighter",
                        "boat$", "säiliöalu", "alus$", "alukse", "laiva", "tankkeri"))],
    "Sabotaasi": [(3, rx("sabot", "(undersea|subsea|submarine|seabed) (cable|pipeline)",
                         "kaapelivaurio", "kaapeli[a-zäö]* (vaurioitui|katkesi|rikkoutui)",
                         "anchor[- ]drag"), None)],
    "Poliittinen muutos": [(4, rx("coup$", "martial law", "vallankaappa", "sotatila"), None),
                           (2, rx("resign", "ousted", "impeach", "no-confidence", "election",
                                  "snap poll", "vaali", "hallitus kaatui"), None)],
    "Pakotteet ja talous": [(1, rx("sanction", "embargo", "tariff", "export ban", "pakote",
                                   "tulli"), None)],
    "Neuvottelut ja tulitauko": [(1, rx("ceasefire", "truce", "talks$", "negotiat", "peace deal",
                                        "summit", "tulitau", "neuvottel", "rauhan"), None)],
    "Kyber ja vaikuttaminen": [(2, rx("cyber", "hack", "ransomware", "data breach", "ddos",
                                      "malware", "disinformation", "propaganda", "kyber",
                                      "kiristyshaitta", "tietomurto", "disinformaatio",
                                      "vaikuttamis"), None)],
    "Vakoilu ja pidätykset": [(2, rx("spy$", "spies", "espionage", "arrested", "expel",
                                     "vakoil", "pidätet", "karkote"), None)],
    "Terroriteko": [(3, rx("terror", "suicide bomb", "isis$", "islamic state", "al-qaeda",
                           "al qaeda", "jihadi", "itsemurha"), None)],
    "Ydin ja asevarustelu": [(3, rx("nuclear", "warhead", "icbm", "enrichment", "ydin"), None)],
    "Kriisi ja evakuointi": [(2, rx("evacuat", "state of emergency", "mobiliz", "mobilis",
                                    "hätätila", "evakuoi", "liikekanna"), None)],
}
YLLATYS = rx("unprecedented", "surprise", "sudden", "unexpected", "snap$", "first time",
             "shock", "yllät", "äkillis", "ennennäkemät")

# Toimijat: (nimi, kuvio, onko alue). Alueita käytetään myös paikan arvaamiseen.
TOIMIJAT = [
    ("Venäjä", rx("russia", "kremlin", "putin", "moscow", "venäj", "moskova", "kreml"), True),
    ("Ukraina", rx("ukrain", "kyiv", "kiev", "zelensk", "kiova"), True),
    ("Israel", rx("israel", "idf$", "netanyahu"), True),
    ("Gaza", rx("gaza"), True),
    ("Hamas", rx("hamas"), False),
    ("Hizbollah", rx("hezbollah", "hizbollah", "hizbullah"), False),
    ("Iran", rx("iran", "tehran"), True),
    ("Houthit", rx("houthi", "huthi"), False),
    ("Jemen", rx("yemen", "jemen"), True),
    ("Syyria", rx("syria", "syyria", "damascus"), True),
    ("Libanon", rx("lebanon", "libanon", "beirut"), True),
    ("Irak", rx("iraq", "irak"), True),
    ("Yhdysvallat", rx("united states", "u[.]s[.]", "!US", "pentagon", "trump",
                       "washington", "white house", "yhdysvalt", "american"), True),
    ("Kiina", rx("china", "chinese", "beijing", "xi jinping", "kiina", "peking"), True),
    ("Taiwan", rx("taiwan"), True),
    ("Pohjois-Korea", rx("north korea", "pyongyang", "pohjois-korea"), True),
    ("Etelä-Korea", rx("south korea", "seoul", "etelä-korea"), True),
    ("Japani", rx("japan", "tokyo", "japani"), True),
    ("Nato", rx("nato$"), False),
    ("EU", rx("european union", "!EU", "euroopan unioni", "brussels"), False),
    ("Suomi", rx("finland", "finnish", "suom", "helsinki"), True),
    ("Viro", rx("estonia", "viro$", "virolai", "tallinn"), True),
    ("Latvia", rx("latvia", "riga$"), True),
    ("Liettua", rx("lithuania", "liettua", "vilnius"), True),
    ("Puola", rx("poland", "puola$", "warsaw"), True),
    ("Saksa", rx("germany", "german$", "berlin", "saksa"), True),
    ("Britannia", rx("britain", "british", "uk$", "london", "britannia"), True),
    ("Ranska", rx("france", "french", "paris", "ranska"), True),
    ("Turkki", rx("turkey", "turkish", "ankara", "turkki"), True),
    ("Pakistan", rx("pakistan"), True),
    ("Intia", rx("india$", "indian$", "delhi", "intia"), True),
    ("Afganistan", rx("afghan"), True),
    ("Taleban", rx("taliban", "taleban"), False),
    ("Sudan", rx("sudan"), True),
    ("Somalia", rx("somalia"), True),
    ("Libya", rx("libya"), True),
    ("Mali", rx("mali$"), True),
    ("Nigeria", rx("nigeria"), True),
    ("Isis", rx("isis$", "islamic state"), False),
    ("Al-Qaida", rx("al-qaeda", "al qaeda"), False),
]
ALUEET = {nimi for nimi, _, alue in TOIMIJAT if alue}

# Tarkat paikat, joita käytetään ennen maiden nimiä
PAIKAT = [
    ("Kiova", rx("kyiv", "kiev", "kiova")),
    ("Harkova", rx("kharkiv", "harkova")),
    ("Odessa", rx("odesa", "odessa")),
    ("Donbas", rx("donbas", "donetsk", "luhansk")),
    ("Krim", rx("crimea", "krim$")),
    ("Moskova", rx("moscow", "moskova")),
    ("Kaliningrad", rx("kaliningrad")),
    ("Gaza", rx("gaza")),
    ("Länsiranta", rx("west bank", "länsiranta")),
    ("Tel Aviv", rx("tel aviv")),
    ("Jerusalem", rx("jerusalem")),
    ("Beirut", rx("beirut")),
    ("Damaskos", rx("damascus", "damaskos")),
    ("Teheran", rx("tehran", "teheran")),
    ("Punainen meri", rx("red sea", "punaisen meren", "punainen meri")),
    ("Hormuzinsalmi", rx("strait of hormuz", "hormuz")),
    ("Musta meri", rx("black sea", "musta meri", "mustan meren")),
    ("Itämeri", rx("baltic", "itämer")),
    ("Suomenlahti", rx("gulf of finland", "suomenlahti")),
    ("Arktis", rx("arctic", "arktis")),
    ("Taiwaninsalmi", rx("taiwan strait")),
    ("Etelä-Kiinan meri", rx("south china sea", "etelä-kiinan meri")),
    ("Peking", rx("beijing", "peking")),
    ("Sahel", rx("sahel")),
    ("Khartum", rx("khartoum", "khartum")),
    ("Kabul", rx("kabul")),
]

PYSAYTYSSANAT = set("""about after again against being between could during first from have into more most
other over said says that their there these they this those through under until were what when where which while
will with would your news report reports says official officials""".split())

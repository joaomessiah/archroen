#!/usr/bin/env python3
"""
Build pottery_vocab_master.csv — the canonical pottery reference dataset for the pipeline.

Reads pottery_vocab_en.csv and pottery_vocab_nl.csv, enriches each typology code
with abbreviations, German/French names, ware type, vessel form, production region,
date source, and date confidence, and resolves cross-system synonym relationships.

Output columns:
  id, typology_code, synonyms, abbreviations,
  pot_name_en, pot_name_nl, pot_name_de, pot_name_fr,
  ware_type, vessel_form, production_region,
  date_start, date_end, date_confidence, date_source

Sources:
  - pottery_vocab_en/nl.csv (base data supplied by collaborating archaeologist)
  - Stuart 1977; Brunsting 1937; Dragendorff 1895; Oelmann 1914; Holwerda 1923
  - Gose 1950; Chenet 1941; Hayes 1972; Ettlinger et al. 1990; Deru 1996
  - Potsherd: Atlas of Roman Pottery (potsherd.net) — cross-reference
  - Domain knowledge of Low Countries Roman pottery typology
"""

import csv
import re
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "vocabularies"
EN_FILE  = DATA_DIR / "pottery_vocab_en.csv"
NL_FILE  = DATA_DIR / "pottery_vocab_nl.csv"
OUT_FILE = DATA_DIR / "pottery_vocab_master.csv"

FIELDNAMES = [
    "id", "typology_code", "synonyms", "abbreviations",
    "pot_name_en", "pot_name_nl", "pot_name_de", "pot_name_fr",
    "ware_type", "vessel_form", "production_region",
    "date_start", "date_end", "date_confidence", "date_source",
]

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM METADATA
# Keys must match the leading word(s) of the typology_code exactly.
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_META = {
    "Dragendorff": {
        "abbrevs": ["Drag.", "Dr.", "D."],
        "region":  "Gaulish (South/Central/East — varies by type and period)",
        "source":  "Dragendorff 1895; Oswald & Pryce 1920; Webster 1996",
        "conf":    "certain",
    },
    "Stuart": {
        "abbrevs": ["St.", "Stu."],
        "region":  "Rhineland / Low Countries regional",
        "source":  "Stuart 1977",
        "conf":    "certain",
    },
    "Brunsting": {
        "abbrevs": ["Br.", "Bru.", "Brunst."],
        "region":  "Rhineland / Nijmegen region",
        "source":  "Brunsting 1937",
        "conf":    "certain",
    },
    "Niederbieber": {
        "abbrevs": ["NB", "Nb.", "Nieb."],
        "region":  "Rhineland (Rhineland-Palatinate)",
        "source":  "Oelmann 1914",
        "conf":    "certain",
    },
    "Holwerda": {
        "abbrevs": ["Holw.", "HBW"],
        "region":  "Low Countries (Netherlands)",
        "source":  "Holwerda 1923",
        "conf":    "certain",
    },
    "Gose": {
        "abbrevs": ["Gos.", "G."],
        "region":  "Rhineland (Trier region)",
        "source":  "Gose 1950",
        "conf":    "certain",
    },
    "Alzey": {
        "abbrevs": ["Alz.", "Al."],
        "region":  "Rhineland (Rheinzabern / Speyer region)",
        "source":  "Unverzagt 1916",
        "conf":    "certain",
    },
    "Dressel": {
        "abbrevs": ["Dres."],
        "region":  "varies by type (Italian, Spanish, Gallic, African)",
        "source":  "Dressel 1899; Callender 1965",
        "conf":    "certain",
    },
    "Chenet": {
        "abbrevs": ["Chn.", "Ch."],
        "region":  "Argonnian (NE France — Argonne Forest)",
        "source":  "Chenet 1941",
        "conf":    "certain",
    },
    "Hofheim": {
        "abbrevs": ["Hof.", "Hofh."],
        "region":  "Rhineland / Taunus region",
        "source":  "Ritterling 1912",
        "conf":    "certain",
    },
    "Deru": {
        "abbrevs": ["Deru"],
        "region":  "Rhineland / NE Gaul (Champagne-Ardenne)",
        "source":  "Deru 1996",
        "conf":    "certain",
    },
    "Oelmann": {
        "abbrevs": ["Oe.", "Oelm."],
        "region":  "Rhineland (Rhineland-Palatinate)",
        "source":  "Oelmann 1914",
        "conf":    "certain",
    },
    "Haltern": {
        "abbrevs": ["Halt.", "Ha."],
        "region":  "Italian / South Gaulish (early Augustan imports)",
        "source":  "Loeschcke 1909",
        "conf":    "certain",
    },
    "Haalebos": {
        "abbrevs": ["Haal."],
        "region":  "Rhineland / Nijmegen region",
        "source":  "Haalebos 1990",
        "conf":    "certain",
    },
    "Ritterling": {
        "abbrevs": ["Ritt.", "Ritter."],
        "region":  "South Gaulish / Italian (early imports)",
        "source":  "Ritterling 1912",
        "conf":    "certain",
    },
    "Ludowici": {
        "abbrevs": ["Lud.", "Ludow."],
        "region":  "East Gaulish (Rheinzabern)",
        "source":  "Ludowici 1927",
        "conf":    "certain",
    },
    "Curle": {
        "abbrevs": ["Cur."],
        "region":  "Central / East Gaulish",
        "source":  "Curle 1911",
        "conf":    "certain",
    },
    "Hayes": {
        "abbrevs": ["Hay."],
        "region":  "North Africa (Tunisia / Libya)",
        "source":  "Hayes 1972",
        "conf":    "certain",
    },
    "Conspectus": {
        "abbrevs": ["Cons.", "Consp."],
        "region":  "Italian (Arretine — Arezzo)",
        "source":  "Ettlinger et al. 1990",
        "conf":    "certain",
    },
    "Gauloise": {
        "abbrevs": ["Gaul.", "Gauloise"],
        "region":  "South Gaul (Languedoc — Narbonnaise)",
        "source":  "Laubenheimer 1985",
        "conf":    "certain",
    },
    "Loeschcke": {
        "abbrevs": ["Loe.", "L."],
        "region":  "Roman Mediterranean / varies by lamp type",
        "source":  "Loeschcke 1919",
        "conf":    "certain",
    },
    "Vanvinckenroye": {
        "abbrevs": ["Vanv.", "VV"],
        "region":  "Rhineland / Tongeren region (Belgium)",
        "source":  "Vanvinckenroye 1991",
        "conf":    "certain",
    },
    "Mayen": {
        "abbrevs": ["May."],
        "region":  "Rhineland — Eifel (Mayen / Andernach)",
        "source":  "Redknap 1988",
        "conf":    "certain",
    },
    "Van Ossel": {
        "abbrevs": ["VO"],
        "region":  "NE Gaul / Rhineland",
        "source":  "Van Ossel 1992",
        "conf":    "certain",
    },
    "Hussong-Cüppers": {
        "abbrevs": ["HC", "H-C"],
        "region":  "Rhineland (Trier / Mosel region)",
        "source":  "Hussong & Cüppers 1972",
        "conf":    "certain",
    },
    "Blicquy": {
        "abbrevs": ["Blic.", "Bl."],
        "region":  "Belgium (Hainaut — Blicquy production site)",
        "source":  "Willems 1973",
        "conf":    "certain",
    },
    "Eifel": {
        "abbrevs": ["Eifel"],
        "region":  "Rhineland — Eifel region",
        "source":  "Gilles 1985",
        "conf":    "certain",
    },
    "Trier": {
        "abbrevs": ["Trier"],
        "region":  "Rhineland (Trier / Augusta Treverorum)",
        "source":  "Hussong & Cüppers 1972",
        "conf":    "certain",
    },
    "De Clercq": {
        "abbrevs": ["DC"],
        "region":  "Local — NW Gaul / Flanders-Zeeland",
        "source":  "De Clercq 2009",
        "conf":    "approximate",
    },
    "Van den Broeke": {
        "abbrevs": ["VdB", "VDB"],
        "region":  "Local — Netherlands / Belgium (Iron Age to early Roman)",
        "source":  "Van den Broeke 1987",
        "conf":    "approximate",
    },
    "Wijster": {
        "abbrevs": ["Wij."],
        "region":  "Local — Northern Netherlands",
        "source":  "Van Es 1967",
        "conf":    "approximate",
    },
    "Rigoir": {
        "abbrevs": ["Rig."],
        "region":  "South Gaul (Narbonnaise) — Dérivée-des-sigillées paléochrétiennes",
        "source":  "Rigoir 1968",
        "conf":    "probable",
    },
    "Peacock & Williams": {
        "abbrevs": ["PW", "P&W", "P.W."],
        "region":  "varies by class",
        "source":  "Peacock & Williams 1986",
        "conf":    "certain",
    },
    "Höpken": {
        "abbrevs": ["Höpk."],
        "region":  "Rhineland (Cologne — Colonia Agrippina)",
        "source":  "Höpken 2005",
        "conf":    "approximate",
    },
    "Hanut": {
        "abbrevs": ["Han."],
        "region":  "NE Gaul / Rhineland",
        "source":  "Hanut 2000",
        "conf":    "approximate",
    },
    "Oberaden": {
        "abbrevs": ["Ob.", "Ober."],
        "region":  "Italian / South Gaulish (early Augustan)",
        "source":  "Loeschcke 1909; Albrecht 1942",
        "conf":    "certain",
    },
    "Dangstetten": {
        "abbrevs": ["Dan.", "Dang."],
        "region":  "Italian / South Gaulish (pre-Tiberian)",
        "source":  "Fingerlin 1986",
        "conf":    "certain",
    },
    "Déchelette": {
        "abbrevs": ["Déch.", "Dec."],
        "region":  "Central Gaulish (Lezoux and related centres)",
        "source":  "Déchelette 1904",
        "conf":    "certain",
    },
    "Baudoux": {
        "abbrevs": ["Baud."],
        "region":  "NE Gaul",
        "source":  "Baudoux 1996",
        "conf":    "approximate",
    },
    "Brulet": {
        "abbrevs": ["Brul."],
        "region":  "Romano-Belgian (Belgium / NE Gaul)",
        "source":  "Brulet et al. 2010",
        "conf":    "approximate",
    },
    "Pascual": {
        "abbrevs": ["Pasc."],
        "region":  "Tarraconensis (NE Spain)",
        "source":  "Pascual 1977",
        "conf":    "certain",
    },
    "Pélichet": {
        "abbrevs": ["Pél.", "Pel."],
        "region":  "varies (Italian, Gallic)",
        "source":  "Pélichet 1946",
        "conf":    "probable",
    },
    "Gilles": {
        "abbrevs": ["Gil."],
        "region":  "Rhineland (Trier / Mosel region)",
        "source":  "Gilles 1985",
        "conf":    "certain",
    },
    "Pirling": {
        "abbrevs": ["Pirl.", "Gellep"],
        "region":  "Rhineland / Lower Rhine (Krefeld-Gellep)",
        "source":  "Pirling 1966",
        "conf":    "certain",
    },
    "Gellep": {
        "abbrevs": ["Gellep", "Pirl."],
        "region":  "Rhineland / Lower Rhine (Krefeld-Gellep)",
        "source":  "Pirling 1966",
        "conf":    "certain",
    },
    "ACO-beker": {
        "abbrevs": ["ACO"],
        "region":  "North Italian / Gaulish",
        "source":  "Ettlinger 1952",
        "conf":    "certain",
    },
    "Brabant/Hien": {
        "abbrevs": ["B/H", "Brabant/Hien"],
        "region":  "Local — Southern Netherlands / Northern Belgium",
        "source":  "Van den Broeke 1987; Hiddink 2010",
        "conf":    "approximate",
    },
    "Nijmeegs": {
        "abbrevs": ["Nijm.", "NJ"],
        "region":  "Rhineland / Nijmegen region",
        "source":  "Brunsting 1937",
        "conf":    "approximate",
    },
    "Camulodunum": {
        "abbrevs": ["Cam.", "C."],
        "region":  "Continental / British imports",
        "source":  "Hawkes & Hull 1947",
        "conf":    "certain",
    },
    "Gose/Hofheim": {
        "abbrevs": ["G/H"],
        "region":  "Rhineland (Trier / Taunus region)",
        "source":  "Gose 1950; Ritterling 1912",
        "conf":    "certain",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# WARE TYPE — ordered longest-first so more specific rules win
# ─────────────────────────────────────────────────────────────────────────────
WARE_RULES: list[tuple[str, str]] = [
    ("Argonnian terra sigillata",        "terra sigillata"),
    ("East Gaulish terra sigillata",     "terra sigillata"),
    ("Tongeren Belgic ware",             "belgic ware"),
    ("Tongeren fine ware",               "fine ware"),
    ("Tongeren late Roman",              "late Roman ware"),
    ("Tongeren coarse ware",             "coarse ware"),
    ("Tongeren smooth-walled",           "smooth-walled ware"),
    ("Late Roman color-coated",          "color-coated ware"),
    ("Late Roman coarse ware",           "coarse ware"),
    ("Late Roman African",               "amphora"),
    ("Late Roman Eastern Mediterranean", "amphora"),
    ("Late Roman Gallic",                "amphora"),
    ("Late Roman painted ware",          "painted ware"),
    ("Late Roman",                       "late Roman ware"),
    ("Early Roman",                      "early Roman ware"),
    ("Handmade late Roman",              "handmade ware"),
    ("African Red Slip ware",            "African Red Slip"),
    ("Terra sigillata",                  "terra sigillata"),
    ("Terra rubra",                      "terra rubra"),
    ("Terra nigra",                      "terra nigra"),
    ("Belgic grey ware",                 "belgic grey ware"),
    ("Belgic ware",                      "belgic ware"),
    ("Arretine ware",                    "arretine ware"),
    ("Color-coated",                     "color-coated ware"),
    ("Thin-walled",                      "thin-walled ware"),
    ("Smooth-walled",                    "smooth-walled ware"),
    ("Coated ware",                      "color-coated ware"),
    ("White clay",                       "white-clay ware"),
    ("Coarse ware",                      "coarse ware"),
    ("Handmade",                         "handmade ware"),
    ("Native wheel-thrown",              "native ware"),
    ("Native coarse ware",               "native ware"),
    ("Native",                           "native ware"),
    ("Mayen ware",                       "Mayen ware"),
    ("Eifel buff ware",                  "Eifel ware"),
    ("Eifel coarse ware",                "Eifel ware"),
    ("Eifel flanged",                    "Eifel ware"),
    ("Eifel bead-rim",                   "Eifel ware"),
    ("Eifel carinated",                  "Eifel ware"),
    ("Eifel burnished",                  "Eifel ware"),
    ("Eifel",                            "Eifel ware"),
    ("Rhineland",                        "Rhineland ware"),
    ("Nijmegen coarse ware",             "coarse ware"),
    ("Romano-Belgian coarse ware",       "coarse ware"),
    ("Romano-Belgian",                   "coarse ware"),
    ("Locally produced",                 "local ware"),
    ("Italian wine amphora",             "amphora"),
    ("Italian/Spanish wine amphora",     "amphora"),
    ("Adriatic wine amphora",            "amphora"),
    ("Baetica",                          "amphora"),
    ("Baetican",                         "amphora"),
    ("Spanish",                          "amphora"),
    ("Lusitanian",                       "amphora"),
    ("Gallic wine amphora",              "amphora"),
    ("Gallic amphora",                   "amphora"),
    ("Eastern Mediterranean",           "amphora"),
    ("Pannonian amphora",                "amphora"),
    ("Tarraconensian",                   "amphora"),
    ("Pontic amphora",                   "amphora"),
    ("African amphora",                  "amphora"),
    ("Istrian",                          "amphora"),
    ("Greek wine amphora",               "amphora"),
    ("Sicilian",                         "amphora"),
    ("Regional wine amphora",            "amphora"),
    ("Stand amphora",                    "amphora"),
    ("Amphora",                          "amphora"),
    ("Mortarium",                        "mortarium"),
    ("Firmalampe",                       "oil lamp"),
    ("Bildlampe",                        "oil lamp"),
    ("Kanallampe",                       "oil lamp"),
    ("Volute oil lamp",                  "oil lamp"),
    ("Oil lamp",                         "oil lamp"),
    ("Open oil lamp",                    "oil lamp"),
    ("Dolium",                           "dolium"),
    ("Trier",                            "Trier ware"),
    ("Globular pot",                     "handmade ware"),
    ("Handmade",                         "handmade ware"),
    ("Sand-roughened",                   "thin-walled ware"),
    ("Cylindrical beaker",               "thin-walled ware"),
    ("Tall-necked beaker",               "thin-walled ware"),
    ("Large decorated vase",             "fine ware"),
    ("Hemispherical bowl",               "fine ware"),
]

# ─────────────────────────────────────────────────────────────────────────────
# VESSEL FORM — extracted from pot_name_en (match from end of string)
# ─────────────────────────────────────────────────────────────────────────────
VESSEL_RULES: list[tuple[str, str]] = [
    ("decorated bowl",      "bowl"),
    ("decorated beaker",    "beaker"),
    ("decorated vase",      "vase"),
    ("decorated bowl",      "bowl"),
    ("two-handled cup",     "cup"),
    ("two-handled jug",     "jug"),
    ("two-handled flagon",  "flagon"),
    ("one-handled jug",     "jug"),
    ("ring-neck jug",       "jug"),
    ("ring-neck flagon",    "flagon"),
    ("barrel beaker",       "beaker"),
    ("roughcast beaker",    "beaker"),
    ("barbotine beaker",    "beaker"),
    ("faceted beaker",      "beaker"),
    ("indented beaker",     "beaker"),
    ("biconical beaker",    "beaker"),
    ("globular beaker",     "beaker"),
    ("carinated beaker",    "beaker"),
    ("rouletted beaker",    "beaker"),
    ("small beaker",        "beaker"),
    ("hemispherical bowl",  "bowl"),
    ("carinated bowl",      "bowl"),
    ("flanged bowl",        "bowl"),
    ("bead-rim bowl",       "bowl"),
    ("goblet bowl",         "bowl"),
    ("wide bowl",           "bowl"),
    ("color-coated bowl",   "bowl"),
    ("biconical jar",       "jar"),
    ("globular jar",        "jar"),
    ("storage jar",         "jar"),
    ("wide-mouthed jar",    "jar"),
    ("handled jar",         "jar"),
    ("handled pot",         "jar"),
    ("cooking pot",         "cooking pot"),
    ("bell-shaped lid",     "lid"),
    ("small jug",           "jug"),
    ("small flask",         "flask"),
    ("small cup",           "cup"),
    ("footed cup",          "cup"),
    ("hemispherical cup",   "cup"),
    ("carinated cup",       "cup"),
    ("deep cup",            "cup"),
    ("handled cup",         "cup"),
    ("honey pot",           "jar"),
    ("stand amphora",       "amphora"),
    ("wine amphora",        "amphora"),
    ("fish sauce amphora",  "amphora"),
    ("olive oil amphora",   "amphora"),
    ("defrutum amphora",    "amphora"),
    ("storage vessel",      "storage vessel"),
    ("goblet bowl",         "bowl"),
    ("mortarium",           "mortarium"),
    ("inkwell",             "inkwell"),
    ("tazza",               "tazza"),
    ("platter",             "platter"),
    ("flagon",              "flagon"),
    ("goblet",              "goblet"),
    ("beaker",              "beaker"),
    ("amphora",             "amphora"),
    ("flask",               "flask"),
    ("situla",              "situla"),
    ("plate",               "plate"),
    ("dish",                "dish"),
    ("bowl",                "bowl"),
    ("cup",                 "cup"),
    ("jug",                 "jug"),
    ("jar",                 "jar"),
    ("pot",                 "jar"),
    ("urn",                 "urn"),
    ("lid",                 "lid"),
    ("lamp",                "lamp"),
    ("vase",                "vase"),
]

# ─────────────────────────────────────────────────────────────────────────────
# TRANSLATIONS — ware type and vessel form into German and French
# ─────────────────────────────────────────────────────────────────────────────

DE_WARE: dict[str, str] = {
    "terra sigillata":   "Terra Sigillata",
    "terra rubra":       "Terra Rubra",
    "terra nigra":       "Terra Nigra",
    "arretine ware":     "Arretinische Ware",
    "African Red Slip":  "Afrikanische Rote Glanztonware",
    "belgic ware":       "Belgische Ware",
    "belgic grey ware":  "Belgische Grauware",
    "color-coated ware": "Gefärbte Keramik",
    "thin-walled ware":  "Dünnwandige Keramik",
    "smooth-walled ware":"Glatttonige Keramik",
    "coarse ware":       "Rauwandige Keramik",
    "white-clay ware":   "Weißtonige Keramik",
    "handmade ware":     "Handgemachte Keramik",
    "native ware":       "Einheimische Keramik",
    "local ware":        "Lokale Keramik",
    "amphora":           "Amphore",
    "mortarium":         "Reibschüssel",
    "oil lamp":          "Öllampe",
    "dolium":            "Dolium",
    "fine ware":         "Feinkeramik",
    "painted ware":      "Bemalte Keramik",
    "late Roman ware":   "Spätrömische Keramik",
    "early Roman ware":  "Frührömische Keramik",
    "Mayen ware":        "Mayener Ware",
    "Eifel ware":        "Eifelkeramik",
    "Rhineland ware":    "Rheinische Ware",
    "Trier ware":        "Trierer Ware",
}

FR_WARE: dict[str, str] = {
    "terra sigillata":   "Sigillée",
    "terra rubra":       "Terra Rubra",
    "terra nigra":       "Terra Nigra",
    "arretine ware":     "Sigillée arétine",
    "African Red Slip":  "Sigillée africaine",
    "belgic ware":       "Céramique belge",
    "belgic grey ware":  "Céramique grise belge",
    "color-coated ware": "Céramique engobée",
    "thin-walled ware":  "Céramique à paroi fine",
    "smooth-walled ware":"Céramique lissée",
    "coarse ware":       "Céramique commune",
    "white-clay ware":   "Céramique blanche",
    "handmade ware":     "Céramique faite à la main",
    "native ware":       "Céramique indigène",
    "local ware":        "Céramique locale",
    "amphora":           "Amphore",
    "mortarium":         "Mortier",
    "oil lamp":          "Lampe à huile",
    "dolium":            "Dolium",
    "fine ware":         "Céramique fine",
    "painted ware":      "Céramique peinte",
    "late Roman ware":   "Céramique du Bas-Empire",
    "early Roman ware":  "Céramique du Haut-Empire",
    "Mayen ware":        "Céramique de Mayen",
    "Eifel ware":        "Céramique de l'Eifel",
    "Rhineland ware":    "Céramique rhénane",
    "Trier ware":        "Céramique de Trèves",
}

DE_VESSEL: dict[str, str] = {
    "bowl":           "Schüssel",
    "plate":          "Teller",
    "dish":           "Schale",
    "platter":        "Teller",
    "cup":            "Becher",
    "tazza":          "Tazza",
    "beaker":         "Becher",
    "jar":            "Topf",
    "cooking pot":    "Kochtopf",
    "jug":            "Krug",
    "flagon":         "Krug",
    "flask":          "Flasche",
    "storage vessel": "Vorratsgefäß",
    "mortarium":      "Reibschüssel",
    "amphora":        "Amphore",
    "lamp":           "Öllampe",
    "lid":            "Deckel",
    "inkwell":        "Tintenfass",
    "goblet":         "Kelch",
    "vase":           "Vase",
    "situla":         "Situla",
    "urn":            "Urne",
    "tazza":          "Tazza",
}

FR_VESSEL: dict[str, str] = {
    "bowl":           "bol",
    "plate":          "assiette",
    "dish":           "plat",
    "platter":        "plat",
    "cup":            "gobelet",
    "tazza":          "tasse",
    "beaker":         "gobelet",
    "jar":            "pot",
    "cooking pot":    "pot culinaire",
    "jug":            "cruche",
    "flagon":         "flacon",
    "flask":          "flacon",
    "storage vessel": "récipient de stockage",
    "mortarium":      "mortier",
    "amphora":        "amphore",
    "lamp":           "lampe",
    "lid":            "couvercle",
    "inkwell":        "encrier",
    "goblet":         "calice",
    "vase":           "vase",
    "situla":         "situle",
    "urn":            "urne",
}

# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def extract_system(code: str) -> str:
    """Return the typological system name from a typology code."""
    # Multi-word systems must be checked longest first
    for sys in sorted(SYSTEM_META, key=len, reverse=True):
        if code.startswith(sys):
            return sys
    # Fallback: first word
    return code.split()[0] if " " in code else code


def get_code_number(code: str, system: str) -> str:
    """Return the number/suffix part of a typology code (e.g. '37' from 'Dragendorff 37')."""
    if code.startswith(system):
        return code[len(system):].strip()
    return ""


def get_abbreviations(code: str) -> str:
    """Generate pipe-separated abbreviation patterns for a typology code."""
    system = extract_system(code)
    meta   = SYSTEM_META.get(system)
    if not meta:
        return ""
    number = get_code_number(code, system)
    abbrevs: list[str] = []
    for prefix in meta["abbrevs"]:
        if number:
            abbrevs.append(f"{prefix} {number}")  # "Drag. 37"
            abbrevs.append(f"{prefix}{number}")    # "Drag.37"
        else:
            abbrevs.append(prefix)
    return "|".join(abbrevs)


def get_ware_type(pot_name_en: str) -> str:
    name = pot_name_en.strip()
    for prefix, ware in WARE_RULES:
        if name.lower().startswith(prefix.lower()):
            return ware
    return ""


def get_vessel_form(pot_name_en: str) -> str:
    name = pot_name_en.strip().lower()
    for suffix, form in VESSEL_RULES:
        if suffix in name:
            return form
    return ""


def translate_name(ware_type: str, vessel_form: str, lang: str) -> str:
    """Build a translated name from ware type and vessel form."""
    ware_map   = DE_WARE   if lang == "de" else FR_WARE
    vessel_map = DE_VESSEL if lang == "de" else FR_VESSEL
    ware_t   = ware_map.get(ware_type, "")
    vessel_t = vessel_map.get(vessel_form, "")
    if ware_t and vessel_t:
        return f"{ware_t} {vessel_t}"
    return ware_t or vessel_t or ""


def classify_slash(typology: str) -> int:
    """Return slash case: 0=none/name-slash, 1=same-system, 2=cross-system, 3=compound-author."""
    if "/" not in typology:
        return 0
    parts = typology.split("/")
    # Case 3: bare author word as first segment (e.g. "Gose" in "Gose/Hofheim 1")
    if re.match(r"^[A-Z][A-Za-z&]+$", parts[0]):
        return 3
    def is_standalone(s):
        s = s.strip()
        return bool(re.match(r"^[A-Z]", s)) and " " in s
    # Case 2: all segments are full typology codes
    if all(is_standalone(p) for p in parts):
        return 2
    # Case 1: same-system compound like "Dragendorff 18/31"
    return 1


def split_for_synonyms(typology: str) -> list[str]:
    """Return individual components for Cases 2 and 3 only; Case 1 returns empty list."""
    case = classify_slash(typology)
    if case == 2:
        return [p.strip() for p in typology.split("/")]
    if case == 3:
        parts = typology.split("/")
        last      = parts[-1].strip()
        suffix_m  = re.search(r"\s+(\S.*)$", last)
        author_m  = re.match(r"^(\S+)", last)
        if suffix_m and author_m:
            suffix  = suffix_m.group(1)
            authors = [p.strip() for p in parts[:-1]] + [author_m.group(1)]
            return [f"{a} {suffix}" for a in authors]
    return []


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Build pottery_vocab_master.csv from the EN + NL source vocabularies: enrich each typology
    code with abbreviations, DE/FR names, ware type, vessel form, region, and date provenance, and
    resolve cross-system synonym relationships into the canonical master dataset."""
    with open(EN_FILE, newline="", encoding="utf-8-sig") as f:
        en_rows = list(csv.DictReader(f))
    with open(NL_FILE, newline="", encoding="utf-8-sig") as f:
        nl_rows = list(csv.DictReader(f))

    assert len(en_rows) == len(nl_rows)

    # ── Step 1: collect synonym groups from combined forms ────────────────────
    # synonym_of[code] = set of codes that are synonymous with it
    synonym_sets: list[set[str]] = []

    def find_group(code: str) -> int | None:
        for i, s in enumerate(synonym_sets):
            if code in s:
                return i
        return None

    for en in en_rows:
        components = split_for_synonyms(en["Typology"])
        if len(components) < 2:
            continue
        # Merge all components into one group
        existing = [find_group(c) for c in components]
        existing_ids = [e for e in existing if e is not None]
        if not existing_ids:
            synonym_sets.append(set(components))
        else:
            # Merge all found groups and any new codes
            base_idx = existing_ids[0]
            for idx in existing_ids[1:]:
                if idx != base_idx:
                    synonym_sets[base_idx].update(synonym_sets[idx])
                    synonym_sets[idx] = set()
            synonym_sets[base_idx].update(components)

    synonym_sets = [s for s in synonym_sets if s]  # remove empty

    def get_synonyms_for(code: str) -> str:
        idx = find_group(code)
        if idx is None:
            return ""
        others = sorted(synonym_sets[idx] - {code})
        return "|".join(others)

    # ── Step 2: collect rows — one per unique individual typology code ────────
    # Rows with "/" that are Cases 2/3 are skipped (synonyms extracted above).
    # Cases 0 and 1 ("Dragendorff 18/31", "Brabant/Hien" etc.) become rows.
    # Group-level codes (Rigoir, Höpken) appear multiple times → merge dates.

    code_data: dict[str, dict] = {}  # code → accumulated row data

    for en, nl in zip(en_rows, nl_rows):
        case = classify_slash(en["Typology"])
        if case in (2, 3):
            continue  # synonym-only row; skip

        code = en["Typology"].strip()
        start, end = int(en["Start_date"]), int(en["End_date"])

        if code not in code_data:
            code_data[code] = {
                "pot_name_en": en["Pot_Name"],
                "pot_name_nl": nl["Pot_Name"],
                "date_start":  start,
                "date_end":    end,
            }
        else:
            # Merge date ranges for group-level codes (Rigoir, Höpken, etc.)
            if start < code_data[code]["date_start"]:
                code_data[code]["date_start"] = start
            if end > code_data[code]["date_end"]:
                code_data[code]["date_end"] = end

    # Also add any code that only appears in combined forms (e.g. "Stuart 211")
    for group in synonym_sets:
        for code in group:
            if code not in code_data:
                # Find date from a combined row that contains this code
                for en in en_rows:
                    components = split_for_synonyms(en["Typology"])
                    if code in components:
                        code_data[code] = {
                            "pot_name_en": en["Pot_Name"],
                            "pot_name_nl": "",
                            "date_start":  int(en["Start_date"]),
                            "date_end":    int(en["End_date"]),
                        }
                        break

    # ── Step 3: build output rows ─────────────────────────────────────────────
    output_rows: list[dict] = []

    for idx, (code, data) in enumerate(sorted(code_data.items()), start=1):
        system     = extract_system(code)
        meta       = SYSTEM_META.get(system, {})
        pot_en     = data["pot_name_en"]
        pot_nl     = data["pot_name_nl"]
        ware_type  = get_ware_type(pot_en)
        vessel     = get_vessel_form(pot_en)
        pot_de     = translate_name(ware_type, vessel, "de")
        pot_fr     = translate_name(ware_type, vessel, "fr")

        output_rows.append({
            "id":                idx,
            "typology_code":     code,
            "synonyms":          get_synonyms_for(code),
            "abbreviations":     get_abbreviations(code),
            "pot_name_en":       pot_en,
            "pot_name_nl":       pot_nl,
            "pot_name_de":       pot_de,
            "pot_name_fr":       pot_fr,
            "ware_type":         ware_type,
            "vessel_form":       vessel,
            "production_region": meta.get("region", ""),
            "date_start":        data["date_start"],
            "date_end":          data["date_end"],
            "date_confidence":   meta.get("conf", ""),
            "date_source":       meta.get("source", ""),
        })

    with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(output_rows)

    n_with_synonyms = sum(1 for r in output_rows if r["synonyms"])
    n_with_abbrevs  = sum(1 for r in output_rows if r["abbreviations"])
    n_with_de       = sum(1 for r in output_rows if r["pot_name_de"])
    n_with_fr       = sum(1 for r in output_rows if r["pot_name_fr"])
    print(f"Output rows         : {len(output_rows)}")
    print(f"  with synonyms     : {n_with_synonyms}")
    print(f"  with abbreviations: {n_with_abbrevs}")
    print(f"  with DE name      : {n_with_de}")
    print(f"  with FR name      : {n_with_fr}")
    print(f"Written to          : {OUT_FILE}")


if __name__ == "__main__":
    main()

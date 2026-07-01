# South Limburg villas: thesis corpus (input PDFs)

This folder holds the PDFs for the **30-report application corpus** of the thesis — the reports the
workflow was actually used to read and summarize. **27 of the 30 PDFs are included here; 3 are
link-only for copyright reasons** (see [Source reports & licensing](#source-reports--licensing) below).

- **These files:** 27 of the 30 source report PDFs.
- **Results (generated):** `output_files/reports/south_limburg_villas/`, one `<report_id>.csv` pottery summary per report (all 30).
- **Full description:** see [`docs/research/datasets/roman_villas.md`](../../../docs/research/datasets/roman_villas.md).

This corpus has **no gold standards**: it is the real-world application, not the accuracy-measurement
set. It was run in Claude mode only, so **no accuracy scores exist** for these reports. For the
measured-accuracy corpus, see `input_files/reports/workflow_evaluation_sample/`.

## Source reports & licensing

The 30 reports come from mixed sources. **27 of the 30 are openly licensed, public domain, or otherwise
freely reusable** and are included here with attribution; the 3 exceptions are noted. License categories:

- **CC-BY-4.0** — deposited at the [DANS Data Station Archaeology](https://archaeology.datastations.nl/); reusable with attribution.
- **Open access** — [Bulletin KNOB](https://bulletin.knob.nl/) (Koninklijke Nederlandse Oudheidkundige Bond; all issues since 1899); freely redistributable with attribution.
- **Public domain** — pre-1940 *De Maasgouw* and *OMRO* (Oudheidkundige Mededelingen) periodicals and 19th-c. LGOG (Limburgs Geschied- en Oudheidkundig Genootschap) articles; out of copyright.
- **Reuse with attribution** — publication by the RCE (Rijksdienst voor het Cultureel Erfgoed / Cultural Heritage Agency of the Netherlands) under the Dutch *Wet hergebruik van overheidsinformatie* (Government Information Reuse Act).
- **⚠️ In copyright — link only** — reports **12726, 12727, 12732** (*Het Land van Herle*) remain under the
  society's copyright and are therefore **not redistributed here**; only their extracted-data CSV is kept.
  The originals are freely available from the publisher via the source link.

| ID | Publisher / author | Title | Year | License | Source |
|---|---|---|---|---|---|
| 12703 | RCE | Roman Bathing in Coriovallum (NAR 65) | 2020 | Reuse with attribution | [cultureelerfgoed.nl](https://www.cultureelerfgoed.nl/publicaties/publicaties/2020/01/01/roman-bathing-in-coriovallum) |
| 12706 | RAAP | Wonen langs de Romeinse weg in Coriovallum | 2012 | CC-BY-4.0 | [DOI](https://doi.org/10.17026/DANS-XMU-4VWP) |
| 12707 | RAAP | Midden in Coriovallum (Tempsplein) | 2020 | CC-BY-4.0 | [DOI](https://doi.org/10.17026/DANS-XK2-HZ2N) |
| 12712 | ADC ArcheoProjecten | In de voetsporen van Braat | 2024 | CC-BY-4.0 | [DOI](https://doi.org/10.17026/AR/ZWCJCW) |
| 12715 | BAAC | Heerlen. De Nor | 2022 | CC-BY-4.0 | [DOI](https://doi.org/10.17026/AR/NOBM17) |
| 12716 | BILAN | Heerlen, Rector Driessenweg | 2005 | CC-BY-4.0 | [DOI](https://doi.org/10.17026/DANS-ZCK-ACJF) |
| 12717 | BILAN | Heerlen, Pleinenplan | 2009 | CC-BY-4.0 | [DOI](https://doi.org/10.17026/DANS-ZYC-Q7JU) |
| 12723 | Het Land van Herle (editorial) | Rond het oudheidkundig bodemonderzoek te Heerlen | 1952 | Public domain | [landvanherle.nl](https://www.landvanherle.nl/) |
| 12726 ⚠️ | Het Land van Herle | Romeinse vondsten in de Geleenstraat | 1964 | In copyright — link only (PDF not included) | [landvanherle.nl](https://www.landvanherle.nl/) |
| 12727 ⚠️ | Het Land van Herle / J.K. Gielen | Romeinse vondsten aan de Promenade te Heerlen | — | In copyright — link only (PDF not included) | [landvanherle.nl](https://www.landvanherle.nl/) |
| 12732 ⚠️ | Het Land van Herle / J.K. Gielen | Romeinse pottenbakkersoven, Akerstraat | 1971 | In copyright — link only (PDF not included) | [landvanherle.nl](https://www.landvanherle.nl/) |
| 12735 | De Maasgouw (LGOG) † | 19th-c. find report (Pleyte) | ~1895 | Public domain | [delpher.nl](https://www.delpher.nl/) |
| 12736 | De Maasgouw (LGOG) | — | 1919 | Public domain | [delpher.nl](https://www.delpher.nl/) |
| 12737 | De Maasgouw (LGOG) † | Het voormalig Huis de Crassier in de Breedestraat | early 20th c. | Public domain | [delpher.nl](https://www.delpher.nl/) |
| 12743 | De Maasgouw (LGOG) † | — | early 20th c. | Public domain | [delpher.nl](https://www.delpher.nl/) |
| 12747 | KNOB Bulletin | Archeologisch Nieuws | mid-20th c. | Open access | [bulletin.knob.nl](https://bulletin.knob.nl/index.php/knob/issue/archive) |
| 12748 | KNOB Bulletin | Archeologisch Nieuws | 1952 | Open access | [bulletin.knob.nl](https://bulletin.knob.nl/index.php/knob/issue/archive) |
| 12751 | KNOB Bulletin | Archeologisch Nieuws | 1952 | Open access | [bulletin.knob.nl](https://bulletin.knob.nl/index.php/knob/issue/archive) |
| 12752 | KNOB Bulletin | Archeologisch Nieuws | — | Open access | [bulletin.knob.nl](https://bulletin.knob.nl/index.php/knob/issue/archive) |
| 12757 | KNOB Bulletin | Archeologisch Nieuws | ~1957 | Open access | [bulletin.knob.nl](https://bulletin.knob.nl/index.php/knob/issue/archive) |
| 12759 | KNOB Bulletin | Archeologisch Nieuws | — | Open access | [bulletin.knob.nl](https://bulletin.knob.nl/index.php/knob/issue/archive) |
| 12768 | KNOB Bulletin | Archeologisch Nieuws | ~1967 | Open access | [bulletin.knob.nl](https://bulletin.knob.nl/index.php/knob/issue/archive) |
| 12770 | De Maasgouw (LGOG) / P. Peters | Uit Heerlens Verleden — Romeinsche Vondsten | ~1913 | Public domain | [delpher.nl](https://www.delpher.nl/) |
| 12774 | Rijksmuseum van Oudheden | OMRO III | ~1905 | Public domain / open access | [rmo.nl](https://www.rmo.nl/onderzoek/rmo-publicaties/) |
| 12954 | KNOB Bulletin / ROB Opgravings-Nieuws | Opgravings-Nieuws | 1950 | Open access | [bulletin.knob.nl](https://bulletin.knob.nl/index.php/knob/issue/archive) |
| 13070 | RAAP | Bedrijventerrein Trilandis | 2009 | CC-BY-4.0 | [DOI](https://doi.org/10.17026/DANS-ZW6-CQ6B) |
| 13250 | KNOB Bulletin | Archeologisch Nieuws | ~1930 | Open access | [bulletin.knob.nl](https://bulletin.knob.nl/index.php/knob/issue/archive) |
| 13319 | ADC ArcheoProjecten | Het villacomplex Kerkrade-Holzkuil | 2005 | CC-BY-4.0 | [DOI](https://doi.org/10.17026/DANS-ZJU-CWC4) |
| 13441 | J. Habets (LGOG) † | Romeinsche voorwerpen te Gronsveld & ara te Odiliënberg | 19th c. | Public domain | [delpher.nl](https://www.delpher.nl/) |
| 13473 | Rijksmuseum van Oudheden | OMRO | ~1920s | Public domain / open access | [rmo.nl](https://www.rmo.nl/onderzoek/rmo-publicaties/) |

*† Journal attribution inferred from content; exact issue unconfirmed.*

*Acronyms: ROB = Rijksdienst voor het Oudheidkundig Bodemonderzoek; NAR = Nederlandse Archeologische Rapporten.*

> The extracted-data CSVs for 12726, 12727, 12732 remain under `output_files/reports/south_limburg_villas/`.

# API Sources

Reference links for the data provider APIs and emission factors.

## ENTSO-E

Base URL: `https://web-api.tp.entsoe.eu/api`

The Zendesk pages can block direct access (HTTP 403). Fetch articles as JSON instead: `https://transparencyplatform.zendesk.com/api/v2/help_center/en-us/articles/<id>.json`

- [API sitemap](https://transparencyplatform.zendesk.com/hc/en-us/articles/15692855254548-Sitemap-for-Restful-API-Integration): index of all API articles
- [Postman API guide](https://documenter.getpostman.com/view/7009892/2s93JtP3F6): request parameters and sample responses. The page renders with JavaScript, so fetch [the collection as JSON](https://documenter.gw.postman.com/api/collections/7009892/2s93JtP3F6?segregateAuth=true&versionTag=latest)
- [XML examples](https://gitlab.entsoe.eu/transparency/xml-examples)
- [Security token](https://transparencyplatform.zendesk.com/hc/en-us/articles/12845911031188)
- [Area codes](https://transparencyplatform.zendesk.com/hc/en-us/articles/15885757676308)
- [PSR types](https://transparencyplatform.zendesk.com/hc/en-us/articles/15856995130004)
- [Query response and HTTP codes](https://transparencyplatform.zendesk.com/hc/en-us/articles/15727773247124)
- [CurveType A01 vs A03](https://transparencyplatform.zendesk.com/hc/en-us/articles/30262342482961)
- [Query size limits](https://transparencyplatform.zendesk.com/hc/en-us/articles/15854536354964)
- [Rate limits](https://transparencyplatform.zendesk.com/hc/en-us/articles/12783148966036)
- [`entsoe-py` parser](https://github.com/EnergieID/entsoe-py/blob/master/entsoe/series_parsers.py): third-party reference for reading A03 curves

## Electricity Maps

Base URL: `https://api.electricitymaps.com`

- [Portal](https://portal.electricitymaps.com/): sign-up and API tokens

## EnergyCharts

Base URL: `https://api.energy-charts.info`

## SMARD (Bundesnetzagentur)

Base URL: `https://www.smard.de/app/chart_data`

## Emission factors

Both the ENTSO-E and Bundesnetzagentur providers use `elephant/providers/emission_factors.py`.

- Primary source: [UBA Emissionsbilanz 2023](https://www.umweltbundesamt.de/system/files/medien/11850/publikationen/03_2025_cc_emissionsbilanz_erneuerbarer_energien_2023.pdf)
- Marine: [IPCC AR5 WG3 Annex III](https://www.ipcc.ch/site/assets/uploads/2018/02/ipcc_wg3_ar5_annex-iii.pdf), Table A.III.2. This is the latest IPCC per-technology table we found: [AR6 WG3 Chapter 6](https://www.ipcc.ch/report/ar6/wg3/downloads/report/IPCC_AR6_WGIII_Chapter06.pdf) (2022) has no replacement
- Waste mapped to biomass: [Electricity Maps ENTSO-E type mapping](https://github.com/electricitymaps/electricitymaps-contrib/blob/master/electricitymap/contrib/parsers/ENTSOE.py)

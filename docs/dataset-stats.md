# Dataset statistics

<!-- stats:begin -->
## Scale 1

| File type | Files | Size (MB) |
|---|---:|---:|
| CSV | 561 | 0.6 |
| XLSX | 83 | 0.4 |
| ISDOC | 4,207 | 16.3 |
| PDF | 4,912 | 15.6 |
| DOCX | 83 | 3.1 |
| DWG | 248 | 9.9 |
| JPG | 30,876 | 237.4 |
| MP4 | 333 | 8.2 |
| GPC | 4,217 | 1.1 |
| STA | 130 | 0.1 |
| TXT | 4,347 | 0.2 |
| KPC | 2,058 | 0.6 |
| **Total** | **52,055** | **293.5** |

| Year | Files | Size (MB) |
|---|---:|---:|
| 2016 | 2,910 | 14.8 |
| 2017 | 3,783 | 20.7 |
| 2018 | 6,120 | 35.3 |
| 2019 | 4,680 | 26.2 |
| 2020 | 5,738 | 33.1 |
| 2021 | 4,485 | 25.1 |
| 2022 | 5,725 | 33.4 |
| 2023 | 4,702 | 25.9 |
| 2024 | 4,228 | 23.2 |
| 2025 | 5,490 | 31.6 |
| 2026 | 4,194 | 24.2 |

Planted problems:

| Truth file | Problem | Count |
|---|---|---:|
| planted_finance.csv | DUPLICATE | 5 |
| planted_finance.csv | MISSING_VS | 10 |
| planted_finance.csv | NO_PROJECT | 25 |
| planted_finance.csv | OVERRUN | 6 |
| planted_finance.csv | PARSE_ERROR | 2 |
| planted_media.csv | NO_GPS | 3,088 |
| planted_media.csv | WRONG_SITE | 309 |
| planted_media.csv | WRONG_VERSION | 1 |
| planted_payments.csv | BAD_FILE | 1 |
| planted_payments.csv | INSTALMENTS | 93 |
| planted_payments.csv | LATE | 139 |
| planted_payments.csv | NEVER | 46 |
| planted_payments.csv | NO_VS | 10 |
| planted_payments.csv | ORDER_LOST | 10 |
| planted_payments.csv | PARTIAL | 46 |
| planted_payments.csv | WRONG_VS | 15 |
<!-- stats:end -->

<!-- x10:begin -->
## Scaled dataset (x10)

Command (repo root): `FVE_DATASET=x10 python -m generators.scale --scale 10`

- Seed: 312; Python 3.13.18
- Runtime: 25.7 minutes
- Compare your regenerated data with `docs/x10-MANIFEST.sha256`.

| File type | Files | Size (MB) |
|---|---:|---:|
| CSV | 565 | 5.6 |
| XLSX | 808 | 4.2 |
| ISDOC | 41,114 | 158.1 |
| PDF | 47,986 | 151.8 |
| DOCX | 808 | 29.8 |
| DWG | 2,412 | 95.6 |
| JPG | 291,840 | 2,241.9 |
| MP4 | 3,184 | 78.3 |
| GPC | 4,217 | 6.3 |
| STA | 130 | 0.7 |
| TXT | 4,347 | 2.2 |
| KPC | 4,260 | 3.6 |
| **Total** | **401,671** | **2,778.0** |

| Year | Files | Size (MB) |
|---|---:|---:|
| 2016 | 20,635 | 144.2 |
| 2017 | 35,117 | 244.1 |
| 2018 | 40,976 | 282.1 |
| 2019 | 36,180 | 248.3 |
| 2020 | 41,164 | 286.8 |
| 2021 | 43,837 | 303.5 |
| 2022 | 41,474 | 285.1 |
| 2023 | 38,281 | 262.0 |
| 2024 | 33,287 | 229.6 |
| 2025 | 36,957 | 255.2 |
| 2026 | 33,763 | 237.1 |

Planted problems:

| Truth file | Problem | Count |
|---|---|---:|
| planted_finance.csv | DUPLICATE | 50 |
| planted_finance.csv | MISSING_VS | 100 |
| planted_finance.csv | NO_PROJECT | 250 |
| planted_finance.csv | OVERRUN | 60 |
| planted_finance.csv | PARSE_ERROR | 20 |
| planted_media.csv | NO_GPS | 29,184 |
| planted_media.csv | WRONG_SITE | 2,918 |
| planted_media.csv | WRONG_VERSION | 10 |
| planted_payments.csv | BAD_FILE | 1 |
| planted_payments.csv | INSTALMENTS | 905 |
| planted_payments.csv | LATE | 1,357 |
| planted_payments.csv | NEVER | 452 |
| planted_payments.csv | NO_VS | 100 |
| planted_payments.csv | ORDER_LOST | 10 |
| planted_payments.csv | PARTIAL | 452 |
| planted_payments.csv | WRONG_VS | 15 |
<!-- x10:end -->

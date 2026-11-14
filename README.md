# asn-geo-recon

**Passive collection of an ISP's address space by ASN, with optional geo filtering by city or oblast.**

[English](#english) · [Українська](#українська)

> **Not a scanner.** The tool only reads the open [RIPEstat](https://stat.ripe.net/) registry
> and an offline MaxMind GeoLite2 database. It never sends a packet to the studied operator's network.

---

## English

### What it does

```
ASN ──► announced BGP prefixes (RIPEstat)
    ──► optional geo filter by city / oblast (GeoLite2)
    ──► subnets.txt  (+ ips.txt)  + report.txt
```

- Collects every prefix an operator announces under one or more ASNs.
- Finds ASNs by operator name (`--search`), for any country.
- Filters address space by **oblast** (matched by ISO 3166-2 code, so Kyiv city `UA-30`
  and Kyiv oblast `UA-32` are never confused) or by **city**.
- Checks every GeoLite2 record inside a prefix, not just its first address, and labels each part
  `confirmed` / `probable` / `doubtful`.
- Counts and expands **unique** addresses: nested announcements (a `/16` plus `/24`s inside it)
  are merged first.

### Quick start

Python 3.8+ and **nothing else**: no pip, no virtualenv, in any mode.

```bash
python3 src/asn_geo_recon.py --asn AS6849            # asks where to save; Enter = out
python3 src/asn_geo_recon.py --search "kyivstar"
python3 src/asn_geo_recon.py --asn AS6849,AS15895 --expand-ips --out out
python3 src/asn_geo_recon.py --help                  # all options with examples
```

Geo filter needs only the free
[GeoLite2-City.mmdb](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) file
(read by the bundled stdlib reader `src/mmdb.py`):

```bash
python3 src/asn_geo_recon.py --asn AS6849 --oblast "Lviv" --geodb GeoLite2-City.mmdb --out out
```

**Linux, one file:** `python3 scripts/build_pyz.py` packs everything into
`dist/asn-geo-recon.pyz` (~16 KB); copy it anywhere and run `./asn-geo-recon.pyz --asn AS6849`.

**Windows:** `scripts\build_exe.bat` builds a standalone console `dist\asn-geo-recon.exe`
(Python bundled).

### Output

Each run gets its own folder, e.g. `out/AS6849_Ukrtelecom/` or `out/AS6849_Ukrtelecom_oblast-UA-46/`:

| File | Content |
|---|---|
| `subnets.txt` | CIDR blocks (one line by default, `--subnets-per-line` for one per line) |
| `ips.txt` | every address, one per line (only with `--expand-ips`) |
| `report.txt` | collected prefixes, unique address count, geo categories |

`ips.txt` is the **potential** address space, not a list of live hosts.

### Project layout

```
src/asn_geo_recon.py   command-line program
src/recon_core.py      core: RIPEstat, ASN search, geo filter, output
src/mmdb.py            GeoLite2 .mmdb reader, standard library only
scripts/               .pyz / .exe build and run helpers
README.txt             full user guide (English + Ukrainian)
```

City-level geolocation is unreliable (bias towards Kyiv, centroids); `--oblast` is more
reliable than `--city`. See `README.txt` for the details of each confidence level.

---

## Українська

### Що робить

Утиліта для **пасивного** збору адресного простору інтернет-провайдера
за номером автономної системи (ASN) та його прив'язки до міста чи області.

- Збирає всі префікси, які оператор анонсує під одним або кількома ASN.
- Знаходить ASN за назвою оператора (`--search`), для будь-якої країни.
- Фільтрує адресний простір за **областю** (за ISO-кодом, тож м. Київ `UA-30` і Київська
  обл. `UA-32` не плутаються) або за **містом**.
- Перевіряє всі записи GeoLite2 усередині префікса, а не лише першу адресу, і позначає кожну
  частину як `confirmed` / `probable` / `doubtful`.
- Рахує й розгортає **унікальні** адреси: вкладені анонси (`/16` і `/24` всередині нього)
  спершу згортаються.

> **Це не сканер.** Дані беруться лише з відкритого RIPEstat і офлайн-бази GeoLite2;
> жодного пакета в мережу досліджуваного оператора не надсилається.

### Швидкий старт

Python 3.8+ і **більше нічого**: без pip і віртуального середовища, у будь-якому режимі.

```bash
python3 src/asn_geo_recon.py --asn AS6849            # спитає, куди зберегти; Enter = out
python3 src/asn_geo_recon.py --search "kyivstar"
python3 src/asn_geo_recon.py --asn AS6849 --oblast "Львівська" --geodb GeoLite2-City.mmdb --out out
```

Для геофільтра потрібен лише безкоштовний файл GeoLite2-City.mmdb з maxmind.com
(його читає вбудований модуль `src/mmdb.py`).

**Linux, один файл:** `python3 scripts/build_pyz.py` → `dist/asn-geo-recon.pyz` (~16 КБ),
копіюєте куди завгодно й запускаєте `./asn-geo-recon.pyz --asn AS6849`.

**Windows:** `scripts\build_exe.bat` збирає самостійний консольний `dist\asn-geo-recon.exe`.

### Результати

Кожен запуск — окрема тека, напр. `out/AS6849_Ukrtelecom/`: `subnets.txt` (підмережі),
`ips.txt` (усі адреси, з `--expand-ips`), `report.txt` (статистика).
`ips.txt` — це **потенційний** адресний простір, а не перелік активних вузлів.

Повна інструкція англійською та українською — у [`README.txt`](README.txt).

================================================================================
  ASN Geo Recon - passive collection of an ISP's address space by ASN
  Version 1.1
================================================================================

  English version first; the Ukrainian version follows below.
  Спочатку англійська версія; українська - нижче.


PURPOSE
--------------------------------------------------------------------------------
The tool finds the routed subnets (CIDR blocks) an operator announces in the
global BGP routing table under a given autonomous system number (ASN) and,
optionally, filters them by city or oblast using a geolocation database.

IMPORTANT: this is NOT a scanner. Not a single packet is sent to the
operator's infrastructure. All data comes from the OPEN RIPEstat Data API
(RIPE NCC) only.

Pipeline:
  ASN -> announced prefixes (RIPEstat)
      -> (optional) geo filter by city/oblast (GeoLite2)
      -> subnets.txt (+ optional ips.txt) + report.txt

Note: BGPView used to be the second source for cross-validation and ASN
search, but its API is gone (api.bgpview.io no longer resolves). ASN search
now uses RIPEstat as well. Cross-validation can be re-enabled by adding a
new source to PREFIX_SOURCES in recon_core.py.


CONTENTS
--------------------------------------------------------------------------------
  asn-geo-recon/
  ├── README.txt          # user guide (EN + UA)
  ├── requirements.txt    # optional dependencies
  ├── .gitignore
  ├── src/                # program code
  │   ├── asn_geo_recon.py    # the program you run (CLI)
  │   ├── recon_core.py       # core library
  │   ├── mmdb.py             # GeoLite2 .mmdb reader (stdlib only)
  │   └── __main__.py         # entry point of the .pyz build
  ├── scripts/            # build and run helpers
  │   ├── build_pyz.py        # one-file dist/asn-geo-recon.pyz (Linux/any OS)
  │   └── build_exe.bat       # build dist\asn-geo-recon.exe (Windows)
  ├── out/                # results, one folder per run (not in git)
  └── dist/               # built .pyz / .exe (not in git)


REQUIREMENTS
--------------------------------------------------------------------------------
  - Python 3.8 or newer (not needed for the prebuilt .exe).
  - NO packages to install, in any mode: standard library only.
    No pip, no virtualenv. Internet access is enough.
  - CITY/OBLAST mode additionally needs the free MaxMind GeoLite2-City.mmdb
    file (sign up at maxmind.com -> GeoLite2 -> download City .mmdb).
    It is read by the bundled src/mmdb.py reader.


USAGE
--------------------------------------------------------------------------------
  Run as  python3 src/asn_geo_recon.py ...  or  asn-geo-recon.exe ...  (same options).

  Full help with examples:
      python3 src/asn_geo_recon.py --help

  All Ukrtelecom prefixes:
      python3 src/asn_geo_recon.py --asn AS6849 --out out

  Several operators at once:
      python3 src/asn_geo_recon.py --asn AS6849,AS15895 --out out

  Find ASNs by operator name (Ukraine by default, --country for others):
      python3 src/asn_geo_recon.py --search "kyivstar"
      python3 src/asn_geo_recon.py --search "orange" --country PL

  Prefixes + every address (one per line) in ips.txt:
      python3 src/asn_geo_recon.py --asn AS6849 --expand-ips

  Filter by oblast (needs GeoLite2):
      python3 src/asn_geo_recon.py --asn AS6849 --oblast "Lviv" \
                         --geodb ./GeoLite2-City.mmdb --out out

  Limit expansion to the first million addresses:
      python3 src/asn_geo_recon.py --asn AS6849 --expand-ips --max-ips 1000000 --out out

  City and oblast names are accepted in English or Ukrainian ("Lviv" / "Львів").
  For oblast mode "Kyiv" means Kyiv oblast; use "Kyiv city" for the city itself.


LINUX: ONE FILE, NOTHING TO INSTALL
--------------------------------------------------------------------------------
  Any Linux with python3 (preinstalled on Ubuntu, Debian, Fedora, ...):
      python3 src/asn_geo_recon.py --asn AS6849

  Or pack the program into a single file and copy it anywhere:
      python3 scripts/build_pyz.py          # -> dist/asn-geo-recon.pyz (~16 KB)
      ./dist/asn-geo-recon.pyz --asn AS6849
      python3 asn-geo-recon.pyz --help      # if the file lost its executable bit


BUILDING THE EXE (Windows)
--------------------------------------------------------------------------------
  1) run scripts\build_exe.bat (double-click or from cmd, any folder);
  2) wait until it finishes;
  3) result:  dist\asn-geo-recon.exe
  4) the exe runs without Python installed. It is a CONSOLE program: start it
     from cmd or PowerShell, e.g.  asn-geo-recon.exe --help


OUTPUT LOCATION
--------------------------------------------------------------------------------
  Without --out the program asks for the output directory; Enter = "out".
  (A path copied from Explorer with quotes is fine.) Each run gets its own
  folder inside it, named after the target, so results never mix:
      out\AS6849_Ukrtelecom\                 --asn AS6849
      out\AS6849+AS15895\                    --asn AS6849,AS15895
      out\AS6849_Ukrtelecom_oblast-UA-46\    --asn AS6849 --oblast Lviv
      out\AS6849_Ukrtelecom_city-lviv\       --asn AS6849 --city Lviv
  Running the same target again overwrites its folder.
  --no-subdir writes straight into --out instead.


OUTPUT FILES (in the run folder)
--------------------------------------------------------------------------------
  subnets.txt   subnet list. By default ONE LINE, space-separated
                (--subnets-per-line -> one per line).
  ips.txt       every address, ONE PER LINE. Only with --expand-ips.
                Network and broadcast addresses are excluded by default.
                Size estimate: ~15 bytes per address
                (e.g. ~480k unique Ukrtelecom addresses -> ~7 MB).
  report.txt    statistics in three sections: [1] collected from the registry
                (prefix count, address count); [2] geo filter categories;
                [3] what went to the output. Sections 2-3 only in geo mode.


GEOLOCATION ACCURACY (read before using --city/--oblast)
--------------------------------------------------------------------------------
  Mapping IPs to a CITY is unreliable: there is a systematic bias towards
  Kyiv (operators register space at their head office) and "centroids"
  (blocks with an unknown city land on an arbitrary point). --oblast is more
  reliable than --city. Oblasts are matched by subdivision ISO code (UA-46
  etc.), so Kyiv city (UA-30) and Kyiv oblast (UA-32) are not confused.

  Each prefix is checked against every database record inside it, not one
  address: a large block (e.g. /16) may split into parts of different
  categories. So after the geo filter subnets.txt holds collapsed CIDR blocks
  that do not necessarily equal the announced prefixes.

  Three confidence levels:
      confirmed  - match at the target level (city for --city, oblast for --oblast);
      probable   - match only at a coarser level (for --city - the city's oblast;
                   for --oblast - a city of the oblast when the record has no oblast);
      doubtful   - unknown / contradictory (likely a centroid).
  confirmed + probable go to the output by default. Add doubtful with
  --include-doubtful.


ETHICS AND LAW
--------------------------------------------------------------------------------
  The tool works only with open routing and geolocation data and does not
  interact with the studied operator's network. ips.txt is the POTENTIAL
  address space (every possible public address of the blocks), NOT a list of
  live hosts: liveness cannot be determined without scanning and this tool
  deliberately does not determine it.


################################################################################
#                           УКРАЇНСЬКА ВЕРСІЯ                                  #
################################################################################

ПРИЗНАЧЕННЯ
--------------------------------------------------------------------------------
Утиліта визначає маршрутизовані підмережі (CIDR-блоки), які оператор анонсує
в глобальній таблиці маршрутизації BGP під заданим номером автономної системи
(ASN), і за потреби фільтрує їх за містом або областю через базу геолокації.

ВАЖЛИВО: це НЕ сканер. Жодного мережевого пакета в інфраструктуру оператора
не надсилається. Усі дані беруться виключно з ВІДКРИТОГО RIPEstat Data API
(RIPE NCC).

Конвеєр:
  ASN -> анонсовані префікси (RIPEstat)
      -> (опційно) геофільтр за містом/областю (GeoLite2)
      -> subnets.txt (+ опційно ips.txt) + report.txt

Примітка: раніше другим джерелом для крос-перевірки й пошуку був BGPView,
але його API більше не існує (api.bgpview.io не резолвиться). Пошук ASN
тепер теж іде через RIPEstat. Крос-перевірку можна повернути, додавши нове
джерело до PREFIX_SOURCES в recon_core.py.


СКЛАД ПАКЕТА
--------------------------------------------------------------------------------
  src/asn_geo_recon.py    програма, яку запускають (CLI, повний --help)
  src/recon_core.py       ядро (збір, геофільтр, запис результатів)
  src/mmdb.py             читач бази GeoLite2 .mmdb (лише stdlib)
  src/__main__.py         точка входу для збірки .pyz
  scripts/build_pyz.py    один файл dist/asn-geo-recon.pyz (Linux/будь-яка ОС)
  scripts/build_exe.bat   збірка в один dist\asn-geo-recon.exe (Windows)
  out/                    результати, окрема тека на кожен запуск
  dist/                   зібрані .pyz / .exe
  README.txt              цей файл


ВИМОГИ
--------------------------------------------------------------------------------
  - Python 3.8 або новіший (для готового .exe не потрібен).
  - ЖОДНИХ пакетів встановлювати не треба, у будь-якому режимі: лише
    стандартна бібліотека. Без pip і без віртуального середовища.
  - Режим МІСТА/ОБЛАСТІ додатково потребує безкоштовного файлу MaxMind
    GeoLite2-City.mmdb (реєстрація на maxmind.com -> GeoLite2 -> City .mmdb).
    Його читає вбудований модуль src/mmdb.py.


ЗАПУСК
--------------------------------------------------------------------------------
  Запускайте як  python3 src/asn_geo_recon.py ...  або  asn-geo-recon.exe ...
  (опції однакові). Інтерфейс програми - англійською.

  Повна довідка з прикладами:
      python3 src/asn_geo_recon.py --help

  Усі префікси Укртелекому:
      python3 src/asn_geo_recon.py --asn AS6849 --out out

  Кілька операторів одразу:
      python3 src/asn_geo_recon.py --asn AS6849,AS15895 --out out

  Знайти ASN за назвою оператора (типово Україна, інші країни - --country):
      python3 src/asn_geo_recon.py --search "kyivstar"
      python3 src/asn_geo_recon.py --search "orange" --country PL

  Префікси + розгорнути всі адреси (одна на рядок) у ips.txt:
      python3 src/asn_geo_recon.py --asn AS6849 --expand-ips

  Фільтр за областю (потрібна база GeoLite2):
      python3 src/asn_geo_recon.py --asn AS6849 --oblast "Львівська" \
                         --geodb ./GeoLite2-City.mmdb --out out

  Обмежити розгортання першим мільйоном адрес:
      python3 src/asn_geo_recon.py --asn AS6849 --expand-ips --max-ips 1000000 --out out

  Назви міст і областей приймаються українською або англійською
  ("Львів" / "Lviv"). Для м. Київ як області - "Київ" або "Kyiv city";
  "Київська" / "Kyiv" - це Київська область.


LINUX: ОДИН ФАЙЛ, НІЧОГО НЕ ВСТАНОВЛЮВАТИ
--------------------------------------------------------------------------------
  Будь-який Linux з python3 (є з коробки в Ubuntu, Debian, Fedora, ...):
      python3 src/asn_geo_recon.py --asn AS6849

  Або запакувати програму в один файл і скопіювати куди завгодно:
      python3 scripts/build_pyz.py          # -> dist/asn-geo-recon.pyz (~16 КБ)
      ./dist/asn-geo-recon.pyz --asn AS6849
      python3 asn-geo-recon.pyz --help      # якщо файл втратив право на запуск


ЗБІРКА EXE (Windows)
--------------------------------------------------------------------------------
  1) запустіть scripts\build_exe.bat (подвійним кліком або з cmd, з будь-якої теки);
  2) дочекайтеся завершення;
  3) результат:  dist\asn-geo-recon.exe
  4) exe працює без встановленого Python. Це КОНСОЛЬНА програма: запускайте
     її з cmd або PowerShell, напр.  asn-geo-recon.exe --help


КУДИ ЗБЕРІГАЮТЬСЯ РЕЗУЛЬТАТИ
--------------------------------------------------------------------------------
  Без --out програма запитує каталог виводу; Enter = "out".
  (Шлях, скопійований з Провідника в лапках, теж підходить.) Кожен запуск
  отримує в ньому власну підтеку з назвою цілі, тож результати не змішуються:
      out\AS6849_Ukrtelecom\                 --asn AS6849
      out\AS6849+AS15895\                    --asn AS6849,AS15895
      out\AS6849_Ukrtelecom_oblast-UA-46\    --asn AS6849 --oblast Lviv
      out\AS6849_Ukrtelecom_city-lviv\       --asn AS6849 --city Lviv
  Повторний запуск тієї ж цілі перезаписує її теку.
  --no-subdir пише файли прямо в --out.


ВИХІДНІ ФАЙЛИ (у теці запуску)
--------------------------------------------------------------------------------
  subnets.txt   список підмереж. За замовчуванням - в ОДИН РЯДОК через пробіл
                (--subnets-per-line -> по рядку).
  ips.txt       усі адреси, ОДНА НА РЯДОК. Лише з --expand-ips.
                Мережева та broadcast-адреси за замовчуванням виключені.
                Орієнтовний розмір: ~15 байт на адресу
                (напр. ~480 тис. унікальних адрес Укртелекому -> ~7 МБ).
  report.txt    статистика у трьох розділах: [1] зібране з реєстру (кількість
                префіксів і адрес); [2] категорії геофільтра; [3] що пішло
                у вихід. Розділи 2-3 - лише в режимі геофільтра.


ПРО ТОЧНІСТЬ ГЕОЛОКАЦІЇ (прочитайте перед використанням --city/--oblast)
--------------------------------------------------------------------------------
  Прив'язка IP до МІСТА ненадійна: діє систематичне зміщення на Київ
  (оператори реєструють простір на головний офіс) і «центроїди» (блоки з
  невизначеним містом звалюються в умовну точку). Режим --oblast надійніший
  за --city. Область звіряється за ISO-кодом суб'єкта (UA-46 тощо), тож
  м. Київ (UA-30) і Київська область (UA-32) не плутаються.

  Кожен префікс перевіряється не за однією адресою, а по всіх записах бази
  всередині нього: великий блок (напр. /16) може розпастися на частини
  різних категорій. Тому у subnets.txt після геофільтра - згорнуті CIDR-блоки,
  які не обов'язково збігаються з анонсованими префіксами.

  Три рівні довіри:
      confirmed  - збіг на рівні цілі (місто для --city, область для --oblast);
      probable   - збіг лише на грубішому рівні (для --city - область міста;
                   для --oblast - місто області, коли область у записі не вказана);
      doubtful   - не визначено / суперечить (ймовірний центроїд).
  За замовчуванням у вихід ідуть confirmed + probable. Додати сумнівні:
  --include-doubtful.

  Докладний розбір похибок - у супровідному PDF до роботи.


ЕТИКА І ПРАВО
--------------------------------------------------------------------------------
  Утиліта працює лише з відкритими даними маршрутизації та геолокації й не
  взаємодіє з мережею досліджуваного оператора. Файл ips.txt - це ПОТЕНЦІЙНИЙ
  адресний простір (усі можливі публічні адреси блоків), а НЕ перелік активних
  вузлів: активність без сканування не визначається й у цій утиліті не
  визначається свідомо.

# -*- coding: utf-8 -*-
"""
recon_core - shared core of the ISP address-space collection tool.

Passive pipeline (NO network scanning):
    ASN  ->  announced prefixes (RIPEstat)
          -> (optional) geo filter by city/oblast (GeoLite2)
          -> subnets.txt  (+ optional ips.txt) + report.txt

All data comes from OPEN BGP registries. Not a single packet is sent to the
operator's network - this is not a scanner.

Dependencies:
    - ASN mode: Python 3.8+ standard library only;
    - city/oblast mode: geoip2 + a GeoLite2-City.mmdb database.
"""
import json
import ipaddress
import re
import urllib.request
import urllib.parse
import urllib.error
import socket
import os
import time

__version__ = "1.1"

RIPESTAT_BASE = "https://stat.ripe.net/data"
RIPESTAT_PREFIXES = RIPESTAT_BASE + "/announced-prefixes/data.json?resource=AS{asn}"
RIPESTAT_COUNTRY_ASNS = RIPESTAT_BASE + "/country-asns/data.json?resource={cc}&lod=1"
RIPESTAT_AS_NAMES = RIPESTAT_BASE + "/as-names/data.json?resource={asns}"
AS_NAMES_BATCH = 200          # ASNs per as-names request (URL stays ~1.2 KB)

USER_AGENT = "asn-geo-recon/%s (passive BGP/ASN research tool)" % __version__
TIMEOUT = 30

# Prefix sources, queried in this order. Each entry is (label, function name).
# The function is looked up at call time, so tests can monkeypatch it.
# To add a source for cross-validation, write a fetch_*(asn, cb) function and
# register it here; collect_prefixes() then reports the differences.
PREFIX_SOURCES = (
    ("RIPEstat", "fetch_ripestat"),
)

# --- Major Ukrainian operators (EDIT AS NEEDED) ------------------------------
# Used only in --city/--oblast mode when no --asn is given: these ASNs are
# run through the geo filter. Use search_asn() to find others.
UA_ISP_ASNS = {
    6849:  "Ukrtelecom",
    15895: "Kyivstar",
    25229: "Volia / Kyivstar TV",
    13188: "Content Delivery Network (Triolan)",
    35297: "Datagroup",
    21011: "Lanet Network",
    43554: "Freenet",
    196739: "Fregat",
}

# --- Name aliases for geo matching ------------------------------------------
# Keys are what the user may type (Ukrainian or English, lowercase); values are
# the variants GeoLite2 uses (mostly English).
CITY_ALIASES = {
    "київ": ["kyiv", "kiev"],
    "львів": ["lviv", "lvov"],
    "харків": ["kharkiv", "kharkov"],
    "одеса": ["odesa", "odessa"],
    "дніпро": ["dnipro", "dnipropetrovsk"],
    "запоріжжя": ["zaporizhzhia", "zaporozhye"],
    "вінниця": ["vinnytsia", "vinnitsa"],
    "полтава": ["poltava"],
    "чернігів": ["chernihiv", "chernigov"],
    "черкаси": ["cherkasy"],
    "житомир": ["zhytomyr"],
    "суми": ["sumy"],
    "рівне": ["rivne", "rovno"],
    "луцьк": ["lutsk"],
    "тернопіль": ["ternopil"],
    "хмельницький": ["khmelnytskyi", "khmelnitskiy"],
    "чернівці": ["chernivtsi"],
    "ужгород": ["uzhhorod", "uzhgorod"],
    "івано-франківськ": ["ivano-frankivsk"],
    "миколаїв": ["mykolaiv", "nikolaev"],
    "херсон": ["kherson"],
    "кропивницький": ["kropyvnytskyi", "kirovohrad"],
}
OBLAST_ALIASES = {
    "київська": ["kyiv", "kiev"],
    "львівська": ["lviv"],
    "харківська": ["kharkiv"],
    "одеська": ["odesa", "odessa"],
    "дніпропетровська": ["dnipropetrovsk", "dnipro"],
    "запорізька": ["zaporizhzhia"],
    "вінницька": ["vinnytsia"],
    "полтавська": ["poltava"],
    "чернігівська": ["chernihiv"],
    "черкаська": ["cherkasy"],
    "житомирська": ["zhytomyr"],
    "сумська": ["sumy"],
    "рівненська": ["rivne"],
    "волинська": ["volyn"],
    "тернопільська": ["ternopil"],
    "хмельницька": ["khmelnytskyi", "khmelnytska"],
    "чернівецька": ["chernivtsi"],
    "закарпатська": ["zakarpattia", "transcarpathia"],
    "івано-франківська": ["ivano-frankivsk"],
    "миколаївська": ["mykolaiv"],
    "херсонська": ["kherson"],
    "кіровоградська": ["kirovohrad", "kropyvnytskyi"],
}

# --- ISO 3166-2:UA oblast codes ---------------------------------------------
# Primary geo-matching key: GeoLite2 returns the subdivision iso_code, which,
# unlike the name, is unambiguous. In particular it separates Kyiv city
# (UA-30) from Kyiv oblast (UA-32), which both match the name "kyiv".
OBLAST_ISO = {
    "вінницька": "UA-05", "волинська": "UA-07", "луганська": "UA-09",
    "дніпропетровська": "UA-12", "донецька": "UA-14", "житомирська": "UA-18",
    "закарпатська": "UA-21", "запорізька": "UA-23", "івано-франківська": "UA-26",
    "київ": "UA-30", "м. київ": "UA-30", "київська": "UA-32",
    "кіровоградська": "UA-35", "севастополь": "UA-40", "крим": "UA-43",
    "автономна республіка крим": "UA-43", "львівська": "UA-46",
    "миколаївська": "UA-48", "одеська": "UA-51", "полтавська": "UA-53",
    "рівненська": "UA-56", "сумська": "UA-59", "тернопільська": "UA-61",
    "харківська": "UA-63", "херсонська": "UA-65", "хмельницька": "UA-68",
    "черкаська": "UA-71", "чернігівська": "UA-74", "чернівецька": "UA-77",
    # English input
    "vinnytsia": "UA-05", "volyn": "UA-07", "luhansk": "UA-09",
    "dnipropetrovsk": "UA-12", "donetsk": "UA-14", "zhytomyr": "UA-18",
    "zakarpattia": "UA-21", "zaporizhzhia": "UA-23", "ivano-frankivsk": "UA-26",
    "kyiv city": "UA-30", "kyiv": "UA-32", "kirovohrad": "UA-35",
    "sevastopol": "UA-40", "crimea": "UA-43", "lviv": "UA-46",
    "mykolaiv": "UA-48", "odesa": "UA-51", "poltava": "UA-53",
    "rivne": "UA-56", "sumy": "UA-59", "ternopil": "UA-61",
    "kharkiv": "UA-63", "kherson": "UA-65", "khmelnytskyi": "UA-68",
    "cherkasy": "UA-71", "chernihiv": "UA-74", "chernivtsi": "UA-77",
}
# City -> code of the oblast it belongs to (used for the "probable" level).
CITY_OBLAST = {
    "київ": "UA-30", "львів": "UA-46", "харків": "UA-63", "одеса": "UA-51",
    "дніпро": "UA-12", "запоріжжя": "UA-23", "вінниця": "UA-05",
    "полтава": "UA-53", "чернігів": "UA-74", "черкаси": "UA-71",
    "житомир": "UA-18", "суми": "UA-59", "рівне": "UA-56", "луцьк": "UA-07",
    "тернопіль": "UA-61", "хмельницький": "UA-68", "чернівці": "UA-77",
    "ужгород": "UA-21", "івано-франківськ": "UA-26", "миколаїв": "UA-48",
    "херсон": "UA-65", "кропивницький": "UA-35",
}
# Allow English city input too: "lviv" -> "львів" (first alias wins).
_CITY_EN_TO_UA = {}
for _ua, _aliases in CITY_ALIASES.items():
    for _en in _aliases:
        _CITY_EN_TO_UA.setdefault(_en, _ua)


class ReconError(Exception):
    pass


def log(msg, cb=None):
    """Emit a message: to stdout, or to the given callback."""
    if cb:
        cb(msg)
    else:
        print(msg, flush=True)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _get_json(url, retries=3):
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, socket.timeout, ValueError) as e:
            last = e
            if attempt < retries:
                time.sleep(2 * attempt)
    raise ReconError("Failed to fetch %s (%s)" % (url, last))


def _norm_asn(asn):
    """Accepts 6849, '6849', 'AS6849', 'as6849' -> int 6849."""
    s = str(asn).strip().upper()
    if s.startswith("AS"):
        s = s[2:]
    if not s.isdigit():
        raise ReconError("Invalid ASN: %r" % asn)
    return int(s)


# ---------------------------------------------------------------------------
# Stage 1: prefixes by ASN
# ---------------------------------------------------------------------------
def fetch_ripestat(asn, cb=None):
    asn = _norm_asn(asn)
    log("  RIPEstat: requesting prefixes for AS%d..." % asn, cb)
    data = _get_json(RIPESTAT_PREFIXES.format(asn=asn))
    out = []
    for p in data.get("data", {}).get("prefixes", []):
        pref = p.get("prefix")
        if pref:
            out.append(pref)
    log("  RIPEstat: got %d prefixes" % len(out), cb)
    return out


def _parse_asn_set(value):
    """country-asns returns ASN sets as a string like '{AsnSingle(6849), ...}'."""
    if isinstance(value, list):
        return {int(x) for x in value}
    return {int(x) for x in re.findall(r"\d+", str(value or ""))}


def search_asn(name, country="UA", cb=None):
    """
    Find ASNs by operator name using RIPEstat only:
      1) country-asns  -> every ASN registered in the country;
      2) as-names      -> their names, in batches;
      3) case-insensitive match: every word of the query must occur in the name.
    Returns list(dict(asn, name, country, routed)), routed ASNs first.
    """
    cc = (country or "UA").strip().upper()
    words = [w for w in name.lower().split() if w]
    if not words:
        raise ReconError("Empty search query.")
    log("  RIPEstat: listing ASNs registered in %s..." % cc, cb)
    data = _get_json(RIPESTAT_COUNTRY_ASNS.format(cc=urllib.parse.quote(cc)))
    countries = data.get("data", {}).get("countries", [])
    if not countries:
        raise ReconError("RIPEstat returned no ASN list for country %r." % cc)
    routed = _parse_asn_set(countries[0].get("routed"))
    all_asns = sorted(routed | _parse_asn_set(countries[0].get("non_routed")))
    log("  RIPEstat: %d ASNs, fetching names..." % len(all_asns), cb)

    res = []
    for i in range(0, len(all_asns), AS_NAMES_BATCH):
        batch = all_asns[i:i + AS_NAMES_BATCH]
        d = _get_json(RIPESTAT_AS_NAMES.format(asns=",".join(map(str, batch))))
        for asn_s, as_name in d.get("data", {}).get("names", {}).items():
            low = (as_name or "").lower()
            if all(w in low for w in words):
                asn = int(asn_s)
                res.append({"asn": asn, "name": as_name, "country": cc,
                            "routed": asn in routed})
    res.sort(key=lambda a: (not a["routed"], a["asn"]))
    log("  RIPEstat: %d ASNs matched" % len(res), cb)
    return res


def fetch_as_names(asns, cb=None):
    """{asn: holder name} from RIPEstat as-names; {} if the request fails."""
    names = {}
    asns = sorted({_norm_asn(a) for a in asns})
    try:
        for i in range(0, len(asns), AS_NAMES_BATCH):
            batch = asns[i:i + AS_NAMES_BATCH]
            d = _get_json(RIPESTAT_AS_NAMES.format(asns=",".join(map(str, batch))))
            for k, v in d.get("data", {}).get("names", {}).items():
                names[int(k)] = v or ""
    except ReconError as e:
        log("  [warning] could not fetch AS names: %s" % e, cb)
    return names


def _slug(text):
    """ASCII-only, filesystem-safe fragment of a folder name."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", text or "").strip("-._")
    return s[:40]


def short_as_name(as_name):
    """
    'UKRTELNET JSC "Ukrtelecom"' -> 'Ukrtelecom' (quoted brand wins);
    'TPNET Orange Polska ...'    -> 'TPNET'      (otherwise the AS handle).
    """
    m = re.search(r'"([^"]+)"', as_name or "")
    if m:
        return _slug(m.group(1))
    handle = (as_name or "").split(" ", 1)[0]
    return _slug(re.sub(r"-AS$", "", handle, flags=re.I))


def target_dirname(asns, names=None, city=None, oblast=None):
    """
    Folder name for one run, e.g.
        AS6849_Ukrtelecom
        AS6849_Ukrtelecom_oblast-UA-46
        AS6849+AS15895_city-lviv
    """
    names = names or {}
    asns = [_norm_asn(a) for a in asns]
    if len(asns) == 1:
        short = short_as_name(names.get(asns[0], ""))
        base = "AS%d" % asns[0] + ("_" + short if short else "")
    elif len(asns) <= 4:
        base = "+".join("AS%d" % a for a in asns)
    else:
        base = "AS%d_and_%d_more" % (asns[0], len(asns) - 1)
    if oblast:
        o = _norm_oblast(oblast)
        base += "_oblast-" + (OBLAST_ISO.get(o) or _slug(o) or "custom")
    if city:
        c = _norm_city(city)
        base += "_city-" + ((CITY_ALIASES.get(c) or [None])[0] or _slug(c) or "custom")
    return base


def _norm_prefix(p):
    """Canonical CIDR form; None if it does not parse."""
    try:
        return str(ipaddress.ip_network(p, strict=False))
    except ValueError:
        return None


def collect_prefixes(asn, cb=None):
    """
    Collect prefixes from every source in PREFIX_SOURCES and merge them.
    Returns (union_sorted, stats). With several sources, stats also lists the
    prefixes seen by one source only (cross-validation).
    """
    per = {}
    for label, fn_name in PREFIX_SOURCES:
        try:
            got = globals()[fn_name](asn, cb)
        except ReconError as e:
            if len(PREFIX_SOURCES) == 1:
                raise
            log("  [warning] %s unavailable: %s" % (label, e), cb)
            continue
        per[label] = {n for n in map(_norm_prefix, got) if n}
    if not per:
        raise ReconError("No prefix source is available.")

    sets = list(per.values())
    union = set().union(*sets)
    stats = {
        "sources": {label: len(s) for label, s in per.items()},
        "common": len(set.intersection(*sets)),
        "only": {},
    }
    if len(per) > 1:
        for label, s in per.items():
            others = set().union(*(o for l2, o in per.items() if l2 != label))
            stats["only"][label] = sorted(s - others)
    return _sort_prefixes(union), stats


def _sort_prefixes(prefixes):
    def key(p):
        net = ipaddress.ip_network(p)
        return (net.version, int(net.network_address), net.prefixlen)
    return sorted(set(prefixes), key=key)


# ---------------------------------------------------------------------------
# Stage 2: geo filter (optional, needs geoip2 + GeoLite2-City.mmdb)
# ---------------------------------------------------------------------------
def _open_geodb(path):
    try:
        import geoip2.database  # noqa
    except ImportError:
        raise ReconError(
            "City/oblast mode needs the geoip2 package "
            "(pip install geoip2) and a GeoLite2-City.mmdb database.")
    if not path or not os.path.isfile(path):
        raise ReconError("GeoLite2-City.mmdb not found at: %r" % path)
    import geoip2.database
    return geoip2.database.Reader(path)


def _norm_oblast(oblast):
    o = oblast.strip().lower()
    for suf in (" область", " обл.", " обл", " oblast", " region"):
        if o.endswith(suf):
            o = o[:-len(suf)]
    return o.strip()


def _norm_city(city):
    c = city.strip().lower()
    return _CITY_EN_TO_UA.get(c, c)


def _norm_region_name(name):
    """GeoLite2 region name without 'oblast/region/province' (keeps 'city')."""
    n = (name or "").strip().lower()
    for suf in (" oblast", " region", " province"):
        if n.endswith(suf):
            n = n[:-len(suf)]
    return n.strip()


def _geo_target(city, oblast):
    """
    Geo filter target:
        cities        - English variants of the city name (exact match);
        region_codes  - expected ISO oblast codes;
        region_names  - fallback oblast names (when a record has no code);
        oblast_cities - English names of cities in the target oblast
                        (used in --oblast mode).
    """
    t = {"cities": set(), "region_codes": set(), "region_names": set(),
         "oblast_cities": set(), "has_city": bool(city)}
    if city:
        c = _norm_city(city)
        t["cities"].update({c, city.strip().lower(), *CITY_ALIASES.get(c, [])})
    if oblast:
        o = _norm_oblast(oblast)
        if o in OBLAST_ISO:
            t["region_codes"].add(OBLAST_ISO[o])
        t["region_names"].update({o, *OBLAST_ALIASES.get(o, [])})
    elif city:
        c = _norm_city(city)
        if c in CITY_OBLAST:
            t["region_codes"].add(CITY_OBLAST[c])
    for c_ua, code in CITY_OBLAST.items():
        if code in t["region_codes"]:
            t["oblast_cities"].update({c_ua, *CITY_ALIASES.get(c_ua, [])})
    if not (t["cities"] or t["region_codes"] or t["region_names"]):
        raise ReconError("Neither city nor oblast given for the geo filter.")
    return t


def _region_code(r):
    """Subdivision ISO code as 'UA-46' (GeoLite2 stores only '46')."""
    code = (r.subdivisions.most_specific.iso_code or "").upper()
    country = (r.country.iso_code or "").upper()
    if code and country and "-" not in code:
        code = "%s-%s" % (country, code)
    return code


def _classify(city_en, region_code, region_name, tgt):
    """Return 'confirmed' / 'probable' / 'doubtful' for one geo record."""
    region_known = bool(region_code or region_name)
    if region_code and tgt["region_codes"]:
        region_ok = region_code in tgt["region_codes"]
    elif region_name and tgt["region_names"]:
        region_ok = _norm_region_name(region_name) in tgt["region_names"]
    else:
        region_ok = False
    region_expected = bool(tgt["region_codes"] or tgt["region_names"])

    if tgt["has_city"]:
        if city_en and city_en in tgt["cities"]:
            # City matches but the oblast contradicts it -> likely a centroid.
            if region_known and region_expected and not region_ok:
                return "doubtful"
            return "confirmed"
        return "probable" if region_ok else "doubtful"

    # Oblast-only mode: the target is the oblast itself.
    if region_ok:
        return "confirmed"
    if not region_known and city_en and city_en in tgt["oblast_cities"]:
        return "probable"
    return "doubtful"


# Step used when the database does not report the bounds of its record.
_GEO_FALLBACK_STEP = {4: 2 ** 8, 6: 2 ** 96}   # /24 for IPv4, /32 for IPv6


def _walk_geo(reader, prefix):
    """
    Walk a prefix record by record: each lookup returns the record's network
    (traits.network), so the next lookup starts right after it. Geo data is
    thus taken for EVERY part of the prefix, not just its first address.
    Yields (start_int, end_int, city, region_code, region_name, country).
    """
    net = ipaddress.ip_network(prefix)
    addr_cls = ipaddress.IPv4Address if net.version == 4 else ipaddress.IPv6Address
    step = _GEO_FALLBACK_STEP[net.version]
    cur, end = int(net.network_address), int(net.broadcast_address)
    while cur <= end:
        city_en = region_code = region_name = country = ""
        rec_net = None
        try:
            r = reader.city(str(addr_cls(cur)))
            rec_net = getattr(r.traits, "network", None)
            city_en = (r.city.name or "").lower()
            region_code = _region_code(r)
            region_name = r.subdivisions.most_specific.name or ""
            country = r.country.iso_code or ""
        except Exception as e:  # AddressNotFoundError carries .network as well
            rec_net = getattr(e, "network", None)
        if rec_net is not None:
            nxt = int(ipaddress.ip_network(rec_net, strict=False).broadcast_address) + 1
        else:
            nxt = (cur // step + 1) * step
        seg_end = min(max(nxt, cur + 1) - 1, end)
        yield cur, seg_end, city_en, region_code, region_name, country
        cur = seg_end + 1


def _ranges_to_cidrs(ranges, version):
    """List of (start, end) -> collapsed list of CIDR strings."""
    cls = ipaddress.IPv4Address if version == 4 else ipaddress.IPv6Address
    nets = []
    for s, e in ranges:
        nets.extend(ipaddress.summarize_address_range(cls(s), cls(e)))
    return [str(n) for n in ipaddress.collapse_addresses(nets)]


def geo_classify(prefixes, geodb_path, city=None, oblast=None, cb=None):
    """
    Classify address space against the target on three levels:
        confirmed - match at the target level (city for --city, oblast for
                    --oblast);
        probable  - match only at a coarser level (the city's oblast; or a
                    city of the target oblast when the record has no oblast);
        doubtful  - no match / unknown / contradictory (possible centroid).
    A prefix may split into parts of different categories, so the lists hold
    collapsed CIDR blocks, not necessarily the original announced prefixes.
    Returns a dict with the three lists + per-prefix geo data.
    """
    tgt = _geo_target(city, oblast)
    reader = _open_geodb(geodb_path)

    res = {"confirmed": [], "probable": [], "doubtful": [], "geo": {}}
    log("  Geo filter: city=%s, oblast=%s" % (
        ", ".join(sorted(tgt["cities"])) or "-",
        ", ".join(sorted(tgt["region_codes"] | tgt["region_names"])) or "-"), cb)
    ranges = {cat: {4: [], 6: []} for cat in ("confirmed", "probable", "doubtful")}
    try:
        for i, pref in enumerate(prefixes, 1):
            version = ipaddress.ip_network(pref).version
            segs = []
            for s, e, city_en, rcode, rname, country in _walk_geo(reader, pref):
                cat = _classify(city_en, rcode, rname, tgt)
                ranges[cat][version].append((s, e))
                segs.append({"start": s, "end": e, "city": city_en,
                             "region": rcode or rname.lower(),
                             "country": country, "category": cat})
            res["geo"][pref] = segs
            if i % 50 == 0:
                log("  Geo filter: processed %d/%d" % (i, len(prefixes)), cb)
    finally:
        reader.close()

    for cat, by_ver in ranges.items():
        res[cat] = _ranges_to_cidrs(by_ver[4], 4) + _ranges_to_cidrs(by_ver[6], 6)
    log("  Geo filter: confirmed=%d, probable=%d, doubtful=%d blocks" % (
        len(res["confirmed"]), len(res["probable"]), len(res["doubtful"])), cb)
    return res


# ---------------------------------------------------------------------------
# Expanding prefixes into addresses
# ---------------------------------------------------------------------------
def _collapse(prefixes, ipv4_only=True):
    """
    Merge overlapping/adjacent prefixes. Operators often announce a covering
    block together with more-specifics inside it (e.g. a /16 plus /24s), so
    without this, addresses are counted and expanded more than once.
    """
    v4, v6 = [], []
    for p in prefixes:
        net = ipaddress.ip_network(p)
        (v4 if net.version == 4 else v6).append(net)
    out = list(ipaddress.collapse_addresses(v4))
    if not ipv4_only:
        out += list(ipaddress.collapse_addresses(v6))
    return out


def count_addresses(prefixes, usable=True, ipv4_only=True):
    """Unique addresses; with usable=True network/broadcast of each merged block are excluded."""
    total = 0
    for net in _collapse(prefixes, ipv4_only):
        if usable and net.num_addresses > 2:
            total += net.num_addresses - 2
        else:
            total += net.num_addresses
    return total


def iter_addresses(prefixes, usable=True, ipv4_only=True, max_ips=None):
    """Unique address generator (as strings). Never holds the whole list in memory."""
    produced = 0
    for net in _collapse(prefixes, ipv4_only):
        hosts = net.hosts() if usable else iter(net)
        for ip in hosts:
            yield str(ip)
            produced += 1
            if max_ips and produced >= max_ips:
                return


# ---------------------------------------------------------------------------
# Writing results
# ---------------------------------------------------------------------------
def write_subnets(path, prefixes, one_line=True):
    with open(path, "w", encoding="utf-8") as f:
        if one_line:
            f.write(" ".join(prefixes))
        else:
            f.write("\n".join(prefixes))
    return len(prefixes)


def write_ips(path, prefixes, usable=True, ipv4_only=True,
              one_per_line=True, max_ips=None, cb=None):
    sep = "\n" if one_per_line else " "
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        first = True
        for ip in iter_addresses(prefixes, usable, ipv4_only, max_ips):
            if not first:
                f.write(sep)
            f.write(ip)
            first = False
            n += 1
            if cb and n % 100000 == 0:
                log("  Written %d addresses..." % n, cb)
    return n


def _prefix_summary(prefixes):
    v4 = sum(1 for p in prefixes if ipaddress.ip_network(p).version == 4)
    return ("%d (IPv4: %d, IPv6: %d; %d IPv4 blocks after merging overlaps), "
            "potential usable IPv4 addresses: %d" % (
                len(prefixes), v4, len(prefixes) - v4,
                len(_collapse(prefixes, ipv4_only=True)),
                count_addresses(prefixes, usable=True, ipv4_only=True)))


def write_report(path, asn_label, prefixes, stats, geo=None,
                 all_prefixes=None, geo_scope=None):
    """
    prefixes     - what went to subnets.txt (after the geo filter, if any);
    all_prefixes - everything collected from the registries (before it).
    Source statistics describe the COLLECTED set, so they get their own
    section and cannot be mistaken for the post-filter totals.
    """
    if all_prefixes is None:
        all_prefixes = prefixes
    lines = ["# asn-geo-recon report", "# Target: %s" % asn_label, "#",
             "# [1] Collected from registries (before geo filter)",
             "# Prefixes: %s" % _prefix_summary(all_prefixes)]
    if stats:
        src = stats.get("sources", {})
        lines.append("# Sources: %s" % ", ".join(
            "%s: %d" % (k, v) for k, v in src.items()))
        if len(src) > 1:
            lines.append("# Seen by all sources: %d" % stats.get("common", 0))
            for label, only in stats.get("only", {}).items():
                if only:
                    lines.append("# Only in %s: %s" % (label, " ".join(only)))
    if geo:
        lines.append("#")
        lines.append("# [2] Geo filter (blocks / potential IPv4 addresses)")
        for cat in ("confirmed", "probable", "doubtful"):
            lines.append("#   %-10s %d / %d" % (cat + ":", len(geo[cat]),
                         count_addresses(geo[cat], usable=False, ipv4_only=True)))
        lines.append("#")
        lines.append("# [3] Output (subnets.txt)%s" % (
            ", categories: %s" % "+".join(geo_scope) if geo_scope else ""))
        lines.append("# Blocks: %s" % _prefix_summary(prefixes))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# High-level pipeline (the CLI is a thin wrapper around it)
# ---------------------------------------------------------------------------
def run_pipeline(asns=None, search=None, search_country="UA",
                 city=None, oblast=None,
                 geodb=None, out_dir="out", subdir=True,
                 expand_ips=False, max_ips=None,
                 usable=True, ipv4_only=True, one_line_subnets=True,
                 geo_scope=("confirmed", "probable"), cb=None):
    """
    Main entry point. Returns a dict with the results and file paths.
    out_dir   - base output directory;
    subdir    - True: write into out_dir/<target_dirname()> (one folder per
                target, e.g. out/AS6849_Ukrtelecom); False: write into out_dir;
    geo_scope - which geo categories go to the output.
    """
    # Resolve target ASNs
    if search and not asns:
        found = search_asn(search, country=search_country, cb=cb)
        if not found:
            raise ReconError("No ASN found for '%s' in %s." % (search, search_country))
        log("Matching ASNs (pick the ones you need with --asn):", cb)
        for a in found:
            log("  AS%-7s %s%s" % (a["asn"], a["name"],
                "" if a["routed"] else "   [not routed]"), cb)
        return {"search_results": found}

    if not asns and (city or oblast):
        # Geo filter without explicit ASNs: use the built-in operator list.
        asns = ["AS%d" % a for a in UA_ISP_ASNS]
        log("No ASN given - using the built-in UA_ISP_ASNS list (%d operators)."
            % len(asns), cb)

    if not asns:
        raise ReconError("No ASN given. Use --asn, or --search/--city/--oblast.")

    asns = [_norm_asn(a) for a in asns]
    if city or oblast:
        # Fail fast: check the geo target and database before any network
        # request or output directory is created.
        _geo_target(city, oblast)
        _open_geodb(geodb).close()

    names = fetch_as_names(asns, cb)
    label = ", ".join(("AS%d %s" % (a, names.get(a, ""))).strip() for a in asns)
    if subdir:
        out_dir = os.path.join(out_dir, target_dirname(asns, names, city, oblast))
    os.makedirs(out_dir, exist_ok=True)
    log("Output directory: %s" % os.path.abspath(out_dir), cb)

    # Collect prefixes
    all_prefixes = []
    merged_stats = {"sources": {}, "common": 0, "only": {}}
    for a in asns:
        log("AS%d: collecting prefixes..." % a, cb)
        prefs, st = collect_prefixes(a, cb=cb)
        all_prefixes.extend(prefs)
        for k, v in st["sources"].items():
            merged_stats["sources"][k] = merged_stats["sources"].get(k, 0) + v
        merged_stats["common"] += st["common"]
        for k, v in st["only"].items():
            merged_stats["only"].setdefault(k, []).extend(v)
    all_prefixes = _sort_prefixes(all_prefixes)
    log("Unique prefixes in total: %d" % len(all_prefixes), cb)

    # Geo filter
    geo = None
    out_prefixes = all_prefixes
    if city or oblast:
        geo = geo_classify(all_prefixes, geodb, city, oblast, cb)
        picked = []
        for scope in geo_scope:
            picked.extend(geo.get(scope, []))
        out_prefixes = _sort_prefixes(picked)
        log("After geo filter (%s): %d blocks" %
            ("+".join(geo_scope), len(out_prefixes)), cb)

    # Write
    sub_path = os.path.join(out_dir, "subnets.txt")
    write_subnets(sub_path, out_prefixes, one_line=one_line_subnets)
    log("Written: %s (%d prefixes)" % (sub_path, len(out_prefixes)), cb)

    rep_path = os.path.join(out_dir, "report.txt")
    write_report(rep_path, label, out_prefixes, merged_stats, geo,
                 all_prefixes=all_prefixes,
                 geo_scope=geo_scope if geo else None)
    log("Written: %s" % rep_path, cb)

    ips_path = None
    if expand_ips:
        est = count_addresses(out_prefixes, usable=usable, ipv4_only=ipv4_only)
        if max_ips:
            est = min(est, max_ips)
        log("Expanding IPs: ~%d addresses expected (~%.1f MB)" %
            (est, est * 15 / 1024 / 1024), cb)
        ips_path = os.path.join(out_dir, "ips.txt")
        n = write_ips(ips_path, out_prefixes, usable=usable, ipv4_only=ipv4_only,
                      one_per_line=True, max_ips=max_ips, cb=cb)
        log("Written: %s (%d addresses)" % (ips_path, n), cb)

    return {
        "label": label,
        "out_dir": out_dir,
        "prefixes": out_prefixes,
        "all_prefixes": all_prefixes,
        "stats": merged_stats,
        "geo": geo,
        "subnets_path": sub_path,
        "report_path": rep_path,
        "ips_path": ips_path,
    }

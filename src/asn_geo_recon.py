#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
asn_geo_recon - command-line front end (Linux / Windows / any OS with Python).

Passive collection of an operator's address space by ASN (or city/oblast)
from open BGP registries. NO network scanning.
"""
import argparse
import os
import sys
import recon_core as core

DEFAULT_OUT = "out"

EPILOG = """\
PURPOSE
  Collects the routed subnets (CIDR blocks) an operator announces in the
  global BGP table and optionally filters them by city or oblast using the
  GeoLite2 geolocation database. No traffic is sent to the operator's
  network - data comes only from the open RIPEstat registry. NOT a scanner.

INPUT MODES (one of):
  --asn AS6849            one or more ASNs (comma-separated)
  --search "ukrtelecom"   find ASNs by operator name (RIPEstat, see --country)
  --city "Lviv"           filter by city      (needs --geodb)
  --oblast "Lviv"         filter by oblast    (needs --geodb)
  If --city/--oblast is used without --asn, the built-in list of major
  Ukrainian operators is used (UA_ISP_ASNS in recon_core.py).
  City/oblast names are accepted in English or Ukrainian ("Lviv" / "Львів").

OUTPUT LOCATION
  If --out is not given, the program asks for the output directory
  (press Enter for "out"; non-interactive runs use "out" silently).
  Each run gets its own folder inside it, named after the target:
    out/AS6849_Ukrtelecom/                 --asn AS6849
    out/AS6849+AS15895/                    --asn AS6849,AS15895
    out/AS6849_Ukrtelecom_oblast-UA-46/    --asn AS6849 --oblast Lviv
  --no-subdir writes straight into --out instead.

OUTPUT FILES (in that folder):
  subnets.txt   subnet list (one line, space-separated, by default)
  ips.txt       expanded address list (only with --expand-ips; one per line)
  report.txt    statistics: collected prefixes, address counts, geo categories

EXAMPLES  (asn-geo-recon = asn-geo-recon.exe or python3 src/asn_geo_recon.py)
  # All Ukrtelecom prefixes -> out/AS6849_Ukrtelecom/subnets.txt
  asn-geo-recon --asn AS6849 --out out

  # Several operators at once
  asn-geo-recon --asn AS6849,AS15895 --out out

  # Find ASNs by name (Ukraine by default)
  asn-geo-recon --search "kyivstar"
  asn-geo-recon --search "orange" --country PL

  # Prefixes + every address (one per line); asks where to save
  asn-geo-recon --asn AS6849 --expand-ips

  # Filter by oblast (needs GeoLite2-City.mmdb)
  asn-geo-recon --asn AS6849 --oblast "Lviv" --geodb ./GeoLite2-City.mmdb --out out

  # Limit expansion to the first million addresses
  asn-geo-recon --asn AS6849 --expand-ips --max-ips 1000000 --out out

GEOLOCATION NOTE
  City-level geolocation is unreliable (bias towards Kyiv, centroids);
  --oblast is more reliable than --city. Oblasts are matched by ISO code
  (Kyiv city UA-30 and Kyiv oblast UA-32 are different targets). Every
  database record inside a prefix is checked, so a prefix may split into
  blocks of different categories:
    confirmed - match at the target level (city for --city, oblast for --oblast);
    probable  - match only at a coarser level;
    doubtful  - unknown or contradictory (likely a centroid).
  'confirmed' and 'probable' go to the output by default; add 'doubtful'
  with --include-doubtful.
"""


def build_parser():
    p = argparse.ArgumentParser(
        prog="asn-geo-recon",
        description="Passive collection of an operator's address space by ASN "
                    "(open BGP registries, no scanning).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG)

    g = p.add_argument_group("Input")
    g.add_argument("--asn", help="ASN, or several comma-separated (AS6849,AS15895)")
    g.add_argument("--search", metavar="NAME",
                   help="find ASNs by operator name and exit")
    g.add_argument("--country", default="UA", metavar="CC",
                   help="country for --search, ISO 3166-1 alpha-2 (default UA)")
    g.add_argument("--city", help="filter by city (needs --geodb)")
    g.add_argument("--oblast", help="filter by oblast (needs --geodb)")

    g2 = p.add_argument_group("Geolocation")
    g2.add_argument("--geodb", metavar="PATH",
                    help="path to the GeoLite2-City.mmdb database")
    g2.add_argument("--include-doubtful", action="store_true",
                    help="also output doubtful blocks (centroids/contradictions)")

    g3 = p.add_argument_group("Output")
    g3.add_argument("--out", default=None, metavar="DIR",
                    help="base output directory; if omitted, you are asked "
                         "(Enter = %s)" % DEFAULT_OUT)
    g3.add_argument("--no-subdir", action="store_true",
                    help="write files directly into --out instead of "
                         "--out/<target> (e.g. out/AS6849_Ukrtelecom)")
    g3.add_argument("--expand-ips", action="store_true",
                    help="write ips.txt with every address (one per line)")
    g3.add_argument("--max-ips", type=int, default=None, metavar="N",
                    help="limit the number of addresses in ips.txt")
    g3.add_argument("--include-network-broadcast", action="store_true",
                    help="keep network/broadcast addresses when expanding")
    g3.add_argument("--subnets-per-line", action="store_true",
                    help="subnets.txt: one subnet per line (default: one line)")
    g3.add_argument("--ipv6", action="store_true",
                    help="include IPv6 when expanding addresses (careful)")

    p.add_argument("--version", action="version",
                   version="asn-geo-recon %s" % core.__version__)
    return p


def _fix_console_encoding():
    """
    On Windows, redirected output (> file, | pipe) uses the ANSI code page
    (e.g. cp1252), which cannot encode Cyrillic city/AS names and would crash.
    Use UTF-8 when redirected, and never fail on an unencodable character.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def ask_out_dir(default=DEFAULT_OUT):
    """
    Ask the user for the base output directory. Enter keeps the default.
    Quotes are stripped, so a path pasted from Explorer ("Copy as path") works.
    Without a terminal (pipe, script) the default is used without asking.
    """
    if not sys.stdin or not sys.stdin.isatty():
        return default
    try:
        ans = input("Output directory [%s]: " % default)
    except EOFError:
        ans = ""
    ans = ans.strip().strip('"').strip("'").strip()
    return os.path.expanduser(ans) if ans else default


def main(argv=None):
    _fix_console_encoding()
    parser = build_parser()
    args = parser.parse_args(argv)

    if not any([args.asn, args.search, args.city, args.oblast]):
        parser.print_help()
        return 2

    # Validate ASNs first, so the user is not asked for a folder in vain.
    try:
        for a in (args.asn or "").split(","):
            if a.strip():
                core._norm_asn(a)
    except core.ReconError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 1

    out_dir = args.out
    if out_dir is None:
        # --search only prints results, so there is nothing to save.
        out_dir = DEFAULT_OUT if (args.search and not args.asn) else ask_out_dir()

    asns = None
    if args.asn:
        asns = [x.strip() for x in args.asn.split(",") if x.strip()]

    scope = ("confirmed", "probable")
    if args.include_doubtful:
        scope = ("confirmed", "probable", "doubtful")

    try:
        core.run_pipeline(
            asns=asns,
            search=args.search,
            search_country=args.country,
            city=args.city,
            oblast=args.oblast,
            geodb=args.geodb,
            out_dir=out_dir,
            subdir=not args.no_subdir,
            expand_ips=args.expand_ips,
            max_ips=args.max_ips,
            usable=not args.include_network_broadcast,
            ipv4_only=not args.ipv6,
            one_line_subnets=not args.subnets_per_line,
            geo_scope=scope,
            cb=None,  # None -> print to stdout
        )
    except core.ReconError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())

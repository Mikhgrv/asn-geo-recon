#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_pyz - pack src/ into one runnable file: dist/asn-geo-recon.pyz

The result needs nothing but python3 (3.8+), which every mainstream Linux
distribution ships. No pip, no virtualenv, no compilation:

    python3 scripts/build_pyz.py
    ./dist/asn-geo-recon.pyz --asn AS6849          # or: python3 dist/asn-geo-recon.pyz ...

Works the same on Windows (python scripts\\build_pyz.py); the .pyz itself is
platform-independent. Standard library only (zipapp).
"""
import os
import stat
import sys
import zipapp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
DIST = os.path.join(ROOT, "dist")
TARGET = os.path.join(DIST, "asn-geo-recon.pyz")


def _include(path):
    """Only the program's .py files: no __pycache__ or stray files."""
    return path.suffix == ".py" and "__pycache__" not in path.parts


def main():
    if not os.path.isfile(os.path.join(SRC, "__main__.py")):
        print("ERROR: %s/__main__.py not found" % SRC, file=sys.stderr)
        return 1
    os.makedirs(DIST, exist_ok=True)
    zipapp.create_archive(SRC, TARGET, interpreter="/usr/bin/env python3",
                          filter=_include, compressed=True)
    # Executable bit, so it can be started as ./asn-geo-recon.pyz on Linux.
    mode = os.stat(TARGET).st_mode
    os.chmod(TARGET, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print("Done: %s (%d KB)" % (TARGET, os.path.getsize(TARGET) // 1024))
    print("Run:  python3 %s --help" % os.path.relpath(TARGET))
    return 0


if __name__ == "__main__":
    sys.exit(main())

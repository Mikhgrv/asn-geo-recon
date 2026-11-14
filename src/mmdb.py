# -*- coding: utf-8 -*-
"""
mmdb - minimal MaxMind DB (.mmdb) reader using only the Python standard library.

Replaces the third-party geoip2/maxminddb packages, so the geo filter works on
any machine with a plain python3 (no pip, no virtualenv).

Format specification: https://maxmind.github.io/MaxMind-DB/
Only reading is implemented; it is enough for GeoLite2-City / GeoIP2-City.

Usage:
    with Reader("GeoLite2-City.mmdb") as r:
        record, network = r.lookup("178.137.5.1")
        # record  - decoded dict (or None if the address is not in the database)
        # network - ipaddress network the answer applies to (the whole record)
"""
import ipaddress
import mmap
import struct

METADATA_MARKER = b"\xab\xcd\xefMaxMind.com"
DATA_SECTION_SEPARATOR = 16       # 16 zero bytes between search tree and data

# Data section field types (spec, "Output Data Section")
_POINTER, _UTF8, _DOUBLE, _BYTES, _UINT16, _UINT32, _MAP = 1, 2, 3, 4, 5, 6, 7
_INT32, _UINT64, _UINT128, _ARRAY, _CONTAINER, _END, _BOOL, _FLOAT = (
    8, 9, 10, 11, 12, 13, 14, 15)


class InvalidDatabaseError(Exception):
    pass


class Reader:
    def __init__(self, path):
        self._file = open(path, "rb")
        try:
            self._buf = mmap.mmap(self._file.fileno(), 0, access=mmap.ACCESS_READ)
        except ValueError:                       # empty file cannot be mapped
            self._file.close()
            raise InvalidDatabaseError("Empty file: %r" % path)
        try:
            self._init_metadata(path)
        except Exception:
            self.close()
            raise
        self._cache = {}

    # --- metadata / layout ----------------------------------------------------
    def _init_metadata(self, path):
        buf = self._buf
        # The marker is in the last 128 KiB; take its last occurrence.
        start = max(0, len(buf) - 128 * 1024)
        pos = buf.rfind(METADATA_MARKER, start)
        if pos < 0:
            raise InvalidDatabaseError("Not a MaxMind DB file: %r" % path)
        # Pointers inside metadata are relative to the metadata section start.
        meta_start = pos + len(METADATA_MARKER)
        meta, _ = self._decode(meta_start, base=meta_start)
        if not isinstance(meta, dict):
            raise InvalidDatabaseError("Broken metadata in %r" % path)
        self.metadata = meta
        try:
            self.node_count = meta["node_count"]
            self.record_size = meta["record_size"]
            self.ip_version = meta["ip_version"]
        except KeyError as e:
            raise InvalidDatabaseError("Metadata misses %s in %r" % (e, path))
        if self.record_size not in (24, 28, 32):
            raise InvalidDatabaseError("Unsupported record size %r" % self.record_size)
        self._node_bytes = self.record_size * 2 // 8
        self._tree_size = self.node_count * self._node_bytes
        self._data_base = self._tree_size + DATA_SECTION_SEPARATOR
        # Node where IPv4 addresses start in an IPv6 tree (::/96 prefix).
        self._ipv4_start = 0
        self._ipv4_depth = 0
        if self.ip_version == 6:
            node = 0
            for _ in range(96):
                if node >= self.node_count:
                    break
                node = self._read_node(node, 0)
                self._ipv4_depth += 1
            self._ipv4_start = node

    def _read_node(self, node, bit):
        b = self._buf
        off = node * self._node_bytes
        if self.record_size == 24:
            off += bit * 3
            return (b[off] << 16) | (b[off + 1] << 8) | b[off + 2]
        if self.record_size == 28:
            if bit == 0:
                return (((b[off + 3] & 0xF0) << 20) | (b[off] << 16)
                        | (b[off + 1] << 8) | b[off + 2])
            return (((b[off + 3] & 0x0F) << 24) | (b[off + 4] << 16)
                    | (b[off + 5] << 8) | b[off + 6])
        off += bit * 4
        return struct.unpack_from(">I", b, off)[0]

    # --- lookup ---------------------------------------------------------------
    def lookup(self, ip):
        """
        -> (record or None, ipaddress network covering the answer).
        The network is what lets callers skip the rest of the record's block.
        """
        addr = ipaddress.ip_address(ip)
        if addr.version == 6 and self.ip_version == 4:
            raise ValueError("IPv6 address %s in an IPv4-only database" % ip)
        bits = 32 if addr.version == 4 else 128
        value = int(addr)
        node = self._ipv4_start if addr.version == 4 else 0
        depth = 0
        while depth < bits and node < self.node_count:
            bit = (value >> (bits - 1 - depth)) & 1
            node = self._read_node(node, bit)
            depth += 1
        if addr.version == 4 and self.ip_version == 6 and self._ipv4_start >= self.node_count:
            # IPv4 subtree is absent: the answer covers the whole IPv4 space.
            depth = 0
        network = ipaddress.ip_network("%s/%d" % (addr, depth), strict=False)
        if node == self.node_count:              # empty record: not found
            return None, network
        if node < self.node_count:
            raise InvalidDatabaseError("Search tree is deeper than the address")
        offset = node - self.node_count - DATA_SECTION_SEPARATOR
        rec = self._cache.get(offset)
        if rec is None:
            rec, _ = self._decode(self._data_base + offset, base=self._data_base)
            self._cache[offset] = rec
        return rec, network

    # --- data section decoder -----------------------------------------------------
    def _decode(self, pos, base):
        """Decode one value at absolute position pos. -> (value, next_pos)."""
        b = self._buf
        ctrl = b[pos]
        pos += 1
        ftype = ctrl >> 5
        if ftype == _POINTER:
            ss = (ctrl >> 3) & 0x3
            vvv = ctrl & 0x7
            if ss == 0:
                ptr, pos = (vvv << 8) | b[pos], pos + 1
            elif ss == 1:
                ptr, pos = ((vvv << 16) | (b[pos] << 8) | b[pos + 1]) + 2048, pos + 2
            elif ss == 2:
                ptr = ((vvv << 24) | (b[pos] << 16) | (b[pos + 1] << 8) | b[pos + 2]) + 526336
                pos += 3
            else:
                ptr, pos = struct.unpack_from(">I", b, pos)[0], pos + 4
            value, _ = self._decode(base + ptr, base)
            return value, pos
        if ftype == 0:                           # extended type
            ftype = 7 + b[pos]
            pos += 1
        size = ctrl & 0x1F
        if ftype != _BOOL:                       # bool keeps its value in size
            if size == 29:
                size, pos = 29 + b[pos], pos + 1
            elif size == 30:
                size, pos = 285 + ((b[pos] << 8) | b[pos + 1]), pos + 2
            elif size == 31:
                size = 65821 + ((b[pos] << 16) | (b[pos + 1] << 8) | b[pos + 2])
                pos += 3

        if ftype == _MAP:
            out = {}
            for _ in range(size):
                key, pos = self._decode(pos, base)
                out[key], pos = self._decode(pos, base)
            return out, pos
        if ftype == _ARRAY:
            out = []
            for _ in range(size):
                item, pos = self._decode(pos, base)
                out.append(item)
            return out, pos
        if ftype == _UTF8:
            return b[pos:pos + size].decode("utf-8"), pos + size
        if ftype in (_UINT16, _UINT32, _UINT64, _UINT128):
            return int.from_bytes(b[pos:pos + size], "big"), pos + size
        if ftype == _INT32:
            raw = b[pos:pos + size]
            # Shorter-than-4-byte int32 values are always positive (spec).
            return int.from_bytes(raw, "big", signed=(size == 4)), pos + size
        if ftype == _DOUBLE:
            return struct.unpack_from(">d", b, pos)[0], pos + 8
        if ftype == _FLOAT:
            return struct.unpack_from(">f", b, pos)[0], pos + 4
        if ftype == _BOOL:
            return bool(size), pos
        if ftype == _BYTES:
            return bytes(b[pos:pos + size]), pos + size
        if ftype in (_CONTAINER, _END):
            return None, pos
        raise InvalidDatabaseError("Unknown data type %d at %d" % (ftype, pos))

    # --- lifetime ---------------------------------------------------------------
    def close(self):
        buf = getattr(self, "_buf", None)
        if buf is not None:
            buf.close()
            self._buf = None
        if self._file:
            self._file.close()
            self._file = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

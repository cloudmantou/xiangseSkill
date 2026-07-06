#!/usr/bin/env python3
"""One-off XBS decoder matching xbsrebuild/yang3yen-xxtea-go semantics."""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

KEY = bytes(
    [
        0xE5,
        0x87,
        0xBC,
        0xE8,
        0xA4,
        0x86,
        0xE6,
        0xBB,
        0xBF,
        0xE9,
        0x87,
        0x91,
        0xE6,
        0xBA,
        0xA1,
        0xE5,
    ]
)

DELTA = 0x9E3779B9


def _mx(y: int, z: int, p: int, e: int, sum_: int, key: list[int]) -> int:
    return (
        ((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4))
    ) ^ ((sum_ ^ y) + (key[(p & 3) ^ e] ^ z)) & 0xFFFFFFFF


def _bytes_to_uint32s(data: bytes) -> list[int]:
    out = [0] * (len(data) // 4)
    for i, b in enumerate(data):
        out[i >> 2] |= b << ((i & 3) << 3)
    return out


def _uint32s_to_bytes(words: list[int], length: int) -> bytes:
    out = bytearray(length)
    for i in range(length):
        out[i] = (words[i >> 2] >> ((i & 3) << 3)) & 0xFF
    return bytes(out)


def _btea_decrypt(v: list[int], key_words: list[int], rounds: int = 0) -> None:
    n = len(v)
    if rounds == 0:
        rounds = 6 + 52 // n
    sum_ = (rounds * DELTA) & 0xFFFFFFFF
    y = v[0]
    for _ in range(rounds):
        e = (sum_ >> 2) & 3
        for p in range(n - 1, 0, -1):
            z = v[p - 1]
            v[p] = (v[p] - _mx(y, z, p, e, sum_, key_words)) & 0xFFFFFFFF
            y = v[p]
        z = v[n - 1]
        v[0] = (v[0] - _mx(y, z, 0, e, sum_, key_words)) & 0xFFFFFFFF
        y = v[0]
        sum_ = (sum_ - DELTA) & 0xFFFFFFFF


def _mx_encrypt(y: int, z: int, p: int, e: int, sum_: int, key: list[int]) -> int:
    return (
        ((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4))
    ) ^ ((sum_ ^ y) + (key[(p & 3) ^ e] ^ z)) & 0xFFFFFFFF


def _btea_encrypt(v: list[int], key_words: list[int], rounds: int = 0) -> None:
    n = len(v)
    if rounds == 0:
        rounds = 6 + 52 // n
    sum_ = 0
    z = v[n - 1]
    for _ in range(rounds):
        sum_ = (sum_ + DELTA) & 0xFFFFFFFF
        e = (sum_ >> 2) & 3
        for p in range(n - 1):
            y = v[p + 1]
            v[p] = (v[p] + _mx_encrypt(y, z, p, e, sum_, key_words)) & 0xFFFFFFFF
            z = v[p]
        y = v[0]
        v[n - 1] = (v[n - 1] + _mx_encrypt(y, z, n - 1, e, sum_, key_words)) & 0xFFFFFFFF
        z = v[n - 1]


def json2xbs_bytes(buf: bytes) -> bytes:
    buffer_len = len(buf)
    pad = (-buffer_len) % 4
    padded = buf + (b"\x00" * pad) + struct.pack("<I", buffer_len)
    words = _bytes_to_uint32s(padded)
    key_words = _bytes_to_uint32s(KEY)
    _btea_encrypt(words, key_words, 0)
    return _uint32s_to_bytes(words, len(padded))


def xbs2json_bytes(buf: bytes) -> bytes:
    if len(buf) < 8 or len(buf) % 4 != 0:
        raise ValueError("invalid xbs length")
    words = _bytes_to_uint32s(buf)
    key_words = _bytes_to_uint32s(KEY)
    _btea_decrypt(words, key_words, 0)
    out = _uint32s_to_bytes(words, len(buf))
    buf_len = len(buf)
    payload_len = buf_len - 4
    m = struct.unpack_from("<I", out, payload_len)[0]
    if m < payload_len - 3 or m > payload_len:
        raise ValueError(f"decode error: m={m}, payload_len={payload_len}")
    return out[:m]


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: decode_xbs.py <input.xbs> [output.json]")
        print("       decode_xbs.py --encode <input.json> <output.xbs>")
        raise SystemExit(2)

    if sys.argv[1] == "--encode":
        src = Path(sys.argv[2])
        dst = Path(sys.argv[3])
        encoded = json2xbs_bytes(src.read_bytes())
        dst.write_bytes(encoded)
        roundtrip = xbs2json_bytes(encoded)
        if roundtrip != src.read_bytes():
            raise SystemExit("roundtrip mismatch after encode")
        print(f"OK_XBS: {dst} ({len(encoded)} bytes)")
        return

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    decoded = xbs2json_bytes(src.read_bytes())
    if dst:
        dst.write_bytes(decoded)
    try:
        obj = json.loads(decoded)
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    except json.JSONDecodeError:
        print(decoded.decode("utf-8", "replace"))


if __name__ == "__main__":
    main()
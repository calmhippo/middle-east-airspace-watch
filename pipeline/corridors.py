#!/usr/bin/env python3
"""Which corridor Gulf <-> Europe flights use, per day, from the line shards (data/lines/<date>.s*.bin).

A leg counts when one end is in the Gulf (GULF box: Kuwait, Bahrain, Qatar, UAE, eastern Saudi Arabia)
and the other in Europe (EUROPE box, Turkey west of 30E included). Its corridor is where the path first
crosses latitude CROSS_LAT (34N, roughly the Syria/Iraq/Iran line north of Jordan and Kuwait):
  west  lon < 40.1   via Saudi Arabia / Jordan / Syria, or Egypt and the Mediterranean
  iraq  40.1 - 45.4  over Iraq
  iran  lon >= 45.4  over Iran
(40.1 and 45.4 are the Syria-Iraq and Iraq-Iran borders on 34N in data/basemap.json; the viewer draws this
line with the same split, CORR_SPLITS in site/index.html, so change both together.)
Unheard stretches (straight joins between reports) are used too, so where no receiver covers the
crossing (most of Iraq and Iran) its position is estimated. Legs that never cross 34N are left out.

  python pipeline/corridors.py data/lines 2026-11-14     prints [west, iraq, iran]
"""
import os
import struct
import sys

CROSS_LAT = 34.0
SPLITS = (40.1, 45.4)            # west | iraq | iran (borders on 34N; was 40.5 / 46 until Nov 16)
GULF = (22.0, 30.5, 46.0, 57.5)  # lat_min, lat_max, lon_min, lon_max
EUROPE = (36.0, 72.0, -15.0, 30.0)
NAMES = ("west", "iraq", "iran")


def _inside(box, lat, lon):
    return box[0] <= lat <= box[1] and box[2] <= lon <= box[3]


def _corridor(pts, gap):
    """pts: list of (lat, lon) in degrees; gap[i] flags the segment ending at point i (2 = not drawn)."""
    a, z = pts[0], pts[-1]
    if not ((_inside(GULF, *a) and _inside(EUROPE, *z)) or (_inside(GULF, *z) and _inside(EUROPE, *a))):
        return None
    for i in range(1, len(pts)):
        if gap[i] > 1:
            continue
        (la0, lo0), (la1, lo1) = pts[i - 1], pts[i]
        if la0 != la1 and (la0 - CROSS_LAT) * (la1 - CROSS_LAT) <= 0:
            lon = lo0 + (lo1 - lo0) * (CROSS_LAT - la0) / (la1 - la0)
            return 0 if lon < SPLITS[0] else 1 if lon < SPLITS[1] else 2
    return None


def shard_counts(buf, counts):
    """Add one shard's Gulf<->Europe legs to counts [west, iraq, iran]. Layout: see process_day.py."""
    _, nl, npts, _ = struct.unpack_from("<4I", buf, 0)
    al = lambda n: (n + 3) & ~3  # noqa: E731
    o = 16
    lens = struct.unpack_from(f"<{nl}H", buf, o); o += al(2 * nl)
    o += al(2 * nl)                                   # orig/dest airport indices (unused here)
    p_off = o; o += al(4 * npts)
    g_off = o
    start = 0
    for n in lens:
        if n >= 2:
            # cheap endpoint test first: only Gulf<->Europe legs need their whole path
            la0, lo0 = struct.unpack_from("<2h", buf, p_off + 4 * start)
            la1, lo1 = struct.unpack_from("<2h", buf, p_off + 4 * (start + n - 1))
            ends = ((la0 / 100, lo0 / 100), (la1 / 100, lo1 / 100))
            if any(_inside(GULF, *e) for e in ends) and any(_inside(EUROPE, *e) for e in ends):
                raw = struct.unpack_from(f"<{2 * n}h", buf, p_off + 4 * start)
                pts = [(raw[2 * i] / 100, raw[2 * i + 1] / 100) for i in range(n)]
                c = _corridor(pts, buf[g_off + start:g_off + start + n])
                if c is not None:
                    counts[c] += 1
        start += n
    return counts


def day_counts(lines_dir, date, shards=8):
    """[west, iraq, iran] for one day, or None if the day has no line files."""
    counts, found = [0, 0, 0], False
    for k in range(shards):
        path = os.path.join(lines_dir, f"{date}.s{k}.bin")
        if os.path.exists(path):
            with open(path, "rb") as fh:
                buf = fh.read()
            if len(buf) >= 16:
                shard_counts(buf, counts)
                found = True
    return counts if found else None


if __name__ == "__main__":
    print(day_counts(sys.argv[1], sys.argv[2]))

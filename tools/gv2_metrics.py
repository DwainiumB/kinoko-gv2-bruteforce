#!/usr/bin/env python3
"""Post-hit metrics for GV2 block hits from CPU replay dumps.

ahead(t) = along-track displacement of the candidate at row t from the reference at row t + shift, divided by the
reference's speed there, in frames (positive = further along the reference path)."""
import csv, math, sys

def load(p):
    return list(csv.DictReader(open(p)))

def P(r):
    return float(r['px']), float(r['pz'])

def yaw(r):
    qx, qy, qz, qw = (float(r[k]) for k in ('qx', 'qy', 'qz', 'qw'))
    return math.degrees(math.atan2(2 * (qx * qz + qw * qy), 1 - 2 * (qx * qx + qy * qy)))

def ev(r):
    return math.hypot(float(r['evx']), float(r['evz']))

def ahead(cand, ci, ref, ri):
    (x, z), (x0, z0), (x1, z1) = P(cand[ci]), P(ref[ri]), P(ref[ri + 1])
    dx, dz = x1 - x0, z1 - z0
    sp = math.hypot(dx, dz)
    along = ((x - x0) * dx + (z - z0) * dz) / sp
    lat = ((x - x0) * dz - (z - z0) * dx) / sp
    return along / sp, lat

def contact(rows, lo, hi):
    for i in range(lo, hi):
        if int(rows[i]['flags']) & 0x400:
            return i
    return None

if __name__ == '__main__':
    A = load(sys.argv[1])
    for spec in sys.argv[2:]:
        path, shift = spec.split('@') if '@' in spec else (spec, '0')
        shift = int(shift)
        B = load(path) if path != 'self' else A
        for lo, hi in ((780, 900), (1340, 1460), (1890, 2010)):
            c = contact(B, lo + 0 if shift == 0 else lo, hi)
            if c is None or not (lo <= c - shift + (0) < hi + 600):
                continue
            out = [f"{path}@{shift} contact row {c}"]
            for k in (0, 10, 20, 30, 40):
                a, lat = ahead(B, c + k, A, c + k - shift) if c + k - shift + 1 < len(A) else (float('nan'), 0)
                out.append(f"+{k}: ahead {a:+.3f}f lat {lat:+6.1f} yaw {yaw(B[c + k]):8.2f} ev {ev(B[c + k]):5.1f} sp {float(B[c + k]['speed']):5.1f}")
            print('\n   '.join(out))
            break

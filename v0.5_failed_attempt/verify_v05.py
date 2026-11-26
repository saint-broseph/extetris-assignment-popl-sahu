#!/usr/bin/env python3
"""
verify_v05.py -- proof that the v0.5 constructor key (bounding box, diagonal
connections) is ambiguous, and what refinement is needed.

    python v0.5_failed_attempt/verify_v05.py

Self-contained: it imports only piece_v05.py from this folder (no v1 code).
Exit code 0 means the proof went through, i.e. the flaw was demonstrated.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import piece_v05 as v05  # noqa: E402

# ----------------------------------------------------------------------------
# Small helpers (rotation classes, mirror, and the two refinement probes)
# ----------------------------------------------------------------------------
def rotations(cells):
    out = [cells]
    for _ in range(3):
        out.append(v05.rotate_cw(out[-1]))
    return out


def piece_id(cells):
    """Same value for all rotations of one piece."""
    return min(tuple(sorted(o)) for o in rotations(cells))


def mirror(cells):
    return v05.normalize({(r, -c) for r, c in cells})


def landing_holes(cells):
    h, w = v05.size(cells)
    total = 0
    for col in range(w):
        top = min(r for r, c in cells if c == col)
        total += sum(1 for r in range(top + 1, h) if (r, col) not in cells)
    return total


def hole_signature(cells):
    """Probe 1: landing holes in the 4 clockwise orientations (cyclic, starts at its minimum)."""
    seq = [landing_holes(o) for o in rotations(cells)]
    return min(tuple(seq[i:] + seq[:i]) for i in range(4))


def handedness(cells):
    """Probe 2: sign of Im(sum z^4) about the centroid (+1 / -1 for mirror twins, 0 if symmetric)."""
    n = len(cells)
    sx = sum(c for _, c in cells)
    sy = sum(-r for r, _ in cells)
    im = sum(4 * (n * c - sx) ** 3 * (n * -r - sy) - 4 * (n * c - sx) * (n * -r - sy) ** 3 for r, c in cells)
    return (im > 0) - (im < 0)


def code(cells):
    bbox = sorted(v05.size(cells))
    return f"X{bbox[0]}x{bbox[1]}.H{''.join(map(str, hole_signature(cells)))}.{'+-0'[[1, -1, 0].index(handedness(cells))]}"


def side_by_side(shapes, labels, gap=4):
    pics = [str(v05.Piece(s)).split("\n") for s in shapes]
    widths = [max(len(lbl), len(p[0])) for p, lbl in zip(pics, labels)]
    lines = ["".ljust(0) + (" " * gap).join(lbl.ljust(w) for lbl, w in zip(labels, widths))]
    for row in range(max(len(p) for p in pics)):
        lines.append((" " * gap).join((p[row] if row < len(p) else "").ljust(w) for p, w in zip(pics, widths)))
    return "\n".join("      " + ln.rstrip() for ln in lines)


# ----------------------------------------------------------------------------
def main() -> int:
    print("=" * 78)
    print("v0.5 constructor: ExTetromino<bbox>(diagonals)  -- collision proof")
    print("=" * 78)

    groups = {}                    # (subclass, diagonals) -> {piece_id: representative cells}
    for cls in v05.SUBCLASSES:
        diags = sorted({v05.diagonal_connections(s) for s in v05.shapes_in_bbox(cls.BBOX)
                        if v05.components(s, v05._EDGE) > 1})
        for d in diags:
            pieces = {}
            # show each piece lying flat (width >= height) so the pictures line up
            for s in sorted(cls.candidates(d), key=lambda s: v05.size(s)[0] > v05.size(s)[1]):
                pieces.setdefault(piece_id(s), s)
            groups[(cls, d)] = pieces

    all_pieces = {pid: s for pieces in groups.values() for pid, s in pieces.items()}
    reachable = {piece_id(cls(d).cells) for (cls, d) in groups}
    print(f"\nExtended pieces that exist: {len(all_pieces)}")
    print(f"Distinct v0.5 constructor calls (subclass, diagonals): {len(groups)}")
    print(f"Pieces the v0.5 constructor can actually build: {len(reachable)}  "
          f"-> {len(all_pieces) - len(reachable)} pieces are unreachable\n")

    print(f"{'constructor call':28s} {'pieces matching':>15s}   status")
    for (cls, d), pieces in groups.items():
        status = "ok (unique)" if len(pieces) == 1 else f"AMBIGUOUS: returns 1 of {len(pieces)}"
        print(f"{cls.__name__ + f'(diagonals={d})':28s} {len(pieces):15d}   {status}")

    # -- the exact collisions --------------------------------------------------------------
    print("\n" + "=" * 78)
    print("Exact colliding shapes (each block = one constructor call; '*' = what v0.5 returns)")
    print("=" * 78)
    mirror_pairs = []
    for (cls, d), pieces in groups.items():
        if len(pieces) < 2:
            continue
        chosen = piece_id(cls(d).cells)
        ids = list(pieces)
        labels = []
        for pid in ids:
            twin = piece_id(mirror(pieces[pid]))
            tag = "*" if pid == chosen else " "
            labels.append(f"{tag}{code(pieces[pid])}")
            if twin != pid and twin in pieces and (twin, pid) not in mirror_pairs:
                mirror_pairs.append((pid, twin))
        print(f"\n  {cls.__name__}(diagonals={d}): bbox {cls.BBOX[0]}x{cls.BBOX[1]}, {d} diagonal "
              f"connection(s) -> {len(pieces)} different pieces")
        print(side_by_side([pieces[p] for p in ids], labels))
        twins_here = [(a, b) for a, b in mirror_pairs if a in pieces]
        for a, b in twins_here:
            print(f"      mirror twins (distinct chiral pieces): {code(pieces[a])}  <->  {code(pieces[b])}")

    # -- why mirror twins can never be separated by this key ----------------------------
    chiral = {pid for pid, s in all_pieces.items() if piece_id(mirror(s)) != pid}
    all_twin_pairs = {tuple(sorted((pid, piece_id(mirror(s))))) for pid, s in all_pieces.items() if pid in chiral}
    collided = all(any(a in g and b in g for g in groups.values()) for a, b in all_twin_pairs)
    preserved = all(sorted(v05.size(mirror(s))) == sorted(v05.size(s)) and
                    v05.diagonal_connections(mirror(s)) == v05.diagonal_connections(s) for s in all_pieces.values())
    print("\n" + "=" * 78)
    print("Why mirror twins always collide")
    print("=" * 78)
    print(f"  Reflection keeps the bounding box and the diagonal count for all {len(all_pieces)} pieces: {preserved}")
    print(f"  Chiral extended pieces: {len(chiral)} = {len(all_twin_pairs)} mirror pairs; "
          f"pairs that share one v0.5 constructor call: "
          f"{sum(any(a in g and b in g for g in groups.values()) for a, b in all_twin_pairs)}/{len(all_twin_pairs)}")
    print("  => Any key built only from reflection-invariant properties can NEVER separate twins;")
    print("     a handedness (reflection-sensitive) parameter is logically required.")

    # -- which refinement fixes it -------------------------------------------------------
    print("\n" + "=" * 78)
    print("Refinement probes (what must be added to the constructor key)")
    print("=" * 78)

    def residual(extra):
        g = defaultdict(list)
        for pid, s in all_pieces.items():
            g[(tuple(sorted(v05.size(s))), v05.diagonal_connections(s)) + extra(s)].append(code(s))
        return [v for v in g.values() if len(v) > 1]

    probes = [
        ("(bbox, diagonals)                    [v0.5]", lambda s: ()),
        ("(bbox, diagonals, hole signature)", lambda s: (hole_signature(s),)),
        ("(bbox, diagonals, handedness)", lambda s: (handedness(s),)),
        ("(bbox, diagonals, holes, handedness)", lambda s: (hole_signature(s), handedness(s))),
        ("(bbox, holes, handedness)            [v1]", None),
    ]
    results = {}
    for label, extra in probes:
        if extra is None:
            g = defaultdict(list)
            for s in all_pieces.values():
                g[(tuple(sorted(v05.size(s))), hole_signature(s), handedness(s))].append(code(s))
            res = [v for v in g.values() if len(v) > 1]
        else:
            res = residual(extra)
        results[label] = res
        keys = len(all_pieces) - sum(len(v) - 1 for v in res)
        print(f"\n  {label}: {keys}/{len(all_pieces)} pieces distinguishable")
        for v in res:
            print("      still colliding: " + ", ".join(v))

    ok = (len(all_pieces) == 27 and len(groups) == 11 and len(reachable) == 11 and preserved and collided
          and results["(bbox, diagonals, hole signature)"] and results["(bbox, diagonals, handedness)"]
          and not results["(bbox, holes, handedness)            [v1]"])
    print("\n" + "=" * 78)
    print("PROOF COMPLETE: (bbox, diagonals) is ambiguous; hole signature AND handedness are both needed."
          if ok else "UNEXPECTED RESULT: the proof did not go through (see above).")
    print("=" * 78)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

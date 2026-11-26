#!/usr/bin/env python3
"""
explore_polyominoes.py -- combinatorics of ExTetrominoes (4-cell "polykings").

Standalone exploration for CS F301 PoPL ExTetris. NOT part of the game.
Standard library only (no numpy).

What it does
  1. Enumerates every 4-cell shape whose cells are connected through edges OR
     corners (king's-graph connectivity) with two independent algorithms and
     checks that they agree.
  2. Counts fixed shapes, one-sided shapes (equal up to 90-degree rotations), and
     free shapes (equal up to rotations and reflections). Expected values come
     from OEIS: A006770 = 110, A030233 = 34, A030222 = 22.
  3. Computes rotation-invariant geometric properties of each one-sided shape and
     checks which combinations of them identify all 34 shapes uniquely, so that no
     boolean matrix needs to be hard-coded.
  4. Optional: --starter PATH maps the 73 matrices of the starter
     allextetrominoes.py onto the 34 shapes. The file is parsed with `ast`;
     nothing is imported or eval()'d.

Usage
  python explore_polyominoes.py
  python explore_polyominoes.py --starter v0_starter/allextetrominoes.py
  python explore_polyominoes.py --starter v0_starter/allextetrominoes.py --json shapes.json

Conventions
  A cell is (row, col): row grows downward and col grows rightward, as in the game
  board. A shape is a frozenset of cells, translated so that its min row and min
  col are 0. CW means clockwise as seen on screen.

  "Landing holes" (an assumption; check it against the 6 Nov tutorial definition):
  drop the piece in a given orientation onto an empty, flat floor. A hole is an
  empty cell inside the piece's bounding box that has a piece cell somewhere above
  it in the same column, i.e. a cell that is covered and can no longer be filled
  from directly above.
"""
import argparse
import ast
import itertools
import json
import re
import sys
from collections import Counter, defaultdict

N = 4
EDGE_STEPS = [(-1, 0), (1, 0), (0, -1), (0, 1)]
CORNER_STEPS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
KING_STEPS = EDGE_STEPS + CORNER_STEPS

# ----------------------------------------------------------------------------
# Basic geometry
# ----------------------------------------------------------------------------
def normalize(cells):
    r0 = min(r for r, _ in cells)
    c0 = min(c for _, c in cells)
    return frozenset((r - r0, c - c0) for r, c in cells)


def rotate_cw(shape):
    """Rotate 90 degrees clockwise on screen: (r, c) -> (c, -r), then re-anchor."""
    return normalize({(c, -r) for r, c in shape})


def mirror(shape):
    """Reflect left-right: (r, c) -> (r, -c), then re-anchor."""
    return normalize({(r, -c) for r, c in shape})


def rotations(shape):
    """The 4 orientations in CW order, starting from `shape` itself."""
    out = [shape]
    for _ in range(3):
        out.append(rotate_cw(out[-1]))
    return out


def key(shape):
    return tuple(sorted(shape))


def components(shape, steps):
    cells, comps = set(shape), 0
    while cells:
        comps += 1
        stack = [cells.pop()]
        while stack:
            r, c = stack.pop()
            for dr, dc in steps:
                q = (r + dr, c + dc)
                if q in cells:
                    cells.remove(q)
                    stack.append(q)
    return comps


def size(shape):
    return 1 + max(r for r, _ in shape), 1 + max(c for _, c in shape)  # (height, width)


def picture(shape, on="#", off="."):
    h, w = size(shape)
    return ["".join(on if (r, c) in shape else off for c in range(w)) for r in range(h)]


# ----------------------------------------------------------------------------
# Enumeration (two independent methods)
# ----------------------------------------------------------------------------
def enumerate_bruteforce(n=N):
    """Every n-subset of an n x n box (any n-cell polyking fits in one), keep king-connected."""
    box = [(r, c) for r in range(n) for c in range(n)]
    found = set()
    for combo in itertools.combinations(box, n):
        if components(combo, KING_STEPS) == 1:
            found.add(normalize(combo))
    return found


def enumerate_growth(n=N):
    """Grow shapes one cell at a time from a single cell, adding any king-neighbour."""
    level = {frozenset({(0, 0)})}
    for _ in range(n - 1):
        nxt = set()
        for s in level:
            for r, c in s:
                for dr, dc in KING_STEPS:
                    q = (r + dr, c + dc)
                    if q not in s:
                        nxt.add(normalize(s | {q}))
        level = nxt
    return level


def onesided_key(shape):
    return min(key(x) for x in rotations(shape))


def free_key(shape):
    return min(onesided_key(shape), onesided_key(mirror(shape)))


# ----------------------------------------------------------------------------
# Invariants. Each is unchanged by 90-degree rotation, so it is a property of a
# one-sided shape, not of one orientation.
# ----------------------------------------------------------------------------
def inv_bbox(shape):
    """Bounding box as an unordered pair, e.g. '2x4' (a 4x2 and a 2x4 are the same piece rotated)."""
    h, w = sorted(size(shape))
    return f"{h}x{w}"


def inv_adjacency(shape):
    """(edge-adjacent pairs, corner-only-adjacent pairs) among the 4 cells."""
    cells = list(shape)
    e = d = 0
    for (r1, c1), (r2, c2) in itertools.combinations(cells, 2):
        dr, dc = abs(r1 - r2), abs(c1 - c2)
        if dr + dc == 1:
            e += 1
        elif dr == 1 and dc == 1:
            d += 1
    return e, d


def inv_edge_components(shape):
    """Edge-connected pieces: 1 = classic tetromino; 2-4 = needs corner contacts."""
    return components(shape, EDGE_STEPS)


def landing_holes(orientation):
    h, w = size(orientation)
    holes = 0
    for c in range(w):
        top = min(r for r, cc in orientation if cc == c)  # every column of a tight bbox is non-empty
        holes += sum(1 for r in range(top + 1, h) if (r, c) not in orientation)
    return holes


def cyclic_min(seq):
    return min(tuple(seq[i:] + seq[:i]) for i in range(len(seq)))


def inv_hole_signature(shape):
    """Holes for the 4 orientations in CW order, read from the canonical starting point
    (lexicographically smallest rotation of the cycle). A mirror image gives the
    reversed cycle, so this can tell some mirror pairs apart."""
    return cyclic_min([landing_holes(o) for o in rotations(shape)])


def inv_hole_multiset(shape):
    """Same as above but ignoring order: also unchanged by reflection."""
    return tuple(sorted(landing_holes(o) for o in rotations(shape)))


def inv_chirality(shape):
    return "achiral" if onesided_key(mirror(shape)) == onesided_key(shape) else "chiral"


def _gmul(a, b):  # Gaussian-integer product, exact
    return (a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0])


def spin4_moment(shape):
    """M4 = sum over cells of z^4, where z = x + iy is measured from the centroid
    (x = col, y = -row, scaled by 4 so everything stays an integer).
    A 90-degree turn multiplies z by -i, and (-i)^4 = 1, so M4 does not change.
    A left-right mirror conjugates z, so Im(M4) flips sign. Im(M4) is therefore a
    rotation-invariant 'handedness' number: 0 for achiral shapes, +/- for mirror pairs."""
    sx = sum(c for _, c in shape)
    sy = sum(-r for r, _ in shape)
    re_, im_ = 0, 0
    for r, c in shape:
        z = (4 * c - sx, 4 * (-r) - sy)
        z2 = _gmul(z, z)
        z4 = _gmul(z2, z2)
        re_ += z4[0]
        im_ += z4[1]
    return re_, im_


def inv_handedness(shape):
    im = spin4_moment(shape)[1]
    return "+" if im > 0 else "-" if im < 0 else "0"


INVARIANTS = {
    "bbox": inv_bbox,
    "edge/corner pairs": inv_adjacency,
    "edge components": inv_edge_components,
    "hole signature (cyclic)": inv_hole_signature,
    "chirality": inv_chirality,
    "handedness (sign Im M4)": inv_handedness,
}

# ----------------------------------------------------------------------------
# Starter-file cross-reference (parsed with ast; never executed)
# ----------------------------------------------------------------------------
def load_starter(path):
    tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            m = re.fullmatch(r"Extetromino(\d+)", node.targets[0].id)
            if m and isinstance(node.value, ast.Call) and node.value.args:
                rows = ast.literal_eval(node.value.args[0])
                out[int(m[1])] = normalize({(r, c) for r, row in enumerate(rows) for c, v in enumerate(row) if v})
    return dict(sorted(out.items()))


# ----------------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--starter", help="path to the starter allextetrominoes.py to cross-reference")
    ap.add_argument("--json", help="write the 34-shape catalogue to this JSON file")
    args = ap.parse_args()

    # 1. Enumeration ---------------------------------------------------------
    brute, grown = enumerate_bruteforce(), enumerate_growth()
    assert brute == grown, "the two enumeration methods disagree"
    fixed = brute
    onesided = defaultdict(list)
    for s in fixed:
        onesided[onesided_key(s)].append(s)
    free = defaultdict(set)
    for k in onesided:
        free[free_key(frozenset(k))].add(k)

    print("=" * 78)
    print("1. COUNTS (king-connected 4-cell shapes)")
    print("=" * 78)
    n_classic_os = sum(1 for k in onesided if inv_edge_components(frozenset(k)) == 1)
    n_classic_free = sum(1 for k in free if inv_edge_components(frozenset(k)) == 1)
    achiral = sum(1 for v in free.values() if len(v) == 1)
    rows = [
        ("fixed (translations only)", len(fixed), 110, "A006770"),
        ("one-sided (up to rotation)", len(onesided), 34, "A030233"),
        ("free (rotation + reflection)", len(free), 22, "A030222"),
        ("free, mirror-symmetric", achiral, 10, "A030234"),
        ("free, chiral (come in pairs)", len(free) - achiral, 12, "A030235"),
    ]
    for label, got, want, oeis in rows:
        print(f"  {label:32s} {got:4d}   expected {want:4d} (OEIS {oeis})  {'OK' if got == want else 'MISMATCH'}")
        assert got == want
    print(f"  brute-force and growth enumerations agree: {len(brute)} == {len(grown)}")
    print(f"  one-sided split: {n_classic_os} classic (edge-connected) + {len(onesided) - n_classic_os} extended")
    print(f"  free split:      {n_classic_free} classic (edge-connected) + {len(free) - n_classic_free} extended")
    orient = Counter(len(v) for v in onesided.values())
    print("  distinct orientations per one-sided shape:",
          ", ".join(f"{k} orientation(s): {orient[k]} shapes" for k in sorted(orient)),
          f"(check: sum = {sum(k * v for k, v in orient.items())})")

    # 2. Catalogue -----------------------------------------------------------
    shapes = sorted((frozenset(k) for k in onesided),
                    key=lambda s: (inv_edge_components(s), inv_bbox(s), inv_adjacency(s),
                                   inv_hole_signature(s), inv_handedness(s)))
    table = []
    for i, s in enumerate(shapes, 1):
        row = {"id": f"P{i:02d}", "picture": "/".join(picture(s))}
        row.update({name: f(s) for name, f in INVARIANTS.items()})
        row["Im M4"] = spin4_moment(s)[1]
        row["orientations"] = len(onesided[key(s)])
        row["mirror"] = None
        table.append(row)
    by_key = {key(s): row for s, row in zip(shapes, table)}
    for s, row in zip(shapes, table):
        mk = onesided_key(mirror(s))
        row["mirror"] = by_key[mk]["id"] if mk != key(s) else "self"

    starter = load_starter(args.starter) if args.starter else {}
    if starter:
        groups = defaultdict(list)
        for idx, s in starter.items():
            groups[onesided_key(s)].append(idx)
        for s, row in zip(shapes, table):
            row["starter indices"] = groups.get(key(s), [])

    print("\n" + "=" * 78)
    print("2. CATALOGUE OF THE 34 ONE-SIDED SHAPES (canonical orientation; '/' = new row)")
    print("=" * 78)
    hdr = f"{'id':4} {'picture':18} {'bbox':4} {'E,D':5} {'eC':2} {'holes':12} {'chir':7} {'hand':4} {'ImM4':>6} {'mir':4} {'or':2}"
    if starter:
        hdr += "  starter idx"
    print(hdr)
    for r in table:
        line = (f"{r['id']:4} {r['picture']:18} {r['bbox']:4} {'%d,%d' % r['edge/corner pairs']:5} "
                f"{r['edge components']:<2} {str(r['hole signature (cyclic)']):12} {r['chirality']:7} "
                f"{r['handedness (sign Im M4)']:4} {r['Im M4']:6d} {r['mirror']:4} {r['orientations']:<2}")
        if starter:
            line += "  " + str(r["starter indices"])
        print(line)
    print("  E,D = edge-adjacent / corner-only-adjacent cell pairs; eC = edge-connected components;")
    print("  holes = landing holes per orientation (CW cycle); or = distinct orientations")

    # 3. Which invariants identify the shapes? -----------------------------------
    print("\n" + "=" * 78)
    print("3. DO THE INVARIANTS IDENTIFY EVERY SHAPE?")
    print("=" * 78)
    names = list(INVARIANTS)
    vals = {n_: [r[n_] for r in table] for n_ in names}

    def distinct(combo):
        return len(set(zip(*(vals[c] for c in combo))))

    def collisions(combo):
        g = defaultdict(list)
        for r in table:
            g[tuple(r[c] for c in combo)].append(r["id"])
        return [v for v in g.values() if len(v) > 1]

    print("  Single invariants (34 = identifies every one-sided shape):")
    for n_ in names:
        d = distinct((n_,))
        biggest = max((len(v) for v in collisions((n_,))), default=1)
        print(f"    {n_:28s} {d:3d} distinct values; largest group of look-alikes = {biggest}")

    requested = ("bbox", "edge/corner pairs", "hole signature (cyclic)", "chirality", "handedness (sign Im M4)")
    print(f"\n  Requested combination {requested}:")
    print(f"    {distinct(requested)} distinct values for 34 shapes -> "
          f"{'UNIQUE' if distinct(requested) == 34 else 'NOT unique: ' + str(collisions(requested))}")

    print("    what collides if one of them is dropped:")
    for drop in requested:
        rest = tuple(c for c in requested if c != drop)
        print(f"      without {drop:26s} {distinct(rest):2d}/34  {collisions(rest) or 'still unique'}")

    minimal = []
    for k in range(1, len(names) + 1):
        for combo in itertools.combinations(names, k):
            if distinct(combo) == 34 and not any(set(m) <= set(combo) for m in minimal):
                minimal.append(combo)
    print("\n  Minimal combinations that identify all 34 (no proper subset suffices):")
    for m in sorted(minimal, key=len):
        print(f"    {len(m)}: " + " + ".join(m))
    near = ("hole signature (cyclic)", "handedness (sign Im M4)")
    print(f"  closest pair: hole signature + handedness -> {distinct(near)}/34, collides on {collisions(near)}")

    no_hand = tuple(n_ for n_ in names if not n_.startswith("handedness"))
    print("\n  Everything except handedness:", distinct(no_hand), "distinct ->",
          "mirror pairs still merged:" if collisions(no_hand) else "", collisions(no_hand) or "none")

    achiral_names = ("bbox", "edge/corner pairs", "edge components", "chirality")
    free_vals = defaultdict(set)
    for s, r in zip(shapes, table):
        free_vals[free_key(s)].add(tuple(r[c] for c in achiral_names) + (inv_hole_multiset(s),))
    free_sigs = Counter(next(iter(v)) for v in free_vals.values())
    print(f"\n  Free level (mirror-proof invariants only: bbox, E/D pairs, edge components, chirality, hole multiset):")
    print(f"    {len(free_sigs)} distinct values for {len(free)} free shapes ->",
          "UNIQUE" if len(free_sigs) == len(free) else "NOT unique")
    chiral_ok = all(r["handedness (sign Im M4)"] != "0" for r in table if r["chirality"] == "chiral") and \
        all(r["handedness (sign Im M4)"] == "0" for r in table if r["chirality"] == "achiral")
    pairs_opposite = all(by_key_r["handedness (sign Im M4)"] != r["handedness (sign Im M4)"]
                         for r in table if r["mirror"] != "self"
                         for by_key_r in [next(t for t in table if t["id"] == r["mirror"])])
    print(f"    Im M4 is 0 exactly for the achiral shapes and non-zero for all chiral ones: {chiral_ok}")
    print(f"    every mirror pair gets opposite handedness signs: {pairs_opposite}")

    print("\n  How each bounding box splits:")
    for bb, grp in itertools.groupby(sorted(table, key=lambda r: r["bbox"]), key=lambda r: r["bbox"]):
        grp = list(grp)
        print(f"    {bb}: {len(grp):2d} shapes ({sum(r['edge components'] == 1 for r in grp)} classic)")

    # 4. Starter cross-reference ------------------------------------------------
    if starter:
        print("\n" + "=" * 78)
        print(f"4. STARTER FILE: {args.starter}")
        print("=" * 78)
        print(f"  {len(starter)} matrices -> {len({onesided_key(s) for s in starter.values()})} distinct one-sided shapes")
        exact = defaultdict(list)
        for idx, s in starter.items():
            exact[key(s)].append(idx)
        print("  identical matrices (same shape, same orientation):", [v for v in exact.values() if len(v) > 1])
        mult = Counter(len(r["starter indices"]) for r in table)
        print("  how many times each shape is listed:",
              ", ".join(f"x{k}: {mult[k]} shapes" for k in sorted(mult, reverse=True)))
        print("  -> P(shape) under uniform-by-index sampling ranges from "
              f"{min(len(r['starter indices']) for r in table)}/73 to {max(len(r['starter indices']) for r in table)}/73")
        missing = [r["id"] for r in table if not r["starter indices"]]
        print("  shapes missing from the starter:", missing or "none")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(table, f, indent=1, default=list)
        print(f"\nCatalogue written to {args.json}")


if __name__ == "__main__":
    sys.exit(main())

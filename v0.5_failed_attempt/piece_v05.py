"""
piece_v05.py -- v0.5 constructor design.  *** FLAWED: preserved for the record. ***

Kept unchanged for the Continued Development Report. Superseded by
v1_core_system/piece.py. Do not import it from the game.

Design idea (v0.5)
    Like v1, no piece is stored as a boolean matrix. ExTetromino subclasses are
    chosen by bounding box, and the constructor takes ONE geometric parameter: the
    number of diagonal connections (pairs of cells that touch only at a corner).
    The constructor generates every 4-cell shape that fits the subclass's bounding
    box and has that many diagonal connections, and assumes that they are all
    rotations of a single piece:

        ExTetromino3x3(diagonals=2)      # "the" 3x3 piece with 2 diagonal links

The flaw (demonstrated by verify_v05.py)
    (bounding box, diagonal count) does not determine the piece. For example,
    6 different 3x3 pieces have exactly 2 diagonal connections. The constructor
    silently returns the first candidate, so most extended pieces can never be
    built, and mirror-image twins can never be told apart. Both properties are
    unchanged by reflection, so no key made only from them can separate twins.
"""
from __future__ import annotations

import itertools

CELL_COUNT = 4
_EDGE = ((-1, 0), (1, 0), (0, -1), (0, 1))
_CORNER = ((-1, -1), (-1, 1), (1, -1), (1, 1))


def normalize(cells):
    r0 = min(r for r, _ in cells)
    c0 = min(c for _, c in cells)
    return frozenset((r - r0, c - c0) for r, c in cells)


def rotate_cw(cells):
    return normalize({(c, -r) for r, c in cells})


def size(cells):
    return 1 + max(r for r, _ in cells), 1 + max(c for _, c in cells)


def components(cells, steps):
    todo, count = set(cells), 0
    while todo:
        count += 1
        stack = [todo.pop()]
        while stack:
            r, c = stack.pop()
            for dr, dc in steps:
                q = (r + dr, c + dc)
                if q in todo:
                    todo.remove(q)
                    stack.append(q)
    return count


def diagonal_connections(cells):
    """Pairs of cells touching only at a corner."""
    return sum(1 for (r1, c1), (r2, c2) in itertools.combinations(cells, 2)
               if abs(r1 - r2) == 1 and abs(c1 - c2) == 1)


def shapes_in_bbox(bbox):
    """All fixed 4-cell, king-connected shapes whose bounding box is bbox (either way round)."""
    h, w = bbox
    found = set()
    for hh, ww in {(h, w), (w, h)}:
        box = [(r, c) for r in range(hh) for c in range(ww)]
        for combo in itertools.combinations(box, CELL_COUNT):
            s = normalize(combo)
            if size(s) == (hh, ww) and components(s, _EDGE + _CORNER) == 1:
                found.add(s)
    return sorted(found, key=lambda s: sorted(s))


class Piece:
    """v0.5 base: an immutable set of cells."""

    __slots__ = ("cells",)

    def __init__(self, cells):
        object.__setattr__(self, "cells", normalize(cells))

    def __setattr__(self, name, value):
        raise AttributeError("Piece is immutable")

    @property
    def bbox(self):
        return tuple(sorted(size(self.cells)))

    @property
    def diagonals(self):
        return diagonal_connections(self.cells)

    def rotated_cw(self):
        return type(self)._from_cells(rotate_cw(self.cells))

    @classmethod
    def _from_cells(cls, cells):
        obj = object.__new__(cls)
        object.__setattr__(obj, "cells", normalize(cells))
        return obj

    def __str__(self):
        h, w = size(self.cells)
        return "\n".join("".join("#" if (r, c) in self.cells else "." for c in range(w)) for r in range(h))


class ExTetromino(Piece):
    """v0.5: an extended piece, chosen by (bounding box, diagonal connections)."""

    __slots__ = ()
    BBOX = None

    def __init__(self, diagonals):
        candidates = self.candidates(diagonals)
        if not candidates:
            raise ValueError(f"{type(self).__name__}: no piece has {diagonals} diagonal connections")
        # v0.5 ASSUMPTION (wrong): every candidate is a rotation of the same piece.
        super().__init__(candidates[0])

    @classmethod
    def candidates(cls, diagonals):
        """Every fixed shape the v0.5 constructor treats as 'the' piece for these arguments."""
        return [s for s in shapes_in_bbox(cls.BBOX)
                if components(s, _EDGE) > 1 and diagonal_connections(s) == diagonals]


class ExTetromino2x3(ExTetromino):
    __slots__ = ()
    BBOX = (2, 3)


class ExTetromino2x4(ExTetromino):
    __slots__ = ()
    BBOX = (2, 4)


class ExTetromino3x3(ExTetromino):
    __slots__ = ()
    BBOX = (3, 3)


class ExTetromino3x4(ExTetromino):
    __slots__ = ()
    BBOX = (3, 4)


class ExTetromino4x4(ExTetromino):
    __slots__ = ()
    BBOX = (4, 4)


SUBCLASSES = (ExTetromino2x3, ExTetromino2x4, ExTetromino3x3, ExTetromino3x4, ExTetromino4x4)

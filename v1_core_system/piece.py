"""
piece.py -- immutable piece hierarchy for the ExTetris Programming System (v1).

A piece is 4 unit cells joined through edges or corners ("king-connected").
Counting rotations as the same piece, there are exactly 34 of them: the 7 classic
tetrominoes plus 27 extended pieces that need at least one corner-only contact.

No piece is stored as a boolean matrix (assignment Section 3.2). On first use the
module generates all 110 fixed shapes by growing cells one at a time. Each
constructor then *selects* its piece using geometric invariants:

    Tetromino("T")                                     # classic piece, by letter
    Tetromino.from_invariants("2x3", (0, 1, 2, 1))     # the same piece, by geometry
    ExTetromino3x3((2, 2, 3, 3), Handedness.PLUS)      # extended piece, by geometry
    ExTetromino.create("3x3", (2, 2, 3, 3), +1)        # the same, dispatching on bbox

Class hierarchy (number of pieces in brackets)

    Piece                     abstract, immutable
    |-- Tetromino             [7]  edge-connected classics I O T S Z L J
    `-- ExTetromino           abstract; [27] pieces that need a corner contact
        |-- ExTetromino2x3    [2]
        |-- ExTetromino2x4    [9]
        |-- ExTetromino3x3    [9]
        |-- ExTetromino3x4    [6]
        `-- ExTetromino4x4    [1]

Invariants (none of them changes when the piece is rotated by 90 degrees)

    bbox            bounding box as (short side, long side), e.g. (2, 4)
    hole_signature  landing holes in each of the 4 orientations, in clockwise order,
                    written from the lexicographically smallest starting point
    handedness      PLUS or MINUS for the two members of a mirror-image pair,
                    NONE for a piece that is its own mirror image. Computed as the
                    sign of Im(sum of z**4) over the cells, measured from the
                    centroid. PLUS is the hand of the classic L and S.

(bbox, hole_signature, handedness) identifies each of the 34 pieces. This is
checked while the catalogue is built, so a constructor call can never be ambiguous.

Landing holes (the definition used throughout, see docs/): rest the piece on an
empty, flat floor. A hole is an empty cell inside the piece's bounding box that has
a piece cell somewhere above it in the same column.

Coordinates: a cell is (row, col), with row growing downward as on the game board.
"""
from __future__ import annotations

import abc
import dataclasses
import enum
import functools
import types
from dataclasses import dataclass
from typing import ClassVar, Iterable, Mapping

import numpy as np

__all__ = [
    "CELL_COUNT",
    "Handedness",
    "PieceSpecError",
    "ShapeInfo",
    "Piece",
    "Tetromino",
    "ExTetromino",
    "ExTetromino2x3",
    "ExTetromino2x4",
    "ExTetromino3x3",
    "ExTetromino3x4",
    "ExTetromino4x4",
    "catalogue_stats",
]

CELL_COUNT = 4
"""Cells per piece. The invariant-uniqueness guarantee is checked for 4 only."""

Cell = tuple[int, int]

# Neighbour steps are generated rather than listed.
_EDGE_STEPS = tuple((dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if abs(dr) + abs(dc) == 1)
_CORNER_STEPS = tuple((dr, dc) for dr in (-1, 1) for dc in (-1, 1))
_KING_STEPS = _EDGE_STEPS + _CORNER_STEPS


class PieceSpecError(ValueError):
    """The arguments do not describe any existing piece (the message lists valid choices)."""


class Handedness(enum.IntEnum):
    """Which member of a mirror-image pair a piece is.

    PLUS is the hand of the classic L and S tetrominoes, and MINUS that of J and Z.
    NONE marks a piece that equals its own mirror image (I, O, T and 7 extended pieces).
    """

    MINUS = -1
    NONE = 0
    PLUS = 1

    @classmethod
    def coerce(cls, value: object) -> "Handedness":
        """Accept Handedness, -1/0/+1, or '+', '-', '0', 'plus', 'minus', 'none'."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            table = {"+": cls.PLUS, "plus": cls.PLUS, "-": cls.MINUS, "minus": cls.MINUS,
                     "0": cls.NONE, "none": cls.NONE}
            if value.strip().lower() in table:
                return table[value.strip().lower()]
        elif isinstance(value, int) and not isinstance(value, bool) and value in (-1, 0, 1):
            return cls(value)
        raise PieceSpecError(f"handedness must be PLUS/+1, MINUS/-1 or NONE/0, got {value!r}")

    @property
    def symbol(self) -> str:
        return {1: "+", -1: "-", 0: "0"}[int(self)]


# ----------------------------------------------------------------------------
# Pure geometry on frozensets of cells
# ----------------------------------------------------------------------------
def _normalize(cells: Iterable[Cell]) -> frozenset[Cell]:
    cells = tuple(cells)
    r0 = min(r for r, _ in cells)
    c0 = min(c for _, c in cells)
    return frozenset((r - r0, c - c0) for r, c in cells)


def _rotate_cw(cells: frozenset[Cell]) -> frozenset[Cell]:
    """Rotate 90 degrees clockwise on screen."""
    return _normalize((c, -r) for r, c in cells)


def _mirror(cells: frozenset[Cell]) -> frozenset[Cell]:
    """Reflect left to right."""
    return _normalize((r, -c) for r, c in cells)


def _size(cells: frozenset[Cell]) -> tuple[int, int]:
    """(height, width) of the bounding box."""
    return 1 + max(r for r, _ in cells), 1 + max(c for _, c in cells)


def _key(cells: frozenset[Cell]) -> tuple[Cell, ...]:
    return tuple(sorted(cells))


def _components(cells: Iterable[Cell], steps: tuple[Cell, ...]) -> int:
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


def _pairs(cells: frozenset[Cell]) -> tuple[int, int]:
    """(edge-adjacent pairs, corner-only-adjacent pairs)."""
    ordered = sorted(cells)
    edge = corner = 0
    for i, (r1, c1) in enumerate(ordered):
        for r2, c2 in ordered[i + 1:]:
            dr, dc = abs(r1 - r2), abs(c1 - c2)
            if dr + dc == 1:
                edge += 1
            elif dr == dc == 1:
                corner += 1
    return edge, corner


def _landing_holes(cells: frozenset[Cell]) -> int:
    height, width = _size(cells)
    holes = 0
    for col in range(width):
        top = min(r for r, c in cells if c == col)
        holes += sum(1 for r in range(top + 1, height) if (r, col) not in cells)
    return holes


def _four_turns(cells: frozenset[Cell]) -> list[frozenset[Cell]]:
    turns = [cells]
    for _ in range(3):
        turns.append(_rotate_cw(turns[-1]))
    return turns


def _orientation_cycle(cells: frozenset[Cell]) -> tuple[frozenset[Cell], ...]:
    """Distinct orientations, clockwise, starting with `cells` (length 1, 2 or 4)."""
    cycle, nxt = [cells], _rotate_cw(cells)
    while nxt != cells:
        cycle.append(nxt)
        nxt = _rotate_cw(nxt)
    return tuple(cycle)


def _onesided_key(cells: frozenset[Cell]) -> tuple[Cell, ...]:
    return min(_key(o) for o in _orientation_cycle(cells))


def _cyclic_min(seq: Iterable[int]) -> tuple[int, ...]:
    seq = list(seq)
    return min(tuple(seq[i:] + seq[:i]) for i in range(len(seq)))


def _spin4_imag(cells: frozenset[Cell]) -> int:
    """Im(sum z^4) with z = x + iy measured from the centroid (x = col, y = -row).

    Everything is scaled by the cell count, so the arithmetic stays in exact
    integers. A 90-degree turn multiplies z by -i, and (-i)^4 = 1, so the value is
    unchanged by rotation. A mirror conjugates z, so the value changes sign.
    """
    n = len(cells)
    sx = sum(c for _, c in cells)
    sy = sum(-r for r, _ in cells)
    total = 0
    for r, c in cells:
        x, y = n * c - sx, n * (-r) - sy
        total += 4 * x ** 3 * y - 4 * x * y ** 3
    return total


def _grow_fixed_shapes(n: int = CELL_COUNT) -> frozenset[frozenset[Cell]]:
    """Every fixed n-cell king-connected shape, grown one cell at a time."""
    level = {frozenset({(0, 0)})}
    for _ in range(n - 1):
        level = {_normalize(s | {(r + dr, c + dc)})
                 for s in level for r, c in s for dr, dc in _KING_STEPS
                 if (r + dr, c + dc) not in s}
    return frozenset(level)


# ----------------------------------------------------------------------------
# Catalogue of the 34 shapes (built once, read-only)
# ----------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ShapeInfo:
    """Read-only geometry shared by every orientation of one piece."""

    identity: tuple[Cell, ...]
    bbox: tuple[int, int]
    edge_pairs: int
    corner_pairs: int
    edge_components: int
    hole_signature: tuple[int, int, int, int]
    handedness: Handedness
    orientations: tuple[frozenset[Cell], ...]
    classic_name: str | None = None

    @property
    def is_classic(self) -> bool:
        return self.edge_components == 1

    @property
    def code(self) -> str:
        """Stable identifier built from the invariants, e.g. 'X3x3.H2233.+'."""
        family = "T" if self.is_classic else "X"
        holes = "".join(str(h) for h in self.hole_signature)
        return f"{family}{self.bbox[0]}x{self.bbox[1]}.H{holes}.{self.handedness.symbol}"


# Letters for the classic pieces, given as invariants (not as cells). Checked
# when the catalogue is built: each letter must match exactly one shape.
_CLASSIC_INVARIANTS: Mapping[str, tuple[tuple[int, int], tuple[int, int, int, int], Handedness]] = \
    types.MappingProxyType({
        "I": ((1, 4), (0, 0, 0, 0), Handedness.NONE),
        "O": ((2, 2), (0, 0, 0, 0), Handedness.NONE),
        "T": ((2, 3), (0, 1, 2, 1), Handedness.NONE),
        "S": ((2, 3), (1, 1, 1, 1), Handedness.PLUS),
        "Z": ((2, 3), (1, 1, 1, 1), Handedness.MINUS),
        "L": ((2, 3), (0, 0, 2, 2), Handedness.PLUS),
        "J": ((2, 3), (0, 0, 2, 2), Handedness.MINUS),
    })
_LETTER_ALIASES = types.MappingProxyType({"GAMMA": "J"})  # the starter code calls J "Gamma"


def _describe(cells: frozenset[Cell]) -> ShapeInfo:
    cycle = _orientation_cycle(cells)
    # Spawn orientation: fewest landing holes, then the flattest, then a fixed tie-break.
    spawn = min(cycle, key=lambda o: (_landing_holes(o), _size(o)[0], _key(o)))
    edge, corner = _pairs(spawn)
    imag = _spin4_imag(spawn)
    return ShapeInfo(
        identity=_onesided_key(spawn),
        bbox=tuple(sorted(_size(spawn))),
        edge_pairs=edge,
        corner_pairs=corner,
        edge_components=_components(spawn, _EDGE_STEPS),
        hole_signature=_cyclic_min(_landing_holes(o) for o in _four_turns(spawn)),
        handedness=Handedness((imag > 0) - (imag < 0)),
        orientations=_orientation_cycle(spawn),
    )


@dataclass(frozen=True)
class _Catalogue:
    fixed_count: int
    shapes: tuple[ShapeInfo, ...]
    by_identity: Mapping[tuple[Cell, ...], ShapeInfo]
    by_orientation: Mapping[frozenset[Cell], tuple[ShapeInfo, int]]
    by_spec: Mapping[tuple[bool, tuple[int, int], tuple[int, ...], Handedness], ShapeInfo]
    by_code: Mapping[str, ShapeInfo]
    by_letter: Mapping[str, ShapeInfo]


@functools.cache
def _catalogue() -> _Catalogue:
    fixed = _grow_fixed_shapes()
    representatives: dict[tuple[Cell, ...], frozenset[Cell]] = {}
    for s in fixed:
        representatives.setdefault(_onesided_key(s), s)
    shapes = [_describe(s) for s in representatives.values()]

    letters = {}
    for letter, (bbox, holes, hand) in _CLASSIC_INVARIANTS.items():
        hits = [s for s in shapes if s.is_classic and (s.bbox, s.hole_signature, s.handedness) == (bbox, holes, hand)]
        if len(hits) != 1:
            raise RuntimeError(f"classic letter {letter} matches {len(hits)} shapes")
        letters[hits[0].identity] = letter
    shapes = [dataclasses.replace(s, classic_name=letters.get(s.identity)) for s in shapes]
    order = "IOTSZLJ"
    shapes.sort(key=lambda s: (not s.is_classic, order.index(s.classic_name) if s.classic_name else 0,
                               s.bbox, s.hole_signature, -int(s.handedness)))

    # Self-checks: if any of these ever fails, constructors would be unsafe.
    by_identity = {s.identity: s for s in shapes}
    free = {min(s.identity, _onesided_key(_mirror(s.orientations[0]))) for s in shapes}
    spec = {(s.is_classic, s.bbox, s.hole_signature, s.handedness): s for s in shapes}
    problems = []
    if len(fixed) != 110:
        problems.append(f"{len(fixed)} fixed shapes (expected 110)")
    if len(shapes) != 34 or sum(s.is_classic for s in shapes) != 7:
        problems.append(f"{len(shapes)} one-sided shapes (expected 34 = 7 + 27)")
    if len(free) != 22:
        problems.append(f"{len(free)} free shapes (expected 22)")
    if len(spec) != len(shapes):
        problems.append("(bbox, hole_signature, handedness) is not unique")
    for s in shapes:
        twin = by_identity[_onesided_key(_mirror(s.orientations[0]))]
        if (twin is s) != (s.handedness is Handedness.NONE) or int(twin.handedness) != -int(s.handedness):
            problems.append(f"handedness check failed for {s.code}")
    if problems:
        raise RuntimeError("piece catalogue self-check failed: " + "; ".join(problems))

    by_orientation = {o: (s, turn) for s in shapes for turn, o in enumerate(s.orientations)}
    return _Catalogue(
        fixed_count=len(fixed),
        shapes=tuple(shapes),
        by_identity=types.MappingProxyType(by_identity),
        by_orientation=types.MappingProxyType(by_orientation),
        by_spec=types.MappingProxyType(spec),
        by_code=types.MappingProxyType({s.code: s for s in shapes}),
        by_letter=types.MappingProxyType({s.classic_name: s for s in shapes if s.classic_name}),
    )


def catalogue_stats() -> dict[str, int]:
    """Counts behind the catalogue (fixed / one-sided / free / classic / extended)."""
    cat = _catalogue()
    free = {min(s.identity, _onesided_key(_mirror(s.orientations[0]))) for s in cat.shapes}
    return {
        "fixed": cat.fixed_count,
        "one_sided": len(cat.shapes),
        "free": len(free),
        "classic": sum(s.is_classic for s in cat.shapes),
        "extended": sum(not s.is_classic for s in cat.shapes),
    }


# ----------------------------------------------------------------------------
# Argument coercion
# ----------------------------------------------------------------------------
def _coerce_bbox(value: object) -> tuple[int, int]:
    if isinstance(value, str):
        parts = value.lower().split("x")
        if len(parts) == 2 and all(p.strip().isdigit() for p in parts):
            return tuple(sorted(int(p) for p in parts))
    elif isinstance(value, (tuple, list)) and len(value) == 2 and all(isinstance(v, int) for v in value):
        return tuple(sorted(value))
    raise PieceSpecError(f"bbox must look like '2x4' or (2, 4), got {value!r}")


def _coerce_holes(value: object) -> tuple[int, int, int, int]:
    if (isinstance(value, (tuple, list)) and len(value) == 4
            and all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in value)):
        return _cyclic_min(value)
    raise PieceSpecError(f"hole signature must be 4 non-negative ints (clockwise order), got {value!r}")


def _lookup(classic: bool, bbox: tuple[int, int], holes: object, hand: object, where: str) -> ShapeInfo:
    holes_c, hand_c = _coerce_holes(holes), Handedness.coerce(hand)
    shape = _catalogue().by_spec.get((classic, bbox, holes_c, hand_c))
    if shape is None:
        valid = [f"({', '.join(map(str, s.hole_signature))}) {s.handedness.name}"
                 for s in _catalogue().shapes if s.is_classic == classic and s.bbox == bbox]
        raise PieceSpecError(
            f"{where}: no piece with bbox {bbox[0]}x{bbox[1]}, hole signature {holes_c} and "
            f"handedness {hand_c.name}. Valid choices: " + ("; ".join(valid) or "none"))
    return shape


# ----------------------------------------------------------------------------
# The hierarchy
# ----------------------------------------------------------------------------
class Piece(abc.ABC):
    """Abstract, immutable piece: one shape in one orientation.

    Rotating a piece returns a new object. Nothing about an existing piece (or the
    shared catalogue) can ever change.
    """

    __slots__ = ("_shape", "_turn")

    # -- construction (internal) ------------------------------------------------
    @classmethod
    def _make(cls, shape: ShapeInfo, turn: int = 0) -> "Piece":
        obj = object.__new__(cls)
        object.__setattr__(obj, "_shape", shape)
        object.__setattr__(obj, "_turn", turn % len(shape.orientations))
        return obj

    @classmethod
    @abc.abstractmethod
    def variants(cls) -> tuple:
        """The constructor arguments that are valid for this class."""

    @abc.abstractmethod
    def _constructor_repr(self) -> str: ...

    # -- immutability -----------------------------------------------------------
    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} objects are immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"{type(self).__name__} objects are immutable")

    def __copy__(self) -> "Piece":
        return self

    def __deepcopy__(self, memo: dict) -> "Piece":
        return self

    def __reduce__(self):
        return (_restore, (type(self).__module__, type(self).__qualname__, self.code, self._turn))

    # -- identity ---------------------------------------------------------------
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Piece):
            return NotImplemented
        return self._shape.identity == other._shape.identity and self._turn == other._turn

    def __hash__(self) -> int:
        return hash((self._shape.identity, self._turn))

    def same_shape(self, other: "Piece") -> bool:
        """True if `other` is the same piece in any orientation."""
        return self._shape.identity == other._shape.identity

    # -- geometry of the current orientation -------------------------------------
    @property
    def shape(self) -> ShapeInfo:
        """Read-only record of the invariants shared by every orientation."""
        return self._shape

    @property
    def cells(self) -> frozenset[Cell]:
        """Occupied (row, col) cells of the current orientation, anchored at (0, 0)."""
        return self._shape.orientations[self._turn]

    @property
    def height(self) -> int:
        return _size(self.cells)[0]

    @property
    def width(self) -> int:
        return _size(self.cells)[1]

    @property
    def turn(self) -> int:
        """Orientation index: 0 is the spawn orientation, +1 per clockwise quarter turn."""
        return self._turn

    @property
    def orientation_count(self) -> int:
        """Number of distinct orientations (1, 2 or 4)."""
        return len(self._shape.orientations)

    @property
    def landing_holes(self) -> int:
        """Holes left under this orientation when it lands on a flat floor."""
        return _landing_holes(self.cells)

    # -- invariants (same for every orientation) ---------------------------------
    @property
    def code(self) -> str:
        return self._shape.code

    @property
    def name(self) -> str:
        """Letter for classic pieces, otherwise the invariant code."""
        return self._shape.classic_name or self._shape.code

    @property
    def bbox(self) -> tuple[int, int]:
        return self._shape.bbox

    @property
    def hole_signature(self) -> tuple[int, int, int, int]:
        return self._shape.hole_signature

    @property
    def min_landing_holes(self) -> int:
        return min(self._shape.hole_signature)

    @property
    def handedness(self) -> Handedness:
        return self._shape.handedness

    @property
    def is_chiral(self) -> bool:
        return self._shape.handedness is not Handedness.NONE

    @property
    def edge_pairs(self) -> int:
        return self._shape.edge_pairs

    @property
    def corner_pairs(self) -> int:
        """Pairs of cells that touch only at a corner (diagonal connections)."""
        return self._shape.corner_pairs

    @property
    def edge_components(self) -> int:
        return self._shape.edge_components

    # -- transformations (all return new objects) --------------------------------
    def turned(self, quarter_turns: int = 1) -> "Piece":
        """Rotate clockwise by `quarter_turns` (negative = anticlockwise)."""
        return type(self)._make(self._shape, self._turn + quarter_turns)

    def rotated_cw(self) -> "Piece":
        return self.turned(1)

    def rotated_ccw(self) -> "Piece":
        return self.turned(-1)

    def with_turn(self, turn: int) -> "Piece":
        """The same piece in absolute orientation `turn` (0 = spawn)."""
        return type(self)._make(self._shape, turn)

    def orientations(self) -> tuple["Piece", ...]:
        """Every distinct orientation, starting at the spawn orientation."""
        return tuple(type(self)._make(self._shape, t) for t in range(self.orientation_count))

    def mirror_image(self) -> "Piece":
        """The left-right mirror twin (itself for pieces with Handedness.NONE)."""
        twin_cells = _mirror(self.cells)
        twin, turn = _catalogue().by_orientation[twin_cells]
        return type(self)._make(twin, turn)

    # -- conversion ---------------------------------------------------------------
    def to_matrix(self) -> np.ndarray:
        """A fresh, read-only boolean array of the current orientation."""
        height, width = _size(self.cells)
        grid = np.zeros((height, width), dtype=bool)
        for r, c in self.cells:
            grid[r, c] = True
        grid.setflags(write=False)
        return grid

    def __str__(self) -> str:
        height, width = _size(self.cells)
        return "\n".join("".join("#" if (r, c) in self.cells else "." for c in range(width))
                         for r in range(height))

    def __repr__(self) -> str:
        base = self._constructor_repr()
        return base if self._turn == 0 else f"{base}.with_turn({self._turn})"

    def describe(self) -> str:
        """Multi-line summary (useful in notebooks and generated docs)."""
        s = self._shape
        return (f"{self.name}  [{type(self).__name__}]\n{self}\n"
                f"bbox {s.bbox[0]}x{s.bbox[1]}  holes {s.hole_signature}  hand {s.handedness.name}  "
                f"edge/corner pairs {s.edge_pairs}/{s.corner_pairs}  orientations {self.orientation_count}")

    # -- catalogue access ---------------------------------------------------------
    @classmethod
    def all_pieces(cls) -> tuple["Piece", ...]:
        """Every piece owned by this class (all 34 when called on Piece), at spawn."""
        out = []
        for shape in _catalogue().shapes:
            owner = _class_for(shape)
            if issubclass(owner, cls):
                out.append(owner._make(shape))
        return tuple(out)

    @staticmethod
    def identify_cells(cells: Iterable[Cell]) -> "Piece":
        """Recognise a set of (row, col) cells as a piece, in that orientation."""
        try:
            cell_set = {(int(r), int(c)) for r, c in cells}
        except (TypeError, ValueError) as exc:
            raise PieceSpecError(f"cells must be (row, col) pairs: {exc}") from None
        if len(cell_set) != CELL_COUNT:
            raise PieceSpecError(f"a piece has exactly {CELL_COUNT} cells, got {len(cell_set)}")
        if _components(cell_set, _KING_STEPS) != 1:
            raise PieceSpecError("cells are not connected through edges or corners")
        shape, turn = _catalogue().by_orientation[_normalize(cell_set)]
        return _class_for(shape)._make(shape, turn)

    @staticmethod
    def identify_matrix(matrix: object) -> "Piece":
        """Recognise a 2-D array-like of truthy cells (e.g. a legacy starter matrix)."""
        grid = np.asarray(matrix, dtype=bool)
        if grid.ndim != 2:
            raise PieceSpecError(f"matrix must be 2-D, got {grid.ndim}-D")
        return Piece.identify_cells(zip(*np.nonzero(grid)))

    @staticmethod
    def from_code(code: str) -> "Piece":
        """Rebuild a piece from its code, e.g. 'X3x3.H2233.+' (spawn orientation)."""
        shape = _catalogue().by_code.get(code)
        if shape is None:
            raise PieceSpecError(f"unknown piece code {code!r}")
        return _class_for(shape)._make(shape)


class Tetromino(Piece):
    """The 7 classic, edge-connected pieces: I O T S Z L J."""

    __slots__ = ()
    LETTERS: ClassVar[str] = "IOTSZLJ"

    def __new__(cls, letter: str) -> "Tetromino":
        key = str(letter).strip().upper()
        key = _LETTER_ALIASES.get(key, key)
        shape = _catalogue().by_letter.get(key)
        if shape is None:
            raise PieceSpecError(f"Tetromino letter must be one of {', '.join(cls.LETTERS)}, got {letter!r}")
        return cls._make(shape)

    @classmethod
    def from_invariants(cls, bbox: object, holes: object, hand: object = Handedness.NONE) -> "Tetromino":
        """Select a classic piece by geometry instead of by letter."""
        shape = _lookup(True, _coerce_bbox(bbox), holes, hand, cls.__name__)
        return cls._make(shape)

    @classmethod
    def variants(cls) -> tuple[str, ...]:
        return tuple(cls.LETTERS)

    @property
    def letter(self) -> str:
        return self._shape.classic_name

    def _constructor_repr(self) -> str:
        return f"{type(self).__name__}({self.letter!r})"


class ExTetromino(Piece):
    """Abstract parent of the 27 extended pieces (they need at least one corner contact).

    Use a bounding-box subclass, e.g. ``ExTetromino2x4((1, 1, 3, 3), Handedness.MINUS)``,
    or ``ExTetromino.create("2x4", (1, 1, 3, 3), -1)``.
    """

    __slots__ = ()
    BBOX: ClassVar[tuple[int, int] | None] = None
    _registry: ClassVar[dict[tuple[int, int], type["ExTetromino"]]] = {}

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Register only the class that first declares a bbox; a designer's subclass
        # of ExTetromino3x3 must not take over identify()/all_pieces().
        if "BBOX" in cls.__dict__ and cls.BBOX is not None:
            cls.BBOX = tuple(sorted(cls.BBOX))
            ExTetromino._registry.setdefault(cls.BBOX, cls)

    def __new__(cls, holes: object, hand: object = Handedness.NONE) -> "ExTetromino":
        if cls.BBOX is None:
            raise TypeError("ExTetromino is abstract: use ExTetromino2x3 ... ExTetromino4x4, "
                            "or ExTetromino.create(bbox, holes, hand)")
        return cls._make(_lookup(False, cls.BBOX, holes, hand, cls.__name__))

    @classmethod
    def create(cls, bbox: object, holes: object, hand: object = Handedness.NONE) -> "ExTetromino":
        """Factory that picks the bounding-box subclass for you."""
        b = _coerce_bbox(bbox)
        sub = ExTetromino._registry.get(b)
        if sub is None:
            valid = ", ".join(f"{h}x{w}" for h, w in sorted(ExTetromino._registry))
            raise PieceSpecError(f"no extended piece has bbox {b[0]}x{b[1]}; valid: {valid}")
        return sub(holes, hand)

    @classmethod
    def variants(cls) -> tuple[tuple[tuple[int, int, int, int], Handedness], ...]:
        return tuple((p.hole_signature, p.handedness) for p in cls.all_pieces())

    def _constructor_repr(self) -> str:
        return f"{type(self).__name__}({self.hole_signature}, Handedness.{self.handedness.name})"


class ExTetromino2x3(ExTetromino):
    """Extended pieces with a 2x3 bounding box (2 pieces: one mirror pair)."""
    __slots__ = ()
    BBOX = (2, 3)


class ExTetromino2x4(ExTetromino):
    """Extended pieces with a 2x4 bounding box (9 pieces)."""
    __slots__ = ()
    BBOX = (2, 4)


class ExTetromino3x3(ExTetromino):
    """Extended pieces with a 3x3 bounding box (9 pieces)."""
    __slots__ = ()
    BBOX = (3, 3)


class ExTetromino3x4(ExTetromino):
    """Extended pieces with a 3x4 bounding box (6 pieces)."""
    __slots__ = ()
    BBOX = (3, 4)


class ExTetromino4x4(ExTetromino):
    """Extended pieces with a 4x4 bounding box (1 piece: the long diagonal)."""
    __slots__ = ()
    BBOX = (4, 4)


def _class_for(shape: ShapeInfo) -> type[Piece]:
    if shape.is_classic:
        return Tetromino
    return ExTetromino._registry[shape.bbox]


def _restore(module: str, qualname: str, code: str, turn: int) -> Piece:
    """Unpickling helper: rebuild via the catalogue, keeping a designer subclass if importable."""
    import importlib
    shape = _catalogue().by_code[code]
    cls: type[Piece] = _class_for(shape)
    try:
        candidate = importlib.import_module(module)
        for part in qualname.split("."):
            candidate = getattr(candidate, part)
        if isinstance(candidate, type) and issubclass(candidate, cls):
            cls = candidate
    except (ImportError, AttributeError):
        pass
    return cls._make(shape, turn)

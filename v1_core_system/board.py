"""
board.py -- immutable game board (v1 core, layer 1).

A Board is a frozen set of filled (row, col) cells plus its size. Every operation
returns a new Board.

Bounds are checked explicitly before any lookup. Python's negative indices are never
used, so pieces can't slip through the left wall (v0 BUG-01). With `wrap=True` the
left and right walls are joined: columns are taken modulo the width. The floor and
ceiling are always solid.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from piece import Piece

__all__ = ["Board", "GRAVITY_MODES"]

Cell = tuple[int, int]
GRAVITY_MODES = ("naive_drop", "cascade")
_EDGE = ((-1, 0), (1, 0), (0, -1), (0, 1))


@dataclass(frozen=True, slots=True)
class Board:
    width: int = 10
    height: int = 20
    filled: frozenset[Cell] = frozenset()

    def __post_init__(self) -> None:
        if not (4 <= self.width <= 64 and 4 <= self.height <= 128):
            raise ValueError("board must be 4..64 columns wide and 4..128 rows high")
        object.__setattr__(self, "filled", frozenset(self.filled))
        bad = [c for c in self.filled if not (0 <= c[0] < self.height and 0 <= c[1] < self.width)]
        if bad:
            raise ValueError(f"cells outside the board: {bad[:3]}")

    # -- geometry ---------------------------------------------------------------------
    def cells_of(self, piece: Piece, pos: tuple[int, int], wrap: bool = False) -> list[Cell]:
        """Absolute board cells of `piece` anchored (top-left) at pos; may be out of bounds."""
        r0, c0 = pos
        return [(r0 + r, (c0 + c) % self.width if wrap else c0 + c) for r, c in piece.cells]

    def fits(self, piece: Piece, pos: tuple[int, int], wrap: bool = False) -> bool:
        for r, c in self.cells_of(piece, pos, wrap):
            if not (0 <= r < self.height and 0 <= c < self.width) or (r, c) in self.filled:
                return False
        return True

    def collides(self, piece: Piece, pos: tuple[int, int], wrap: bool = False) -> bool:
        return not self.fits(piece, pos, wrap)

    def place(self, piece: Piece, pos: tuple[int, int], wrap: bool = False) -> "Board":
        if not self.fits(piece, pos, wrap):
            raise ValueError("cannot place a piece where it collides")
        return Board(self.width, self.height, self.filled | frozenset(self.cells_of(piece, pos, wrap)))

    def drop_distance(self, piece: Piece, pos: tuple[int, int], wrap: bool = False) -> int:
        d = 0
        while self.fits(piece, (pos[0] + d + 1, pos[1]), wrap):
            d += 1
        return d

    # -- rows -------------------------------------------------------------------------------
    def full_rows(self) -> tuple[int, ...]:
        counts = Counter(r for r, _ in self.filled)
        return tuple(sorted(r for r, n in counts.items() if n == self.width))

    def clear_rows(self, gravity: str = "naive_drop") -> tuple["Board", int, int]:
        """Clear full rows. Returns (new board, lines cleared, chain steps).

        naive_drop  rows above a cleared row move down by the number of cleared rows below them
        cascade     after clearing, every edge-connected group of blocks falls as far as it can;
                    repeat while new full rows appear (each repeat is one chain step)
        """
        if gravity not in GRAVITY_MODES:
            raise ValueError(f"gravity must be one of {GRAVITY_MODES}")
        board, lines, chains = self, 0, 0
        while True:
            full = set(board.full_rows())
            if not full:
                return board, lines, chains
            lines += len(full)
            chains += 1
            if gravity == "naive_drop":
                cells = {(r + sum(1 for f in full if f > r), c) for r, c in board.filled if r not in full}
                return Board(board.width, board.height, frozenset(cells)), lines, chains
            remaining = {cell for cell in board.filled if cell[0] not in full}
            board = Board(board.width, board.height, frozenset(_settle(remaining, board.height)))

    def max_height(self) -> int:
        return self.height - min((r for r, _ in self.filled), default=self.height)

    def __str__(self) -> str:
        return "\n".join("".join("#" if (r, c) in self.filled else "." for c in range(self.width))
                         for r in range(self.height))

    def to_json(self) -> dict:
        return {"width": self.width, "height": self.height, "filled": sorted(map(list, self.filled))}

    @classmethod
    def from_json(cls, data: dict) -> "Board":
        return cls(int(data["width"]), int(data["height"]), frozenset(tuple(c) for c in data["filled"]))


def _settle(cells: set[Cell], height: int) -> set[Cell]:
    """Let edge-connected groups fall until nothing moves (sticky cascade gravity)."""
    cells = set(cells)
    moved = True
    while moved:
        moved = False
        groups, todo = [], set(cells)
        while todo:
            stack, group = [todo.pop()], set()
            while stack:
                cell = stack.pop()
                group.add(cell)
                for dr, dc in _EDGE:
                    q = (cell[0] + dr, cell[1] + dc)
                    if q in todo:
                        todo.remove(q)
                        stack.append(q)
            groups.append(group)
        for group in sorted(groups, key=lambda g: -max(r for r, _ in g)):   # lowest groups first
            cells -= group
            d = 0
            while all(r + d + 1 < height and (r + d + 1, c) not in cells for r, c in group):
                d += 1
            cells |= {(r + d, c) for r, c in group}
            moved = moved or d > 0
    return cells

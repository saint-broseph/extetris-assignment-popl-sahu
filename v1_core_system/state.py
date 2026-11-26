"""
state.py -- rules, policies and immutable game state (v1 core, layers 2-3).

    Rules        board size, walls (solid | wrap), rotation, kicks, gravity
                 (naive_drop | cascade), spawn cursor, game-over rule, hard-drop locking
    Scoring      points for clears, chains and drops
    LevelPolicy  level from TOTAL lines (threshold crossing) and
                 gravity_ms = base_ms * factor ** level, clamped
    GameState    frozen snapshot of one moment of a game (JSON round-trip)
    Mode, Action, Event

No tkinter, no clock, no I/O.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field, fields, replace
from typing import Any, Mapping

from board import GRAVITY_MODES, Board
from piece import Piece

__all__ = ["Mode", "Action", "Event", "Rules", "Scoring", "LevelPolicy", "GameState", "ConfigError"]


class ConfigError(ValueError):
    """Invalid configuration value (message names the offending key)."""


class Mode(enum.Enum):
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    GAME_OVER = "GAME_OVER"


class Action(enum.Enum):
    MOVE_LEFT = "MOVE_LEFT"
    MOVE_RIGHT = "MOVE_RIGHT"
    SOFT_DROP = "SOFT_DROP"
    HARD_DROP = "HARD_DROP"
    ROTATE_CW = "ROTATE_CW"
    ROTATE_CCW = "ROTATE_CCW"
    PAUSE = "PAUSE"
    RESET = "RESET"


@dataclass(frozen=True)
class Event:
    """Something that happened, e.g. Event('LinesCleared', {'lines': 2, 'chains': 1})."""
    kind: str
    data: Mapping[str, Any] = field(default_factory=dict)


def _from_dict(cls, data: Mapping, section: str):
    names = {f.name for f in fields(cls)}
    extra = set(data) - names
    if extra:
        raise ConfigError(f"[{section}] unknown keys {sorted(extra)}; valid: {sorted(names)}")
    try:
        return cls(**dict(data))
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"[{section}] {exc}") from None


@dataclass(frozen=True)
class Rules:
    width: int = 10
    height: int = 20
    walls: str = "solid"                 # solid | wrap
    rotation: str = "both"               # both | cw_only | none
    kicks: bool = True                   # try column offsets 0, -1, +1, -2, +2 when rotating
    gravity: str = "naive_drop"          # naive_drop | cascade
    spawn_row: int = 0
    spawn_col: int | str = "center"      # "center" or a column index
    game_over: str = "block_out"         # block_out (spawn collides) | top_rows (block locked in danger zone)
    danger_rows: int = 2
    hard_drop_locks: bool = True
    preview: int = 3                     # number of next pieces shown / queued

    def __post_init__(self):
        checks = [
            (4 <= self.width <= 64, "width must be 4..64"),
            (4 <= self.height <= 128, "height must be 4..128"),
            (self.walls in ("solid", "wrap"), "walls must be 'solid' or 'wrap'"),
            (self.rotation in ("both", "cw_only", "none"), "rotation must be 'both', 'cw_only' or 'none'"),
            (self.gravity in GRAVITY_MODES, f"gravity must be one of {GRAVITY_MODES}"),
            (self.game_over in ("block_out", "top_rows"), "game_over must be 'block_out' or 'top_rows'"),
            (0 <= self.spawn_row < self.height - 4, "spawn_row out of range"),
            (self.spawn_col == "center" or (isinstance(self.spawn_col, int) and 0 <= self.spawn_col < self.width),
             "spawn_col must be 'center' or a column index"),
            (0 <= self.danger_rows < self.height, "danger_rows out of range"),
            (1 <= self.preview <= 6, "preview must be 1..6"),
            (isinstance(self.kicks, bool) and isinstance(self.hard_drop_locks, bool), "kicks/hard_drop_locks must be booleans"),
        ]
        for ok, msg in checks:
            if not ok:
                raise ValueError(msg)

    @classmethod
    def from_dict(cls, data: Mapping) -> "Rules":
        return _from_dict(cls, data, "rules")

    @property
    def wrap(self) -> bool:
        return self.walls == "wrap"

    def spawn_position(self, piece: Piece) -> tuple[int, int]:
        col = (self.width - piece.width) // 2 if self.spawn_col == "center" else self.spawn_col
        if not self.wrap:
            col = max(0, min(col, self.width - piece.width))
        return self.spawn_row, col

    def kick_offsets(self) -> tuple[int, ...]:
        return (0, -1, 1, -2, 2) if self.kicks else (0,)


@dataclass(frozen=True)
class Scoring:
    line_points: tuple[int, ...] = (0, 100, 300, 500, 800)
    extra_line_points: int = 300          # per line beyond the table (cascades can clear more than 4)
    chain_bonus: int = 50                 # per chain step after the first
    soft_drop: int = 1                    # per cell
    hard_drop: int = 2                    # per cell
    level_multiplier: bool = True         # multiply clears by (level + 1)

    def __post_init__(self):
        object.__setattr__(self, "line_points", tuple(int(x) for x in self.line_points))
        if len(self.line_points) < 2 or any(x < 0 for x in self.line_points):
            raise ValueError("line_points needs >= 2 non-negative entries")

    @classmethod
    def from_dict(cls, data: Mapping) -> "Scoring":
        return _from_dict(cls, data, "scoring")

    def for_clear(self, lines: int, chains: int, level: int) -> int:
        if lines <= 0:
            return 0
        table = self.line_points
        base = table[lines] if lines < len(table) else table[-1] + (lines - len(table) + 1) * self.extra_line_points
        base += self.chain_bonus * max(0, chains - 1)
        return base * (level + 1 if self.level_multiplier else 1)


@dataclass(frozen=True)
class LevelPolicy:
    base_ms: float = 1000.0
    factor: float = 0.9
    lines_per_level: int = 10
    min_ms: int = 50
    start_level: int = 0
    max_level: int = 99

    def __post_init__(self):
        if not (self.base_ms > 0 and 0 < self.factor <= 1 and self.lines_per_level >= 1
                and 1 <= self.min_ms <= self.base_ms and 0 <= self.start_level <= self.max_level):
            raise ValueError("invalid level policy values")

    @classmethod
    def from_dict(cls, data: Mapping) -> "LevelPolicy":
        return _from_dict(cls, data, "level")

    def level_for(self, total_lines: int) -> int:
        """Computed from the total, so a multi-line clear can never skip a threshold (v0 BUG-06)."""
        return min(self.max_level, self.start_level + total_lines // self.lines_per_level)

    def gravity_ms(self, level: int) -> int:
        """1000 * 0.9 ** level by default, never below min_ms (v0 BUG-07)."""
        return max(self.min_ms, round(self.base_ms * self.factor ** level))


def _piece_json(p: Piece | None):
    return None if p is None else [p.code, p.turn]


def _piece_from(data) -> Piece | None:
    return None if data is None else Piece.from_code(data[0]).with_turn(int(data[1]))


@dataclass(frozen=True)
class GameState:
    """Immutable snapshot. The engine replaces it; nobody mutates it."""
    board: Board
    active: Piece | None
    pos: tuple[int, int]
    queue: tuple[Piece, ...]
    mode: Mode = Mode.READY
    score: int = 0
    lines: int = 0
    level: int = 0
    gravity_acc: float = 0.0
    tick: int = 0
    pieces_spawned: int = 0
    draws: int = 0
    history: tuple[str, ...] = ()
    fired_triggers: frozenset[str] = frozenset()
    last_clear: int = 0
    max_chain: int = 0

    def with_(self, **changes) -> "GameState":
        return replace(self, **changes)

    def to_json(self) -> dict:
        return {
            "board": self.board.to_json(), "active": _piece_json(self.active), "pos": list(self.pos),
            "queue": [_piece_json(p) for p in self.queue], "mode": self.mode.value, "score": self.score,
            "lines": self.lines, "level": self.level, "gravity_acc": self.gravity_acc, "tick": self.tick,
            "pieces_spawned": self.pieces_spawned, "draws": self.draws, "history": list(self.history),
            "fired_triggers": sorted(self.fired_triggers), "last_clear": self.last_clear,
            "max_chain": self.max_chain,
        }

    @classmethod
    def from_json(cls, d: Mapping) -> "GameState":
        return cls(
            board=Board.from_json(d["board"]), active=_piece_from(d["active"]), pos=tuple(d["pos"]),
            queue=tuple(_piece_from(q) for q in d["queue"]), mode=Mode(d["mode"]), score=int(d["score"]),
            lines=int(d["lines"]), level=int(d["level"]), gravity_acc=float(d["gravity_acc"]),
            tick=int(d["tick"]), pieces_spawned=int(d["pieces_spawned"]), draws=int(d["draws"]),
            history=tuple(d["history"]), fired_triggers=frozenset(d["fired_triggers"]),
            last_clear=int(d["last_clear"]), max_chain=int(d["max_chain"]),
        )

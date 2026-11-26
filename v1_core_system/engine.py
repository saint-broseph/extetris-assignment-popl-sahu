"""
engine.py -- the headless ExTetris engine (v1 core, layer 3).

Pure Python: no tkinter, no timers, no threads, no file I/O.
  * Time enters only through tick(elapsed_ms).
  * Input enters only through apply_action(action).
  * Both return a list of Events, and the current GameState is an immutable snapshot.

Configuration is layered; later layers override earlier ones:

    DEFAULTS  ->  spec (the game variant)  ->  player (preferences)  ->  runtime (live changes)

  * spec      Any known key. Defines the variant; its SHA-256 is the variant hash.
  * player    Only PLAYER_KEYS, e.g. UI settings, preview size, start level.
  * runtime   Only RUNTIME_KEYS. Changes are requested with request_update() and applied at
              the next tick boundary, never in the middle of a move.

Triggers are restricted, data-only rules. No eval: conditions come from a fixed
whitelist, and actions may only set RUNTIME_KEYS. Each trigger fires once:

    {"id": "wrap-at-20", "when": {"lines_at_least": 20}, "set": {"rules.walls": "wrap"}}

Save and resume use JSON. The file stores the variant hash and a SHA-256 checksum of
its own payload. Resuming against a different variant, or from an edited file, is
refused.
"""
from __future__ import annotations

import copy
import hashlib
import json
import random
import secrets
from pathlib import Path
from typing import Any, Mapping

from board import Board
from distribution import Distribution, distribution_from_spec
from family import PieceFamily
from piece import Piece, PieceSpecError
from state import Action, ConfigError, Event, GameState, LevelPolicy, Mode, Rules, Scoring

__all__ = ["Engine", "DEFAULTS", "PLAYER_KEYS", "RUNTIME_KEYS", "TRIGGER_CONDITIONS",
           "SaveError", "VariantMismatchError", "load_spec", "variant_hash"]

SAVE_FORMAT = "extetris-save/1"
HISTORY_CAP = 256

DEFAULTS: dict[str, Any] = {
    "variant": {"name": "Classic", "version": "1.0", "authors": []},
    "rules": {f: getattr(Rules(), f) for f in Rules.__dataclass_fields__},
    "scoring": {"line_points": [0, 100, 300, 500, 800], "extra_line_points": 300, "chain_bonus": 50,
                "soft_drop": 1, "hard_drop": 2, "level_multiplier": True},
    "level": {f: getattr(LevelPolicy(), f) for f in LevelPolicy.__dataclass_fields__},
    "pieces": {"preset": "Classic"},
    "distribution": {"kind": "uniform"},
    "triggers": [],
    "ui": {"cell_px": 28, "theme": "dark", "show_ghost": True,
           "keys": {"move_left": "Left", "move_right": "Right", "rotate_cw": "Up", "rotate_ccw": "z",
                    "soft_drop": "Down", "hard_drop": "space", "pause": "p"}},
}
PLAYER_KEYS = ("ui", "rules.preview", "level.start_level")
RUNTIME_KEYS = ("rules.walls", "rules.rotation", "rules.kicks", "rules.gravity", "rules.game_over",
                "rules.danger_rows", "rules.hard_drop_locks", "rules.preview", "level.base_ms",
                "level.factor", "level.lines_per_level", "level.min_ms", "scoring", "pieces",
                "distribution", "ui")
TRIGGER_CONDITIONS = ("lines_at_least", "level_at_least", "score_at_least", "pieces_at_least", "tick_at_least")


class SaveError(ValueError):
    """The save file is malformed or was modified."""


class VariantMismatchError(SaveError):
    """The save file belongs to a different variant (hash mismatch)."""


# ----------------------------------------------------------------------------
# Config helpers
# ----------------------------------------------------------------------------
def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=list)


def _sha256(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def _allowed(path: str, allowed: tuple[str, ...]) -> bool:
    return any(path == a or path.startswith(a + ".") for a in allowed)


def _set_path(d: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    for p in parts[:-1]:
        d = d.setdefault(p, {})
    d[parts[-1]] = copy.deepcopy(value)


def _merge(base: dict, over: Mapping) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if k in ("pieces", "distribution", "triggers"):          # replaced as a whole
            out[k] = copy.deepcopy(v)
        elif isinstance(v, Mapping) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _check_known(layer: Mapping, name: str) -> None:
    for section, value in layer.items():
        if section not in DEFAULTS:
            raise ConfigError(f"{name}: unknown section [{section}]; valid: {sorted(DEFAULTS)}")
        if section in ("rules", "level", "variant") and isinstance(value, Mapping):
            extra = set(value) - set(DEFAULTS[section])
            if extra:
                raise ConfigError(f"{name}: [{section}] unknown keys {sorted(extra)}")


def _flatten_layer(layer: Mapping) -> list[str]:
    paths = []
    for section, value in layer.items():
        if isinstance(value, Mapping) and section in ("rules", "level", "variant"):
            paths += [f"{section}.{k}" for k in value]
        else:
            paths.append(section)
    return paths


def variant_hash(spec: Mapping | None) -> str:
    """SHA-256 of the effective variant (defaults merged with spec)."""
    return _sha256(_merge(DEFAULTS, spec or {}))


def load_spec(path: str | Path) -> dict:
    """Read a variant file (.toml via tomllib, or .json)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".toml":
        import tomllib
        return tomllib.loads(text)
    return json.loads(text)


def _rng_to_json(rng: random.Random) -> list:
    version, internal, gauss = rng.getstate()
    return [version, list(internal), gauss]


def _rng_from_json(data: list) -> random.Random:
    rng = random.Random()
    rng.setstate((data[0], tuple(data[1]), data[2]))
    return rng


# ----------------------------------------------------------------------------
class Engine:
    """Headless, deterministic game engine.

    >>> e = Engine({"pieces": {"preset": "Full"}}, seed=7)
    >>> events = e.apply_action(Action.HARD_DROP)
    >>> events = e.tick(1000)
    """

    def __init__(self, spec: Mapping | None = None, *, player: Mapping | None = None,
                 seed: int | None = None) -> None:
        self._spec = copy.deepcopy(dict(spec or {}))
        self._player = copy.deepcopy(dict(player or {}))
        self._runtime: dict = {}
        self._pending: list[tuple[str, Any]] = []
        _check_known(self._spec, "spec")
        _check_known(self._player, "player")
        for p in _flatten_layer(self._player):
            if not _allowed(p, PLAYER_KEYS):
                raise ConfigError(f"player layer may not set '{p}'; allowed: {PLAYER_KEYS}")
        self.variant_hash = variant_hash(self._spec)
        self._build()
        self._validate_triggers()
        self.reset(seed)

    # -- configuration ------------------------------------------------------------------
    def _effective(self, runtime: Mapping | None = None) -> dict:
        cfg = _merge(DEFAULTS, self._spec)
        cfg = _merge(cfg, self._player)
        return _merge(cfg, self._runtime if runtime is None else runtime)

    def _components(self, cfg: Mapping):
        try:
            rules = Rules.from_dict(cfg["rules"])
            scoring = Scoring.from_dict(cfg["scoring"])
            level = LevelPolicy.from_dict(cfg["level"])
            family = PieceFamily.from_spec(cfg["pieces"])
            dist = distribution_from_spec(cfg["distribution"], family)
            dist.probabilities()                     # fails early if every weight is zero
        except PieceSpecError as exc:
            raise ConfigError(str(exc)) from None
        return rules, scoring, level, family, dist

    def _build(self) -> None:
        cfg = self._effective()
        self.rules, self.scoring, self.level_policy, self.family, self.distribution = self._components(cfg)
        self._config = cfg

    @property
    def config(self) -> dict:
        """Effective configuration (a copy; edit layers, not this)."""
        return copy.deepcopy(self._config)

    def _validate_triggers(self) -> None:
        seen = set()
        for t in self._config["triggers"]:
            if not isinstance(t, Mapping) or set(t) - {"id", "when", "set"} or "id" not in t:
                raise ConfigError(f"trigger must be {{id, when, set}}: {t!r}")
            if t["id"] in seen:
                raise ConfigError(f"duplicate trigger id {t['id']!r}")
            seen.add(t["id"])
            for cond, val in t.get("when", {}).items():
                if cond not in TRIGGER_CONDITIONS or not isinstance(val, int):
                    raise ConfigError(f"trigger {t['id']!r}: condition must be one of {TRIGGER_CONDITIONS} with an int")
            for path in t.get("set", {}):
                if not _allowed(path, RUNTIME_KEYS):
                    raise ConfigError(f"trigger {t['id']!r} may not set '{path}'; allowed: {RUNTIME_KEYS}")
            trial = copy.deepcopy(self._runtime)
            for path, value in t.get("set", {}).items():
                _set_path(trial, path, value)
            self._components(self._effective(trial))     # the trigger's result must be a valid config

    def request_update(self, path: str, value: Any) -> None:
        """Queue a runtime change; it is validated now and applied at the next tick boundary."""
        if not _allowed(path, RUNTIME_KEYS):
            raise ConfigError(f"'{path}' cannot change during a game; allowed: {RUNTIME_KEYS}")
        trial = copy.deepcopy(self._runtime)
        for p, v in self._pending:
            _set_path(trial, p, v)
        _set_path(trial, path, value)
        self._components(self._effective(trial))
        self._pending.append((path, copy.deepcopy(value)))

    def _apply_updates(self, updates: list[tuple[str, Any]]) -> list[Event]:
        if not updates:
            return []
        for path, value in updates:
            _set_path(self._runtime, path, value)
        self._build()
        return [Event("ConfigChanged", {"paths": [p for p, _ in updates]})]

    # -- lifecycle ----------------------------------------------------------------------------
    def reset(self, seed: int | None = None) -> list[Event]:
        """Start a new game (a new seed is derived deterministically if none is given)."""
        if seed is None:
            seed = self._rng.randrange(2 ** 63) if hasattr(self, "_rng") else secrets.randbits(63)
        self.seed = int(seed)
        self._rng = random.Random(self.seed)
        start_level = self.level_policy.start_level
        state = GameState(board=Board(self.rules.width, self.rules.height), active=None, pos=(0, 0),
                          queue=(), mode=Mode.RUNNING, level=start_level)
        for _ in range(self.rules.preview):
            state = self._draw_into_queue(state)
        self.state, events = self._spawn(state)
        return [Event("Reset", {"seed": self.seed})] + events

    def _draw_into_queue(self, s: GameState) -> GameState:
        piece = self.distribution.draw(self._rng, s.history, s.draws)
        return s.with_(queue=s.queue + (piece,), draws=s.draws + 1,
                       history=(s.history + (piece.code,))[-HISTORY_CAP:])

    def _spawn(self, s: GameState) -> tuple[GameState, list[Event]]:
        while len(s.queue) < self.rules.preview + 1:
            s = self._draw_into_queue(s)
        piece, queue = s.queue[0], s.queue[1:]
        pos = self.rules.spawn_position(piece)
        s = s.with_(active=piece, pos=pos, queue=queue, pieces_spawned=s.pieces_spawned + 1, gravity_acc=0.0)
        if not s.board.fits(piece, pos, self.rules.wrap):
            return s.with_(mode=Mode.GAME_OVER), [Event("Spawned", {"piece": piece.code}),
                                                  Event("GameOver", {"reason": "block_out", "score": s.score})]
        return s, [Event("Spawned", {"piece": piece.code})]

    # -- time -------------------------------------------------------------------------------------
    def tick(self, elapsed_ms: float) -> list[Event]:
        """Advance time. Tick boundary: pending updates and triggers are applied here."""
        if elapsed_ms < 0:
            raise ValueError("elapsed_ms must be >= 0")
        pending, self._pending = self._pending, []
        events = self._apply_updates(pending)
        s = self.state
        if s.mode is not Mode.RUNNING:
            return events
        acc, steps = s.gravity_acc + elapsed_ms, 0
        s = s.with_(tick=s.tick + 1)
        while s.mode is Mode.RUNNING and acc >= self.level_policy.gravity_ms(s.level) and steps < 10_000:
            acc -= self.level_policy.gravity_ms(s.level)
            steps += 1
            s, ev = self._step_down(s, locks=True)
            events += ev
        self.state = s.with_(gravity_acc=acc if s.mode is Mode.RUNNING else 0.0)
        events += self._run_triggers()
        return events

    def _run_triggers(self) -> list[Event]:
        s, events, updates = self.state, [], []
        values = {"lines_at_least": s.lines, "level_at_least": s.level, "score_at_least": s.score,
                  "pieces_at_least": s.pieces_spawned, "tick_at_least": s.tick}
        fired = set(s.fired_triggers)
        for t in self._config["triggers"]:
            if t["id"] in fired:
                continue
            if all(values[c] >= v for c, v in t.get("when", {}).items()):
                fired.add(t["id"])
                updates += list(t.get("set", {}).items())
                events.append(Event("TriggerFired", {"id": t["id"]}))
        if events:
            self.state = s.with_(fired_triggers=frozenset(fired))
            events += self._apply_updates(updates)
        return events

    # -- input ------------------------------------------------------------------------------------
    def apply_action(self, action: Action | str) -> list[Event]:
        action = Action(action) if not isinstance(action, Action) else action
        s = self.state
        if action is Action.RESET:
            return self.reset()
        if action is Action.PAUSE:
            if s.mode is Mode.RUNNING:
                self.state = s.with_(mode=Mode.PAUSED)
                return [Event("Paused")]
            if s.mode is Mode.PAUSED:
                self.state = s.with_(mode=Mode.RUNNING)
                return [Event("Resumed")]
            return []
        if s.mode is not Mode.RUNNING:
            return []                                          # paused / game over: ignore input
        wrap = self.rules.wrap
        if action in (Action.MOVE_LEFT, Action.MOVE_RIGHT):
            dc = -1 if action is Action.MOVE_LEFT else 1
            col = s.pos[1] + dc
            if wrap:
                col %= self.rules.width
            if s.board.fits(s.active, (s.pos[0], col), wrap):
                self.state = s.with_(pos=(s.pos[0], col))
                return [Event("Moved", {"pos": (s.pos[0], col)})]
            return []
        if action is Action.SOFT_DROP:
            s2, events = self._step_down(s, locks=True)
            if events and events[0].kind == "Moved":
                s2 = s2.with_(score=s2.score + self.scoring.soft_drop, gravity_acc=0.0)
            self.state = s2
            return events
        if action is Action.HARD_DROP:
            d = s.board.drop_distance(s.active, s.pos, wrap)
            s = s.with_(pos=(s.pos[0] + d, s.pos[1]), score=s.score + d * self.scoring.hard_drop)
            events = [Event("Dropped", {"rows": d})]
            if self.rules.hard_drop_locks:
                s, more = self._lock(s)
                events += more
            self.state = s
            return events
        if action in (Action.ROTATE_CW, Action.ROTATE_CCW):
            if self.rules.rotation == "none" or (self.rules.rotation == "cw_only" and action is Action.ROTATE_CCW):
                return []
            turned = s.active.turned(1 if action is Action.ROTATE_CW else -1)
            for dc in self.rules.kick_offsets():
                col = s.pos[1] + dc
                if wrap:
                    col %= self.rules.width
                if s.board.fits(turned, (s.pos[0], col), wrap):
                    self.state = s.with_(active=turned, pos=(s.pos[0], col))
                    return [Event("Rotated", {"turn": turned.turn, "kick": dc})]
            return []
        raise ValueError(f"unhandled action {action}")

    # -- mechanics ---------------------------------------------------------------------------------
    def _step_down(self, s: GameState, locks: bool) -> tuple[GameState, list[Event]]:
        below = (s.pos[0] + 1, s.pos[1])
        if s.board.fits(s.active, below, self.rules.wrap):
            return s.with_(pos=below), [Event("Moved", {"pos": below})]
        return self._lock(s) if locks else (s, [])

    def _lock(self, s: GameState) -> tuple[GameState, list[Event]]:
        board = s.board.place(s.active, s.pos, self.rules.wrap)
        events = [Event("Locked", {"piece": s.active.code, "pos": s.pos})]
        board, lines, chains = board.clear_rows(self.rules.gravity)
        score, total = s.score, s.lines + lines
        if lines:
            score += self.scoring.for_clear(lines, chains, s.level)
            events.append(Event("LinesCleared", {"lines": lines, "chains": chains}))
        level = max(s.level, self.level_policy.level_for(total))
        if level != s.level:
            events.append(Event("LevelChanged", {"level": level, "gravity_ms": self.level_policy.gravity_ms(level)}))
        s = s.with_(board=board, score=score, lines=total, level=level, last_clear=lines,
                    max_chain=max(s.max_chain, chains), active=None)
        if self.rules.game_over == "top_rows" and any(r < self.rules.danger_rows for r, _ in board.filled):
            return s.with_(mode=Mode.GAME_OVER), events + [Event("GameOver", {"reason": "top_rows", "score": score})]
        s, more = self._spawn(s)
        return s, events + more

    # -- views for renderers --------------------------------------------------------------------
    def active_cells(self) -> list[tuple[int, int]]:
        s = self.state
        return [] if s.active is None else s.board.cells_of(s.active, s.pos, self.rules.wrap)

    def ghost_cells(self) -> list[tuple[int, int]]:
        s = self.state
        if s.active is None or s.mode is Mode.GAME_OVER:
            return []
        d = s.board.drop_distance(s.active, s.pos, self.rules.wrap)
        return s.board.cells_of(s.active, (s.pos[0] + d, s.pos[1]), self.rules.wrap)

    # -- save / resume -------------------------------------------------------------------------
    def save(self) -> str:
        body = {"format": SAVE_FORMAT, "variant_hash": self.variant_hash,
                "variant_name": self._config["variant"].get("name", ""), "seed": self.seed,
                "player": self._player, "runtime": self._runtime,
                "pending": [[p, v] for p, v in self._pending],
                "state": self.state.to_json(), "rng": _rng_to_json(self._rng)}
        body["payload_sha256"] = _sha256(body)
        return json.dumps(body, indent=1, sort_keys=True)

    @classmethod
    def resume(cls, text: str, spec: Mapping | None, *, player: Mapping | None = None) -> "Engine":
        """Rebuild an engine from save(). `spec` must be the variant the game was played with."""
        try:
            body = json.loads(text)
            claimed = body.pop("payload_sha256")
        except (ValueError, KeyError, AttributeError) as exc:
            raise SaveError(f"not an ExTetris save file: {exc}") from None
        if body.get("format") != SAVE_FORMAT:
            raise SaveError(f"unsupported save format {body.get('format')!r}")
        if _sha256(body) != claimed:
            raise SaveError("save file checksum mismatch: the file was modified")
        if variant_hash(spec) != body["variant_hash"]:
            raise VariantMismatchError(
                f"save belongs to variant {body.get('variant_name')!r} with a different hash; "
                "load it with the same variant spec")
        eng = cls(spec, player=player if player is not None else body["player"], seed=body["seed"])
        eng._runtime = body["runtime"]
        eng._build()
        eng._pending = [(p, v) for p, v in body["pending"]]
        eng.state = GameState.from_json(body["state"])
        eng._rng = _rng_from_json(body["rng"])
        return eng

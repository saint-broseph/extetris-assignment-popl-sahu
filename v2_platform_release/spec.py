"""
spec.py -- VariantSpec: a game designer's .toml file, validated in plain English.

    from spec import VariantSpec, SpecError
    spec = VariantSpec.from_toml("variants/corner_chaos.toml")   # raises SpecError with every problem
    engine = spec.build_engine(seed=1)

TOML layout (every section is optional; missing values use the defaults)

    [variant]       name, version, authors, description
    [board]         width, height, walls = "solid" | "wrap"
    [pieces]        preset, include, exclude, bbox, connectivity, handedness, max_holes
    [distribution]  kind = uniform | weighted | by_property | bag | adaptive | mixture, seed, ...
    [levels]        start_level, lines_per_level, base_ms, factor, min_ms
    [scoring]       line_points, soft_drop, hard_drop, chain_bonus
    [physics]       gravity, rotation, kicks, hard_drop_locks, spawn_column, game_over, danger_rows, preview
    [theme]         name, cell_px, show_ghost, colors = { block = "#..", ... }
    [controls]      move_left, move_right, rotate_cw, rotate_ccw, soft_drop, hard_drop, pause
    [[triggers]]    id, when = { lines_at_least = 20 }, set = { "board.walls" = "wrap" }

The validator never runs designer text as code: triggers use a fixed list of
conditions, and may only change a fixed list of settings.
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

_HERE = Path(__file__).resolve().parent
CORE = next((d for d in (_HERE, _HERE.parent / "v1_core_system") if (d / "engine.py").is_file()),
            _HERE.parent / "v1_core_system")
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from engine import Engine, PLAYER_KEYS  # noqa: E402,F401
from family import PRESETS, PieceFamily, piece_by_id  # noqa: E402
from distribution import PROPERTY_RULES  # noqa: E402
from piece import PieceSpecError  # noqa: E402
from state import ConfigError  # noqa: E402

__all__ = ["VariantSpec", "SpecValidator", "SpecError", "dump_toml", "THEME_NAMES", "TRIGGER_TARGETS"]

THEME_NAMES = ("dark", "light", "retro")
COLOR_KEYS = ("bg", "grid", "block", "active", "ghost", "text", "overlay")
CONDITIONS = {"lines_at_least": "total lines cleared", "level_at_least": "current level",
              "score_at_least": "score", "pieces_at_least": "pieces played", "tick_at_least": "engine ticks"}
# Settings a trigger (or the in-game customizer) may change, in designer words -> engine path.
TRIGGER_TARGETS = {
    "board.walls": "rules.walls",
    "physics.gravity": "rules.gravity", "physics.rotation": "rules.rotation", "physics.kicks": "rules.kicks",
    "physics.hard_drop_locks": "rules.hard_drop_locks", "physics.preview": "rules.preview",
    "physics.game_over": "rules.game_over", "physics.danger_rows": "rules.danger_rows",
    "levels.base_ms": "level.base_ms", "levels.factor": "level.factor",
    "levels.lines_per_level": "level.lines_per_level", "levels.min_ms": "level.min_ms",
}


class SpecError(ValueError):
    """Raised with every validation problem; str() is a readable bullet list."""

    def __init__(self, errors: list[str], source: str = "variant"):
        self.errors = errors
        super().__init__(f"{source} has {len(errors)} problem(s):\n" + "\n".join(f"  - {e}" for e in errors))


# ----------------------------------------------------------------------------
# Field checkers: each returns an error message (str) or None
# ----------------------------------------------------------------------------
def _int(lo, hi):
    def check(v):
        if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
            return f"must be a whole number from {lo} to {hi} (you wrote {v!r})"
    return check


def _num(lo, hi):
    def check(v):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
            return f"must be a number from {lo} to {hi} (you wrote {v!r})"
    return check


def _choice(*options):
    def check(v):
        if v not in options:
            return f"must be one of {', '.join(repr(o) for o in options)} (you wrote {v!r})"
    return check


def _bool(v):
    if not isinstance(v, bool):
        return f"must be true or false (you wrote {v!r})"


def _text(v):
    if not isinstance(v, str) or not v.strip():
        return f"must be some text in quotes (you wrote {v!r})"


def _text_list(v):
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        return f"must be a list of texts, like [\"a\", \"b\"] (you wrote {v!r})"


def _piece_ids(v):
    if _text_list(v):
        return _text_list(v)
    bad = []
    for x in v:
        try:
            piece_by_id(x)
        except PieceSpecError:
            bad.append(x)
    if bad:
        return (f"contains unknown piece names {bad}. Use a classic letter (I O T S Z L J) or a code "
                "such as \"X3x3.H2233.+\" (run `cli.py pieces` to list them)")


def _bboxes(v):
    items = v if isinstance(v, list) else [v]
    if not all(isinstance(x, str) and re.fullmatch(r"\s*\d+\s*[xX]\s*\d+\s*", x) for x in items):
        return f"must be a size like \"2x4\" or a list of sizes (you wrote {v!r})"


def _hand(v):
    items = v if isinstance(v, list) else [v]
    if not all(x in ("+", "-", "0", "chiral", "achiral") for x in items):
        return f"must be \"+\", \"-\", \"0\", \"chiral\" or \"achiral\" (or a list of them); you wrote {v!r}"


def _line_points(v):
    if (not isinstance(v, list) or len(v) < 2 or
            not all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in v)):
        return f"must be a list of at least 2 whole numbers, like [0, 100, 300, 500, 800] (you wrote {v!r})"


def _spawn(v):
    if v != "center" and (isinstance(v, bool) or not isinstance(v, int) or v < 0):
        return f"must be \"center\" or a column number (you wrote {v!r})"


def _colors(v):
    if not isinstance(v, dict):
        return "must be a table like { block = \"#4f8cff\" }"
    for k, c in v.items():
        if k not in COLOR_KEYS:
            return f"has unknown colour '{k}'; valid names: {', '.join(COLOR_KEYS)}"
        if not isinstance(c, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", c):
            return f"colour '{k}' must look like \"#4f8cff\" (you wrote {c!r})"


def _weights(v):
    if not isinstance(v, dict):
        return "must be a table of piece = weight, e.g. { I = 2.0, S = 0.5 }"
    for k, w in v.items():
        try:
            piece_by_id(k)
        except PieceSpecError:
            return f"names an unknown piece '{k}'"
        if isinstance(w, bool) or not isinstance(w, (int, float)) or w < 0:
            return f"weight for '{k}' must be a number 0 or more (you wrote {w!r})"


DIST_KINDS = ("uniform", "weighted", "by_property", "bag", "adaptive", "mixture")
SCHEMA: dict[str, dict[str, Callable]] = {
    "variant": {"name": _text, "version": _text, "authors": _text_list, "description": _text},
    "board": {"width": _int(4, 64), "height": _int(8, 128), "walls": _choice("solid", "wrap")},
    "pieces": {"preset": _choice(*PRESETS), "include": _piece_ids, "exclude": _piece_ids, "bbox": _bboxes,
               "connectivity": _choice("edge", "corner"), "handedness": _hand, "max_holes": _int(0, 6)},
    "distribution": {"kind": _choice(*DIST_KINDS), "seed": _int(0, 2 ** 63 - 1), "weights": _weights,
                     "default_weight": _num(0, 1e6), "rule": _choice(*PROPERTY_RULES), "strength": _num(0, 10),
                     "copies": _int(1, 7), "base": _choice("uniform", "bag", "by_property", "weighted"),
                     "drought_boost": _num(0, 20), "repeat_penalty": _num(0, 1), "parts": lambda v: None},
    "levels": {"start_level": _int(0, 99), "lines_per_level": _int(1, 1000), "base_ms": _num(20, 10_000),
               "factor": _num(0.01, 1), "min_ms": _int(1, 10_000)},
    "scoring": {"line_points": _line_points, "soft_drop": _int(0, 1000), "hard_drop": _int(0, 1000),
                "chain_bonus": _int(0, 100_000), "extra_line_points": _int(0, 100_000),
                "level_multiplier": _bool},
    "physics": {"gravity": _choice("naive_drop", "cascade"), "rotation": _choice("both", "cw_only", "none"),
                "kicks": _bool, "hard_drop_locks": _bool, "spawn_column": _spawn, "spawn_row": _int(0, 100),
                "game_over": _choice("block_out", "top_rows"), "danger_rows": _int(0, 20), "preview": _int(1, 6)},
    "theme": {"name": _choice(*THEME_NAMES), "cell_px": _int(10, 64), "show_ghost": _bool, "colors": _colors},
    "controls": {k: _text for k in ("move_left", "move_right", "rotate_cw", "rotate_ccw", "soft_drop",
                                    "hard_drop", "pause")},
}
PART_SCHEMA = {"weight": _num(0, 1e6), "kind": _choice("uniform", "weighted", "by_property", "bag"),
               "weights": _weights, "rule": _choice(*PROPERTY_RULES), "strength": _num(0, 10),
               "copies": _int(1, 7)}


def _suggest(word: str, options) -> str:
    close = difflib.get_close_matches(word, list(options), n=1)
    return f" Did you mean '{close[0]}'?" if close else f" Valid names: {', '.join(options)}."


class SpecValidator:
    """Checks raw TOML data and explains every problem in plain English."""

    def __init__(self, data: Mapping[str, Any]):
        self.data = data
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate(self) -> bool:
        for section, value in self.data.items():
            if section == "triggers":
                self._triggers(value)
                continue
            if section not in SCHEMA:
                self.errors.append(f"I don't recognise the section [{section}].{_suggest(section, list(SCHEMA) + ['triggers'])}")
                continue
            if not isinstance(value, dict):
                self.errors.append(f"[{section}] must be a section (a table), not a single value.")
                continue
            for key, v in value.items():
                checker = SCHEMA[section].get(key)
                if checker is None:
                    self.errors.append(f"In [{section}], I don't recognise '{key}'.{_suggest(key, SCHEMA[section])}")
                elif (msg := checker(v)):
                    self.errors.append(f"In [{section}], '{key}' {msg}.")
        self._cross_checks()
        if not self.errors:
            try:
                VariantSpec(dict(self.data)).build_engine(seed=0)
            except (ConfigError, PieceSpecError, ValueError) as exc:
                self.errors.append(f"The game engine rejected this combination: {exc}")
        return not self.errors

    def _cross_checks(self) -> None:
        board = self.data.get("board", {}) if isinstance(self.data.get("board"), dict) else {}
        phys = self.data.get("physics", {}) if isinstance(self.data.get("physics"), dict) else {}
        lv = self.data.get("levels", {}) if isinstance(self.data.get("levels"), dict) else {}
        dist = self.data.get("distribution", {}) if isinstance(self.data.get("distribution"), dict) else {}
        width = board.get("width", 10)
        if isinstance(phys.get("spawn_column"), int) and isinstance(width, int) and phys["spawn_column"] >= width:
            self.errors.append(f"In [physics], 'spawn_column' ({phys['spawn_column']}) must be inside the board "
                               f"(0 to {width - 1}).")
        if isinstance(lv.get("min_ms"), (int, float)) and isinstance(lv.get("base_ms", 1000), (int, float)) \
                and lv["min_ms"] > lv.get("base_ms", 1000):
            self.errors.append("In [levels], 'min_ms' (the fastest speed) cannot be slower than 'base_ms'.")
        kind = dist.get("kind", "uniform")
        needs = {"weighted": "weights", "by_property": "rule", "mixture": "parts"}
        if kind in needs and needs[kind] not in dist:
            self.errors.append(f"In [distribution], kind = \"{kind}\" also needs '{needs[kind]}'.")
        if kind == "mixture":
            parts = dist.get("parts")
            if not isinstance(parts, list) or not parts:
                self.errors.append("In [distribution], a mixture needs at least one [[distribution.parts]] entry.")
            else:
                for i, part in enumerate(parts, 1):
                    for k, v in part.items():
                        chk = PART_SCHEMA.get(k)
                        if chk is None:
                            self.errors.append(f"In mixture part {i}, I don't recognise '{k}'.{_suggest(k, PART_SCHEMA)}")
                        elif (msg := chk(v)):
                            self.errors.append(f"In mixture part {i}, '{k}' {msg}.")
        if isinstance(board.get("width"), int) and board.get("width", 10) < 6 and dist:
            self.warnings.append("A board narrower than 6 columns makes wide extended pieces very hard.")
        if isinstance(lv.get("base_ms"), (int, float)) and lv["base_ms"] < 200:
            self.warnings.append("A starting speed under 200 ms is very fast for new players.")

    def _triggers(self, triggers) -> None:
        if not isinstance(triggers, list):
            self.errors.append("Triggers must be written as [[triggers]] blocks.")
            return
        ids = set()
        for i, t in enumerate(triggers, 1):
            where = f"Trigger {i}" + (f" ('{t.get('id')}')" if isinstance(t, dict) and t.get("id") else "")
            if not isinstance(t, dict):
                self.errors.append(f"{where} must be a [[triggers]] block.")
                continue
            for k in t:
                if k not in ("id", "when", "set", "message"):
                    self.errors.append(f"{where}: I don't recognise '{k}'.{_suggest(k, ['id', 'when', 'set', 'message'])}")
            if not isinstance(t.get("id"), str) or not t.get("id"):
                self.errors.append(f"{where} needs an id, e.g. id = \"speed-bonus\".")
            elif t["id"] in ids:
                self.errors.append(f"{where}: the id '{t['id']}' is used twice.")
            else:
                ids.add(t["id"])
            when, sets = t.get("when"), t.get("set")
            if not isinstance(when, dict) or not when:
                self.errors.append(f"{where} needs a condition, e.g. when = {{ lines_at_least = 20 }}.")
            else:
                for c, v in when.items():
                    if c not in CONDITIONS:
                        self.errors.append(f"{where}: '{c}' is not a condition I can check.{_suggest(c, CONDITIONS)}")
                    elif isinstance(v, bool) or not isinstance(v, int) or v < 0:
                        self.errors.append(f"{where}: '{c}' needs a whole number (you wrote {v!r}).")
            if not isinstance(sets, dict) or not sets:
                self.errors.append(f"{where} needs something to change, e.g. set = {{ \"board.walls\" = \"wrap\" }}.")
            else:
                for path, v in sets.items():
                    if path in ("board.width", "board.height"):
                        self.errors.append(f"{where}: the board size cannot change during a game.")
                        continue
                    if path not in TRIGGER_TARGETS:
                        self.errors.append(f"{where}: triggers cannot change '{path}'.{_suggest(path, TRIGGER_TARGETS)}")
                        continue
                    section, key = path.split(".")
                    if (msg := SCHEMA[section][key](v)):
                        self.errors.append(f"{where}: '{path}' {msg}.")


# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class VariantSpec:
    """A designer's variant: raw TOML data plus the engine config derived from it."""

    data: Mapping[str, Any]
    source: str = "variant"

    @classmethod
    def from_toml(cls, path: str | Path) -> "VariantSpec":
        path = Path(path)
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise SpecError([f"I can't find the file '{path}'."], str(path)) from None
        except tomllib.TOMLDecodeError as exc:
            raise SpecError([f"The file is not valid TOML: {exc}. Check quotes, '=' signs and [section] lines."],
                            str(path)) from None
        return cls.from_dict(data, source=str(path))

    @classmethod
    def from_dict(cls, data: Mapping, source: str = "variant") -> "VariantSpec":
        v = SpecValidator(data)
        if not v.validate():
            raise SpecError(v.errors, source)
        spec = cls(copy.deepcopy(dict(data)), source)
        object.__setattr__(spec, "_warnings", tuple(v.warnings))
        return spec

    @property
    def warnings(self) -> tuple[str, ...]:
        return getattr(self, "_warnings", ())

    # -- accessors --------------------------------------------------------------------------
    def section(self, name: str) -> dict:
        return dict(self.data.get(name, {}))

    @property
    def name(self) -> str:
        return self.section("variant").get("name", "Untitled variant")

    @property
    def version(self) -> str:
        return self.section("variant").get("version", "1.0")

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "_", self.name.lower()).strip("_") or "variant"

    @property
    def seed(self) -> int | None:
        return self.section("distribution").get("seed")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.data, sort_keys=True).encode()).hexdigest()

    # -- translation to the v1 engine's layered config ---------------------------------------
    def _distribution(self, d: Mapping) -> dict:
        kind = d.get("kind", "uniform")
        if kind == "weighted":
            return {"kind": "weighted", "weights": dict(d.get("weights", {})), "default": d.get("default_weight", 1.0)}
        if kind == "by_property":
            return {"kind": "by_property", "rule": d.get("rule", "uniform"), "strength": d.get("strength", 1.0)}
        if kind == "bag":
            return {"kind": "bag", "copies": d.get("copies", 1)}
        if kind == "adaptive":
            base = self._distribution({**{k: v for k, v in d.items() if k not in ("kind", "base")},
                                       "kind": d.get("base", "uniform")})
            return {"kind": "adaptive", "base": base, "drought_boost": d.get("drought_boost", 1.0),
                    "repeat_penalty": d.get("repeat_penalty", 0.5)}
        if kind == "mixture":
            return {"kind": "mixture", "parts": [
                {"weight": p.get("weight", 1.0), "dist": self._distribution({k: v for k, v in p.items() if k != "weight"})}
                for p in d.get("parts", [])]}
        return {"kind": "uniform"}

    def engine_spec(self) -> dict:
        meta, board, pieces = self.section("variant"), self.section("board"), self.section("pieces")
        phys, lv, sc = self.section("physics"), self.section("levels"), self.section("scoring")
        theme, controls = self.section("theme"), self.section("controls")
        rules = {k: v for k, v in {"width": board.get("width"), "height": board.get("height"),
                                   "walls": board.get("walls")}.items() if v is not None}
        rename = {"spawn_column": "spawn_col"}
        rules.update({rename.get(k, k): v for k, v in phys.items()})
        filt = {k: pieces[k] for k in ("bbox", "connectivity", "handedness", "max_holes") if k in pieces}
        fam = {"preset": pieces.get("preset", "Classic")}
        if filt:
            fam["filter"] = filt
        for k in ("include", "exclude"):
            if pieces.get(k):
                fam[k] = list(pieces[k])
        ui = {}
        if "name" in theme:
            ui["theme"] = theme["name"]
        for k in ("cell_px", "show_ghost", "colors"):
            if k in theme:
                ui[k] = theme[k]
        if controls:
            ui["keys"] = {**{"move_left": "Left", "move_right": "Right", "rotate_cw": "Up", "rotate_ccw": "z",
                             "soft_drop": "Down", "hard_drop": "space", "pause": "p"}, **controls}
        out = {
            "variant": {"name": self.name, "version": self.version, "authors": list(meta.get("authors", []))},
            "rules": rules, "scoring": sc, "level": lv, "pieces": fam,
            "distribution": self._distribution(self.section("distribution")),
            "triggers": [{"id": t["id"], "when": dict(t["when"]),
                          "set": {TRIGGER_TARGETS[p]: v for p, v in t["set"].items()}}
                         for t in self.data.get("triggers", [])],
        }
        if ui:
            out["ui"] = ui
        return out

    def build_engine(self, seed: int | None = None, player: Mapping | None = None) -> Engine:
        return Engine(self.engine_spec(), player=player, seed=self.seed if seed is None else seed)

    def family(self) -> PieceFamily:
        return PieceFamily.from_spec(self.engine_spec()["pieces"])

    def with_changes(self, changes: Mapping[str, Any]) -> "VariantSpec":
        """New spec with 'section.key' values replaced (used by the customizer and notebook)."""
        data = copy.deepcopy(dict(self.data))
        for path, value in changes.items():
            section, key = path.split(".", 1)
            data.setdefault(section, {})[key] = value
        return VariantSpec.from_dict(data, self.source)

    def to_toml(self) -> str:
        return dump_toml(self.data)


# ----------------------------------------------------------------------------
# Minimal TOML writer for the variant schema (tomllib only reads)
# ----------------------------------------------------------------------------
_BARE = re.compile(r"^[A-Za-z0-9_-]+$")
_ORDER = ["variant", "board", "pieces", "distribution", "levels", "scoring", "physics", "theme", "controls", "triggers"]


def _key(k: str) -> str:
    return k if _BARE.match(k) else json.dumps(k)


def _val(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, list):
        return "[" + ", ".join(_val(x) for x in v) + "]"
    if isinstance(v, Mapping):
        return "{ " + ", ".join(f"{_key(k)} = {_val(x)}" for k, x in v.items()) + " }"
    raise TypeError(f"cannot write {type(v).__name__} to TOML")


def dump_toml(data: Mapping[str, Any], header: str = "") -> str:
    lines = [header.rstrip()] if header else []
    sections = sorted(data, key=lambda s: _ORDER.index(s) if s in _ORDER else 99)
    for section in sections:
        value = data[section]
        if isinstance(value, list) and value and all(isinstance(x, Mapping) for x in value):
            for item in value:
                lines += ["", f"[[{_key(section)}]]"] + [f"{_key(k)} = {_val(v)}" for k, v in item.items()]
            continue
        lines += ["", f"[{_key(section)}]"]
        sub_arrays = []
        for k, v in value.items():
            if isinstance(v, list) and v and all(isinstance(x, Mapping) for x in v):
                sub_arrays.append((k, v))
            else:
                lines.append(f"{_key(k)} = {_val(v)}")
        for k, items in sub_arrays:
            for item in items:
                lines += ["", f"[[{_key(section)}.{_key(k)}]]"] + [f"{_key(a)} = {_val(b)}" for a, b in item.items()]
    return "\n".join(lines).lstrip("\n") + "\n"

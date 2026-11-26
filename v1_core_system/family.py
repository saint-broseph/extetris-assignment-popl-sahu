"""
family.py -- immutable, named sets of pieces (v1 core, layer 1).

    from family import PieceFamily, CLASSIC, EXTENDED_EASY, FULL

    CLASSIC                                   # the 7 classic tetrominoes
    EXTENDED_EASY                             # 15: every piece that can land with <= 1 hole
    FULL                                      # all 34
    FULL.filter(bbox="2x4", handedness="chiral")
    CLASSIC | FULL.filter(category="ExTetromino3x3")
    FULL.exclude("X4x4.H6666.0").include("I")

A family is immutable: every operation returns a new family. Pieces are always
listed in catalogue order, so iteration (and therefore seeded sampling) is
deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from piece import (ExTetromino, ExTetromino2x3, ExTetromino2x4, ExTetromino3x3, ExTetromino3x4,
                   ExTetromino4x4, Handedness, Piece, PieceSpecError, Tetromino, _coerce_bbox)

__all__ = ["PieceFamily", "CLASSIC", "EXTENDED_EASY", "FULL", "PRESETS", "piece_by_id"]

_CATEGORIES: Mapping[str, type[Piece]] = {
    cls.__name__: cls for cls in (Piece, Tetromino, ExTetromino, ExTetromino2x3, ExTetromino2x4,
                                  ExTetromino3x3, ExTetromino3x4, ExTetromino4x4)}


def piece_by_id(ident: str) -> Piece:
    """Look a piece up by classic letter ('T') or invariant code ('X3x3.H2233.+')."""
    ident = str(ident).strip()
    if len(ident) <= 5 and ident.upper() in ("I", "O", "T", "S", "Z", "L", "J", "GAMMA"):
        return Tetromino(ident)
    return Piece.from_code(ident)


def _as_list(value: object) -> list:
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value]


def _category_pred(value):
    classes = []
    for v in _as_list(value):
        cls = _CATEGORIES.get(v) if isinstance(v, str) else v
        if not (isinstance(cls, type) and issubclass(cls, Piece)):
            raise PieceSpecError(f"unknown category {v!r}; valid: {', '.join(_CATEGORIES)}")
        classes.append(cls)
    return lambda p: isinstance(p, tuple(classes))


def _connectivity_pred(value):
    kinds = {str(v).lower() for v in _as_list(value)}
    if not kinds <= {"edge", "corner"}:
        raise PieceSpecError("connectivity must be 'edge' (classic) or 'corner' (extended)")
    return lambda p: ("edge" if p.edge_components == 1 else "corner") in kinds


def _bbox_pred(value):
    boxes = {_coerce_bbox(v) for v in (_as_list(value) if not isinstance(value, tuple) or
                                         isinstance(value[0], (tuple, list, str)) else [value])}
    return lambda p: p.bbox in boxes


def _hand_pred(value):
    wanted = set()
    for v in _as_list(value):
        if isinstance(v, str) and v.lower() == "chiral":
            wanted |= {Handedness.PLUS, Handedness.MINUS}
        elif isinstance(v, str) and v.lower() == "achiral":
            wanted.add(Handedness.NONE)
        else:
            wanted.add(Handedness.coerce(v))
    return lambda p: p.handedness in wanted


def _ids_pred(value):
    codes = {piece_by_id(v).code for v in _as_list(value)}
    return lambda p: p.code in codes


@dataclass(frozen=True)
class PieceFamily:
    """An immutable, named set of pieces in catalogue order."""

    name: str
    codes: tuple[str, ...]

    def __post_init__(self) -> None:
        order = {p.code: i for i, p in enumerate(Piece.all_pieces())}
        unknown = [c for c in self.codes if c not in order]
        if unknown:
            raise PieceSpecError(f"unknown piece codes {unknown}")
        object.__setattr__(self, "codes", tuple(sorted(set(self.codes), key=order.__getitem__)))

    # -- construction ----------------------------------------------------------------
    @classmethod
    def of(cls, pieces: Iterable[Piece | str], name: str = "custom") -> "PieceFamily":
        return cls(name, tuple(p.code if isinstance(p, Piece) else piece_by_id(p).code for p in pieces))

    @classmethod
    def preset(cls, name: str) -> "PieceFamily":
        try:
            return PRESETS[name]
        except KeyError:
            raise PieceSpecError(f"unknown preset {name!r}; valid: {', '.join(PRESETS)}") from None

    @classmethod
    def from_spec(cls, spec: Mapping) -> "PieceFamily":
        """Build from config data: {"preset", "filter", "include", "include_filter", "exclude"}."""
        allowed = {"preset", "filter", "include", "include_filter", "exclude", "name"}
        extra = set(spec) - allowed
        if extra:
            raise PieceSpecError(f"unknown pieces keys {sorted(extra)}; valid: {sorted(allowed)}")
        fam = cls.preset(spec.get("preset", "Full"))
        if spec.get("filter"):
            fam = fam.filter(**spec["filter"])
        if spec.get("include"):
            fam = fam.include(*spec["include"])
        if spec.get("include_filter"):
            fam = fam.include(**spec["include_filter"])
        if spec.get("exclude"):
            fam = fam.exclude(*spec["exclude"])
        if not fam.codes:
            raise PieceSpecError("the piece family is empty")
        return fam.renamed(spec.get("name", fam.name))

    # -- container protocol -----------------------------------------------------------
    @property
    def pieces(self) -> tuple[Piece, ...]:
        return tuple(Piece.from_code(c) for c in self.codes)

    def __iter__(self):
        return iter(self.pieces)

    def __len__(self) -> int:
        return len(self.codes)

    def __contains__(self, item: object) -> bool:
        code = item.code if isinstance(item, Piece) else piece_by_id(str(item)).code
        return code in self.codes

    def renamed(self, name: str) -> "PieceFamily":
        return PieceFamily(name, self.codes)

    # -- filtering ----------------------------------------------------------------------
    def where(self, predicate, name: str | None = None) -> "PieceFamily":
        """Keep pieces for which predicate(piece) is true (functional filter)."""
        return PieceFamily(name or f"{self.name}[where]", tuple(p.code for p in self if predicate(p)))

    def filter(self, *, category=None, connectivity=None, bbox=None, max_holes=None,
               handedness=None, ids=None) -> "PieceFamily":
        """AND of the given criteria.

        category      class or class name(s): 'Tetromino', 'ExTetromino', 'ExTetromino3x3', ...
        connectivity  'edge' (classic) or 'corner' (extended)
        bbox          '2x4' / (2, 4) or a list of them
        max_holes     pieces that can land leaving at most this many holes (best orientation)
        handedness    '+', '-', '0', 'chiral', 'achiral', Handedness, or a list
        ids           classic letters and/or invariant codes
        """
        preds = []
        if category is not None:
            preds.append(_category_pred(category))
        if connectivity is not None:
            preds.append(_connectivity_pred(connectivity))
        if bbox is not None:
            preds.append(_bbox_pred(bbox))
        if max_holes is not None:
            preds.append(lambda p, n=int(max_holes): p.min_landing_holes <= n)
        if handedness is not None:
            preds.append(_hand_pred(handedness))
        if ids is not None:
            preds.append(_ids_pred(ids))
        return self.where(lambda p: all(f(p) for f in preds), name=f"{self.name}[filtered]")

    # -- set algebra ---------------------------------------------------------------------
    def _other(self, items, filters) -> "PieceFamily":
        parts = [FULL.filter(**filters)] if filters else []
        for it in items:
            parts.append(it if isinstance(it, PieceFamily) else PieceFamily.of([it]))
        codes = set().union(*(p.codes for p in parts)) if parts else set()
        return PieceFamily("other", tuple(codes))

    def include(self, *items, **filters) -> "PieceFamily":
        """Add pieces/families/ids, and/or every piece matching filter keywords."""
        return PieceFamily(self.name, self.codes + self._other(items, filters).codes)

    def exclude(self, *items, **filters) -> "PieceFamily":
        drop = set(self._other(items, filters).codes)
        return PieceFamily(self.name, tuple(c for c in self.codes if c not in drop))

    def union(self, other: "PieceFamily") -> "PieceFamily":
        return PieceFamily(f"{self.name}|{other.name}", self.codes + other.codes)

    def intersection(self, other: "PieceFamily") -> "PieceFamily":
        keep = set(other.codes)
        return PieceFamily(f"{self.name}&{other.name}", tuple(c for c in self.codes if c in keep))

    def difference(self, other: "PieceFamily") -> "PieceFamily":
        drop = set(other.codes)
        return PieceFamily(f"{self.name}-{other.name}", tuple(c for c in self.codes if c not in drop))

    __or__ = union
    __and__ = intersection
    __sub__ = difference

    def __eq__(self, other: object) -> bool:  # same members, name ignored
        return isinstance(other, PieceFamily) and set(self.codes) == set(other.codes)

    def __hash__(self) -> int:
        return hash(frozenset(self.codes))

    def __repr__(self) -> str:
        return f"PieceFamily({self.name!r}, {len(self)} pieces)"


FULL = PieceFamily("Full", tuple(p.code for p in Piece.all_pieces()))
CLASSIC = FULL.filter(category=Tetromino).renamed("Classic")
EXTENDED_EASY = FULL.filter(max_holes=1).renamed("Extended-Easy")
PRESETS: Mapping[str, PieceFamily] = {"Classic": CLASSIC, "Extended-Easy": EXTENDED_EASY, "Full": FULL}

"""
distribution.py -- seeded, functional-OO piece distributions (v1 core, layer 1).

Replaces the starter's "repeat an index in a list" scheme. Probabilities are defined
per *piece* (34 one-sided shapes), not per stored matrix. This removes the starter's
1x-4x orientation bias, where one piece could be listed 4 times and another once.

Every distribution is an immutable object whose weights are a pure function of the
draw history:

    weights(history, count) -> {code: weight}        # pure
    draw(rng, history, count) -> Piece               # the only use of randomness

The engine owns the seeded random.Random and the history, so games are reproducible
and can be saved and resumed exactly.

    UniformDistribution(FULL)
    WeightedDistribution(CLASSIC, {"I": 2, "S": 0.5})
    ByPropertyDistribution(FULL, lambda p: 1 / (1 + p.min_landing_holes))
    BagDistribution(CLASSIC)                              # 7-bag
    AdaptiveDistribution(UniformDistribution(FULL), drought_boost=2.0)
    mix((BagDistribution(CLASSIC), 0.8), (UniformDistribution(EXTENDED_EASY), 0.2))
"""
from __future__ import annotations

import abc
import random
from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

from family import FULL, PieceFamily, piece_by_id
from piece import Piece, PieceSpecError

__all__ = ["Distribution", "UniformDistribution", "WeightedDistribution", "ByPropertyDistribution",
           "BagDistribution", "AdaptiveDistribution", "MixtureDistribution", "mix",
           "PROPERTY_RULES", "distribution_from_spec"]

History = Sequence[str]


class Distribution(abc.ABC):
    """Abstract base: a family plus a pure weight function of the history."""

    family: PieceFamily

    @abc.abstractmethod
    def weights(self, history: History = (), count: int = 0) -> dict[str, float]:
        """Non-negative weight per piece code (codes outside the family are ignored)."""

    def probabilities(self, history: History = (), count: int = 0) -> dict[str, float]:
        w = self.weights(history, count)
        total = sum(w.get(c, 0.0) for c in self.family.codes)
        if total <= 0:
            raise PieceSpecError(f"{type(self).__name__}: all weights are zero")
        return {c: w.get(c, 0.0) / total for c in self.family.codes}

    def draw(self, rng: random.Random, history: History = (), count: int = 0) -> Piece:
        """Draw one piece. Deterministic for a given rng state and history."""
        w = self.weights(history, count)
        codes = [c for c in self.family.codes if w.get(c, 0.0) > 0]
        if not codes:
            raise PieceSpecError(f"{type(self).__name__}: all weights are zero")
        total = sum(w[c] for c in codes)
        x, acc = rng.random() * total, 0.0
        for c in codes:
            acc += w[c]
            if x < acc:
                return Piece.from_code(c)
        return Piece.from_code(codes[-1])

    def __mul__(self, weight: float) -> tuple["Distribution", float]:  # sugar: mix(d1 * 0.8, d2 * 0.2)
        return (self, float(weight))


@dataclass(frozen=True)
class UniformDistribution(Distribution):
    """Every piece in the family equally likely."""
    family: PieceFamily = FULL

    def weights(self, history=(), count=0):
        return {c: 1.0 for c in self.family.codes}


@dataclass(frozen=True)
class WeightedDistribution(Distribution):
    """Explicit weights by letter or code; pieces not listed get `default`."""
    family: PieceFamily = FULL
    table: Mapping[str, float] = field(default_factory=dict)
    default: float = 1.0

    def __post_init__(self):
        resolved = {}
        for ident, w in dict(self.table).items():
            if float(w) < 0:
                raise PieceSpecError(f"negative weight for {ident!r}")
            resolved[piece_by_id(ident).code] = float(w)
        object.__setattr__(self, "table", resolved)

    def weights(self, history=(), count=0):
        return {c: self.table.get(c, self.default) for c in self.family.codes}


# Named property rules, so data files can choose a rule without code.
PROPERTY_RULES: Mapping[str, Callable[[Piece], float]] = {
    "uniform": lambda p: 1.0,
    "favor_few_holes": lambda p: 1.0 / (1 + p.min_landing_holes),
    "favor_classic": lambda p: 3.0 if p.edge_components == 1 else 1.0,
    "favor_small_bbox": lambda p: 1.0 / (p.bbox[0] * p.bbox[1]),
    "favor_symmetric": lambda p: 2.0 if not p.is_chiral else 1.0,
}


@dataclass(frozen=True)
class ByPropertyDistribution(Distribution):
    """Weight computed from piece invariants by a pure function (or a named rule)."""
    family: PieceFamily = FULL
    rule: Callable[[Piece], float] | str = "uniform"
    strength: float = 1.0          # weight ** strength sharpens or flattens the rule

    def _fn(self):
        if isinstance(self.rule, str):
            if self.rule not in PROPERTY_RULES:
                raise PieceSpecError(f"unknown rule {self.rule!r}; valid: {', '.join(PROPERTY_RULES)}")
            return PROPERTY_RULES[self.rule]
        return self.rule

    def weights(self, history=(), count=0):
        fn = self._fn()
        return {p.code: max(0.0, float(fn(p))) ** self.strength for p in self.family}


@dataclass(frozen=True)
class BagDistribution(Distribution):
    """Shuffle-bag: each piece appears `copies` times per bag, without replacement.

    The bag position is derived from the total draw count, and the bag contents from
    the last draws in the history, so no hidden mutable state is needed.
    """
    family: PieceFamily = FULL
    copies: int = 1

    def __post_init__(self):
        if not 1 <= self.copies <= 7:
            raise PieceSpecError("bag copies must be between 1 and 7")

    def weights(self, history=(), count=0):
        size = len(self.family) * self.copies
        k = count % size
        recent = list(history[-k:]) if k else []
        w = {c: float(self.copies - recent.count(c)) for c in self.family.codes}
        if all(v <= 0 for v in w.values()):       # inconsistent history (e.g. inside a mixture)
            return {c: 1.0 for c in self.family.codes}
        return {c: max(0.0, v) for c, v in w.items()}


@dataclass(frozen=True)
class AdaptiveDistribution(Distribution):
    """Wraps a base distribution. Boosts pieces not seen for a while (fewer droughts)
    and damps an immediate repeat."""
    base: Distribution = field(default_factory=UniformDistribution)
    drought_boost: float = 1.0
    repeat_penalty: float = 0.5

    @property
    def family(self) -> PieceFamily:  # type: ignore[override]
        return self.base.family

    def weights(self, history=(), count=0):
        base = self.base.weights(history, count)
        n = len(self.family)
        out = {}
        for c in self.family.codes:
            try:
                since = len(history) - 1 - max(i for i, h in enumerate(history) if h == c)
            except ValueError:
                since = len(history)
            w = base.get(c, 0.0) * (1.0 + self.drought_boost * min(since, 4 * n) / n)
            if history and history[-1] == c:
                w *= self.repeat_penalty
            out[c] = w
        return out


@dataclass(frozen=True)
class MixtureDistribution(Distribution):
    """Weighted mixture: P(piece) = sum_i w_i * P_i(piece)."""
    parts: tuple[tuple[Distribution, float], ...] = ()

    def __post_init__(self):
        if not self.parts or any(w < 0 for _, w in self.parts) or sum(w for _, w in self.parts) <= 0:
            raise PieceSpecError("a mixture needs at least one part with positive weight")

    @property
    def family(self) -> PieceFamily:  # type: ignore[override]
        fam = self.parts[0][0].family
        for d, _ in self.parts[1:]:
            fam = fam | d.family
        return fam.renamed("mixture")

    def weights(self, history=(), count=0):
        total = sum(w for _, w in self.parts)
        out: dict[str, float] = {}
        for d, w in self.parts:
            for c, p in d.probabilities(history, count).items():
                out[c] = out.get(c, 0.0) + (w / total) * p
        return out


def mix(*parts: tuple[Distribution, float]) -> MixtureDistribution:
    return MixtureDistribution(tuple((d, float(w)) for d, w in parts))


def distribution_from_spec(spec: Mapping, family: PieceFamily) -> Distribution:
    """Build from config data (no code): {"kind": ..., ...}."""
    spec = dict(spec)
    kind = spec.pop("kind", "uniform")
    fam = PieceFamily.from_spec(spec.pop("pieces")) if "pieces" in spec else family

    def check(allowed):
        extra = set(spec) - set(allowed)
        if extra:
            raise PieceSpecError(f"distribution kind {kind!r}: unknown keys {sorted(extra)}")

    if kind == "uniform":
        check([])
        return UniformDistribution(fam)
    if kind == "weighted":
        check(["weights", "default"])
        return WeightedDistribution(fam, spec.get("weights", {}), float(spec.get("default", 1.0)))
    if kind == "by_property":
        check(["rule", "strength"])
        return ByPropertyDistribution(fam, spec.get("rule", "uniform"), float(spec.get("strength", 1.0)))
    if kind == "bag":
        check(["copies"])
        return BagDistribution(fam, int(spec.get("copies", 1)))
    if kind == "adaptive":
        check(["base", "drought_boost", "repeat_penalty"])
        base = distribution_from_spec(spec.get("base", {"kind": "uniform"}), fam)
        return AdaptiveDistribution(base, float(spec.get("drought_boost", 1.0)),
                                    float(spec.get("repeat_penalty", 0.5)))
    if kind == "mixture":
        check(["parts"])
        return mix(*[(distribution_from_spec(p["dist"], fam), float(p.get("weight", 1.0)))
                     for p in spec.get("parts", [])])
    raise PieceSpecError(f"unknown distribution kind {kind!r}; valid: uniform, weighted, "
                         "by_property, bag, adaptive, mixture")

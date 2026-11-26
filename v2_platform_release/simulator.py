"""
simulator.py -- headless balance checks for a variant.

The bot plays through Engine.apply_action() only, exactly like a human with a
keyboard; it never edits the state. Two bots are available:
  * greedy  tries every reachable orientation and column, scores each landing
            (holes, height, bumpiness, lines), then steers there and hard-drops
  * random  random rotation and column (a pessimistic baseline)
"""
from __future__ import annotations

import random
import statistics
import time
from collections import Counter
from dataclasses import dataclass, field

from spec import VariantSpec
from state import Action, Mode

__all__ = ["simulate", "SimulationReport"]


def _evaluate(board, lines: int) -> float:
    heights = [0] * board.width
    tops = {}
    for r, c in board.filled:
        tops[c] = min(tops.get(c, board.height), r)
    holes = 0
    for c, top in tops.items():
        heights[c] = board.height - top
        holes += sum(1 for r in range(top + 1, board.height) if (r, c) not in board.filled)
    bump = sum(abs(heights[i] - heights[i + 1]) for i in range(board.width - 1))
    return 3.0 * lines - 4.0 * holes - 0.5 * sum(heights) - 0.4 * bump - 0.8 * max(heights)


def _plan(engine, bot: random.Random, greedy: bool):
    s, rules = engine.state, engine.rules
    turns = {"both": range(4), "cw_only": range(4), "none": range(1)}[rules.rotation]
    if not greedy:
        return bot.choice(list(turns)), bot.randrange(rules.width)
    best, best_score = None, None
    for k in turns:
        piece = s.active.turned(k)
        cols = range(rules.width) if rules.wrap else range(rules.width - piece.width + 1)
        for col in cols:
            if not s.board.fits(piece, (s.pos[0], col), rules.wrap):
                continue
            d = s.board.drop_distance(piece, (s.pos[0], col), rules.wrap)
            board, lines, _ = s.board.place(piece, (s.pos[0] + d, col), rules.wrap).clear_rows(rules.gravity)
            score = _evaluate(board, lines) + bot.random() * 1e-3
            if best_score is None or score > best_score:
                best, best_score = (k, col), score
    return best or (0, s.pos[1])


def _steer_and_drop(engine, turns: int, col: int) -> None:
    for _ in range(turns):
        engine.apply_action(Action.ROTATE_CW)
    for _ in range(engine.rules.width):
        cur = engine.state.pos[1]
        if cur == col or engine.state.active is None:
            break
        before = engine.state.pos
        engine.apply_action(Action.MOVE_LEFT if col < cur else Action.MOVE_RIGHT)
        if engine.state.pos == before:
            break
    spawned = engine.state.pieces_spawned
    engine.apply_action(Action.HARD_DROP)
    guard = 0
    while engine.state.mode is Mode.RUNNING and engine.state.pieces_spawned == spawned and guard < 200:
        engine.tick(engine.level_policy.gravity_ms(engine.state.level))   # lock if hard drop does not
        guard += 1


@dataclass
class SimulationReport:
    variant: str
    games: int
    bot: str
    pieces: list[int] = field(default_factory=list)
    lines: list[int] = field(default_factory=list)
    scores: list[int] = field(default_factory=list)
    levels: list[int] = field(default_factory=list)
    capped: int = 0
    counts: Counter = field(default_factory=Counter)
    expected: dict[str, float] = field(default_factory=dict)
    triggers: Counter = field(default_factory=Counter)
    seconds: float = 0.0

    def max_frequency_deviation(self) -> float:
        total = sum(self.counts.values()) or 1
        return max(abs(self.counts[c] / total - p) for c, p in self.expected.items())

    def verdicts(self) -> list[str]:
        out = []
        avg_pieces = statistics.mean(self.pieces)
        lpp = sum(self.lines) / max(1, sum(self.pieces))
        if avg_pieces < 40:
            out.append(f"HARD: games last only {avg_pieces:.0f} pieces on average - consider easier pieces, "
                       "a wider board or a slower speed.")
        elif self.capped > self.games / 2:
            out.append("EASY: most games reached the piece limit - consider faster levels or harder pieces.")
        else:
            out.append(f"BALANCED: average game {avg_pieces:.0f} pieces.")
        out.append(f"Lines per piece {lpp:.2f} (a strong classic game is about 0.35-0.40).")
        out.append(f"Piece frequencies differ from the design probabilities by at most "
                   f"{100 * self.max_frequency_deviation():.1f} percentage points.")
        return out

    def summary(self) -> str:
        def stat(xs):
            return f"mean {statistics.mean(xs):8.1f}   median {statistics.median(xs):7.1f}   max {max(xs):7d}"
        lines = [f"Simulation of '{self.variant}': {self.games} games, {self.bot} bot, {self.seconds:.1f} s",
                 f"  pieces per game  {stat(self.pieces)}",
                 f"  lines per game   {stat(self.lines)}",
                 f"  score per game   {stat(self.scores)}",
                 f"  level reached    {stat(self.levels)}",
                 f"  games stopped at the piece limit: {self.capped}"]
        if self.triggers:
            lines.append("  triggers fired: " + ", ".join(f"{k} x{v}" for k, v in sorted(self.triggers.items())))
        total = sum(self.counts.values())
        lines.append("  most / least frequent pieces (observed vs designed):")
        ranked = sorted(self.expected, key=lambda c: -self.counts[c])
        for c in ranked[:3] + (ranked[-2:] if len(ranked) > 5 else []):
            lines.append(f"     {c:14s} {100 * self.counts[c] / total:5.1f}%  vs {100 * self.expected[c]:5.1f}%")
        lines.append("  verdict:")
        lines += [f"     {v}" for v in self.verdicts()]
        return "\n".join(lines)


def simulate(spec: VariantSpec, games: int = 100, *, seed: int = 0, bot: str = "greedy",
             max_pieces: int = 300) -> SimulationReport:
    report = SimulationReport(spec.name, games, bot)
    started = time.perf_counter()
    for g in range(games):
        engine = spec.build_engine(seed=seed + g)
        if g == 0:
            report.expected = engine.distribution.probabilities()
        rng = random.Random((seed + g) * 7919 + 1)
        n = 0
        while engine.state.mode is Mode.RUNNING and n < max_pieces:
            report.counts[engine.state.active.code] += 1
            turns, col = _plan(engine, rng, bot == "greedy")
            _steer_and_drop(engine, turns, col)
            n += 1
        st = engine.state
        report.pieces.append(n)
        report.lines.append(st.lines)
        report.scores.append(st.score)
        report.levels.append(st.level)
        report.capped += n >= max_pieces
        report.triggers.update(st.fired_triggers)
    report.seconds = time.perf_counter() - started
    return report

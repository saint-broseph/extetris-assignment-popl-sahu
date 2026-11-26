"""
test_v1.py -- pytest suite for the ExTetris v1 core system.

    pytest v1_core_system            (from the repo root)
"""
from __future__ import annotations

import ast
import json
import os
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from board import Board  # noqa: E402
from distribution import (AdaptiveDistribution, BagDistribution, ByPropertyDistribution,  # noqa: E402
                          UniformDistribution, WeightedDistribution, distribution_from_spec, mix)
from engine import ConfigError, Engine, SaveError, VariantMismatchError, variant_hash  # noqa: E402
from family import CLASSIC, EXTENDED_EASY, FULL, PieceFamily  # noqa: E402
from piece import ExTetromino, Handedness, Piece, Tetromino  # noqa: E402
from state import Action, LevelPolicy, Mode, Rules, Scoring  # noqa: E402

STARTER = HERE.parent / "v0_starter" / "allextetrominoes.py"
CORE_MODULES = ["piece.py", "family.py", "distribution.py", "board.py", "state.py", "engine.py"]


# ---------------------------------------------------------------- pieces
def test_all_34_pieces():
    pieces = Piece.all_pieces()
    assert len(pieces) == 34 and len(Tetromino.all_pieces()) == 7 and len(ExTetromino.all_pieces()) == 27
    assert sum(p.orientation_count for p in pieces) == 110
    assert len({(p.bbox, p.hole_signature, p.handedness) for p in pieces}) == 34
    for p in pieces:
        assert Piece.from_code(p.code) == p and Piece.identify_cells(p.cells) == p


@pytest.mark.skipif(not STARTER.is_file(), reason="v0_starter not present")
def test_starter_matrices_match_up_to_rotation():
    seen = set()
    for node in ast.parse(STARTER.read_text()).body:
        if isinstance(node, ast.Assign) and node.targets[0].id.startswith("Extetromino"):
            seen.add(Piece.identify_matrix(ast.literal_eval(node.value.args[0])).code)
    assert len(seen) == 34


# ---------------------------------------------------------------- families
def test_presets():
    assert (len(CLASSIC), len(EXTENDED_EASY), len(FULL)) == (7, 15, 34)
    assert set(CLASSIC.codes) <= set(EXTENDED_EASY.codes)
    assert all(p.min_landing_holes <= 1 for p in EXTENDED_EASY)


def test_filters():
    assert len(FULL.filter(category="Tetromino")) == 7
    assert len(FULL.filter(category="ExTetromino3x3")) == 9
    assert len(FULL.filter(connectivity="corner")) == 27 and len(FULL.filter(connectivity="edge")) == 7
    assert len(FULL.filter(bbox="2x4")) == 9 and len(FULL.filter(bbox=["2x3", "4x4"])) == 8
    assert len(FULL.filter(max_holes=0)) == 5          # I O T L J
    assert len(FULL.filter(handedness="achiral")) == 10 and len(FULL.filter(handedness="chiral")) == 24
    assert len(FULL.filter(handedness="+")) == 12
    assert FULL.filter(ids=["T", "X4x4.H6666.0"]).codes == ("T2x3.H0121.0", "X4x4.H6666.0")


def test_set_algebra():
    a, b = FULL.filter(bbox="2x3"), FULL.filter(handedness="chiral")
    assert a | b == b | a and a & b == b & a
    assert len(a | b) == len(a) + len(b) - len(a & b)
    assert (a - b) | (a & b) == a
    assert FULL.exclude(CLASSIC) == FULL.filter(connectivity="corner")
    assert CLASSIC.include("X4x4.H6666.0") == CLASSIC | FULL.filter(bbox="4x4")
    assert FULL.include(bbox="3x3") == FULL and CLASSIC.include(bbox="3x3") - CLASSIC == FULL.filter(bbox="3x3")
    assert PieceFamily.from_spec({"preset": "Classic", "exclude": ["S", "Z"]}).codes == \
        CLASSIC.exclude("S", "Z").codes
    with pytest.raises(Exception):
        PieceFamily.from_spec({"preset": "Classic", "exclude": list(Tetromino.LETTERS)})


# ---------------------------------------------------------------- distributions
def _count(dist, n, seed=1):
    rng, hist, counts = random.Random(seed), [], Counter()
    for i in range(n):
        p = dist.draw(rng, tuple(hist[-256:]), i)
        hist.append(p.code)
        counts[p.code] += 1
    return counts, hist


def test_uniform_is_fair_per_piece_and_fixes_starter_bias():
    probs = UniformDistribution(FULL).probabilities()
    assert max(probs.values()) / min(probs.values()) == 1.0
    counts, _ = _count(UniformDistribution(FULL), 34_000)
    assert all(800 <= counts[c] <= 1200 for c in FULL.codes), counts.most_common(3)
    if STARTER.is_file():   # the starter's index scheme: 1/73 .. 4/73 per piece
        mult = Counter(Piece.identify_matrix(ast.literal_eval(n.value.args[0])).code
                       for n in ast.parse(STARTER.read_text()).body
                       if isinstance(n, ast.Assign) and n.targets[0].id.startswith("Extetromino"))
        assert max(mult.values()) / min(mult.values()) == 4


def test_weighted_and_by_property_match_probabilities():
    w = WeightedDistribution(CLASSIC, {"I": 3, "O": 0})
    p = w.probabilities()
    assert p["T1x4.H0000.0"] == pytest.approx(3 / 8) and p["T2x2.H0000.0"] == 0
    counts, _ = _count(w, 16_000)
    assert counts["T1x4.H0000.0"] / 16_000 == pytest.approx(3 / 8, abs=0.02) and counts["T2x2.H0000.0"] == 0
    bp = ByPropertyDistribution(FULL, "favor_few_holes").probabilities()
    assert bp["T1x4.H0000.0"] > bp["X4x4.H6666.0"] * 6


def test_bag_gives_each_piece_once_per_bag():
    _, hist = _count(BagDistribution(CLASSIC), 7 * 50)
    for i in range(0, len(hist), 7):
        assert sorted(hist[i:i + 7]) == sorted(CLASSIC.codes)


def test_adaptive_shortens_droughts_and_mixture_sums():
    def longest_gap(hist):
        last, worst = {}, 0
        for i, c in enumerate(hist):
            worst = max(worst, i - last.get(c, -1))
            last[c] = i
        return worst
    _, uni = _count(UniformDistribution(CLASSIC), 5000)
    _, ada = _count(AdaptiveDistribution(UniformDistribution(CLASSIC), drought_boost=3.0), 5000)
    assert longest_gap(ada) < longest_gap(uni)
    m = mix((BagDistribution(CLASSIC), 0.8), (UniformDistribution(EXTENDED_EASY), 0.2))
    assert sum(m.probabilities().values()) == pytest.approx(1.0)
    assert m.probabilities()["X2x3.H1112.+"] == pytest.approx(0.2 / 15)
    spec = {"kind": "mixture", "parts": [{"weight": 1, "dist": {"kind": "bag"}},
                                         {"weight": 1, "dist": {"kind": "adaptive"}}]}
    assert distribution_from_spec(spec, CLASSIC).probabilities()


def test_distributions_are_deterministic_per_seed():
    d = AdaptiveDistribution(BagDistribution(FULL))
    assert _count(d, 500, seed=42)[1] == _count(d, 500, seed=42)[1]


# ---------------------------------------------------------------- board, rules, scoring, levels
def test_solid_walls_block_and_wrap_walls_wrap():
    i = Tetromino("I")
    b = Board(10, 20)
    assert b.fits(i, (5, 0)) and not b.fits(i, (5, -1))          # v0 BUG-01 is gone
    assert not b.fits(i, (5, 7))
    assert b.fits(i, (5, -1), wrap=True)
    assert sorted(b.place(i, (5, 8), wrap=True).filled) == [(5, 0), (5, 1), (5, 8), (5, 9)]
    blocked = Board(10, 20, frozenset({(5, 0)}))
    assert not blocked.fits(i, (5, 8), wrap=True)                  # collides through the wrap
    e = Engine({"rules": {"walls": "wrap"}, "pieces": {"preset": "Classic", "filter": {"ids": ["O"]}}}, seed=1)
    for _ in range(5):                                               # spawn col 4 -> 3, 2, 1, 0, 9
        e.apply_action(Action.MOVE_LEFT)
    assert sorted({c for _, c in e.active_cells()}) == [0, 9]       # straddles the seam


def test_naive_vs_cascade_gravity():
    cells = {(19, c) for c in range(10)} | {(18, c) for c in range(9)} | {(17, 9), (16, 9)}
    b = Board(10, 20, frozenset(cells))
    naive, n_lines, _ = b.clear_rows("naive_drop")
    assert n_lines == 1 and (17, 9) in naive.filled and (18, 9) in naive.filled
    casc, c_lines, chains = b.clear_rows("cascade")
    assert c_lines == 2 and chains == 2 and casc.filled == frozenset({(19, 9)})   # chain reaction


def test_level_policy_threshold_crossing_and_clamp():
    lp = LevelPolicy()
    assert lp.level_for(98) == 9 and lp.level_for(102) == 10      # 98 + 4 crosses 100 (v0 skipped it)
    assert [lp.gravity_ms(k) for k in (0, 1, 2)] == [1000, 900, 810]
    assert lp.gravity_ms(500) == lp.min_ms
    assert all(lp.level_for(n) == n // 10 for n in range(0, 300, 3))


def test_scoring_and_rules_validation():
    s = Scoring()
    assert s.for_clear(4, 1, 0) == 800 and s.for_clear(2, 1, 2) == 900 and s.for_clear(6, 2, 0) == 800 + 600 + 50
    for bad in ({"walls": "soft"}, {"gravity": "magic"}, {"width": 2}, {"preview": 0}):
        with pytest.raises(ValueError):
            Rules(**bad)


# ---------------------------------------------------------------- engine
def test_engine_has_zero_tkinter():
    for name in CORE_MODULES:
        tree = ast.parse((HERE / name).read_text())
        mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        assert "tkinter" not in mods, name
    code = ("import sys; sys.modules['tkinter'] = None; sys.path.insert(0, %r); import engine; "
            "e = engine.Engine(seed=1); e.tick(5000); print('ok')" % str(HERE))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == "ok", out.stderr


def test_pause_ignores_ticks_and_input():
    e = Engine(seed=5)
    e.apply_action(Action.PAUSE)
    before = e.state
    for _ in range(10):
        e.apply_action(Action.SOFT_DROP)
        e.tick(5000)
    assert e.state == before and e.state.mode is Mode.PAUSED
    e.apply_action(Action.PAUSE)
    e.tick(1000)
    assert e.state.pos[0] == before.pos[0] + 1                       # exactly one gravity step, no stacking


def test_determinism_same_seed_same_game():
    def play(seed):
        e, r = Engine({"pieces": {"preset": "Full"}}, seed=seed), random.Random(seed)
        for _ in range(400):
            e.apply_action(r.choice(list(Action)[:6]))
            e.tick(r.choice([0, 30, 500]))
        return e.save()
    assert play(9) == play(9) and play(9) != play(10)


def test_layered_config_and_restrictions():
    e = Engine({"level": {"base_ms": 800}}, player={"level": {"start_level": 2}, "ui": {"theme": "light"}}, seed=1)
    assert e.level_policy.gravity_ms(e.state.level) == round(800 * 0.9 ** 2)
    assert e.config["ui"]["theme"] == "light"
    with pytest.raises(ConfigError):
        Engine(player={"rules": {"width": 20}})
    with pytest.raises(ConfigError):
        Engine({"rules": {"colour": "red"}})
    with pytest.raises(ConfigError):
        e.request_update("rules.width", 12)                          # not allowed mid-game


def test_runtime_updates_apply_only_at_tick_boundary():
    e = Engine(seed=2)
    e.request_update("rules.walls", "wrap")
    assert e.rules.walls == "solid"
    e.apply_action(Action.MOVE_LEFT)
    assert e.rules.walls == "solid"                                  # still the old rules
    events = e.tick(0)
    assert e.rules.walls == "wrap" and events[0].kind == "ConfigChanged"
    with pytest.raises(ConfigError):
        e.request_update("rules.walls", "bouncy")                     # validated on request


def test_triggers_fire_once_and_are_restricted():
    spec = {"triggers": [{"id": "wrap-later", "when": {"pieces_at_least": 3}, "set": {"rules.walls": "wrap"}}]}
    e = Engine(spec, seed=3)
    fired = []
    for _ in range(10):
        e.apply_action(Action.HARD_DROP)
        fired += [ev for ev in e.tick(0) if ev.kind == "TriggerFired"]
    assert len(fired) == 1 and e.rules.walls == "wrap"
    for bad in ({"id": "x", "when": {"python": 1}, "set": {}},
                {"id": "x", "when": {"lines_at_least": 1}, "set": {"rules.width": 5}}):
        with pytest.raises(ConfigError):
            Engine({"triggers": [bad]})


def test_save_resume_with_hash_verification(tmp_path):
    spec = {"pieces": {"preset": "Extended-Easy"}, "distribution": {"kind": "bag"}}
    script = [random.Random(4).choice(list(Action)[:6]) for _ in range(300)]

    def run(engine, steps):
        for a in steps:
            engine.apply_action(a)
            engine.tick(120)
        return engine

    straight = run(Engine(spec, seed=11), script)
    half = run(Engine(spec, seed=11), script[:150])
    half.request_update("level.base_ms", 700)
    text = half.save()
    (tmp_path / "game.json").write_text(text)
    resumed = Engine.resume((tmp_path / "game.json").read_text(), spec)
    assert resumed.state == half.state and json.loads(resumed.save()) == json.loads(text)
    reference = run(Engine.resume(text, spec), script[150:])
    half_continued = run(half, script[150:])
    assert reference.state == half_continued.state
    assert straight.variant_hash == variant_hash(spec)
    with pytest.raises(VariantMismatchError):
        Engine.resume(text, {"pieces": {"preset": "Full"}})
    tampered = json.loads(text)
    tampered["state"]["score"] += 1000
    with pytest.raises(SaveError):
        Engine.resume(json.dumps(tampered), spec)


# ---------------------------------------------------------------- 300 simulated games
VARIANTS = [
    {},
    {"pieces": {"preset": "Full"}, "rules": {"walls": "wrap", "gravity": "cascade"}},
    {"pieces": {"preset": "Extended-Easy"}, "distribution": {"kind": "bag", "copies": 2},
     "rules": {"game_over": "top_rows", "width": 8, "height": 16}},
    {"pieces": {"preset": "Full"}, "distribution": {"kind": "adaptive"}, "rules": {"hard_drop_locks": False}},
    {"pieces": {"preset": "Classic"}, "distribution": {"kind": "by_property", "rule": "favor_few_holes"},
     "rules": {"rotation": "cw_only", "kicks": False}, "level": {"lines_per_level": 2}},
]


def _bot_game(spec, seed):
    e, bot = Engine(spec, seed=seed), random.Random(seed * 7 + 1)
    lines_seen, pieces = 0, 0
    while e.state.mode is Mode.RUNNING and pieces < 400:
        for _ in range(bot.randrange(4)):
            e.apply_action(Action.ROTATE_CW)
        move = bot.choice([Action.MOVE_LEFT, Action.MOVE_RIGHT])
        for _ in range(bot.randrange(6)):
            e.apply_action(move)
        before = e.state.pieces_spawned
        for ev in e.apply_action(Action.HARD_DROP):
            lines_seen += ev.data.get("lines", 0) if ev.kind == "LinesCleared" else 0
        guard = 0
        while e.state.mode is Mode.RUNNING and e.state.pieces_spawned == before and guard < 100:
            for ev in e.tick(e.level_policy.gravity_ms(e.state.level)):   # locks when hard drop doesn't
                lines_seen += ev.data.get("lines", 0) if ev.kind == "LinesCleared" else 0
            guard += 1
        b = e.state.board
        assert all(0 <= r < b.height and 0 <= c < b.width for r, c in b.filled)
        assert not b.full_rows()
        pieces += 1
    assert e.state.lines == lines_seen and e.state.score >= 0
    assert e.state.level == e.level_policy.level_for(e.state.lines)
    return e


def test_300_simulated_games():
    finished = Counter()
    for g in range(300):
        e = _bot_game(VARIANTS[g % len(VARIANTS)], seed=g)
        finished[e.state.mode] += 1
    assert sum(finished.values()) == 300 and finished[Mode.GAME_OVER] >= 290, finished


# ---------------------------------------------------------------- tkinter adapter (needs a display)
def test_tk_adapter_smoke(tmp_path):
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    root.withdraw()
    import tk_adapter
    spec = {"pieces": {"preset": "Classic"}}
    ctl = tk_adapter.TkinterController(Engine(spec, seed=1), root, spec=spec)
    try:
        for _ in range(5):
            ctl.start()                                    # repeated starts must not stack loops
        pending = root.tk.splitlist(root.tk.call("after", "info"))
        assert len(pending) == 1
        for _ in range(4):
            ctl.act(Action.PAUSE)
        for _ in range(5):
            root.update()
        ctl.save_to(tmp_path / "s.json")
        ctl.act(Action.HARD_DROP)
        ctl.load_from(tmp_path / "s.json")
        assert ctl.engine.state.pieces_spawned == 1
        while ctl.engine.state.mode is not Mode.GAME_OVER:
            ctl.act(Action.HARD_DROP)
        ctl.renderer.draw(ctl.engine)                      # game over draws an overlay, no crash
        ctl.new_game()
        assert ctl.engine.state.mode is Mode.RUNNING
    finally:
        ctl.quit()

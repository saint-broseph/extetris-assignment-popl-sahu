#!/usr/bin/env python3
"""
verify_piece.py -- verification of v1_core_system/piece.py.

Run as a script (prints a report, exit code 1 on any failure):
    python v1_core_system/verify_piece.py [--starter PATH]

or with pytest (the same checks, one test each):
    pytest v1_core_system/verify_piece.py

What is checked
  1. Catalogue counts: 110 fixed, 34 one-sided (7 + 27), 22 free; class sizes 7/2/9/9/6/1.
  2. Every piece is built through its constructor from invariants only, and the
     invariants read back from the built piece equal the constructor arguments.
  3. (bbox, hole signature, handedness) is unique, which resolves the v0.5 collision
     where (bbox, diagonal count) mapped 27 extended pieces onto only 11 keys.
  4. piece.py contains no boolean-matrix literal and no eval/exec (AST scan).
  5. Immutability, plus a regression test for v0 BUG-02 (rotation corrupting shared shapes).
  6. Rotation and mirror algebra for all 34 pieces.
  7. All 73 starter matrices in v0_starter/allextetrominoes.py are matched up to
     rotation. The starter file is parsed with `ast`, never imported or eval()'d,
     and the match is re-checked with numpy.rot90, an independent rotation.
  8. The starter's own labels (I, O, L, T, Gamma, S, Z) agree with Tetromino(letter).
  9. The classic pieces spawn in the standard flat-side-down orientations.
"""
from __future__ import annotations

import argparse
import ast
import copy
import itertools
import os
import pickle
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import piece as P  # noqa: E402
from piece import (ExTetromino, ExTetromino2x3, ExTetromino2x4, ExTetromino3x3,  # noqa: E402
                   ExTetromino3x4, ExTetromino4x4, Handedness, Piece, PieceSpecError, Tetromino)

STARTER = Path(os.environ.get("EXTETRIS_STARTER", HERE.parent / "v0_starter" / "allextetrominoes.py"))
CLASSES = (Tetromino, ExTetromino2x3, ExTetromino2x4, ExTetromino3x3, ExTetromino3x4, ExTetromino4x4)
EXPECTED_SIZES = {Tetromino: 7, ExTetromino2x3: 2, ExTetromino2x4: 9, ExTetromino3x3: 9,
                  ExTetromino3x4: 6, ExTetromino4x4: 1}
_RUNNER = False


class _Skip(Exception):
    pass


def _skip(msg: str) -> None:
    if _RUNNER:
        raise _Skip(msg)
    import pytest
    pytest.skip(msg)


def _say(*args: object) -> None:
    if _RUNNER:
        print("     ", *args)


def _flat(p: Piece) -> str:
    return str(p).replace("\n", "/")


def _build_all_via_constructors() -> list[Piece]:
    built = []
    for cls in CLASSES:
        for args in cls.variants():
            built.append(cls(args) if cls is Tetromino else cls(*args))
    return built


# ----------------------------------------------------------------------------
def test_1_catalogue_counts():
    stats = P.catalogue_stats()
    assert stats == {"fixed": 110, "one_sided": 34, "free": 22, "classic": 7, "extended": 27}, stats
    sizes = {cls: len(cls.all_pieces()) for cls in CLASSES}
    assert sizes == EXPECTED_SIZES, sizes
    assert len(Piece.all_pieces()) == 34 and len(ExTetromino.all_pieces()) == 27
    assert sum(p.orientation_count for p in Piece.all_pieces()) == 110
    _say(f"counts {stats}")
    _say("class sizes " + ", ".join(f"{c.__name__}={n}" for c, n in sizes.items()))


def test_2_constructive_instantiation_round_trip():
    built = _build_all_via_constructors()
    assert len(built) == 34
    assert len({p.shape.identity for p in built}) == 34, "two constructor calls gave the same piece"
    for cls in CLASSES:
        for args in cls.variants():
            p = cls(args) if cls is Tetromino else cls(*args)
            assert type(p) is cls
            if cls is Tetromino:
                assert p.edge_components == 1 and p.letter == args
                again = Tetromino.from_invariants(p.bbox, p.hole_signature, p.handedness)
                assert again == p, f"Tetromino.from_invariants disagrees for {args}"
            else:
                holes, hand = args
                assert p.edge_components > 1, f"{p.code} is edge-connected but in ExTetromino"
                assert p.bbox == cls.BBOX and p.hole_signature == holes and p.handedness == hand
                assert ExTetromino.create(f"{cls.BBOX[1]}x{cls.BBOX[0]}", holes, int(hand)) == p
    # Rotating the hole signature (the same cycle read from another start) is accepted.
    assert ExTetromino3x3((3, 2, 2, 3), "+") == ExTetromino3x3((2, 2, 3, 3), Handedness.PLUS)
    # Bad arguments fail loudly and list the valid choices.
    for bad in (lambda: ExTetromino3x3((1, 1, 1, 1), "+"), lambda: Tetromino("Q"),
                lambda: ExTetromino.create("5x5", (0, 0, 0, 0)), lambda: ExTetromino2x4((1, 2, 3), 0)):
        try:
            bad()
        except PieceSpecError:
            pass
        else:
            raise AssertionError("invalid constructor arguments were accepted")
    for abstract in (lambda: Piece(), lambda: ExTetromino((1, 1, 2, 2), "+")):
        try:
            abstract()
        except TypeError:
            pass
        else:
            raise AssertionError("an abstract class was instantiated")
    _say("34 constructor calls -> 34 distinct pieces; invariants round-trip; bad/abstract calls rejected")


def test_3_invariant_key_unique_and_v05_resolved():
    pieces = Piece.all_pieces()
    keys = Counter((p.edge_components == 1, p.bbox, p.hole_signature, p.handedness) for p in pieces)
    assert all(n == 1 for n in keys.values()), "v1 constructor key is ambiguous"
    groups = defaultdict(list)
    for p in ExTetromino.all_pieces():
        groups[(p.bbox, p.corner_pairs)].append(p)
    colliding = {k: v for k, v in groups.items() if len(v) > 1}
    assert len(groups) == 11 and len(colliding) == 7, (len(groups), len(colliding))
    for (bbox, diag), members in sorted(colliding.items()):
        refined = {(m.hole_signature, m.handedness) for m in members}
        assert len(refined) == len(members)
        _say(f"v0.5 key ({bbox[0]}x{bbox[1]}, diagonals={diag}) -> {len(members)} pieces, "
             f"separated by (holes, hand): " + ", ".join(m.code for m in members))
    _say(f"v0.5 key: 27 extended pieces -> {len(groups)} keys ({27 - len(groups)} pieces unreachable); "
         f"v1 key: 34 pieces -> {len(keys)} keys")


def _matrix_like(node: ast.AST) -> bool:
    """A 2-D list/tuple literal whose leaves are all bools or 0/1 ints, or a 1-D run of >= 3 bools."""
    if not isinstance(node, (ast.List, ast.Tuple)) or not node.elts:
        return False

    def leaf_ok(n):
        return isinstance(n, ast.Constant) and (n.value is True or n.value is False or n.value in (0, 1)) \
            and not isinstance(n.value, str)

    if all(isinstance(e, (ast.List, ast.Tuple)) and e.elts for e in node.elts) and len(node.elts) >= 2:
        return all(leaf_ok(x) for e in node.elts for x in e.elts)
    return len(node.elts) >= 3 and all(isinstance(e, ast.Constant) and isinstance(e.value, bool) for e in node.elts)


def test_4_no_hardcoded_matrices_or_eval():
    source = Path(P.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    literals = [n.lineno for n in ast.walk(tree) if _matrix_like(n)]
    evals = [n.lineno for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("eval", "exec")]
    arrays = [n.lineno for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "array"
              and n.args and isinstance(n.args[0], (ast.List, ast.Tuple))]
    assert not literals, f"matrix-like literals at lines {literals}"
    assert not evals, f"eval/exec at lines {evals}"
    assert not arrays, f"numpy.array(<literal>) at lines {arrays}"
    _say(f"AST scan of {Path(P.__file__).name}: 0 matrix literals, 0 eval/exec, 0 array(<literal>) calls")


def test_5_immutability_and_bug02_regression():
    s = Tetromino("S")
    for attempt in (lambda: setattr(s, "_turn", 1), lambda: setattr(s, "colour", "red"),
                    lambda: delattr(s, "_shape")):
        try:
            attempt()
        except AttributeError:
            pass
        else:
            raise AssertionError("a Piece attribute could be changed")
    spun = s
    for _ in range(7):
        spun = spun.rotated_cw()
    assert s.turn == 0 and spun is not s
    assert Tetromino("S") == s and Tetromino("S").cells == s.cells, "rotation leaked into a fresh piece"
    assert not Tetromino("S").same_shape(Tetromino("Z")), "S turned into Z (v0 BUG-02 is back)"
    m = s.to_matrix()
    try:
        m[0, 0] = not m[0, 0]
    except ValueError:
        pass
    else:
        raise AssertionError("to_matrix() returned a writable array")
    assert s.to_matrix() is not m and isinstance(s.cells, frozenset)
    assert copy.deepcopy(s) is s and pickle.loads(pickle.dumps(spun)) == spun
    assert hash(Tetromino("T").rotated_cw()) == hash(Tetromino("T").with_turn(1))
    _say("setattr/delattr blocked; rotation returns new objects; 7 turns of S leave a fresh S intact;")
    _say("matrices are read-only copies; deepcopy/pickle/hash consistent")


def test_6_rotation_and_mirror_algebra():
    twins = 0
    for p in Piece.all_pieces():
        assert p.turned(4) == p and p.rotated_cw().rotated_ccw() == p
        assert len({o.cells for o in p.orientations()}) == p.orientation_count in (1, 2, 4)
        assert all(o.hole_signature == p.hole_signature and o.handedness == p.handedness for o in p.orientations())
        m = p.mirror_image()
        assert type(m) is type(p) and m.bbox == p.bbox and m.mirror_image().same_shape(p)
        assert int(m.handedness) == -int(p.handedness)
        assert m.same_shape(p) == (p.handedness is Handedness.NONE)
        twins += not m.same_shape(p)
    assert twins == 24
    _say("turned(4) = identity, cw/ccw inverse, invariants equal in every orientation;")
    _say("mirror keeps class and bbox and flips hand; 24 pieces form 12 mirror pairs, 10 are symmetric")


def _load_starter(path: Path):
    source = path.read_text(encoding="utf-8")
    matrices = {}
    for node in ast.parse(source).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and re.fullmatch(r"Extetromino\d+", node.targets[0].id) and isinstance(node.value, ast.Call)):
            matrices[int(node.targets[0].id[len("Extetromino"):])] = np.array(ast.literal_eval(node.value.args[0]), dtype=bool)
    labels = {int(m[1]): m[2] for m in re.finditer(r"^\s*Extetromino(\d+)\s*=.*#\s*(\w+)", source, re.M)}
    return dict(sorted(matrices.items())), labels


def test_7_all_73_starter_matrices_match_up_to_rotation():
    if not STARTER.is_file():
        _skip(f"starter file not found at {STARTER}")
    before = STARTER.read_bytes()
    matrices, _ = _load_starter(STARTER)
    assert len(matrices) == 73, len(matrices)
    seen = defaultdict(list)
    for idx, mat in matrices.items():
        p = Piece.identify_matrix(mat)
        spawn = p.with_turn(0).to_matrix()
        assert any(r.shape == spawn.shape and np.array_equal(r, spawn) for r in (np.rot90(mat, k) for k in range(4))), \
            f"Extetromino{idx} does not rotate onto {p.code}"
        seen[p.code].append(idx)
    assert len(seen) == 34, f"starter covers {len(seen)} of 34 pieces"
    assert STARTER.read_bytes() == before, "the starter file was modified"
    mult = Counter(len(v) for v in seen.values())
    _say(f"73/73 starter matrices matched (numpy.rot90 cross-check); all 34 pieces covered; "
         f"{STARTER.relative_to(STARTER.parent.parent)} unchanged")
    _say("listed x4: {} pieces, x3: {}, x2: {}, x1: {}".format(mult[4], mult[3], mult[2], mult[1]))
    if _RUNNER:
        print()
        print(f"      {'code':14s} {'class':15s} {'spawn (rows split by /)':24s} starter indices")
        for p in Piece.all_pieces():
            print(f"      {p.name:14s} {type(p).__name__:15s} {_flat(p):24s} {seen[p.code]}")


def test_8_starter_labels_agree_with_tetromino_letters():
    if not STARTER.is_file():
        _skip(f"starter file not found at {STARTER}")
    matrices, labels = _load_starter(STARTER)
    checked = []
    for idx, label in labels.items():
        if label.upper() in ("I", "O", "T", "S", "Z", "L", "J", "GAMMA"):
            assert Piece.identify_matrix(matrices[idx]).same_shape(Tetromino(label)), f"Extetromino{idx} '{label}'"
            checked.append(f"{idx}:{label}")
    assert len(checked) == 9, checked  # 1-7 plus the two repeated I pieces (10, 11)
    _say("starter labels agree: " + " ".join(checked))


def test_9_classic_spawn_orientations():
    expected = {"I": "####", "O": "##/##", "T": ".#./###", "S": ".##/##.",
                "Z": "##./.##", "L": "..#/###", "J": "#../###"}
    got = {letter: _flat(Tetromino(letter)) for letter in Tetromino.LETTERS}
    assert got == expected, got
    _say("spawn orientations are flat side down: " + "  ".join(f"{k}={v}" for k, v in got.items()))


# ----------------------------------------------------------------------------
def main() -> int:
    global _RUNNER, STARTER
    ap = argparse.ArgumentParser(description="Verify v1_core_system/piece.py")
    ap.add_argument("--starter", type=Path, help="path to v0_starter/allextetrominoes.py")
    args = ap.parse_args()
    if args.starter:
        STARTER = args.starter.resolve()
    _RUNNER = True
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn)]
    failed = skipped = 0
    print(f"verify_piece.py: {len(tests)} checks on {Path(P.__file__).resolve()}")
    for name, fn in tests:
        try:
            print(f"[....] {name}")
            fn()
            print(f"[PASS] {name}")
        except _Skip as exc:
            skipped += 1
            print(f"[SKIP] {name}: {exc}")
        except Exception as exc:  # report every failure, keep going
            failed += 1
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed - skipped} passed, {failed} failed, {skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

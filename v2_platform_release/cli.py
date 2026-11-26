#!/usr/bin/env python3
"""
cli.py -- the ExTetris Variant Development Platform command line.

    python v2_platform_release/cli.py new "My Variant" [--template classic|chaos|zen|blank]
    python v2_platform_release/cli.py validate variants/corner_chaos.toml
    python v2_platform_release/cli.py play variants/corner_chaos.toml [--seed 7] [--customize]
    python v2_platform_release/cli.py simulate variants/corner_chaos.toml --games 100
    python v2_platform_release/cli.py package variants/corner_chaos.toml [--pyinstaller]
    python v2_platform_release/cli.py pieces [--preset Full]

No Python knowledge is needed: every error is explained in plain English.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from spec import CONDITIONS, SpecError, VariantSpec, dump_toml  # noqa: E402
from piece import Piece  # noqa: E402

REPO = HERE.parent

TEMPLATES = {
    "blank": {"variant": {"name": "", "version": "0.1", "authors": ["you"], "description": "Describe your game."},
              "pieces": {"preset": "Classic"}},
    "classic": {"variant": {"name": "", "version": "0.1", "authors": ["you"], "description": "A classic-style game."},
                "board": {"width": 10, "height": 20, "walls": "solid"}, "pieces": {"preset": "Classic"},
                "distribution": {"kind": "bag", "copies": 1},
                "levels": {"lines_per_level": 10, "base_ms": 1000, "factor": 0.9, "min_ms": 60},
                "physics": {"gravity": "naive_drop", "kicks": True, "preview": 3}, "theme": {"name": "dark"}},
    "chaos": {"variant": {"name": "", "version": "0.1", "authors": ["you"], "description": "All 34 pieces."},
              "board": {"width": 12, "height": 22, "walls": "wrap"}, "pieces": {"preset": "Full"},
              "distribution": {"kind": "adaptive", "base": "uniform", "drought_boost": 2.0},
              "physics": {"gravity": "cascade", "preview": 3},
              "triggers": [{"id": "faster", "when": {"lines_at_least": 30}, "set": {"levels.factor": 0.85}}]},
    "zen": {"variant": {"name": "", "version": "0.1", "authors": ["you"], "description": "Slow and forgiving."},
            "board": {"width": 14, "height": 24}, "pieces": {"preset": "Extended-Easy"},
            "distribution": {"kind": "bag", "copies": 2}, "levels": {"base_ms": 1400, "factor": 0.96, "min_ms": 400},
            "physics": {"hard_drop_locks": False, "preview": 5}, "theme": {"name": "light"}},
}
HEADER = """# ExTetris variant file. Edit the values, then run:
#   python v2_platform_release/cli.py validate {path}
# Sections: [variant] [board] [pieces] [distribution] [levels] [scoring] [physics] [theme] [controls] [[triggers]]
# Piece names: classic letters I O T S Z L J, or codes listed by `cli.py pieces --preset Full`.
"""


def _load(path: str) -> VariantSpec:
    try:
        return VariantSpec.from_toml(path)
    except SpecError as exc:
        print(f"PROBLEMS in {path}:")
        for e in exc.errors:
            print(f"  - {e}")
        print("\nFix these and run `validate` again.")
        raise SystemExit(1)


def cmd_new(args) -> int:
    slug = re.sub(r"[^a-z0-9]+", "_", args.name.lower()).strip("_") or "variant"
    path = Path(args.dir) / f"{slug}.toml"
    if path.exists() and not args.force:
        print(f"{path} already exists (use --force to overwrite).")
        return 1
    data = json.loads(json.dumps(TEMPLATES[args.template]))
    data["variant"]["name"] = args.name
    VariantSpec.from_dict(data)                       # templates are always valid
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_toml(data, HEADER.format(path=path.as_posix())), encoding="utf-8")
    print(f"Created {path} from the '{args.template}' template.\nNext: python v2_platform_release/cli.py validate {path.as_posix()}")
    return 0


def describe(spec: VariantSpec) -> str:
    engine = spec.build_engine(seed=0)
    r, lp = engine.rules, engine.level_policy
    probs = engine.distribution.probabilities()
    lines = [f"OK  '{spec.name}' v{spec.version} is a valid variant.",
             f"    board        {r.width} x {r.height}, {r.walls} walls, {r.gravity} gravity, rotation {r.rotation}"
             f"{' with kicks' if r.kicks else ''}",
             f"    pieces       {len(engine.family)} ({', '.join(p.name for p in engine.family)[:150]}"
             f"{'...' if len(engine.family) > 12 else ''})",
             f"    distribution {spec.section('distribution').get('kind', 'uniform')}; most likely: " +
             ", ".join(f"{Piece.from_code(c).name} {100 * p:.1f}%" for c, p in sorted(probs.items(), key=lambda kv: -kv[1])[:3]),
             f"    speed        level 0: {lp.gravity_ms(0)} ms, level 5: {lp.gravity_ms(5)} ms, level 10: "
             f"{lp.gravity_ms(10)} ms (new level every {lp.lines_per_level} lines)"]
    for t in spec.data.get("triggers", []):
        cond = " and ".join(f"{CONDITIONS[c]} reaches {v}" for c, v in t["when"].items())
        act = ", ".join(f"{p} becomes {v}" for p, v in t["set"].items())
        lines.append(f"    trigger      '{t['id']}': when {cond}, {act}")
    for w in spec.warnings:
        lines.append(f"    warning      {w}")
    lines.append(f"    fingerprint  {spec.sha256[:16]}")
    return "\n".join(lines)


def cmd_validate(args) -> int:
    print(describe(_load(args.toml)))
    return 0


def cmd_simulate(args) -> int:
    from simulator import simulate
    spec = _load(args.toml)
    report = simulate(spec, games=args.games, seed=args.seed, bot=args.bot, max_pieces=args.max_pieces)
    print(report.summary())
    if args.json:
        Path(args.json).write_text(json.dumps({
            "variant": report.variant, "games": report.games, "bot": report.bot, "pieces": report.pieces,
            "lines": report.lines, "scores": report.scores, "levels": report.levels, "capped": report.capped,
            "counts": dict(report.counts), "expected": report.expected, "verdicts": report.verdicts()}, indent=1))
        print(f"Raw results written to {args.json}")
    return 0


def cmd_play(args) -> int:
    spec = _load(args.toml)
    import tk_adapter                                  # tkinter is imported only here
    from customizer import attach_customizer
    engine = spec.build_engine(seed=args.seed)
    controller = tk_adapter.TkinterController(engine, spec=spec.engine_spec())
    customizer = attach_customizer(controller, spec)
    if args.customize:
        controller.root.after(200, customizer.open)
    controller.run()
    return 0


def cmd_package(args) -> int:
    from packager import build_package
    out = build_package(args.toml, args.out, pyinstaller=args.pyinstaller)
    print(f"Package ready: {out}")
    return 0


def cmd_pieces(args) -> int:
    from family import PieceFamily
    for p in PieceFamily.preset(args.preset):
        print(f"{p.name:14s} {type(p).__name__:15s} holes {p.hole_signature}  {str(p).replace(chr(10), ' / ')}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="extetris", description="ExTetris Variant Development Platform")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("new", help="create a variant file from a template")
    p.add_argument("name")
    p.add_argument("--template", choices=sorted(TEMPLATES), default="classic")
    p.add_argument("--dir", default=str(REPO / "variants"))
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_new)
    p = sub.add_parser("validate", help="check a variant and explain any problems")
    p.add_argument("toml")
    p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("play", help="play a variant (with an in-game Customizer)")
    p.add_argument("toml")
    p.add_argument("--seed", type=int)
    p.add_argument("--customize", action="store_true", help="open the Customizer at start")
    p.set_defaults(fn=cmd_play)
    p = sub.add_parser("simulate", help="balance check with a bot, no window")
    p.add_argument("toml")
    p.add_argument("--games", type=int, default=100)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--bot", choices=["greedy", "random"], default="greedy")
    p.add_argument("--max-pieces", type=int, default=300)
    p.add_argument("--json", help="also write raw results to this file")
    p.set_defaults(fn=cmd_simulate)
    p = sub.add_parser("package", help="build a shippable zip of the variant")
    p.add_argument("toml")
    p.add_argument("--out", default=str(REPO / "dist"))
    p.add_argument("--pyinstaller", action="store_true", help="also write a PyInstaller .spec")
    p.set_defaults(fn=cmd_package)
    p = sub.add_parser("pieces", help="list piece names and pictures")
    p.add_argument("--preset", default="Full", choices=["Classic", "Extended-Easy", "Full"])
    p.set_defaults(fn=cmd_pieces)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

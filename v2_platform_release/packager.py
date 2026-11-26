#!/usr/bin/env python3
"""
packager.py -- turn a validated variant into a shippable game.

    python v2_platform_release/packager.py variants/corner_chaos.toml [--out dist] [--pyinstaller]

Produces dist/<slug>-<version>.zip containing

    <slug>/
      run.bat, run.sh, run.py      double-click (Windows) / ./run.sh (macOS, Linux)
      variant.toml                 the validated variant
      VARIANT_GUIDE.md             generated docs: rules, speed table, pieces, triggers, controls
      README.txt, requirements.txt
      extetris/                    engine + adapter + spec modules (no tests)
      <slug>.spec                  (with --pyinstaller) a PyInstaller spec for a one-folder build

`python run.py --check` validates the variant and plays 3 headless bot games, so a
package can be smoke-tested without a display.
"""
from __future__ import annotations

import argparse
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from spec import CONDITIONS, VariantSpec  # noqa: E402

CORE_DIR = HERE.parent / "v1_core_system"
CORE_FILES = ["piece.py", "family.py", "distribution.py", "board.py", "state.py", "engine.py", "tk_adapter.py"]
PLATFORM_FILES = ["spec.py", "simulator.py"]

RUN_PY = '''#!/usr/bin/env python3
"""Launcher for this ExTetris variant.  python run.py [--seed N] [--check]"""
import argparse, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "extetris"))
from spec import SpecError, VariantSpec

ap = argparse.ArgumentParser(description="Play this ExTetris variant")
ap.add_argument("--seed", type=int)
ap.add_argument("--check", action="store_true", help="validate and play 3 headless bot games, then exit")
args = ap.parse_args()
try:
    spec = VariantSpec.from_toml(HERE / "variant.toml")
except SpecError as exc:
    print(exc)
    sys.exit(1)
if args.check:
    from simulator import simulate
    report = simulate(spec, games=3, max_pieces=60)
    print(f"CHECK OK: '{spec.name}' - 3 bot games, {sum(report.pieces)} pieces, {sum(report.lines)} lines")
    sys.exit(0)
import tk_adapter
tk_adapter.TkinterController(spec.build_engine(seed=args.seed), spec=spec.engine_spec()).run()
'''
RUN_BAT = '@echo off\r\ncd /d "%~dp0"\r\npython run.py %*\r\nif errorlevel 1 pause\r\n'
RUN_SH = '#!/bin/sh\ncd "$(dirname "$0")"\nexec python3 run.py "$@"\n'
PYI_SPEC = '''# PyInstaller spec for "{name}".  Build with:  pyinstaller {slug}.spec
# Result: dist/{slug}/{slug}(.exe) -- a one-folder build that needs no Python install.
a = Analysis(["run.py"], pathex=["extetris"],
             datas=[("variant.toml", "."), ("VARIANT_GUIDE.md", "."), ("extetris", "extetris")],
             hiddenimports={modules})
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="{slug}", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="{slug}")
'''


def variant_guide(spec: VariantSpec) -> str:
    engine = spec.build_engine(seed=0)
    r, lp, sc = engine.rules, engine.level_policy, engine.scoring
    probs = engine.distribution.probabilities()
    keys = engine.config["ui"]["keys"]
    meta = spec.section("variant")
    out = [f"# {spec.name} (v{spec.version})", "", meta.get("description", ""), "",
           f"*By {', '.join(meta.get('authors', [])) or 'unknown'} - variant fingerprint `{spec.sha256[:16]}`*", "",
           "## How to play", "", "- **Windows:** double-click `run.bat`", "- **macOS / Linux:** run `./run.sh`",
           "- Needs Python 3.11+ with `numpy` (`pip install -r requirements.txt`).", "",
           "| Action | Key |", "|---|---|"]
    out += [f"| {k.replace('_', ' ')} | `{v}` |" for k, v in keys.items()]
    out += ["", "## Rules", "", "| Setting | Value |", "|---|---|",
            f"| Board | {r.width} x {r.height} |",
            f"| Walls | {'wrap around (left and right edges are joined)' if r.wrap else 'solid'} |",
            f"| Line-clear gravity | {'cascade: loose groups fall and can chain' if r.gravity == 'cascade' else 'classic: rows above drop down'} |",
            f"| Rotation | {r.rotation}{' with wall kicks' if r.kicks else ''} |",
            f"| Hard drop | {'locks immediately' if r.hard_drop_locks else 'lands, then locks on the next gravity step'} |",
            f"| Next pieces shown | {r.preview} |",
            f"| Game over | {'a new piece cannot appear' if r.game_over == 'block_out' else f'a block locks in the top {r.danger_rows} rows'} |",
            "", "## Speed", "", f"A new level every **{lp.lines_per_level} lines**.", "",
            "| Level | Fall time per row |", "|---|---|"]
    out += [f"| {lvl} | {lp.gravity_ms(lvl)} ms |" for lvl in (0, 1, 2, 3, 5, 8, 10, 15, 20)]
    out += ["", "## Scoring", "", f"Lines cleared at once -> points (times level + 1): "
            + ", ".join(f"{i}: {p}" for i, p in enumerate(sc.line_points) if i),
            f"Chain bonus {sc.chain_bonus}; soft drop {sc.soft_drop}/row; hard drop {sc.hard_drop}/row.", "",
            f"## Pieces ({len(engine.family)})", "", "| Piece | Shape | Chance |", "|---|---|---|"]
    for p in engine.family:
        out.append(f"| `{p.name}` | `{str(p).replace(chr(10), ' / ')}` | {100 * probs[p.code]:.1f}% |")
    triggers = spec.data.get("triggers", [])
    if triggers:
        out += ["", "## Special events", ""]
        for t in triggers:
            cond = " and ".join(f"{CONDITIONS[c]} reaches {v}" for c, v in t["when"].items())
            out.append(f"- **{t['id']}**: when {cond}, " + ", ".join(f"`{k}` becomes `{v}`" for k, v in t["set"].items()))
    return "\n".join(out) + "\n"


def build_package(toml_path: str | Path, out_dir: str | Path = "dist", *, pyinstaller: bool = False) -> Path:
    spec = VariantSpec.from_toml(toml_path)                 # refuses invalid variants
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / spec.slug
        (root / "extetris").mkdir(parents=True)
        for name in CORE_FILES:
            shutil.copy2(CORE_DIR / name, root / "extetris" / name)
        for name in PLATFORM_FILES:
            shutil.copy2(HERE / name, root / "extetris" / name)
        shutil.copy2(toml_path, root / "variant.toml")
        (root / "VARIANT_GUIDE.md").write_text(variant_guide(spec), encoding="utf-8")
        (root / "run.py").write_text(RUN_PY, encoding="utf-8")
        (root / "run.bat").write_bytes(RUN_BAT.encode())
        (root / "run.sh").write_text(RUN_SH, encoding="utf-8")
        (root / "requirements.txt").write_text("numpy>=1.24\n", encoding="utf-8")
        (root / "README.txt").write_text(
            f"{spec.name} v{spec.version} - an ExTetris variant.\n\nWindows: double-click run.bat\n"
            "macOS/Linux: ./run.sh\nRules and pieces: VARIANT_GUIDE.md\n", encoding="utf-8")
        if pyinstaller:
            mods = [m[:-3] for m in CORE_FILES + PLATFORM_FILES]
            (root / f"{spec.slug}.spec").write_text(
                PYI_SPEC.format(name=spec.name, slug=spec.slug, modules=mods), encoding="utf-8")
        target = out_dir / f"{spec.slug}-{spec.version}.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(root.rglob("*")):
                if f.is_file():
                    info = zipfile.ZipInfo.from_file(f, f.relative_to(root.parent).as_posix())
                    if f.name in ("run.sh", "run.py"):
                        info.external_attr = (0o755 | stat.S_IFREG) << 16
                    with open(f, "rb") as fh:
                        zf.writestr(info, fh.read(), zipfile.ZIP_DEFLATED)
    return target


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Package an ExTetris variant")
    ap.add_argument("toml")
    ap.add_argument("--out", default=str(HERE.parent / "dist"))
    ap.add_argument("--pyinstaller", action="store_true")
    args = ap.parse_args(argv)
    print(f"Package ready: {build_package(args.toml, args.out, pyinstaller=args.pyinstaller)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

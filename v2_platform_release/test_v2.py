"""
test_v2.py -- pytest suite for the ExTetris v2 platform layer.

    pytest v2_platform_release
"""
from __future__ import annotations

import json
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from spec import SpecError, SpecValidator, VariantSpec, dump_toml  # noqa: E402
from simulator import simulate  # noqa: E402
from packager import build_package  # noqa: E402
import cli  # noqa: E402

VARIANTS = sorted((REPO / "variants").glob("*.toml"))
SHOWCASE = ["classic_1984", "corner_chaos", "zen_sandbox"]


def _errors(data):
    v = SpecValidator(data)
    v.validate()
    return v.errors


def test_showcase_variants_exist_and_validate():
    names = {p.stem for p in VARIANTS}
    assert set(SHOWCASE) <= names
    for p in VARIANTS:
        spec = VariantSpec.from_toml(p)
        assert spec.build_engine(seed=1).state.mode.value == "RUNNING"
    chaos = VariantSpec.from_toml(REPO / "variants/corner_chaos.toml").build_engine(seed=0)
    assert len(chaos.family) == 34 and chaos.rules.walls == "wrap" and type(chaos.distribution).__name__ == "AdaptiveDistribution"
    zen = VariantSpec.from_toml(REPO / "variants/zen_sandbox.toml").build_engine(seed=0)
    assert (zen.rules.width, zen.rules.height, len(zen.family)) == (14, 24, 15) and zen.config["triggers"]


@pytest.mark.parametrize("data, fragment", [
    ({"board": {"widht": 10}}, "Did you mean 'width'"),
    ({"board": {"height": 3}}, "whole number from 8 to 128"),
    ({"bord": {}}, "Did you mean 'board'"),
    ({"pieces": {"preset": "Everything"}}, "must be one of"),
    ({"pieces": {"exclude": ["Q"]}}, "unknown piece names"),
    ({"distribution": {"kind": "weighted"}}, "also needs 'weights'"),
    ({"levels": {"base_ms": 300, "min_ms": 500}}, "cannot be slower"),
    ({"theme": {"colors": {"block": "blue"}}}, "must look like"),
    ({"triggers": [{"id": "a", "when": {"python": 1}, "set": {"board.walls": "wrap"}}]}, "not a condition"),
    ({"triggers": [{"id": "a", "when": {"lines_at_least": 1}, "set": {"board.width": 12}}]}, "board size cannot change"),
    ({"triggers": [{"id": "a", "when": {"lines_at_least": 1}, "set": {"physics.gravity": "magic"}}]}, "must be one of"),
    ({"pieces": {"preset": "Classic", "exclude": ["I", "O", "T", "S", "Z", "L", "J"]}}, "engine rejected"),
])
def test_validator_plain_english(data, fragment):
    errors = _errors(data)
    assert errors and any(fragment in e for e in errors), errors


def test_bad_toml_syntax_is_explained(tmp_path):
    f = tmp_path / "broken.toml"
    f.write_text("[board\nwidth = ")
    with pytest.raises(SpecError, match="not valid TOML"):
        VariantSpec.from_toml(f)


def test_dump_toml_round_trip():
    for p in VARIANTS:
        data = tomllib.loads(p.read_text())
        assert tomllib.loads(dump_toml(data)) == data
    for t in cli.TEMPLATES.values():
        assert tomllib.loads(dump_toml(t)) == t


def test_mixture_and_weighted_specs():
    spec = VariantSpec.from_dict({"pieces": {"preset": "Full"}, "distribution": {"kind": "mixture", "parts": [
        {"weight": 0.7, "kind": "bag"}, {"weight": 0.3, "kind": "weighted", "weights": {"I": 5}}]}})
    probs = spec.build_engine(seed=0).distribution.probabilities()
    assert sum(probs.values()) == pytest.approx(1.0) and probs["T1x4.H0000.0"] > probs["T2x2.H0000.0"]


def test_trigger_translation_fires_in_engine():
    spec = VariantSpec.from_dict({"triggers": [{"id": "w", "when": {"pieces_at_least": 2},
                                               "set": {"board.walls": "wrap", "levels.base_ms": 500}}]})
    e = spec.build_engine(seed=3)
    from state import Action
    for _ in range(3):
        e.apply_action(Action.HARD_DROP)
        e.tick(0)
    assert e.rules.walls == "wrap" and e.level_policy.base_ms == 500


@pytest.mark.parametrize("name", SHOWCASE)
def test_simulate_showcase(name):
    report = simulate(VariantSpec.from_toml(REPO / f"variants/{name}.toml"), games=8, max_pieces=150)
    assert len(report.pieces) == 8 and sum(report.lines) > 0
    assert report.max_frequency_deviation() < 0.06 and report.verdicts()


def test_with_changes_and_customizer_targets():
    spec = VariantSpec.from_toml(REPO / "variants/classic_1984.toml")
    changed = spec.with_changes({"board.walls": "wrap", "physics.preview": 4})
    assert changed.build_engine(seed=0).rules.walls == "wrap"
    with pytest.raises(SpecError):
        spec.with_changes({"physics.preview": 99})


def test_cli_new_validate_simulate(tmp_path):
    py, cli_path = sys.executable, str(HERE / "cli.py")
    run = lambda *a: subprocess.run([py, cli_path, *a], capture_output=True, text=True, timeout=300)
    out = run("new", "Test Game", "--template", "zen", "--dir", str(tmp_path))
    assert out.returncode == 0, out.stderr
    toml = tmp_path / "test_game.toml"
    v = run("validate", str(toml))
    assert v.returncode == 0 and "is a valid variant" in v.stdout
    s = run("simulate", str(toml), "--games", "3", "--max-pieces", "50", "--json", str(tmp_path / "r.json"))
    assert s.returncode == 0 and "verdict" in s.stdout and json.loads((tmp_path / "r.json").read_text())["games"] == 3
    toml.write_text(toml.read_text().replace("width = 14", "width = 2"))
    bad = run("validate", str(toml))
    assert bad.returncode == 1 and "PROBLEMS" in bad.stdout and "whole number from 4 to 64" in bad.stdout


def test_package_is_self_contained(tmp_path):
    z = build_package(REPO / "variants/zen_sandbox.toml", tmp_path, pyinstaller=True)
    with zipfile.ZipFile(z) as zf:
        names = set(zf.namelist())
        zf.extractall(tmp_path / "x")
    for f in ("run.py", "run.bat", "run.sh", "variant.toml", "VARIANT_GUIDE.md", "zen_sandbox.spec",
              "extetris/engine.py", "extetris/spec.py"):
        assert f"zen_sandbox/{f}" in names
    assert not any("test_" in n or "verify_" in n for n in names)
    guide = (tmp_path / "x/zen_sandbox/VARIANT_GUIDE.md").read_text()
    assert "Special events" in guide and "bonus-cascade" in guide
    check = subprocess.run([sys.executable, str(tmp_path / "x/zen_sandbox/run.py"), "--check"],
                           capture_output=True, text=True, timeout=300, cwd=tmp_path)
    assert check.returncode == 0 and "CHECK OK" in check.stdout, check.stderr
    with pytest.raises(SpecError):
        bad = tmp_path / "bad.toml"
        bad.write_text("[board]\nwidth = 1\n")
        build_package(bad, tmp_path)


def test_notebook_is_valid_nbformat4():
    nb = json.loads((HERE / "Variant_Designer_Studio.ipynb").read_text())
    assert nb["nbformat"] == 4 and len(nb["cells"]) >= 10
    code = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    compile(code.replace("# @param", "#"), "notebook", "exec")
    assert "# @param" in code and "dump_toml" in code and "simulate(" in code


def test_play_with_customizer_smoke():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    import tk_adapter
    from customizer import attach_customizer
    spec = VariantSpec.from_toml(REPO / "variants/corner_chaos.toml")
    ctl = tk_adapter.TkinterController(spec.build_engine(seed=1), root, spec=spec.engine_spec())
    try:
        cust = attach_customizer(ctl, spec)
        ctl.engine.request_update("rules.walls", "solid")     # what Apply does
        cust.changes["board.walls"] = "solid"
        assert ctl.engine.rules.walls == "wrap"                 # not before the next tick boundary
        ctl.start()
        import time
        end = time.time() + 0.3
        while time.time() < end:                               # let the controller's frames run
            root.update()
            time.sleep(0.01)
        assert ctl.engine.rules.walls == "solid"
        assert spec.with_changes(cust.changes).build_engine(seed=0).rules.walls == "solid"
        assert ctl.renderer.colors["block"] == "#c45cff"       # theme colour override from the TOML
    finally:
        ctl.quit()

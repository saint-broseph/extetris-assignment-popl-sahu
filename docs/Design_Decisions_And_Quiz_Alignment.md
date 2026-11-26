# Design Decisions and Quiz Alignment — Traceability Matrix

This document traces every requirement and quiz answer to the module, class and test that satisfy it. Test names are pytest node names; run any of them with `python -m pytest <file>::<test>`.

| Part | Source | Status |
|---|---|---|
| A | Assignment specification PDF, every requirement (§1.2–§3.2) | **Complete**: traced from the PDF |
| B | Starter `engine.py`, every line marked "Programmable" | **Complete**: traced from the source |
| C | v0 audit: 23 bugs | **Complete** |
| D | Moodle starter quiz: Q1–Q3 + Q4's 11 technical-specification answers | **Complete**: each answer checked against the delivered code (status: Met / Partly met) |
| E | Feature → module → test index | **Complete** |

---

## A. Assignment specification → implementation

| # | Spec § | Requirement (paraphrased) | Design decision | Module · class | Verified by |
|---|---|---|---|---|---|
| A1 | 1.2 | A class hierarchy giving application programmers an API to build an ExTetris engine by instantiating and extending classes | Layered library; every policy is an injectable, subclassable class | `v1_core_system/*` · `Piece`, `PieceFamily`, `Distribution`, `Rules`, `Scoring`, `LevelPolicy`, `Engine` | `test_v1.py` (23 tests); `docs/api/` |
| A2 | 2 | Condense the hard-coded pieces into subclasses instantiated by parameters (e.g. "4x2" shapes) | Bounding-box subclasses constructed from invariants | `piece.py` · `Tetromino`, `ExTetromino2x3/2x4/3x3/3x4/4x4` | `verify_piece.py` tests 2, 4; `test_all_34_pieces` |
| A3 | 2 | Choose the subclass/constructor design "after some experimentation" | v0.5 key `(bbox, diagonals)` tried, proven ambiguous, replaced by `(bbox, holes, handedness)` | `v0.5_failed_attempt/piece_v05.py` → `piece.py` | `verify_v05.py` (proof); `verify_piece.py` test 3 |
| A4 | 2 | `shape` provides dynamics inherited by all pieces; constructors overridden per subclass | Rotation/mirror/matrix dynamics in abstract `Piece`; each branch overrides `__new__` | `piece.py` · `Piece.turned/rotated_cw/mirror_image`; `Tetromino.__new__`, `ExTetromino.__new__` | `verify_piece.py` test 6 |
| A5 | 2.1 | Entity relationships, division of labour, flexibility without programming prowess | UML + layered config; designers use TOML only | `docs/Design_Document_UML.md`; `v2_platform_release/spec.py` | `test_v2.py::test_showcase_variants_exist_and_validate` |
| A6 | 2.2 | Candid AI log: prompts and responses verbatim, interpretation, plan, implementation, outcome, modifications, trade-offs | 8-point log, Parts 1 and 2 | `docs/AI_Interaction_Log.md`, `docs/AI_Interaction_Log_Part2.md` | manual review |
| A7 | 2.2 | Compare AI-assisted effort with effort without AI | Quantitative + qualitative comparison | `docs/Continued_Development_Report.md` §7 | — |
| A8 | 3 | A bundle with build/run scripts and docs, so a designer can release a variant without programming expertise (Jupyter/Colab analogy) | CLI + notebook + packager + root build scripts | `cli.py`, `Variant_Designer_Studio.ipynb`, `packager.py`, `Makefile`, `build.sh`, `build.bat` | `test_cli_new_validate_simulate`, `test_package_is_self_contained`, `test_notebook_is_valid_nbformat4` |
| A9 | 3.1 | Design documents with UML graphics | Mermaid UML, all diagrams parser-validated | `docs/Design_Document_UML.md`, `docs/architecture_v1_blueprint.md` | Mermaid parse check (0 errors) |
| A10 | 3.1 | API documentation | Generated from docstrings | `docs/api/` (pdoc) | — |
| A11 | 3.1 | Game Programmer's Manual | Non-programmer manual + Python appendix | `docs/Game_Programmers_Manual.md` | — |
| A12 | 3.2 (1) | No piece initialised from matrix data; a hierarchy classified by shapes, bounding boxes and landing holes | 110 orientations generated; pieces selected by `(bbox, hole_signature, handedness)` | `piece.py` · `_grow_fixed_shapes`, `ShapeInfo`, `_landing_holes` | `verify_piece.py` test 4 (AST: 0 matrix literals), test 7 (73/73 starter matrices) |
| A13 | 3.2 (2) | Replace "repeat an index to raise probability" with a functional-OO distribution class | Immutable distributions with pure `weights(history)`; combinators | `distribution.py` · 6 classes + `mix` | `test_uniform_is_fair_per_piece_and_fixes_starter_bias`, `test_bag_gives_each_piece_once_per_bag`, `test_adaptive_shortens_droughts_and_mixture_sums`, `test_distributions_are_deterministic_per_seed` |
| A14 | 4 | Use the quiz to record, review and revise the design and plan | Part D below | this file | — |

---

## B. Starter "Programmable" points → v1/v2 settings

| Starter `engine.py` | Comment in the starter | Now | Designer key |
|---|---|---|---|
| L26–31 `extetromino_distribution=range(1,8)` | "Programmable: pass a different parameter… repeat their index" | `PieceFamily` + `Distribution` | `[pieces]`, `[distribution]` |
| L33 window title | "Programmable, inconsequential" | `TkinterController` title from the variant name | `[variant] name` |
| L34–35 width/height | "Essential and programmable" | `Rules.width/height` | `[board] width, height` |
| L38 `wrap=tk.CHAR` | "please find some way not to let it wrap" | Canvas renderer; no Text widget | `[theme] cell_px` |
| L41–43 bg/fg/font | "programmable" | Themes + colour overrides | `[theme] name, colors` |
| L48–53 key bindings | "semi-fixed: change by providing a new callback" | Key map from config | `[controls]` |
| L56–57, L162–166 move-down duration, speed-up/slow-down | "fixed, but its progression programmable" | `LevelPolicy` (threshold crossing, clamped) | `[levels]` |
| L59 `default_cursor` | "Programmable. Where the new piece appears" | `Rules.spawn_position` | `[physics] spawn_column, spawn_row` |
| L73–74 every method | "programmable (replaceable)" | Policies are injectable classes | Appendix A10 of the Manual |
| L138 `speed_up()` every 100 lines | "programmable" | `LevelPolicy.lines_per_level` | `[levels] lines_per_level` |

---

## C. v0 audit bugs → fixes

| Bug | Fix (module) | Regression test |
|---|---|---|
| BUG-01 left-wall wrap | Explicit bounds; deliberate `wrap` walls (`board.py`) | `test_solid_walls_block_and_wrap_walls_wrap` |
| BUG-02 rotation mutates templates | Immutable `Piece` (`piece.py`) | `verify_piece.py` test 5 |
| BUG-03 Down while paused stacks timers | Engine mode guard + single controller clock | `test_pause_ignores_ticks_and_input`, `test_tk_adapter_smoke` |
| BUG-04 About freezes the game | `_paused_dialog` restores the previous mode (`tk_adapter.py`) | `test_tk_adapter_smoke` (indirect) |
| BUG-05 game over broken | `Mode.GAME_OVER` + overlay + `RESET` | `test_tk_adapter_smoke`, `test_300_simulated_games` |
| BUG-06 `% 100` speed-up skip | `LevelPolicy.level_for(total)` | `test_level_policy_threshold_crossing_and_clamp` |
| BUG-07 speed reaches 0 ms | `min_ms` clamp | same |
| BUG-08/09/10 `eval`, index 0, bad input | Code-based lookup, validators, no `eval` | `verify_piece.py` test 4, `test_validator_plain_english` |
| BUG-11 distribution bias | Per-piece probabilities, seeded RNG | `test_uniform_is_fair_per_piece_and_fixes_starter_bias` |
| BUG-12/22 editable board, glyph width | Canvas rectangles | `test_tk_adapter_smoke` |
| BUG-13/14 implicit imports | Explicit imports; layer test | `test_engine_has_zero_tkinter` |
| BUG-15 constructor runs `mainloop` | `TkinterController.run()` | `test_tk_adapter_smoke` |
| BUG-16 Save saves screen text | Hashed JSON save/resume | `test_save_resume_with_hash_verification` |
| BUG-17–21, 23 minor | Fixed by construction | covered by the suites above |

---

## D. Moodle starter quiz → implementation

Answers are the team's submitted quiz answers (2026-11-26), quoted verbatim. Each row was checked against the code in this repository.

- **Met:** the repository does what the answer says.
- **Partly met:** the answer claims more than is implemented. The Note says exactly what differs, so the answer or the code can be brought into line.

| Q | Submitted answer (verbatim) | Implementation (module · class / symbol) | Evidence (tests / artefacts) | Status |
|---|---|---|---|---|
| **Q1** System vs. Platform | Envisaged as an ExTetris Game Variant Development Platform with an ExTetris Programming System (Python class library with an API) embedded inside it as a subset. Platform is required so non-programmers can design/release variants (like on Jupyter/Colab); system is built first so a usable API is delivered even if the platform is incomplete. | System: `v1_core_system/` (`piece`, `family`, `distribution`, `board`, `state`, `engine`, `tk_adapter`). Platform: `v2_platform_release/` (`spec`, `cli`, `simulator`, `customizer`, `packager`, `Variant_Designer_Studio.ipynb`), `variants/`, root build scripts. Built in that order (Phase 3 → Phase 4). | `test_v1.py` 23/23 passed *before* `v2_platform_release/` existed; `test_package_is_self_contained` (the platform ships the system as a subset); `Design_Document_UML.md` §1 | **Met** |
| **Q2** Design thinking flow | Both, in a cyclic manner (top-down ↔ bottom-up). | Top-down: `architecture_v1_blueprint.md` rev 1.0 before coding. Bottom-up: layers built and verified L0 → L5 → platform. Feedback: rev 1.1 changed the plan after implementation (`Rules`/`Scoring`/`LevelPolicy` moved into `state.py`; `VariantSpec` moved to the platform). | Blueprint revision log; `verify_piece.py` 9/9 before `family.py`; `Continued_Development_Report.md` §4–6 | **Met** |
| **Q3** Paradigm | Bottom-up, Modular, Imperative-OO. | Layered modules with downward-only imports; imperative engine state machine (`Engine._step_down/_lock/_spawn`); abstract classes + polymorphism (`Piece`, `Distribution`); composition in `Engine`; functional elements where the spec asks for them (immutable values, pure `weights()`) | `test_engine_has_zero_tkinter` (module boundary); `Design_Document_UML.md` §4 | **Met** |
| **Q4.1** Languages | Python 3.11+ only (matches starter code, built-in `tomllib`, fits Jupyter model); TOML (specs), Markdown/Mermaid (docs), bash/batch/Makefile (build/run). | Python everywhere (`tomllib` in `spec.py`, `engine.load_spec`); `variants/*.toml`; `docs/*.md` with Mermaid; `build.sh`, `build.bat`, `Makefile` | Suites run on Python 3.11.18 and 3.12.3; all Mermaid blocks parser-validated; `make notebook-check` / `make package` run in the sandbox | **Met** |
| **Q4.2** Full-fledged vs scripting; infrastructure | Python is full-fledged/interpreted (treated as scripting for infrastructure); bash/batch/make are glue. Requires CPython 3.11+ with pip/venv, `numpy`, Tcl/Tk runtime for `tkinter`, `PyInstaller`, `pytest`, and `pdoc`. | `numpy` (`piece.to_matrix`), Tk (`tk_adapter`, `customizer`), `pytest` (`test_v1/test_v2`), `pdoc` (`docs/api/`), PyInstaller (`packager.py --pyinstaller` writes `<slug>.spec`); build scripts `pip install numpy pytest` | 48 pytest; `docs/api/` generated; packages built with `.spec` files | **Partly met.** The PyInstaller spec is generated but no executable has been built yet (`pyinstaller <slug>.spec`). The build scripts use `pip` but don't create a venv. |
| **Q4.3** Class hierarchy | `Piece` (abstract, immutable) → `Tetromino` (7) & `ExTetromino` (27) → `ExTetromino2x3`, `2x4`, `3x3`, `3x4`, `4x4`. Supporting classes: `PieceFamily`, `Distribution`, `Board`, `Rules`, `Scoring`, `LevelPolicy`, `GameState`, `Engine`, `Renderer`, `Controller`, `VariantSpec`. `Engine` decoupled from `tkinter`. CLI platform (`new/validate/play/simulate/docs/package`) on top. | `piece.py` (hierarchy exactly as stated); `family.py`, `distribution.py`, `board.py`, `state.py`, `engine.py`; Renderer/Controller = `tk_adapter.TkinterRenderer` / `TkinterController`; `VariantSpec` = `v2_platform_release/spec.py`; CLI = `cli.py` | `verify_piece.py` tests 1–2 (sizes 7/27 = 2+9+9+6+1); `test_engine_has_zero_tkinter`; `test_cli_new_validate_simulate` | **Partly met.** There is no `docs` CLI command: API docs come from `pdoc` (see `Design_Document_UML.md`), and the CLI's sixth command is `pieces`. `Renderer`/`Controller` exist as the concrete Tkinter classes; there are no separate abstract base classes. |
| **Q4.4** Count & inclusion/exclusion | 34 chiral pieces (7 classic + 27 extended; verified 110 fixed orientations, 34 up to rotation, 22 free). Generated constructively, not hard-coded. Included/excluded by class, property, or ID; 3 presets: `Classic` (7), `Extended-Easy` (15), `Full` (34). | `piece._grow_fixed_shapes`, `catalogue_stats`; `family.PieceFamily.filter/include/exclude`; `CLASSIC`, `EXTENDED_EASY`, `FULL`; TOML `[pieces]` | `verify_piece.py` tests 1, 4 (0 matrix literals); `test_all_34_pieces`; `test_presets`; `test_filters`; `scripts/explore_polyominoes.py` (110/34/22, OEIS-matched) | **Met** |
| **Q4.5** Subclassification & criteria | Set operations on immutable `PieceFamily`; instantiated via subclass constructor (`connectivity` → `bounding box`), selected uniquely by `(landing-hole signature, handedness)`. API exposes 5+ criteria; player UI exposes 3 + presets. | `PieceFamily` (`union/intersection/include/exclude`, `\| & -`); `Tetromino` vs `ExTetromino` (connectivity) → `ExTetromino<bbox>` → `(holes, hand)`; API `filter()` has 6 criteria (category, connectivity, bbox, max_holes, handedness, ids); TOML exposes all 6 | `test_set_algebra`; `verify_piece.py` test 3 (34 unique keys; v0.5 ambiguity resolved); `verify_v05.py` | **Partly met.** The API (6 criteria) and TOML (6) match. The notebook exposes preset + add/remove-by-ID; the in-game Customizer changes rules, not pieces. "3 + presets" fits the notebook only if you count preset, add and remove. |
| **Q4.6** Probability distribution | Seeded functional-OO `Distribution` objects (`Uniform`, `Weighted`, `ByProperty`, `Bag`, `Adaptive`, plus mixtures), removing the starter's up-to-4× orientation bias. | `distribution.py`: `UniformDistribution`, `WeightedDistribution`, `ByPropertyDistribution`, `BagDistribution`, `AdaptiveDistribution`, `MixtureDistribution`/`mix`; seeded `random.Random` owned by `Engine` | `test_uniform_is_fair_per_piece_and_fixes_starter_bias` (starter ratio 4.0 → 1.0); `test_bag_gives_each_piece_once_per_bag`; `test_adaptive_shortens_droughts_and_mixture_sums`; `test_distributions_are_deterministic_per_seed` | **Met** |
| **Q4.7** Levels & dynamic speed | Lines map to level (default: every 10 lines), level maps to gravity interval (`1000 ms * 0.9^level`), applied at safe tick boundaries—fixing the `% 100` skip bug. | `state.LevelPolicy.level_for(total_lines)`, `gravity_ms(level)` (clamped by `min_ms`); `Engine.tick` re-reads the interval each step; runtime speed changes queued by `request_update` and applied at the next tick | `test_level_policy_threshold_crossing_and_clamp` (98→102 crosses level 10; 1000/900/810 ms); `test_runtime_updates_apply_only_at_tick_boundary` | **Met** |
| **Q4.8** Layered configuration | `defaults -> TOML spec -> player settings -> runtime changes`. Commented template + plain-English validator + restricted event triggers (arbitrary code only via Python hooks). | `engine.DEFAULTS`, `PLAYER_KEYS`, `RUNTIME_KEYS`, `_effective()`; `cli.py new` writes a commented template; `spec.SpecValidator`; triggers: `TRIGGER_CONDITIONS` + `spec.TRIGGER_TARGETS`; Python extension by subclassing (`Game_Programmers_Manual.md` §10) | `test_layered_config_and_restrictions`; `test_validator_plain_english` (12 cases); `test_triggers_fire_once_and_are_restricted`; `test_trigger_translation_fires_in_engine` | **Met.** "Python hooks" means the Python API (subclass a `Distribution`/`Scoring`/`LevelPolicy`). There is no plug-in registry that TOML can name. |
| **Q4.9** Physics flexibility | Configurable: board size, piece size/adjacency, speeds, rotation, spawn, `solid` vs `wrap` walls, `naive_drop` vs `cascade` gravity, game-over rule. Fixed: square cells, orthogonal grid, whole-cell moves, 90° rotations. | `state.Rules` (width, height, walls, rotation, kicks, gravity, spawn_row/col, game_over, danger_rows, hard_drop_locks, preview); `LevelPolicy` (speeds); `board.Board` (wrap, cascade); adjacency choice via `connectivity` filter (edge-only = classic) | `test_solid_walls_block_and_wrap_walls_wrap`; `test_naive_vs_cascade_gravity`; `test_scoring_and_rules_validation`; `test_300_simulated_games` (5 physics combinations) | **Partly met.** Piece size is fixed at 4 cells (`CELL_COUNT = 4`; the uniqueness proof covers n = 4 only). Adjacency can be restricted (edge-only vs corner pieces) but not redefined. The "Fixed" list is accurate. |
| **Q4.10** Game states, suspension & resumption | Immutable `GameState` replaced on each tick/action; pause cancels/restarts timer cleanly; JSON save/resume with variant SHA-256 hash check; starter pause, rotation, and game-over bugs fixed. | `state.GameState` (frozen) replaced by `Engine`; pause = `Mode.PAUSED` (tick and input ignored) with the controller's single `after()` loop, which `start()` cancels before rescheduling; `Engine.save/resume` (variant hash + payload SHA-256) | `test_pause_ignores_ticks_and_input`; `test_tk_adapter_smoke` (1 pending timer after 5 `start()`s; game-over overlay, New Game); `test_save_resume_with_hash_verification`; `verify_piece.py` test 5 (rotation/S→Z bug) | **Met (mechanism differs slightly).** Pausing does not cancel the timer. The one timer keeps running and the engine ignores ticks while paused. Restarting cancels any existing timer, so loops can never stack. |
| **Q4.11** Testing & docs | `pytest` (48 passing tests), Mermaid UML, `pdoc` HTML API docs, Game Programmer's Manual, and verbatim AI interaction log. | `v1_core_system/test_v1.py` (23) + `v2_platform_release/test_v2.py` (25); `verify_piece.py`, `verify_v05.py`; `Design_Document_UML.md`; `docs/api/`; `Game_Programmers_Manual.md`; `AI_Interaction_Log.md` + `AI_Interaction_Log_Part2.md` | `docs/phase4_pytest_output.txt`: 48 passed | **Met** |

**Summary.**
- **Met:** 9 rows (Q1, Q2, Q3, Q4.1, 4.4, 4.6, 4.7, 4.8, 4.11), plus Q4.10, which is met but works slightly differently from the answer.
- **Partly met:** 4 rows (Q4.2, 4.3, 4.5, 4.9), each wording more than is implemented.

**Smallest fixes**, either code or wording:
- add a `docs` subcommand (or say "docs via pdoc");
- build one PyInstaller executable;
- say "piece size fixed at 4".

---

## E. Feature → module → test index

| Feature | Module · symbol | Test(s) |
|---|---|---|
| 34 pieces / 110 orientations / 22 free | `piece.py` · `catalogue_stats`, `Piece.all_pieces` | `test_all_34_pieces`; `verify_piece.py` test 1 |
| Immutability of pieces | `piece.py` · `Piece.__setattr__`, `turned` | `verify_piece.py` test 5 |
| Constructive instantiation (holes + handedness) | `piece.py` · `ExTetromino.__new__`, `_lookup` | `verify_piece.py` tests 2–3 |
| Landing-hole signature | `piece.py` · `_landing_holes`, `ShapeInfo.hole_signature` | `verify_piece.py` test 3 |
| Handedness / chirality | `piece.py` · `Handedness`, `_spin4_imag` | `verify_piece.py` test 6 |
| Starter matrices compatibility | `piece.py` · `Piece.identify_matrix` | `test_starter_matrices_match_up_to_rotation`; `verify_piece.py` tests 7–8 |
| Families: presets 7/15/34 | `family.py` · `CLASSIC`, `EXTENDED_EASY`, `FULL` | `test_presets` |
| Families: 6 filters | `family.py` · `PieceFamily.filter` | `test_filters` |
| Families: set algebra | `family.py` · `include/exclude/union/intersection` | `test_set_algebra` |
| Uniform / weighted / by-property | `distribution.py` | `test_uniform_is_fair_...`, `test_weighted_and_by_property_match_probabilities` |
| Bag / adaptive / mixture | `distribution.py` | `test_bag_gives_each_piece_once_per_bag`, `test_adaptive_shortens_droughts_and_mixture_sums` |
| Seeded determinism | `distribution.py`, `engine.py` | `test_distributions_are_deterministic_per_seed`, `test_determinism_same_seed_same_game` |
| Solid vs wrap walls | `board.py` · `Board.fits` | `test_solid_walls_block_and_wrap_walls_wrap` |
| Naive vs cascade gravity | `board.py` · `Board.clear_rows` | `test_naive_vs_cascade_gravity` |
| Levels: threshold crossing, 1000·0.9^level | `state.py` · `LevelPolicy` | `test_level_policy_threshold_crossing_and_clamp` |
| Scoring / rules validation | `state.py` · `Scoring`, `Rules` | `test_scoring_and_rules_validation` |
| Headless engine, zero tkinter | `engine.py` | `test_engine_has_zero_tkinter` |
| Pause semantics | `engine.py` · `apply_action` | `test_pause_ignores_ticks_and_input` |
| Layered config defaults→spec→player→runtime | `engine.py` · `_effective`, `PLAYER_KEYS`, `RUNTIME_KEYS` | `test_layered_config_and_restrictions` |
| Tick-boundary dynamic updates | `engine.py` · `request_update`, `tick` | `test_runtime_updates_apply_only_at_tick_boundary` |
| Restricted conditional triggers | `engine.py` · `TRIGGER_CONDITIONS`, `_run_triggers`; `spec.py` · `TRIGGER_TARGETS` | `test_triggers_fire_once_and_are_restricted`, `test_trigger_translation_fires_in_engine` |
| JSON save/resume + SHA-256 variant hash | `engine.py` · `save`, `resume`, `variant_hash` | `test_save_resume_with_hash_verification` |
| 300 simulated games | `test_v1.py` · `_bot_game` | `test_300_simulated_games` |
| Tkinter renderer/controller | `tk_adapter.py` | `test_tk_adapter_smoke`, `test_play_with_customizer_smoke` |
| TOML schema + plain-English validator | `spec.py` · `VariantSpec`, `SpecValidator` | `test_validator_plain_english` (12 cases), `test_bad_toml_syntax_is_explained` |
| TOML writer | `spec.py` · `dump_toml` | `test_dump_toml_round_trip` |
| CLI new/validate/simulate | `cli.py` | `test_cli_new_validate_simulate` |
| Balance simulation | `simulator.py` · `simulate` | `test_simulate_showcase` (3 variants) |
| In-game customizer | `customizer.py` · `VariantCustomizer` | `test_with_changes_and_customizer_targets`, `test_play_with_customizer_smoke` |
| Packaging | `packager.py` · `build_package` | `test_package_is_self_contained` |
| Notebook | `Variant_Designer_Studio.ipynb` | `test_notebook_is_valid_nbformat4` (+ executed end-to-end with nbclient in the sandbox) |
| Showcase variants | `variants/*.toml` | `test_showcase_variants_exist_and_validate`; `docs/phase4_cli_output.txt` |
